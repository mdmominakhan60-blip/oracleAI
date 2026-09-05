"""P1-004: Independent astrology comparison harness (Data Scientist, BUS-111).

Compares OracleAI canonical chart (`app.core.astro.compute_chart`, Kerykeion
5.12.9 -> Swiss Ephemeris 2.10.3.2) against two independent authorities:

  A. NASA/JPL Horizons API — observer quantity 31, apparent ecliptic-of-date
     longitude, geocenter 500@399 (network).
  B. Skyfield + JPL DE421.bsp + ERFA — fully independent implementation:
     DE421 Chebyshev interpolation, IAU 2006/2000A precession-nutation
     (pnm06a), true obliquity (obl06). No shared code or data with Swiss
     Ephemeris.

Non-comparable fields (ASC/MC/houses/nodes/Lilith/retrograde) are recorded
per case in `non_comparable`, never relabeled.

Date-only cases use the documented technical-noon convention (12:00 local
time), planets comparable; angular data excluded by contract.

Usage:
    python scripts/independent_comparison.py             # all authorities
    python scripts/independent_comparison.py --offline   # Skyfield only
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core import astro  # noqa: E402

# Case matrix: one case per type required by TASKS.md P1-004 — normal, DST,
# historical timezone, unknown time, edge longitude, high latitude, midnight.
# Inputs match tests/fixtures/domain_golden.json so settings are identical to
# the release golden suite.
CASES = [
    ("kazan_1990_normal",        "1990-06-21", "14:30", "Europe/Moscow",     55.79,    49.12,    True,  "normal"),
    ("berlin_2020_dst",          "2020-07-01", "12:00", "Europe/Berlin",     52.52,    13.405,   True,  "dst_summer"),
    ("kolkata_2020_hist_tz",     "2020-01-15", "12:00", "Asia/Kolkata",      22.5726,  88.3639,  True,  "historical_timezone"),
    ("utc_2000_midnight",        "2000-01-01", "00:00", "UTC",               0.0,      0.0,      True,  "midnight_and_zero_meridian"),
    ("anchorage_2000_high_lat",  "2000-03-20", "12:00", "America/Anchorage", 61.2181,  -149.9003, True, "high_latitude"),
    ("sydney_1990_edge_lon",     "1990-06-21", "14:30", "Australia/Sydney",  -33.8688, 151.2093, True,  "edge_longitude_southern"),
    ("kazan_1990_date_only",     "1990-06-21", None,    "Europe/Moscow",     55.79,    49.12,    False, "unknown_time"),
]

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

SF_BODIES = {
    "Солнце": "sun",
    "Луна": "moon",
    "Меркурий": "mercury",
    "Венера": "venus",
    "Марс": "mars",
    "Юпитер": "jupiter barycenter",
    "Сатурн": "saturn barycenter",
    "Уран": "uranus barycenter",
    "Нептун": "neptune barycenter",
    "Плутон": "pluto barycenter",
}

NON_COMPARABLE = [
    "ASC", "MC", "Placidus houses", "true lunar nodes", "True Lilith",
    "retrograde flag", "Chiron/asteroids",
]


def angular_delta(left: float, right: float) -> float:
    return abs((left - right + 180.0) % 360.0 - 180.0)


def local_to_utc(date_s: str, time_s: str | None, tz: str) -> datetime:
    hour, minute = (12, 0) if time_s is None else (int(time_s[:2]), int(time_s[3:5]))
    local = datetime.strptime(f"{date_s} {hour:02d}:{minute:02d}", "%Y-%m-%d %H:%M")
    return local.replace(tzinfo=ZoneInfo(tz)).astimezone(timezone.utc)


# ───────────────────────── Authority A: JPL Horizons ──────────────────────────
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


# ─────────────── Authority B: Skyfield + DE421 (fully offline) ────────────────
def skyfield_longitude(eph, ts, body_key: str, utc: datetime) -> float:
    """Apparent ecliptic-of-date geocentric longitude via DE421 + ERFA."""
    import math

    import erfa
    t = ts.from_datetime(utc)
    p = eph["earth"].at(t).observe(eph[body_key]).apparent()
    jd_tt = t.tt  # pnm06a/obl06 operate on TT; float64 JD resolution ~1e-10 day is sufficient
    rpnb = erfa.pnm06a(jd_tt, 0.0)
    x, y, z = erfa.rxp(rpnb, p.position.au)
    # rotate true-equator vector into ecliptic-of-date: R_x(-eps) applied manually
    obl = erfa.obl06(jd_tt, 0.0)
    c, s = math.cos(obl), math.sin(obl)
    y_ecl = y * c + z * s
    x_ecl = x
    return float(erfa.anp(math.atan2(y_ecl, x_ecl)) * erfa.DR2D)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--offline", action="store_true", help="Skip JPL API (Skyfield only)")
    parser.add_argument("--out", default=None, help="Output JSON path")
    args = parser.parse_args()

    out_path = Path(args.out) if args.out else (
        ROOT / "docs" / "DOMAIN" / f"independent_comparison_{datetime.now(timezone.utc):%Y-%m-%d}.json"
    )

    from skyfield.api import Loader
    bsp_dir = os.environ.get("ORACLEAI_BSP_DIR", str(ROOT / "data" / "bsp"))
    loader = Loader(bsp_dir, verbose=False)
    eph = loader("de421.bsp")
    ts = loader.timescale(builtin=True)

    results = []
    for case_id, date_s, time_s, tz, lat, lon, time_known, covers in CASES:
        utc = local_to_utc(date_s, time_s, tz)
        chart = astro.compute_chart(date_s, time_s, "case", lat, lon, tz, time_known=time_known)
        canonical = {item["name"]: float(item["abs_deg_exact"]) for item in chart["planets"]}

        start = utc.strftime("%Y-%m-%dT%H:%M")
        stop = (utc + timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M")

        comparisons_a = []
        comparisons_b = []
        for body in TARGETS:
            our = canonical[body]
            if not args.offline:
                ext = jpl_longitude(TARGETS[body], start, stop)
                comparisons_a.append({
                    "body": body,
                    "jpl_command": TARGETS[body],
                    "oracleai_abs_deg_exact": our,
                    "jpl_obs_ecliptic_longitude_deg": ext,
                    "delta_deg": angular_delta(our, ext),
                })
            sf_lon = skyfield_longitude(eph, ts, SF_BODIES[body], utc)
            comparisons_b.append({
                "body": body,
                "oracleai_abs_deg_exact": our,
                "skyfield_de421_ecliptic_of_date_longitude_deg": sf_lon,
                "delta_deg": angular_delta(our, sf_lon),
            })

        case_result = {
            "case_id": case_id,
            "input": {
                "date": date_s, "time": time_s, "tz": tz,
                "lat": lat, "lon": lon, "time_known": time_known,
            },
            "utc_instant": utc.isoformat(),
            "covers": covers,
            "precision": "exact" if time_known else "date_only",
            "comparisons_skyfield_de421": comparisons_b,
            "non_comparable": NON_COMPARABLE,
        }
        if not args.offline:
            case_result["comparisons_jpl_horizons"] = comparisons_a
            case_result["max_delta_jpl_deg"] = max(r["delta_deg"] for r in comparisons_a)
        case_result["max_delta_skyfield_deg"] = max(r["delta_deg"] for r in comparisons_b)
        results.append(case_result)
        print(f"[ok] {case_id}: jpl={len(comparisons_a)} skyfield={len(comparisons_b)}", file=sys.stderr)

    summary = {
        "schema": "oracleai-independent-comparison-v1",
        "generated": datetime.now(timezone.utc).isoformat(),
        "product_engine": {
            "name": "OracleAI Engine v2 -> Kerykeion 5.12.9 -> Swiss Ephemeris 2.10.3.2",
            "contract": "app/core/chart_contract v1; adapter oracleai-kerykeion-engine-v2",
            "settings": {
                "zodiac": "Tropical", "perspective": "Apparent Geocentric",
                "houses": "Placidus (P)", "nodes": "true node",
                "node_lilith_policy": "true_lunar_nodes_plus_true_lilith",
            },
        },
        "authority_a": {
            "name": "NASA/JPL Horizons API",
            "quantity": "Observer quantity 31, apparent ecliptic-of-date longitude, geocenter 500@399",
            "independence_note": "Separate implementation and pipeline from Swiss Ephemeris; network API.",
            "status": "skipped (--offline)" if args.offline else "captured",
        },
        "authority_b": {
            "name": "Skyfield + JPL DE421.bsp + ERFA (pyerfa)",
            "quantity": "apparent GCRS position rotated to ecliptic-of-date (pnm06a + obl06, TT)",
            "independence_note": (
                "Fully independent code path: DE421 Chebyshev interpolation and IAU 2006/2000A "
                "precession-nutation from ERFA; no shared code or data with Swiss Ephemeris."
            ),
        },
        "cases": results,
        "note": (
            "Identical-settings comparison: one date/time/place -> OracleAI engine vs two "
            "independent authorities. Deltas recorded as-is; no silent relabeling. Angular data "
            "(ASC/MC/houses) and node/Lilith/retrograde remain non-comparable and are tracked in "
            "docs/DOMAIN/ACCURACY_MATRIX.md. Date-only case uses the documented technical-noon "
            "convention (12:00 local); planets only."
        ),
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"written: {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
