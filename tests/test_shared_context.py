from __future__ import annotations

import json

import pytest

from app.core import shared_context
from app.core.agents import runtime
from app.core.agents.registry import codes, get
from app.repo import users


@pytest.mark.asyncio
async def test_shared_context_records_cross_agent_recommendations_and_canonical_transits(db, user):
    await users.update(db, user["tg_id"], memory_enabled=1)
    current = await users.get(db, user["tg_id"])
    saved = await shared_context.record_recommendation(
        db,
        current,
        agent="astro",
        text="Сначала проверь окно по датам, затем сделай один пробный шаг.",
        source_ref="thread:astro-1",
    )
    assert saved is True

    block = await shared_context.prompt_block(db, current, "Когда начинать проект?")
    assert "[SHARED_CONTEXT]" in block
    assert "astro" in block
    assert "Сначала проверь окно по датам" in block
    assert "active_transits" in block
    assert "canonical_transit_contract" in block


@pytest.mark.asyncio
async def test_shared_context_does_not_leak_when_memory_is_disabled(db, user):
    await users.update(db, user["tg_id"], memory_enabled=1)
    enabled = await users.get(db, user["tg_id"])
    await shared_context.record_recommendation(
        db, enabled, agent="tarot", text="Секретная рекомендация", source_ref="reading:1"
    )
    await users.update(db, user["tg_id"], memory_enabled=0)
    disabled = await users.get(db, user["tg_id"])
    block = await shared_context.prompt_block(db, disabled, "вопрос")
    assert "Секретная рекомендация" not in block
    assert "память пользователя выключена" in block


@pytest.mark.asyncio
async def test_all_agents_receive_shared_context_and_compact_natal_json(db, user):
    await users.update(db, user["tg_id"], memory_enabled=1)
    current = await users.get(db, user["tg_id"])
    await shared_context.record_recommendation(
        db, current, agent="oracle", text="Сделай один наблюдаемый шаг.", source_ref="thread:1"
    )
    for code in codes():
        prompt = await runtime.system_for(db, current, get(code), question="Какой мой следующий шаг?")
        assert "[SHARED_CONTEXT]" in prompt
        assert "[NATAL_CONTEXT_JSON]" in prompt
        assert '"schema_version":1' in prompt
    assert '"Марс"' in prompt or "Марс" in prompt


def test_compact_natal_summary_is_bounded_and_respects_unknown_time():
    chart = {
        "precision": "unknown",
        "planets": [
            {"name": "Солнце", "sign": "Рак", "element": "вода", "house": 4},
            {"name": "Марс", "sign": "Дева", "element": "земля", "house": 6},
            {"name": "Неизвестная точка", "sign": "Овен", "element": "огонь"},
        ],
        "houses": [{"n": 1, "sign": "Весы"}],
        "nodes": [{"name": "Раху (Северный узел)", "sign": "Козерог", "house": 10}],
    }
    summary = shared_context.compact_natal_summary(chart, time_known=False)
    assert summary["precision"] == "date_only_or_unknown"
    assert summary["houses_available"] is False
    assert "house" not in summary["planets"]["Марс"]
    assert "Неизвестная точка" not in json.dumps(summary, ensure_ascii=False)
