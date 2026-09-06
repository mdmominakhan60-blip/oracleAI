"""Админка R6 (BUS-237): чтение отзывов day-7 опроса.

Источники: feedback_responses (схема 0009, ответы — JSON, free text — только
здесь по privacy-инварианту BUS-168 §2.3) + deliveries (kind='feedback_survey',
key='day7_v1') для response rate. Роли модерации (pending/ok/flagged) —
семантика поля status: сейчас всё 'submitted' (LLM-классификация придёт позже),
фильтр/флаги оставлены в контракте, чтобы UI не менялся при включении.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

SURVEY_CODE = "day7_v1"

#: Вопросы day7_v1: категориальные (варианты), score (NPS), текст.
CHOICES: dict[str, tuple[str, ...]] = {
    "like": ("forecasts", "tarot", "diary", "voice", "chart"),
    "blocker": ("offtopic", "slow", "paywall", "lost", "nothing", "other"),
    "next": ("compat", "practices", "lunar", "personal", "other"),
}
SCORE_QUESTIONS = ("nps",)
TEXT_QUESTIONS = ("dream",)

#: Модерация-статусы R6 (LLM-классификация асинхронная): 'submitted' до
#: классификации читается как pending.
MODERATION_MAP = {"submitted": "pending", "ok": "ok", "flagged": "flagged"}


def _answers_of(row) -> list[dict]:
    try:
        data = json.loads(row["answers_json"] or "[]")
    except (TypeError, ValueError):
        return []
    return data if isinstance(data, list) else []


def _nps_of(row) -> int | None:
    for entry in _answers_of(row):
        if entry.get("question_code") == "nps":
            try:
                return int(entry.get("score"))
            except (TypeError, ValueError):
                return None
    return None


def _choice_of(row, question: str) -> str | None:
    for entry in _answers_of(row):
        if entry.get("question_code") == question:
            return entry.get("choice")
    return None


async def summary(db, *, days: int) -> dict:
    """NPS-сводка и распределения (R6): promoters 9-10, detractors 0-6.

    Окно days применяется ко всем счётчикам (канон _ago: ISO-строка
    параметром, created_at — TEXT). Response rate — заполнившие /
    получившие приглашение (deliveries kind='feedback_survey',
    key='day7_v1').
    """
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    cur = await db.execute(
        "SELECT COUNT(*) n, "
        "SUM(CASE WHEN EXISTS (SELECT 1 FROM jsonb_array_elements("
        "COALESCE(answers_json::jsonb, '[]'::jsonb)) a "
        "WHERE a->>'question_code'='nps') THEN 1 ELSE 0 END) nps_n "
        "FROM feedback_responses WHERE survey_code=:code AND created_at>=:since",
        {"code": SURVEY_CODE, "since": since})
    row = await cur.fetchone()
    total = int(row["n"] or 0)
    nps_n = int(row["nps_n"] or 0)

    promoters = passives = detractors = 0
    if nps_n:
        cur = await db.execute(
            "SELECT (a->>'score')::int score, COUNT(*) c "
            "FROM feedback_responses, jsonb_array_elements("
            "COALESCE(answers_json::jsonb, '[]'::jsonb)) a "
            "WHERE survey_code=:code AND created_at>=:since "
            "AND a->>'question_code'='nps' "
            "GROUP BY 1", {"code": SURVEY_CODE, "since": since})
        dist = {int(r["score"]): int(r["c"]) for r in await cur.fetchall()}
        promoters = sum(dist.get(s, 0) for s in (9, 10))
        passives = sum(dist.get(s, 0) for s in (7, 8))
        detractors = sum(dist.get(s, 0) for s in range(0, 7))

    invited = 0
    cur = await db.execute(
        "SELECT COUNT(*) n FROM deliveries WHERE kind='feedback_survey' "
        "AND key=:key AND created_at>=:since",
        {"key": SURVEY_CODE, "since": since})
    invited = int((await cur.fetchone())["n"] or 0)

    distributions = {}
    for question, options in CHOICES.items():
        cur = await db.execute(
            "SELECT a->>'choice' choice, COUNT(*) c "
            "FROM feedback_responses, jsonb_array_elements("
            "COALESCE(answers_json::jsonb, '[]'::jsonb)) a "
            "WHERE survey_code=:code AND created_at>=:since "
            "AND a->>'question_code'=:q "
            "GROUP BY 1", {"code": SURVEY_CODE, "q": question, "since": since})
        counts = {r["choice"]: int(r["c"]) for r in await cur.fetchall()}
        distributions[question] = [
            {"choice": option, "count": counts.get(option, 0)}
            for option in options]

    nps = round(100 * (promoters - detractors) / nps_n) if nps_n else None
    return {
        "survey_code": SURVEY_CODE,
        "window_days": days,
        "total_responses": total,
        "invited": invited,
        "response_rate_pct": round(100 * total / invited, 1) if invited else None,
        "nps": {"score": nps, "nps_responses": nps_n,
                "promoters": promoters, "passives": passives,
                "detractors": detractors},
        "distributions": distributions,
    }


async def list_responses(db, *, days: int, nps_min: int | None,
                         nps_max: int | None, question: str | None,
                         choice: str | None, moderation: str | None,
                         text_query: str | None, limit: int,
                         offset: int) -> tuple[list[dict], int]:
    """Страница отзывов с фильтрами R6 (дата, NPS-диапазон, вопрос+вариант,
    модерация, поиск по свободному тексту). Free text — только здесь,
    CSV-экспорт его не выгружает.

    Возвращает (items, total) — total по тем же фильтрам без лимита.
    """
    conditions = ["r.survey_code=:code"]
    params: dict = {"code": SURVEY_CODE}

    # Дни: created_at — ISO-текст (TEXT-колонка), сравниваем строкой через
    # ISO-параметр (канон _ago из analytics.py; timestamp-сравнение упало бы
    # "operator does not exist: text >= timestamptz").
    if days:
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        conditions.append("r.created_at >= :since")
        params["since"] = since
    if nps_min is not None:
        conditions.append("EXISTS (SELECT 1 FROM jsonb_array_elements("
                          "COALESCE(r.answers_json::jsonb, '[]'::jsonb)) a "
                          "WHERE a->>'question_code'='nps' "
                          "AND (a->>'score')::int >= :nps_min)")
        params["nps_min"] = nps_min
    if nps_max is not None:
        conditions.append("EXISTS (SELECT 1 FROM jsonb_array_elements("
                          "COALESCE(r.answers_json::jsonb, '[]'::jsonb)) a "
                          "WHERE a->>'question_code'='nps' "
                          "AND (a->>'score')::int <= :nps_max)")
        params["nps_max"] = nps_max
    if question and choice:
        conditions.append("EXISTS (SELECT 1 FROM jsonb_array_elements("
                          "COALESCE(r.answers_json::jsonb, '[]'::jsonb)) a "
                          "WHERE a->>'question_code'=:question "
                          "AND a->>'choice'=:choice)")
        params["question"] = question
        params["choice"] = choice
    if moderation:
        # 'pending' соответствует дефолтному 'submitted' (см. MODERATION_MAP).
        db_status = {v: k for k, v in MODERATION_MAP.items()}.get(moderation)
        if db_status:
            conditions.append("r.status=:status")
            params["status"] = db_status
    if text_query:
        conditions.append("r.free_text ILIKE :text_query")
        params["text_query"] = f"%{text_query}%"

    where = " AND ".join(conditions)
    cur = await db.execute(
        f"SELECT COUNT(*) n FROM feedback_responses r WHERE {where}", params)
    total = int((await cur.fetchone())["n"] or 0)

    params["limit"] = limit
    params["offset"] = offset
    cur = await db.execute(
        f"SELECT r.id, r.tg_id, r.survey_code, r.answers_json, r.free_text, "
        f"r.status, r.bonus_granted, r.created_at, u.name user_name, "
        f"u.sub_level, u.status user_status "
        f"FROM feedback_responses r LEFT JOIN users u ON u.tg_id=r.tg_id "
        f"WHERE {where} ORDER BY r.created_at DESC, r.id DESC "
        f"LIMIT :limit OFFSET :offset", params)
    items = []
    for row in await cur.fetchall():
        items.append({
            "id": int(row["id"]),
            "tg_id": int(row["tg_id"]),
            "user_name": row["user_name"],
            "sub_level": row["sub_level"],
            "user_status": row["user_status"],
            "created_at": row["created_at"],
            "answers": _answers_of(row),
            "nps": _nps_of(row),
            "free_text": row["free_text"],
            "moderation": MODERATION_MAP.get(row["status"], "pending"),
            "bonus_granted": bool(row["bonus_granted"]),
        })
    return items, total


async def export_rows(db, *, days: int) -> list[dict]:
    """Агрегаты для CSV (R8): по каждому отзыву — категориальные ответы и NPS.
    Free text НЕ входит (текст не выгружается без явного разрешения владельца).

    Строка = отзыв: tg_id, дата, NPS, choice по каждому категориальному
    вопросу, модерация-флаг, bonus_granted. Окно days — как в summary.
    """
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    cur = await db.execute(
        "SELECT r.id, r.tg_id, r.answers_json, r.status, r.bonus_granted, "
        "r.created_at FROM feedback_responses r "
        "WHERE r.survey_code=:code AND r.created_at>=:since "
        "ORDER BY r.created_at DESC",
        {"code": SURVEY_CODE, "since": since})
    rows = []
    for row in await cur.fetchall():
        answers = {a.get("question_code"): a for a in _answers_of(row)}
        item = {
            "tg_id": int(row["tg_id"]),
            "created_at": row["created_at"],
            "nps": None,
            "moderation": MODERATION_MAP.get(row["status"], "pending"),
            "bonus_granted": 1 if row["bonus_granted"] else 0,
        }
        for question in CHOICES:
            item[question] = (answers.get(question) or {}).get("choice") or ""
        nps = (answers.get("nps") or {}).get("score")
        item["nps"] = nps if nps is not None else ""
        rows.append(item)
    return rows
