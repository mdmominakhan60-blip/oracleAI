from __future__ import annotations

import pytest

from app.core import agent as agent_core
from app.core import astro


def _chart(*, exact: bool) -> dict:
    planets = [
        {"name": "Солнце", "sign": "Лев", "deg": 10.0, "abs_deg": 130.0, "house": 1 if exact else None, "retro": False},
        {"name": "Луна", "sign": "Рак", "deg": 8.0, "abs_deg": 98.0, "house": 12 if exact else None, "retro": False},
        {"name": "Меркурий", "sign": "Дева", "deg": 4.0, "abs_deg": 154.0, "house": 2 if exact else None, "retro": False},
        {"name": "Венера", "sign": "Весы", "deg": 16.0, "abs_deg": 196.0, "house": 3 if exact else None, "retro": False},
        {"name": "Марс", "sign": "Скорпион", "deg": 2.0, "abs_deg": 212.0, "house": 4 if exact else None, "retro": False},
    ]
    return {
        "mode": "full",
        "precision": "exact" if exact else "date_only",
        "sun": {"sign": "Лев", "symbol": "☉", "element": "огонь"},
        "ascendant": {"sign": "Рак", "deg": 12.0, "abs_deg": 102.0} if exact else None,
        "mc": {"sign": "Овен", "deg": 4.0} if exact else None,
        "planets": planets,
        "houses": ([
            {"n": 2, "sign": "Лев", "deg": 1.0},
            {"n": 6, "sign": "Стрелец", "deg": 7.0},
            {"n": 7, "sign": "Козерог", "deg": 13.0},
            {"n": 10, "sign": "Овен", "deg": 4.0},
        ] if exact else []),
        "aspects": [],
        "nodes": [
            {"name": "Раху (Северный узел)", "sign": "Близнецы", "deg": 22.0},
            {"name": "Кету (Южный узел)", "sign": "Стрелец", "deg": 22.0},
        ],
    }


def test_chart_sections_cover_required_user_topics() -> None:
    result = astro.chart_sections(_chart(exact=True), time_known=True)
    sections = result["sections"]
    assert result["exact"] is True
    assert set(sections) == {"identity", "mind_career", "relationships", "nodes"}
    labels = {item["label"] for section in sections.values() for item in section["items"]}
    assert {"Солнце", "Луна", "Асцендент", "Меркурий", "Марс", "Карьера", "Финансы", "Венера", "7-й дом", "Кету · Южный узел", "Раху · Северный узел"} <= labels
    assert "привычную силу" in sections["nodes"]["intro"]
    assert "направление роста" in sections["nodes"]["intro"]
    assert sections["mind_career"]["items"][-1]["available"] is True


def test_chart_sections_hide_unreliable_houses_without_birth_time() -> None:
    result = astro.chart_sections(_chart(exact=False), time_known=False)
    sections = result["sections"]
    assert result["exact"] is False
    identity = {item["label"]: item for item in sections["identity"]["items"]}
    assert identity["Солнце"]["available"] is True
    assert identity["Асцендент"]["available"] is False
    career = {item["label"]: item for item in sections["mind_career"]["items"]}
    assert career["Карьера"]["available"] is False
    assert career["Финансы"]["available"] is False
    assert "точные дома" in sections["mind_career"]["note"]


@pytest.mark.asyncio
async def test_interpret_chart_retries_until_all_required_topics_are_present(monkeypatch):
    chart = _chart(exact=True)
    user = {"tg_id": 7001, "birth_time_known": 1}
    calls = []

    async def fake_system_for(*_args, **_kwargs):
        return "Ты — Урания"

    async def fake_guide(*_args, **_kwargs):
        return "Используй только проверенные данные карты."

    full = "\n\n".join([
        "**1. Ядро личности** Солнце во Льве, Луна в Раке и Асцендент в Раке описывают разные слои самовосприятия и первого впечатления.",
        "**2. Интеллект и общение** Меркурий в Деве задаёт тему точности, проверки деталей и ясных формулировок.",
        "**3. Действие** Марс в Скорпионе символически связан с глубиной усилия, границами и выдержкой в напряжении.",
        "**4. Карьера и финансы** MC в Овне, 10-й дом в Овне, 6-й дом в Стрельце и 2-й дом во Льве дают темы инициативы, режима и ресурсов.",
        "**5. Любовь** Венера в Весах показывает ценность взаимности, эстетики и уважительного диалога.",
        "**6. Партнёрство** 7-й дом в Козероге предлагает смотреть на договорённости и ответственность, а не искать идеальный сценарий.",
        "**7. Узлы** Кету в Стрельце можно читать как привычный багаж, а Раху в Близнецах — как символическое направление роста и любопытства.",
        "**8. Синтез** Сопоставь реакцию Луны, способ действия Марса и реальные разговоры; выбери один проверяемый шаг и оцени результат через неделю.",
    ])

    async def fake_complete(_system, user_text, **_kwargs):
        calls.append(user_text)
        return "Солнце в Льве." if len(calls) < 3 else full

    monkeypatch.setattr(agent_core.llm, "enabled", lambda: True)
    monkeypatch.setattr(agent_core.agents, "system_for", fake_system_for)
    monkeypatch.setattr(agent_core.skills, "guide", fake_guide)
    monkeypatch.setattr(agent_core.llm, "complete", fake_complete)

    text, live = await agent_core.interpret_chart(None, user, chart)
    assert live is True
    assert len(calls) == 3
    assert "ПОВТОРНАЯ ГЕНЕРАЦИЯ" in calls[1]
    assert all(term in text for term in ("Луна", "Меркурий", "Марс", "Венера", "Кету"))
    assert len(text) >= 900


@pytest.mark.asyncio
async def test_interpret_chart_last_resort_is_detailed_and_covers_available_topics(monkeypatch):
    chart = _chart(exact=True)
    user = {"tg_id": 7002, "birth_time_known": 1}

    async def fake_system_for(*_args, **_kwargs):
        return "Ты — Урания"

    async def fake_guide(*_args, **_kwargs):
        return "Используй только проверенные данные карты."

    async def always_short(*_args, **_kwargs):
        return "Солнце в Льве."

    monkeypatch.setattr(agent_core.llm, "enabled", lambda: True)
    monkeypatch.setattr(agent_core.agents, "system_for", fake_system_for)
    monkeypatch.setattr(agent_core.skills, "guide", fake_guide)
    monkeypatch.setattr(agent_core.llm, "complete", always_short)

    text, live = await agent_core.interpret_chart(None, user, chart)
    assert live is False
    assert len(text) >= 900
    assert all(term in text for term in ("Луна", "Меркурий", "Марс", "Венера", "Кету", "Раху", "7-й дом"))
