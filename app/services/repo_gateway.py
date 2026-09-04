"""Presentation-layer repo gateway (ARCH-004 close-out).

The single access point from app/api to app/repo: routers and deps import
repository modules from here, never from ``app/repo`` directly. This keeps
the presentation → services → repo layering checkable by
``tests/test_architecture_boundaries.py`` and gives SQL optimization one
funnel to reason about, mirroring the per-domain facades
(``app/services/admin.py`` et al.) used earlier in ARCH-004.
"""
from __future__ import annotations

from ..repo import admin  # noqa: F401
from ..repo import analytics  # noqa: F401
from ..repo import billing  # noqa: F401
from ..repo import comms  # noqa: F401
from ..repo import content  # noqa: F401
from ..repo import crm  # noqa: F401
from ..repo import dialog  # noqa: F401
from ..repo import growth  # noqa: F401
from ..repo import jobs  # noqa: F401
from ..repo import monetization  # noqa: F401
from ..repo import notifications  # noqa: F401
from ..repo import palm  # noqa: F401
from ..repo import readings  # noqa: F401
from ..repo import users  # noqa: F401

__all__ = ["admin", "analytics", "billing", "comms", "content", "crm",
           "dialog", "growth", "jobs", "monetization", "notifications",
           "palm", "readings", "users"]
