"""Authenticated API routes for structured astrology product paths."""
from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, Depends, HTTPException

from ...core import chart_products
from ...services.repo_gateway import readings, users
from ..contracts.chart_products import CompositeIn, ReturnsIn, SynastryIn, TransitIn
from ..deps import active_user, get_db, rate_limit

router = APIRouter(prefix="/api", tags=["chart-products"])
log = logging.getLogger("oracle.chart_products")



def _product_error(exc: chart_products.ChartProductError) -> HTTPException:
    return HTTPException(
        status_code=422,
        detail={"code": exc.code, "message": exc.message, "missing": exc.missing},
    )



def _partner_chart(partner) -> dict:
    try:
        return json.loads(partner["chart_json"] or "{}")
    except (TypeError, ValueError):
        return {}



def _partner_not_found() -> HTTPException:
    # Do not distinguish missing records from another user's records.
    return HTTPException(
        status_code=404,
        detail={
            "code": "partner_not_found",
            "message": "Сохранённый партнёр не найден.",
            "missing": [],
        },
    )


@router.post("/synastry")
async def calculate_synastry(
    payload: SynastryIn,
    db=Depends(get_db),
    user=Depends(active_user),
    _rate=Depends(rate_limit("read")),
):
    """Return the structured exact synastry for one saved partner."""
    partner = await readings.get_partner(db, payload.partner_id, user["tg_id"])
    if not partner:
        raise _partner_not_found()
    try:
        return chart_products.build_synastry_contract(
            users.chart_of(user),
            _partner_chart(partner),
            partner_id=int(partner["id"]),
            partner_label=str(partner["name"] or "Партнёр"),
        )
    except chart_products.ChartProductError as exc:
        raise _product_error(exc) from exc
    except Exception as exc:  # noqa: BLE001
        log.exception("synastry calculation failed: %s", type(exc).__name__)
        raise HTTPException(
            status_code=503,
            detail={
                "code": "calculation_unavailable",
                "message": "Синастрия сейчас недоступна. Попробуйте ещё раз.",
                "missing": [],
            },
        ) from exc


@router.post("/composite")
async def calculate_composite(
    payload: CompositeIn,
    db=Depends(get_db),
    user=Depends(active_user),
    _rate=Depends(rate_limit("read")),
):
    """Return the structured exact composite for one saved partner."""
    partner = await readings.get_partner(db, payload.partner_id, user["tg_id"])
    if not partner:
        raise _partner_not_found()
    try:
        return chart_products.build_composite_contract(
            users.chart_of(user),
            _partner_chart(partner),
            partner_id=int(partner["id"]),
            partner_label=str(partner["name"] or "Партнёр"),
        )
    except chart_products.ChartProductError as exc:
        raise _product_error(exc) from exc
    except Exception as exc:  # noqa: BLE001
        log.exception("composite calculation failed: %s", type(exc).__name__)
        raise HTTPException(
            status_code=503,
            detail={
                "code": "calculation_unavailable",
                "message": "Композит сейчас недоступен. Попробуйте ещё раз.",
                "missing": [],
            },
        ) from exc


@router.post("/transits")
async def calculate_transits(
    payload: TransitIn,
    db=Depends(get_db),
    user=Depends(active_user),
    _rate=Depends(rate_limit("read")),
):
    """Return a deterministic transit snapshot against the saved natal planets."""
    try:
        natal_chart = users.chart_of(user)
        return await asyncio.to_thread(
            chart_products.build_transit_contract,
            natal_chart,
            as_of=payload.as_of,
            clock=payload.time,
        )
    except chart_products.ChartProductError as exc:
        raise _product_error(exc) from exc
    except Exception as exc:  # noqa: BLE001
        log.exception("transit calculation failed: %s", type(exc).__name__)
        raise HTTPException(
            status_code=503,
            detail={
                "code": "calculation_unavailable",
                "message": "Транзиты сейчас недоступны. Попробуйте ещё раз.",
                "missing": [],
            },
        ) from exc


@router.post("/returns")
async def calculate_returns(
    payload: ReturnsIn,
    db=Depends(get_db),
    user=Depends(active_user),
    _rate=Depends(rate_limit("read")),
):
    """Return the exact solar-return event for the owner's saved natal chart."""
    try:
        natal_chart = users.chart_of(user)
        return await asyncio.to_thread(
            chart_products.build_returns_contract,
            natal_chart,
            target_year=payload.year,
            planet_id=payload.planet,
            lat=user["birth_lat"],
            lon=user["birth_lon"],
            tz_name=user["tz"],
        )
    except chart_products.ChartProductError as exc:
        raise _product_error(exc) from exc
    except Exception as exc:  # noqa: BLE001
        log.exception("returns calculation failed: %s", type(exc).__name__)
        raise HTTPException(
            status_code=503,
            detail={
                "code": "calculation_unavailable",
                "message": "Возврат планеты сейчас недоступен. Попробуйте ещё раз.",
                "missing": [],
            },
        ) from exc
