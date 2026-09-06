"""BUS-180: day-7 опрос (feedback).

Контракт:
- POST /api/feedback — happy path, анти-абьюз-ветки, 409 на дубль, allowlist.
- /api/me — флаг feedback_pending (True, если onboarded и ответов нет).
- События: feedback_survey_completed, survey_grant_issued (категориальные props,
  без score/текста — privacy-правило).
- Грант crystal_lot 40✦ source='review_bonus' на 90 дней — один на жизнь.
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
from app.repo import analytics, feedback as feedback_repo, users  # noqa: E402


# ───────────────────────────────── helpers ────────────────────────────────────

BASE_URL = "http://test"
HEADERS = {"X-Dev-Key": TEST_DEV_KEY}


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


def _post(client, user, body: dict):
    return client.post(
        "/api/feedback",
        params=_as_user(user),
        json=body,
        headers=HEADERS,
    )


async def _ensure_active_user(db, tg_id: int, name: str = "Участник") -> dict:
    """Активный onboarded-пользователь с подтверждённым возрастом."""
    await users.ensure(db, tg_id, name, f"user{tg_id}")
    await users.update(db, tg_id, onboarded=1, status="active",
                       birth_date="1992-03-15", birth_time="12:00",
                       birth_time_known=1, tz="Europe/Moscow",
                       sub_level="vip", memory_enabled=0)
    return await users.get(db, tg_id)


async def _seed_activity(db, tg_id: int, days: int = 7, events_per_day: int = 2):
    """Ключевые события последней недели: forecast_view, tarot_draw, question."""
    names = ["forecast_view", "tarot_draw", "question"]
    now = datetime.now(timezone.utc)
    for d in range(days):
        dt = now - timedelta(days=d)
        day = dt.strftime("%Y-%m-%d")
        for e in range(events_per_day):
            await db.execute(
                "INSERT INTO events(tg_id, name, day, created_at) "
                "VALUES(:tg_id, :name, :day, :created_at)",
                {"tg_id": tg_id, "name": names[e % len(names)],
                 "day": day, "created_at": dt.isoformat()})


# ─────────────────────────── fixtures ─────────────────────────────────────────

@pytest.fixture
async def client(db):
    app.dependency_overrides[get_db] = lambda: db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url=BASE_URL,
                           headers=HEADERS) as http:
        yield http
    app.dependency_overrides.clear()


# ─────────────────────────── happy path ───────────────────────────────────────

async def test_feedback_happy_path_bonus_granted(client, db):
    """Активный пользователь с активностью и длинным текстом → 200, бонус."""
    user = await _ensure_active_user(db, 2001, "Активная")
    await _seed_activity(db, 2001, days=5, events_per_day=2)

    resp = await _post(client, user, {
        "answers": _answers(),
        "survey_code": feedback_repo.SURVEY_CODE,
    })
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert body["bonus_granted"] is True

    # Ответ сохранён.
    row = await feedback_repo.get_response(db, 2001)
    assert row is not None
    assert row["bonus_granted"] == 1
    assert row["bonus_lot_id"] is not None

    # События воронки — только категориальные props.
    ev_completed = await db.execute(
        "SELECT props_json FROM events "
        "WHERE tg_id=2001 AND name='feedback_survey_completed'")
    ev = await ev_completed.fetchone()
    assert ev is not None
    props = json.loads(ev["props_json"] or "{}")
    assert props["survey_code"] == "day7_v1"
    assert props["bonus_granted"] == "true"
    assert props["question_count"] == 5
    assert "score" not in props
    assert "text" not in props

    ev_grant = await db.execute(
        "SELECT props_json FROM events "
        "WHERE tg_id=2001 AND name='survey_grant_issued'")
    ev2 = await ev_grant.fetchone()
    assert ev2 is not None
    props2 = json.loads(ev2["props_json"] or "{}")
    assert props2["bonus_kind"] == feedback_repo.BONUS_KIND
    assert props2["amount"] == 40

    # crystal_lot создана.
    lot = await db.execute(
        "SELECT * FROM crystal_lots WHERE tg_id=2001 AND source='review_bonus'")
    assert await lot.fetchone() is not None


async def test_feedback_no_bonus_no_activity(client, db):
    """Гейт активности не пройден → ответ сохранён, бонуса нет."""
    user = await _ensure_active_user(db, 2002, "Без_активности")

    resp = await _post(client, user, {
        "answers": _answers(),
        "survey_code": feedback_repo.SURVEY_CODE,
    })
    assert resp.status_code == 200
    assert resp.json()["bonus_granted"] is False

    row = await feedback_repo.get_response(db, 2002)
    assert row is not None
    assert row["bonus_granted"] == 0

    # survey_grant_issued не записан.
    ev = await db.execute(
        "SELECT 1 FROM events WHERE tg_id=2002 AND name='survey_grant_issued'")
    assert await ev.fetchone() is None


async def test_feedback_no_bonus_short_text(client, db):
    """Текст < 50 символов → гейт содержательного отзыва не пройден."""
    user = await _ensure_active_user(db, 2003, "Короткий")
    await _seed_activity(db, 2003, days=5, events_per_day=2)
    short = "Мало символов."

    resp = await _post(client, user, {
        "answers": [
            {"question_code": "like", "choice": "forecasts"},
            {"question_code": "dream", "text": short},
        ],
        "survey_code": feedback_repo.SURVEY_CODE,
    })
    assert resp.status_code == 200
    assert resp.json()["bonus_granted"] is False

    row = await feedback_repo.get_response(db, 2003)
    assert row["free_text"] == short


async def test_feedback_no_bonus_already_issued(client, db):
    """Один бонус за всю жизнь — повторный грант отклонён."""
    user = await _ensure_active_user(db, 2004, "Повтор")
    await _seed_activity(db, 2004, days=5, events_per_day=2)
    # Имитируем выданный ранее бонус.
    await db.execute(
        "INSERT INTO crystal_lots(tg_id, source, original_qty, remaining_qty, "
        "expires_at, created_at) VALUES(:tg_id, :source, 40, 40, :exp, :now)",
        {"tg_id": 2004, "source": feedback_repo.BONUS_SOURCE,
         "exp": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
         "now": datetime.now(timezone.utc).isoformat()})

    resp = await _post(client, user, {
        "answers": _answers(),
        "survey_code": feedback_repo.SURVEY_CODE,
    })
    assert resp.status_code == 200
    assert resp.json()["bonus_granted"] is False

    # Новый lot не создался.
    lots = await db.execute(
        "SELECT COUNT(*) c FROM crystal_lots WHERE tg_id=2004 "
        "AND source='review_bonus'")
    assert (await lots.fetchone())["c"] == 1


# ─────────────────────────── ошибки и границы ────────────────────────────────

async def test_feedback_duplicate_returns_409(client, db):
    """Повторный POST с тем же survey_code → 409 (UNIQUE на уровне БД)."""
    user = await _ensure_active_user(db, 2005, "Дубль")
    await _seed_activity(db, 2005, days=5, events_per_day=2)
    body = {"answers": _answers(), "survey_code": feedback_repo.SURVEY_CODE}

    r1 = await _post(client, user, body)
    assert r1.status_code == 200

    r2 = await _post(client, user, body)
    assert r2.status_code == 409
    assert r2.json()["detail"]["code"] == "survey_already_completed"


async def test_feedback_wrong_survey_code_rejected(client, db):
    """Неизвестная версия опроса → 422."""
    user = await _ensure_active_user(db, 2006, "Версия")
    resp = await _post(client, user, {
        "answers": _answers(),
        "survey_code": "day7_v2",
    })
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "survey_version_unknown"


async def test_feedback_allowlist_invalid_choice(client, db):
    """Категориальный код вне allowlist отбрасывается; если не осталось
    валидных ответов → 422."""
    user = await _ensure_active_user(db, 2007, "Allowlist")
    resp = await _post(client, user, {
        "answers": [{"question_code": "like", "choice": "invalid_choice"}],
        "survey_code": feedback_repo.SURVEY_CODE,
    })
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "no_valid_answers"


async def test_feedback_allowlist_score_out_of_range(client, db):
    """Score вне 0–10 отбрасывается."""
    user = await _ensure_active_user(db, 2008, "Score")
    resp = await _post(client, user, {
        "answers": [{"question_code": "nps", "score": 11}],
        "survey_code": feedback_repo.SURVEY_CODE,
    })
    assert resp.status_code == 422


# ─────────────────────────── /api/me flag ─────────────────────────────────────

async def test_feedback_pending_flag_in_me(client, db, user):
    """До ответа — feedback_pending=True; после ответа — False."""
    # До отправки.
    r = await client.get("/api/me", params=_as_user(user))
    assert r.status_code == 200
    assert r.json()["feedback_pending"] is True

    # Отправляем.
    await _seed_activity(db, user["tg_id"], days=5, events_per_day=2)
    r2 = await _post(client, user, {
        "answers": _answers(),
        "survey_code": feedback_repo.SURVEY_CODE,
    })
    assert r2.status_code == 200

    # После — флаг сброшен.
    r3 = await client.get("/api/me", params=_as_user(user))
    assert r3.status_code == 200
    assert r3.json()["feedback_pending"] is False
