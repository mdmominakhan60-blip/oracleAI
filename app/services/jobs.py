"""Public service for enqueueing and reading background jobs."""
from __future__ import annotations

from kombu.utils.uuid import uuid

from ..config import settings
from ..repo import jobs as jobs_repo
from ..queue import celery_app


class QueueUnavailable(RuntimeError):
    pass


async def enqueue_chat(db, user, text: str, *, agent: str = "oracle",
                       thread_id: int | None = None,
                       allow_paid: bool = False) -> dict:
    if not settings.celery_enabled:
        raise QueueUnavailable("background queue is disabled")
    task_id = uuid()
    payload = {"agent": agent, "thread_id": thread_id, "text": text}
    await jobs_repo.create(db, task_id, "llm.chat", tg_id=user["tg_id"], payload=payload)
    try:
        celery_app.send_task(
            "oracle.llm.chat",
            args=[task_id, user["tg_id"], text],
            kwargs={"agent": agent, "thread_id": thread_id,
                    "allow_paid": allow_paid},
            task_id=task_id,
            queue="llm",
        )
    except Exception as exc:  # noqa: BLE001
        await jobs_repo.mark_failed(db, task_id, str(exc))
        raise QueueUnavailable("background queue is unavailable") from exc
    return {"job_id": task_id, "status": "queued", "kind": "llm.chat"}


async def enqueue_maintenance(db) -> dict:
    if not settings.celery_enabled:
        raise QueueUnavailable("background queue is disabled")
    task_id = uuid()
    await jobs_repo.create(db, task_id, "maintenance")
    try:
        celery_app.send_task("oracle.maintenance", args=[task_id], task_id=task_id,
                             queue="maintenance")
    except Exception as exc:  # noqa: BLE001
        await jobs_repo.mark_failed(db, task_id, str(exc))
        raise QueueUnavailable("background queue is unavailable") from exc
    return {"job_id": task_id, "status": "queued", "kind": "maintenance"}


async def get_for_user(db, task_id: str, tg_id: int):
    job = await jobs_repo.get(db, task_id)
    if not job or job.get("tg_id") != tg_id:
        return None
    return job
