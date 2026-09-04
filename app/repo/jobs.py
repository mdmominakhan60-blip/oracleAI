"""Durable status records for Celery jobs.

Redis is the broker/result transport; task_jobs is the user-visible audit/status
projection stored in the primary database so status survives worker restarts and
Redis result expiry.
"""
from __future__ import annotations

import json
from typing import Any

from ..data.session import transaction, utcnow

TERMINAL_STATUSES = frozenset({"succeeded", "failed", "rejected"})


async def create(db, task_id: str, kind: str, *, tg_id: int | None = None,
                 payload: dict[str, Any] | None = None) -> None:
    now = utcnow()
    async with transaction(db):
        await db.execute(
            "INSERT INTO task_jobs "
            "(id, kind, status, tg_id, payload_json, attempts, available_at, "
            "created_at, updated_at) VALUES(:id, :kind, 'queued', :tg_id, "
            ":payload_json, 0, :available_at, :created_at, :updated_at) "
            "ON CONFLICT (id) DO NOTHING",
            {"id": task_id, "kind": kind, "tg_id": tg_id,
             "payload_json": json.dumps(payload, ensure_ascii=False) if payload else None,
             "available_at": now, "created_at": now, "updated_at": now})


async def mark_running(db, task_id: str) -> bool:
    async with transaction(db):
        cur = await db.execute(
            "UPDATE task_jobs SET status='running', attempts=attempts+1, "
            "started_at=COALESCE(started_at, :started_at), updated_at=:updated_at "
            "WHERE id=:id AND status NOT IN ('succeeded','failed','rejected')",
            {"started_at": utcnow(), "updated_at": utcnow(), "id": task_id})
        return bool(cur.rowcount)


async def mark_retry(db, task_id: str, error: str, available_at: str) -> None:
    async with transaction(db):
        await db.execute(
            "UPDATE task_jobs SET status='retry', error=:error, available_at=:available_at, "
            "updated_at=:updated_at WHERE id=:id "
            "AND status NOT IN ('succeeded','failed','rejected')",
            {"error": error[:1000], "available_at": available_at,
             "updated_at": utcnow(), "id": task_id})


async def mark_succeeded(db, task_id: str, result: Any = None) -> None:
    async with transaction(db):
        await db.execute(
            "UPDATE task_jobs SET status='succeeded', result_json=:result_json, "
            "error=NULL, finished_at=:finished_at, updated_at=:updated_at "
            "WHERE id=:id AND status NOT IN ('succeeded','failed','rejected')",
            {"result_json": json.dumps(result, ensure_ascii=False) if result is not None else None,
             "finished_at": utcnow(), "updated_at": utcnow(), "id": task_id})


async def mark_rejected(db, task_id: str, code: str, reason: str) -> None:
    """Persist a non-retryable policy rejection without storing user input."""
    error = f"{code}: {reason}"[:2000]
    async with transaction(db):
        await db.execute(
            "UPDATE task_jobs SET status='rejected', result_json=NULL, error=:error, "
            "finished_at=:finished_at, updated_at=:updated_at WHERE id=:id "
            "AND status NOT IN ('succeeded','failed','rejected')",
            {"error": error, "finished_at": utcnow(), "updated_at": utcnow(),
             "id": task_id},
        )


async def mark_failed(db, task_id: str, error: str) -> None:
    async with transaction(db):
        await db.execute(
            "UPDATE task_jobs SET status='failed', error=:error, "
            "finished_at=:finished_at, updated_at=:updated_at WHERE id=:id "
            "AND status NOT IN ('succeeded','failed','rejected')",
            {"error": error[:2000], "finished_at": utcnow(),
             "updated_at": utcnow(), "id": task_id})


async def get(db, task_id: str):
    cur = await db.execute(
        "SELECT * FROM task_jobs WHERE id=:id", {"id": task_id})
    row = await cur.fetchone()
    if not row:
        return None
    item = dict(row)
    for field in ("payload_json", "result_json"):
        raw = item.get(field)
        if raw:
            try:
                item[field.removesuffix("_json")] = json.loads(raw)
            except (TypeError, ValueError):
                item[field.removesuffix("_json")] = None
        else:
            item[field.removesuffix("_json")] = None
    return item


async def list_for_user(db, tg_id: int, *, limit: int = 20) -> list[dict]:
    limit = max(1, min(limit, 100))
    cur = await db.execute(
        "SELECT id, kind, status, result_json, error, attempts, available_at, "
        "started_at, finished_at, created_at, updated_at FROM task_jobs "
        "WHERE tg_id=:tg_id ORDER BY created_at DESC LIMIT :limit",
        {"tg_id": tg_id, "limit": limit})
    rows = []
    for row in await cur.fetchall():
        item = dict(row)
        raw = item.pop("result_json", None)
        try:
            item["result"] = json.loads(raw) if raw else None
        except (TypeError, ValueError):
            item["result"] = None
        rows.append(item)
    return rows
