from __future__ import annotations

import asyncio

import pytest

from app.core.agents import runtime_guard


@pytest.mark.asyncio
async def test_public_answer_has_one_outer_deadline(monkeypatch):
    class Spec:
        code = "mira"
        timeout_s = 0.01

    async def slow_answer(*args, **kwargs):
        await asyncio.sleep(1)
        return "never"

    monkeypatch.setattr(runtime_guard.runtime, "get", lambda code: Spec())
    monkeypatch.setattr(runtime_guard.runtime, "answer", slow_answer)
    monkeypatch.setattr(runtime_guard.runtime.users_repo, "chart_of", lambda user: {})
    monkeypatch.setattr(runtime_guard.runtime, "offline_answer", lambda user, q, chart, memories, spec: "offline")

    user = {"tg_id": 1, "memory_enabled": False}
    result = await runtime_guard.answer(None, user, "test", agent="mira")
    assert result == "offline"


@pytest.mark.asyncio
async def test_public_answer_preserves_success(monkeypatch):
    class Spec:
        code = "mira"
        timeout_s = 1.0

    async def fast_answer(*args, **kwargs):
        return "ok"

    monkeypatch.setattr(runtime_guard.runtime, "get", lambda code: Spec())
    monkeypatch.setattr(runtime_guard.runtime, "answer", fast_answer)
    result = await runtime_guard.answer(None, {"tg_id": 1, "memory_enabled": False}, "test", agent="mira")
    assert result == "ok"
