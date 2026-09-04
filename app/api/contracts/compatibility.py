"""HTTP-контракты для расчёта и разбора совместимости."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class CompatIn(BaseModel):
    partner_date: str
    partner_name: str = Field(default="", max_length=30)
    save: bool = False
    relation: Literal["love", "friend", "work", "family"] = "love"
