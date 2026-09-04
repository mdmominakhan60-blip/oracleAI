from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core import astro  # noqa: E402
FIXTURE = ROOT / "tests" / "fixtures" / "domain_golden.json"


def jsonable(value):
    return json.loads(json.dumps(value, ensure_ascii=False))


def chart_summary(chart: dict) -> dict:
    return {
        "mode": chart.get("mode"),
        "precision": chart.get("precision"),
        "sun": chart.get("sun"),
        "ascendant": chart.get("ascendant"),
        "mc": chart.get("mc"),
        "planets": chart.get("planets"),
        "houses": chart.get("houses"),
        "aspects": chart.get("aspects"),
        "nodes": chart.get("nodes"),
        "calculation": chart.get("calculation"),
    }


def main() -> None:
    corpus = json.loads(FIXTURE.read_text(encoding="utf-8"))
    for case in corpus["cases"]:
        inputs = case["input"]
        chart = astro.compute_chart(
            inputs["birth_date"], inputs["birth_time"], inputs["city"],
            inputs["lat"], inputs["lon"], inputs["tz"],
            time_known=inputs["time_known"],
        )
        case["output"] = jsonable(chart_summary(chart))
    FIXTURE.write_text(
        json.dumps(corpus, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"updated {FIXTURE} with {len(corpus['cases'])} cases")


if __name__ == "__main__":
    main()
