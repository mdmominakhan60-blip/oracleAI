from __future__ import annotations

from app.repo import dialog
from app.services import rate_limit


async def test_memory_limiter_returns_retry_after_without_cross_user_coupling():
    limiter = rate_limit.MemoryLimiter()
    first = await limiter.allow("1001", "llm", 1, 60)
    blocked = await limiter.allow("1001", "llm", 1, 60)
    other_user = await limiter.allow("1002", "llm", 1, 60)

    assert first.allowed
    assert not blocked.allowed
    assert blocked.retry_after > 0
    assert blocked.backend == "memory"
    assert other_user.allowed


async def test_chat_request_claim_replays_completed_response(db):
    first = await dialog.claim_chat_request(db, 1001, "request-1")
    assert first == {"state": "claimed"}

    payload = {"answer": "ok", "thread_id": 7}
    await dialog.finish_chat_request(db, 1001, "request-1", payload)

    replay = await dialog.claim_chat_request(db, 1001, "request-1")
    assert replay["state"] == "completed"
    assert replay["response"] == payload


async def test_chat_request_key_is_scoped_to_owner(db):
    first = await dialog.claim_chat_request(db, 1001, "request-owner")
    assert first["state"] == "claimed"
    conflict = await dialog.claim_chat_request(db, 1002, "request-owner")
    assert conflict["state"] == "conflict"


async def test_chat_service_replays_idempotent_result_without_second_generation(db, user, monkeypatch):
    from app.core import agent as agent_core
    from app.services import chat

    calls = 0

    async def fake_answer(*args, **kwargs):
        nonlocal calls
        calls += 1
        return "deterministic answer"

    monkeypatch.setattr(agent_core, "ask_oracle", fake_answer)
    first = await chat.ask(db, user, "Повтори один раз", idempotency_key="same-request")
    second = await chat.ask(db, user, "Повтори один раз", idempotency_key="same-request")

    assert calls == 1
    assert second == first
