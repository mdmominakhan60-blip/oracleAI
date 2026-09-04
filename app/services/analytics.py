"""Трекинг событий — обёртка, которая никогда не ломает пользовательский путь.

Аналитика полезна, но не важнее ответа клиентке. Если запись события упала
(заблокированная БД, битые props), продукт продолжает работать, а мы видим это
в логах. Поэтому все имена событий и `track` живут здесь, а не вызываются из
хендлеров напрямую.
"""
from __future__ import annotations

import asyncio
from datetime import date, timedelta
import logging

from ..repo import analytics as repo

log = logging.getLogger("oracle.analytics")

#: Фоновые записи событий. Сильная ссылка, чтобы задача не умерла по сборке мусора.
_pending: set[asyncio.Task] = set()

# Реэкспорт имён событий: хендлеры импортируют их отсюда, а не из репозитория.
E_START = repo.E_START
E_ONBOARD_DONE = repo.E_ONBOARD_DONE
E_QUESTION = repo.E_QUESTION
E_TAROT = repo.E_TAROT
E_FORECAST = repo.E_FORECAST
E_LIMIT_HIT = repo.E_LIMIT_HIT
E_SHOP_VIEW = repo.E_SHOP_VIEW
E_INVOICE = repo.E_INVOICE
E_PAID = repo.E_PAID
E_PROMO = repo.E_PROMO
E_REFERRAL = repo.E_REFERRAL
E_MINIAPP_OPEN = repo.E_MINIAPP_OPEN
E_CHURN_WARN = repo.E_CHURN_WARN
E_FIRST_RITUAL = repo.E_FIRST_RITUAL
E_FIRST_QUESTION = repo.E_FIRST_QUESTION
E_RETURN_D1 = repo.E_RETURN_D1
E_RETURN_D7 = repo.E_RETURN_D7
E_PAYWALL_VIEW = repo.E_PAYWALL_VIEW
E_PAYWALL_CHOICE = repo.E_PAYWALL_CHOICE
E_CREDIT_PACK_CHECKOUT_STARTED = repo.E_CREDIT_PACK_CHECKOUT_STARTED
E_CREDIT_PACK_PAID = repo.E_CREDIT_PACK_PAID
E_CREDIT_SPENT = repo.E_CREDIT_SPENT
E_CREDIT_BALANCE_LOW = repo.E_CREDIT_BALANCE_LOW
E_REPORT_DELIVERED = repo.E_REPORT_DELIVERED
E_REFUND_REQUESTED = repo.E_REFUND_REQUESTED
E_REFUND_COMPLETED = repo.E_REFUND_COMPLETED

_MONETIZATION_EVENTS = {
    E_PAYWALL_VIEW, E_PAYWALL_CHOICE, E_CREDIT_PACK_CHECKOUT_STARTED,
    E_CREDIT_PACK_PAID, E_CREDIT_SPENT, E_CREDIT_BALANCE_LOW,
    E_REPORT_DELIVERED, E_REFUND_REQUESTED, E_REFUND_COMPLETED,
}
_ALLOWED_SURFACES = {"bot", "miniapp", "admin", "system"}
_ALLOWED_CATEGORIES = _ALLOWED_SURFACES | {"web"}
_ALLOWED_CREDIT_BANDS = {"micro", "small", "medium", "large"}
_ALLOWED_RESULT_CATEGORIES = {"report", "spread", "question", "crystals", "plan", "daily", "tarot", "natal", "compatibility"}
_ALLOWED_REASONS = {"threshold_20", "support_request", "provider_refund", "delivery_failed"}


def credit_band(amount: int | None) -> str:
    value = max(0, int(amount or 0))
    if value <= 10:
        return "micro"
    if value <= 50:
        return "small"
    if value <= 150:
        return "medium"
    return "large"


