"""Add status and error columns to deliveries (BUS-308).

- status TEXT NOT NULL DEFAULT 'sent': sent|failed|forbidden
- error TEXT: exception class name only (no PII, no error messages)
- Idempotent (ADD COLUMN IF NOT EXISTS), style of 0008/0010/0011
- Fresh DBs seeded from baseline already have both columns — no-op for them
- Down-revision: 0011_promo_is_active (0011 added by BUS-302)
"""

from __future__ import annotations

from alembic import op

revision = "0012_delivery_status"
down_revision = "0011_promo_is_active"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE deliveries "
        "ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'sent'"
    )
    op.execute(
        "ALTER TABLE deliveries "
        "ADD COLUMN IF NOT EXISTS error TEXT"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE deliveries DROP COLUMN IF EXISTS error")
    op.execute("ALTER TABLE deliveries DROP COLUMN IF EXISTS status")
