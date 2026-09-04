"""Сервисы — правила продукта поверх репозиториев.

Разделение простое: репозитории знают, *где* лежат данные, сервисы — *что можно*
с ними делать. Хендлеры бота и роутеры API не содержат бизнес-логики, поэтому
одно и то же правило (лимит вопросов, выдача купленного) работает одинаково и в
Telegram, и в Mini App, и в админке.

Модули:
    limits      — можно ли задать вопрос и за счёт чего
    chat        — единый путь вопроса и расклада для бота и Mini App
    billing     — витрина, заказы, приём оплаты, выдача, промокоды
    referrals   — приглашения и бонусы
    catalog     — расклады: встроенные + добавленные из админки
    practices   — практики и мантры: программа по дням и стрик
    horoscopes  — дневные гороскопы по знакам и каналы-спутники
    analytics   — безопасный трекинг событий и дашборд
    invoices    — ссылки на оплату Stars для Mini App
    broadcast   — рассылки по сегментам
    scheduler   — регулярные сценарии: прогнозы, отчёты, продления, напоминания
"""
from . import (analytics, billing, broadcast, catalog, chat,  # noqa: F401
               horoscopes, invoices, limits, practices, referrals, scheduler)

__all__ = ["limits", "chat", "billing", "referrals", "catalog", "analytics",
           "invoices", "broadcast", "scheduler", "practices", "horoscopes"]
