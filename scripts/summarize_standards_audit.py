"""Summarize the expanded standards audit without inline code."""
from __future__ import annotations

import json
from pathlib import Path

path = Path(__file__).resolve().parents[1] / "artifacts" / "standards-audit" / "report.json"
data = json.loads(path.read_text(encoding="utf-8"))
records = [state for states in data.values() for state in states.values()]
small = [entry for record in records for entry in record["smallTargets"]]
unnamed = [entry for record in records for entry in record["unnamed"]]
no_alt = [entry for record in records for entry in record["imagesWithoutAlt"]]
unlabelled = [entry for record in records for entry in record["inputsWithoutLabel"]]
print(f"records={len(records)}")
print(f"small_targets={len(small)}")
print(f"unnamed={len(unnamed)}")
print(f"images_without_alt={len(no_alt)}")
print(f"inputs_without_label={len(unlabelled)}")
print("languages_titles=")
for value in sorted({(record["htmlLang"], record["title"]) for record in records}):
    print(value)
print("small_target_details=")
seen = set()
for entry in small:
    key = (entry["className"], entry["text"], entry["rect"]["width"], entry["rect"]["height"])
    if key not in seen:
        seen.add(key)
        print(key)
