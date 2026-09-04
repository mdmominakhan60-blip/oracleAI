"""Add a deck column to tarot_readings so a chosen deck survives replay.

Revision ID: 0007_add_tarot_deck
Revises: 0006_drop_age_columns
"""
from __future__ import annotations

from alembic import op

revision = "0007_add_tarot_deck"
down_revision = "0006_drop_age_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE tarot_readings ADD COLUMN IF NOT EXISTS deck TEXT DEFAULT 'tarot'"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE tarot_readings DROP COLUMN IF EXISTS deck")
