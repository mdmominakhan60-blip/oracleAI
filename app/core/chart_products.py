"""Structured product contracts for relationship, transit, composite and return paths.

The module deliberately contains no FastAPI, database, or LLM code. It consumes
already calculated canonical charts and returns stable JSON-ready dictionaries.
"""
from __future__ import annotations

import math
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from typing import Any

from . import astro

SYNASTRY_SCHEMA_VERSION = 1
TRANSIT_SCHEMA_VERSION = 1
COMPOSITE_SCHEMA_VERSION = 1
RETURNS_SCHEMA_VERSION = 1
RETURNS_SUPPORTED_PLANETS = ("Sun",)

_NAME_TO_ID = {value: key for key, value in astro.PLANET_RU.items()}


class ChartProductError(ValueError):
    """A stable, client-facing product validation error."""

    def __init__(self, code: str, message: str, missing: list[str] | None = None):
        self.code = code
        self.message = message
        self.missing = missing or []
        super().__init__(message)



def _chart_evidence(chart: dict[str, Any]) -> dict[str, Any]:
    calculation = chart.get("calculation") or {}
    return {
        "contract_version": calculation.get("contract_version"),
        "configuration_fingerprint": calculation.get("configuration_fingerprint"),
        "request_fingerprint": (calculation.get("input") or {}).get("request_fingerprint"),
        "precision": chart.get("precision"),
        "engine": (calculation.get("config") or {}).get("ephemeris_engine", chart.get("engine")),
    }


def _planet_rows(chart: dict[str, Any]) -> list[dict[str, Any]]:
    """Return only canonical planetary rows, preserving exact longitudes."""
    rows = []
    for point in chart.get("planets") or []:
        if point.get("abs_deg_exact") is None and point.get("abs_deg") is None:
            continue
        name = str(point.get("name") or "")
        rows.append({
            "id": _NAME_TO_ID.get(name, name),
            "name": name,
            "label": name,
            "sign": point.get("sign"),
            "deg": point.get("deg"),
            "deg_exact": point.get("deg_exact"),
            "abs_deg": point.get("abs_deg"),
            "abs_deg_exact": point.get("abs_deg_exact"),
            "retro": bool(point.get("retro", False)),
        })
    return rows



def _longitude(row: dict[str, Any]) -> float | None:
    value = row.get("abs_deg_exact")
    if value is None:
        value = row.get("abs_deg")
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value % 360



def _aspect_row(aspect: dict[str, Any], *, first_role: str,
                second_role: str) -> dict[str, Any]:
    first_label = str(aspect.get("p1") or "")
    second_label = str(aspect.get("p2") or "")
    return {
        "first": _NAME_TO_ID.get(first_label, first_label),
        "first_label": first_label,
        "first_role": first_role,
        "second": _NAME_TO_ID.get(second_label, second_label),
        "second_label": second_label,
        "second_role": second_role,
        "code": aspect.get("code"),
        "label": aspect.get("aspect"),
        "glyph": aspect.get("glyph"),
        "orb_deg": aspect.get("orb"),
        "orb_exact": aspect.get("orb_exact", aspect.get("orb")),
    }



def _require_planets(chart: dict[str, Any], role: str, *, exact: bool) -> None:
    if not isinstance(chart, dict) or not chart.get("planets"):
        raise ChartProductError("chart_required", "Для расчёта нужна сохранённая натальная карта.", [role])
    if exact and chart.get("precision") != "exact":
        raise ChartProductError(
            "exact_charts_required",
            "Для этого расчёта нужна точная натальная карта.",
            [role],
        )



def _require_full_exact(chart: dict[str, Any], role: str) -> None:
    _require_planets(chart, role, exact=True)
    if chart.get("mode") != "full":
        raise ChartProductError(
            "exact_charts_required",
            "Для этого расчёта нужна полная точная натальная карта.",
            [role],
        )



