"""Практики и мантры: каталог, старт, отметка дня, прогресс."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from ...services import analytics
from ...services import practices as practices_svc
from ..deps import confirmed_age_user, get_db, rate_limit

router = APIRouter(prefix="/api/practices", tags=["practices"])


@router.get("")
async def catalog(category: str | None = Query(default=None),
                  user=Depends(confirmed_age_user), db=Depends(get_db)):
    """Каталог с её прогрессом. Идущие практики — первыми."""
    return {
        "categories": await practices_svc.categories(),
        "items": await practices_svc.list_for_user(db, user, category=category),
    }


@router.get("/{code}")
async def one(code: str, user=Depends(confirmed_age_user), db=Depends(get_db)):
    items = await practices_svc.list_for_user(db, user)
    item = next((p for p in items if p["code"] == code), None)
    if not item:
        raise HTTPException(404, "такой практики нет")
    return item


@router.post("/{code}/start", dependencies=[Depends(rate_limit("write"))])
async def start(code: str, user=Depends(confirmed_age_user), db=Depends(get_db)):
    try:
        item = await practices_svc.start(db, user, code)
    except LookupError as e:
        raise HTTPException(404, str(e)) from e
    await analytics.track(db, "practice_start", user["tg_id"],
                          props={"code": code}, surface="miniapp")
    return item


@router.post("/{code}/done", dependencies=[Depends(rate_limit("write"))])
async def done(code: str, user=Depends(confirmed_age_user), db=Depends(get_db)):
    """Отметка дня. Повторная за сутки ничего не меняет — так и отвечаем."""
    try:
        result = await practices_svc.mark_done(db, user, code)
    except LookupError as e:
        raise HTTPException(404, str(e)) from e
    if not result["already"]:
        await analytics.track(db, "practice_done", user["tg_id"],
                              props={"code": code, "streak": result["streak"],
                                     "finished": result["finished"]},
                              surface="miniapp")
        await analytics.track_once(
            db, analytics.E_FIRST_RITUAL, user["tg_id"],
            props={"surface_action": "practice_done"}, surface="miniapp",
        )
    return result


@router.post("/{code}/stop", dependencies=[Depends(rate_limit("write"))])
async def stop(code: str, user=Depends(confirmed_age_user), db=Depends(get_db)):
    stopped = await practices_svc.stop(db, user, code)
    if stopped:
        await analytics.track(db, "practice_stop", user["tg_id"],
                              props={"code": code}, surface="miniapp")
    return {"ok": stopped}
