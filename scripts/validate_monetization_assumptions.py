"""Validate the reviewed-input boundary of the monetization assumptions template."""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

SCENARIOS = {"cash_constrained", "validated_growth", "large_team"}
REQUIRED_COLUMNS = {
    "version", "scenario", "metric", "value", "unit", "source", "as_of", "status", "notes",
}
ALLOWED_STATUS = {"hypothesis", "estimated", "required_input", "observed_input", "reviewed_input"}
HYPOTHESIS_SOURCES = {"approved_plan", "market_research_recommendation"}


def validate(path: Path) -> list[str]:
    errors: list[str] = []
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if set(reader.fieldnames or ()) != REQUIRED_COLUMNS:
            return ["columns do not match the monetization assumptions contract"]
        seen: set[tuple[str, str]] = set()
        versions: set[str] = set()
        rows = list(reader)
    if not rows:
        return ["assumptions file is empty"]
    for line, row in enumerate(rows, start=2):
        key = (row["scenario"], row["metric"])
        if key in seen:
            errors.append(f"line {line}: duplicate scenario/metric {key}")
        seen.add(key)
        versions.add(row["version"])
        if row["scenario"] not in SCENARIOS:
            errors.append(f"line {line}: unsupported scenario {row['scenario']}")
        if row["status"] not in ALLOWED_STATUS:
            errors.append(f"line {line}: unsupported status {row['status']}")
        if not row["source"] or not row["notes"]:
            errors.append(f"line {line}: source and notes are mandatory")
        if row["status"] == "reviewed_input" and (not row["value"] or row["as_of"] == "TBD"):
            errors.append(f"line {line}: reviewed_input requires value and as_of")
        if row["status"] == "hypothesis" and row["source"] not in HYPOTHESIS_SOURCES:
            errors.append(f"line {line}: hypotheses must identify an approved plan or research recommendation source")
        if row["status"] == "estimated" and row["source"] in {"approved_plan", "settlement_export", "tax_review"}:
            errors.append(f"line {line}: estimated inputs must identify a model or external market source, not a decision/settlement placeholder")
    if len(versions) != 1:
        errors.append(f"multiple assumption versions found: {sorted(versions)}")
    for metric in ("effective_platform_realization", "tax_and_withholding_rate", "refund_rate"):
        present = {row["scenario"] for row in rows if row["metric"] == metric}
        if present != SCENARIOS:
            errors.append(f"metric {metric} must exist for every scenario")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", nargs="?", type=Path,
                        default=Path(__file__).resolve().parent.parent
                        / "docs" / "MONETIZATION_ASSUMPTIONS.csv")
    args = parser.parse_args()
    errors = validate(args.path)
    if errors:
        for error in errors:
            print(error)
        return 1
    print(f"monetization assumptions ok: {args.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