def build_synastry_contract(owner_chart: dict[str, Any], partner_chart: dict[str, Any],
                            *, partner_id: int, partner_label: str) -> dict[str, Any]:
    """Build the exact two-chart contract from two owner-scoped saved charts."""
    _require_planets(owner_chart, "owner", exact=True)
    _require_planets(partner_chart, "partner", exact=True)
    owner_planets = _planet_rows(owner_chart)
    partner_planets = _planet_rows(partner_chart)
    raw_aspects = astro.synastry_aspects(owner_planets, partner_planets, limit=20)
    result = {
        "synastry_schema_version": SYNASTRY_SCHEMA_VERSION,
        "product": "synastry",
        "precision": "exact",
        "person": {
            "role": "owner",
            "label": "Я",
            "chart_precision": owner_chart.get("precision"),
            "evidence": _chart_evidence(owner_chart),
            "planets": owner_planets,
        },
        "partner": {
            "role": "partner",
            "partner_id": partner_id,
            "label": partner_label or "Партнёр",
            "chart_precision": partner_chart.get("precision"),
            "evidence": _chart_evidence(partner_chart),
            "planets": partner_planets,
        },
        "aspects": [
            _aspect_row(item, first_role="owner", second_role="partner")
            for item in raw_aspects
        ],
        "limitations": [
            "Показываются мажорные межпланетные аспекты; дома, углы и композитная карта не строятся.",
        ],
    }
    validate_synastry_contract(result)
    return result



