"""Hard outer deadline for public agent requests.

The legacy runtime may perform a second quality-regeneration pass. This guard makes
that whole logical request share one wall-clock budget, so a retry cannot double the
profile timeout. On timeout we degrade to the existing deterministic offline answer.
"""
from __future__ import annotations

import asyncio
import logging

from . import runtime

log = logging.getLogger("oracle.agents")


async def answer(*args, **kwargs) -> str:
    """Run the canonical runtime answer under one wall-clock deadline."""
    agent = kwargs.get("agent") or runtime.DEFAULT_AGENT
    db = args[0] if args else kwargs.get("db")
    user = args[1] if len(args) > 1 else kwargs.get("user")
    spec = runtime.get(agent)
    timeout = max(1.0, float(spec.timeout_s))
    try:
        return await asyncio.wait_for(runtime.answer(*args, **kwargs), timeout=timeout)
    except asyncio.TimeoutError:
        log.warning("agent %s exceeded outer request deadline %.1fs — offline fallback", spec.code, timeout)
        chart = runtime.users_repo.chart_of(user)
        memories = (
            await runtime.dialog_repo.get_memories(db, user["tg_id"], limit=5)
            if bool(user["memory_enabled"]) else []
        )
        question = args[2] if len(args) > 2 else kwargs.get("question", "")
        return runtime.offline_answer(user, question, chart, memories, spec)
