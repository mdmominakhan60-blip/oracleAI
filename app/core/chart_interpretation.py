"""Structured natal interpretation contract.

The model receives deterministic evidence and returns JSON only. This module
validates shape/lengths before the result is cached or rendered to legacy text.
"""
from __future__ import annotations

import json
import re
from typing import Any

MAX = {
    "luminaries.sun": 500,
    "luminaries.moon": 500,
    "luminaries.ascendant": 500,
    "personality_portrait": 900,
    "purpose": 700,
    "relationships": 700,
    "career_money": 700,
    "aspect_synthesis": 700,
    "synthesis": 900,
    "disclaimer": 260,
    "rahu_ketu.rahu": 600,
    "rahu_ketu.ketu": 600,
    "rahu_ketu.growth_step": 450,
    "peak_periods.status": 320,
    "peak_periods.note": 450,
    "list_item": 280,
}

REQUIRED_KEYS = {
    "luminaries", "personality_portrait", "rahu_ketu", "strengths", "weaknesses",
    "purpose", "relationships", "career_money", "aspect_synthesis",
    "peak_periods", "synthesis", "disclaimer",
}

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": sorted(REQUIRED_KEYS),
    "properties": {
        "luminaries": {
            "type": "object", "additionalProperties": False,
            "required": ["sun", "moon", "ascendant"],
            "properties": {
                "sun": {"type": "string", "maxLength": MAX["luminaries.sun"]},
                "moon": {"type": "string", "maxLength": MAX["luminaries.moon"]},
                "ascendant": {"type": "string", "maxLength": MAX["luminaries.ascendant"]},
            },
        },
        "personality_portrait": {"type": "string", "maxLength": MAX["personality_portrait"]},
        "rahu_ketu": {
            "type": "object", "additionalProperties": False,
            "required": ["rahu", "ketu", "growth_step"],
            "properties": {
                "rahu": {"type": "string", "maxLength": MAX["rahu_ketu.rahu"]},
                "ketu": {"type": "string", "maxLength": MAX["rahu_ketu.ketu"]},
                "growth_step": {"type": "string", "maxLength": MAX["rahu_ketu.growth_step"]},
            },
        },
        "strengths": {"type": "array", "minItems": 2, "maxItems": 5, "items": {"type": "string", "maxLength": MAX["list_item"]}},
        "weaknesses": {"type": "array", "minItems": 2, "maxItems": 4, "items": {"type": "string", "maxLength": MAX["list_item"]}},
        "purpose": {"type": "string", "maxLength": MAX["purpose"]},
        "relationships": {"type": "string", "maxLength": MAX["relationships"]},
        "career_money": {"type": "string", "maxLength": MAX["career_money"]},
        "aspect_synthesis": {"type": "string", "maxLength": MAX["aspect_synthesis"]},
        "peak_periods": {
            "type": "object", "additionalProperties": False,
            "required": ["status", "periods", "note"],
            "properties": {
                "status": {"type": "string", "maxLength": MAX["peak_periods.status"]},
                "periods": {"type": "array", "maxItems": 4, "items": {"type": "string", "maxLength": MAX["list_item"]}},
                "note": {"type": "string", "maxLength": MAX["peak_periods.note"]},
            },
        },
        "synthesis": {"type": "string", "maxLength": MAX["synthesis"]},
        "disclaimer": {"type": "string", "maxLength": MAX["disclaimer"]},
    },
}


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def parse_json_object(raw: str) -> dict[str, Any]:
    """Parse JSON while accepting a fenced response, never arbitrary prose."""
    value = (raw or "").strip()
    if value.startswith("```"):
        value = re.sub(r"^```(?:json)?\s*|\s*```$", "", value, flags=re.I | re.S).strip()
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise ValueError("structured natal output must be a JSON object")
    return parsed


