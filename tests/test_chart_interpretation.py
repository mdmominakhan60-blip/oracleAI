from __future__ import annotations

import json

import pytest

from app.core import chart_interpretation


def valid_payload() -> dict:
    return {
        "luminaries": {
            "sun": "Солнце в Льве — наблюдаемый стиль воли и самовыражения.",
            "moon": "Луна в Раке — эмоциональный ритм, который можно проверять дневником.",
            "ascendant": "ASC недоступен без подтверждённого времени рождения.",
        },
        "personality_portrait": "Солнце и Луна задают разные ритмы, которые полезно согласовывать через наблюдение.",
        "rahu_ketu": {
            "rahu": "Раху: направление роста видно только в переданном placement, без обещания судьбы.",
            "ketu": "Кету: знакомая стратегия, которую можно использовать осознанно.",
            "growth_step": "Выбери один малый эксперимент и проверь результат через неделю.",
        },
        "strengths": ["Умение замечать связи", "Выносливость в длинных задачах"],
        "weaknesses": ["Склонность перегружать себя", "Трудность с паузой"],
        "purpose": "Собирай роль и среду через конкретные факты карты и собственные решения.",
        "relationships": "Венера и доступные данные отношений дают тему ясных договорённостей.",
        "career_money": "Планеты и доступные дома описывают рабочие привычки, а не гарантируют доход.",
        "aspect_synthesis": "Аспекты связывают ресурс и напряжение; проверь их на одном реальном выборе.",
        "peak_periods": {
            "status": "Deterministic-периоды не предоставлены.",
            "periods": [],
            "note": "Не заменяем отсутствие транзитов выдуманными датами.",
        },
        "synthesis": "Используй карту как язык вопросов, а следующий шаг сделай наблюдаемым и обратимым.",
        "disclaimer": "Символическая интерпретация для саморефлексии, не профессиональная рекомендация.",
    }


def test_valid_structured_payload_renders_legacy_text():
    payload = valid_payload()
    issues = chart_interpretation.validate_payload(
        payload, chart={"nodes": [{"name": "Раху (Северный узел)"}]}, time_known=True,
    )
    assert issues == []
    text = chart_interpretation.render_text(payload)
    assert "Общий портрет личности" in text
    assert "Раху" in text
    assert "Карьера и деньги" in text


def test_parser_accepts_json_fence_but_rejects_prose():
    payload = valid_payload()
    parsed = chart_interpretation.parse_json_object("```json\n" + json.dumps(payload, ensure_ascii=False) + "\n```")
    assert parsed["strengths"] == payload["strengths"]
    with pytest.raises(json.JSONDecodeError):
        chart_interpretation.parse_json_object("Вот мой разбор: " + json.dumps(payload, ensure_ascii=False))


def test_date_only_payload_cannot_claim_houses():
    payload = valid_payload()
    payload["career_money"] = "В 10-й дом ты войдёшь уверенно, а 2-й дом гарантирует деньги."
    issues = chart_interpretation.validate_payload(
        payload, chart={"nodes": []}, time_known=False,
    )
    assert any("house claim" in issue for issue in issues)


def test_extra_keys_and_missing_sections_are_rejected():
    payload = valid_payload()
    payload.pop("purpose")
    payload["unexpected"] = "not allowed"
    issues = chart_interpretation.validate_payload(payload, chart={"nodes": []}, time_known=False)
    assert any("missing keys" in issue for issue in issues)
    assert any("unexpected keys" in issue for issue in issues)


@pytest.mark.asyncio
async def test_canonical_chart_uses_structured_llm_path(monkeypatch):
    from app.core import agent as agent_core

    payload = valid_payload()
    monkeypatch.setattr(agent_core.llm, "enabled", lambda: True)

    async def fake_system_for(*_args, **_kwargs):
        return "system"

    async def fake_guide(*_args, **_kwargs):
        return "guide"

    async def fake_complete(*_args, **_kwargs):
        return json.dumps(payload, ensure_ascii=False)

    monkeypatch.setattr(agent_core.agents, "system_for", fake_system_for)
    monkeypatch.setattr(agent_core.skills, "guide", fake_guide)
    monkeypatch.setattr(agent_core.llm, "complete", fake_complete)

    chart = {
        "mode": "full",
        "calculation": {"contract_version": 1},
        "sun": {"sign": "Лев"},
        "planets": [{"name": "Солнце", "sign": "Лев", "deg": 12.4}],
        "nodes": [
            {"name": "Раху (Северный узел)", "sign": "Близнецы"},
            {"name": "Кету (Южный узел)", "sign": "Стрелец"},
        ], "houses": [], "aspects": [],
    }
    text, live = await agent_core.interpret_chart(
        None, {"birth_time_known": 0, "tg_id": 1}, chart,
    )
    assert live is True
    assert chart["interpretation_structured"]["strengths"] == payload["strengths"]
    assert "Общий портрет личности" in text
