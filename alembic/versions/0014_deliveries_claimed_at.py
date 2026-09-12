"""Add claimed_at column to deliveries (BUS-313 F1/Q3).

- claimed_at TEXT (ISO): когда строка занята под отправку (claim), аналог
  broadcast_targets.claimed_at. Основа reclaim: строки, зависшие в
  status='sending' дольше CLAIM_TIMEOUT_S (крэш процесса между claim
  и mark), возвращаются в очередь следующим тиком планировщика.
- Idempotent (ADD COLUMN IF NOT EXISTS), style of 0008/0010/0012
- Down-revision: 0013_remove_mantra_practices
"""

from __future__ import annotations

from alembic import op

revision = "0014_deliveries_claimed_at"
down_revision = "0013_remove_mantra_practices"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE deliveries "
        "ADD COLUMN IF NOT EXISTS claimed_at TEXT"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE deliveries DROP COLUMN IF EXISTS claimed_at")
