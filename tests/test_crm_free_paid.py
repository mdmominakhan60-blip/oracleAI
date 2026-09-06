"""BUS-257 волна 3.2 — free→paid по событию: post_limit (+24ч) и low_balance (<1ч).

Контракт:
- post_limit: ключ = event_date (дата limit_reached), окно 24–48ч, нет покупки после.
- low_balance: ключ = event_date (дата credit_balance_low), окно <1ч, нет покупки после,
  не в день post_limit (разводка через comms.sent_since по deliveries.created_at).
- Разводка: если post_limit ушёл сегодня, low_balance переносится на следующий день.
- Стоп поканальный: post_limit/low_balance не чаще раза в 7 дней.
- Событийные — вне guardrail 1/7д, но между собой не в один день (BUS-190 §5).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from app.repo import users
from app.services import scheduler


class RecordingBot:
    def __init__(self):
        self.sent: list[tuple[int, str, str, str]] = []

    async def send_message(self, tg_id, text, reply_markup=None):
        self.sent.append((tg_id, "", text, ""))


def _iso(dt: datetime) -> str:
    return dt.isoformat()


async def _ensure_free(db, tg_id: int, name: str = "Тест") -> dict:
    await users.ensure(db, tg_id, name)
    await users.update(db, tg_id, onboarded=1, sub_level="free",
                       sub_until=None, lang="ru")
    return await users.get(db, tg_id)


async def _event(db, tg_id: int, name: str, dt: datetime):
    await db.execute(
        "INSERT INTO events(tg_id, name, day, created_at) "
        "VALUES(:tg_id, :name, :day, :created_at)",
        {"tg_id": tg_id, "name": name,
         "day": dt.strftime("%Y-%m-%d"), "created_at": _iso(dt)})


# ─────────────────────────── моки comms + _send_once ───────────────────────────

@pytest.fixture(autouse=True)
def _patch_comms():
    """Перехватываем comms и _send_once, чтобы не зависеть от схемы deliveries тестовой БД."""
    claimed: dict[tuple[int, str, str], bool] = {}
    sent: dict[tuple[int, str, str], bool] = {}
    sent_since_map: dict[tuple[int, str], str] = {}

    async def fake_claim(db, tg_id, kind, key):
        result = claimed.get((tg_id, kind, key), True)
        claimed[(tg_id, kind, key)] = result
        return result

    async def fake_already_sent(db, tg_id, kind, key):
        return sent.get((tg_id, kind, key), False)

    async def fake_sent_since(db, tg_id, kind, since: str) -> bool:
        ts = sent_since_map.get((tg_id, kind))
        return ts >= since if ts else False

    async def fake_send_once(bot, db, tg_id, kind, key, text, markup=None):
        sent[(tg_id, kind, key)] = True
        sent_since_map[(tg_id, kind)] = datetime.now(timezone.utc).isoformat()
        bot.sent.append((tg_id, kind, text, key))
        return True

    with patch("app.services.scheduler.comms.claim", fake_claim), \
         patch("app.services.scheduler.comms.already_sent", fake_already_sent), \
         patch("app.services.scheduler.comms.sent_since", fake_sent_since), \
         patch("app.services.scheduler._send_once", fake_send_once):
        yield


# ─────────────────────────── post_limit ───────────────────────────────────────

async def test_post_limit_sent_after_24h(db):
    """post_limit уходит, если limit_reached был 24–48ч назад и покупок нет."""
    user = await _ensure_free(db, 5001)
    bot = RecordingBot()
    now = datetime.now(timezone.utc)
    limit_dt = now - timedelta(hours=30)
    await _event(db, user["tg_id"], "limit_reached", limit_dt)
    await db.commit()

    await scheduler._crm_free_paid(bot, db, user, now_utc=now)

    kinds = {kind for _, kind, _, _ in bot.sent}
    assert kinds == {"post_limit"}
    assert bot.sent[0][2].startswith("{name}") is False


async def test_post_limit_not_sent_if_paid_after_limit(db):
    """Стоп-условие: payment_success после limit_reached — post_limit не уходит."""
    user = await _ensure_free(db, 5002)
    bot = RecordingBot()
    now = datetime.now(timezone.utc)
    limit_dt = now - timedelta(hours=30)
    pay_dt = now - timedelta(hours=10)
    await _event(db, user["tg_id"], "limit_reached", limit_dt)
    await _event(db, user["tg_id"], "payment_success", pay_dt)
    await db.commit()

    await scheduler._crm_free_paid(bot, db, user, now_utc=now)

    assert bot.sent == []


async def test_post_limit_not_sent_outside_window(db):
    """post_limit не уходит за пределами 24–48ч окна."""
    user = await _ensure_free(db, 5003)
    bot = RecordingBot()
    now = datetime.now(timezone.utc)
    limit_dt = now - timedelta(hours=10)  # слишком рано
    await _event(db, user["tg_id"], "limit_reached", limit_dt)
    await db.commit()

    await scheduler._crm_free_paid(bot, db, user, now_utc=now)

    assert bot.sent == []


# ─────────────────────────── low_balance ──────────────────────────────────────

async def test_low_balance_sent_within_hour(db):
    """low_balance уходит, если credit_balance_low <1ч назад, покупок нет."""
    user = await _ensure_free(db, 5004)
    bot = RecordingBot()
    now = datetime.now(timezone.utc)
    low_dt = now - timedelta(minutes=20)
    await _event(db, user["tg_id"], "credit_balance_low", low_dt)
    await db.commit()

    await scheduler._crm_free_paid(bot, db, user, now_utc=now)

    kinds = {kind for _, kind, _, _ in bot.sent}
    assert kinds == {"low_balance"}


async def test_low_balance_not_sent_outside_window(db):
    """low_balance не уходит за пределами 1ч окна."""
    user = await _ensure_free(db, 5005)
    bot = RecordingBot()
    now = datetime.now(timezone.utc)
    low_dt = now - timedelta(hours=2)
    await _event(db, user["tg_id"], "credit_balance_low", low_dt)
    await db.commit()

    await scheduler._crm_free_paid(bot, db, user, now_utc=now)

    assert bot.sent == []


# ─────────────────────────── разводка post_limit ↔ low_balance ────────────────

async def test_low_balance_deferred_when_post_limit_sent_today(db):
    """Если post_limit ушёл сегодня — low_balance не уходит в тот же день;
    на следующий день с новым credit_balance_low — уходит (разводка снята)."""
    user = await _ensure_free(db, 5006)
    bot = RecordingBot()
    now = datetime.now(timezone.utc)
    limit_dt = now - timedelta(hours=30)
    low_dt = now - timedelta(minutes=20)
    await _event(db, user["tg_id"], "limit_reached", limit_dt)
    await _event(db, user["tg_id"], "credit_balance_low", low_dt)
    await db.commit()

    await scheduler._crm_free_paid(bot, db, user, now_utc=now)

    kinds = {kind for _, kind, _, _ in bot.sent}
    assert kinds == {"post_limit"}, f"ожидался только post_limit, ушло: {kinds}"

    # следующий день: свежий credit_balance_low → low_balance уходит
    tomorrow = now + timedelta(days=1)
    fresh = await users.get(db, user["tg_id"])
    bot2 = RecordingBot()
    new_low = tomorrow - timedelta(minutes=20)
    await _event(db, user["tg_id"], "credit_balance_low", new_low)
    await db.commit()
    await scheduler._crm_free_paid(bot2, db, fresh, now_utc=tomorrow)
    kinds2 = {kind for _, kind, _, _ in bot2.sent}
    assert "low_balance" in kinds2, f"на следующий день low_balance не ушёл: {kinds2}"


# ─────────────────────────── поканальные стоп-условия ──────────────────────────

async def test_stop_post_limit_after_7_days(db):
    """7 дней без покупки после limit_reached — post_limit не уходит."""
    user = await _ensure_free(db, 5007)
    bot = RecordingBot()
    now = datetime.now(timezone.utc)
    limit_dt = now - timedelta(days=8)
    await _event(db, user["tg_id"], "limit_reached", limit_dt)
    await db.commit()

    await scheduler._crm_free_paid(bot, db, user, now_utc=now)

    assert bot.sent == []


async def test_stop_low_balance_after_7_days(db):
    """7 дней без покупки после credit_balance_low — low_balance не уходит."""
    user = await _ensure_free(db, 5008)
    bot = RecordingBot()
    now = datetime.now(timezone.utc)
    low_dt = now - timedelta(days=8)
    await _event(db, user["tg_id"], "credit_balance_low", low_dt)
    await db.commit()

    await scheduler._crm_free_paid(bot, db, user, now_utc=now)

    assert bot.sent == []


async def test_post_limit_not_blocked_by_low_balance_7d_stop(db):
    """Кросс-канальный7-дневный стоп НЕ блокирует post_limit, если
    последний low_balance был >7д назад (поканальный стоп, не кросс-канальный)."""
    user = await _ensure_free(db, 5011)
    bot = RecordingBot()
    now = datetime.now(timezone.utc)
    limit_dt = now - timedelta(hours=30)
    old_low_dt = now - timedelta(days=10)
    await _event(db, user["tg_id"], "limit_reached", limit_dt)
    await _event(db, user["tg_id"], "credit_balance_low", old_low_dt)
    await db.commit()

    await scheduler._crm_free_paid(bot, db, user, now_utc=now)

    kinds = {kind for _, kind, _, _ in bot.sent}
    assert kinds == {"post_limit"}


async def test_low_balance_not_sent_if_paid_after_low(db):
    """Стоп: payment_success после credit_balance_low — low_balance не уходит."""
    user = await _ensure_free(db, 5009)
    bot = RecordingBot()
    now = datetime.now(timezone.utc)
    low_dt = now - timedelta(minutes=20)
    pay_dt = now - timedelta(minutes=5)
    await _event(db, user["tg_id"], "credit_balance_low", low_dt)
    await _event(db, user["tg_id"], "payment_success", pay_dt)
    await db.commit()

    await scheduler._crm_free_paid(bot, db, user, now_utc=now)

    assert bot.sent == []


async def test_no_send_if_user_is_paid(db):
    """Активная подписка — обе ветки молчат."""
    user = await _ensure_free(db, 5010)
    await users.update(db, user["tg_id"], sub_level="vip",
                       sub_until=_iso(datetime.now(timezone.utc) + timedelta(days=10)))
    user = await users.get(db, user["tg_id"])
    bot = RecordingBot()
    now = datetime.now(timezone.utc)
    limit_dt = now - timedelta(hours=30)
    low_dt = now - timedelta(minutes=20)
    await _event(db, user["tg_id"], "limit_reached", limit_dt)
    await _event(db, user["tg_id"], "credit_balance_low", low_dt)
    await db.commit()

    await scheduler._crm_free_paid(bot, db, user, now_utc=now)

    assert bot.sent == []


async def test_seed_content_ru_en_exists(db):
    """Seed-тексты post_limit и low_balance существуют на ru (seed) и en (fallback)."""
    from app.repo.content import DEFAULT_EN_CONTENT
    ru_post = await db.execute(
        "SELECT body FROM content_items WHERE kind='copy' AND code='post_limit'")
    ru_low = await db.execute(
        "SELECT body FROM content_items WHERE kind='copy' AND code='low_balance'")
    rp = await ru_post.fetchone()
    rl = await ru_low.fetchone()
    assert rp and "{name}" in rp["body"]
    assert rl and "{name}" in rl["body"]
    assert ("copy", "post_limit") in DEFAULT_EN_CONTENT
    assert ("copy", "low_balance") in DEFAULT_EN_CONTENT
    assert "{name}" in DEFAULT_EN_CONTENT[("copy", "post_limit")]["body"]
    assert "{name}" in DEFAULT_EN_CONTENT[("copy", "low_balance")]["body"]
