#!/usr/bin/env python3
"""Aggregate palm evidence metrics without fabricating semantic accuracy.

The input may be the JSON emitted by ``benchmark_palm_cv.py``. Semantic
precision/recall/F1/IoU stay null unless a separate annotated ground-truth
file is explicitly supplied and validated by a future evaluator.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


def percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    position = (len(ordered) - 1) * q
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def benchmark_summary(data: dict) -> dict:
    rows = data.get("results") or data.get("rows") or data.get("items") or []
    if isinstance(rows, dict):
        rows = list(rows.values())
    if not rows:
        raise ValueError("benchmark JSON has no result rows")
    hands = sum(bool((row.get("hand_geometry") or {}).get("hands")) for row in rows)
    precheck = [
        (row.get("precheck") or {}).get("score") for row in rows
        if isinstance((row.get("precheck") or {}).get("score"), (int, float))
    ]
    full_status = Counter((row.get("full_scope") or {}).get("status", "unknown") for row in rows)
    views = Counter((row.get("full_scope") or {}).get("view_type", "unknown") for row in rows)
    ensemble_status = Counter()
    agreement = Counter()
    major_lines = {name: 0 for name in ("heart_line", "head_line", "life_line")}
    raw_flags_clear = True
    for row in rows:
        ensemble = row.get("line_segmentation_ensemble") or {}
        ensemble_status[ensemble.get("status", "unknown")] += 1
        agreement[(ensemble.get("ensemble") or {}).get("status", "unknown")] += 1
        for name in major_lines:
            major_lines[name] += int(bool(((ensemble.get("lines") or {}).get(name) or {}).get("detected")))
        full = row.get("full_scope") or {}
        raw_flags_clear &= not full.get("raw_mask_stored", True)
        raw_flags_clear &= not full.get("raw_edge_map_stored", True)
        raw_flags_clear &= not ensemble.get("raw_mask_stored", True)
    return {
        "fixtures": len(rows),
        "hand_detected": hands,
        "hand_detection_rate": round(hands / len(rows), 4),
        "full_scope_status": dict(full_status),
        "view_type": dict(views),
        "precheck_score_mean": round(sum(precheck) / len(precheck), 4) if precheck else None,
        "precheck_score_p50": round(percentile(precheck, 0.5), 4) if precheck else None,
        "onnx_ensemble_status": dict(ensemble_status),
        "onnx_ensemble_agreement": dict(agreement),
        "major_line_detected": major_lines,
        "raw_flags_clear": raw_flags_clear,
    }


def user_series_summary(data: dict) -> dict:
    aggregate = data.get("aggregates")
    if aggregate:
        return {"frames": data.get("file_count"), **aggregate}
    keys = ("file_count", "detected", "no_lines", "needs_vision_review", "agreement", "raw_flags_clear")
    return {key: data[key] for key in keys if key in data}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True,
                        help="benchmark_palm_cv JSON")
    parser.add_argument("--user-series", type=Path,
                        help="optional aggregate JSON for a user photo series")
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = {
        "repository_benchmark": benchmark_summary(json.loads(args.input.read_text(encoding="utf-8"))),
        "user_series": None,
        "semantic_ground_truth_available": False,
        "semantic_precision_recall_f1_iou": None,
        "interpretation": "Operational evidence only; semantic metrics require annotated masks/polylines and adjudicated labels.",
    }
    if args.user_series:
        result["user_series"] = user_series_summary(json.loads(args.user_series.read_text(encoding="utf-8")))
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
