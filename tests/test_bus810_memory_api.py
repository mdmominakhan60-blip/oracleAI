"""BUS-810 (G-12): публичный read-only API shared context.

Owner-scope: пользователь A не видит данные B; параметр tg_id в контракте
не существует — фильтр ставится из auth-зависимости. Отсутствие данных —
200 с пустым списком, не ошибка.
"""
from __future__ import annotations

import pytest

from conftest import TEST_DEV_KEY  # noqa: E402

pytest.importorskip("httpx", reason="httpx нужен для тестов API")

from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.api.deps import get_db  # noqa: E402
from app.api.main import app  # noqa: E402
from app.core import shared_context  # noqa: E402
from app.repo import users  # noqa: E402


@pytest.fixture
async def client(db, user):
    app.dependency_overrides[get_db] = lambda: db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test",
                           headers={"X-Dev-Key": TEST_DEV_KEY}) as http:
        yield http
    app.dependency_overrides.clear()


def as_user(user, params: dict | None = None) -> dict:
    return {"dev_user": user["tg_id"], **(params or {})}


async def _other_user_with_event(db):
    """Второй пользователь B с собственной рекомендацией в shared context."""
    from app.repo import users
    await users.ensure(db, 2002, "Вторая", "second")
    await users.update(db, 2002, onboarded=1, memory_enabled=1)
    other = await users.get(db, 2002)
    await shared_context.record_recommendation(
        db, other, agent="tarot", text="ЧУЖАЯ рекомендация для B",
        source_ref="reading:999",
    )
    return other


@pytest.mark.asyncio
async def test_memory_context_owner_scoped_empty_without_data(client, user):
    """Fail-closed: у пользователя без событий — 200 и пустой список, не ошибка."""
    response = await client.get("/api/memory/context", params=as_user(user))
    assert response.status_code == 200
    payload = response.json()
    assert payload["events"] == []
    assert payload["owner_scoped"] is True


@pytest.mark.asyncio
async def test_memory_context_returns_only_own_events(client, db, user):
    """Пользователь A не видит события B: чужие данные недостижимы."""
    await users.update(db, user["tg_id"], memory_enabled=1)
    current = await users.get(db, user["tg_id"])
    await shared_context.record_recommendation(
        db, current, agent="astro", text="СВОЯ рекомендация для A",
        source_ref="thread:1",
    )
    await _other_user_with_event(db)

    response = await client.get("/api/memory/context", params=as_user(user))
    assert response.status_code == 200
    events = response.json()["events"]
    assert len(events) == 1
    assert events[0]["content"] == "СВОЯ рекомендация для A"
    assert events[0]["agent"] == "astro"
    assert events[0]["source_ref"] == "thread:1"
    assert all("ЧУЖАЯ" not in e["content"] for e in events)


@pytest.mark.asyncio
async def test_memory_context_has_no_tg_id_parameter(client, db, user):
    """По контракту нет параметра tg_id: попытка подставить чужой tg_id
    не меняет owner-scope — фильтр из auth, из запроса не приходит."""
    await _other_user_with_event(db)

    for params in ({"tg_id": 2002}, {"user_id": 2002}, {"owner": 2002}):
        response = await client.get("/api/memory/context",
                                    params=as_user(user, params))
        assert response.status_code == 200
        assert response.json()["events"] == []


@pytest.mark.asyncio
async def test_memory_context_pagination(client, db, user):
    """limit/offset листают ленту без нарушения owner-scope."""
    await users.update(db, user["tg_id"], memory_enabled=1)
    current = await users.get(db, user["tg_id"])
    for i in range(3):
        await shared_context.record_recommendation(
            db, current, agent="oracle", text=f"рекомендация {i}",
            source_ref=f"thread:{i}",
        )

    page1 = (await client.get("/api/memory/context",
                              params=as_user(user, {"limit": 2}))).json()
    assert len(page1["events"]) == 2
    page2 = (await client.get(
        "/api/memory/context",
        params=as_user(user, {"limit": 2, "offset": 2}))).json()
    assert len(page2["events"]) == 1

    all_ids = {e["id"] for e in page1["events"]} | {e["id"] for e in page2["events"]}
    assert len(all_ids) == 3
    # Новые впереди: последняя записанная рекомендация — первая в списке.
    assert page1["events"][0]["content"] == "рекомендация 2"

    bad = await client.get("/api/memory/context",
                           params=as_user(user, {"limit": 500}))
    assert bad.status_code == 422


@pytest.mark.asyncio
async def test_memory_snapshots_owner_scoped_and_latest_first(client, db, user):
    """Снапшоты: только свои, latest-first, payload — разобранный JSON."""
    import json
    now_iso = "2026-09-10T12:00:00+00:00"
    older_iso = "2026-09-09T12:00:00+00:00"
    await db.execute(
        "INSERT INTO shared_context_snapshots"
        "(tg_id, snapshot_type, snapshot_key, payload_json, created_at, expires_at) "
        "VALUES(:tg_id, :type_, :key_, :payload, :created, :expires)",
        {"tg_id": user["tg_id"], "type_": "transits", "key_": "2026-09-10",
         "payload": json.dumps({"schema_version": 1, "date": "2026-09-10",
                                "available": False}),
         "created": now_iso, "expires": "2026-09-11T12:00:00+00:00"},
    )
    await db.execute(
        "INSERT INTO shared_context_snapshots"
        "(tg_id, snapshot_type, snapshot_key, payload_json, created_at, expires_at) "
        "VALUES(:tg_id, :type_, :key_, :payload, :created, :expires)",
        {"tg_id": user["tg_id"], "type_": "transits", "key_": "2026-09-09",
         "payload": json.dumps({"schema_version": 1, "date": "2026-09-09",
                                "available": False}),
         "created": older_iso, "expires": "2026-09-10T12:00:00+00:00"},
    )
    # Чужой снапшот пользователя B.
    other = await _other_user_with_event(db)
    await db.execute(
        "INSERT INTO shared_context_snapshots"
        "(tg_id, snapshot_type, snapshot_key, payload_json, created_at, expires_at) "
        "VALUES(:tg_id, :type_, :key_, :payload, :created, :expires)",
        {"tg_id": other["tg_id"], "type_": "transits", "key_": "2026-09-10",
         "payload": json.dumps({"schema_version": 1, "secret": "CHUZHOE"}),
         "created": now_iso, "expires": "2026-09-11T12:00:00+00:00"},
    )

    response = await client.get("/api/memory/snapshots", params=as_user(user))
    assert response.status_code == 200
    payload = response.json()
    assert payload["owner_scoped"] is True
    snapshots = payload["snapshots"]
    assert len(snapshots) == 2
    assert snapshots[0]["snapshot_key"] == "2026-09-10"
    assert snapshots[1]["snapshot_key"] == "2026-09-09"
    assert snapshots[0]["payload"]["date"] == "2026-09-10"
    assert all("CHUZHOE" not in json.dumps(s) for s in snapshots)


@pytest.mark.asyncio
async def test_memory_snapshots_empty_without_data(client, user):
    """Fail-closed: нет снапшотов — 200 и пустой список."""
    response = await client.get("/api/memory/snapshots", params=as_user(user))
    assert response.status_code == 200
    assert response.json()["snapshots"] == []


@pytest.mark.asyncio
async def test_memory_endpoints_require_auth(client, db, user):
    """Без подписи Telegram или dev_user — 401, данные не отдаются."""
    for path in ("/api/memory/context", "/api/memory/snapshots"):
        response = await client.get(path)
        assert response.status_code == 401, path