def _sign_fields(longitude: float) -> dict[str, Any]:
    normalized = longitude % 360
    sign_index = min(11, int(normalized // 30))
    sign, symbol, element = astro.SIGNS[sign_index]
    degree = normalized - sign_index * 30
    return {
        "sign": sign,
        "symbol": symbol,
        "element": element,
        "deg": round(degree, 1),
        "deg_exact": degree,
        "abs_deg": round(normalized, 1),
        "abs_deg_exact": normalized,
    }



def circular_midpoint(first: float, second: float) -> float:
    """Return the midpoint on the shortest circular arc between two longitudes."""
    first = float(first) % 360
    second = float(second) % 360
    delta = (second - first) % 360
    if delta > 180:
        delta -= 360
    return (first + delta / 2) % 360



def _composite_aspects(points: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Reuse the canonical major-aspect policy and remove reverse duplicates."""
    aspect_points = [
        {"name": point["label"], "abs_deg": point["abs_deg_exact"]}
        for point in points
    ]
    raw = astro.synastry_aspects(aspect_points, aspect_points, limit=200)
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str | None]] = set()
    for aspect in raw:
        pair = tuple(sorted((str(aspect.get("p1")), str(aspect.get("p2")))))
        key = (*pair, aspect.get("code"))
        if key in seen:
            continue
        seen.add(key)
        out.append(aspect)
    return out[:40]



def build_composite_contract(owner_chart: dict[str, Any], partner_chart: dict[str, Any],
                             *, partner_id: int, partner_label: str) -> dict[str, Any]:
    """Build a v1 composite from circular midpoints of two exact full charts."""
    _require_full_exact(owner_chart, "owner")
    _require_full_exact(partner_chart, "partner")
    owner = {row["id"]: row for row in _planet_rows(owner_chart)}
    partner = {row["id"]: row for row in _planet_rows(partner_chart)}
    points: list[dict[str, Any]] = []
    missing: list[str] = []
    for planet_id, label in astro.PLANET_RU.items():
        first = _longitude(owner.get(planet_id, {}))
        second = _longitude(partner.get(planet_id, {}))
        if first is None or second is None:
            missing.append(label)
            continue
        midpoint = circular_midpoint(first, second)
        points.append({
            "id": planet_id,
            "label": label,
            "source": {
                "owner_abs_deg_exact": first,
                "partner_abs_deg_exact": second,
            },
            **_sign_fields(midpoint),
            "retro": False,
        })

    if not points:
        raise ChartProductError(
            "chart_required",
            "В сохранённых картах нет общих планет для композита.",
            ["owner", "partner"],
        )
    limitations = [
        "Показываются десять традиционных планет и мажорные аспекты внутри композита; узлы, дополнительные точки, ASC/MC и дома пока не строятся.",
    ]
    if missing:
        limitations.append("Недоступные точки пропущены: " + ", ".join(missing) + ".")
    result = {
        "composite_schema_version": COMPOSITE_SCHEMA_VERSION,
        "product": "composite",
        "precision": "exact",
        "sources": {
            "owner": {"role": "owner", "chart_precision": owner_chart.get("precision"),
                      "evidence": _chart_evidence(owner_chart)},
            "partner": {
                "role": "partner",
                "partner_id": partner_id,
                "label": partner_label or "Партнёр",
                "chart_precision": partner_chart.get("precision"),
                "evidence": _chart_evidence(partner_chart),
            },
        },
        "points": points,
        "aspects": [
            _aspect_row(item, first_role="composite", second_role="composite")
            for item in _composite_aspects(points)
        ],
        "limitations": limitations,
    }
    validate_composite_contract(result)
    return result



def build_transit_contract(natal_chart: dict[str, Any], *, as_of: date,
                           clock: time | None = None) -> dict[str, Any]:
    """Build a deterministic geocentric transit snapshot against natal planets.

    A neutral 0°/0°, UTC subject is used only to obtain geocentric longitudes;
    transit houses and angles are intentionally not part of this first contract.
    """
    _require_planets(natal_chart, "owner", exact=False)
    sample_time = clock or time(12, 0)
    transit_time = f"{sample_time.hour:02d}:{sample_time.minute:02d}"
    transit_chart = astro.compute_chart(
        as_of.isoformat(), transit_time, "UTC", 0.0, 0.0, "UTC", time_known=True,
    )
    transit_planets = _planet_rows(transit_chart)
    natal_planets = _planet_rows(natal_chart)
    raw_aspects = astro.synastry_aspects(transit_planets, natal_planets, limit=20)
    sampled_at = datetime(
        as_of.year, as_of.month, as_of.day, sample_time.hour, sample_time.minute,
        tzinfo=timezone.utc,
    )
    limitations = ["Транзитные дома и углы в этом контракте не строятся."]
    precision = "instant" if clock is not None else "day"
    if clock is None:
        limitations.insert(0, "Без времени показан дневной срез на 12:00 UTC; положение Луны внутри дня может меняться.")
    result = {
        "transit_schema_version": TRANSIT_SCHEMA_VERSION,
        "product": "transits",
        "as_of": as_of.isoformat(),
        "sampled_at": sampled_at.isoformat(),
        "precision": precision,
        "natal_precision": natal_chart.get("precision"),
        "natal_evidence": _chart_evidence(natal_chart),
        "transit_evidence": _chart_evidence(transit_chart),
        "transit_planets": transit_planets,
        "aspects_to_natal": [
            _aspect_row(item, first_role="transit", second_role="natal")
            for item in raw_aspects
        ],
        "limitations": limitations,
    }
    validate_transit_contract(result)
    return result



def _circular_distance(first: float, second: float) -> float:
    delta = abs(first - second) % 360
    return min(delta, 360 - delta)



def _return_planet_longitude(instant: datetime, planet_id: str) -> float:
    instant = instant.astimezone(timezone.utc).replace(second=0, microsecond=0)
    chart = astro.compute_chart(
        instant.date().isoformat(),
        f"{instant.hour:02d}:{instant.minute:02d}",
        "UTC", 0.0, 0.0, "UTC", time_known=True,
    )
    row = next((item for item in _planet_rows(chart) if item["id"] == planet_id), None)
    longitude = _longitude(row or {})
    if longitude is None:
        raise ChartProductError(
            "calculation_unavailable",
            "Долгота планеты недоступна для расчёта возврата.",
            [planet_id],
        )
    return longitude



def _target_on_arc(first: float, second: float, target: float) -> bool:
    """Return whether target lies on the shortest sampled arc first→second."""
    movement = (second - first + 180) % 360 - 180
    if abs(movement) < 1e-9:
        return _circular_distance(first, target) < 1e-7
    if movement > 0:
        return ((target - first) % 360) <= movement + 1e-9
    return ((first - target) % 360) <= -movement + 1e-9



def _refine_return(lo: datetime, hi: datetime, target: float, planet_id: str,
                   lo_longitude: float, hi_longitude: float) -> tuple[datetime, float]:
    """Refine a bounded crossing to one-minute resolution."""
    if lo == hi:
        return lo, lo_longitude
    while hi - lo > timedelta(minutes=1):
        span_minutes = int((hi - lo).total_seconds() // 60)
        midpoint = lo + timedelta(minutes=max(1, span_minutes // 2))
        mid_longitude = _return_planet_longitude(midpoint, planet_id)
        if _target_on_arc(lo_longitude, mid_longitude, target):
            hi, hi_longitude = midpoint, mid_longitude
        else:
            lo, lo_longitude = midpoint, mid_longitude
    if _circular_distance(lo_longitude, target) <= _circular_distance(hi_longitude, target):
        return lo, lo_longitude
    return hi, hi_longitude



def _valid_coordinates(lat: float | None, lon: float | None) -> bool:
    try:
        return (lat is not None and lon is not None
                and math.isfinite(float(lat)) and math.isfinite(float(lon))
                and -90 <= float(lat) <= 90 and -180 <= float(lon) <= 180)
    except (TypeError, ValueError):
        return False



def build_returns_contract(natal_chart: dict[str, Any], *, target_year: int,
                           planet_id: str = "Sun", lat: float | None = None,
                           lon: float | None = None, tz_name: str | None = None) -> dict[str, Any]:
    """Build a v1 solar-return event using a bounded canonical ephemeris search."""
    if target_year < 1900 or target_year > 2200:
        raise ChartProductError("invalid_year", "Год возврата должен быть между 1900 и 2200 годом.")
    if planet_id not in RETURNS_SUPPORTED_PLANETS:
        raise ChartProductError("unsupported_planet", "В первой версии доступен только возврат Солнца.")
    _require_full_exact(natal_chart, "owner")
    if not _valid_coordinates(lat, lon) or not tz_name:
        raise ChartProductError(
            "return_location_required",
            "Для локального времени возврата нужны сохранённые координаты и часовой пояс.",
            ["lat", "lon", "tz"],
        )
    try:
        local_zone = ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ChartProductError("return_location_required", "Часовой пояс владельца недоступен.", ["tz"]) from exc

    natal_row = next((row for row in _planet_rows(natal_chart) if row["id"] == planet_id), None)
    natal_longitude = _longitude(natal_row or {})
    if natal_longitude is None:
        raise ChartProductError("chart_required", "В натальной карте нет долготы Солнца.", [planet_id])

    start = datetime(target_year, 1, 1, tzinfo=timezone.utc)
    end = datetime(target_year + 1, 1, 1, tzinfo=timezone.utc)
    step = timedelta(hours=12)
    samples: list[tuple[datetime, float]] = []
    instant = start
    while instant <= end:
        samples.append((instant, _return_planet_longitude(instant, planet_id)))
        instant += step

    matches: list[tuple[datetime, float]] = []
    for (lo, lo_longitude), (hi, hi_longitude) in zip(samples, samples[1:]):
        if _circular_distance(lo_longitude, natal_longitude) < 1e-7:
            match = (lo, lo_longitude)
        elif _target_on_arc(lo_longitude, hi_longitude, natal_longitude):
            match = _refine_return(lo, hi, natal_longitude, planet_id, lo_longitude, hi_longitude)
        else:
            continue
        if not matches or match[0] != matches[-1][0]:
            matches.append(match)

    if not matches:
        raise ChartProductError(
            "no_return_found",
            "В заданном году момент возврата не найден.",
            [planet_id, str(target_year)],
        )

    serialized_matches = []
    for matched_at, matched_longitude in matches:
        matched_at = matched_at.astimezone(timezone.utc)
        serialized_matches.append({
            "return_at_utc": matched_at.isoformat(),
            "return_at_local": matched_at.astimezone(local_zone).isoformat(),
            "return_longitude_deg": matched_longitude,
        })
    first = serialized_matches[0]
    limitations = [
        "Это астрономический момент возврата, а не гарантия события.",
        "Первая версия поддерживает только солнечный возврат; дома, ASC/MC и return wheel не строятся.",
    ]
    if len(serialized_matches) > 1:
        limitations.append("В заданном году найдено несколько пересечений; все моменты перечислены в matches.")
    result = {
        "returns_schema_version": RETURNS_SCHEMA_VERSION,
        "product": "returns",
        "planet": planet_id,
        "planet_label": astro.PLANET_RU[planet_id],
        "target_year": target_year,
        "precision": "exact",
        "natal_evidence": _chart_evidence(natal_chart),
        "natal_longitude_deg": natal_longitude,
        "return_longitude_deg": first["return_longitude_deg"],
        "return_at_utc": first["return_at_utc"],
        "return_at_local": first["return_at_local"],
        "timezone": tz_name,
        "search_window": {"start": start.isoformat(), "end": end.isoformat()},
        "match_count": len(serialized_matches),
        "matches": serialized_matches,
        "limitations": limitations,
    }
    validate_returns_contract(result)
    return result



def _finite_degree(value: Any) -> bool:
    try:
        return math.isfinite(float(value)) and 0 <= float(value) < 360
    except (TypeError, ValueError):
        return False


def _validate_aspect_rows(rows: Any, *, allowed_roles: set[tuple[str, str]]) -> None:
    if not isinstance(rows, list):
        raise ChartProductError("invalid_product_contract", "Список аспектов имеет неверный формат.")
    for row in rows:
        if not isinstance(row, dict) or row.get("code") not in astro.ASPECT_RU:
            raise ChartProductError("invalid_product_contract", "Аспект не соответствует policy.")
        if tuple((row.get("first_role"), row.get("second_role"))) not in allowed_roles:
            raise ChartProductError("invalid_product_contract", "Роль точки в аспекте не соответствует contract.")
        if not _finite_degree(float(row.get("orb_exact", -1))):
            raise ChartProductError("invalid_product_contract", "Орб аспекта имеет неверный формат.")
        if float(row["orb_exact"]) > astro.ASPECT_ORBS[row["code"]] + 1e-9:
            raise ChartProductError("invalid_product_contract", "Орб аспекта превышает product policy.")


def validate_synastry_contract(result: dict[str, Any]) -> None:
    if result.get("synastry_schema_version") != SYNASTRY_SCHEMA_VERSION or result.get("product") != "synastry":
        raise ChartProductError("invalid_product_contract", "Неверная версия synastry contract.")
    if result.get("precision") != "exact":
        raise ChartProductError("exact_charts_required", "Synastry contract требует exact precision.")
    for role in ("person", "partner"):
        block = result.get(role) or {}
        planets = block.get("planets")
        if block.get("role") not in {"owner", "partner"} or not isinstance(planets, list) or not planets:
            raise ChartProductError("invalid_product_contract", "Synastry source block неполон.", [role])
        ids = [item.get("id") for item in planets if isinstance(item, dict)]
        if len(ids) != len(set(ids)):
            raise ChartProductError("invalid_product_contract", "В synastry source есть duplicate points.", [role])
        if any(not _finite_degree(item.get("abs_deg_exact", item.get("abs_deg"))) for item in planets):
            raise ChartProductError("invalid_product_contract", "В synastry source есть невалидная долгота.", [role])
    _validate_aspect_rows(result.get("aspects"), allowed_roles={("owner", "partner")})


def validate_composite_contract(result: dict[str, Any]) -> None:
    if result.get("composite_schema_version") != COMPOSITE_SCHEMA_VERSION or result.get("product") != "composite":
        raise ChartProductError("invalid_product_contract", "Неверная версия composite contract.")
    if result.get("precision") != "exact":
        raise ChartProductError("exact_charts_required", "Composite contract требует exact precision.")
    points = result.get("points")
    if not isinstance(points, list) or not points:
        raise ChartProductError("invalid_product_contract", "Composite points отсутствуют.")
    ids = [point.get("id") for point in points if isinstance(point, dict)]
    if len(ids) != len(set(ids)):
        raise ChartProductError("invalid_product_contract", "Composite содержит duplicate points.")
    for point in points:
        source = point.get("source") or {}
        first = source.get("owner_abs_deg_exact")
        second = source.get("partner_abs_deg_exact")
        expected = circular_midpoint(float(first), float(second))
        actual = point.get("abs_deg_exact")
        if not _finite_degree(first) or not _finite_degree(second) or not _finite_degree(actual):
            raise ChartProductError("invalid_product_contract", "Composite longitude is invalid.")
        if _circular_distance(expected, float(actual)) > 1e-9:
            raise ChartProductError("invalid_product_contract", "Composite midpoint is not shortest-arc deterministic.")
    _validate_aspect_rows(result.get("aspects"), allowed_roles={("composite", "composite")})


def validate_transit_contract(result: dict[str, Any]) -> None:
    if result.get("transit_schema_version") != TRANSIT_SCHEMA_VERSION or result.get("product") != "transits":
        raise ChartProductError("invalid_product_contract", "Неверная версия transit contract.")
    if result.get("precision") not in {"day", "instant"}:
        raise ChartProductError("invalid_product_contract", "Transit precision должен быть day или instant.")
    if not isinstance(result.get("as_of"), str) or not isinstance(result.get("sampled_at"), str):
        raise ChartProductError("invalid_product_contract", "Transit timestamps отсутствуют.")
    planets = result.get("transit_planets")
    if not isinstance(planets, list) or not planets or any(
        not _finite_degree(item.get("abs_deg_exact", item.get("abs_deg"))) for item in planets
    ):
        raise ChartProductError("invalid_product_contract", "Transit planet inventory invalid.")
    _validate_aspect_rows(result.get("aspects_to_natal"), allowed_roles={("transit", "natal")})


def validate_returns_contract(result: dict[str, Any]) -> None:
    if result.get("returns_schema_version") != RETURNS_SCHEMA_VERSION or result.get("product") != "returns":
        raise ChartProductError("invalid_product_contract", "Неверная версия returns contract.")
    if result.get("precision") != "exact" or result.get("planet") not in RETURNS_SUPPORTED_PLANETS:
        raise ChartProductError("invalid_product_contract", "Returns contract имеет несовместимую precision или planet.")
    matches = result.get("matches")
    if not isinstance(matches, list) or not matches or result.get("match_count") != len(matches):
        raise ChartProductError("invalid_product_contract", "Solar-return matches неполны.")
    parsed: list[datetime] = []
    for match in matches:
        try:
            instant = datetime.fromisoformat(match["return_at_utc"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ChartProductError("invalid_product_contract", "UTC return timestamp invalid.") from exc
        if instant.tzinfo is None or not _finite_degree(match.get("return_longitude_deg")):
            raise ChartProductError("invalid_product_contract", "Solar-return match has invalid timestamp/longitude.")
        parsed.append(instant.astimezone(timezone.utc))
    if parsed != sorted(parsed):
        raise ChartProductError("invalid_product_contract", "Solar-return matches должны быть отсортированы.")
    target = result.get("natal_longitude_deg")
    for match in matches:
        if _circular_distance(float(target), float(match["return_longitude_deg"])) > 0.2:
            raise ChartProductError("invalid_product_contract", "Solar-return root не подтверждён точностью поиска.")
