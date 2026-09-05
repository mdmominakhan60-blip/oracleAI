"""Session-scoped funnel events (EXP-004, BUS-144).

- `events.session_id` — анонимный идентификатор визита (sid), связывает
  visit → signup → activation до первой идентификации клиента. NULL для всех
  существующих событий: колонка аддитивная, старые записи не трогаем.
- Частичный уникальный индекс делает приём идемпотентным на уровне БД:
  INSERT ... ON CONFLICT DO NOTHING отбрасывает повтор (retry, дубль beacon),
  поэтому перезапуск приёма не плодит дубли в воронке.

Revision ID: 0008_funnel_session_id
Revises: 0007_add_tarot_deck
"""
from __future__ import annotations

from alembic import op

revision = "0008_funnel_session_id"
down_revision = "0007_add_tarot_deck"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE events ADD COLUMN IF NOT EXISTS session_id TEXT")
    # Идемпотентный приём: одно (session_id, name) на сессию. События без
    # session_id (весь существующий трекинг) индексом не затрагиваются.
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_events_session_name "
        "ON events(session_id, name) WHERE session_id IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_events_session_name")
    op.execute("ALTER TABLE events DROP COLUMN IF EXISTS session_id")
