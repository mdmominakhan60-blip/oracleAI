"""Request models for versioned chart product paths."""
from __future__ import annotations

from datetime import date, time as dt_time
from typing import Literal

from pydantic import BaseModel, Field, validator


class SynastryIn(BaseModel):
    partner_id: int = Field(..., gt=0)


class TransitIn(BaseModel):
    as_of: date
    time: dt_time | None = None

    @validator("as_of")
    def reject_unreasonable_year(cls, value: date) -> date:
        if value.year < 1900 or value.year > 2200:
            raise ValueError("Дата транзита должна быть между 1900 и 2200 годом")
        return value


class CompositeIn(BaseModel):
    partner_id: int = Field(..., gt=0)


class ReturnsIn(BaseModel):
    planet: Literal["Sun"] = "Sun"
    year: int = Field(..., ge=1900, le=2200)
