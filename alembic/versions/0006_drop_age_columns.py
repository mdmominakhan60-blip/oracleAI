"""Drop the age-gate columns (age_confirmed, age_proof_hash).

GAUNTLET v2: age verification was removed entirely — the self-confirmation
flag and its SEC-010 keyed hash are no longer read or written. These columns
carry no product data and are dropped to avoid dead schema and PII the app
never uses. Anonymization no longer needs to reset age_confirmed.

Revision ID: 0006_drop_age_columns
Revises: 0005_composite_indexes
"""
from __future__ import annotations

from alembic import op

revision = "0006_drop_age_columns"
down_revision = "0005_composite_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS age_confirmed")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS age_proof_hash")


def downgrade() -> None:
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS age_confirmed BIGINT DEFAULT 0")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS age_proof_hash TEXT")
