"""Day-7 опрос отзывов (BUS-180): ответы, гейт активности, бонус-грант.

Схема — миграция 0009: одна строка `feedback_responses` на (tg_id, survey_code),
ответы вопросов — JSON-массив `answers_json` (категориальные коды + score),
свободный текст — единственное место его хранения (privacy-инвариант: в events
текст пользователя не попадает). Повторный POST отклоняется UNIQUE-констрейнтом
на уровне БД — анти-абьюз BUS-170 §5.1 не полагается на клиент или флаг.

Бонус — crystal_lot (40✦, source='review_bonus', 90 дней, BUS-177) в той же
внешней транзакции, что и INSERT ответов: UNIQUE откатит лот при конкурентном
дабл-посте. Идемпотентность гранта по (tg_id, source='review_bonus') — один
бонус на пользователя за всю жизнь.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ..data.session import utcnow

SURVEY_CODE = "day7_v1"

#: Allowlist категориальных кодов по вопросам (BUS-167 §2; 'other' — кнопка
#: ввода своего текста, в answers_json не пишется — текст уходит в free_text).
ALLOWED_CHOICES: dict[str, set[str]] = {
    "like": {"forecasts", "tarot", "diary", "voice", "chart"},
    "blocker": {"offtopic", "slow", "paywall", "lost", "nothing", "other"},
    "next": {"compat", "practices", "lunar", "personal", "other"},
}

SCORE_QUESTIONS = {"nps"}
TEXT_QUESTIONS = {"dream"}
ALL_QUESTIONS = ("like", "blocker", "nps", "dream", "next")

#: Гейт содержательного отзыва (CFO BUS-177 §5.3b): текст ≥50 символов —
#: гейт бонуса, не гейт подачи.
MIN_REVIEW_CHARS = 50

#: Параметры гранта (BUS-170 §7 v3): 40✦ lot'ом на 90 дней.
BONUS_CRYSTALS = 40
BONUS_SOURCE = "review_bonus"
BONUS_VALID_DAYS = 90
BONUS_KIND = "crystals_40"


class SurveyAlreadyCompleted(Exception):
    """Повторный POST при существующей строке (tg_id, survey_code) → 409."""


async def get_response(db, tg_id: int, survey_code: str = SURVEY_CODE):
    cur = await db.execute(
        "SELECT tg_id, survey_code, answers_json, free_text, status, "
        "bonus_granted, bonus_lot_id, created_at FROM feedback_responses "
        "WHERE tg_id=:tg_id AND survey_code=:code",
        {"tg_id": tg_id, "code": survey_code})
    row = await cur.fetchone()
    return dict(row) if row else None


async def pending(db, tg_id: int) -> bool:
    """True — опрос ещё не пройден (флаг feedback_pending для /api/me)."""
    return await get_response(db, tg_id) is None


def normalize_answers(items: list[dict]) -> tuple[list[dict], str]:
    """Валидация и нормализация ответов (серверный allowlist, BUS-170 §5.5).

    Возвращает (answers_json, free_text). Коды вариантов вне allowlist
    отбрасываются, score — только целое 0–10, текст — только у dream/other,
    длина ограничена. Исключение пустых вопросов — забота вызывающего
    (нужен ≥1 валидный ответ, иначе 422).
    """
    answers: list[dict] = []
    free_text = ""
    # Q4 (dream) — основной отзыв для бонус-гейта; other-текст Q2/Q5 —
    # запасной вариант: одна колонка free_text на отзыв (миграция 0009).
    dream_text = ""
    other_text = ""
    for item in items:
        question = str(item.get("question_code") or "")[:32]
        if question not in ALL_QUESTIONS:
            continue
        entry: dict = {"question_code": question}
        if question in SCORE_QUESTIONS:
            try:
                score = int(item.get("score"))
            except (TypeError, ValueError):
                continue
            if not 0 <= score <= 10:
                continue
            entry["score"] = score
        else:
            choice = str(item.get("choice") or "")[:32]
            if choice not in ALLOWED_CHOICES.get(question, set()):
                continue
            entry["choice"] = choice
            # Свой вариант по Q2/Q5 ('other') и текст Q4 — в free_text:
            # событие остаётся категориальным (privacy-правило словаря).
            text = str(item.get("text") or "").strip()[:4000]
            if question in TEXT_QUESTIONS:
                dream_text = text or dream_text
            elif question in ("blocker", "next") and choice == "other":
                other_text = other_text or text
        answers.append(entry)
    free_text = dream_text or other_text
    return answers, free_text


async def activity_gate(db, tg_id: int, *, now: datetime | None = None) -> bool:
    """Гейт реальной недели активности (CFO BUS-177 §5.3a): ≥3 из 7 дней
    ИЛИ ≥5 ключевых событий. Окно — 7 дней до момента проверки. fail-open
    недопустим: ключевая активность определяется по существующим таблицам.

    Ключевые события (BUS-170 §5.3a): daily insight (forecast_view), ритуал
    (tarot_draw / практики — упрощено до событий), AI-сообщение.
    """
    now = now or datetime.now(timezone.utc)
    since = (now - timedelta(days=7)).isoformat()
    cur = await db.execute(
        "SELECT COUNT(DISTINCT substr(created_at,1,10)) days, COUNT(*) n "
        "FROM events WHERE tg_id=:tg_id AND created_at>=:since "
        "AND name IN (:forecast, :ritual, :question)",
        {"tg_id": tg_id, "since": since, "forecast": "forecast_view",
         "ritual": "tarot_draw", "question": "question"})
    row = await cur.fetchone()
    if not row:
        return False
    if int(row["days"] or 0) >= 3:
        return True
    return int(row["n"] or 0) >= 5


async def bonus_issued_before(db, tg_id: int) -> bool:
    """Один бонус на пользователя за всю жизнь (BUS-170 §5.3): SELECT перед
    грантом, т.к. crystal_lot() — чистый INSERT без dedup."""
    cur = await db.execute(
        "SELECT 1 FROM crystal_lots WHERE tg_id=:tg_id AND source=:source "
        "AND remaining_qty>0 LIMIT 1",
        {"tg_id": tg_id, "source": BONUS_SOURCE})
    return bool(await cur.fetchone())


async def submit(db, tg_id: int, *, answers_json: str, free_text: str,
                 bonus_granted: bool, bonus_lot_id: int | None) -> dict:
    """INSERT строки отзыва. IntegrityError на UNIQUE — SurveyAlreadyCompleted.

    Вызывается внутри внешней транзакции вместе с грантом: конфликт UNIQUE
    откатывает всю транзакцию (ответы не пишутся без однозначного исхода).
    """
    try:
        cur = await db.execute(
            "INSERT INTO feedback_responses(tg_id, survey_code, answers_json, "
            "free_text, status, bonus_granted, bonus_lot_id, created_at) "
            "VALUES(:tg_id, :code, :answers, :free_text, 'submitted', "
            ":bonus_granted, :lot_id, :created_at) "
            "RETURNING id, created_at",
            {"tg_id": tg_id, "code": SURVEY_CODE, "answers": answers_json,
             "free_text": free_text or None,
             "bonus_granted": 1 if bonus_granted else 0,
             "lot_id": bonus_lot_id, "created_at": utcnow()})
        row = await cur.fetchone()
    except Exception as exc:  # sqlalchemy.exc.IntegrityError на UNIQUE
        if "unique" in str(exc).lower() or "duplicate" in str(exc).lower():
            raise SurveyAlreadyCompleted() from exc
        raise
    return {"id": int(row["id"]), "created_at": row["created_at"]}


def grant_expires_at(now: datetime) -> str:
    return (now + timedelta(days=BONUS_VALID_DAYS)).isoformat()


def answers_summary(answers: list[dict]) -> dict:
    """Категориальные props события feedback_survey_completed (без score/текста
    — privacy-правило словаря: вопрос-коды и их количество, не содержание)."""
    return {"question_count": len(answers)}