def validate_payload(payload: dict[str, Any], *, chart: dict, time_known: bool) -> list[str]:
    issues: list[str] = []
    missing = REQUIRED_KEYS - set(payload)
    if missing:
        issues.append("missing keys: " + ", ".join(sorted(missing)))
    extra = set(payload) - REQUIRED_KEYS
    if extra:
        issues.append("unexpected keys: " + ", ".join(sorted(extra)))
    for key in REQUIRED_KEYS & set(payload):
        value = payload[key]
        if key in {"luminaries", "rahu_ketu", "peak_periods"}:
            if not isinstance(value, dict):
                issues.append(f"{key} must be an object")
                continue
            expected = {
                "luminaries": ("sun", "moon", "ascendant"),
                "rahu_ketu": ("rahu", "ketu", "growth_step"),
                "peak_periods": ("status", "periods", "note"),
            }[key]
            for nested_key in expected:
                if nested_key not in value:
                    issues.append(f"{key}.{nested_key} is missing")
            if key == "peak_periods":
                if not isinstance(value.get("periods"), list) or len(value.get("periods", [])) > 4:
                    issues.append("peak_periods.periods must be a list with up to four items")
                elif not all(isinstance(item, str) for item in value["periods"]):
                    issues.append("peak_periods.periods must contain strings")
            else:
                for nested_key in expected:
                    nested_value = value.get(nested_key)
                    if not isinstance(nested_value, str) or not nested_value.strip():
                        issues.append(f"{key}.{nested_key} must be a non-empty string")
                    elif len(nested_value.strip()) > MAX[f"{key}.{nested_key}"]:
                        issues.append(f"{key}.{nested_key} is too long")
            continue
        if key in {"strengths", "weaknesses"}:
            if not isinstance(value, list) or not value or not all(isinstance(item, str) and item.strip() for item in value):
                issues.append(f"{key} must be a non-empty string list")
            elif len(value) > (5 if key == "strengths" else 4):
                issues.append(f"{key} has too many items")
            for item in value if isinstance(value, list) else []:
                if len(item.strip()) > MAX["list_item"]:
                    issues.append(f"{key} item is too long")
            continue
        if not isinstance(value, str) or not value.strip():
            issues.append(f"{key} must be a non-empty string")
        elif len(value.strip()) > MAX.get(key, 1000):
            issues.append(f"{key} is too long")

    nodes = {str(item.get("name", "")): item for item in chart.get("nodes") or []}
    if time_known:
        for key in ("rahu", "ketu"):
            if not isinstance(payload.get("rahu_ketu"), dict) or not _text(payload["rahu_ketu"].get(key)):
                issues.append(f"rahu_ketu.{key} is empty")
    if not nodes and isinstance(payload.get("rahu_ketu"), dict):
        if any(_text(payload["rahu_ketu"].get(key)) for key in ("rahu", "ketu")):
            issues.append("Rahu/Ketu mentioned without node evidence")
    if not time_known and re.search(r"\b(?:\d{1,2}-й|\d{1,2}th|\d{1,2}st|\d{1,2}nd|\d{1,2}rd)\s+дом", json.dumps(payload, ensure_ascii=False), re.I):
        issues.append("house claim in date-only interpretation")
    return issues


def prompt(evidence_block: str, guide: str) -> str:
    return f"""{guide}

{evidence_block}

Верни только один валидный JSON-объект по схеме ниже, без Markdown, комментариев и текста до/после JSON.
LLM интерпретирует только проверенные данные выше и не вычисляет градусы, дома, аспекты или периоды самостоятельно.
Сначала называй факт из evidence, затем объясняй простыми словами и добавляй наблюдаемый следующий шаг.
Раху и Кету раскрывай прямо: Кету показывает накопленную силу и привычный сценарий, Раху — направление роста и новый опыт.
Если транзиты/периоды не переданы, status в peak_periods должен честно сказать, что deterministic-периоды не предоставлены, а periods должен быть [].
Если time_known=false, не упоминай ASC, MC или дома как факт.
Пиши на русском, на «ты», конкретно и без эзотерического тумана. Для поля disclaimer используй короткую сильную closing note, которая закрепляет главный инсайт карты; это поле сохраняется ради совместимости схемы.

JSON schema (contract v1):
{json.dumps(SCHEMA, ensure_ascii=False, separators=(',', ':'))}
"""


def render_text(payload: dict[str, Any]) -> str:
    """Render structured data for legacy rich-markdown UI and Telegram clients."""
    rk = payload["rahu_ketu"]
    periods = payload["peak_periods"]
    lum = payload["luminaries"]
    sections = [
        "**1. Солнце, Луна и Асцендент**\n"
        f"Солнце: {lum['sun']}\nЛуна: {lum['moon']}\nАсцендент: {lum['ascendant']}",
        f"**2. Общий портрет личности**\n{payload['personality_portrait']}",
        "**3. Раху и Кету**\n"
        f"Раху: {rk['rahu']}\nКету: {rk['ketu']}\n"
        f"Следующий шаг: {rk['growth_step']}",
        "**4. Сильные стороны**\n" + "\n".join(f"• {item}" for item in payload["strengths"]),
        "**5. Слабые стороны и точки внимания**\n" + "\n".join(f"• {item}" for item in payload["weaknesses"]),
        f"**6. Предназначение и жизненный вектор**\n{payload['purpose']}",
        f"**7. Отношения**\n{payload['relationships']}",
        f"**8. Карьера и деньги**\n{payload['career_money']}",
        f"**9. Аспекты и синтез**\n{payload['aspect_synthesis']}",
        "**10. Благоприятные периоды**\n"
        f"{periods['status']}\n" + ("\n".join(f"• {item}" for item in periods["periods"]) or "Периоды не рассчитаны.") + f"\n{periods['note']}",
        f"**11. Итог**\n{payload['synthesis']}\n\n_{payload['disclaimer']}_",
    ]
    return "\n\n".join(sections)
