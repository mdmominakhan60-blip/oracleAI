"""Independent, context-light critic for the Palm/Mira accuracy gauntlet.

The critic checks deterministic source guardrails and reports whether a human/
domain review has actually supplied semantic evidence. It never treats mocks
or the absence of a manifest as accuracy data.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from validate_palm_reviewer_registry import validate as validate_reviewer_registry

ROOT = Path(__file__).resolve().parents[1]


def require(text: str, needle: str, label: str, failures: list[str]) -> None:
    if needle not in text:
        failures.append(f"missing {label}: {needle}")


def _load_review_report(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"semantic_signoff": "INVALID", "block_reasons": ["review report is unreadable"]}
    return value if isinstance(value, dict) else {"semantic_signoff": "INVALID"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=None)
    parser.add_argument("--reviewers", type=Path, default=None)
    parser.add_argument("--review-report", type=Path, default=None)
    args = parser.parse_args()
    failures: list[str] = []
    palm = ((ROOT / "app/core/palm/service.py").read_text(encoding="utf-8")
            + "\n" + (ROOT / "app/core/palm/prompts.py").read_text(encoding="utf-8"))
    landmarks = (ROOT / "app/core/palm_landmarks.py").read_text(encoding="utf-8")
    full_scope = (ROOT / "app/core/palm_full_scope.py").read_text(encoding="utf-8")
    skills = (ROOT / "app/core/tool_registry.py").read_text(encoding="utf-8")
    ui = (ROOT / "miniapp/js/13-palm.js").read_text(encoding="utf-8")
    locale = (ROOT / "miniapp/js/12-misc.js").read_text(encoding="utf-8")
    tests = (ROOT / "tests/test_palm_gauntlet.py").read_text(encoding="utf-8")
    tests += "\n" + (ROOT / "tests/test_palm_integration.py").read_text(encoding="utf-8")

    for needle, label in [
        ("EVIDENCE_CONTRACT_VERSION", "versioned evidence contract"),
        ("EVIDENCE_STATES", "evidence state enum"),
        ("declared_content_type", "declared MIME input"),
        ("actual_mime", "signature MIME check"),
        ("n_frames", "animated-image rejection"),
        ("hard_cv_reject", "hard CV rejection"),
        ("multiple_hands", "multiple-hand boundary"),
        ("vision_skipped", "provider skip metric"),
        ("provider_content_stored", "provider content retention flag"),
        ("_UNTRUSTED_TEXT", "prompt-injection sanitizer"),
    ]:
        require(palm, needle, label, failures)
    require(palm, '"additionalProperties": False', "strict closed schema", failures)
    require(palm, '"evidence_state"', "observation evidence state", failures)
    require(palm, '"requires_view"', "required view contract", failures)
    require(landmarks, "num_hands=2", "no arbitrary one-hand selection", failures)
    require(full_scope, '"status": "hand_hull_scoped"', "palm-region scope", failures)
    require(full_scope, '"raw_mask_stored": False', "raw mask non-retention", failures)
    require(skills, "PALM_LIMITATION", "Mira weak-evidence boundary", failures)
    require(ui, "PALM_I18N", "Palm RU/EN dictionary", failures)
    require(ui, "refreshPalmLocale", "Palm locale refresh hook", failures)
    require(ui, "folded-edge", "folded-edge guidance", failures)
    require(locale, "refreshPalmLocale", "language-switch integration", failures)
    for needle, label in [
        ("adversarial", "adversarial visual text case"),
        ("multiple_hands", "multiple hands case"),
        ("folded_edge", "folded edge case"),
        ("mismatched", "MIME mismatch case"),
        ("weak_evidence", "weak evidence case"),
    ]:
        require(tests, needle, label, failures)

    review_files = {
        "corpus_schema": ROOT / "data/palm_golden/schema.json",
        "annotation_handbook": ROOT / "data/palm_golden/README.md",
        "manifest_template": ROOT / "data/palm_golden/manifest.template.jsonl",
        "predictions_template": ROOT / "data/palm_golden/predictions.template.jsonl",
        "corpus_validator": ROOT / "scripts/validate_palm_corpus.py",
        "review_runner": ROOT / "scripts/run_palm_human_review.py",
        "reviewer_registry_schema": ROOT / "data/palm_golden/reviewer_registry.schema.json",
        "reviewer_registry_validator": ROOT / "scripts/validate_palm_reviewer_registry.py",
    }
    review_block_reasons = [f"missing review asset: {name}" for name, path in review_files.items() if not path.is_file()]
    manifest_path = args.manifest or (ROOT / "data/palm_golden/manifest.jsonl")
    reviewer_path = args.reviewers or (ROOT / "data/palm_golden/reviewer_registry.json")
    if not manifest_path.is_file():
        review_block_reasons.append(f"adjudicated manifest not supplied: {manifest_path}")
    else:
        try:
            records = [line for line in manifest_path.read_text(encoding="utf-8").splitlines() if line.strip() and not line.lstrip().startswith("#")]
        except OSError:
            records = []
        if not records:
            review_block_reasons.append("golden manifest is empty")
        if not reviewer_path.is_file():
            review_block_reasons.append(f"reviewer registry not supplied: {reviewer_path}")
        else:
            try:
                reviewer_registry = json.loads(reviewer_path.read_text(encoding="utf-8"))
                review_block_reasons.extend(f"reviewer registry: {error}" for error in validate_reviewer_registry(reviewer_registry, require_domain=True))
            except (OSError, json.JSONDecodeError) as exc:
                review_block_reasons.append(f"reviewer registry is unreadable: {exc}")
    review_report = _load_review_report(args.review_report)
    if args.review_report is None:
        review_block_reasons.append("no human-review report supplied")
    elif not review_report or review_report.get("semantic_signoff") != "PASS":
        review_block_reasons.extend((review_report or {}).get("block_reasons") or ["human-review report is not PASS"])

    result = {
        "critic": "palm-independent-static-critic-v3",
        "blocking_failures": failures,
        "deterministic_contract": "PASS" if not failures else "BLOCKED",
        "semantic_accuracy": "PASS" if not review_block_reasons else "BLOCKED",
        "semantic_block_reasons": list(dict.fromkeys(review_block_reasons)),
        "required_for_semantic_signoff": [
            "two independent annotators per record",
            "domain-reviewer adjudication for test/challenge records",
            "immutable image hashes and exact prediction/manifest coverage",
            "zero critical false-observed promotions",
        ],
        "review_assets": {name: path.is_file() for name, path in review_files.items()},
        "review_manifest": {"path": str(manifest_path), "present": manifest_path.is_file()},
        "reviewer_registry": {"path": str(reviewer_path), "present": reviewer_path.is_file()},
        "review_report": {"path": str(args.review_report) if args.review_report else None, "present": review_report is not None},
        "ship_verdict": "BLOCKED" if failures else ("SEMANTIC SIGNOFF PASS" if not review_block_reasons else "SHIP WITH ACCURACY GATE"),
        "reason": "A passing contract critic proves guardrails, not semantic palm-reading accuracy.",
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
