"""Роутеры API. Каждый файл — один экран или одна область продукта."""
from . import (admin, chart, chart_products, chat, diary, history, jobs, logs,
               notifications, placements, practices, profile, share, shop, tarot,
               today, webhooks)  # noqa: F401

ROUTERS = (profile.router, today.router, chat.router, tarot.router, chart.router,
           chart_products.router, placements.router, diary.router, history.router,
           notifications.router, logs.router,
           practices.router, share.router, shop.router, webhooks.router,
           admin.router, jobs.router)

__all__ = ["ROUTERS"]
