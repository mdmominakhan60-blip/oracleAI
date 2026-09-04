from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ...core import agents
from ...services.repo_gateway import jobs as jobs_repo
from ...services import jobs as jobs_service
from ..contracts.chat import AskIn
from ..deps import confirmed_age_user, current_user, get_db, rate_limit

router = APIRouter(prefix="/api/jobs", tags=["background-jobs"])


def _public_job(job: dict) -> dict:
    """Return status/result metadata without echoing the submitted prompt."""
    allowed = (
        "id", "kind", "status", "result", "error", "attempts", "available_at",
        "started_at", "finished_at", "created_at", "updated_at",
    )
    return {key: job.get(key) for key in allowed}


@router.post("/chat/{agent}", status_code=status.HTTP_202_ACCEPTED,
             dependencies=[Depends(rate_limit("llm"))])
async def enqueue_chat(agent: str, item: AskIn, thread_id: int | None = Query(default=None),
                       user=Depends(confirmed_age_user), db=Depends(get_db)):
    if agent not in agents.codes():
        raise HTTPException(404, "нет такого собеседника")
    try:
        return await jobs_service.enqueue_chat(
            db, user, item.text, agent=agent, thread_id=thread_id,
            allow_paid=item.allow_paid)
    except jobs_service.QueueUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("")
async def list_jobs(limit: int = Query(default=20, ge=1, le=100),
                    user=Depends(current_user), db=Depends(get_db)):
    rows = await jobs_repo.list_for_user(db, user["tg_id"], limit=limit)
    return [_public_job(row) for row in rows]


@router.get("/{task_id}")
async def get_job(task_id: str, user=Depends(current_user), db=Depends(get_db)):
    job = await jobs_service.get_for_user(db, task_id, user["tg_id"])
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return _public_job(job)
