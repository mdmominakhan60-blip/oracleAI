"""Canonical monetization v2 catalog and price-book seed data.

The legacy ``plans``/``products`` rows remain untouched. These records are the
server-owned source for new purchases and are copied into versioned database tables
on first startup. Prices and cost budgets are hypotheses until provider settlement
and observed usage data are reviewed.
"""
from __future__ import annotations

CATALOG_VERSION = "2026-08-v2"
PRICE_BOOK_VERSION = "pb-2026-08-v2"
STARS_PER_USD_ASSUMPTION = 52

PLAN_DEFINITIONS = (
    {
        "code": "free",
        "title": "✦ Искра",
        "tagline": "Базовая ценность, Today и понятный preview премиум-возможностей",
        "period_days": 36500,
        "monthly_usd": 0.0,
        "annual_usd": 0.0,
        "monthly_stars": 0,
        "annual_stars": 0,
        "ai_messages": 0,
        "compute_budget_usd": 0.0,
        "memory_depth": 0,
        "crystals_grant": 0,
        "sort": 10,
        "badge": None,
        "features": [
            "today.basic", "astro.basic", "report.natal.basic", "tarot.basic",
            "history.basic", "premium.preview", "crystals.purchase",
        ],
    },
    {
        "code": "vip_core",
        "title": "VIP",
        "tagline": "Личный AI-проводник, память и регулярная глубина",
        "period_days": 30,
        "monthly_usd": 19.99,
        "annual_usd": 199.90,
        "monthly_stars": 1040,
        "annual_stars": 10395,
        "ai_messages": 120,
        "compute_budget_usd": 0.12,
        "memory_depth": 40,
        "crystals_grant": 60,
        "sort": 20,
        "badge": None,
        "features": [
            "today.basic", "astro.basic", "astro.advanced", "tarot.basic",
            "tarot.advanced", "palm.basic", "ai.chat", "ai.memory",
            "ai.deep_context", "report.natal.basic", "report.natal.deep.limited",
            "voice", "crystals.purchase",
        ],
    },
    {
        "code": "vip_plus",
        "title": "VIP Plus",
        "tagline": "Лучший выбор для регулярной работы и расширенных разборов",
        "period_days": 30,
        "monthly_usd": 34.99,
        "annual_usd": 349.90,
        "monthly_stars": 1820,
        "annual_stars": 18195,
        "ai_messages": 300,
        "compute_budget_usd": 0.35,
        "memory_depth": 100,
        "crystals_grant": 180,
        "sort": 30,
        "badge": "выбор большинства",
        "features": [
            "today.basic", "astro.basic", "astro.advanced", "tarot.basic",
            "tarot.advanced", "palm.basic", "palm.advanced", "ai.chat",
            "ai.memory", "ai.deep_context", "report.natal.basic", "report.natal.deep",
            "report.synastry.deep.limited", "monthly_report", "priority_queue",
            "voice", "crystals.purchase",
        ],
    },
    {
        "code": "pro",
        "title": "Pro",
        "tagline": "Высокий allowance, advanced reports и приоритетная обработка",
        "period_days": 30,
        "monthly_usd": 69.99,
        "annual_usd": 699.90,
        "monthly_stars": 3640,
        "annual_stars": 36395,
        "ai_messages": 700,
        "compute_budget_usd": 0.90,
        "memory_depth": 250,
        "crystals_grant": 450,
        "sort": 40,
        "badge": None,
        "features": [
            "today.basic", "astro.basic", "astro.advanced", "tarot.basic",
            "tarot.advanced", "palm.basic", "palm.advanced", "ai.chat",
            "ai.memory", "ai.deep_context", "report.natal.basic", "report.natal.deep",
            "report.synastry.deep", "monthly_report", "priority_queue", "voice",
            "advanced_reports", "crystals.purchase",
        ],
    },
    {
        "code": "concierge_v2",
        "title": "Concierge",
        "tagline": "Максимальное качество маршрутизации и высокий fair-use allowance",
        "period_days": 30,
        "monthly_usd": 99.99,
        "annual_usd": 999.90,
        "monthly_stars": 5200,
        "annual_stars": 51995,
        "ai_messages": 1200,
        "compute_budget_usd": 1.50,
        "memory_depth": 500,
        "crystals_grant": 800,
        "sort": 50,
        "badge": "highest priority",
        "features": [
            "today.basic", "astro.basic", "astro.advanced", "tarot.basic",
            "tarot.advanced", "palm.basic", "palm.advanced", "ai.chat",
            "ai.memory", "ai.deep_context", "report.natal.basic", "report.natal.deep",
            "report.synastry.deep", "monthly_report", "priority_queue", "voice",
            "advanced_reports", "concierge_tools", "crystals.purchase",
        ],
    },
)

ANNUAL_PLANS = {item["code"]: item for item in PLAN_DEFINITIONS if item["monthly_usd"]}

