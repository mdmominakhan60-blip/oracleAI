"""Independent domain QA for critical chart calculation cases.

The application adapter uses Kerykeion; this harness computes the same planetary
longitudes directly through pyswisseph and compares the two software paths. Both
paths share the Swiss Ephemeris kernel, so this is independent implementation QA,
not an independent ephemeris-vendor comparison.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import swisseph as swe

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.core import astro  # noqa: E402

THRESHOLD_DEG = 0.02

BODIES = {
    "Солнце": swe.SUN,
    "Луна": swe.MOON,
    "Меркурий": swe.MERCURY,
    "Венера": swe.VENUS,
    "Марс": swe.MARS,
    "Юпитер": swe.JUPITER,
    "Сатурн": swe.SATURN,
    "Уран": swe.URANUS,
    "Нептун": swe.NEPTUNE,
    "Плутон": swe.PLUTO,
}

CASES = [
    {"id": "normal_exact", "date": "1990-06-21", "time": "14:30", "city": "Kazan", "lat": 55.79, "lon": 49.12, "tz": "Europe/Moscow", "time_known": True},
    {"id": "dst_summer", "date": "2021-07-01", "time": "12:30", "city": "New York", "lat": 40.7128, "lon": -74.0060, "tz": "America/New_York", "time_known": True},
    {"id": "dst_fall_back_ambiguous", "date": "2021-11-07", "time": "01:30", "city": "New York", "lat": 40.7128, "lon": -74.0060, "tz": "America/New_York", "time_known": True, "expected_mode": "lite", "comparison": "fail_closed_ambiguous_local_time"},
    {"id": "historical_timezone", "date": "1945-05-09", "time": "12:00", "city": "Berlin", "lat": 52.52, "lon": 13.405, "tz": "Europe/Berlin", "time_known": True},
    {"id": "unknown_time", "date": "2000-01-01", "time": None, "city": "London", "lat": 51.5074, "lon": -0.1278, "tz": "Europe/London", "time_known": False},
    {"id": "edge_longitude", "date": "2020-03-20", "time": "00:05", "city": "Fiji", "lat": -17.7134, "lon": 178.0650, "tz": "Pacific/Fiji", "time_known": True},
    {"id": "high_latitude", "date": "2022-12-21", "time": "12:00", "city": "Longyearbyen", "lat": 78.2232, "lon": 15.6469, "tz": "Arctic/Longyearbyen", "time_known": True, "expected_mode": "polar"},
    {"id": "midnight_boundary", "date": "2011-12-31", "time": "23:59", "city": "Kiritimati", "lat": 1.8721, "lon": -157.4278, "tz": "Pacific/Kiritimati", "time_known": True},
]


def direct_positions(case: dict) -> dict[str, float]:
    hour, minute = (12, 0) if case["time"] is None else map(int, case["time"].split(":"))
    local = datetime.strptime(
        f"{case['date']} {int(hour):02d}:{int(minute):02d}", "%Y-%m-%d %H:%M"
    ).replace(tzinfo=ZoneInfo(case["tz"]))
    utc = local.astimezone(timezone.utc)
    jd = swe.julday(utc.year, utc.month, utc.day,
                    utc.hour + utc.minute / 60 + utc.second / 3600)
    return {
        name: float(swe.calc_ut(jd, body, swe.FLG_SWIEPH)[0][0]) % 360
        for name, body in BODIES.items()
    }


def direct_houses(case: dict) -> tuple[dict[int, float], dict[str, float]]:
    hour, minute = map(int, case["time"].split(":"))
    local = datetime.strptime(
        f"{case['date']} {hour:02d}:{minute:02d}", "%Y-%m-%d %H:%M"
    ).replace(tzinfo=ZoneInfo(case["tz"]))
    utc = local.astimezone(timezone.utc)
    jd = swe.julday(utc.year, utc.month, utc.day,
                    utc.hour + utc.minute / 60 + utc.second / 3600)
    cusps, ascmc = swe.houses_ex(jd, case["lat"], case["lon"], b"P")
    return (
        {index + 1: float(value) % 360 for index, value in enumerate(cusps)},
        {"ASC": float(ascmc[0]) % 360, "MC": float(ascmc[1]) % 360},
    )


def angular_delta(left: float, right: float) -> float:
    return abs((left - right + 180) % 360 - 180)


def check_case(case: dict) -> dict:
    chart = astro.compute_chart(
        case["date"], case["time"], case["city"], case["lat"], case["lon"],
        case["tz"], time_known=case["time_known"])
    expected_mode = case.get("expected_mode", "full")
    if case.get("comparison") == "fail_closed_ambiguous_local_time":
        note = str(chart.get("note") or "")
        passed = (
            chart.get("mode") == "full"
            and chart.get("precision") == "date_only"
            and not chart.get("calculation", {}).get("angular_data_available")
            and not chart.get("houses")
            and chart.get("ascendant") is None
            and chart.get("mc") is None
        )
        return {
            "id": case["id"],
            "passed": passed,
            "mode": chart.get("mode"),
            "precision": chart.get("precision"),
            "angular_data_available": bool(chart.get("calculation", {}).get("angular_data_available")),
            "expected_angular_data": False,
            "planet_count": len(chart.get("planets", [])),
            "max_planet_delta_deg": None,
            "planet_deltas_deg": {},
            "comparison": case.get("comparison"),
            "note": note,
        }
    if expected_mode == "lite":
        note = str(chart.get("note") or "")
        passed = chart.get("mode") == "lite" and chart.get("precision") == "sun_only"
        return {
            "id": case["id"],
            "passed": passed,
            "mode": chart.get("mode"),
            "precision": chart.get("precision"),
            "angular_data_available": False,
            "expected_angular_data": False,
            "planet_count": len(chart.get("planets", [])),
            "max_planet_delta_deg": None,
            "planet_deltas_deg": {},
            "comparison": case.get("comparison"),
            "note": note,
        }
    if expected_mode == "polar":
        try:
            direct_houses(case)
        except swe.Error as error:
            direct = direct_positions(case)
            canonical = {planet["name"]: float(planet["abs_deg_exact"])
                         for planet in chart.get("planets", [])
                         if planet.get("abs_deg_exact") is not None}
            diffs = {
                name: round(angular_delta(canonical[name], expected), 6)
                for name, expected in direct.items() if name in canonical
            }
            max_planet_diff = max(diffs.values(), default=999.0)
            return {
                "id": case["id"],
                "passed": len(canonical) == len(BODIES) and max_planet_diff <= 0.02,
                "mode": chart.get("mode"),
                "precision": chart.get("precision"),
                "angular_data_available": bool(chart.get("calculation", {}).get("angular_data_available")),
                "expected_angular_data": True,
                "planet_count": len(canonical),
                "house_count": len(chart.get("houses", [])),
                "max_planet_delta_deg": max_planet_diff,
                "max_house_delta_deg": None,
                "max_angle_delta_deg": None,
                "planet_deltas_deg": diffs,
                "house_deltas_deg": {},
                "angle_deltas_deg": {},
                "comparison": "planet_numeric_houses_unavailable_polar",
                "house_comparison": "unavailable_in_direct_reference",
                "unverified": ["houses", "ASC", "MC"],
                "note": f"direct houses_ex unavailable: {error}",
            }
    direct = direct_positions(case)
    canonical = {planet["name"]: float(planet["abs_deg_exact"])
                 for planet in chart.get("planets", [])
                 if planet.get("abs_deg_exact") is not None}
    diffs = {
        name: round(angular_delta(canonical[name], expected), 6)
        for name, expected in direct.items() if name in canonical
    }
    max_planet_diff = max(diffs.values(), default=999.0)
    expected_angles = bool(case["time_known"])
    if expected_angles:
        direct_cusps, direct_angles = direct_houses(case)
        canonical_cusps = {
            int(house["n"]): float(house["abs_deg_exact"])
            for house in chart.get("houses", [])
            if house.get("abs_deg_exact") is not None
        }
        canonical_angles = {
            "ASC": float((chart.get("ascendant") or {})["abs_deg_exact"]),
            "MC": float((chart.get("mc") or {})["abs_deg_exact"]),
        }
    else:
        direct_cusps, direct_angles = {}, {}
        canonical_cusps, canonical_angles = {}, {}
    house_diffs = {
        str(number): round(angular_delta(canonical_cusps[number], expected), 6)
        for number, expected in direct_cusps.items() if number in canonical_cusps
    }
    angle_diffs = {
        name: round(angular_delta(canonical_angles[name], expected), 6)
        for name, expected in direct_angles.items()
    }
    max_house_diff = max(house_diffs.values(), default=0.0)
    max_angle_diff = max(angle_diffs.values(), default=0.0)
    angles_available = bool(chart.get("calculation", {}).get("angular_data_available"))
    passed = (
        chart.get("mode") == "full"
        and len(canonical) == len(BODIES)
        and (len(canonical_cusps) == 12 if expected_angles else not canonical_cusps)
        and max_planet_diff <= THRESHOLD_DEG
        and max_house_diff <= THRESHOLD_DEG
        and max_angle_diff <= THRESHOLD_DEG
        and (angles_available == expected_angles)
        and (expected_angles or not chart.get("houses"))
    )
    return {
        "id": case["id"],
        "passed": passed,
        "mode": chart.get("mode"),
        "precision": chart.get("precision"),
        "comparison": "numeric_planets_houses_angles",
        "angular_data_available": angles_available,
        "expected_angular_data": expected_angles,
        "planet_count": len(canonical),
        "house_count": len(canonical_cusps),
        "max_planet_delta_deg": max_planet_diff,
        "max_house_delta_deg": max_house_diff,
        "max_angle_delta_deg": max_angle_diff,
        "planet_deltas_deg": diffs,
        "house_deltas_deg": house_diffs,
        "angle_deltas_deg": angle_diffs,
        "note": chart.get("note"),
    }


def main() -> int:
    results = [check_case(case) for case in CASES]
    summary = {
        "calculator_a": "OracleAI Kerykeion adapter",
        "calculator_b": "direct pyswisseph calc_ut",
        "shared_ephemeris_kernel": "Swiss Ephemeris",
        "threshold_deg": THRESHOLD_DEG,
        "cases": results,
        "passed": sum(result["passed"] for result in results),
        "total": len(results),
        "external_vendor_comparison": "open",
        "unverified_comparisons": [
            {"case": result["id"], "fields": result.get("unverified", [])}
            for result in results if result.get("unverified")
        ],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["passed"] == summary["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
