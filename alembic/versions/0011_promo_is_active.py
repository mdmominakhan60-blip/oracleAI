"""Voucher channel v1: promo_codes.is_active for revoking a code/batch (BUS-317, G3).

Маркетплейс-ваучеры (BUS-287 rev 2, партии mpl_*): leaked/compromised codes
needed a kill switch — without it a batch stays redeemable until expires_at
and CS has no way to revoke it (BUS-289 gap G3).

Idempotent (ADD COLUMN IF NOT EXISTS), style of 0008/0010: DBs seeded from
baseline already have the column — for them this is a no-op. Baseline.sql is
updated in the same change; migrations remain the primary schema source.

- Column mirrors products.is_active (BIGINT DEFAULT 1); explicit 0 = revoked.
  redeem (app/repo/growth.py) refuses is_active=0 together with the
  expiry/limit checks, in the same transaction.

Revision ID: 0011_promo_is_active
Revises: 0010_close_schema_drift
"""
from __future__ import annotations

from alembic import op

revision = "0011_promo_is_active"
down_revision = "0010_close_schema_drift"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE promo_codes "
        "ADD COLUMN IF NOT EXISTS is_active BIGINT DEFAULT 1"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE promo_codes DROP COLUMN IF EXISTS is_active")
