"""Validate Palm golden-corpus manifests without exposing raw images.

A manifest can be checked structurally with --schema-only, or checked against
an external protected image root with exact SHA-256/signature validation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from PIL import Image, UnidentifiedImageError

ROOT = Path(__file__).resolve().parents[1]
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
HEX64 = re.compile(r"^[a-f0-9]{64}$")
ID = re.compile(r"^[a-z0-9][a-z0-9._-]{2,95}$")
FORBIDDEN_KEYS = {"raw_image", "image_bytes", "data_url", "provider_response", "raw_provider_output"}
VALID_STATES = {"observed", "inferred", "unknown", "not_supported"}
VALID_VISIBILITY = {"clear", "partial", "unclear", "not_visible"}
VALID_BANDS = {"zero", "low", "medium", "high"}
VALID_TOPICS = {
    "life_line", "head_line", "heart_line", "fate_line", "sun_line", "mercury_line",
    "relationship_lines", "children_lines", "travel_lines", "girdle_of_venus",
    "ring_of_solomon", "ring_of_apollo", "via_lasciva", "mars_lines", "influence_lines",
    "bracelets", "mounts", "fingers", "markings", "palm_region",
}
REVIEWER_ROLES = {"annotator", "domain_reviewer", "safety_reviewer"}


def _walk_forbidden(value: Any, path: str, errors: list[str]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).lower() in FORBIDDEN_KEYS:
                errors.append(f"{path}.{key}: raw/provider content is forbidden")
            _walk_forbidden(child, f"{path}.{key}", errors)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _walk_forbidden(child, f"{path}[{index}]", errors)


def _required(obj: dict[str, Any], keys: tuple[str, ...], path: str, errors: list[str]) -> None:
    for key in keys:
        if key not in obj:
            errors.append(f"{path}: missing {key}")


def _validate_record(
    record: Any,
    index: int,
    image_root: Path | None,
    schema_only: bool,
    reviewer_map: dict[str, dict[str, Any]] | None = None,
    require_adjudicated: bool = False,
) -> list[str]:
    errors: list[str] = []
    path = f"record[{index}]"
    if not isinstance(record, dict):
        return [f"{path}: record must be an object"]
    _walk_forbidden(record, path, errors)
    _required(record, ("record_id", "image_path", "image_sha256", "source", "consent", "split", "capture", "regions", "expected_claims", "prohibited_claims", "adjudication"), path, errors)
    record_id = record.get("record_id")
    if not isinstance(record_id, str) or not ID.fullmatch(record_id):
        errors.append(f"{path}.record_id: invalid stable id")
    image_path = record.get("image_path")
    relative = None
    if not isinstance(image_path, str) or image_path.startswith("/") or ".." in Path(image_path).parts:
        errors.append(f"{path}.image_path: must be a relative protected path")
    else:
        relative = Path(image_path)
        if relative.suffix.lower() not in ALLOWED_EXTENSIONS:
            errors.append(f"{path}.image_path: unsupported extension")
    digest = record.get("image_sha256")
    if not isinstance(digest, str) or not HEX64.fullmatch(digest):
        errors.append(f"{path}.image_sha256: expected lowercase SHA-256")
    source = record.get("source")
    if not isinstance(source, dict):
        errors.append(f"{path}.source: object required")
    else:
        _required(source, ("kind", "license_or_permission", "collected_at"), f"{path}.source", errors)
        if source.get("kind") not in {"consented_user", "synthetic_contract", "public_permitted", "internal_fixture"}:
            errors.append(f"{path}.source.kind: unsupported provenance kind")
    consent = record.get("consent")
    if not isinstance(consent, dict):
        errors.append(f"{path}.consent: object required")
    else:
        _required(consent, ("status", "raw_image_retention", "review_use"), f"{path}.consent", errors)
        if consent.get("status") not in {"granted", "synthetic_no_person", "not_applicable"}:
            errors.append(f"{path}.consent.status: invalid")
        if consent.get("review_use") is not True:
            errors.append(f"{path}.consent.review_use: must be true")
    if record.get("split") not in {"train", "dev", "test", "challenge"}:
        errors.append(f"{path}.split: invalid split")
    capture = record.get("capture")
    if not isinstance(capture, dict):
        errors.append(f"{path}.capture: object required")
    else:
        _required(capture, ("quality_state", "view_type", "hand_count", "hand_side", "expected_user_action"), f"{path}.capture", errors)
        if capture.get("quality_state") not in {"usable", "reshoot_recommended", "invalid_image"}:
            errors.append(f"{path}.capture.quality_state: invalid")
        if capture.get("view_type") not in {"open_palm", "folded_edge", "unclear", "not_applicable"}:
            errors.append(f"{path}.capture.view_type: invalid")
        if not isinstance(capture.get("hand_count"), int) or not 0 <= capture.get("hand_count", -1) <= 2:
            errors.append(f"{path}.capture.hand_count: expected integer 0..2")
        if capture.get("expected_user_action") not in {"analyze", "reshoot", "reject"}:
            errors.append(f"{path}.capture.expected_user_action: invalid")
    regions = record.get("regions")
    if not isinstance(regions, list) or not regions:
        errors.append(f"{path}.regions: at least one region label required")
    else:
        for region_index, region in enumerate(regions):
            rpath = f"{path}.regions[{region_index}]"
            if not isinstance(region, dict):
                errors.append(f"{rpath}: object required")
                continue
            _required(region, ("region_id", "topic", "visibility", "evidence_state", "expected_confidence_band", "annotator_refs"), rpath, errors)
            if region.get("topic") not in VALID_TOPICS:
                errors.append(f"{rpath}.topic: unsupported region topic")
            if region.get("visibility") not in VALID_VISIBILITY:
                errors.append(f"{rpath}.visibility: invalid")
            if region.get("evidence_state") not in VALID_STATES:
                errors.append(f"{rpath}.evidence_state: invalid")
            if region.get("expected_confidence_band") not in VALID_BANDS:
                errors.append(f"{rpath}.expected_confidence_band: invalid")
            refs = region.get("annotator_refs")
            if not isinstance(refs, list) or len(refs) < 2 or len(set(refs)) < 2:
                errors.append(f"{rpath}.annotator_refs: two independent reviewers required")
            if region.get("visibility") == "not_visible" and region.get("evidence_state") in {"observed", "inferred"}:
                errors.append(f"{rpath}: not_visible cannot be observed/inferred")
            if region.get("evidence_state") in {"unknown", "not_supported"} and region.get("expected_confidence_band") != "zero":
                errors.append(f"{rpath}: unknown/not_supported must use zero confidence band")
            for box_key in ("bbox_norm",):
                if box_key in region:
                    box = region[box_key]
                    if not isinstance(box, list) or len(box) != 4 or any(not isinstance(v, (int, float)) or not 0 <= v <= 1 for v in box):
                        errors.append(f"{rpath}.{box_key}: normalized four-number box required")
    adjudication = record.get("adjudication")
    if not isinstance(adjudication, dict):
        errors.append(f"{path}.adjudication: object required")
    else:
        _required(adjudication, ("status", "annotators", "domain_reviewer_required"), f"{path}.adjudication", errors)
        annotators = adjudication.get("annotators")
        if not isinstance(annotators, list) or len(annotators) < 2 or len(set(annotators)) < 2:
            errors.append(f"{path}.adjudication.annotators: two independent reviewers required")
        if adjudication.get("domain_reviewer_required") is not True:
            errors.append(f"{path}.adjudication.domain_reviewer_required: must be true")
        if adjudication.get("status") not in {"pending", "independently_labeled", "adjudicated", "rejected"}:
            errors.append(f"{path}.adjudication.status: invalid")
        if require_adjudicated and adjudication.get("status") != "adjudicated":
            errors.append(f"{path}.adjudication.status: adjudicated record required")
        domain_reviewer = adjudication.get("domain_reviewer")
        if adjudication.get("status") == "adjudicated" and not domain_reviewer:
            errors.append(f"{path}.adjudication.domain_reviewer: required for adjudicated record")
        if reviewer_map is not None:
            annotator_ids = [str(item) for item in (annotators or [])]
            if domain_reviewer and str(domain_reviewer) in annotator_ids:
                errors.append(f"{path}.adjudication: domain reviewer must be independent from annotators")
            for reviewer_id in annotator_ids + ([str(domain_reviewer)] if domain_reviewer else []):
                reviewer = reviewer_map.get(reviewer_id)
                if not reviewer:
                    errors.append(f"{path}.adjudication: reviewer not found in registry: {reviewer_id}")
                    continue
                if reviewer.get("active") is not True or reviewer.get("independence") != "independent":
                    errors.append(f"{path}.adjudication: reviewer is inactive or ineligible: {reviewer_id}")
                attestation = reviewer.get("attestation") or {}
                if attestation.get("signed") is not True or attestation.get("policy_version") != "palm-human-review-v1":
                    errors.append(f"{path}.adjudication: reviewer attestation invalid: {reviewer_id}")
                if not reviewer.get("qualification_reference"):
                    errors.append(f"{path}.adjudication: reviewer qualification reference missing: {reviewer_id}")
                if reviewer.get("conflict_of_interest") not in {"none", "disclosed"}:
                    errors.append(f"{path}.adjudication: reviewer conflict declaration invalid: {reviewer_id}")
                if attestation.get("blinded_review") is not True:
                    errors.append(f"{path}.adjudication: blinded-review attestation missing: {reviewer_id}")
                roles = set(reviewer.get("roles") or [])
                required_role = "domain_reviewer" if domain_reviewer and reviewer_id == str(domain_reviewer) else "annotator"
                if required_role not in roles or not roles.issubset(REVIEWER_ROLES):
                    errors.append(f"{path}.adjudication: reviewer role invalid: {reviewer_id}")
    if image_root is not None and not schema_only and relative is not None:
        image_file = image_root / relative
        if not image_file.is_file():
            errors.append(f"{path}.image_path: protected image does not exist")
        else:
            try:
                with Image.open(image_file) as image:
                    image.verify()
                with Image.open(image_file) as image:
                    if str(image.format or "").upper() not in ALLOWED_FORMATS:
                        errors.append(f"{path}.image_path: signature is not JPEG/PNG/WebP")
                actual_digest = hashlib.sha256(image_file.read_bytes()).hexdigest()
                if actual_digest != digest:
                    errors.append(f"{path}.image_sha256: hash mismatch")
            except (OSError, UnidentifiedImageError):
                errors.append(f"{path}.image_path: unreadable image")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--image-root", type=Path, default=None)
    parser.add_argument("--schema-only", action="store_true")
    parser.add_argument("--reviewers", type=Path, default=None)
    parser.add_argument("--require-adjudicated", action="store_true")
    args = parser.parse_args()
    errors: list[str] = []
    reviewer_map: dict[str, dict[str, Any]] | None = None
    if args.reviewers is not None:
        if not args.reviewers.is_file():
            errors.append(f"reviewer registry not found: {args.reviewers}")
        else:
            try:
                registry = json.loads(args.reviewers.read_text(encoding="utf-8"))
                if registry.get("registry_version") != "palm-reviewers-v1":
                    errors.append("reviewer registry version is invalid")
                reviewer_map = {}
                for reviewer in registry.get("reviewers") or []:
                    reviewer_id = reviewer.get("reviewer_id")
                    if not isinstance(reviewer_id, str) or reviewer_id in reviewer_map:
                        errors.append("reviewer registry contains invalid or duplicate reviewer_id")
                    else:
                        reviewer_map[reviewer_id] = reviewer
            except (OSError, json.JSONDecodeError) as exc:
                errors.append(f"reviewer registry unreadable: {exc}")
    records = 0
    if not args.manifest.is_file():
        errors.append(f"manifest not found: {args.manifest}")
    else:
        for index, line in enumerate(args.manifest.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                errors.append(f"line {index}: invalid JSON: {exc.msg}")
                continue
            records += 1
            errors.extend(_validate_record(record, records, args.image_root, args.schema_only, reviewer_map, args.require_adjudicated))
    output = {"manifest": str(args.manifest), "records": records, "errors": errors, "status": "PASS" if not errors else "FAIL"}
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
