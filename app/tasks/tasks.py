"""Celery task implementations.

Celery executes synchronous callables; each task owns one asyncio loop and one
short-lived application DB handle. No DB connection or event loop is shared across
worker processes.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from celery import Task

from ..config import settings
from ..data.session import connect
from ..repo import jobs as jobs_repo, users
from ..services import analytics, eligibility
from ..queue import celery_app


def _run(awaitable):
    return asyncio.run(awaitable)


def _retry_delay(retries: int) -> int:
    return min(300, 2 ** min(retries + 1, 8))


class OracleTask(Task):
    max_retries = settings.celery_max_retries
    retry_backoff = True
    retry_jitter = True

    def _retry_or_fail(self, task_id: str, exc: Exception):
        retries = self.request.retries
        if retries < self.max_retries:
            delay = _retry_delay(retries)
            available = (datetime.now(timezone.utc)
                         + timedelta(seconds=delay)).isoformat()
            _run(_mark_retry(task_id, str(exc), available))
            raise self.retry(exc=exc, countdown=delay, max_retries=self.max_retries)
        _run(_mark_failed(task_id, str(exc)))
        raise exc


async def _mark_retry(task_id: str, error: str, available_at: str) -> None:
    db = await connect(seed=False)
    try:
        await jobs_repo.mark_retry(db, task_id, error, available_at)
    finally:
        await db.close()


async def _mark_failed(task_id: str, error: str) -> None:
    db = await connect(seed=False)
    try:
        await jobs_repo.mark_failed(db, task_id, error)
    finally:
        await db.close()


async def _chat(task_id: str, tg_id: int, text: str, *, agent: str,
                thread_id: int | None, allow_paid: bool):
    db = await connect(seed=False)
    try:
        claimed = await jobs_repo.mark_running(db, task_id)
        if not claimed:
            existing = await jobs_repo.get(db, task_id)
            if existing and existing["status"] in jobs_repo.TERMINAL_STATUSES:
                return existing.get("result") or {
                    "status": existing["status"],
                    "code": ((existing.get("error") or "").split(":", 1)[0]
                             or existing["status"]),
                }
            raise RuntimeError("job is already running or unavailable")
        user = await users.get(db, tg_id)
        try:
            eligibility.require_eligible_user(user, operation="queued_chat")
        except eligibility.EligibilityDenied as exc:
            await jobs_repo.mark_rejected(db, task_id, exc.code, str(exc))
            return {"status": "rejected", "code": exc.code}
        from ..services import chat as chat_service
        result = await chat_service.ask(
            db, user, text, agent=agent, surface="miniapp",
            allow_paid=allow_paid, thread_id=thread_id)
        await jobs_repo.mark_succeeded(db, task_id, result)
        return result
    finally:
        await db.close()


async def _forecast(task_id: str, tg_id: int):
    db = await connect(seed=False)
    try:
        await jobs_repo.mark_running(db, task_id)
        user = await users.get(db, tg_id)
        if not user:
            raise ValueError("user not found")
        from ..core import agent as agent_core
        result = await agent_core.daily_forecast_cached(db, user)
        output = {"forecast": result}
        await jobs_repo.mark_succeeded(db, task_id, output)
        return output
    finally:
        await db.close()


async def _maintenance(task_id: str):
    db = await connect(seed=False)
    try:
        await jobs_repo.create(db, task_id, "maintenance")
        await jobs_repo.mark_running(db, task_id)
        rolled = await analytics.rollup(db)
        pruned = await analytics.prune(db)
        output = {"rolled_up": bool(rolled), "pruned": pruned}
        await jobs_repo.mark_succeeded(db, task_id, output)
        return output
    finally:
        await db.close()


@celery_app.task(
    bind=True, base=OracleTask, name="oracle.llm.chat", queue="llm", acks_late=True)
def chat_task(self, task_id: str, tg_id: int, text: str, *, agent: str = "oracle",
              thread_id: int | None = None, allow_paid: bool = False):
    try:
        return _run(_chat(task_id, tg_id, text, agent=agent,
                          thread_id=thread_id, allow_paid=allow_paid))
    except Exception as exc:  # noqa: BLE001
        return self._retry_or_fail(task_id, exc)


@celery_app.task(
    bind=True, base=OracleTask, name="oracle.llm.forecast", queue="llm", acks_late=True)
def forecast_task(self, task_id: str, tg_id: int):
    try:
        return _run(_forecast(task_id, tg_id))
    except Exception as exc:  # noqa: BLE001
        return self._retry_or_fail(task_id, exc)


@celery_app.task(
    bind=True, base=OracleTask, name="oracle.maintenance", queue="maintenance", acks_late=True)
def maintenance_task(self, task_id: str | None = None):
    task_id = task_id or self.request.id
    try:
        return _run(_maintenance(task_id))
    except Exception as exc:  # noqa: BLE001
        return self._retry_or_fail(task_id, exc)
