"""Защита LLM-слоя от всплеска: лимит частоты и одновременных вызовов.

На 10k пользователей без ограничителей пик вопросов или утренняя рассылка
открывают сотни соединений к провайдеру, который режет пачку 429-ми — и вместо
«сейчас отвечу» клиентки получают отказы. Проверяем, что слот работает.
"""
from __future__ import annotations

import asyncio
import time

import pytest

from app.config import settings
from app.core import llm


def test_completion_timeout_is_bounded():
    """Зависший провайдер не держит слот семафора минуты: таймаут ≤ 40с."""
    assert llm.TIMEOUT <= 40


def test_gpt_reasoning_effort_is_provider_correct(monkeypatch):
    monkeypatch.setattr(settings, "llm_reasoning_effort", "low")
    assert llm._reasoning_kwargs("gpt-5-mini") == {
        "extra_body": {"reasoning": {"effort": "low"}}
    }
    assert llm._reasoning_kwargs("claude-sonnet-4-6") == {}
    monkeypatch.setattr(settings, "llm_reasoning_effort", "unsupported")
    assert llm._reasoning_kwargs("gpt-5") == {
        "extra_body": {"reasoning": {"effort": "minimal"}}
    }


async def test_rate_limit_paces_bursts():
    """После заполнения окна следующий вызов ждёт, а не проходит сразу."""
    rl = llm._RateLimit(rate=2, window_sec=1)
    await rl.acquire()
    await rl.acquire()
    started = time.monotonic()
    await rl.acquire()          # третьего токена нет — ждём истечения первого
    assert time.monotonic() - started >= 0.8


async def test_semaphore_bounds_concurrent_calls(monkeypatch):
    """Всплеск вызовов не открывает больше соединений, чем разрешено."""
    monkeypatch.setattr(settings, "llm_provider", "anthropic")
    monkeypatch.setattr(settings, "anthropic_key", "test")
    monkeypatch.setattr(llm, "_CONCURRENCY", asyncio.Semaphore(3))
    monkeypatch.setattr(llm, "_RATE", llm._RateLimit(10_000))  # частоту не режем

    active = 0
    peak = 0

    async def fake_complete(*_a, **_k):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.05)
        active -= 1
        return "ок"

    monkeypatch.setattr(llm, "_complete_with", fake_complete)
    results = await asyncio.gather(*(llm.complete("s", "u") for _ in range(20)))
    assert all(r == "ок" for r in results)
    assert peak <= 3


async def _two_provider_chain(monkeypatch):
    """Цепочка anthropic → openai; custom-провайдер в тестовом .env гасим."""
    monkeypatch.setattr(settings, "llm_provider", "anthropic")
    monkeypatch.setattr(settings, "anthropic_key", "k")
    monkeypatch.setattr(settings, "openai_key", "k")
    monkeypatch.setattr(settings, "custom_base_url", "")
    monkeypatch.setattr(settings, "custom_model_main", "")


async def test_failover_uses_next_provider(monkeypatch, db):
    """Упавший основной не роняет ответ: цепочка переходит на резерв (G28)."""
    await _two_provider_chain(monkeypatch)

    calls = []

    async def flaky(provider, *a, **k):
        calls.append(provider)
        if provider == "anthropic":
            raise ConnectionError("основной упал")
        return "ответ от резерва"

    monkeypatch.setattr(llm, "_complete_with", flaky)
    assert await llm.complete("s", "u", db=db) == "ответ от резерва"
    assert calls == ["anthropic", "anthropic", "openai"], calls

    cur = await db.execute(
        "SELECT provider, ok FROM llm_usage ORDER BY id")
    rows = [dict(r) for r in await cur.fetchall()]
    assert {r["provider"] for r in rows} == {"anthropic", "openai"}
    assert next(r["ok"] for r in rows if r["provider"] == "openai")
    assert not next(r["ok"] for r in rows if r["provider"] == "anthropic")


