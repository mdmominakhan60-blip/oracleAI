"""Composite indexes for the hot full-scan queries.

Audit DB-018 / API-013:
- the scheduler's daily-push loop scanned the whole users table
  (WHERE onboarded=1 AND status='active' ...);
- `SELECT MIN(day) ... WHERE tg_id=? AND name=?` in services/chat.py had no
  composite index to serve it.

Revision ID: 0005_composite_indexes
Revises: 0004_age_proof_hash
"""
from __future__ import annotations

from alembic import op

revision = "0005_composite_indexes"
down_revision = "0004_age_proof_hash"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_users_push_segment "
        "ON users(status, onboarded, morning_push, tz)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_events_tg_name_day "
        "ON events(tg_id, name, day)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_users_push_segment")
    op.execute("DROP INDEX IF EXISTS idx_events_tg_name_day")
