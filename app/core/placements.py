"""Deterministic placement calculators for OracleAI.

The LLM never calculates these values. This module returns Swiss Ephemeris facts,
precision metadata, and compact interpretation scopes for the specialized agents.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from . import astro
from .chart_contract import public_calculation_contract
from .astro import (
    EPHEMERIS_ENGINE,
    HOUSE_SYSTEM_IDENTIFIER,
    HOUSE_SYSTEM_NAME,
    NODE_MODE,
    PERSPECTIVE_TYPE,
    SIGNS,
    ZODIAC_TYPE,
)

SIGN_SYMBOL = {name: symbol for name, symbol, _ in SIGNS}
SIGN_ELEMENT = {name: element for name, _, element in SIGNS}

PLACEMENT_META = {
    "moon_sign": {"label": "Лунный знак", "point": "Moon", "scope": "emotions, needs, safety"},
    "venus_sign": {"label": "Знак Венеры", "point": "Venus", "scope": "values, affection, attraction"},
    "rising_sign": {"label": "Восходящий знак", "point": "Ascendant", "scope": "first impression, approach, presentation"},
    "chiron_sign": {"label": "Знак Хирона", "point": "Chiron", "scope": "vulnerability, learning, repair"},
    "juno_sign": {"label": "Знак Джуно", "point": "Juno", "scope": "trust, commitment, agreements"},
    "jupiter_sign": {"label": "Знак Юпитера", "point": "Jupiter", "scope": "growth, learning, opportunity"},
    "mars_sign": {"label": "Знак Марса", "point": "Mars", "scope": "drive, action, boundaries"},
    "mercury_sign": {"label": "Знак Меркурия", "point": "Mercury", "scope": "communication, learning, decisions"},
    "neptune_sign": {"label": "Знак Нептуна", "point": "Neptune", "scope": "imagination, ideals, boundaries"},
    "north_node_sign": {"label": "Северный узел / Rahu", "point": "True_North_Lunar_Node", "scope": "growth direction, unfamiliar development"},
    "rahu_sign": {"label": "Раху (Северный узел)", "point": "True_North_Lunar_Node", "scope": "growth direction, unfamiliar development"},
    "pluto_sign": {"label": "Знак Плутона", "point": "Pluto", "scope": "transformation, power, renewal"},
    "saturn_sign": {"label": "Знак Сатурна", "point": "Saturn", "scope": "discipline, limits, mature skill"},
    "south_node_sign": {"label": "Южный узел / Ketu", "point": "True_South_Lunar_Node", "scope": "familiar strategies, inherited patterns"},
    "ketu_sign": {"label": "Кету (Южный узел)", "point": "True_South_Lunar_Node", "scope": "familiar strategies, inherited patterns"},
    "uranus_sign": {"label": "Знак Урана", "point": "Uranus", "scope": "freedom, innovation, change"},
    "asteroid_sign": {"label": "Знаки астероидов", "points": ("Ceres", "Vesta", "Pallas"), "scope": "care, devotion, problem-solving"},
    "ceres_sign": {"label": "Знак Цереры", "point": "Ceres", "scope": "care, nourishment, practical support"},
    "vesta_sign": {"label": "Знак Весты", "point": "Vesta", "scope": "devotion, focus, protected inner space"},
    "pallas_sign": {"label": "Знак Паллады", "point": "Pallas", "scope": "pattern recognition, strategy, creative intelligence"},
    "lilith_sign": {"label": "Лилит (Чёрная Луна)", "point": "True_Lilith", "scope": "shadow themes, autonomy, boundaries"},
}

WESTERN_PLACEMENTS = tuple(PLACEMENT_META)
ALL_CALCULATORS = WESTERN_PLACEMENTS + ("life_path", "chinese_zodiac", "natal_chart")

_CHINESE_ANIMALS = ("Крыса", "Бык", "Тигр", "Кролик", "Дракон", "Змея",
                    "Лошадь", "Коза", "Обезьяна", "Петух", "Собака", "Свинья")
_CHINESE_ELEMENTS = ("Дерево", "Огонь", "Земля", "Металл", "Вода")


def _parse_date(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError) as exc:
        raise ValueError("дата рождения должна быть в формате YYYY-MM-DD") from exc


def _parse_time(value: str | None) -> tuple[int, int] | None:
    if not value:
        return None
    try:
        parsed = datetime.strptime(value, "%H:%M")
    except (TypeError, ValueError) as exc:
        raise ValueError("время рождения должно быть в формате ЧЧ:ММ") from exc
    return parsed.hour, parsed.minute



_PLANET_RU = {
    "Sun": "Солнце", "Moon": "Луна", "Mercury": "Меркурий", "Venus": "Венера",
    "Mars": "Марс", "Jupiter": "Юпитер", "Saturn": "Сатурн", "Uranus": "Уран",
    "Neptune": "Нептун", "Pluto": "Плутон",
}


def _canonical_point(point_name: str, chart: dict) -> dict | None:
    if point_name in _PLANET_RU:
        label = _PLANET_RU[point_name]
        return next((item for item in chart.get("planets") or [] if item.get("name") == label), None)
    if point_name in {"True_North_Lunar_Node", "True_South_Lunar_Node", "True_Lilith"}:
        prefixes = {
            "True_North_Lunar_Node": "Раху",
            "True_South_Lunar_Node": "Кету",
            "True_Lilith": "Лилит",
        }
        return next((item for item in chart.get("nodes") or []
                     if str(item.get("name", "")).startswith(prefixes[point_name])), None)
    if point_name == "Ascendant":
        return chart.get("ascendant")
    if point_name == "Medium_Coeli":
        return chart.get("mc")
    return next((item for item in chart.get("additional_points") or []
                 if item.get("point") == point_name), None)


def _point_payload(point_name: str, chart: dict, *, exact: bool) -> dict:
    point = _canonical_point(point_name, chart)
    if point is None:
        raise ValueError(f"точка {point_name} недоступна в эфемеридах")
    sign = point.get("sign")
    if not sign:
        raise ValueError(f"знак для точки {point_name} не рассчитан")
    house = point.get("house")
    return {
        "point": point_name,
        "label": point_name.replace("_", " "),
        "sign": sign,
        "symbol": SIGN_SYMBOL.get(sign, ""),
        "element": SIGN_ELEMENT.get(sign, ""),
        "degree": round(float(point.get("deg_exact", 0.0)), 1),
        "degree_exact": float(point.get("deg_exact", 0.0)),
        "abs_degree": round(float(point.get("abs_deg_exact", 0.0)), 1),
        "abs_degree_exact": float(point.get("abs_deg_exact", 0.0)),
        "house": str(house) if exact and house else None,
        "retrograde": bool(point.get("retro", False)),
    }


def _western_meta(precision: str, note: str = "", chart: dict | None = None) -> dict:
    calculation = (chart or {}).get("calculation") or {}
    public_contract = public_calculation_contract(chart or {}) if chart else {}
    return {
        "precision": precision,
        "engine_provenance": public_contract.get("engine_provenance") or {},
        "source": "swiss_ephemeris",
        "engine": EPHEMERIS_ENGINE,
        "zodiac_type": ZODIAC_TYPE,
        "house_system": HOUSE_SYSTEM_IDENTIFIER,
        "house_system_name": HOUSE_SYSTEM_NAME,
        "perspective_type": PERSPECTIVE_TYPE,
        "node_mode": NODE_MODE,
        "note": note,
        "calculation": {
            "contract_version": calculation.get("contract_version"),
            "configuration_fingerprint": calculation.get("configuration_fingerprint"),
            "request_fingerprint": (calculation.get("input") or {}).get("request_fingerprint"),
        },
    }


def _western_points(birth_date: str, birth_time: str | None, city: str | None,
                    lat: float | None, lon: float | None, tz: str | None,
                    time_known: bool | None = None) -> tuple[dict, bool]:
    chart = astro.compute_chart(
        birth_date, birth_time, city, lat, lon, tz, time_known=time_known,
        coordinate_source="unknown", timezone_source="provided" if tz else "missing",
    )
    return chart, chart.get("precision") == "exact"


def life_path(birth_date: str) -> dict:
    d = _parse_date(birth_date)
    digits = [int(ch) for ch in d.strftime("%Y%m%d")]
    trace = [sum(digits)]
    value = trace[0]
    while value > 9 and value not in (11, 22, 33):
        value = sum(int(ch) for ch in str(value))
        trace.append(value)
    return {
        "code": "life_path",
        "label": "Число жизненного пути",
        "value": value,
        "trace": trace,
        "master_number": value in (11, 22, 33),
        "source": "digit_reduction",
        "interpretation_scope": "traditional themes of purpose and recurring choices",
    }


def chinese_zodiac(birth_date: str) -> dict:
    d = _parse_date(birth_date)
    try:
        from lunardate import LunarDate
        lunar = LunarDate.fromSolarDate(d.year, d.month, d.day)
        lunar_year = lunar.year
    except Exception as exc:  # noqa: BLE001
        raise ValueError("китайский календарь временно недоступен") from exc
    offset = lunar_year - 1984  # 1984 — Деревянная Крыса, начало 60-летнего цикла.
    animal = _CHINESE_ANIMALS[offset % 12]
    element = _CHINESE_ELEMENTS[(offset % 10) // 2]
    return {
        "code": "chinese_zodiac",
        "label": "Китайский зодиакальный знак",
        "animal": animal,
        "element": element,
        "lunar_year": lunar_year,
        "western_year": d.year,
        "boundary_adjusted": lunar_year != d.year,
        "source": "lunisolar_calendar",
        "interpretation_scope": "temperament and habitual way of moving through life",
    }


def calculate_placement(code: str, birth_date: str, birth_time: str | None = None,
                        city: str | None = None, lat: float | None = None,
                        lon: float | None = None, tz: str | None = None,
                        time_known: bool | None = None) -> dict:
    if code == "life_path":
        return life_path(birth_date)
    if code == "chinese_zodiac":
        return chinese_zodiac(birth_date)
    if code == "natal_chart":
        model, exact = _western_points(birth_date, birth_time, city, lat, lon, tz, time_known)
        return {"code": code, "label": "Натальная карта",
                **_western_meta(model.get("precision", "date_only"), chart=model),
                "points": all_western(model, exact=exact)}
    if code not in PLACEMENT_META:
        raise ValueError("неизвестный placement-калькулятор")
    meta = PLACEMENT_META[code]
    model, exact = _western_points(birth_date, birth_time, city, lat, lon, tz, time_known)
    precision = model.get("precision", "exact" if exact else "date_only")
    note = "" if exact else "Время/координаты не подтверждены; дома и углы скрыты."
    if code == "rising_sign" and not exact:
        return {"code": code, "label": meta["label"],
                **_western_meta("insufficient", chart=model),
                "error": "Для Асцендента нужны точные дата, время, город и таймзона."}
    if "points" in meta:
        points = [_point_payload(point, model, exact=exact) for point in meta["points"]]
        return {"code": code, "label": meta["label"], "points": points,
                **_western_meta(precision, note, chart=model),
                "interpretation_scope": meta["scope"]}
    point = _point_payload(meta["point"], model, exact=exact)
    return {"code": code, "label": meta["label"], **point,
            **_western_meta(precision, note, chart=model),
            "interpretation_scope": meta["scope"]}


def all_western(model, *, exact: bool) -> list[dict]:
    points = []
    for code, meta in PLACEMENT_META.items():
        if "points" in meta:
            for point_name in meta["points"]:
                point = _point_payload(point_name, model, exact=exact)
                points.append({"code": code, "label": meta["label"], **point,
                               "interpretation_scope": meta["scope"]})
        else:
            if code == "rising_sign" and not exact:
                points.append({"code": code, "label": meta["label"],
                               "precision": "insufficient",
                               "error": "Для Асцендента нужны точные дата, время, город и таймзона.",
                               "source": "swiss_ephemeris",
                               "interpretation_scope": meta["scope"]})
                continue
            point = _point_payload(meta["point"], model, exact=exact)
            points.append({"code": code, "label": meta["label"], **point,
                           "precision": "exact" if exact else "date_only",
                           "interpretation_scope": meta["scope"]})
    return points


def all_calculators(birth_date: str, birth_time: str | None = None,
                    city: str | None = None, lat: float | None = None,
                    lon: float | None = None, tz: str | None = None,
                    time_known: bool | None = None) -> list[dict]:
    model, exact = _western_points(birth_date, birth_time, city, lat, lon, tz, time_known)
    out = all_western(model, exact=exact)
    out += [life_path(birth_date), chinese_zodiac(birth_date)]
    return out


def as_tool_json(data: dict | list[dict]) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))
