"""Data-hygiene: birth_time_precision 'approximate' → 'approx' (BUS-1232).

Ботные поверхности онбординга до фикса писали в users.birth_time_precision
токен 'approximate', тогда как API-контракт и потребители (GET /api/me,
/api/chart) используют канон 'approx'. Расхождение молча превращало
примерное время в 'unknown' на карте и ломало resume-онбординг в miniapp.
Код фикса (app/core/precision.py + нормализация на границах) не допускает
новых таких строк; эта миграция вычищает существующие.

- Idempotent (UPDATE по конкретному значению)
- Down-revision: 0014_deliveries_claimed_at
"""

from __future__ import annotations

from alembic import op

revision = "0015_precision_approx_canon"
down_revision = "0014_deliveries_claimed_at"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "UPDATE users SET birth_time_precision = 'approx' "
        "WHERE birth_time_precision = 'approximate'"
    )


def downgrade() -> None:
    # Обратное маппинг канона на устаревший токен — только для симметричности;
    # данных в 'approximate' после апгрейда не остаётся.
    op.execute(
        "UPDATE users SET birth_time_precision = 'approximate' "
        "WHERE birth_time_precision = 'approx' AND birth_time_known = 0"
    )
