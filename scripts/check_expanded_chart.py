from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.astro import compute_chart  # noqa: E402

chart = compute_chart(
    "1990-06-21", "14:30", "Казань", 55.79, 49.12, "Europe/Moscow", time_known=True
)
print(json.dumps({
    "mode": chart.get("mode"),
    "precision": chart.get("precision"),
    "planets": len(chart.get("planets", [])),
    "nodes": [n.get("name") for n in chart.get("nodes", [])],
    "additional_points": [p.get("name") for p in chart.get("additional_points", [])],
    "rahu": chart.get("lunar_nodes", {}).get("rahu", {}).get("name"),
    "ketu": chart.get("lunar_nodes", {}).get("ketu", {}).get("name"),
    "error": chart.get("error"),
}, ensure_ascii=False, indent=2))
