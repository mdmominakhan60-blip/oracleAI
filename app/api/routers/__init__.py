"""Роутеры API. Каждый файл — один экран или одна область продукта."""
from . import (admin, auth_router, chart, chart_products, chat, diary, entitlements,
               feedback, funnel, history, jobs, logs, notifications, placements,
               practices, profile, share, shop, tarot, today, webhooks)  # noqa: F401

ROUTERS = (profile.router, today.router, chat.router, tarot.router, chart.router,
           chart_products.router, placements.router, diary.router, history.router,
           notifications.router, logs.router,
           practices.router, share.router, shop.router, webhooks.router,
           admin.router, jobs.router,
           funnel.router, feedback.router, auth_router.router,
           entitlements.router)

__all__ = ["ROUTERS"]
