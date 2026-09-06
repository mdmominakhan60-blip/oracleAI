"""Close schema drift prod vs baseline.sql (BUS-298).

Прод-БД (восстановлена из бэкапа 04:49 на 0008, инцидент BUS-294) не имеет
колонок, добавленных в baseline.sql коммитом c45a6b4 (BUS-231) и ранее:
INSERT/UPDATE их пишет (app/core/llm.py:229-234, app/core/product_cost.py:105,
app/bot/onboarding.py:684) — на проде это падало «column does not exist».

Миграция идемпотентная (ADD COLUMN IF NOT EXISTS): свежие БД, посеянные из
baseline через 0001, уже содержат все колонки — для них это no-op. Стиль 0008.

- llm_usage: 6 колонок монетизационного контекста (sku-каталог BUS-231).
- product_cost_events.price_variant: v1/v2 цена (BUS-185 price book).
- users: natal_technique/_version, onboarding_step, birth_time_precision —
  есть в baseline и в коде, но не были ни в одной версии миграций
  (пробел 0001; на проде пропали при восстановлении).

feedback_responses и idx_feedback_* НЕ здесь: их создаёт 0009 (применяется
перед 0010 штатно). idx_monetization_usage_sku / idx_product_cost_day_sku на
проде уже существуют (проверено), CREATE INDEX IF NOT EXISTS в 0005-стиле
оставлен в baseline только.

Правило (DoD BUS-298): изменения схемы — только через миграцию;
baseline.sql — производная (выжимка после миграций), не первичный источник.

Revision ID: 0010_close_schema_drift
Revises: 0009_feedback_responses
"""
from __future__ import annotations

from alembic import op

revision = "0010_close_schema_drift"
down_revision = "0009_feedback_responses"
branch_labels = None
depends_on = None

_ADD_COLUMNS: list[tuple[str, str, str]] = [
    # (таблица, колонка, DDL-определение после имени) — типы/дефолты сверены
    # со staging (посеян из текущего baseline) и с baseline.sql.
    ("llm_usage", "sku", "TEXT"),
    ("llm_usage", "catalog_version", "TEXT DEFAULT 'legacy'"),
    ("llm_usage", "subscription_code", "TEXT"),
    ("llm_usage", "included_usage", "BIGINT DEFAULT 0"),
    ("llm_usage", "crystal_spend", "BIGINT DEFAULT 0"),
    ("llm_usage", "overage", "BIGINT DEFAULT 0"),
    ("product_cost_events", "price_variant", "TEXT"),
    ("users", "natal_technique", "TEXT DEFAULT 'astrology'"),
    ("users", "natal_technique_version", "TEXT DEFAULT 'v1'"),
    ("users", "onboarding_step", "TEXT"),
    ("users", "birth_time_precision", "TEXT DEFAULT 'exact'"),
]


def upgrade() -> None:
    for table, column, spec in _ADD_COLUMNS:
        op.execute(
            f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {spec}"
        )


def downgrade() -> None:
    # Честный реверс списка; NULL-дефолты не ставим (симметрично ADD).
    for table, column, _spec in reversed(_ADD_COLUMNS):
        op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS {column}")
