"""BUS-264: эндпоинт /api/admin/analytics/scenarios (карточки CRM-сценариев R7).

Шейп и семантика — контракт bus-264-scenario-cards-api-contract v1 (§3–6):
репо-функции тестируются напрямую (когорты входа по триггеру цепочки,
стопы из deliveries three-state, R9-gap-поведение), API-слой — через
admin_client (валидация периода/scenario, no-store, права support/analyst).
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from app.repo import analytics as analytics_repo
from app.repo import users as users_repo


async def _track(db, name: str, *, tg_id: int | None = None, day: str,
                 surface: str = "bot", props: dict | None = None,
                 created: str | None = None):
    await db.execute(
        "INSERT INTO events(tg_id, name, props_json, surface, day, created_at) "
        "VALUES(:tg_id, :name, :props, :surface, :day, :created)",
        {"tg_id": tg_id, "name": name,
         "props": json.dumps(props, ensure_ascii=False) if props else None,
         "surface": surface, "day": day,
         "created": created or f"{day}T12:00:00+00:00"})


async def _ensure(db, tg_id: int, **fields):
    await users_repo.ensure(db, tg_id, f"U{tg_id}")
    for key, value in fields.items():
        if value is None:
            continue
        await db.execute(f"UPDATE users SET {key}=:v WHERE tg_id=:t",
                         {"v": value, "t": tg_id})
    await db.commit()


async def _delivery(db, tg_id: int, kind: str, key: str, status: str = "sent",
                    days_ago: int = 3, created: str | None = None):
    created = created or _ago(days_ago)
    await db.execute(
        "INSERT INTO deliveries(tg_id, kind, key, status, created_at) "
        "VALUES(:tg_id, :kind, :key, :status, :created) "
        "ON CONFLICT (tg_id, kind, key) DO UPDATE SET status=EXCLUDED.status",
        {"tg_id": tg_id, "kind": kind, "key": key, "status": status,
         "created": created})
    await db.commit()


def _ago(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def _card(res: dict, key: str) -> dict:
    return next(c for c in res["scenarios"] if c["key"] == key)


def _day(days_ago: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).date().isoformat()


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


async def _set_role(db, tg_id: int, role: str):
    await db.execute(
        "INSERT INTO admins(tg_id, role, title, added_by, created_at) "
        "VALUES(:tg_id, :role, :role, 1, NOW()) "
        "ON CONFLICT (tg_id) DO UPDATE SET role=EXCLUDED.role",
        {"tg_id": tg_id, "role": role})
    await db.commit()


# ────────────────────────────── репо: welcome_chain ──────────────────────────

async def test_welcome_chain_cohort_conversion_and_exit(db):
    """Когорта — onboard_done в окне; конверсия — first-value после него."""
    # Обе вошли: onboard_done 5д назад.
    await _ensure(db, 5001, onboarded=1)
    await _track(db, "onboard_done", tg_id=5001, day=_day(5))
    await _ensure(db, 5002, onboarded=1)
    await _track(db, "onboard_done", tg_id=5002, day=_day(5))
    # 5001 конвертировалась: first_ritual после onboard_done (3д назад).
    await _track(db, "first_ritual", tg_id=5001, day=_day(3))
    # 5002 не конвертировала.
    # Касание дошло только 5001.
    await _delivery(db, 5001, "welcome_chain", f"d1:5001", days_ago=4)
    await db.commit()

    res = await analytics_repo.owner_scenarios(
        db, date_from=_day(7), date_to=_day(0))
    card = _card(res, "welcome_chain")
    assert card["data_status"] == "ok"
    assert card["entered"] == 2
    assert card["reached"] == 1
    assert card["converted"] == 1
    assert card["stops"]["segment_exit"] == 1  # 5001 вышла (first-value)


async def test_welcome_chain_delivery_stops_three_state(db):
    """forbidden не «дошёл» и идёт в стопы; failed — в stops.other."""
    await _ensure(db, 5011, onboarded=1)
    await _track(db, "onboard_done", tg_id=5011, day=_day(5))
    await _ensure(db, 5012, onboarded=1)
    await _track(db, "onboard_done", tg_id=5012, day=_day(5))
    await _delivery(db, 5011, "welcome_chain", "d1:5011", status="forbidden", days_ago=5)
    await _delivery(db, 5012, "welcome_chain", "d1:5012", status="failed", days_ago=5)
    await db.commit()

    res = await analytics_repo.owner_scenarios(
        db, date_from=_day(7), date_to=_day(0))
    card = _card(res, "welcome_chain")
    assert card["reached"] == 0
    assert card["stops"]["forbidden"] == 1
    assert card["stops"]["other"] == 1


# ────────────────────────────── репо: onboard_nudge ──────────────────────────

async def test_onboard_nudge_first_start_cohort(db):
    """Когорта — ПЕРВОЕ start в окне; ранние старты вне окна не входят."""
    await _ensure(db, 5101, onboarded=0)
    await _track(db, "start", tg_id=5101, day=_day(5))
    await _ensure(db, 5102, onboarded=0)
    await _track(db, "start", tg_id=5102, day=_day(5))
    # 5103 стартовала ДО окна — не входит.
    await _ensure(db, 5103, onboarded=0)
    await _track(db, "start", tg_id=5103, day=_day(40))
    # 5101 завершила онбординг: exited + converted.
    await _track(db, "onboard_done", tg_id=5101, day=_day(3))
    await _delivery(db, 5101, "onboard_nudge", "d1:5101", days_ago=4)
    await db.commit()

    res = await analytics_repo.owner_scenarios(
        db, date_from=_day(7), date_to=_day(0))
    card = _card(res, "onboard_nudge")
    assert card["entered"] == 2
    assert card["reached"] == 1
    assert card["converted"] == 1
    assert card["stops"]["segment_exit"] == 1


# ────────────────────────────── репо: reactivate (G-1) ───────────────────────

async def test_reactivate_gap_behaviour(db):
    """G-1: конверсия null (не ноль), data_status=no_data, reason G-1;
    entered/reached считаются (не зависят от гэпа)."""
    await _ensure(db, 5201, last_seen=_ago(20))
    await _delivery(db, 5201, "reactivate", "r1:2026-08", days_ago=4)
    await db.commit()

    res = await analytics_repo.owner_scenarios(
        db, date_from=_day(7), date_to=_day(0))
    card = _card(res, "reactivate")
    assert card["data_status"] == "no_data"
    assert card["no_data_reason"] == "G-1"
    assert card["entered"] == 1
    assert card["reached"] == 1
    assert card["converted"] is None
    assert card["conversion_rate"] is None


async def test_reactivate_entered_uses_r1_keys_only(db):
    """Вход — только r1-ключи (r2 и fallback не считаются повторным входом)."""
    await _ensure(db, 5211, last_seen=_ago(20))
    await _delivery(db, 5211, "reactivate", "r1:2026-08", days_ago=4)
    await _delivery(db, 5211, "reactivate", "r2:2026-08", days_ago=8)
    await _ensure(db, 5212, last_seen=_ago(20))
    await _delivery(db, 5212, "reactivate", "r1:2026-08:fallback", days_ago=4)
    await db.commit()

    res = await analytics_repo.owner_scenarios(
        db, date_from=_day(30), date_to=_day(0))
    card = _card(res, "reactivate")
    assert card["entered"] == 2  # 5211 (r1) + 5212 (fallback = r1-цикл)
    assert card["reached"] == 2


# ────────────────────────────── репо: winback2 (G-2) ─────────────────────────

async def test_winback2_gap_and_redemption_counter(db):
    """G-2: payback под гэпом (карточка no_data), redemption считается."""
    # Юзерка с истёкшей в окне подпиской, тёплый winback видел.
    await _ensure(db, 5301, sub_until=_day(5), expiry_notified=2)
    await _delivery(db, 5301, "winback2", _day(5), days_ago=3)
    # Активная подписка — выход из сегмента (не entered: sub_until > now).
    await _ensure(db, 5302, sub_until=_day(-5), expiry_notified=2)
    # Redemption winback-партии — счётчик (не деньги).
    await _ensure(db, 5303)
    await _track(db, "promo_redeemed", tg_id=5303, day=_day(2),
                 props={"batch": "winback_2026-09"})
    # Чужая партия — не считается.
    await _track(db, "promo_redeemed", tg_id=5303, day=_day(2),
                 props={"batch": "mystery_2026-09"})
    await db.commit()

    res = await analytics_repo.owner_scenarios(
        db, date_from=_day(7), date_to=_day(0))
    card = _card(res, "winback2")
    assert card["data_status"] == "no_data"
    assert card["no_data_reason"] == "G-2"
    assert card["entered"] == 1
    assert card["reached"] == 1
    assert card["converted"] == 1  # redemption из winback-партии


async def test_winback2_durable_cohort_from_deliveries(db):
    """Продлившие теряют sub_until-след в users, но остаются в журнале."""
    await _ensure(db, 5311, sub_until=_day(-3), expiry_notified=2)
    await _delivery(db, 5311, "winback2", _day(5), days_ago=6)
    await db.commit()

    res = await analytics_repo.owner_scenarios(
        db, date_from=_day(7), date_to=_day(0))
    card = _card(res, "winback2")
    assert card["entered"] == 1  # durable-хвост по deliveries (key=sub_until)


# ────────────────────── репо: post_limit / low_balance ───────────────────────

async def test_free_paid_conversion_after_trigger(db):
    """Конверсия — покупка ПОСЛЕ триггера; без покупки + >7д — segment_exit."""
    for tg_id in (5401, 5402, 5403):
        await _ensure(db, tg_id)
    await _track(db, "limit_reached", tg_id=5401, day=_day(3))
    # 5401 купила после триггера.
    await _track(db, "payment_success", tg_id=5401, day=_day(2))
    await _track(db, "limit_reached", tg_id=5402, day=_day(10))
    # 5402 не купила, триггеру >7д — вышла из сегмента.
    await _track(db, "limit_reached", tg_id=5403, day=_day(3))
    # 5403: покупка ДО триггера — не конверсия, и <7д — не выход.
    await _track(db, "payment_success", tg_id=5403, day=_day(4))
    await _delivery(db, 5401, "post_limit", _day(3), created=_ago(2))
    await db.commit()

    res = await analytics_repo.owner_scenarios(
        db, date_from=_day(30), date_to=_day(0))
    card = _card(res, "post_limit")
    assert card["entered"] == 3
    assert card["converted"] == 1
    assert card["stops"]["segment_exit"] == 1
    assert card["reached"] == 1
    assert card["data_status"] == "ok"
    # entered >= 5 не набралось → rate null (анти-reid).
    assert card["conversion_rate"] is None


async def test_low_balance_converted_after_trigger(db):
    await _ensure(db, 5411)
    await _track(db, "credit_balance_low", tg_id=5411, day=_day(3))
    await _track(db, "credit_pack_paid", tg_id=5411, day=_day(2))
    await db.commit()

    res = await analytics_repo.owner_scenarios(
        db, date_from=_day(7), date_to=_day(0))
    card = _card(res, "low_balance")
    assert card["entered"] == 1
    assert card["converted"] == 1
    assert card["data_status"] == "ok"


# ───────────────────────────── репо: общая форма ─────────────────────────────

async def test_shape_all_six_scenarios_and_scenario_filter(db):
    res = await analytics_repo.owner_scenarios(
        db, date_from=_day(7), date_to=_day(0))
    assert [c["key"] for c in res["scenarios"]] == list(analytics_repo.SCENARIO_KEYS)
    for card in res["scenarios"]:
        assert {"key", "entered", "reached", "converted", "conversion_rate",
                "stops", "data_status"} <= set(card)
    res_one = await analytics_repo.owner_scenarios(
        db, date_from=_day(7), date_to=_day(0), scenario="welcome_chain")
    assert [c["key"] for c in res_one["scenarios"]] == ["welcome_chain"]


async def test_empty_window_no_crash(db):
    res = await analytics_repo.owner_scenarios(
        db, date_from="2026-01-01", date_to="2026-01-05")
    for card in res["scenarios"]:
        if card["data_status"] == "ok":
            assert card["entered"] == 0 and card["reached"] == 0


# ─────────────────────────────────── API-слой ────────────────────────────────

async def test_api_shape_and_no_store(admin_client):
    res = await admin_client.get("/api/admin/analytics/scenarios",
                                 params={"dev_user": 1})
    assert res.status_code == 200
    assert res.headers["cache-control"] == "no-store"
    body = res.json()
    assert set(body["period"]) == {"from", "to"}
    assert len(body["scenarios"]) == 6


async def test_api_unknown_scenario_422(admin_client):
    res = await admin_client.get("/api/admin/analytics/scenarios",
                                 params={"dev_user": 1, "scenario": "unknown"})
    assert res.status_code == 422
    assert "welcome_chain" in res.json()["detail"]


async def test_api_period_validation(admin_client):
    res = await admin_client.get("/api/admin/analytics/scenarios",
                                 params={"dev_user": 1, "from": "2026-09-10",
                                         "to": "2026-09-01"})
    assert res.status_code == 422
    res = await admin_client.get("/api/admin/analytics/scenarios",
                                 params={"dev_user": 1, "from": "01012026"})
    assert res.status_code == 422


async def test_api_support_and_analyst_access(db, admin_client):
    """support и analyst ходят в карточки (права dashboard) — read-only."""
    await _set_role(db, 5551, "support")
    await _set_role(db, 5552, "analyst")
    res_s = await admin_client.get("/api/admin/analytics/scenarios",
                                   params={"dev_user": 5551})
    assert res_s.status_code == 200
    res_a = await admin_client.get("/api/admin/analytics/scenarios",
                                   params={"dev_user": 5552})
    assert res_a.status_code == 200
    # Privacy: агрегаты без tg_id-детализации в ответе.
    body = json.dumps(res_s.json(), ensure_ascii=False)
    assert "tg_id" not in body