async def track_monetization(db, name: str, tg_id: int | None = None, *,
                             surface: str = "system", sku: str | None = None,
                             channel: str | None = None,
                             price_variant: str | None = None,
                             credit_band_name: str | None = None,
                             result_category: str | None = None,
                             reason: str | None = None) -> bool:
    """Write an allowlisted monetization event without free-form payloads."""
    if name not in _MONETIZATION_EVENTS or surface not in _ALLOWED_SURFACES:
        return False
    values = {
        "sku": sku,
        "channel": channel,
        "price_variant": price_variant,
        "credit_band": credit_band_name,
        "result_category": result_category,
        "reason": reason,
    }
    props = {}
    for key, value in values.items():
        if value is None:
            continue
        if key == "channel" and value in _ALLOWED_CATEGORIES:
            props[key] = value
        elif key == "credit_band" and value in _ALLOWED_CREDIT_BANDS:
            props[key] = value
        elif key == "result_category" and value in _ALLOWED_RESULT_CATEGORIES:
            props[key] = value
        elif key == "reason" and value in _ALLOWED_REASONS:
            props[key] = value
        elif key in {"sku", "price_variant"} and isinstance(value, str):
            if 0 < len(value) <= 48 and all(char.isalnum() or char in "_-.:" for char in value):
                props[key] = value
    return await track_now(db, name, tg_id, props=props, surface=surface)


async def track(db, name: str, tg_id: int | None = None, *,
                props: dict | None = None, surface: str = "bot") -> None:
    """Ставит запись события в фон и возвращается сразу.

    Хендлеры ждут `await track(...)`, но тело не делает ни одной await-паузы:
    INSERT уходит в отдельную задачу, а пользовательский запрос не держится ради
    аналитики. `drain()` даёт тестам и шатдауну дождаться фоновых записей.
    """
    task = asyncio.get_running_loop().create_task(
        _record(db, name, tg_id, props, surface))
    _pending.add(task)
    task.add_done_callback(_pending.discard)


async def _record(db, name: str, tg_id: int | None, props, surface: str) -> None:
    try:
        await repo.track(db, name, tg_id, props=props, surface=surface)
    except Exception as e:  # noqa: BLE001
        log.warning("событие %s не записано: %s", name, e)


async def track_now(db, name: str, tg_id: int | None = None, *,
                   props: dict | None = None, surface: str = "system") -> bool:
    """Синхронная запись для server-side milestone, где важен read-after-write."""
    try:
        await repo.track(db, name, tg_id, props=props, surface=surface)
    except Exception as e:  # noqa: BLE001
        log.warning("событие %s не записано: %s", name, e)
        return False
    return True


async def track_once(db, name: str, tg_id: int, *,
                     props: dict | None = None, surface: str = "miniapp") -> bool:
    """Атомарно записывает milestone один раз; имена задаются сервером."""
    try:
        return await repo.track_once(db, name, tg_id, props=props, surface=surface)
    except Exception as e:  # noqa: BLE001
        log.warning("milestone %s не записан: %s", name, e)
        return False


async def drain() -> None:
    """Ждёт фоновые записи событий. Тесты и корректный шатдаун."""
    if _pending:
        await asyncio.gather(*_pending, return_exceptions=True)


async def prune(db, days: int = 120) -> int:
    """Чистит события и учёт LLM старее окна. Дашборд живёт на rolling-окнах,
    история на годы только раздувает базу."""
    return await repo.prune_analytics(db, days)


async def _monetization_v2_dashboard(db, *, days: int = 30) -> dict:
    from ..repo import monetization
    return await monetization.dashboard(db, days=days)


async def dashboard(db, *, days: int = 30) -> dict:
    """Единый ответ для главного экрана админки."""
    from ..repo import billing, growth
    return {
        "overview": await repo.overview(db),
        "funnel": await repo.funnel(db, days),
        "activation": await repo.activation_funnel(db, days),
        "timeseries": await repo.timeseries(db, days),
        "retention": await repo.retention(db),
        "top_events": await repo.top_events(db, days=7),
        "surfaces": await repo.surface_split(db, days),
        "sources": await repo.source_split(db, days),
        "revenue": await billing.revenue(db, days=days),
        "top_products": await billing.top_products(db, days=days),
        "top_referrers": await growth.top_referrers(db, limit=10),
        "promo_batches": await growth.batch_stats(db),
        # себестоимость рядом с выручкой: маржа должна быть видна одним взглядом
        "llm_costs": await repo.llm_costs(db, days=days),
        "monetization": await repo.monetization_kpis(db, days=days),
        "monetization_v2": await _monetization_v2_dashboard(db, days=days),
    }


