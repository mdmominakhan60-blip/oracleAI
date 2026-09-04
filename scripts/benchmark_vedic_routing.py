"""Adversarial routing set for the newly added Vedic Urania skills."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.agents.file_loader import profile_for_legacy, select_skills

CASES = [
    ("ведическая лагна и kundli по Lahiri", "vedic-foundations"),
    ("What is my Moon nakshatra and pada?", "nakshatra-pada"),
    ("Покажи Vimshottari Mahadasha и antardasha", "vimshottari-dasha"),
    ("Panchang for tomorrow and Rahu Kaal", "panchang-muhurta"),
    ("Сравни две даты для muhurta launch", "panchang-muhurta"),
    ("Read my Navamsa D9 and Dasamsa D10", "varga-charts"),
    ("Ashtakoot Guna Milan для нас", "guna-milan"),
    ("Vedic sidereal transits for today", "vedic-transits"),
    ("Graha strength / exaltation in my Kundli", "graha-strengths"),
    ("No birth time, can I get Vedic houses?", "date-only-mode"),
]


def main() -> int:
    profile = profile_for_legacy("astro")
    rows = []
    for query, expected in CASES:
        selected = [skill.name for skill in select_skills(profile, query, 3)]
        rank = selected.index(expected) + 1 if expected in selected else None
        rows.append({"query": query, "expected": expected, "selected": selected,
                     "expected_rank": rank, "top1": rank == 1, "top3": rank is not None})
    report = {
        "total": len(rows),
        "top1_passed": sum(row["top1"] for row in rows),
        "top3_passed": sum(row["top3"] for row in rows),
        "top1_accuracy": round(sum(row["top1"] for row in rows) / len(rows), 3),
        "top3_accuracy": round(sum(row["top3"] for row in rows) / len(rows), 3),
        "cases": rows,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["top3_passed"] == report["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
