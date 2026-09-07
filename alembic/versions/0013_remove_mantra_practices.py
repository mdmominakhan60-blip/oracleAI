"""Remove mantra practices (BUS-391 W1/Э1).

- Deactivate content_items rows with kind='practice' and code LIKE 'mantra_%'
  (is_active=0, not DELETE: admin audit trail and UNIQUE (kind, code) stay intact).
- Close active user practices of mantra codes via finished_at=NOW — history,
  day_index and streak are preserved, so streak-based stats (ltv_tier,
  CRM chains) keep working; started/unfinished rows just stop being active.

Down-revision: 0012_delivery_status (added by BUS-308).
Idempotent, style of 0008/0010/0011/0012. Baseline.sql is not changed here:
fresh DBs no longer seed mantra items because the seed source (PRACTICES)
no longer contains them.
"""

from __future__ import annotations

from alembic import op

revision = "0013_remove_mantra_practices"
down_revision = "0012_delivery_status"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "UPDATE content_items SET is_active = 0, updated_at = "
        "to_char(now() at time zone 'utc', 'YYYY-MM-DD\"T\"HH24:MI:SS') "
        "WHERE kind = 'practice' AND code LIKE 'mantra_%' AND is_active <> 0"
    )
    # Close active user practices: idempotent (WHERE finished_at IS NULL),
    # streak/day_index/last_done stay untouched on purpose.
    op.execute(
        "UPDATE practices SET finished_at = "
        "to_char(now() at time zone 'utc', 'YYYY-MM-DD\"T\"HH24:MI:SS') "
        "WHERE code LIKE 'mantra_%' AND finished_at IS NULL"
    )


def downgrade() -> None:
    # Catalog rows: reactivation restores visibility, but seed content
    # (title/body/meta) comes from seeding, not from this migration.
    op.execute(
        "UPDATE content_items SET is_active = 1 "
        "WHERE kind = 'practice' AND code LIKE 'mantra_%'"
    )
    # User practices: not reopened — closed runs are closed history.
