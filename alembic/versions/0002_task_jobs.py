"""Add durable Celery job status projection.

Revision ID: 0002_task_jobs
Revises: 0001_pg_baseline
"""
from __future__ import annotations

from alembic import op

revision = "0002_task_jobs"
down_revision = "0001_pg_baseline"
branch_labels = None
depends_on = None


_TASK_JOBS = """
CREATE TABLE IF NOT EXISTS task_jobs (
    id           TEXT PRIMARY KEY,
    kind         TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'queued', -- queued|running|succeeded|failed|retry|rejected
    tg_id        BIGINT,
    payload_json TEXT,
    result_json  TEXT,
    error        TEXT,
    attempts     INTEGER NOT NULL DEFAULT 0,
    available_at TEXT,
    started_at   TEXT,
    finished_at  TEXT,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
)
"""

_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_task_jobs_status_available "
    "ON task_jobs(status, available_at)",
    "CREATE INDEX IF NOT EXISTS idx_task_jobs_user_created "
    "ON task_jobs(tg_id, created_at DESC)",
)


def upgrade() -> None:
    op.execute(_TASK_JOBS)
    for statement in _INDEXES:
        op.execute(statement)


def downgrade() -> None:
    raise RuntimeError(
        "task_jobs downgrade is destructive; restore a backup or remove it manually"
    )
