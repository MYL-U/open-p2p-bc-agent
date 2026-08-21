#!/usr/bin/env python3
"""UDS inference client for the Open P2P behavior-cloning agent (course D3).

Reads the toy VideoAnnotation dataset (one `*.proto` annotation + a sibling
video, e.g. `192x192.mp4`), sends every frame to the UDS inference server as a
`Frame` message and writes the received `Action` into a predictions JSONL file.

Wire protocol (see elefant/inference/unix_socket_server.py):
    send: [uint32 LE length][Frame.SerializeToString()]
    recv: [uint32 LE length][Action.SerializeToString()]
Frame.data is raw RGB bytes in HWC layout (no JPEG); the server resizes to
192x192 when needed. The output JSONL schema is documented in
docs/API_CONTRACT.md (section "predictions JSONL").

Run on the server inside the repo uv environment:

    uv run python scripts/collect_predictions.py \
        --dataset dataset --uds-path /tmp/uds.recap \
        --output predictions/predictions.jsonl \
        --max-videos 3 --max-frames 200
"""

from __future__ import annotations

import argparse
import json
import os
import random
import socket
import sys


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument(
        "--dataset", required=True,
        help="toy dataset root: recursively find *.proto annotations and their sibling videos",
    )
    p.add_argument(
        "--uds-path", default="/tmp/uds.recap",
        help="UDS socket path of the inference server (default: /tmp/uds.recap)",
    )
    p.add_argument(
        "--output", default="predictions/predictions.jsonl",
        help="output predictions JSONL path (default: predictions/predictions.jsonl)",
    )
    p.add_argument(
        "--video-name", default="192x192.mp4",
        help="video file name expected next to each *.proto (default: 192x192.mp4)",
    )
    p.add_argument("--max-videos", type=int, default=None,
                   help="limit how many videos to process (testing)")
    p.add_argument("--max-frames", type=int, default=None,
                   help="limit total frames processed (testing)")
    p.add_argument("--frame-timeout", type=float, default=15.0,
                   help="per-frame recv timeout in seconds (default: 15.0)")
    p.add_argument("--reconnect-max", type=int, default=5,
                   help="give up after this many consecutive failures (default: 5)")
    p.add_argument("--seed", type=int, default=None,
                   help="shuffle the video order deterministically (reproducibility)")
    p.add_argument("--append", action="store_true",
                   help="append to --output instead of overwriting it (resume)")
    return p


def import_protos():
    """Import the generated protobuf modules from the repo.

    The script must run inside the repo uv environment so that `elefant`
    is importable.
    """
    try:
        from elefant.data.proto import video_annotation_pb2  # noqa: F401
        from elefant.data.proto import video_inference_pb2  # noqa: F401
        from elefant.data.proto import shared_pb2  # noqa: F401
        return video_annotation_pb2, video_inference_pb2, shared_pb2
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            "Cannot import elefant proto modules. Run inside the repo uv "
            f"environment, e.g. `uv run python scripts/collect_predictions.py ...`. "
            f"Original error: {exc}"
        ) from exc


def find_examples(root: str, video_name: str):
    """Return sorted [(proto_path, video_path)] pairs under root."""
    examples = []
    for dirpath, _dirs, files in os.walk(root):
        for name in files:
            if name.endswith(".proto"):
                proto_path = os.path.join(dirpath, name)
                video_path = os.path.join(dirpath, video_name)
                if os.path.exists(video_path):
                    examples.append((proto_path, video_path))
    examples.sort()
    return examples


def load_video_tensor(path: str):
    """Decode a video into a uint8 RGB tensor [T, H, W, 3].

    Prefers torchvision (video already named for the model input size), falls
    back to torchcodec. Returns None when the file cannot be decoded.
    """
    try:
        import torch
        import torchvision.io as tvi

        video, _audio, _meta = tvi.read_video(
            path, pts_unit="sec", output_format="HWC"
        )
        if video.dtype != torch.uint8:
            video = video.to(torch.uint8)
        return video
    except Exception as exc:  # noqa: BLE001
        try:
            import torch
            from torchcodec.decoders import VideoDecoder

            decoder = VideoDecoder(path, device="cpu")
            return torch.stack([torch.as_tensor(frame) for frame in decoder])
        except Exception as exc2:  # noqa: BLE001
            print(
                f"[warn] cannot decode {path}: torchvision: {exc}; "
                f"torchcodec: {exc2}",
                file=sys.stderr,
            )
            return None


def read_exact(sock: socket.socket, n: int) -> bytes:
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("socket closed by peer")
        buf += chunk
    return buf


