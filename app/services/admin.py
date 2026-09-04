"""Admin API service facade — the only repo access point for the admin router."""
from __future__ import annotations

from ..repo import admin as admin_repo
from ..repo import analytics as analytics_repo
from ..repo import billing, comms, content, crm, growth, users

__all__ = ["admin_repo", "analytics_repo", "billing", "comms", "content",
           "crm", "growth", "users"]