async def demo_dashboard(*, days: int = 30) -> dict:
    """Return clearly labelled synthetic KPIs without touching the database."""
    days = max(1, min(int(days), 365))
    today = date.today()
    chart_days = [(today - timedelta(days=days - 1 - i)).isoformat()
                   for i in range(days)]
    active = [0] * days
    questions = [0] * days
    registrations = [0] * days
    stars = [0] * days
    sample_users = [12, 18, 21, 24, 27, 30, 35, 29, 33, 38, 42, 31, 36, 40, 25, 24, 22]
    sample_questions = [18, 26, 33, 41, 45, 49, 55, 52, 58, 61, 66, 60, 64, 70, 73, 78, 82]
    sample_active = [31, 44, 52, 60, 66, 72, 79, 83, 88, 91, 96, 101, 108, 112, 118, 124, 130]
    sample_stars = [300, 500, 700, 800, 900, 650, 750, 850, 1000, 900, 1100,
                    1200, 950, 1250, 1350, 1400, 1456]
    offset = max(0, days - 17)
    for idx, values in enumerate((sample_active, sample_questions,
                                  sample_users, sample_stars)):
        target = (active, questions, registrations, stars)[idx]
        target[offset:] = values[-min(17, days):]

    overview = {
        "users_total": 451, "users_today": 22, "users_7d": 247,
        "users_30d": 451, "onboarded": 389, "subs_active": 164,
        "dau": 130, "wau": 318, "mau": 451, "questions_today": 82,
        "questions_7d": sum(sample_questions[-7:]), "readings_total": 736,
        "readings_7d": 126, "diary_7d": 74, "stars_total": 17056,
        "stars_30d": 17056, "payers": 182, "crystals_outstanding": 8420,
    }
    total = overview["users_total"]
    funnel_values = [("Пришли", 451), ("Прошли знакомство", 389),
                     ("Задали вопрос", 273), ("Вернулись на 2-й день", 196),
                     ("Заплатили", 182)]
    funnel = [{"step": label, "value": value,
               "of_total": round(value * 100 / total, 1)}
              for label, value in funnel_values]
    retention = [{"cohort": chart_days[max(0, days - 17)], "size": 451,
                  "d1": 64.0, "d3": 48.0, "d7": 31.0, "d14": 21.0,
                  "d30": 0.0}]
    return {
        "demo": {"active": True, "label": "ДЕМО · тестовые данные",
                  "note": "Не реальные пользователи, заказы или баланс",
                  "operating_days": 17},
        "overview": overview, "funnel": funnel,
        "activation": {"days": days, "cohort": 451, "steps": []},
        "timeseries": [{"day": day, "active": active[i],
                        "questions": questions[i], "users": registrations[i],
                        "readings": 0, "stars": stars[i]}
                       for i, day in enumerate(chart_days)],
        "retention": retention, "top_events": [], "surfaces": [],
        "sources": [{"source": "Telegram", "users": 451, "payers": 182,
                     "stars": 17056}],
        "revenue": {"stars_total": 17056, "stars_period": 17056,
                    "orders_paid": 182, "orders_period": 182,
                    "payers": 182, "refunds": 0},
        "top_products": [{"sku": "demo_subscription", "title": "Демо-подписка",
                          "sales": 182, "stars": 17056}],
        "top_referrers": [], "promo_batches": [], "llm_costs": {},
        "monetization": {"days": days, "paid_arppu_stars": 94,
                          "paid_payers": 182, "repeat_payers": 130,
                          "repeat_payer_rate": 71.4, "refund_rate": 0.0,
                          "refund_orders": 0},
    }


async def rollup(db, day: str | None = None) -> dict:
    return await repo.rollup_day(db, day)
