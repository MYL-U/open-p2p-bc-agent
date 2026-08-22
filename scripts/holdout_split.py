#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""holdout_split.py — 按视频划分 train/holdout，供评测参照。

设计：以「视频」为最小划分单位（绝不按帧切，避免同一视频的帧跨 train/holdout 泄漏）。
用法：
  python scripts/holdout_split.py --dataset dataset --output holdout_split.json
  python scripts/holdout_split.py --dataset dataset --output holdout_split.json --holdout-videos <uuid> [<uuid>...]
  python scripts/holdout_split.py --dataset dataset --output holdout_split.json --ratio 0.3 --seed 42

输出：holdout_split.json = {"splits": {"train": ["<uuid>", ...], "holdout": ["<uuid>", ...]}, "overlap_ok": true, ...}
"""
import argparse
import json
import random
import sys
from pathlib import Path


def find_videos(dataset_dir):
    """扫描 dataset 下每个 <uuid>/ 目录，以存在 192x192.mp4 视为有效视频。"""
    videos = []
    for d in sorted(Path(dataset_dir).iterdir()):
        if not d.is_dir():
            continue
        has_mp4 = (d / "192x192.mp4").is_file()
        has_proto = (d / "annotation.proto").is_file()
        if has_mp4 or has_proto:
            videos.append({"id": d.name, "mp4": has_mp4, "proto": has_proto})
    return videos


def main():
    ap = argparse.ArgumentParser(description="按视频划分 train/holdout 并做重叠校验")
    ap.add_argument("--dataset", required=True, help="dataset 目录（含 <uuid>/192x192.mp4 与 annotation.proto）")
    ap.add_argument("--output", default="holdout_split.json", help="输出 JSON 路径")
    grp = ap.add_mutually_exclusive_group()
    grp.add_argument("--holdout-videos", nargs="+", default=None, help="显式指定 holdout 视频 UUID 列表")
    grp.add_argument("--ratio", type=float, default=0.0, help="按比例随机划分 holdout（如 0.3），配合 --seed")
    ap.add_argument("--seed", type=int, default=0, help="随机种子")
    args = ap.parse_args()

    videos = find_videos(args.dataset)
    if not videos:
        print("ERROR: no videos found under --dataset", args.dataset, file=sys.stderr)
        sys.exit(1)

    all_ids = [v["id"] for v in videos]

    if args.holdout_videos is not None:
        holdout = args.holdout_videos
        missing = [v for v in holdout if v not in all_ids]
        if missing:
            print("ERROR: holdout videos not in dataset:", missing, file=sys.stderr)
            sys.exit(1)
        train = [v for v in all_ids if v not in holdout]
        if not train:
            print("ERROR: train split is empty", file=sys.stderr)
            sys.exit(1)
    else:
        n = int(round(len(all_ids) * args.ratio)) if args.ratio > 0 else 1
        n = max(1, min(n, len(all_ids) - 1))
        rng = random.Random(args.seed)
        pool = list(all_ids)
        rng.shuffle(pool)
        holdout = sorted(pool[:n])
        train = sorted(pool[n:])

    overlap = sorted(set(train) & set(holdout))

    result = {
        "splits": {"train": train, "holdout": holdout},
        "counts": {"train": len(train), "holdout": len(holdout), "total": len(all_ids)},
        "overlap_ok": not overlap,
        "overlap_videos": overlap,
        "criteria": "by_video (no frame-level cross-split leakage)",
    }
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("wrote", out)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if overlap:
        print("WARNING: overlap detected:", overlap, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