async def test_failover_exhausts_all_providers(monkeypatch):
    """Все провайдеры легли — клиентке уходит явная ошибка, а не тишина (G28)."""
    await _two_provider_chain(monkeypatch)

    calls = []

    async def always_down(provider, *a, **k):
        calls.append(provider)
        raise ConnectionError("всё лежит")

    monkeypatch.setattr(llm, "_complete_with", always_down)
    with pytest.raises(RuntimeError):
        await llm.complete("s", "u")
    assert len(calls) == 2 * llm.RETRIES, "каждый провайдер пробуется до упора"


async def test_tool_results_are_bounded(monkeypatch):
    monkeypatch.setattr(llm, "MAX_TOOL_OUTPUT", 32)

    async def execute(_name, _args):
        return "x" * 100

    result = (await llm._gather_tools(execute, [("chart", {})]))[0]
    assert len(result) <= 32 + len("\n[данные сокращены; опирайся на доступную часть]")
    assert "данные сокращены" in result


async def test_tool_timeout_returns_safe_fallback(monkeypatch):
    monkeypatch.setattr(llm, "TOOL_TIMEOUT", 0.01)
    async def execute(_name, _args):
        await asyncio.sleep(0.05)
        return "late"

    result = (await llm._gather_tools(execute, [("chart", {})]))[0]
    assert "временно недоступны" in result
    assert "late" not in result


async def test_workflow_budget_rejects_excess_tool_calls():
    budget = llm._WorkflowBudget(timeout=10, max_tool_calls=1, max_cost_usd=1.0)
    budget.reserve_tools(1)
    with pytest.raises(RuntimeError, match="tool-call budget"):
        budget.reserve_tools(1)


def test_workflow_budget_rejects_excess_cost():
    budget = llm._WorkflowBudget(timeout=10, max_tool_calls=4, max_cost_usd=0.01)
    with pytest.raises(RuntimeError, match="cost budget"):
        budget.add_usage("gpt-5", 0, 10000)


async def test_workflow_budget_deadline_is_enforced():
    budget = llm._WorkflowBudget(timeout=0.001, max_tool_calls=4, max_cost_usd=1.0)
    await asyncio.sleep(0.01)
    with pytest.raises(TimeoutError, match="deadline"):
        budget.check()


async def test_complete_uses_workflow_deadline(monkeypatch):
    await _two_provider_chain(monkeypatch)
    monkeypatch.setattr(settings, "llm_workflow_timeout", 1.0)
    monkeypatch.setattr(llm, "_RATE", llm._RateLimit(10_000))

    async def slow_complete(*_args, **_kwargs):
        await asyncio.sleep(1.2)
        return "late"

    monkeypatch.setattr(llm, "_complete_with", slow_complete)
    with pytest.raises(RuntimeError, match="недоступны"):
        await llm.complete("s", "u")


async def test_complete_vision_passes_primary_and_bounded_focus_images(monkeypatch):
    await _two_provider_chain(monkeypatch)
    monkeypatch.setattr(llm, "_RATE", llm._RateLimit(10_000))
    seen = []

    async def capture(_provider, _system, _user_text, image_urls, *_args, **_kwargs):
        seen.append(image_urls)
        return "{}"

    monkeypatch.setattr(llm, "_vision_with", capture)
    result = await llm.complete_vision(
        "s", "u", "data:image/jpeg;base64,one",
        additional_image_data_urls=[
            "data:image/jpeg;base64,two",
            "data:image/jpeg;base64,three",
            "data:image/jpeg;base64,four",
        ],
    )
    assert result == "{}"
    assert seen == [[
        "data:image/jpeg;base64,one",
        "data:image/jpeg;base64,two",
        "data:image/jpeg;base64,three",
    ]]


async def test_complete_vision_uses_workflow_deadline(monkeypatch):
    await _two_provider_chain(monkeypatch)
    monkeypatch.setattr(settings, "llm_workflow_timeout", 1.0)
    monkeypatch.setattr(llm, "_RATE", llm._RateLimit(10_000))

    async def slow_vision(*_args, **_kwargs):
        await asyncio.sleep(1.2)
        return "late"

    monkeypatch.setattr(llm, "_vision_with", slow_vision)
    with pytest.raises(RuntimeError, match="vision-провайдеры"):
        await llm.complete_vision("s", "u", "data:image/jpeg;base64,AA==")
