from datetime import datetime, timezone

import pytest

from conftest import TEST_DEV_KEY  # noqa: E402

from app.repo import notifications, readings


@pytest.fixture
async def client(db, user):
    pytest.importorskip("httpx")
    from httpx import ASGITransport, AsyncClient
    from app.api.deps import get_db
    from app.api.main import app
    app.dependency_overrides[get_db] = lambda: db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test",
                      headers={"X-Dev-Key": TEST_DEV_KEY}) as http:
        yield http
    app.dependency_overrides.clear()


def as_user(user):
    return {"dev_user": user["tg_id"]}


@pytest.mark.asyncio
async def test_notification_inbox_is_owner_scoped_and_deduplicates_forecast(client, db, user, free_user):
    day = datetime.now(timezone.utc).date().isoformat()
    await readings.save_forecast(db, user["tg_id"], day, "<b>Твой прогноз</b><br>Спокойный день.", lang="ru")
    await readings.save_forecast(db, free_user["tg_id"], day, "Чужой прогноз", lang="ru")
    await notifications.sync_daily_forecast(db, 9999, lang="ru", day=day)

    first = await client.get("/api/notifications", params=as_user(user))
    assert first.status_code == 200
    payload = first.json()
    assert payload["unread_count"] == 1
    assert len(payload["items"]) == 1
    assert payload["items"][0]["kind"] == "forecast"
    assert "<b>" not in payload["items"][0]["body"]
    assert "Твой прогноз" in payload["items"][0]["body"]
    assert "Чужой прогноз" not in str(payload)
    assert payload["privacy"]

    second = await client.get("/api/notifications", params=as_user(user))
    assert second.json()["unread_count"] == 1
    assert len(second.json()["items"]) == 1


@pytest.mark.asyncio
async def test_notification_preferences_are_owner_scoped_and_persist(client, user):
    current = await client.get("/api/notifications/preferences", params=as_user(user))
    assert current.status_code == 200
    assert current.json()["morning_forecast"] is True
    assert current.json()["delivery_channel"] == "telegram_bot"
    assert current.json()["supported"] == ["morning_forecast"]

    updated = await client.patch(
        "/api/notifications/preferences", params=as_user(user),
        json={"morning_forecast": False},
    )
    assert updated.status_code == 200
    assert updated.json()["morning_forecast"] is False

    again = await client.get("/api/notifications/preferences", params=as_user(user))
    assert again.json()["morning_forecast"] is False


@pytest.mark.asyncio
async def test_notification_mark_all_read_is_idempotent_and_owner_scoped(client, db, user, free_user):
    day = datetime.now(timezone.utc).date().isoformat()
    await readings.save_forecast(db, user["tg_id"], day, "Forecast", lang="ru")
    await readings.save_forecast(db, free_user["tg_id"], day, "Other forecast", lang="ru")

    assert (await client.get("/api/notifications", params=as_user(user))).json()["unread_count"] == 1
    marked = await client.post("/api/notifications/read-all", params=as_user(user), json={})
    assert marked.status_code == 200
    assert marked.json()["marked_count"] == 1
    assert marked.json()["unread_count"] == 0

    repeated = await client.post("/api/notifications/read-all", params=as_user(user), json={})
    assert repeated.status_code == 200
    assert repeated.json()["marked_count"] == 0
    assert repeated.json()["unread_count"] == 0

    foreign = await client.get("/api/notifications", params=as_user(free_user))
    assert foreign.json()["unread_count"] == 1
