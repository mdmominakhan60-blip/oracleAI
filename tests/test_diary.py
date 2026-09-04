"""Дневник: записи, вечерний вопрос, месячная сводка «что показала Вселенная».

Сводка считает факты кодом (сколько записей, о чём, что менялось), а не LLM:
текст итога пишет Оракул, но цифры не выдумываются.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from conftest import TEST_DEV_KEY  # noqa: E402

pytest.importorskip("httpx", reason="httpx нужен для тестов API")

from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.api.deps import get_db  # noqa: E402
from app.api.main import app  # noqa: E402


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


async def _add(db, tg_id: int, text: str, day: int) -> None:
    """Запись с фиксированным числом текущего месяца (UTC)."""
    from app.data.session import transaction as _tx

    now = datetime.now(timezone.utc)
    created = f"{now.year:04d}-{now.month:02d}-{day:02d}T20:00:00+00:00"
    async with _tx(db):
        await db.execute(
            "INSERT INTO diary(tg_id, text, mood, created_at) VALUES(?,?,?,?)",
            (tg_id, text, "calm", created))


async def test_diary_summary_facts(client, db, user):
    now = datetime.now(timezone.utc)
    month = f"{now.year:04d}-{now.month:02d}"
    tg = user["tg_id"]

    await _add(db, tg, "Деньги поджимают, работа выматывает", 1)
    await _add(db, tg, "Ссора с мужем, расставание не идёт из головы", 2)
    await _add(db, tg, "Мантра вечером, наконец выспалась", 3)

    res = await client.get("/api/diary/summary",
                           params=as_user(user, {"month": month}))
    assert res.status_code == 200
    data = res.json()
    assert data["empty"] is False
    assert data["count"] == 3
    assert data["days_written"] == 3
    assert data["moods"] == {"calm": 3}
    themes = {t["theme"] for t in data["themes"]}
    assert {"отношения", "деньги и работа"} <= themes
    assert data["changes"] >= 1                    # «наконец» в третьей записи
    assert "Записей за месяц: 3" in data["data_for_prompt"]


async def test_diary_summary_empty_month(client, db, user):
    res = await client.get("/api/diary/summary",
                           params=as_user(user, {"month": "1999-01"}))
    assert res.status_code == 200
    data = res.json()
    assert data["empty"] is True and data["count"] == 0


async def test_diary_summary_counts_days_not_entries(client, db, user):
    """Две записи за сутки — один день дневника в сводке."""
    now = datetime.now(timezone.utc)
    month = f"{now.year:04d}-{now.month:02d}"
    tg = user["tg_id"]

    await _add(db, tg, "Первая запись дня", 5)
    await _add(db, tg, "Вторая запись того же дня", 5)

    res = await client.get("/api/diary/summary",
                           params=as_user(user, {"month": month}))
    data = res.json()
    assert data["count"] == 2
    assert data["days_written"] == 1
    assert data["streak_max"] == 1
