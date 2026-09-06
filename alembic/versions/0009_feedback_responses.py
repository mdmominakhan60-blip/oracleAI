"""Feedback-опрос day7_v1: хранение отзывов (BUS-231, задача 1.5.1 BUS-172).

- `feedback_responses` — одна строка на отзыв пользователя (на survey_code):
  ответы вопросов — JSON (категориальные коды + score, allowlist на сервере),
  свободный текст — только здесь, НЕ в events (privacy-инвариант BUS-168 §2.3:
  events — rolling window 120 дней и без пользовательского текста).
  UNIQUE (tg_id, survey_code) — один отзыв на пользователя на версию опроса;
  повторный POST отклоняется на уровне БД (анти-абьюз BUS-170 §5.1).
- `bonus_lot_id` — ссылка на строку `crystal_lots` (source='review_bonus',
  грант 40✦ на 90 дней, BUS-177). FK нет по конвенции схемы (как tg_id везде).
- `deliveries` — дедуп приглашения (kind='feedback_survey', key='day7_v1') и
  напоминания (key='day7_v1_remind') обеспечивается СУЩЕСТВУЮЩЕЙ механикой:
  PK (tg_id, kind, key) + атомарный comms.claim → mark_sent (ON CONFLICT DO
  NOTHING) — повторные отправки при рестартах scheduler'а исключены без DDL.
  Правка baseline.sql — только комментарий-справка о новых kind.

По завершении фичи бонусная семантика статусов/полей уточняется Backend в
рамках BUS-172 (этап 2 плана BUS-167 §5); схема фиксирует минимум контракта.

Revision ID: 0009_feedback_responses
Revises: 0008_funnel_session_id
"""
from __future__ import annotations

from alembic import op

revision = "0009_feedback_responses"
down_revision = "0008_funnel_session_id"
branch_labels = None
depends_on = None


_FEEDBACK_RESPONSES = """
CREATE TABLE IF NOT EXISTS feedback_responses (
    id            BIGSERIAL PRIMARY KEY,
    tg_id         BIGINT NOT NULL,
    survey_code   TEXT NOT NULL DEFAULT 'day7_v1',  -- версия опроса: day7_v1, далее day7_v2...
    answers_json  TEXT,                  -- [{question_code, choice, score}] — без свободного текста
    free_text     TEXT,                  -- свободный текст отзыва (единственное место хранения)
    status        TEXT NOT NULL DEFAULT 'submitted',  -- исход обработки; бонусные детали ниже
    bonus_granted BIGINT DEFAULT 0,      -- 0|1: начислен ли бонус (одна попытка за всю жизнь, BUS-177)
    bonus_lot_id  BIGINT,                -- crystal_lots.id гранта source='review_bonus'
    created_at    TEXT,
    UNIQUE (tg_id, survey_code)
)
"""

_INDEXES = (
    # Список/экспорт отзывов в админке (BUS-168) — по дате; по tg_id выборку
    # обслуживает UNIQUE-индекс (tg_id слева).
    "CREATE INDEX IF NOT EXISTS idx_feedback_created ON feedback_responses(created_at)",
    "CREATE INDEX IF NOT EXISTS idx_feedback_status ON feedback_responses(status, created_at)",
)


def upgrade() -> None:
    op.execute(_FEEDBACK_RESPONSES)
    for statement in _INDEXES:
        op.execute(statement)
    # Справка о назначении kind='feedback_survey'/'day7_v1_remind' — в
    # канонической схеме; DDL deliveries не меняется (см. docstring).
    op.execute(
        "COMMENT ON TABLE deliveries IS "
        "'Журнал дедупа исходящих: tg_id+kind+key уникальны. kind: forecast|weekly|"
        "expiry|winback|broadcast|feedback_survey (key: day7_v1|day7_v1_remind)'"
    )


def downgrade() -> None:
    # Удаляет пользовательские отзывы. На проде откат только по бэкапу/с
    # осознанным решением (прецедент 0001/0002), в dev — свободно.
    op.execute("DROP INDEX IF EXISTS idx_feedback_status")
    op.execute("DROP INDEX IF EXISTS idx_feedback_created")
    op.execute("DROP TABLE IF EXISTS feedback_responses")
