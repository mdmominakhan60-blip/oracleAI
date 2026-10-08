"""Трекинг событий — обёртка, которая никогда не ломает пользовательский путь.

Аналитика полезна, но не важнее ответа клиентке. Если запись события упала
(заблокированная БД, битые props), продукт продолжает работать, а мы видим это
в логах. Поэтому все имена событий и `track` живут здесь, а не вызываются из
хендлеров напрямую.
"""
from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone
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
E_WINBACK_OFFER = repo.E_WINBACK_OFFER
E_REFERRAL = repo.E_REFERRAL
E_MINIAPP_OPEN = repo.E_MINIAPP_OPEN
E_CHURN_WARN = repo.E_CHURN_WARN
E_FIRST_RITUAL = repo.E_FIRST_RITUAL
E_FIRST_QUESTION = repo.E_FIRST_QUESTION
E_RETURN_D1 = repo.E_RETURN_D1
E_RETURN_D7 = repo.E_RETURN_D7
E_RETURN_D30 = repo.E_RETURN_D30
E_PAYWALL_VIEW = repo.E_PAYWALL_VIEW
E_PAYWALL_CHOICE = repo.E_PAYWALL_CHOICE
E_CREDIT_PACK_CHECKOUT_STARTED = repo.E_CREDIT_PACK_CHECKOUT_STARTED
E_CREDIT_PACK_PAID = repo.E_CREDIT_PACK_PAID
E_CREDIT_SPENT = repo.E_CREDIT_SPENT
E_CREDIT_BALANCE_LOW = repo.E_CREDIT_BALANCE_LOW
E_POST_LIMIT = repo.E_POST_LIMIT
E_LOW_BALANCE_SENT = repo.E_LOW_BALANCE_SENT
E_REPORT_DELIVERED = repo.E_REPORT_DELIVERED
E_REFUND_REQUESTED = repo.E_REFUND_REQUESTED
E_REFUND_COMPLETED = repo.E_REFUND_COMPLETED
E_VISIT = repo.E_VISIT
E_SIGNUP = repo.E_SIGNUP
E_ACTIVATION = repo.E_ACTIVATION
E_SESSION_LINKED = repo.E_SESSION_LINKED
E_REPEAT_PAID = repo.E_REPEAT_PAID
E_FEEDBACK_SURVEY_SENT = repo.E_FEEDBACK_SURVEY_SENT
E_FEEDBACK_SURVEY_COMPLETED = repo.E_FEEDBACK_SURVEY_COMPLETED
E_SURVEY_GRANT_ISSUED = repo.E_SURVEY_GRANT_ISSUED


def safe_web_source(value: str | None) -> str | None:
    """Публичная обёртка валидатора web-props (BUS-116): utm/referrer → токен.

    API-слой вызывает отсюда, не из repo: layering presentation→services→repo.
    """
    return repo._safe_web_source(value)

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


async def track_funnel(db, *, name: str, session_id: str,
                       tg_id: int | None = None, surface: str = "web",
                       source: str = "direct", medium: str = "none",
                       campaign: str | None = None, path: str | None = None,
                       activation_action: str | None = None,
                       signup_method: str | None = None) -> bool:
    """Приём funnel-события (EXP-004) без риска для пользовательского пути.

    Публичный эндпоинт: невалидное имя/surface/sid — не ошибка запроса, а
    False; битые события видны по False в ответе, а не 500 на лендинге.
    """
    try:
        return await repo.track_funnel(
            db, name=name, session_id=session_id, tg_id=tg_id, surface=surface,
            source=source, medium=medium, campaign=campaign, path=path,
            activation_action=activation_action, signup_method=signup_method)
    except Exception as e:  # noqa: BLE001
        log.warning("funnel-событие %s не записано: %s", name, e)
        return False


async def track_session_link(db, *, session_id: str | None, tg_id: int,
                             surface: str = "miniapp") -> bool:
    """Мост session→user (BUS-195): best-effort запись при идентификации.

    Вызывается из аутентифицированного пути (/api/me): сбой записи не должен
    ломать ответ, поэтому всё исключение гасится с логом. Дедуп на уровне БД —
    один мост на сессию, повторы безвредны.
    """
    if not session_id:
        return False
    try:
        return await repo.track_session_link(
            db, session_id=session_id, tg_id=tg_id, surface=surface)
    except Exception as e:  # noqa: BLE001
        log.warning("session_linked %s не записан: %s", session_id, e)
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
        # BUS-284 §2.3: счётчики очереди внимания в блоке «сегодня»
        "attention": await _attention_summary(db),
    }


async def _attention_summary(db) -> dict:
    """counts/overdue очереди внимания — для блока «сегодня» в Dashboard.

    Отдельно от ltv_tier.attention_queue: карточки строить не нужно,
    поэтому лимит 1 не режет набор правил — каждая карточка короткая,
    а счётчики считаются по всем сработавшим правилам.
    """
    from ..repo import ltv_tier as ltv_repo

    queue = await ltv_repo.attention_queue(db, limit=1)
    return {"counts": queue["counts"], "overdue": queue["overdue"]}


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


async def backfill(db, days: int = 7) -> list[dict]:
    """Backfill daily_stats for the last N missing days."""
    today = date.today()
    results = []
    for i in range(1, days + 1):
        day = (today - timedelta(days=i)).isoformat()
        results.append(await repo.rollup_day(db, day))
    return results


