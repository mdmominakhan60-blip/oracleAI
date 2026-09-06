"""Аудитория MVP+ CRM волна 1 (BUS-230): сегменты, Δ7д, churn-карточки, goal.

Каноника: crm-frame BUS-169 §1, R1/R2 BUS-168. Ключевое равенство (§3.3):
счётчик сегмента == счётчик broadcast preview того же сегмента — оба идут
через users.segment_count, поэтому в API-тесте дельта против preview ноль.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.repo import analytics as analytics_repo
from app.repo import users as users_repo
from app.services import analytics, broadcast


async def _track(db, name: str, tg_id: int | None = None, day: str | None = None):
    """Прямая вставка события с контролируемым днём (для daily_user)."""
    created = (datetime.now(timezone.utc) - timedelta(days=0)).isoformat()
    await db.execute(
        "INSERT INTO events(tg_id, name, day, created_at) VALUES(:tg, :name, :day, :created)",
        {"tg": tg_id, "name": name, "day": day, "created": created})


async def _ensure(db, tg_id: int, **fields):
    await users_repo.ensure(db, tg_id, "Т")
    if fields:
        await users_repo.update(db, tg_id, **fields)


# ─────────────────────────── предикаты SEGMENTS ───────────────────────────────

async def test_onboarded_unactivated_vs_first_value(db):
    """onboarded без first_ritual/first_question → unactivated; с ними → first_value."""
    await _ensure(db, 2001, onboarded=1)                 # без ценности
    await _ensure(db, 2002, onboarded=1)                 # с ритуалом
    await _track(db, "first_ritual", 2002)
    await _ensure(db, 2003, onboarded=0)                 # не онбординг — не в обоих
    await _track(db, "first_question", 2003)

    assert await users_repo.segment_count(db, "onboarded_unactivated") == 1
    assert await users_repo.segment_ids(db, "onboarded_unactivated") == [2001]
    assert await users_repo.segment_count(db, "first_value") == 2


async def test_first_value_requires_either_milestone(db):
    await _ensure(db, 2010)
    await _track(db, "first_question", 2010)
    assert await users_repo.segment_ids(db, "first_value") == [2010]


async def test_cancelled_recent_window_bounds(db):
    """Истекла ≤30 дней назад → cancelled_recent; свежая/старая/никогда — нет."""
    now = datetime.now(timezone.utc)
    await _ensure(db, 2021, sub_until=(now - timedelta(days=10)).isoformat())
    await _ensure(db, 2022, sub_until=(now - timedelta(days=60)).isoformat())
    await _ensure(db, 2023, sub_until=(now + timedelta(days=10)).isoformat())
    await _ensure(db, 2024)                              # sub_until NULL

    assert await users_repo.segment_ids(db, "cancelled_recent") == [2021]


async def test_paying_pack_excludes_active_subscribers(db):
    """Пакетные покупательницы без живой подписки; платящая подписчица — нет.

    AUTO_TRIAL=1 в conftest даёт каждому ensure() живой триал — у «паковой»
    подписку гасим явно.
    """
    now = datetime.now(timezone.utc)
    await _ensure(db, 2031, ltv_stars=500,
                  sub_until=(now - timedelta(days=1)).isoformat())
    await _ensure(db, 2032, ltv_stars=500,
                  sub_until=(now + timedelta(days=20)).isoformat())  # подписчица — нет
    await _ensure(db, 2033, sub_until=None, ltv_stars=0)  # бесплатная — нет

    assert await users_repo.segment_ids(db, "paying_pack") == [2031]


async def test_daily_user_requires_five_active_days(db):
    """≥5 активных дней за 7 → daily_user; 4 дня — только weekly_user."""
    await _ensure(db, 2041, onboarded=1)
    await _ensure(db, 2042, onboarded=1)
    today = datetime.now(timezone.utc).date()
    for offset in range(5):                              # 2041: 5 дней
        await _track(db, "forecast_view", 2041,
                     day=(today - timedelta(days=offset)).isoformat())
    for offset in range(4):                              # 2042: 4 дня
        await _track(db, "forecast_view", 2042,
                     day=(today - timedelta(days=offset)).isoformat())

    assert await users_repo.segment_ids(db, "daily_user") == [2041]
    assert await users_repo.segment_ids(db, "weekly_user") == [2041, 2042]


async def test_weekly_user_single_recent_event(db):
    await _ensure(db, 2045)
    await _track(db, "miniapp_open", 2045,
                 day=datetime.now(timezone.utc).date().isoformat())
    assert await users_repo.segment_ids(db, "weekly_user") == [2045]


async def test_ritual_streak_3plus_active_practice(db):
    """streak ≥3 у незавершённой практики; завершённая не считается."""
    now = datetime.now(timezone.utc).isoformat()
    for tg_id, streak, finished in ((2051, 3, None), (2052, 2, None),
                                    (2053, 5, now)):
        await _ensure(db, tg_id)  # без users-строк EXISTS не с чем коррелировать
        await db.execute(
            "INSERT INTO practices(tg_id, code, day_index, streak, last_done, "
            "started_at, finished_at) VALUES(:tg, 'morning_pages', 3, :streak, "
            "'2026-09-05', :started, :finished)",
            {"tg": tg_id, "streak": streak, "started": now, "finished": finished})

    assert await users_repo.segment_ids(db, "ritual_streak_3plus") == [2051]


async def test_limit_hitters(db):
    await _ensure(db, 2061)
    await _track(db, "limit_reached", 2061)
    assert await users_repo.segment_ids(db, "limit_hitters") == [2061]


async def test_sleeping_14d_push_composite(db):
    """Композит §1.5(2): спящая + push_on; спящая без push не входит."""
    now = datetime.now(timezone.utc)
    await _ensure(db, 2071, last_seen=(now - timedelta(days=20)).isoformat(),
                  morning_push=1)
    await _ensure(db, 2072, last_seen=(now - timedelta(days=20)).isoformat(),
                  morning_push=0)
    await _ensure(db, 2073, last_seen=now.isoformat(), morning_push=1)

    assert await users_repo.segment_ids(db, "sleeping_14d_push") == [2071]


async def test_deleted_users_excluded_from_segments(db):
    """Анонимизированные не попадают ни в один сегмент-счётчик."""
    await _ensure(db, 2081, onboarded=1)
    await _track(db, "first_ritual", 2081)
    await users_repo.anonymize(db, 2081)
    assert await users_repo.segment_ids(db, "first_value") == []
    assert await users_repo.segment_count(db, "onboarded_unactivated") == 0


async def test_unknown_segment_falls_back_to_all(db):
    """_segment_sql fallback на 'all' — поведение broadcast и поиска."""
    where, params = users_repo._segment_sql("выдумка")
    assert where == "1=1"
    assert params == {}


# ─────────────────────── Δ7д, churn-карточки, goal ────────────────────────────

async def test_audience_segments_delta_on_empty_base_is_zero(db):
    """Критерий приёмки: на пустой базе дельта == 0, не None, для сегментов
    с временной границей; событийным — null (R9)."""
    result = await analytics.audience_segments(db)
    by_name = {s["segment"]: s for s in result["segments"]}
    assert len(by_name) >= 19
    assert by_name["sleeping_14d"]["count"] == 0
    assert by_name["sleeping_14d"]["delta_7d"] == 0
    assert by_name["first_value"]["delta_7d"] is None


async def test_audience_segments_matches_broadcast_preview(db):
    """§3.3: счётчики дашборда == broadcast preview (дельта 0)."""
    await _ensure(db, 2101, onboarded=1)
    await _ensure(db, 2102)
    table = await analytics.audience_segments(db)
    counts = {s["segment"]: s["count"] for s in table["segments"]}
    preview = await broadcast.preview(db, "onboarded")
    assert counts["onboarded"] == preview["count"] == 1


async def test_audience_churn_cards_split_by_paying(db):
    now = datetime.now(timezone.utc)
    # last_seen ставим свежий, иначе auto-trial клиентки без last_seen
    # попадают в sleeping_14d (last_seen IS NULL).
    await _ensure(db, 2111, last_seen=now.isoformat(),
                  sub_until=(now + timedelta(days=2)).isoformat(),
                  ltv_stars=300)
    await _ensure(db, 2112, last_seen=now.isoformat(),
                  sub_until=(now + timedelta(days=1)).isoformat(),
                  ltv_stars=0)
    await _ensure(db, 2113, last_seen=(now - timedelta(days=30)).isoformat(),
                  ltv_stars=900)

    cards = {c["segment"]: c for c in
             (await analytics.audience_churn(db))["cards"]}
    assert cards["expiring_3d"]["total"] == 2
    assert cards["expiring_3d"]["payers"] == 1
    assert cards["expiring_3d"]["free"] == 1
    assert cards["sleeping_14d"]["total"] == 1
    assert cards["sleeping_14d"]["payers"] == 1


async def test_goal_split_groups_and_unsets(db):
    await _ensure(db, 2121, goal="love", ltv_stars=100)
    await _ensure(db, 2122, goal="love")
    await _ensure(db, 2123, goal="career")
    await _ensure(db, 2124)                              # goal NULL → unset

    split = await analytics_repo.goal_split(db)
    goals = {g["goal"]: g for g in split["goals"]}
    assert goals["love"]["users"] == 2
    assert goals["love"]["payers"] == 1
    assert goals["career"]["users"] == 1
    assert goals["unset"]["users"] == 1
    assert split["total"] == 4
    assert goals["love"]["share_pct"] == 50.0


async def test_goal_split_excludes_deleted(db):
    await _ensure(db, 2131, goal="practice")
    await users_repo.anonymize(db, 2131)
    split = await analytics_repo.goal_split(db)
    assert split["total"] == 0
    assert split["goals"] == []


# ─────────────────────────── перцентили латентности ───────────────────────────

async def test_latency_percentiles_no_data(db):
    """R9: пустой llm_usage → null + no_data, никогда не ноль."""
    result = await analytics_repo.latency_percentiles(db, days=30)
    assert result == {"p50_ms": None, "p95_ms": None,
                      "status": "no_data", "note": "llm_usage пуст в окне"}


async def test_latency_percentiles_from_llm_usage(db):
    now = datetime.now(timezone.utc).isoformat()
    await db.executemany(
        "INSERT INTO llm_usage(tg_id, purpose, latency_ms, ok, day, created_at) "
        "VALUES(?, 'answer', ?, 1, '2026-09-06', ?)",
        [(1001, latency, now) for latency in (100, 200, 300, 400, 1000)])
    await db.commit()

    result = await analytics_repo.latency_percentiles(db, days=30)
    assert result["status"] == "full"
    # percentile_cont на 5 точках: p50 = 300,
    # p95 = интерполяция 800 + 0.75*200 = 950... точнее: idx=0.95*4=3.8 → 400+0.8*600=880
    assert result["p50_ms"] == 300
    assert result["p95_ms"] == 880


async def test_llm_costs_includes_latency_block(db):
    now = datetime.now(timezone.utc).isoformat()
    await db.executemany(
        "INSERT INTO llm_usage(tg_id, purpose, latency_ms, ok, day, created_at) "
        "VALUES(?, 'answer', ?, 1, '2026-09-06', ?)",
        [(1001, 150, now), (1001, 250, now)])
    await db.commit()

    costs = await analytics_repo.llm_costs(db, days=30)
    assert costs["latency"]["status"] == "full"
    assert costs["latency"]["p50_ms"] == 200


# ─────────────────────────────── API-слой ─────────────────────────────────────

@pytest.fixture
async def admin_client(db, user):
    from httpx import ASGITransport, AsyncClient

    from app.api.deps import get_db
    from app.api.main import app
    from tests.conftest import TEST_DEV_KEY

    app.dependency_overrides[get_db] = lambda: db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test",
                           headers={"X-Dev-Key": TEST_DEV_KEY}) as http:
        yield http
    app.dependency_overrides.clear()


async def test_audience_segments_endpoint(admin_client, db):
    await _ensure(db, 2201, onboarded=1)
    res = await admin_client.get("/api/admin/audience/segments",
                                 params={"dev_user": 1})
    assert res.status_code == 200
    body = res.json()
    names = {s["segment"] for s in body["segments"]}
    assert {"onboarded_unactivated", "first_value", "cancelled_recent",
            "paying_pack", "daily_user", "weekly_user",
            "ritual_streak_3plus", "limit_hitters",
            "sleeping_14d_push"} <= names


async def test_audience_segment_users_endpoint_requires_users_read(admin_client):
    res = await admin_client.get("/api/admin/audience/segments/onboarded/users",
                                 params={"dev_user": 1})
    # dev_user=1 — owner из ADMIN_ID, доступ есть; важен сам шейп ответа.
    assert res.status_code == 200
    body = res.json()
    assert body["segment"] == "onboarded"
    assert "items" in body and "total" in body


async def test_audience_segment_users_unknown_segment(admin_client):
    res = await admin_client.get("/api/admin/audience/segments/выдумка/users",
                                 params={"dev_user": 1})
    assert res.status_code == 404


async def test_audience_churn_endpoint_shape(admin_client):
    res = await admin_client.get("/api/admin/audience/churn",
                                 params={"dev_user": 1})
    assert res.status_code == 200
    cards = {c["segment"] for c in res.json()["cards"]}
    assert cards == {"expiring_3d", "sleeping_14d"}


async def test_audience_goals_endpoint(admin_client, db):
    await _ensure(db, 2211, goal="love")
    res = await admin_client.get("/api/admin/audience/goals",
                                 params={"dev_user": 1})
    assert res.status_code == 200
    body = res.json()
    goals = {g["goal"]: g for g in body["goals"]}
    # fixture-клиентка 1001 без goal попадает в unset — она тоже часть базы.
    assert goals["love"]["users"] == 1
    assert goals["unset"]["users"] == 1
    assert body["total"] == 2
