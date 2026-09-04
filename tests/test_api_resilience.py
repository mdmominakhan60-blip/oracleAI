from __future__ import annotations

import pytest

from conftest import TEST_DEV_KEY  # noqa: E402
from httpx import ASGITransport, AsyncClient

from app.api.routers import profile as profile_router
from app.api.deps import get_db
from app.api.main import app
from app.repo import users


@pytest.fixture
async def resilience_client(db, user):
    app.dependency_overrides[get_db] = lambda: db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test",
                      headers={"X-Dev-Key": TEST_DEV_KEY}) as client:
        yield client
    app.dependency_overrides.clear()



def auth(user, extra: dict | None = None) -> dict:

    return {"dev_user": user["tg_id"], **(extra or {})}


async def test_route_resilience_matrix(resilience_client, db, user):
    client = resilience_client
    unauthenticated = await client.get("/api/memories")
    assert unauthenticated.status_code == 401

    bad_profile = await client.post(
        "/api/profile", params=auth(user), json={"lang": "fr"})
    assert bad_profile.status_code == 400

    bad_memory = await client.post(
        "/api/memories", params=auth(user), json={"fact": "x"})
    assert bad_memory.status_code == 422

    await users.update(db, user["tg_id"], memory_enabled=0)
    paused = await client.post(
        "/api/memories", params=auth(user), json={"fact": "paused synthetic fact"})
    assert paused.status_code == 409
    assert (await client.get("/api/memories", params=auth(user))).json() == []

    missing_tarot = await client.get("/api/tarot/history/999999", params=auth(user))
    missing_diary = await client.get("/api/diary/999999", params=auth(user))
    assert missing_tarot.status_code == 404
    assert missing_diary.status_code == 404


async def test_rate_limit_returns_retryable_429_without_mutation(resilience_client, user):
    client = resilience_client
    responses = [await client.post("/api/profile", params=auth(user), json={})
                 for _ in range(32)]
    assert responses[-1].status_code == 429
    assert any(response.status_code == 200 for response in responses)


async def test_unhandled_api_error_is_safe_and_correlated(resilience_client, monkeypatch):
    client = resilience_client
    async def fail(_db):
        raise RuntimeError("synthetic internal secret")

    monkeypatch.setattr(profile_router, "healthcheck", fail)
    response = await client.get("/api/health")
    assert response.status_code == 500
    assert response.headers["X-Request-ID"]
    assert response.headers["X-Response-Time"].endswith("ms")
    assert "synthetic internal secret" not in response.text
    assert "Traceback" not in response.text
