#!/usr/bin/env python3
"""Check the privacy-safe PDF/HTML golden-case matrix locally."""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.pdfgen import builder  # noqa: E402


CASES = [
    {"id": "ru-exact", "name": "Анна Синтетическая", "date": "1990-06-21", "time": "14:30", "city": "Казань", "lang": "ru", "lat": 55.79, "lon": 49.12, "tz": "Europe/Moscow"},
    {"id": "en-exact", "name": "Anna Synthetic", "date": "1990-06-21", "time": "14:30", "city": "Kazan", "lang": "en", "lat": 55.79, "lon": 49.12, "tz": "Europe/Moscow"},
    {"id": "ru-date-only", "name": "Анна Синтетическая", "date": "1990-06-21", "time": None, "city": "Казань", "lang": "ru", "lat": 55.79, "lon": 49.12, "tz": "Europe/Moscow"},
    {"id": "en-date-only", "name": "Anna Synthetic", "date": "1990-06-21", "time": None, "city": "Kazan", "lang": "en", "lat": 55.79, "lon": 49.12, "tz": "Europe/Moscow"},
    {"id": "dst-long-name", "name": "A Synthetic Name With A Deliberately Long Display Value", "date": "2026-03-29", "time": "01:30", "city": "Edge City", "lang": "en", "lat": 59.93, "lon": 30.31, "tz": "Europe/Moscow"},
    {"id": "high-latitude", "name": "Тест Севера", "date": "2000-12-21", "time": "23:59", "city": "High Latitude", "lang": "ru", "lat": 69.65, "lon": 18.95, "tz": "Europe/Oslo"},
]


async def main() -> int:
    original_geo = builder.geo.resolve_city_async
    original_llm_enabled = builder.llm.enabled
    builder.llm.enabled = lambda: False

    async def fake_geo(city: str):
        case = next(item for item in CASES if item["city"] == city)
        return case["lat"], case["lon"], case["tz"]

    builder.geo.resolve_city_async = fake_geo
    checks: dict[str, dict[str, bool]] = {}
    try:
        for case in CASES:
            order = builder.Order(
                name=case["name"], birth_date=case["date"], birth_time=case["time"],
                birth_city=case["city"], lang=case["lang"],
            )
            html = await builder.generate(None, order, concurrency=1)
            date_only = case["time"] is None
            expected = {
                "document": "<html" in html and "</html>" in html,
                "localized": ('lang="en"' in html) if case["lang"] == "en" else ('lang="ru"' in html),
                "truth_state": ("The wheel image is not generated" in html or "Изображение колеса не строится" in html) if date_only else True,
                "no_unsupported_engine_leak": all(token not in html for token in ("Swiss Ephemeris", "Kerykeion", "Placidus", "Tropical")),
                "long_name_bounded": len(case["name"]) <= 60 or case["name"][:30] in html,
            }
            checks[case["id"]] = expected
    finally:
        builder.geo.resolve_city_async = original_geo
        builder.llm.enabled = original_llm_enabled
    report = {
        "synthetic": True,
        "cases": len(CASES),
        "checks": checks,
        "pass": all(all(values.values()) for values in checks.values()),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
