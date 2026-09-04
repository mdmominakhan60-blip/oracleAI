"""Таро: каталог раскладов, раздача, трактовка, история, отметка «сбылось»."""
from __future__ import annotations

import json

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ...core import tarot
from ...services.repo_gateway import readings
from ...services import catalog
from ...services import chat as chat_svc
from ..common.errors import access_denied
from ..deps import confirmed_age_user, get_db, rate_limit

router = APIRouter(prefix="/api/tarot", tags=["tarot"])


@router.get("/spreads")
async def spreads(user=Depends(confirmed_age_user), db=Depends(get_db)):
    """Витрина раскладов: что входит в тариф, что куплено, что стоит денег."""
    return await catalog.spread_list(db, user)


@router.get("/spreads/full")
async def spreads_full(user=Depends(confirmed_age_user)):
    """Все встроенные расклады с `guide` — пояснения для страницы выбора.

    `/spreads` (витрина) не несёт `guide`, а здесь он нужен фронту, чтобы
    показать клиентке, что именно покажет расклад, до того как она заплатит.
    """
    fields = ("title", "positions", "tier", "emoji", "hint", "guide")
    return [{"code": code, **{f: item.get(f) for f in fields}}
            for code, item in tarot.SPREADS.items()]


class DrawIn(BaseModel):
    question: str | None = None
    deck: str | None = None


@router.post("/draw", dependencies=[Depends(rate_limit("write"))])
async def draw(spread: str = Query(default="three"), item: DrawIn | None = None,
               question: str = Query(default=""),
               user=Depends(confirmed_age_user), db=Depends(get_db)):
    """Тянет карты. Трактовка — вторым запросом, после анимации переворота.

    `question` — формулировка клиентки «что спросить у карт»: сохраняется в
    раскладе и на трактовке читается моделью (карты отвечают на конкретное).
    Принимаем и из query, и из тела — фронтенд шлёт в теле, старые вызовы в query.
    `deck` — выбранная колода (tarot|lenormand): сохраняется в раскладе, чтобы
    история/воспроизведение использовали ту же художественную школу.
    """
    q = (item.question if item and item.question else question or "").strip() or None
    deck = (item.deck if item and item.deck else "tarot").strip() or "tarot"
    if deck not in ("tarot", "lenormand"):
        deck = "tarot"
    try:
        result = await chat_svc.draw(db, user, spread, surface="miniapp",
                                     question=q, deck=deck)
    except chat_svc.ChatDenied as e:
        raise access_denied(e.verdict, lang=user["lang"] or "ru") from e
    # короткое описание расклада для страницы выбора / карточки результата
    result["guide"] = tarot.spread(result["spread"]).get("guide", "")
    return result


@router.post("/interpret/{reading_id}", dependencies=[Depends(rate_limit("llm"))])
async def interpret(reading_id: int, user=Depends(confirmed_age_user), db=Depends(get_db)):
    try:
        answer = await chat_svc.interpret(db, user, reading_id, surface="miniapp")
    except LookupError as e:
        raise HTTPException(404, str(e)) from e
    return {"answer": answer}


@router.get("/history")
async def history(user=Depends(confirmed_age_user), db=Depends(get_db)):
    return await readings.recent_readings(db, user["tg_id"], limit=30)


@router.get("/history/{reading_id}")
async def history_item(reading_id: int, user=Depends(confirmed_age_user), db=Depends(get_db)):
    row = await readings.get_reading(db, reading_id, user["tg_id"])
    if not row or not row["answer"]:
        raise HTTPException(404, "расклад не найден")
    cards = json.loads(row["cards_json"] or "[]")
    deck = row.get("deck") or "tarot"
    return {
        "id": row["id"], "spread": row["spread"], "question": row["question"],
        "answer": row["answer"], "outcome": row["outcome"],
        "created_at": row["created_at"], "cards": cards, "deck": deck,
        "ledger": tarot.reading_ledger(cards, row["spread"] or "three",
                                       deck=deck),
    }


@router.get("/stats")
async def stats(user=Depends(confirmed_age_user), db=Depends(get_db)):
    """Что сбывалось: счётчик отметок «сбылось / частично / нет»."""
    return await readings.outcome_stats(db, user["tg_id"])


class OutcomeIn(BaseModel):
    # Аудит API-012: исход — закрытое множество, а не произвольная строка.
    outcome: Literal["came_true", "partly", "no"]


@router.post("/outcome/{reading_id}", dependencies=[Depends(rate_limit("write"))])
async def set_outcome(reading_id: int, item: OutcomeIn, user=Depends(confirmed_age_user),
                      db=Depends(get_db)):
    """Отметка «сбылось». Это и обратная связь, и доказательство ценности."""
    if not await readings.set_outcome(db, reading_id, user["tg_id"], item.outcome):
        raise HTTPException(400, "не удалось отметить расклад")
    return {"ok": True}