CRYSTAL_PACKS = (
    {
        "sku": "crystals_50_v2", "title": "50 ✦ Кристаллов",
        "description": "Первый запас для одного короткого глубокого результата",
        "crystals": 50, "bonus": 0, "usd": 9.99, "stars": 520, "sort": 10,
    },
    {
        "sku": "crystals_150_v2", "title": "150 ✦ Кристаллов",
        "description": "Основной пакет для нескольких глубоких разборов",
        "crystals": 150, "bonus": 0, "usd": 24.99, "stars": 1300, "sort": 20,
    },
    {
        "sku": "crystals_400_v2", "title": "400 ✦ Кристаллов",
        "description": "Запас для power users и больших отчётов",
        "crystals": 400, "bonus": 0, "usd": 59.99, "stars": 3120, "sort": 30,
    },
)

DEEP_PRODUCTS = (
    {
        "sku": "deep_followup", "title": "Глубокое уточнение",
        "description": "Расширить уже начатый разбор с дополнительным контекстом",
        "crystals": 15, "cost_budget_usd": 0.02, "grant_kind": "report",
        "grant_code": "deep_followup", "grant_qty": 1, "valid_days": 30, "sort": 10,
    },
    {
        "sku": "tarot_one_deep", "title": "Глубокий расклад: одна карта",
        "description": "Персональная интерпретация одной карты с контекстом вопроса",
        "crystals": 20, "cost_budget_usd": 0.03, "grant_kind": "spread",
        "grant_code": "one_deep", "grant_qty": 1, "valid_days": 30, "sort": 20,
    },
    {
        "sku": "tarot_three_deep", "title": "Глубокий расклад: три карты",
        "description": "Связный разбор прошлого, настоящего и направления",
        "crystals": 40, "cost_budget_usd": 0.05, "grant_kind": "spread",
        "grant_code": "three_deep", "grant_qty": 1, "valid_days": 30, "sort": 30,
    },
    {
        "sku": "report_natal_deep", "title": "Глубокий натальный отчёт",
        "description": "Большой персональный отчёт с фактами карты и ограничениями точности",
        "crystals": 120, "cost_budget_usd": 0.14, "grant_kind": "report",
        "grant_code": "natal_deep", "grant_qty": 1, "valid_days": None, "sort": 40,
    },
    {
        "sku": "report_synastry_deep", "title": "Глубокий отчёт о совместимости",
        "description": "Разбор пары при явном согласии и сохранённых данных партнёра",
        "crystals": 150, "cost_budget_usd": 0.18, "grant_kind": "report",
        "grant_code": "synastry_deep", "grant_qty": 1, "valid_days": None, "sort": 50,
    },
    {
        "sku": "report_annual_deep", "title": "Большой годовой отчёт",
        "description": "Расширенный годовой обзор с bounded AI computation",
        "crystals": 240, "cost_budget_usd": 0.28, "grant_kind": "report",
        "grant_code": "annual_deep", "grant_qty": 1, "valid_days": None, "sort": 60,
    },
)

CAPABILITY_MATRIX = {
    "free": {
        "today.basic": True, "astro.basic": True, "report.natal.basic": True,
        "tarot.basic": True, "history.basic": True, "premium.preview": True,
        "crystals.purchase": True,
    },
    "vip_core": {
        "today.basic": True, "astro.basic": True, "astro.advanced": True,
        "tarot.basic": True, "tarot.advanced": True, "palm.basic": True,
        "ai.chat": True, "ai.memory": True, "ai.deep_context": True,
        "report.natal.basic": True, "report.natal.deep": "limited", "voice": True,
        "crystals.purchase": True,
    },
    "vip_plus": {
        "today.basic": True, "astro.basic": True, "astro.advanced": True,
        "tarot.basic": True, "tarot.advanced": True, "palm.basic": True,
        "palm.advanced": True, "ai.chat": True, "ai.memory": True,
        "ai.deep_context": True, "report.natal.basic": True,
        "report.natal.deep": True, "report.synastry.deep": "limited",
        "monthly_report": True, "priority_queue": True, "voice": True,
        "crystals.purchase": True,
    },
    "pro": {
        "today.basic": True, "astro.basic": True, "astro.advanced": True,
        "tarot.basic": True, "tarot.advanced": True, "palm.basic": True,
        "palm.advanced": True, "ai.chat": True, "ai.memory": True,
        "ai.deep_context": True, "report.natal.basic": True,
        "report.natal.deep": True, "report.synastry.deep": True,
        "monthly_report": True, "priority_queue": True, "voice": True,
        "advanced_reports": True, "crystals.purchase": True,
    },
    "concierge_v2": {
        "today.basic": True, "astro.basic": True, "astro.advanced": True,
        "tarot.basic": True, "tarot.advanced": True, "palm.basic": True,
        "palm.advanced": True, "ai.chat": True, "ai.memory": True,
        "ai.deep_context": True, "report.natal.basic": True,
        "report.natal.deep": True, "report.synastry.deep": True,
        "monthly_report": True, "priority_queue": "highest", "voice": True,
        "advanced_reports": True, "concierge_tools": True,
        "crystals.purchase": True,
    },
}

LEGACY_TIER_ALIASES = {
    "trial": "free", "guide": "vip_core", "vip": "vip_plus", "vip_year": "vip_plus",
}
