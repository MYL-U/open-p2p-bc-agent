#!/usr/bin/env python3
"""Evaluate predictions JSONL against toy VideoAnnotation labels (course D5).

Metrics (docs/API_CONTRACT.md §4):
- keyboard agreement rate: predicted key SET == annotated key SET (exact match)
- mouse Pearson correlation: decoded pixel deltas (x and y separately)

Reference levels from the official agent: ≈55% keyboard / ≈0.5 mouse r.
We report what we measure; these values are NOT pass/fail criteria.

Frame alignment:
- The collector writes one JSONL row per video frame with `video_id` and
  `frame_index` (frame ordinal inside the video, 0-based).
- The annotation `*.proto` holds `frame_annotations` in the same order as video
  frames; frame `i` of the video maps to `frame_annotations[i]`.
- Only frames with `is_known == true`, `error == null` and
  `frame_index < len(frame_annotations)` take part in the metrics.

Run on the server inside the repo uv environment:

    uv run python scripts/evaluate.py \
        --predictions predictions/predictions.jsonl \
        --dataset dataset \
        --output metrics/metrics.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys

try:
    import numpy as np
except ImportError:  # pragma: no cover
    np = None


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--predictions", required=True,
                   help="predictions JSONL produced by scripts/collect_predictions.py")
    p.add_argument("--dataset", required=True,
                   help="toy dataset root used to find *.proto annotations")
    p.add_argument("--output", default="metrics/metrics.json",
                   help="metrics JSON output path (default: metrics/metrics.json)")
    p.add_argument("--per-video", action="store_true",
                   help="also emit per-video metric breakdown")
    return p


def import_protos():
    try:
        from elefant.data.proto import video_annotation_pb2  # noqa: F401
        return video_annotation_pb2
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            "Cannot import elefant proto modules. Run inside the repo uv "
            f"environment. Original error: {exc}"
        ) from exc


def find_protos(root: str):
    """Return sorted list of *.proto paths under root."""
    out = []
    for dirpath, _dirs, files in os.walk(root):
        for name in files:
            if name.endswith(".proto"):
                out.append(os.path.join(dirpath, name))
    out.sort()
    return out


def annotation_index(anns_root: str, video_id: str, proto_mod):
    """Build {video_id: (proto_path, annotations)} for all dataset annotations."""
    index = {}
    for proto_path in find_protos(anns_root):
        ann = proto_mod.VideoAnnotation()
        try:
            with open(proto_path, "rb") as fh:
                ann.ParseFromString(fh.read())
        except Exception as exc:  # noqa: BLE001
            print(f"[warn] unparsable annotation {proto_path}: {exc}", file=sys.stderr)
            continue
        vid = None
        try:
            vid = ann.metadata.id
        except Exception:  # noqa: BLE001
            vid = None
        if not vid:
            vid = os.path.basename(os.path.dirname(proto_path))
        if vid in index:
            print(f"[warn] duplicate video_id {vid!r}: keeping first", file=sys.stderr)
            continue
        index[vid] = (proto_path, ann)
    return index


def pearson_r(xs, ys):
    """Pearson correlation coefficient; None when fewer than 2 points or zero std."""
    if np is not None:
        x = np.asarray(xs, dtype=np.float64)
        y = np.asarray(ys, dtype=np.float64)
        if x.size < 2:
            return None
        sx, sy = x.std(ddof=1), y.std(ddof=1)
        if sx == 0.0 or sy == 0.0:
            return None
        return float(np.corrcoef(x, y)[0, 1])
    n = len(xs)
    if n < 2:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    cov = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
    vx = sum((a - mx) ** 2 for a in xs)
    vy = sum((b - my) ** 2 for b in ys)
    if vx == 0 or vy == 0:
        return None
    return cov / (vx * vy) ** 0.5


def evaluate_row(rec, fa):
    """Return (key_hit, key_total, dx, dy, lx, ly) for one frame or None if skipped.

    key_total counts frames where the annotation has a known keyboard action;
    key_hit is 1 when the predicted key set equals the annotated set exactly.
    Mouse coordinates (dx, dy) are predicted deltas; (lx, ly) annotated deltas.
    """
    if rec.get("error"):
        return None
    if not rec.get("is_known"):
        return None
    ua = fa.user_action
    ann_keys = sorted(set(ua.keyboard.keys))
    pred_keys = sorted(set(rec.get("pred_keyboard") or []))
    key_hit = int(pred_keys == ann_keys)
    key_total = 1
    ann_mouse = ua.mouse
    pm = rec.get("pred_mouse") or {}
    dx, dy = pm.get("delta_x"), pm.get("delta_y")
    lx = ann_mouse.mouse_delta_px.x if ann_mouse.HasField("mouse_delta_px") else 0
    ly = ann_mouse.mouse_delta_px.y if ann_mouse.HasField("mouse_delta_px") else 0
    return key_hit, key_total, dx, dy, lx, ly


def main(argv=None) -> int:
    args = build_arg_parser().parse_args(argv)
    proto_mod = import_protos()

    rows = []
    try:
        with open(args.predictions, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
    except FileNotFoundError:
        print(f"error: predictions file not found: {args.predictions}", file=sys.stderr)
        return 1

    ann_index = annotation_index(args.dataset, None, proto_mod)
    if not ann_index:
        print(f"error: no annotations found under {args.dataset}", file=sys.stderr)
        return 1

    stats = {
        "predictions_rows": len(rows),
        "valid_frames": 0,
        "skipped_unknown": 0,
        "skipped_error": 0,
        "skipped_no_annotation": 0,
        "keyboard_frames": 0,
        "keyboard_hit": 0,
        "mouse_frames": 0,
        "per_video": {},
    }
    dxs, dys, lxs, lys = [], [], [], []

    for rec in rows:
        vid = rec.get("video_id")
        if vid not in ann_index:
            stats["skipped_no_annotation"] += 1
            continue
        _path, ann = ann_index[vid]
        idx = rec.get("frame_index")
        if idx is None or not isinstance(idx, int) or idx < 0:
            stats["skipped_no_annotation"] += 1
            continue
        if idx >= len(ann.frame_annotations):
            stats["skipped_no_annotation"] += 1
            continue
        fa = ann.frame_annotations[idx]
        if not rec.get("is_known"):
            stats["skipped_unknown"] += 1
            continue
        if rec.get("error"):
            stats["skipped_error"] += 1
            continue

        out = evaluate_row(rec, fa)
        if out is None:
            stats["skipped_unknown"] += 1
            continue
        key_hit, key_total, dx, dy, lx, ly = out
        stats["valid_frames"] += 1
        if key_total:
            stats["keyboard_frames"] += 1
            stats["keyboard_hit"] += key_hit
            if args.per_video:
                pv = stats["per_video"].setdefault(
                    vid, {"keyboard_frames": 0, "keyboard_hit": 0, "mouse_frames": 0}
                )
                pv["keyboard_frames"] += 1
                pv["keyboard_hit"] += key_hit
        if dx is not None and lx is not None:
            stats["mouse_frames"] += 1
            dxs.append(dx)
            dys.append(dy)
            lxs.append(lx)
            lys.append(ly)
            if args.per_video:
                pv = stats["per_video"].setdefault(
                    vid, {"keyboard_frames": 0, "keyboard_hit": 0, "mouse_frames": 0}
                )
                pv["mouse_frames"] += 1

    kf = stats["keyboard_frames"]
    mf = stats["mouse_frames"]
    metrics = {
        "frame_counts": {
            "predictions_rows": stats["predictions_rows"],
            "valid_frames": stats["valid_frames"],
            "skipped_unknown": stats["skipped_unknown"],
            "skipped_error": stats["skipped_error"],
            "skipped_no_annotation": stats["skipped_no_annotation"],
        },
        "keyboard_agreement_rate": (stats["keyboard_hit"] / kf) if kf else None,
        "keyboard_agreed_frames": stats["keyboard_hit"],
        "keyboard_frames": kf,
        "mouse_pearson_x": pearson_r(dxs, lxs) if mf else None,
        "mouse_pearson_y": pearson_r(dys, lys) if mf else None,
        "mouse_frames": mf,
    }
    if args.per_video:
        metrics["per_video"] = {
            vid: {
                "keyboard_agreement_rate": (
                    v["keyboard_hit"] / v["keyboard_frames"]
                ) if v["keyboard_frames"] else None,
                "keyboard_agreed_frames": v["keyboard_hit"],
                "keyboard_frames": v["keyboard_frames"],
                "mouse_frames": v["mouse_frames"],
            }
            for vid, v in sorted(stats["per_video"].items())
        }

    out_dir = os.path.dirname(os.path.abspath(args.output))
    os.makedirs(out_dir, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as fh:
        json.dump(metrics, fh, ensure_ascii=False, indent=2)
    print(json.dumps(metrics, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
