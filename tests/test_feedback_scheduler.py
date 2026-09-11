"""BUS-235: e2e day-7 опроса — доставка, напоминание, opt-out (scheduler).

Покрывает недостающую часть скоупа BUS-170 §2/§5 против реализованной
scheduler-линии (app/services/scheduler.py::_feedback_survey):

1. Триггер день 7: приглашение уходит ровно один раз (dedup deliveries
   kind='feedback_survey', key='day7_v1') + событие feedback_survey_sent
   с категориальными props (без score/текста — privacy).
2. Напоминание день 10: уходит только если приглашение было, ответов нет;
   ровно один раз (key='day7_v1_remind').
3. После ответа (feedback_responses) напоминание не уходит.
4. Opt-out (deliveries kind='feedback_optout', key=str(tg_id)) гасит любые
   отправки — приглашение и напоминание больше не приходят.
5. e2e-шов «доставка → ответ через API → бонус»: после приглашения
   отправка POST /api/feedback даёт кристаллы (тот же тест-контур, что и
   продовый путь scheduler → Mini App → API).

Форма Mini App и кнопки Telegram — вне unit-досягаемости: клавиатура
собирается aiogram-типами (маркер web_app-кнопки проверяется косвенно
через «отправлено/не отправлено»), UI-форма верифицируется отдельно
(scripts/verify_feedback_ui.mjs, BUS-237).
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from conftest import TEST_DEV_KEY  # noqa: E402

pytest.importorskip("httpx", reason="httpx нужен для тестов API")
from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.api.deps import get_db  # noqa: E402
from app.api.main import app  # noqa: E402
from app.repo import comms, feedback as feedback_repo, users  # noqa: E402
from app.services import scheduler  # noqa: E402


BASE_URL = "http://test"
HEADERS = {"X-Dev-Key": TEST_DEV_KEY}


@pytest.fixture
async def client(db):
    from app.api.deps import get_db
    from app.api.main import app
    from httpx import ASGITransport, AsyncClient
    app.dependency_overrides[get_db] = lambda: db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test",
                           headers=HEADERS) as http:
        yield http
    app.dependency_overrides.clear()


class RecordingBot:
    """Фейковый бот: фиксирует (tg_id, text) отправок — паттерн test_scheduler_dedup."""

    def __init__(self):
        self.sent: list[tuple[int, str]] = []

    async def send_message(self, tg_id, text, reply_markup=None):
        self.sent.append((tg_id, text))


def _as_user(user):
    return {"dev_user": user["tg_id"]}


def _answers(extra_text: str = "") -> list:
    text = ("Этот текст длиной заведомо больше пятидесяти символов, "
            "поэтому пройдёт гейт бонуса." + extra_text).strip()
    return [
        {"question_code": "like", "choice": "forecasts"},
        {"question_code": "blocker", "choice": "nothing"},
        {"question_code": "nps", "score": 9},
        {"question_code": "dream", "text": text},
        {"question_code": "next", "choice": "practices"},
    ]


async def _day7_user(db, tg_id: int, days_ago: int, fixed_now: datetime) -> dict:
    """Onboarded-активный пользователь, зарегистрированный N дней назад."""
    created = (fixed_now - timedelta(days=days_ago)).isoformat()
    await users.ensure(db, tg_id, f"Участник{tg_id}", f"user{tg_id}")
    await users.update(db, tg_id, onboarded=1, status="active",
                       birth_date="1992-03-15", birth_time="12:00",
                       birth_time_known=1, tz="Europe/Moscow",
                       sub_level="vip", memory_enabled=0)
    await db.execute(
        "UPDATE users SET created_at=:created WHERE tg_id=:tg",
        {"tg": tg_id, "created": created})
    row = await users.get(db, tg_id)
    # created_at фиксируем явно, чтобы _feedback_survey считал от него.
    assert row is not None
    return row


def _make_fixed_now(hour_utc: int = 12) -> datetime:
    """Фиксированное «сейчас» в UTC, в окне 10–21 по Europe/Moscow.

    12:00 UTC = 15:00 MSK, часовой гейт проходит.
    """
    return datetime(2026, 9, 6, hour_utc, 0, 0, tzinfo=timezone.utc)


class FixedDatetime(datetime):
    """Монки-патч для scheduler.datetime, возвращает фиксированное UTC."""

    @classmethod
    def now(cls, tz=None):
        return FIXED_NOW.astimezone(tz) if tz else FIXED_NOW


@pytest.fixture(autouse=True)
def _patch_scheduler_env(monkeypatch):
    """Разрешаем _feedback_survey уходить дальше часового/флагового гейта."""
    from app.services import scheduler as s
    monkeypatch.setattr(s, "settings", type("S", (), {"webapp_url": "https://t.me"}))
    monkeypatch.setattr(s, "datetime", FixedDatetime)


FIXED_NOW = _make_fixed_now(12)


async def _run_feedback_survey(bot, db, user) -> None:
    await scheduler._feedback_survey(bot, db, user, FIXED_NOW)


async def _deliveries(db, tg_id: int, kind: str) -> list[str]:
    cur = await db.execute(
        "SELECT key, status FROM deliveries WHERE tg_id=:tg AND kind=:kind",
        {"tg": tg_id, "kind": kind})
    return [f"{r['key']}:{r['status']}" for r in await cur.fetchall()]


# ─────────────────────── триггер день 7 ──────────────────────────────────────

async def test_day7_invite_sent_once_and_event(db):
    """День 7: приглашение уходит, дедупится в deliveries, событие без score/текста."""
    user = await _day7_user(db, 4001, days_ago=7, fixed_now=FIXED_NOW)

    bot = RecordingBot()
    await _run_feedback_survey(bot, db, user)
    # track() пишет событие фоновой задачей — дожидаемся её перед SELECT.
    from app.services import analytics
    await analytics.drain()

    assert len(bot.sent) == 1, f"приглашение должно уйти один раз: {bot.sent}"
    text = bot.sent[0][1]
    assert "40 кристаллов" in text, "в приглашении должна быть мотивация бонуса"

    # Dedup: ровно одна строка kind='feedback_survey' key='day7_v1' в sent.
    marks = await _deliveries(db, 4001, "feedback_survey")
    assert marks == ["day7_v1:sent"], f"ожидали одну sent-отметку: {marks}"

    # Событие feedback_survey_sent — категориальные props.
    cur = await db.execute(
        "SELECT props_json FROM events WHERE tg_id=4001 "
        "AND name='feedback_survey_sent'")
    row = await cur.fetchone()
    assert row is not None, "feedback_survey_sent не записан"
    props = json.loads(row["props_json"] or "{}")
    assert props["survey_code"] == "day7_v1"
    assert props["delivery_key"] == "day7_v1"

    # Повторный тик (в тот же день) — второго сообщения нет.
    bot2 = RecordingBot()
    await _run_feedback_survey(bot2, db, user)
    assert bot2.sent == [], "повторный тик задублировал приглашение"


async def test_day7_not_sent_before_day7(db):
    """День < 7: приглашение не уходит."""
    user = await _day7_user(db, 4002, days_ago=3, fixed_now=FIXED_NOW)
    bot = RecordingBot()
    await _run_feedback_survey(bot, db, user)
    assert bot.sent == []
    assert await _deliveries(db, 4002, "feedback_survey") == []


# ─────────────────────── напоминание день 10 ─────────────────────────────────

async def test_day10_reminder_sent_once_after_invite(db):
    """День 10 без ответа: одно напоминание после приглашения, dedup по ключу."""
    user = await _day7_user(db, 4011, days_ago=10, fixed_now=FIXED_NOW)

    bot = RecordingBot()
    # Тик на день 7+: уходит приглашение.
    await _run_feedback_survey(bot, db, user)
    assert len(bot.sent) == 1

    # Второй тик в день 10: приглашение уже ушло, ответов нет → напоминание.
    await _run_feedback_survey(bot, db, user)
    assert len(bot.sent) == 2, f"напоминание должно уйти: {bot.sent}"

    marks = sorted(await _deliveries(db, 4011, "feedback_survey"))
    assert marks == ["day7_v1:sent", "day7_v1_remind:sent"], marks

    # Третий тик — тишина: максимум 2 сообщения за кампанию.
    bot2 = RecordingBot()
    await _run_feedback_survey(bot2, db, user)
    assert bot2.sent == [], "третья отправка за кампанию запрещена"


async def test_day10_reminder_not_sent_without_invite(db):
    """Напоминание само по себе не стартует без отправленного приглашения."""
    # Блокируем отправку приглашения через feedback_optout — напоминание
    # не сработает, т.к. sent_invite=False.
    user = await _day7_user(db, 4012, days_ago=10, fixed_now=FIXED_NOW)
    await comms.mark_sent(db, 4012, "feedback_optout", "4012")

    bot = RecordingBot()
    await _run_feedback_survey(bot, db, user)
    assert bot.sent == [], "opt-out блокирует и приглашение"


async def test_reminder_not_sent_after_answer(db):
    """Опрос пройден между приглашением и днём 10 — напоминание отменяется."""
    user = await _day7_user(db, 4013, days_ago=10, fixed_now=FIXED_NOW)

    bot = RecordingBot()
    await _run_feedback_survey(bot, db, user)  # приглашение
    assert len(bot.sent) == 1

    # Пользователь отвечает на опрос.
    await feedback_repo.submit(db, 4013,
                               answers_json='[{"question_code":"nps","score":9}]',
                               free_text=None, bonus_granted=False,
                               bonus_lot_id=None)

    await _run_feedback_survey(bot, db, user)
    assert len(bot.sent) == 1, "после ответа напоминание не должно уходить"


# ─────────────────────── opt-out ─────────────────────────────────────────────

async def test_optout_blocks_invite_and_reminder(db):
    """«Не спрашивать» → feedback_optout → ни приглашение, ни напоминание."""
    user = await _day7_user(db, 4021, days_ago=10, fixed_now=FIXED_NOW)

    # Пользователь нажал «Не спрашивать» до первого тика.
    await comms.mark_sent(db, 4021, "feedback_optout", "4021")

    bot = RecordingBot()
    await _run_feedback_survey(bot, db, user)
    await _run_feedback_survey(bot, db, user)
    assert bot.sent == [], "opt-out должен погасить все отправки day-7"
    assert await _deliveries(db, 4021, "feedback_survey") == []


async def test_optout_after_invite_blocks_reminder(db):
    """Приглашение ушло, затем «Не спрашивать» — напоминание не приходит."""
    user = await _day7_user(db, 4022, days_ago=10, fixed_now=FIXED_NOW)

    bot = RecordingBot()
    await _run_feedback_survey(bot, db, user)
    assert len(bot.sent) == 1

    await comms.mark_sent(db, 4022, "feedback_optout", "4022")
    await _run_feedback_survey(bot, db, user)
    assert len(bot.sent) == 1, "после opt-out напоминание ушло"

    marks = await _deliveries(db, 4022, "feedback_survey")
    assert marks == ["day7_v1:sent"], marks


# ─────────────────────── e2e-шов: доставка → ответ → бонус ────────────────────

async def test_e2e_invite_then_submit_via_api_grants_bonus(client, db):
    """Полный путь день 7: scheduler доставил приглашение → пользователь
    ответил через POST /api/feedback → бонус 40✦ (review_bonus, 90 дней)
    + dedup deliveries + события воронки."""
    user = await _day7_user(db, 4031, days_ago=7, fixed_now=FIXED_NOW)

    # Ключевая активность недели (гейт бонуса): 5 дней по 2 события.
    # События — относительно РЕАЛЬНОГО «сейчас»: activity_gate в API-пути
    # берёт now из datetime.now() (не из scheduler-патча), поэтому фикс на
    # FIXED_NOW делал тест красным, как только окно 7д уезжало от 06.09.
    names = ["forecast_view", "tarot_draw", "question"]
    real_now = datetime.now(timezone.utc)
    for d in range(5):
        moment = real_now - timedelta(days=d, hours=1)
        for e in range(2):
            await db.execute(
                "INSERT INTO events(tg_id, name, day, created_at) "
                "VALUES(:tg, :name, :day, :created)",
                {"tg": 4031, "name": names[e % len(names)],
                 "day": moment.strftime("%Y-%m-%d"),
                 "created": moment.isoformat()})

    bot = RecordingBot()
    await _run_feedback_survey(bot, db, user)
    assert len(bot.sent) == 1, "приглашение должно быть доставлено"

    # Пользователь отвечает в Mini App-форме → POST /api/feedback.
    app.dependency_overrides[get_db] = lambda: db
    try:
        async with AsyncClient(transport=ASGITransport(app=app),
                               base_url=BASE_URL, headers=HEADERS) as http:
            resp = await http.post(
                "/api/feedback", params=_as_user(user),
                json={"answers": _answers(),
                      "survey_code": feedback_repo.SURVEY_CODE})
    finally:
        app.dependency_overrides.clear()
    assert resp.status_code == 200, resp.text
    assert resp.json()["bonus_granted"] is True

    # Бонус: один лот 40✦ на 90 дней.
    lot = await db.execute(
        "SELECT source, original_qty, remaining_qty, expires_at FROM crystal_lots "
        "WHERE tg_id=4031 AND source='review_bonus'")
    row = await lot.fetchone()
    assert row is not None, "лот review_bonus не создан"
    assert row["original_qty"] == 40 and row["remaining_qty"] == 40
    exp = datetime.fromisoformat(row["expires_at"])
    days_left = (exp - datetime.now(timezone.utc)).days
    assert 88 <= days_left <= 90, f"expiry должен быть ~90 дней: {days_left}"

    # Напоминание после ответа не уходит.
    bot2 = RecordingBot()
    await _run_feedback_survey(bot2, db, user)
    assert bot2.sent == [], "после ответа никаких отправок"

    marks = await _deliveries(db, 4031, "feedback_survey")
    assert marks == ["day7_v1:sent"], marks
