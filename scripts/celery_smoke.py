from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://oracle_test:oracle_test@127.0.0.1:5432/oracle_test",
)
os.environ.setdefault("REDIS_URL", "redis://127.0.0.1:6379/15")
os.environ.setdefault("CELERY_ENABLED", "1")
os.environ.setdefault("LLM_PROVIDER", "off")
os.environ.setdefault("ADMIN_ID", "900001")

from app.data.session import connect
from app.repo import jobs as jobs_repo, users
from app.services.jobs import enqueue_chat


async def main() -> None:
    db = await connect(seed=False)
    try:
        user = await users.ensure(db, 990001, "Celery Test", "celery_test")
        job = await enqueue_chat(db, user, "Celery offline smoke", agent="oracle")
        print("enqueued", job)
        for _ in range(60):
            current = await jobs_repo.get(db, job["job_id"])
            print("status", current["status"] if current else None)
            if current and current["status"] in {"succeeded", "failed"}:
                print("result", current)
                if current["status"] != "succeeded":
                    raise SystemExit(1)
                return
            await asyncio.sleep(0.5)
        raise TimeoutError("Celery job did not finish in 30 seconds")
    finally:
        await db.close()


asyncio.run(main())
