"""Realtime operational log endpoints for the admin monitoring screen."""
from __future__ import annotations

import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse

from ...core.log_stream import log_stream
from ..deps import rate_limit, require

router = APIRouter(
    prefix="/api/admin/logs",
    tags=["admin-logs"],
    dependencies=[Depends(rate_limit("admin")), Depends(require("dashboard"))],
)


@router.get("")
async def recent_logs(
    limit: int = Query(default=200, ge=1, le=500),
    level: str | None = Query(default=None, max_length=10),
    logger_name: str | None = Query(default=None, alias="logger", max_length=120),
    query: str | None = Query(default=None, max_length=120),
):
    entries = log_stream.snapshot(
        limit=limit,
        level=level,
        logger_name=logger_name,
        query=query,
    )
    return {
        "entries": entries,
        "count": len(entries),
        "buffer_size": log_stream.max_entries,
        "stream": "sse",
    }


@router.get("/stream")
async def stream_logs(
    request: Request,
    level: str | None = Query(default=None, max_length=10),
    logger_name: str | None = Query(default=None, alias="logger", max_length=120),
    query: str | None = Query(default=None, max_length=120),
):
    async def events() -> AsyncIterator[str]:
        yield "event: ready\ndata: {\"stream\":\"admin-logs\"}\n\n"
        async for entry in log_stream.stream(
            level=level,
            logger_name=logger_name,
            query=query,
        ):
            if await request.is_disconnected():
                break
            if entry is None:
                yield ": keep-alive\n\n"
                continue
            yield f"event: log\ndata: {json.dumps(entry, ensure_ascii=False, separators=(',', ':'))}\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-store",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
