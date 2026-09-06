"""Day-7 опрос (BUS-180): приём ответов, анти-абьюз, бонус-грант.

Контракт (BUS-170 rev 5 §5, словарь событий 8d33f33):
- POST /api/feedback — одна транзакция: INSERT feedback_responses + грант
  crystal_lot 40✦ (source='review_bonus', 90d) + события воронки. Повторный
  POST отклоняется UNIQUE (tg_id, survey_code) на уровне БД → 409.
- Гейты бонуса, не подачи: активность ≥3/7 дней ИЛИ ≥5 ключевых событий;
  свободный текст ≥50 символов. Не пройдены — ответы сохраняются, бонус нет
  (экран благодарности без обещания кристаллов — BUS-179 §2).
- События: feedback_survey_completed (once на tg_id+survey_code,
  bonus_granted + question_count) → survey_grant_issued (только при гранте).
  Score/текст в события не пишутся (privacy-правило словаря).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ...data.session import transaction
from ...repo import analytics as analytics_repo
from ...repo import feedback as feedback_repo
from ...repo import monetization
from ...services.eligibility import require_eligible_user
from ..deps import confirmed_age_user, get_db, rate_limit

router = APIRouter(prefix="/api", tags=["feedback"])


class FeedbackAnswerIn(BaseModel):
    """Один ответ: категориальный код или score; текст — опционален.

    Нормализация по allowlist'у — в repo (константы схемы); здесь отсекаем
    заведомый мусор и размер на границе.
    """
    question_code: str = Field(min_length=1, max_length=32,
                               pattern=r"^[a-z0-9_]+$")
    choice: str | None = Field(default=None, max_length=32,
                               pattern=r"^[a-z0-9_]*$")
    score: int | None = Field(default=None, ge=0, le=10)
    text: str | None = Field(default=None, max_length=4000)


class FeedbackIn(BaseModel):
    answers: list[FeedbackAnswerIn] = Field(min_length=1, max_length=5)
    survey_code: str = Field(default=feedback_repo.SURVEY_CODE,
                             pattern=r"^day7_v\d+$")


@router.post("/feedback", dependencies=[Depends(rate_limit("write"))])
async def submit_feedback(item: FeedbackIn,
                          user=Depends(confirmed_age_user),
                          db=Depends(get_db)):
    """Принимает ответы day-7 опроса; бонус — в той же транзакции."""
    require_eligible_user(user, operation="feedback")

    if item.survey_code != feedback_repo.SURVEY_CODE:
        # day7_v2 и дальше — новые вопросы/коды: принимаются отдельным
        # контрактом, старый allowlist на них не отвечает (BUS-167 §2).
        raise HTTPException(422, {"code": "survey_version_unknown",
                                  "message": "неизвестная версия опроса"})

    answers, free_text = feedback_repo.normalize_answers(
        [a.model_dump() for a in item.answers])
    if not answers:
        raise HTTPException(422, {"code": "no_valid_answers",
                                  "message": "ни один ответ не прошёл валидацию"})
    answers_json = json.dumps(answers, ensure_ascii=False)

    # Гейты бонуса — до транзакции (read-only), один бонус за жизнь.
    active_week = await feedback_repo.activity_gate(db, user["tg_id"])
    enough_text = len(free_text) >= feedback_repo.MIN_REVIEW_CHARS
    bonus_granted = active_week and enough_text \
        and not await feedback_repo.bonus_issued_before(db, user["tg_id"])

    now = datetime.now(timezone.utc)
    expires_at = None
    lot_id = None
    try:
        async with transaction(db):
            if bonus_granted:
                # Порядок важен: грант до INSERT ответов — конфликт UNIQUE
                # на ответах откатит и лот (не оставит лот без отзыва).
                lot_id = await monetization.crystal_lot(
                    db, user["tg_id"], source=feedback_repo.BONUS_SOURCE,
                    qty=feedback_repo.BONUS_CRYSTALS,
                    valid_days=feedback_repo.BONUS_VALID_DAYS)
                expires_at = feedback_repo.grant_expires_at(now)
            await feedback_repo.submit(
                db, user["tg_id"], answers_json=answers_json,
                free_text=free_text, bonus_granted=bonus_granted,
                bonus_lot_id=lot_id)
    except feedback_repo.SurveyAlreadyCompleted:
        raise HTTPException(409, {"code": "survey_already_completed",
                                  "message": "опрос уже пройден"}) from None

    # События воронки — после фиксации строки. question_count —
    # категориальный prop; score/текст не пишутся (словарь 8d33f33).
    await analytics_repo.track_once(
        db, "feedback_survey_completed", user["tg_id"],
        props={"survey_code": item.survey_code,
               "bonus_granted": "true" if bonus_granted else "false",
               "question_count": len(answers)},
        surface="miniapp")
    if bonus_granted:
        await analytics_repo.track_once(
            db, "survey_grant_issued", user["tg_id"],
            props={"survey_code": item.survey_code,
                   "bonus_kind": feedback_repo.BONUS_KIND,
                   "amount": feedback_repo.BONUS_CRYSTALS,
                   "expires_at": expires_at},
            surface="miniapp")

    return {"ok": True, "bonus_granted": bonus_granted}
