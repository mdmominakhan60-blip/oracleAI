"""Evaluate Palm predictions against an adjudicated golden manifest.

This runner accepts only structured predictions. It never accepts raw images or
provider payloads and it never calls an LLM. Semantic sign-off is blocked when
labels are pending, coverage is incomplete, capture state mismatches, or an
unknown/not-supported region is promoted to observed/inferred.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

SAFE_KEYS = {"record_id", "quality_state", "status", "view_type", "observations", "processing_metrics"}
FORBIDDEN_KEYS = {"raw_image", "image_bytes", "data_url", "provider_response", "raw_provider_output"}
VALID_STATES = {"observed", "inferred", "unknown", "not_supported"}
VALID_VISIBILITY = {"clear", "partial", "unclear", "not_visible"}


def _load_jsonl(path: Path) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        item = json.loads(line)
        if not isinstance(item, dict) or not item.get("record_id"):
            raise ValueError(f"{path}:{line_number}: record_id required")
        record_id = str(item["record_id"])
        if record_id in rows:
            raise ValueError(f"{path}:{line_number}: duplicate record_id {record_id}")
        rows[record_id] = item
    return rows


def _forbidden_paths(value: Any, path: str = "prediction") -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if str(key).lower() in FORBIDDEN_KEYS:
                found.append(child_path)
            found.extend(_forbidden_paths(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(_forbidden_paths(child, f"{path}[{index}]"))
    return found


def _prediction_map(prediction: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], list[str]]:
    observations = prediction.get("observations") or []
    output: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    if not isinstance(observations, list):
        return output, ["observations must be an array"]
    for index, item in enumerate(observations):
        if not isinstance(item, dict) or not item.get("topic"):
            errors.append(f"observations[{index}] missing topic")
            continue
        topic = str(item["topic"])
        if topic in output:
            errors.append(f"duplicate observation topic: {topic}")
            continue
        state = str(item.get("evidence_state") or "unknown")
        visibility = str(item.get("visibility") or "unclear")
        if state not in VALID_STATES:
            errors.append(f"{topic}: invalid evidence_state {state}")
        if visibility not in VALID_VISIBILITY:
            errors.append(f"{topic}: invalid visibility {visibility}")
        output[topic] = item
    return output, errors


def _band(confidence: Any) -> str:
    try:
        value = float(confidence)
    except (TypeError, ValueError):
        return "zero"
    if value <= 0:
        return "zero"
    if value < 0.5:
        return "low"
    if value < 0.8:
        return "medium"
    return "high"


def evaluate(manifest: dict[str, dict[str, Any]], predictions: dict[str, dict[str, Any]]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    missing_predictions = sorted(set(manifest) - set(predictions))
    unexpected_predictions = sorted(set(predictions) - set(manifest))
    for record_id, record in manifest.items():
        adjudication = record.get("adjudication") or {}
        record_ready = adjudication.get("status") == "adjudicated" and bool(adjudication.get("domain_reviewer"))
        prediction = predictions.get(record_id) or {}
        predicted, prediction_errors = _prediction_map(prediction)
        prediction_errors.extend(_forbidden_paths(prediction))
        expected_capture = record.get("capture") or {}
        capture_match = (
            prediction.get("quality_state") == expected_capture.get("quality_state")
            and prediction.get("view_type", expected_capture.get("view_type")) == expected_capture.get("view_type")
        )
        region_results: list[dict[str, Any]] = []
        for region in record.get("regions") or []:
            topic = str(region.get("topic"))
            actual = predicted.get(topic) or {}
            expected_state = region.get("evidence_state")
            actual_state = str(actual.get("evidence_state") or "unknown")
            expected_visibility = region.get("visibility")
            actual_visibility = str(actual.get("visibility") or "unclear")
            false_observed = expected_state in {"unknown", "not_supported"} and actual_state in {"observed", "inferred"}
            state_match = actual_state == expected_state
            visibility_match = actual_visibility == expected_visibility
            region_results.append({
                "topic": topic, "expected_state": expected_state, "actual_state": actual_state,
                "expected_visibility": expected_visibility, "actual_visibility": actual_visibility,
                "expected_band": region.get("expected_confidence_band"),
                "actual_band": _band(actual.get("confidence")),
                "state_match": state_match, "visibility_match": visibility_match,
                "false_observed": false_observed,
            })
        region_count = len(region_results)
        rows.append({
            "record_id": record_id,
            "adjudicated": record_ready,
            "capture_state_match": capture_match,
            "prediction_errors": prediction_errors,
            "regions": region_results,
            "region_state_accuracy": round(sum(r["state_match"] for r in region_results) / region_count, 4) if region_count else 0.0,
            "false_observed_count": sum(r["false_observed"] for r in region_results),
        })
    all_regions = [region for row in rows for region in row["regions"]]
    false_observed = sum(row["false_observed_count"] for row in rows)
    state_matches = sum(region["state_match"] for region in all_regions)
    visibility_matches = sum(region["visibility_match"] for region in all_regions)
    pending = sum(1 for row in rows if not row["adjudicated"])
    capture_mismatches = sum(1 for row in rows if not row["capture_state_match"])
    malformed = sum(len(row["prediction_errors"]) for row in rows)
    critical = false_observed > 0
    ready = bool(rows) and not missing_predictions and not unexpected_predictions and pending == 0 and capture_mismatches == 0 and malformed == 0 and not critical
    block_reasons = []
    if pending:
        block_reasons.append("manifest has pending/non-adjudicated records")
    if missing_predictions or unexpected_predictions:
        block_reasons.append("prediction coverage does not exactly match manifest")
    if capture_mismatches:
        block_reasons.append("capture quality/view state mismatch detected")
    if malformed:
        block_reasons.append("malformed or privacy-unsafe structured prediction detected")
    if critical:
        block_reasons.append("critical false-observed region promotion detected")
    if not rows or not all_regions:
        block_reasons.append("empty manifest or regions")
    return {
        "runner": "palm-human-domain-review-v1",
        "records": len(rows),
        "regions": len(all_regions),
        "missing_predictions": missing_predictions,
        "unexpected_predictions": unexpected_predictions,
        "pending_adjudication_records": pending,
        "metrics": {
            "region_state_accuracy": round(state_matches / len(all_regions), 4) if all_regions else 0.0,
            "region_visibility_accuracy": round(visibility_matches / len(all_regions), 4) if all_regions else 0.0,
            "false_observed_count": false_observed,
            "unknown_safety_precision": round(1 - (false_observed / len(all_regions)), 4) if all_regions else 0.0,
            "capture_state_mismatches": capture_mismatches,
            "malformed_prediction_count": malformed,
        },
        "semantic_signoff": "PASS" if ready else "BLOCKED",
        "block_reasons": block_reasons,
        "rows": rows,
        "privacy_check": "structured predictions only; raw image/provider payload not accepted by contract",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    manifest = _load_jsonl(args.manifest)
    predictions = _load_jsonl(args.predictions)
    for record_id, prediction in predictions.items():
        forbidden = sorted(set(prediction) - SAFE_KEYS)
        if forbidden:
            raise ValueError(f"{record_id}: prediction contains forbidden keys: {forbidden}")
    result = evaluate(manifest, predictions)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("runner", "records", "regions", "metrics", "semantic_signoff", "block_reasons")}, ensure_ascii=False, indent=2))
    return 0 if result["semantic_signoff"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
