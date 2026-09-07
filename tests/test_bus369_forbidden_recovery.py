"""BUS-369 mvp6_w2: порог forbidden + авто-очистка при возврате пользователя.

Критерии приёма:
- первые 2 неудачи подряд по разным дням → мягкий retry (failed)
- 3-я неудача подряд → hard_forbidden (терминально)
- clean_forbidden удаляет forbidden-строки кроме chain-видов
- /start и /api/me с auth вызывают clean_forbidden
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from aiogram.exceptions import TelegramForbiddenError
from aiogram.methods import SendMessage

from app.repo import comms, users
from app.services import scheduler

pytest.importorskip("httpx", reason="httpx нужен для тестов API")


class FakeBot:
    """Бот, который всегда падает с TelegramForbiddenError."""
    async def send_message(self, tg_id, text, reply_markup=None):
        raise TelegramForbiddenError(
            method=SendMessage(chat_id=tg_id, text=text),
            message="Forbidden: bot was blocked by the user")


class FakeOKBot:
    """Бот, который всегда доставляет."""
    async def send_message(self, tg_id, text, reply_markup=None):
        return None


# ──────────────────────── вспомогательные фикстуры ────────────────────────────


async def _ensure_user(db, tg_id: int = 4001):
    await users.ensure(db, tg_id, f"BUS369-{tg_id}")
    await users.update(db, tg_id, onboarded=1, tz="Europe/Moscow",
                       morning_push=1, sub_level="vip")
    return await users.get(db, tg_id)


def _freeze_today(monkeypatch, day: str):
    """Фиксирует datetime.now() на заданный день."""
    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            fixed = datetime.strptime(day, "%Y-%m-%d").replace(
                tzinfo=timezone.utc)
            return fixed.astimezone(tz) if tz else fixed

    monkeypatch.setattr(comms, "datetime", FixedDatetime)
    monkeypatch.setattr(scheduler, "datetime", FixedDatetime)


# ─────────────────────── порог 3: 2 failed → hard_forbidden ───────────────────


async def test_forbidden_threshold_three_consecutive_days(db, monkeypatch):
    """3-й день подряд → hard_forbidden; первые 2 → failed."""
    await _ensure_user(db, 4001)

    # День 1: forbidden → failed (счётчик=1)
    _freeze_today(monkeypatch, "2026-09-01")
    bot = FakeBot()
    ok = await scheduler._send_once(bot, db, 4001, "forecast", "2026-09-01", "день1")
    assert not ok
    row = await _get_delivery(db, 4001, "forecast", "2026-09-01")
    assert row["status"] == "failed"
    assert row["error"] == "TelegramForbiddenError"

    # День 2: forbidden → failed (счётчик=2)
    _freeze_today(monkeypatch, "2026-09-02")
    ok = await scheduler._send_once(bot, db, 4001, "forecast", "2026-09-02", "день2")
    assert not ok
    row = await _get_delivery(db, 4001, "forecast", "2026-09-02")
    assert row["status"] == "failed"

    # День 3: forbidden → hard_forbidden (счётчик=3)
    _freeze_today(monkeypatch, "2026-09-03")
    ok = await scheduler._send_once(bot, db, 4001, "forecast", "2026-09-03", "день3")
    assert not ok
    row = await _get_delivery(db, 4001, "forecast", "2026-09-03")
    assert row["status"] == "forbidden", \
        f"ожидали hard_forbidden (forbidden), получили {row['status']}"
    assert row["error"] == "TelegramForbiddenError"


async def test_forbidden_same_day_does_not_stack(db, monkeypatch):
    """Два сбоя в один день → не порог (нужны разные дни)."""
    await _ensure_user(db, 4002)
    _freeze_today(monkeypatch, "2026-09-04")

    bot = FakeBot()
    await scheduler._send_once(bot, db, 4002, "forecast", "2026-09-04", "a")
    await scheduler._send_once(bot, db, 4002, "forecast", "2026-09-05", "b")

    # Два разных дня — счётчик 2, порога нет.
    assert not await comms.forbidden_threshold(db, 4002)


async def test_forbidden_window_7_days(db, monkeypatch):
    """Счётчик сбрасывается, если последняя неудача старше 7 дней."""
    await _ensure_user(db, 4003)

    bot = FakeBot()
    # 3 дня подряд: 01, 02, 03 → порог достиг (09-03 — hard_forbidden)
    for day in ["2026-09-01", "2026-09-02", "2026-09-03"]:
        _freeze_today(monkeypatch, day)
        await scheduler._send_once(bot, db, 4003, "forecast", day, "x")

    row = await _get_delivery(db, 4003, "forecast", "2026-09-03")
    assert row["status"] == "forbidden"

    # Пропускаем 7 дней: 04-10. 11 сентября — новое окно, счётчик пуст.
    _freeze_today(monkeypatch, "2026-09-11")
    ok_bot = FakeOKBot()
    ok = await scheduler._send_once(ok_bot, db, 4003, "forecast", "2026-09-11", "ок")
    assert ok, "успешная доставка не прошла"

    # Следующая неудача должна начать новый счётчик с 1.
    _freeze_today(monkeypatch, "2026-09-12")
    ok = await scheduler._send_once(bot, db, 4003, "forecast", "2026-09-12", "y")
    assert not ok
    row = await _get_delivery(db, 4003, "forecast", "2026-09-12")
    assert row["status"] == "failed", \
        "после окна 7 дней счётчик должен сброситься"
    assert not await comms.forbidden_threshold(db, 4003)


async def test_success_resets_forbidden_counter(db, monkeypatch):
    """Успешная доставка между неудачами сбрасывает streak."""
    await _ensure_user(db, 4004)

    bot = FakeBot()
    ok_bot = FakeOKBot()
    _freeze_today(monkeypatch, "2026-09-01")
    await scheduler._send_once(bot, db, 4004, "forecast", "2026-09-01", "x")
    _freeze_today(monkeypatch, "2026-09-02")
    await scheduler._send_once(ok_bot, db, 4004, "forecast", "2026-09-02", "ok")
    _freeze_today(monkeypatch, "2026-09-03")
    await scheduler._send_once(bot, db, 4004, "forecast", "2026-09-03", "y")

    # success посередине разрывает streak: 2 дня подряд не набралось.
    row = await _get_delivery(db, 4004, "forecast", "2026-09-03")
    assert row["status"] == "failed", \
        "success посередине должен сбросить streak forbidden"
    assert not await comms.forbidden_threshold(db, 4004)


# ─────────────────────── clean_forbidden ───────────────────────────────────────


async def test_clean_forbidden_removes_non_chain(db):
    """clean_forbidden удаляет forbidden-строки не-chain-видов."""
    await _ensure_user(db, 4010)
    await comms.mark_sent(db, 4010, "forecast", "f1", status="forbidden",
                          error="TelegramForbiddenError")
    await comms.mark_sent(db, 4010, "weekly", "w1", status="forbidden",
                          error="TelegramForbiddenError")
    await comms.mark_sent(db, 4010, "welcome_chain", "d1:4010",
                          status="forbidden", error="TelegramForbiddenError")

    removed = await comms.clean_forbidden(db, 4010)
    assert removed == 2, f"ожидали удаление 2 строк, удалено {removed}"

    assert await comms.already_sent(db, 4010, "forecast", "f1") is False
    assert await comms.already_sent(db, 4010, "weekly", "w1") is False
    # Chain-вид сохраняется.
    assert await comms.already_sent(db, 4010, "welcome_chain", "d1:4010") is True


async def test_clean_forbidden_resets_counter(db):
    """clean_forbidden сбрасывает forbidden-счётчик."""
    await _ensure_user(db, 4011)
    from app.repo import content as content_repo
    key = comms._forbidden_key(4011)
    await content_repo.set_setting(db, key, {"events": ["2026-09-01", "2026-09-02"]})
    assert await comms.forbidden_threshold(db, 4011) is False  # 2 < 3

    await comms.clean_forbidden(db, 4011)

    cur = await db.execute("SELECT 1 FROM settings WHERE key=:k", {"k": key})
    assert await cur.fetchone() is None, "счётчик не очищен"
    assert not await comms.forbidden_threshold(db, 4011)


async def test_clean_forbidden_keeps_sent_and_failed(db):
    """clean_forbidden трогает только forbidden; sent/failed остаются."""
    await _ensure_user(db, 4012)
    await comms.mark_sent(db, 4012, "forecast", "sent1", status="sent")
    await comms.mark_sent(db, 4012, "forecast", "forb1", status="forbidden")
    await comms.mark_sent(db, 4012, "forecast", "fail1",
                          status="failed", error="ConnectionError")

    removed = await comms.clean_forbidden(db, 4012)
    assert removed == 1
    assert await comms.already_sent(db, 4012, "forecast", "sent1")
    assert await comms.already_sent(db, 4012, "forecast", "forb1") is False
    assert await comms.already_sent(db, 4012, "forecast", "fail1") is False


# ─────────────────────── точки возврата ───────────────────────────────────────


@pytest.fixture
async def client(db):
    from httpx import ASGITransport, AsyncClient

    from conftest import TEST_DEV_KEY
    from app.api.deps import get_db
    from app.api.main import app

    app.dependency_overrides[get_db] = lambda: db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test",
                           headers={"X-Dev-Key": TEST_DEV_KEY}) as http:
        yield http
    app.dependency_overrides.clear()


async def test_api_me_triggers_clean_forbidden(client, db):
    """GET /api/me вызывает clean_forbidden — восстановление пуша."""
    await _ensure_user(db, 4021)
    await comms.mark_sent(db, 4021, "forecast", "f1", status="forbidden")
    assert await comms.already_sent(db, 4021, "forecast", "f1")

    resp = await client.get("/api/me", params={"dev_user": 4021})
    assert resp.status_code == 200

    assert not await comms.already_sent(db, 4021, "forecast", "f1"), \
        "/api/me не очистил forbidden"


async def test_start_deeplink_triggers_clean_forbidden(db):
    """start_deeplink вызывает clean_forbidden."""
    from app.bot import onboarding

    await _ensure_user(db, 4031)
    await comms.mark_sent(db, 4031, "forecast", "f1", status="forbidden")

    msg = _fake_message(4031, "/start ref_abc")
    state = _FakeState()
    with patch.object(onboarding.users, "ensure"), \
         patch.object(onboarding.users, "get", return_value=await users.get(db, 4031)), \
         patch.object(onboarding, "referrals") as mock_referrals, \
         patch.object(onboarding.billing_svc, "redeem_promo",
                      side_effect=AsyncMock(return_value=None)), \
         patch.object(onboarding, "_begin"), \
         patch.object(onboarding.analytics, "track"):
        mock_referrals.parse_ref.return_value = None
        await onboarding.start_deeplink(msg, _FakeCommand(args="ref_abc"),
                                        state, db)

    assert not await comms.already_sent(db, 4031, "forecast", "f1"), \
        "start_deeplink не очистил forbidden"


async def test_start_command_triggers_clean_forbidden(db):
    """Обычный /start вызывает clean_forbidden."""
    from app.bot import onboarding

    await _ensure_user(db, 4032)
    await comms.mark_sent(db, 4032, "forecast", "f2", status="forbidden")

    msg = _fake_message(4032, "/start")
    state = _FakeState()
    with patch.object(onboarding.users, "ensure"), \
         patch.object(onboarding.users, "get", return_value=await users.get(db, 4032)), \
         patch.object(onboarding, "_begin"), \
         patch.object(onboarding.analytics, "track"):
        await onboarding.start(msg, state, db)

    assert not await comms.already_sent(db, 4032, "forecast", "f2")


# ─────────────────────── chain-виды: не доотправляем ───────────────────────────


async def test_chain_forbidden_preserved_after_clean(db):
    """Chain-виды (welcome_chain, reactivate…) не удаляются clean_forbidden."""
    await _ensure_user(db, 4040)
    chain_kinds = [
        ("welcome_chain", "d1:4040"),
        ("onboard_nudge", "d1:4040"),
        ("reactivate", "r1:2026-09"),
        ("feedback_survey", "day7_v1"),
        ("winback2", "2026-09-01"),
    ]
    for kind, key in chain_kinds:
        await comms.mark_sent(db, 4040, kind, key, status="forbidden")

    removed = await comms.clean_forbidden(db, 4040)
    assert removed == 0, "chain-виды не должны удаляться"

    for kind, key in chain_kinds:
        assert await comms.already_sent(db, 4040, kind, key), \
            f"chain-kind {kind} не должен удаляться"


# ─────────────────────── chain-виды: hard_forbidden стопит цепочку ─────────────


async def test_chain_threshold_still_blocks(db, monkeypatch):
    """Chain-виды при hard_forbidden останавливаются (не доотправляем)."""
    await _ensure_user(db, 4050)

    bot = FakeBot()
    # 3 дня подряд для chain-вида.
    for day in ["2026-09-01", "2026-09-02", "2026-09-03"]:
        _freeze_today(monkeypatch, day)
        await scheduler._send_once(bot, db, 4050, "welcome_chain",
                                   f"d1:{4050}", "text")

    row = await _get_delivery(db, 4050, "welcome_chain", f"d1:{4050}")
    assert row["status"] == "forbidden"

    # clean_forbidden НЕ удаляет chain-вид → цепочка остаётся заблокированной.
    removed = await comms.clean_forbidden(db, 4050)
    assert removed == 0
    assert await comms.already_sent(db, 4050, "welcome_chain", f"d1:{4050}")

    # Возврат пользователя: /start очищает не-chain forbidden, но цепочка
    # уже в hard_forbidden и НЕ доотправляется — верно по PM-решению.
    ok_bot = FakeOKBot()
    _freeze_today(monkeypatch, "2026-09-04")
    # Новый вызов — тот же kind+key, claim не пройдёт (forbidden).
    sent = await scheduler._send_once(ok_bot, db, 4050, "welcome_chain",
                                      f"d1:{4050}", "retry")
    assert not sent, "chain-вид при hard_forbidden не должен доотправляться"


# ─────────────────────── утилиты ───────────────────────────────────────────────


async def _get_delivery(db, tg_id: int, kind: str, key: str):
    cur = await db.execute(
        "SELECT * FROM deliveries WHERE tg_id=:tg_id AND kind=:kind AND key=:key",
        {"tg_id": tg_id, "kind": kind, "key": key})
    return await cur.fetchone()


class _FakeCommand:
    def __init__(self, args=""):
        self.args = args


class _FakeState:
    async def clear(self):
        pass

    async def set_state(self, *a, **kw):
        pass

    @property
    def state(self):
        return self


def _fake_message(tg_id: int, text: str):
    from aiogram.types import Message, User as TgUser, Chat
    return Message(
        message_id=1,
        date=0,
        chat=Chat(id=tg_id, type="private"),
        from_user=TgUser(id=tg_id, first_name=f"U{tg_id}", is_bot=False),
        text=text,
    )
