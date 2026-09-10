"""Публичное read-only API shared context (BUS-810, gap G-12).

Новый UI (волна A) показывает панель «Память о пользователе» (continuity),
читая слой shared context напрямую: события-рекомендации между агентами и
кэшированные транзитные снапшоты. Owner-scope по tg_id аутентифицированной
клиентки: чужие данные недостижимы по контракту — параметр tg_id в API не
существует, фильтр ставится на уровне SQL-запроса из auth-зависимости.

Пишущая логика слоя остаётся в `app/core/shared_context.py` и здесь не
дублируется: роутер только читает.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from ..contracts.memory import (
    SharedContextEventList,
    SharedContextSnapshotList,
)
from ..deps import confirmed_age_user, get_db, rate_limit

router = APIRouter(prefix="/api/memory", tags=["memory"])


def _event_view(row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "event_type": row["event_type"],
        "agent": row["agent"],
        "content": row["content"],
        "source_ref": row["source_ref"] or "",
        "created_at": row["created_at"],
        "expires_at": row["expires_at"],
    }


def _snapshot_view(row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "snapshot_type": row["snapshot_type"],
        "snapshot_key": row["snapshot_key"],
        "created_at": row["created_at"],
        "expires_at": row["expires_at"],
        "payload": _safe_json(row["payload_json"]),
    }


def _safe_json(raw: Any) -> dict[str, Any]:
    """Повреждённый payload отдаём как {} — read-only API не должен падать."""
    import json
    try:
        value = json.loads(raw or "{}")
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


@router.get("/context", dependencies=[Depends(rate_limit("read"))],
            response_model=SharedContextEventList)
async def memory_context(
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user=Depends(confirmed_age_user),
    db=Depends(get_db),
):
    """События shared context текущего пользователя, новые впереди.

    Fail-closed: у пользователя без памяти пусто (рекомендации пишутся только
    при consent), но ответ остаётся 200 с пустым списком — отсутствие данных
    не ошибка.
    """
    cur = await db.execute(
        "SELECT id, event_type, agent, content, source_ref, created_at, expires_at "
        "FROM shared_context_events WHERE tg_id=:tg_id "
        "ORDER BY created_at DESC, id DESC LIMIT :limit_ OFFSET :offset_",
        {"tg_id": user["tg_id"], "limit_": limit, "offset_": offset},
    )
    return {
        "events": [_event_view(r) for r in await cur.fetchall()],
        "limit": limit,
        "offset": offset,
        "owner_scoped": True,
    }


@router.get("/snapshots", dependencies=[Depends(rate_limit("read"))],
            response_model=SharedContextSnapshotList)
async def memory_snapshots(
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user=Depends(confirmed_age_user),
    db=Depends(get_db),
):
    """Снапшоты shared context текущего пользователя, новые впереди.

    Снапшоты без истёкшего TTL отдавались агентам и теперь отдаются UI;
    payload — уже разобранный JSON (см. `_safe_json`).
    """
    cur = await db.execute(
        "SELECT id, snapshot_type, snapshot_key, payload_json, created_at, expires_at "
        "FROM shared_context_snapshots WHERE tg_id=:tg_id "
        "ORDER BY created_at DESC, id DESC LIMIT :limit_ OFFSET :offset_",
        {"tg_id": user["tg_id"], "limit_": limit, "offset_": offset},
    )
    return {
        "snapshots": [_snapshot_view(r) for r in await cur.fetchall()],
        "limit": limit,
        "offset": offset,
        "owner_scoped": True,
    }
