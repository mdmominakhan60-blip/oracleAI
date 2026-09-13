"""HTTP-контракты волны A (R07): модели запросов, вынесенные из роутеров.

Источник: gap-анализ BUS-735 (G-1) и issue BUS-805. Перенос без изменения
поведения — роутеры импортируют эти же классы, поэтому OpenAPI-схема и
валидация совпадают с предыдущими инлайн-определениями.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from ...services.repo_gateway import feedback as feedback_repo
from .chart_products import SynastryIn  # noqa: F401 — реэкспорт для стабильного пути


class DrawIn(BaseModel):
    question: str | None = None
    deck: str | None = None


class OutcomeIn(BaseModel):
    # Аудит API-012: исход — закрытое множество, а не произвольная строка.
    outcome: Literal["came_true", "partly", "no"]


class ChartBuildIn(BaseModel):
    birth_date: str | None = None
    birth_time: str | None = None
    birth_time_precision: Literal["exact", "approx", "unknown"] | None = None
    birth_city: str | None = Field(default=None, max_length=60)


class PartnerIn(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    birth_date: str
    relation: str = Field(default="partner", max_length=20)
    birth_time: str | None = None
    birth_city: str | None = Field(default=None, max_length=60)


class ReportIn(BaseModel):
    partner_date: str | None = None
    partner_name: str = Field(default="", max_length=30)


class DiaryIn(BaseModel):
    text: str = Field(min_length=1, max_length=1000)
    mood: str | None = Field(default=None, max_length=20)


class FeedbackAnswerIn(BaseModel):
    """Один ответ: категориальный код или score; текст — опционален.

    Нормализация по allowlist'у — в repo (константы схемы); здесь отсекаем
    заведомый мусор и размер на границе.
    """
    question_code: str = Field(min_length=1, max_length=32,
                               pattern=r"^[a-z0-9_]+$")
    choice: str | None = Field(default=None, max_length=32,
                               pattern=r"^[a-z0-9_]*$")
    score: int | None = Field(default=None, ge=0, le=10)
    text: str | None = Field(default=None, max_length=4000)


class FeedbackIn(BaseModel):
    answers: list[FeedbackAnswerIn] = Field(min_length=1, max_length=5)
    survey_code: str = Field(default=feedback_repo.SURVEY_CODE,
                             pattern=r"^day7_v\d+$")


class NotificationPreferencesIn(BaseModel):
    morning_forecast: bool | None = None


class PlacementIn(BaseModel):
    placement: str = Field(min_length=2, max_length=40)
    birth_date: str | None = None
    birth_time: str | None = Field(default=None, max_length=5)
    birth_city: str | None = Field(default=None, max_length=60)


class InvoiceIn(BaseModel):
    sku: str | None = None
    plan: str | None = None
    billing_period: Literal["monthly", "annual"] = "monthly"


class SubscriptionCancelIn(BaseModel):
    cancel_at_period_end: bool = True


class CryptoIn(BaseModel):
    sku: str = Field(min_length=1, max_length=40)
    asset: str = Field(default="USDT", min_length=2, max_length=8)