class UDSClient:
    """Thin [4B LE len][protobuf] framed client for the UDS server."""

    def __init__(self, path: str, timeout: float):
        self.path = path
        self.timeout = timeout
        self.sock: socket.socket | None = None
        self.connect()

    def connect(self) -> None:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        sock.connect(self.path)
        self.sock = sock

    def send_frame(self, frame) -> None:
        payload = frame.SerializeToString()
        self.sock.sendall(len(payload).to_bytes(4, "little") + payload)

    def recv_action(self):
        self.sock.settimeout(self.timeout)
        length = int.from_bytes(read_exact(self.sock, 4), "little")
        body = read_exact(self.sock, length)
        return video_inference_pb2.Action.FromString(body)

    def reconnect(self) -> None:
        self.close()
        self.connect()

    def close(self) -> None:
        if self.sock is not None:
            self.sock.close()
            self.sock = None


def build_record(ann, video_path: str, index: int, n_annot: int) -> dict:
    """Baseline record for frame `index`; pred fields filled after the roundtrip."""
    video_id = getattr(ann, "metadata", None).id if hasattr(ann, "metadata") else None
    if not video_id:
        video_id = os.path.basename(os.path.dirname(video_path))
    frame_ts = None
    is_known = False
    if index < n_annot:
        fa = ann.frame_annotations[index]
        frame_ts = int(fa.frame_time)
        is_known = bool(fa.user_action.is_known)
    return {
        "video_id": video_id,
        "frame_index": index,
        "frame_ts": frame_ts,
        "pred_keyboard": None,
        "pred_mouse": None,
        "is_known": is_known,
        "error": "pending",
    }


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)

    global video_inference_pb2  # noqa: PLW0603  (used by UDSClient.recv_action)
    video_annotation_pb2, video_inference_pb2, _shared_pb2 = import_protos()

    examples = find_examples(args.dataset, args.video_name)
    if not examples:
        print(f"error: no {args.video_name} + *.proto pairs found under {args.dataset}",
              file=sys.stderr)
        return 1
    if args.seed is not None:
        random.Random(args.seed).shuffle(examples)
    if args.max_videos is not None:
        examples = examples[: args.max_videos]

    out_dir = os.path.dirname(os.path.abspath(args.output))
    os.makedirs(out_dir, exist_ok=True)
    out = open(args.output, "a" if args.append else "w", encoding="utf-8")

    client = UDSClient(args.uds_path, args.frame_timeout)
    stats = {"videos": 0, "frames": 0, "ok": 0, "failed": 0, "skipped": 0}
    consecutive_failures = 0
    global_index = 0

    for proto_path, video_path in examples:
        if args.max_frames is not None and stats["frames"] >= args.max_frames:
            break

        ann = video_annotation_pb2.VideoAnnotation()
        try:
            with open(proto_path, "rb") as fh:
                ann.ParseFromString(fh.read())
        except Exception as exc:  # noqa: BLE001
            print(f"[warn] skip annotation {proto_path}: {exc}", file=sys.stderr)
            stats["skipped"] += 1
            continue

        video = load_video_tensor(video_path)
        if video is None:
            stats["skipped"] += 1
            continue
        n_frames = int(video.shape[0])
        n_annot = len(ann.frame_annotations)
        stats["videos"] += 1

        for i in range(n_frames):
            if args.max_frames is not None and stats["frames"] >= args.max_frames:
                break

            rec = build_record(ann, video_path, i, n_annot)
            frame = video_inference_pb2.Frame(
                id=global_index,
                width=int(video.shape[2]),
                height=int(video.shape[1]),
                data=video[i].numpy().tobytes(),
            )

            try:
                client.send_frame(frame)
                action = client.recv_action()
                mouse = action.mouse_action
                rec["pred_keyboard"] = list(action.keys)
                rec["pred_mouse"] = {
                    "delta_x": int(mouse.mouse_delta_px.x),
                    "delta_y": int(mouse.mouse_delta_px.y),
                    "scroll_x": int(mouse.scroll_delta_px.x),
                    "scroll_y": int(mouse.scroll_delta_px.y),
                    "buttons": list(mouse.buttons_down),
                }
                rec["error"] = None
                stats["ok"] += 1
                consecutive_failures = 0
            except (socket.timeout, OSError, ConnectionError) as exc:
                rec["error"] = f"{type(exc).__name__}: {exc}"
                stats["failed"] += 1
                consecutive_failures += 1
                try:
                    client.reconnect()
                except OSError as exc2:
                    rec["error"] += f"; reconnect failed: {exc2}"
                if consecutive_failures >= args.reconnect_max:
                    out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    out.flush()
                    print(
                        f"giving up after {consecutive_failures} consecutive failures "
                        f"(last error: {rec['error']})",
                        file=sys.stderr,
                    )
                    client.close()
                    out.close()
                    return 1

            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
            out.flush()
            stats["frames"] += 1
            global_index += 1

    client.close()
    out.close()
    print(json.dumps(stats))
    return 0 if stats["failed"] == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
