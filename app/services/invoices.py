"""Ссылки на оплату Stars — совместимые имена поверх `services.telegram`."""
from __future__ import annotations

from .telegram import TelegramError as InvoiceError  # noqa: F401
from .telegram import create_invoice_link as create_link  # noqa: F401
from .telegram import refund_star_payment as refund  # noqa: F401

__all__ = ["create_link", "refund", "InvoiceError"]
