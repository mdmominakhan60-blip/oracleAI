"""Fail when new/changed Palm golden records lack domain adjudication.

The manifest may be stored separately from raw images. This gate compares the
working-tree JSONL with a Git ref when available and validates only records that
were added or changed; the full manifest validator remains the source of truth.
"""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

from validate_palm_corpus import _validate_record
from validate_palm_reviewer_registry import validate as validate_reviewer_registry


def _records_from_text(text: str) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        item = json.loads(line)
        if not isinstance(item, dict) or not item.get("record_id"):
            raise ValueError(f"line {line_number}: record_id required")
        record_id = str(item["record_id"])
        if record_id in records:
            raise ValueError(f"duplicate record_id: {record_id}")
        records[record_id] = item
    return records


def _ref_exists(ref: str) -> bool:
    return subprocess.run(["git", "rev-parse", "--verify", ref], check=False, capture_output=True, text=True).returncode == 0


def _base_text(ref: str, path: str) -> str | None:
    try:
        return subprocess.run(
            ["git", "show", f"{ref}:{path}"], check=True, capture_output=True, text=True,
        ).stdout
    except subprocess.CalledProcessError:
        return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--reviewers", type=Path, required=True)
    parser.add_argument("--base-ref", default=None)
    args = parser.parse_args()
    if not args.manifest.is_file():
        print(json.dumps({"status": "SKIP", "reason": "manifest not supplied", "changed_records": []}, ensure_ascii=False))
        return 0
    errors: list[str] = []
    try:
        current = _records_from_text(args.manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"status": "FAIL", "errors": [str(exc)]}, ensure_ascii=False, indent=2))
        return 1
    base = {}
    if args.base_ref:
        if not _ref_exists(args.base_ref):
            errors.append(f"base ref is unavailable: {args.base_ref}")
        previous = _base_text(args.base_ref, str(args.manifest))
        if previous is not None:
            try:
                base = _records_from_text(previous)
            except (json.JSONDecodeError, ValueError) as exc:
                errors.append(f"base manifest invalid: {exc}")
    changed_ids = sorted(record_id for record_id, record in current.items() if record_id not in base or record != base[record_id])
    removed_ids = sorted(set(base) - set(current))
    reviewer_map: dict[str, dict[str, Any]] | None = None
    if not args.reviewers.is_file():
        errors.append(f"reviewer registry not supplied: {args.reviewers}")
    else:
        try:
            registry = json.loads(args.reviewers.read_text(encoding="utf-8"))
            errors.extend(f"reviewer registry: {error}" for error in validate_reviewer_registry(registry, require_domain=True))
            reviewer_map = {str(item["reviewer_id"]): item for item in (registry.get("reviewers") or []) if isinstance(item, dict) and item.get("reviewer_id")}
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"reviewer registry invalid: {exc}")
    if removed_ids:
        errors.extend(f"{record_id}: removal requires explicit corpus-owner review" for record_id in removed_ids)
    immutable_fields = ("image_path", "image_sha256", "split", "capture")
    for record_id in changed_ids:
        if record_id in base and (base[record_id].get("split") in {"test", "challenge"} or current[record_id].get("split") in {"test", "challenge"}):
            for field in immutable_fields:
                if base[record_id].get(field) != current[record_id].get(field):
                    errors.append(f"{record_id}: immutable {field} changed for test/challenge record")
        errors.extend(_validate_record(current[record_id], record_id, None, True, reviewer_map, True))
    result = {
        "status": "PASS" if not errors else "FAIL",
        "manifest": str(args.manifest),
        "base_ref": args.base_ref,
        "changed_records": changed_ids,
        "removed_records": removed_ids,
        "errors": errors,
        "policy": "every added/changed record must be independently annotated and domain-adjudicated",
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
