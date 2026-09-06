"""BUS-229: эндпоинты /api/admin/analytics/{funnel,retention,revenue,segments}.

Шейпы и семантика — §4.1–4.4 спеки BUS-176, ошибки — §4.5. Репо-функции
тестируются напрямую (SQL-семантика: стык session/user, milestone-когорты,
gross-граница, анти-reid), API-слой — через admin_client (валидация периода,
unsupported-фильтры → 422, Cache-Control: no-store).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.repo import analytics as analytics_repo
from app.repo import users as users_repo


async def _track(db, name: str, *, tg_id: int | None = None, day: str,
                 session_id: str | None = None, surface: str = "bot",
                 props: dict | None = None):
    await db.execute(
        "INSERT INTO events(tg_id, name, props_json, surface, session_id, day, "
        "created_at) VALUES(:tg_id, :name, :props, :surface, :sid, :day, :created)",
        {"tg_id": tg_id, "name": name,
         "props": __import__("json").dumps(props, ensure_ascii=False) if props else None,
         "surface": surface, "sid": session_id, "day": day,
         "created": f"{day}T12:00:00+00:00"})


async def _ensure(db, tg_id: int, **fields):
    await users_repo.ensure(db, tg_id, f"U{tg_id}")
    for key, value in fields.items():
        if value is None:
            continue
        await db.execute(f"UPDATE users SET {key}=:v WHERE tg_id=:t",
                         {"v": value, "t": tg_id})
    await db.commit()


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


# ─────────────────────────────── репо: воронка ────────────────────────────────

async def test_funnel_session_user_units(db):
    """Верх — по сессиям, низ — по tg_id; of_prev/of_start считаются."""
    await _track(db, "visit", session_id="s1", day="2026-09-01", surface="web",
                 props={"source": "instagram", "medium": "social"})
    await _track(db, "visit", session_id="s2", day="2026-09-02", surface="web",
                 props={"source": "instagram", "medium": "social"})
    await _track(db, "signup", tg_id=3001, session_id="s1", day="2026-09-01",
                 surface="web")
    await _track(db, "session_linked", tg_id=3001, session_id="s1",
                 day="2026-09-01", surface="miniapp")
    await _track(db, "session_linked", tg_id=3001, session_id="s2",
                 day="2026-09-02", surface="miniapp")
    await _ensure(db, 3001, source="instagram")
    await _track(db, "paywall_view", tg_id=3001, day="2026-09-02", surface="web")
    await db.execute(
        "INSERT INTO orders(tg_id, kind, sku, amount_stars, status, payload, "
        "surface, created_at, paid_at) VALUES(3001, 'product', 'pack_small', "
        "150, 'paid', 'p1', 'miniapp', '2026-09-03T10:00:00+00:00', "
        "'2026-09-03T10:00:00+00:00')")
    await db.commit()

    res = await analytics_repo.owner_funnel(db, date_from="2026-09-01",
                                            date_to="2026-09-30")
    steps = {s["step"]: s for s in res["steps"]}
    assert steps["visit"]["value"] == 2
    assert steps["visit"]["unit"] == "session"
    assert steps["visit"]["of_prev"] is None
    assert steps["signup"]["value"] == 1
    assert steps["signup"]["of_prev"] == 50.0
    assert steps["paywall_view"]["value"] == 1
    assert steps["paywall_view"]["unit"] == "user"
    assert steps["paid"]["value"] == 1
    assert steps["paid"]["of_start"] == 50.0
    assert res["data_quality"]["status"] == "full"


async def test_funnel_source_filter_reaches_user_steps(db):
    """source фильтрует и событийные шаги, и users.source для user-шагов."""
    await _track(db, "visit", session_id="s1", day="2026-09-01", surface="web",
                 props={"source": "instagram"})
    await _track(db, "session_linked", tg_id=3002, session_id="s1",
                 day="2026-09-01", surface="miniapp")
    await _ensure(db, 3002, source="telegram")
    await _track(db, "paywall_view", tg_id=3002, day="2026-09-02", surface="web")
    await db.commit()

    res = await analytics_repo.owner_funnel(
        db, date_from="2026-09-01", date_to="2026-09-30", source="instagram")
    steps = {s["step"]: s for s in res["steps"]}
    assert steps["visit"]["value"] == 1
    assert steps["paywall_view"]["value"] == 0


async def test_funnel_empty_window_reports_no_data(db):
    res = await analytics_repo.owner_funnel(db, date_from="2026-08-01",
                                            date_to="2026-08-10")
    assert res["data_quality"]["status"] == "no_data"
    visit = res["steps"][0]
    assert visit["value"] == 0 and visit["of_start"] == 0.0


async def test_funnel_unreliable_when_only_deep_steps(db):
    """BUS-144 не деплоирован: нет visit → no_data, не unreliable.

    Семантика: без visit-когорты user_scope пуст → все deep шаги = 0.
    Это не «верх пуст при непустом низе», а «всё пусто» → no_data.
    """
    await _ensure(db, 3010)
    await _track(db, "paywall_view", tg_id=3010, day="2026-09-02", surface="web")
    await db.commit()
    res = await analytics_repo.owner_funnel(db, date_from="2026-09-01",
                                            date_to="2026-09-30")
    assert res["data_quality"]["status"] == "no_data"


# ────────────────────────────── репо: retention ───────────────────────────────

async def test_retention_milestones_and_maturity(db):
    """Когорта по первому miniapp_open; d1/d7 milestone; зрелость по календарю."""
    # Когорта 3 дня назад: d1 (3+1=4 <= сегодня) зрел, d7 (3+7=10) не зрел.
    d0 = (datetime.now(timezone.utc) - timedelta(days=3)).date().isoformat()
    await _ensure(db, 3101)
    await _track(db, "miniapp_open", tg_id=3101, day=d0, surface="miniapp")
    await _track(db, "return_d1", tg_id=3101,
                 day=(datetime.fromisoformat(d0) + timedelta(days=1)).date().isoformat())
    await db.commit()

    res = await analytics_repo.owner_retention(db, date_from=d0, date_to=d0)
    assert res["cohort_anchor"] == "miniapp_open"
    cohort = res["cohorts"][0]
    assert cohort["size"] == 1
    assert cohort["d1"]["matured"] is True and cohort["d1"]["value"] == 1
    assert cohort["d1"]["rate"] == 100.0
    # Когорта 3d назад: сегодня >= 3+7=10? Нет → не зрел.
    assert cohort["d7"]["matured"] is False and cohort["d7"]["value"] is None
    # d30 — activity_fallback до G1.
    assert cohort["d30"]["method"] == "activity_fallback"
    assert cohort["d30"]["matured"] is False


async def test_retention_d30_activity_fallback(db):
    # Когорта 35 дней назад: d30 (35+30=65) не в 120d окне, matured=true.
    d0 = (datetime.now(timezone.utc) - timedelta(days=35)).date().isoformat()
    d30 = (datetime.fromisoformat(d0) + timedelta(days=30)).date().isoformat()
    await _ensure(db, 3102)
    await _track(db, "miniapp_open", tg_id=3102, day=d0, surface="miniapp")
    await _track(db, "question", tg_id=3102, day=d30)
    await db.commit()

    res = await analytics_repo.owner_retention(db, date_from=d0, date_to=d0)
    d30 = res["cohorts"][0]["d30"]
    assert d30["matured"] is True
    assert d30["value"] == 1 and d30["rate"] == 100.0


async def test_retention_week_granularity_buckets_by_iso_week(db):
    # Два юзера в одной ISO-неделе → одна week-когорта.
    d1 = "2026-09-07"  # понедельник
    d2 = "2026-09-08"
    await _ensure(db, 3103)
    await _ensure(db, 3104)
    await _track(db, "miniapp_open", tg_id=3103, day=d1, surface="miniapp")
    await _track(db, "miniapp_open", tg_id=3104, day=d2, surface="miniapp")
    await db.commit()

    res = await analytics_repo.owner_retention(db, date_from=d1, date_to=d2,
                                               granularity="week")
    assert len(res["cohorts"]) == 1
    assert res["cohorts"][0]["day"] == "2026-09-07"
    assert res["cohorts"][0]["size"] == 2


# ─────────────────────────────── репо: revenue ────────────────────────────────

async def test_revenue_gross_in_stars_and_by_sku(db):
    await _ensure(db, 3201)
    for payload, stars, paid_at in (("r1", 100, "2026-09-01T10:00:00+00:00"),
                                    ("r2", 50, "2026-09-02T10:00:00+00:00")):
        await db.execute(
            "INSERT INTO orders(tg_id, kind, sku, amount_stars, status, payload, "
            "surface, created_at, paid_at) VALUES(3201, 'product', 'pack_small', "
            ":stars, 'paid', :payload, 'miniapp', :created, :paid)",
            {"stars": stars, "payload": payload, "created": paid_at,
             "paid": paid_at})
    await db.execute(
        "INSERT INTO payments(order_id, tg_id, amount_stars, status, created_at) "
        "VALUES(1, 3201, 100, 'succeeded', '2026-09-01T10:00:00+00:00')")
    await db.commit()

    res = await analytics_repo.owner_revenue(db, date_from="2026-09-01",
                                             date_to="2026-09-30")
    assert res["totals"]["gross_booking_stars"] == 100  # payments, не orders
    assert res["totals"]["paid_orders"] == 2
    assert res["totals"]["payers"] == 1
    assert res["totals"]["net_revenue_estimate"] is None
    assert "settlement" in res["totals"]["net_revenue_note"]
    assert len(res["timeseries"]) == 30
    ts = {t["day"]: t for t in res["timeseries"]}
    assert ts["2026-09-02"]["orders"] == 1 and ts["2026-09-02"]["gross_stars"] == 50
    sku = res["by_sku"][0]
    assert sku["sku"] == "pack_small" and sku["orders"] == 2
    assert sku["gross_stars"] == 150


async def test_revenue_sku_filter(db):
    await _ensure(db, 3202)
    await db.execute(
        "INSERT INTO orders(tg_id, kind, sku, amount_stars, status, payload, "
        "surface, created_at, paid_at) VALUES(3202, 'product', 'pack_big', "
        "500, 'paid', 'r3', 'miniapp', '2026-09-01T10:00:00+00:00', "
        "'2026-09-01T10:00:00+00:00')")
    await db.commit()
    res = await analytics_repo.owner_revenue(db, date_from="2026-09-01",
                                             date_to="2026-09-30", sku="pack_big")
    assert res["totals"]["paid_orders"] == 1
    res2 = await analytics_repo.owner_revenue(db, date_from="2026-09-01",
                                              date_to="2026-09-30", sku="other")
    assert res2["totals"]["paid_orders"] == 0


# ────────────────────────────── репо: segments ────────────────────────────────

async def test_segments_by_source_with_other_aggregation(db):
    """Анти-reid: сегменты <5 users сливаются в other (§4.4)."""
    for i in range(5):
        await _ensure(db, 3300 + i, source="tg")
    for i in range(5):
        await _ensure(db, 3310 + i, source="instagram",
                      ltv_stars=100 if i == 0 else 0)
    await _ensure(db, 3320, source="reddit")
    await _ensure(db, 3321, source="vk")
    await db.commit()

    res = await analytics_repo.owner_segments(db, by="source")
    by_key = {s["key"]: s for s in res["segments"]}
    assert res["total"] == 12
    assert by_key["tg"]["users"] == 5
    assert by_key["tg"]["share_pct"] == 41.7  # 5/12
    assert "reddit" not in by_key and "vk" not in by_key
    assert by_key["other"]["users"] == 2
    src = by_key["instagram"]
    assert src["users"] == 5
    assert src["payers"] == 1 and src["payer_rate_pct"] == 20.0
    assert src["ltv_stars"] == 100


async def test_segments_by_tier_uses_subscription_state(db):
    # 5 free (без subscription_state) и 5 vip — оба сегмента видны (>=5).
    for i in range(5):
        await _ensure(db, 3400 + i)
    for i in range(5):
        await db.execute(
            "INSERT INTO subscription_state(tg_id, tier_code, status, "
            "updated_at) VALUES(:t, 'vip', 'active', "
            "'2026-09-05T00:00:00+00:00') ON CONFLICT (tg_id) DO UPDATE SET "
            "tier_code=excluded.tier_code, status=excluded.status, "
            "updated_at=excluded.updated_at",
            {"t": 3450 + i})
        await _ensure(db, 3450 + i)
    await db.commit()

    res = await analytics_repo.owner_segments(db, by="tier")
    by_key = {s["key"]: s for s in res["segments"]}
    assert by_key["free"]["users"] == 5
    assert by_key["vip"]["users"] == 5


async def test_segments_by_lifecycle_intersects_and_merges(db):
    # fixture user (id=1001) может быть onboarded — считаем от чистых данных.
    await _ensure(db, 3501, onboarded=1,
                  created_at=datetime.now(timezone.utc).isoformat())
    for i in range(5):
        await _ensure(db, 3510 + i, onboarded=1)
    await db.commit()

    res = await analytics_repo.owner_segments(db, by="lifecycle")
    by_key = {s["key"]: s for s in res["segments"]}
    # new = созданы за последние 7 дней (все 6), onboarded = все 6, paying = 0.
    assert by_key["new"]["users"] == 6
    assert by_key["onboarded"]["users"] == 6


# ────────────────────────────────── API-слой ──────────────────────────────────

async def test_api_funnel_shape_and_no_store(admin_client):
    res = await admin_client.get("/api/admin/analytics/funnel",
                                 params={"dev_user": 1})
    assert res.status_code == 200
    assert res.headers["cache-control"] == "no-store"
    body = res.json()
    assert body["period"]["from"] and body["period"]["to"]
    assert {"steps", "filters", "data_quality"} <= set(body)
    step = body["steps"][0]
    assert {"step", "event", "value", "unit", "of_prev", "of_start"} <= set(step)


async def test_api_retention_granularity_validation(admin_client):
    res = await admin_client.get("/api/admin/analytics/retention",
                                 params={"dev_user": 1, "granularity": "month"})
    assert res.status_code == 422


async def test_api_revenue_net_is_null(admin_client):
    res = await admin_client.get("/api/admin/analytics/revenue",
                                 params={"dev_user": 1})
    assert res.status_code == 200
    body = res.json()
    assert body["totals"]["net_revenue_estimate"] is None
    assert body["data_quality"]["status"] == "full"


async def test_api_segments_unknown_by_422(admin_client):
    res = await admin_client.get("/api/admin/analytics/segments",
                                 params={"dev_user": 1, "by": "language"})
    assert res.status_code == 422


async def test_api_period_validation(admin_client):
    res = await admin_client.get("/api/admin/analytics/funnel",
                                 params={"dev_user": 1, "from": "2026-09-10",
                                         "to": "2026-09-01"})
    assert res.status_code == 422
    res = await admin_client.get("/api/admin/analytics/funnel",
                                 params={"dev_user": 1, "from": "2025-01-01",
                                         "to": "2026-02-04"})
    assert res.status_code == 422
    res = await admin_client.get("/api/admin/analytics/funnel",
                                 params={"dev_user": 1, "from": "01012026"})
    assert res.status_code == 422


async def test_api_funnel_unsupported_source_422(admin_client):
    res = await admin_client.get("/api/admin/analytics/funnel",
                                 params={"dev_user": 1, "source": "tiktok"})
    assert res.status_code == 422
