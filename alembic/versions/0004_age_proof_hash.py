"""Store an age-attestation proof hash instead of a client-controlled boolean.

Audit SEC-010: the 16+ age gate used to be a bare `age_confirmed` flag that the
Mini App set with `POST /api/profile {age_confirmed: true}` — a fully
client-controlled attestation. The API now requires a birth year together with
the confirmation and persists only a keyed hash of it (never the raw year), so
the server can prove a plausible attestation happened without keeping extra PII.

Revision ID: 0004_age_proof_hash
Revises: 0003_widen_tg_id_to_bigint
"""
from __future__ import annotations

from alembic import op

revision = "0004_age_proof_hash"
down_revision = "0003_widen_tg_id_to_bigint"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS age_proof_hash TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS age_proof_hash")