# ────────────────────────── Аудитория (BUS-230, волна 1) ──────────────────────

#: Сегменты, чья Δ7д вычислима (временная граница входит в предикат).
#: Остальные (событийные/композитные) дают null — R9 BUS-168: «нет данных»,
#: а не ноль, иначе виджет врёт о динамике.
_DELTA_SEGMENTS = {
    "sleeping_14d", "active_7d", "cancelled_recent", "expiring_3d",
    "sleeping_14d_push", "cancelled_5_7d",
}


async def audience_segments(db) -> dict:
    """Таблица сегментов crm-frame §1 для экрана A: имя, размер, Δ7д.

    Единственный источник предикатов — SEGMENTS (users.py), счётчик —
    segment_count: равенство broadcast preview (§3.3 BUS-168) соблюдается
    конструкцией, а не согласованием цифр.
    """
    from ..repo import users as users_repo

    now = datetime.now(timezone.utc)
    week_ago = (now - timedelta(days=7)).isoformat()
    # Границы «оценки 7 дней назад»: окно предиката целиком сдвинуто на -7д,
    # а не только одна из границ (иначе прошлое завышено/занижено → дельта врёт).
    month_ago_past = (now - timedelta(days=37)).isoformat()   # 30-дн. окно на -7д
    in_3d_past = (now - timedelta(days=4)).isoformat()        # «истекает в 3д» на -7д
    five_days_ago_past = (now - timedelta(days=12)).isoformat()  # WB2-окно [5,7]д на -7д
    seven_days_ago_past = (now - timedelta(days=14)).isoformat()

    # BUS-1019: Δ7д-выборка тоже users-таблица — без анти-тестового фильтра
    # синтетика 999xxx/10001/10002 считалась в «прошлом», и дельта врала вниз
    # даже при чистом текущем segment_count.
    from ..repo.ltv_constants import not_synthetic_tg_sql

    segments = []
    for name in users_repo.SEGMENTS:
        count = await users_repo.segment_count(db, name)
        if name in _DELTA_SEGMENTS:
            # Δ7д: сколько клиенток было в сегменте 7 дней назад — предикат
            # со сдвинутой границей. Сегодняшний сегмент — знаменатель.
            if name == "sleeping_14d_push":
                past_where = ("((last_seen IS NULL OR last_seen < :two_weeks_ago) "
                              "AND morning_push = 1)")
                params = {"two_weeks_ago": (now - timedelta(days=21)).isoformat()}
            elif name == "sleeping_14d":
                past_where = ("(last_seen IS NULL OR last_seen < :two_weeks_ago)")
                params = {"two_weeks_ago": (now - timedelta(days=21)).isoformat()}
            elif name == "active_7d":
                past_where = "last_seen >= :from"
                params = {"from": (now - timedelta(days=14)).isoformat()}
            elif name == "cancelled_recent":
                past_where = ("(sub_until IS NOT NULL AND sub_until <= :from "
                              "AND sub_until >= :month_ago)")
                params = {"from": week_ago, "month_ago": month_ago_past}
            elif name == "cancelled_5_7d":
                past_where = ("(sub_until IS NOT NULL AND sub_until <= :upper "
                              "AND sub_until >= :lower)")
                params = {"upper": five_days_ago_past,
                          "lower": seven_days_ago_past}
            else:  # expiring_3d: (now-7d, now-4d], не (now-7d, now+3d]
                past_where = ("sub_until > :from AND sub_until <= :in_3d")
                params = {"from": week_ago, "in_3d": in_3d_past}
            cur = await db.execute(
                "SELECT COUNT(*) c FROM users WHERE status <> 'deleted' "
                f"AND ({past_where}) AND {not_synthetic_tg_sql('users')}", params)
            past = (await cur.fetchone())["c"]
            delta = count - past
        else:
            delta = None
        segments.append({"segment": name, "count": count, "delta_7d": delta})

    return {
        "segments": segments,
        "generated_at": now.isoformat(),
        "data_quality": {"status": "full", "note": None},
    }


async def audience_churn(db) -> dict:
    """Churn-карточки R3 BUS-168: expiring_3d/sleeping_14d с платёжным сплитом.

    Окно берётся из SEGMENTS (users.py) через _segment_sql — тот же предикат,
    что в segment_count таблицы аудитории, поэтому расхождение карточки и
    таблицы невозможно конструкцией (ревью BUS-279: копипаст (now-7d, now+3d]
    давал карточке завышение на истёкших за неделю).
    Privacy §2.3: только агрегаты; категория пользователя (payer/free) —
    денормализованное поле ltv_stars, не PII.
    """
    from ..repo import users as users_repo

    now = datetime.now(timezone.utc)
    cards = []
    for name in ("expiring_3d", "sleeping_14d"):
        where, params = users_repo._segment_sql(name)
        cur = await db.execute(
            "SELECT COUNT(*) total, "
            "SUM(CASE WHEN ltv_stars > 0 THEN 1 ELSE 0 END) payers "
            "FROM users WHERE status <> 'deleted' "
            f"AND ({where})", params)
        row = dict(await cur.fetchone())
        total = row["total"] or 0
        payers = row["payers"] or 0
        cards.append({"segment": name, "total": total,
                      "payers": payers, "free": total - payers})

    return {"cards": cards, "generated_at": now.isoformat()}
