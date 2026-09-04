"""Summarize the deterministic visual QA report without mutating the project."""
from __future__ import annotations
import json
from pathlib import Path

report = json.loads((Path(__file__).resolve().parents[1] / "artifacts" / "visual-qa" / "report.json").read_text(encoding="utf-8"))
for group, states in report["results"].items():
    for state, data in states.items():
        if data["horizontalOverflow"]:
            print(group, state, data["scroll"], data["overflowNodes"])
