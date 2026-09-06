"""BUS-309: LTV-тиры, очередь внимания Q1–Q7, user_card.ltv.

Покрываем:
- ltv_tier: A/B/C/D/вне тира, деградация без платящих, топ-20% (PG), SQLite-деградация.
- attention_queue: 7 правил, forbidden-исключение, сортировка, счётчики по всей очереди.
- user_card.ltv: объект, risk_flags, timeline, channel_closed, next_best_action.
- Синтетика 10001/10002 исключается.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

pytest.importorskip("httpx", reason="httpx нужен для тестов API")
from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.api.deps import get_db  # noqa: E402
from app.api.main import app  # noqa: E402
from app.repo import analytics as analytics_repo, users  # noqa: E402
from app.repo.ltv_tier import (  # noqa: E402
    attention_queue, channel_closed, ltv_tier, user_card_ltv,
)
from tests.conftest import TEST_DEV_KEY  # noqa: E402


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(days_ago: int = 0, hours_ago: int = 0) -> str:
    return (_now() - timedelta(days=days_ago, hours=hours_ago)).isoformat()


async def _track_at(db, tg_id: int, name: str, created_at: str) -> None:
    """Событие с бэкдейтом: track() пишет only-now, правилам нужны окна в прошлом."""
    await db.execute(
        "INSERT INTO events(tg_id, name, day, created_at) VALUES "
        "(:t, :n, :d, :c)",
        {"t": tg_id, "n": name,
         "d": created_at[:10], "c": created_at})


async def _deliver_at(db, tg_id: int, kind: str, key: str, created_at: str,
                      status: str = "sent", error: str | None = None) -> None:
    """Доставка с бэкдейтом: mark_sent() пишет only-now."""
    await db.execute(
        "INSERT INTO deliveries(tg_id, kind, key, status, error, created_at) "
        "VALUES(:t, :k, :key, :s, :e, :c) "
        "ON CONFLICT (tg_id, kind, key) DO UPDATE SET status=:s, error=:e, "
        "created_at=:c",
        {"t": tg_id, "k": kind, "key": key, "s": status, "e": error,
         "c": created_at})


async def _ensure(db, tg_id: int, **fields):
    await users.ensure(db, tg_id, f"T-{tg_id}")
    fields.setdefault("last_seen", _now().isoformat())
    writable = {
        "name", "username", "lang", "gender", "persona", "oracle_name", "tz",
        "birth_date", "birth_time", "birth_time_known", "birth_time_precision",
        "birth_city", "birth_lat", "birth_lon", "chart_json",
        "natal_technique", "natal_technique_version", "onboarding_step",
        "sub_level", "sub_until", "crystals",
        "onboarded", "morning_push", "memory_enabled", "ref_by", "goal",
        "source", "status", "ltv_stars", "expiry_notified", "last_seen",
        "deleted_at",
    }
    writable_fields = {k: v for k, v in fields.items() if k in writable}
    raw_fields = {k: v for k, v in fields.items() if k not in writable}
    if writable_fields:
        await users.update(db, tg_id, **writable_fields)
    if raw_fields:
        keys = ", ".join(f"{k}=:{k}" for k in raw_fields)
        await db.execute(
            f"UPDATE users SET {keys} WHERE tg_id=:tg_id",
            {**raw_fields, "tg_id": tg_id})


# ──────────────────────────────────────────────────────────────────────────────
# ltv_tier
# ──────────────────────────────────────────────────────────────────────────────

async def test_ltv_tier_A_top20_or_2_payments(db):
    """A: топ-20% ИЛИ ≥2 платежа."""
    await _ensure(db, 3011, ltv_stars=500, sub_until=None)
    await _ensure(db, 3012, ltv_stars=50, sub_until=None)
    # 2 платёжа
    await db.execute(
        "INSERT INTO orders(tg_id, kind, sku, title, amount_stars, amount_crystals, "
        "status, paid_at, created_at) VALUES "
        "(:t, 'plan', 'vip', 'v1', 100, 0, 'paid', :d1, :d1), "
        "(:t, 'plan', 'vip', 'v2', 200, 0, 'paid', :d2, :d2)",
        {"t": 3012, "d1": _iso(-30), "d2": _iso(-10)})
    await _ensure(db, 3013, ltv_stars=0)
    # 1 платёж
    await db.execute(
        "INSERT INTO orders(tg_id, kind, sku, title, amount_stars, amount_crystals, "
        "status, paid_at, created_at) VALUES "
        "(:t, 'plan', 'free', 'v1', 50, 0, 'paid', :d1, :d1)",
        {"t": 3013, "d1": _iso(-5)})

    assert (await ltv_tier(db, 3011))["tier"] == "A"  # ltv_stars высокий
    assert (await ltv_tier(db, 3012))["tier"] == "A"  # 2 платежа
    assert (await ltv_tier(db, 3013))["tier"] == "B"  # 1 платёж


async def test_ltv_tier_B_one_payment(db):
    await _ensure(db, 3021, ltv_stars=0)
    await db.execute(
        "INSERT INTO orders(tg_id, kind, sku, title, amount_stars, amount_crystals, "
        "status, paid_at, created_at) VALUES "
        "(:t, 'plan', 'free', 'v1', 50, 0, 'paid', :d1, :d1)",
        {"t": 3021, "d1": _iso(-3)})
    assert (await ltv_tier(db, 3021))["tier"] == "B"


async def test_ltv_tier_C_never_paid_active_free(db):
    """C: never_paid + ≥3 miniapp_open за 14д."""
    await _ensure(db, 3031, ltv_stars=0, created_at=_iso(-10))
    for i in range(5):
        await _track_at(db, 3031, "miniapp_open", _iso(days_ago=i))
    assert (await ltv_tier(db, 3031))["tier"] == "C"


async def test_ltv_tier_C_streak(db):
    """C: стрик ≥3."""
    await _ensure(db, 3032, ltv_stars=0)
    # diary_streak ≥3 через фикстуру practices
    await db.execute(
        "INSERT INTO practices(tg_id, code, day_index, streak, started_at) "
        "VALUES(:t, 'p1', 5, 3, :s)",
        {"t": 3032, "s": _iso(-1)})
    assert (await ltv_tier(db, 3032))["tier"] == "C"


async def test_ltv_tier_D_new_user(db):
    await _ensure(db, 3041, ltv_stars=0, created_at=_iso(days_ago=3))
    assert (await ltv_tier(db, 3041))["tier"] == "D"


async def test_ltv_tier_outside_old_user_no_activity(db):
    """Вне тира: старая, never_paid, без miniapp_open, без стрика."""
    await _ensure(db, 3051, ltv_stars=0, created_at=_iso(days_ago=30))
    assert (await ltv_tier(db, 3051))["tier"] is None


async def test_ltv_tier_no_payers_degradation(db):
    """Нулевая база платящих: A/B недостижимы, C/D работают (Q6 живой).

    BUS-183 baseline: 0 платящих → никто не получает A/B; при этом тир D
    зависит только от created_at и обязан присваиваться существующим данным.
    """
    await _ensure(db, 3061, ltv_stars=0, created_at=_iso(days_ago=2))
    await _ensure(db, 3062, ltv_stars=0, created_at=_iso(days_ago=1))
    await _ensure(db, 3063, ltv_stars=0, created_at=_iso(days_ago=30))
    await _ensure(db, 3064, ltv_stars=0, created_at=_iso(days_ago=30))
    for i in range(3):
        await _track_at(db, 3064, "miniapp_open", _iso(days_ago=i))
    assert (await ltv_tier(db, 3061))["tier"] == "D"
    assert (await ltv_tier(db, 3062))["tier"] == "D"
    assert (await ltv_tier(db, 3063))["tier"] is None
    assert (await ltv_tier(db, 3064))["tier"] == "C"


async def test_ltv_tier_synthetic_excluded(db):
    assert await ltv_tier(db, 10001) is None
    assert await ltv_tier(db, 10002) is None


# ──────────────────────────────────────────────────────────────────────────────
# channel_closed
# ──────────────────────────────────────────────────────────────────────────────

async def test_channel_closed_forbidden(db):
    await _ensure(db, 3101)
    await _deliver_at(db, 3101, "forecast", "2026-09-01", _iso(hours_ago=1),
                      status="forbidden", error="TelegramForbiddenError")
    assert await channel_closed(db, 3101) is True


async def test_channel_closed_open_after_forbidden(db):
    await _ensure(db, 3102)
    await _deliver_at(db, 3102, "forecast", "d1", _iso(days_ago=2),
                      status="forbidden", error="TelegramForbiddenError")
    await _deliver_at(db, 3102, "forecast", "d2", _iso(hours_ago=1),
                      status="sent")
    assert await channel_closed(db, 3102) is False


async def test_channel_closed_synthetic(db):
    assert await channel_closed(db, 10001) is False


# ──────────────────────────────────────────────────────────────────────────────
# attention_queue — 7 правил
# ──────────────────────────────────────────────────────────────────────────────

async def test_attention_queue_q1_refund_48h(db):
    await _ensure(db, 3201, ltv_stars=100)
    await db.execute(
        "INSERT INTO events(tg_id, name, day, created_at) VALUES "
        "(:t, 'refund_requested', :d, :c)",
        {"t": 3201, "d": _now().strftime("%Y-%m-%d"), "c": _iso(hours_ago=2)})
    queue = await attention_queue(db, limit=50)
    rules = {c["tg_id"]: c["rule"] for c in queue["items"]}
    assert rules.get(3201) == "q1"
    assert queue["counts"]["p1"] >= 1


async def test_attention_queue_q2_vip_sleeping(db):
    await _ensure(db, 3211, ltv_stars=500, last_seen=_iso(days_ago=20))
    queue = await attention_queue(db, limit=50)
    assert any(c["tg_id"] == 3211 and c["rule"] == "q2" for c in queue["items"])


async def test_attention_queue_q2_vip_sub_expired_5d(db):
    await _ensure(db, 3212, ltv_stars=200, sub_until=_iso(days_ago=6))
    queue = await attention_queue(db, limit=50)
    assert any(c["tg_id"] == 3212 and c["rule"] == "q2" for c in queue["items"])


async def test_attention_queue_q3_wb2_no_redemption(db):
    await _ensure(db, 3221, ltv_stars=100, sub_until=_iso(days_ago=10))
    # WB2 отправлена 10 дней назад
    await _deliver_at(db, 3221, "winback2", "wb-3221", _iso(days_ago=10))
    queue = await attention_queue(db, limit=50)
    assert any(c["tg_id"] == 3221 and c["rule"] == "q3" for c in queue["items"])


async def test_attention_queue_q4_limit_hits(db):
    await _ensure(db, 3231, ltv_stars=50)
    for i in range(4):
        await analytics_repo.track(db, "limit_reached", 3231)
    queue = await attention_queue(db, limit=50)
    assert any(c["tg_id"] == 3231 and c["rule"] == "q4" for c in queue["items"])


async def test_attention_queue_q5_delivery_failed_24h(db):
    await _ensure(db, 3241)
    await _deliver_at(db, 3241, "forecast", "k1", _iso(hours_ago=2),
                      status="forbidden", error="TelegramForbiddenError")
    queue = await attention_queue(db, limit=50)
    assert any(c["tg_id"] == 3241 and c["rule"] == "q5" for c in queue["items"])


async def test_attention_queue_q6_new_not_onboarded_O1_sent(db):
    await _ensure(db, 3251, ltv_stars=0, onboarded=0, created_at=_iso(days_ago=4))
    await _deliver_at(db, 3251, "onboard_nudge", "d1:3251", _iso(days_ago=3))
    queue = await attention_queue(db, limit=50)
    assert any(c["tg_id"] == 3251 and c["rule"] == "q6" for c in queue["items"])


async def test_attention_queue_q7_return_gap(db):
    await _ensure(db, 3261)
    # Первый miniapp_open 40 дней назад
    await _track_at(db, 3261, "miniapp_open", _iso(days_ago=40))
    # Возврат 2 часа назад
    await _track_at(db, 3261, "miniapp_open", _iso(hours_ago=2))
    queue = await attention_queue(db, limit=50)
    assert any(c["tg_id"] == 3261 and c["rule"] == "q7" for c in queue["items"])


async def test_attention_queue_forbidden_excludes_q2_q3_q4_q6_q7(db):
    """Закрытый канал: исключается из Q2/Q3/Q4/Q6/Q7; Q1 и Q5 — нет."""
    await _ensure(db, 3271, ltv_stars=200, last_seen=_iso(days_ago=20),
                  sub_until=_iso(days_ago=6))
    await _deliver_at(db, 3271, "forecast", "k", _iso(hours_ago=1),
                      status="forbidden", error="TelegramForbiddenError")
    queue = await attention_queue(db, limit=50)
    rules = {c["tg_id"]: c["rule"] for c in queue["items"]}
    assert rules.get(3271) != "q2"
    assert rules.get(3271) != "q3"
    assert rules.get(3271) != "q4"
    assert rules.get(3271) != "q6"
    assert rules.get(3271) != "q7"


async def test_attention_queue_forbidden_q5_serves_channel(db):
    """Q5 — обслуживание канала, forbidden НЕ исключается."""
    await _ensure(db, 3272)
    await _deliver_at(db, 3272, "forecast", "k", _iso(hours_ago=1),
                      status="forbidden", error="TelegramForbiddenError")
    queue = await attention_queue(db, limit=50)
    assert any(c["tg_id"] == 3272 and c["rule"] == "q5" for c in queue["items"])


async def test_attention_queue_counts_full_not_limited(db):
    """counts/overdue — по всей очереди, не по limit."""
    await _ensure(db, 3281, ltv_stars=200, last_seen=_iso(days_ago=20))
    await _ensure(db, 3282, ltv_stars=200, last_seen=_iso(days_ago=25))
    await _ensure(db, 3283, ltv_stars=200, last_seen=_iso(days_ago=30))
    queue = await attention_queue(db, limit=2)
    assert queue["counts"]["p1"] >= 3  # все в P1 (Q2), лимит 2 не влияет на счётчик
    assert len(queue["items"]) == 2
    assert queue["truncated"] is True


async def test_attention_queue_synthetic_excluded(db):
    await _ensure(db, 10001, ltv_stars=100, last_seen=_iso(days_ago=20))
    queue = await attention_queue(db, limit=50)
    assert not any(c["tg_id"] == 10001 for c in queue["items"])


async def test_attention_queue_sorting(db):
    """P1 → P2 → P3, внутри тир A→B→None, затем давность."""
    await _ensure(db, 3291, ltv_stars=500, last_seen=_iso(days_ago=1))  # A, P1
    await _ensure(db, 3292, ltv_stars=500, last_seen=_iso(days_ago=10))  # A, P1 старше
    await _ensure(db, 3293, ltv_stars=0)  # None, P3
    await analytics_repo.track(db, "limit_reached", 3293)
    await analytics_repo.track(db, "limit_reached", 3293)
    await analytics_repo.track(db, "limit_reached", 3293)
    await _ensure(db, 3294, ltv_stars=50)  # B, P2
    await _deliver_at(db, 3294, "forecast", "k", _iso(hours_ago=1),
                      status="forbidden", error="TelegramForbiddenError")

    queue = await attention_queue(db, limit=50)
    priorities = [c["priority"] for c in queue["items"]]
    assert priorities == sorted(priorities, key=lambda p: ["p1", "p2", "p3"].index(p))


# ──────────────────────────────────────────────────────────────────────────────
# user_card_ltv
# ──────────────────────────────────────────────────────────────────────────────

async def test_user_card_ltv_fields(db):
    await _ensure(db, 3301, ltv_stars=100)
    await db.execute(
        "INSERT INTO orders(tg_id, kind, sku, title, amount_stars, amount_crystals, "
        "status, paid_at, created_at) VALUES "
        "(:t, 'plan', 'vip', 'v1', 100, 0, 'paid', :d1, :d1), "
        "(:t, 'plan', 'vip', 'v2', 200, 0, 'paid', :d2, :d2)",
        {"t": 3301, "d1": _iso(-30), "d2": _iso(-10)})
    await _deliver_at(db, 3301, "forecast", "k", _iso(hours_ago=1),
                      status="forbidden", error="TelegramForbiddenError")
    await analytics_repo.track(db, "limit_reached", 3301)
    await analytics_repo.track(db, "limit_reached", 3301)
    await analytics_repo.track(db, "limit_reached", 3301)
    await db.execute(
        "INSERT INTO user_notes(tg_id, author_id, text, created_at) "
        "VALUES(:t, 1, 'note', :c)",
        {"t": 3301, "c": _iso(-1)})

    ltv = await user_card_ltv(db, 3301)
    assert ltv["tier"] == "A"
    assert ltv["payments_count"] == 2
    assert ltv["avg_check_stars"] == 150
    assert ltv["channel_closed"] is True
    assert ltv["next_best_action"]["rule"] == "q5"
    assert "limit_hits" in ltv["risk_flags"]
    assert len(ltv["timeline"]) >= 1


async def test_user_card_ltv_synthetic(db):
    assert await user_card_ltv(db, 10001) is None


async def test_attention_queue_reason_data_fields(db):
    await _ensure(db, 3311, ltv_stars=100, sub_level="free")
    for i in range(4):
        await analytics_repo.track(db, "limit_reached", 3311)
    queue = await attention_queue(db, limit=50)
    item = next(c for c in queue["items"] if c["tg_id"] == 3311)
    assert item["rule"] == "q4"
    rd = item["reason_data"]
    assert "limit_hits_count" in rd
    assert "plan" in rd
    assert "next_plan" in rd
    assert "deep_link" in rd
    assert rd["limit_hits_count"] >= 3


# ──────────────────────────────────────────────────────────────────────────────
# API: GET /api/admin/attention-queue, user_card["ltv"]
# ──────────────────────────────────────────────────────────────────────────────

BASE_URL = "http://test"
HEADERS = {"X-Dev-Key": TEST_DEV_KEY}


@pytest.fixture
async def admin_client(db):
    app.dependency_overrides[get_db] = lambda: db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url=BASE_URL,
                           headers=HEADERS) as http:
        yield http
    app.dependency_overrides.clear()


def _admin_params(**extra):
    return {"dev_user": 1, **extra}


async def test_api_attention_queue_dashboard_ok(admin_client, db):
    await _ensure(db, 3401, ltv_stars=200, last_seen=_iso(days_ago=20))
    res = await admin_client.get("/api/admin/attention-queue",
                                 params=_admin_params())
    assert res.status_code == 200, res.text
    body = res.json()
    assert {"items", "counts", "overdue", "limit", "truncated"} <= set(body)
    assert body["limit"] == 50
    assert any(c["tg_id"] == 3401 and c["rule"] == "q2" and c["playbook"] == "pb-1"
               for c in body["items"])


async def test_api_attention_queue_requires_dashboard(admin_client, db):
    """dev_user без записи в admins → роль None → 403 (dev_user=1 — owner)."""
    res = await admin_client.get("/api/admin/attention-queue",
                                 params={"dev_user": 777001})
    assert res.status_code == 403, res.text


async def test_api_user_card_contains_ltv(admin_client, db):
    # 3421 — VIP с высоким ltv: поднимает топ-20% порог, 3411 остаётся в B.
    await _ensure(db, 3421, ltv_stars=900)
    await _ensure(db, 3411, ltv_stars=150)
    await db.execute(
        "INSERT INTO orders(tg_id, kind, sku, title, amount_stars, amount_crystals, "
        "status, paid_at, created_at) VALUES "
        "(:t, 'plan', 'vip', 'v1', 150, 0, 'paid', :d, :d)",
        {"t": 3411, "d": _iso(-5)})
    res = await admin_client.get("/api/admin/users/3411",
                                 params=_admin_params())
    assert res.status_code == 200, res.text
    ltv = res.json()["ltv"]
    assert ltv["tier"] == "B"
    assert ltv["payments_count"] == 1
    assert ltv["avg_check_stars"] == 150
    assert ltv["next_best_action"] is None
    assert isinstance(ltv["timeline"], list)
    assert ltv["channel_closed"] is False
