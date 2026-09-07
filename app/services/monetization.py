"""Thin monetization facade (ARCH-004: router→services→repo).

Сейчас только `crystal_lot` — нужен feedback-роуту для гранта 40✦.
В будущем сюда переедут остальные монетизационные операции, чтобы
роутеры не доставали `app.repo.monetization` напрямую.
"""
from __future__ import annotations

from ..repo.monetization import crystal_lot

__all__ = ["crystal_lot"]
