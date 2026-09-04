from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core import astro  # noqa: E402

CASE = {
    "id": "kazan_1990_planets",
    "date": "1990-06-21",
    "time": "14:30",
    "tz": "Europe/Moscow",
    "lat": 55.79,
    "lon": 49.12,
}

TARGETS = {
    "Солнце": "10",
    "Луна": "301",
    "Меркурий": "199",
    "Венера": "299",
    "Марс": "499",
    "Юпитер": "599",
    "Сатурн": "699",
    "Уран": "799",
    "Нептун": "899",
    "Плутон": "999",
}


def angular_delta(left: float, right: float) -> float:
    return abs((left - right + 180.0) % 360.0 - 180.0)


def jpl_longitude(command: str, start: str, stop: str) -> float:
    params = {
        "format": "text",
        "COMMAND": command,
        "OBJ_DATA": "NO",
        "MAKE_EPHEM": "YES",
        "EPHEM_TYPE": "OBSERVER",
        "CENTER": "500@399",
        "START_TIME": start,
        "STOP_TIME": stop,
        "STEP_SIZE": "1m",
        "QUANTITIES": "31",
        "CSV_FORMAT": "YES",
    }
    url = "https://ssd.jpl.nasa.gov/api/horizons.api?" + urlencode(params)
    with urlopen(url, timeout=30) as response:
        payload = response.read().decode("utf-8")
    data_block = payload.split("$$SOE", 1)[1].split("$$EOE", 1)[0]
    line = next(line for line in data_block.splitlines() if line.strip())
    return float(line.split(",")[3])


def main() -> None:
    local = datetime.strptime(f"{CASE['date']} {CASE['time']}", "%Y-%m-%d %H:%M").replace(
        tzinfo=ZoneInfo(CASE["tz"])
    )
    utc = local.astimezone(timezone.utc)
    start = utc.strftime("%Y-%m-%dT%H:%M")
    stop = (utc + timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M")
    chart = astro.compute_chart(
        CASE["date"], CASE["time"], "Kazan", CASE["lat"], CASE["lon"], CASE["tz"], time_known=True
    )
    canonical = {item["name"]: float(item["abs_deg_exact"]) for item in chart["planets"]}
    comparisons = []
    for name, command in TARGETS.items():
        external = jpl_longitude(command, start, stop)
        comparisons.append({
            "body": name,
            "jpl_command": command,
            "oracleai_abs_deg_exact": canonical[name],
            "jpl_obs_ecliptic_longitude_deg": external,
            "delta_deg": angular_delta(canonical[name], external),
        })
    result = {
        "case": CASE,
        "utc": utc.isoformat(),
        "source": "NASA/JPL Horizons observer quantity 31, apparent ecliptic-of-date longitude, Earth geocentric center 500@399",
        "comparisons": comparisons,
        "max_delta_deg": max(item["delta_deg"] for item in comparisons),
        "query_window": {"start": start, "stop": stop, "step": "1m"},
        "non_comparable": ["ASC", "MC", "Placidus houses", "true lunar nodes", "True Lilith", "retrograde flag"],
        "note": "JPL Horizons is an independent ephemeris/reference implementation. Quantity 31 is apparent observer-centered ecliptic-of-date longitude; OracleAI uses its documented Kerykeion/Swiss Ephemeris contract. The comparison records deltas and does not silently relabel JPL fields as the OracleAI contract.",
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
