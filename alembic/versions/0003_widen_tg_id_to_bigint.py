"""Widen Telegram id columns from INTEGER (int32) to BIGINT.

Telegram user ids exceed the int32 range (e.g. 5721249303 > 2^31), so any column
storing a Telegram identifier overflows INTEGER. The baseline schema rendered
tg_id and related user/admin id columns as INTEGER; this migration widens them
to BIGINT. It is idempotent: ALTER of an already-BIGINT column is a no-op.

Revision ID: 0003_widen_tg_id_to_bigint
Revises: 0002_task_jobs
"""
from __future__ import annotations

from alembic import op

revision = "0003_widen_tg_id_to_bigint"
down_revision = "0002_task_jobs"
branch_labels = None
depends_on = None

# Columns that hold Telegram ids (or ids derived from them: referrers, admins,
# content authors, broadcast creators, code curators). "id INTEGER PRIMARY KEY
# AUTOINCREMENT" already renders as BIGSERIAL on PostgreSQL, so only these need
# an explicit ALTER. Column order is irrelevant; each is widened independently.
_USER_ID_COLUMNS: tuple[tuple[str, str], ...] = (
    ("users", "tg_id"),
    ("users", "ref_by"),
    ("threads", "tg_id"),
    ("messages", "tg_id"),
    ("chat_requests", "tg_id"),
    ("memories", "tg_id"),
    ("profile_summaries", "tg_id"),
    ("shared_context_events", "tg_id"),
    ("shared_context_snapshots", "tg_id"),
    ("diary", "tg_id"),
    ("forecasts", "tg_id"),
    ("reports", "tg_id"),
    ("deliveries", "tg_id"),
    ("user_notifications", "tg_id"),
    ("tarot_readings", "tg_id"),
    ("palm_readings", "tg_id"),
    ("partners", "tg_id"),
    ("synastry_cache", "tg_id"),
    ("practices", "tg_id"),
    ("orders", "tg_id"),
    ("payments", "tg_id"),
    ("entitlements", "tg_id"),
    ("crystal_ledger", "tg_id"),
    ("promo_redemptions", "tg_id"),
    ("referrals", "referrer_id"),
    ("referrals", "invitee_id"),
    ("llm_usage", "tg_id"),
    ("safety_events", "tg_id"),
    ("task_jobs", "tg_id"),
    ("events", "tg_id"),
    ("product_cost_events", "tg_id"),
    ("admins", "tg_id"),
    ("admin_audit", "admin_id"),
    ("user_notes", "tg_id"),
    ("user_notes", "author_id"),
    ("user_tags", "tg_id"),
    ("broadcast_targets", "tg_id"),
    ("settings", "updated_by"),
    ("content_items", "updated_by"),
    ("feature_flags", "updated_by"),
    ("broadcasts", "created_by"),
    ("promo_codes", "created_by"),
    ("promo_codes", "used_by"),
)


def upgrade() -> None:
    for table, column in _USER_ID_COLUMNS:
        op.execute(f"ALTER TABLE {table} ALTER COLUMN {column} TYPE BIGINT")


def downgrade() -> None:
    raise RuntimeError(
        "tg_id downgrade to INTEGER is destructive for ids beyond int32; "
        "restore a backup or widen only what is safe"
    )
