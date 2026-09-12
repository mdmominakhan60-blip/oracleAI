"""Аналитика: события воронки, временные ряды, удержание, агрегаты для админки.

События пишутся из бота и API через `services.analytics.track`. Здесь только
чтение и запись строк — вся интерпретация в сервисном слое и панели.

Колонка `day` дублирует дату из `created_at` намеренно: группировка по
`substr(created_at,1,10)` не может использовать индекс, и на сотнях тысяч
событий дашборд начинал ощутимо тормозить.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta, timezone

from ..data.session import transaction, utcnow
from .ltv_constants import not_synthetic_tg_sql

# Ключевые события воронки — фиксированные имена, чтобы дашборд не разъезжался
# с кодом при опечатке.
E_START = "start"
E_ONBOARD_DONE = "onboard_done"
E_QUESTION = "question"
E_TAROT = "tarot_draw"
E_FORECAST = "forecast_view"
E_LIMIT_HIT = "limit_reached"
E_SHOP_VIEW = "shop_view"
E_INVOICE = "invoice_created"
E_PAID = "payment_success"
E_PROMO = "promo_redeemed"
E_WINBACK_OFFER = "winback_offer_sent"
E_REFERRAL = "referral_joined"
E_MINIAPP_OPEN = "miniapp_open"
E_CHURN_WARN = "expiry_notified"
# Privacy-safe activation/retention milestones. Props for these events must stay
# categorical and never contain user text, memory, birth data or model output.
E_FIRST_RITUAL = "first_ritual"
E_FIRST_QUESTION = "first_question"
E_RETURN_D1 = "return_d1"
E_RETURN_D7 = "return_d7"
E_RETURN_D30 = "return_d30"

E_REPEAT_PAID = "repeat_purchase"

# Monetization milestones. These names and props are server-owned; clients cannot
# create arbitrary revenue events or attach payment/content data.
E_PAYWALL_VIEW = "paywall_view"
E_PAYWALL_CHOICE = "paywall_choice"
E_CREDIT_PACK_CHECKOUT_STARTED = "credit_pack_checkout_started"
E_CREDIT_PACK_PAID = "credit_pack_paid"
E_CREDIT_SPENT = "credit_spent"
E_CREDIT_BALANCE_LOW = "credit_balance_low"
E_POST_LIMIT = "post_limit_sent"
E_LOW_BALANCE_SENT = "low_balance_sent"
E_REPORT_DELIVERED = "report_delivered"
E_REFUND_REQUESTED = "refund_requested"
E_REFUND_COMPLETED = "refund_completed"

# Funnel top-of-funnel events (EXP-004). Пишутся через API приёма (router
# funnel.py) c анонимным session_id до первой идентификации клиента; props
# строго категориальные, без PII — так же, как milestone-события выше.
E_VISIT = "visit"
E_SIGNUP = "signup"
E_ACTIVATION = "activation"

# Мост session→user (BUS-176 §3 G2): серверная запись при первой
# аутентифицированной идентификации анонимной сессии. Оба идентификатора — в
# индексированные колонки (не в props): join воронки по индексу, tg_id в
# дашборд-агрегаты не выводится. Клиентское событие с этим именем
# отбрасывается allowlist'ом router funnel.py.
E_SESSION_LINKED = "session_linked"

# Day-7 опрос (BUS-170 rev 5 §5, словарь 8d33f33). Props категориальные:
# survey_code, delivery_key, bonus_granted, question_count, bonus_kind,
# amount — score и свободный текст в события не пишутся (privacy-правило).
E_FEEDBACK_SURVEY_SENT = "feedback_survey_sent"
E_FEEDBACK_SURVEY_COMPLETED = "feedback_survey_completed"
E_SURVEY_GRANT_ISSUED = "survey_grant_issued"


async def track(db, name: str, tg_id: int | None = None, *,
                props: dict | None = None, surface: str = "bot") -> None:
    now = datetime.now(timezone.utc)
    async with transaction(db):
        await db.execute(
            "INSERT INTO events(tg_id, name, props_json, surface, day, created_at) "
            "VALUES(:tg_id, :name, :props_json, :surface, :day, :created_at)",
            {
                "tg_id": tg_id,
                "name": name,
                "props_json": json.dumps(props, ensure_ascii=False) if props else None,
                "surface": surface,
                "day": now.strftime("%Y-%m-%d"),
                "created_at": now.isoformat(),
            },
        )


async def track_once(db, name: str, tg_id: int, *,
                     props: dict | None = None, surface: str = "miniapp") -> bool:
    """Записывает milestone только один раз для владельца события.

    SELECT и INSERT выполняются в одной транзакции через соединение;
    milestone names не зависят от client-supplied event names и props остаются
    ограниченными вызывающим server-side кодом.
    """
    now = datetime.now(timezone.utc)
    async with transaction(db):
        cur = await db.execute(
            "SELECT 1 FROM events WHERE tg_id=:tg_id AND name=:name LIMIT 1",
            {"tg_id": tg_id, "name": name},
        )
        if await cur.fetchone():
            return False
        await db.execute(
            "INSERT INTO events(tg_id, name, props_json, surface, day, created_at) "
            "VALUES(:tg_id, :name, :props_json, :surface, :day, :created_at)",
            {
                "tg_id": tg_id,
                "name": name,
                "props_json": json.dumps(props, ensure_ascii=False) if props else None,
                "surface": surface,
                "day": now.strftime("%Y-%m-%d"),
                "created_at": now.isoformat(),
            },
        )
    return True


_COST_EVENT_KINDS = {"llm", "pdf", "voice", "tool", "delivery", "refund", "support"}
_COST_CHANNELS = {"bot", "miniapp", "web", "system"}
_COST_STATUSES = {"succeeded", "failed", "delivered", "refunded", "pending"}

# Категориальные props funnel-событий (EXP-004). Allowlist в трёх местах:
# ключи, значения utm/referrer-семейства и формат session_id. Ничего из этого
# не принимает свободный текст пользователя — событие с PII не запишется.
_FUNNEL_EVENT_NAMES = {E_VISIT, E_SIGNUP, E_ACTIVATION}
_FUNNEL_SURFACES = {"web", "bot", "miniapp"}
_FUNNEL_SOURCES = {"organic", "direct", "referral", "tg", "instagram",
                   "reddit", "email", "paid", "unknown"}
_FUNNEL_MEDIUMS = {"organic", "cpc", "social", "email", "referral", "none", "unknown"}
_FUNNEL_ACTIVATION_ACTIONS = {"first_question", "first_ritual", "profile_complete",
                              "daily_forecast"}
_SESSION_ID_LIMIT = 64


def _safe_session_id(value: str | None) -> str | None:
    """sid генерирует клиент (uuid4/случайный токен) и шлёт обратно при retry."""
    if value is None:
        return None
    value = str(value).strip()
    if not value or len(value) > _SESSION_ID_LIMIT:
        return None
    if not all(char.isalnum() or char in "_-." for char in value):
        return None
    return value


async def track_funnel(db, *, name: str, session_id: str, tg_id: int | None = None,
                       surface: str = "web", source: str = "direct",
                       medium: str = "none", campaign: str | None = None,
                       path: str | None = None,
                       activation_action: str | None = None,
                       signup_method: str | None = None) -> bool:
    """Идемпотентная запись funnel-события: одно (session_id, name) навсегда.

    INSERT ... ON CONFLICT DO NOTHING — дедупликация на уровне БД: повторный
    beacon/retry/перезапуск приёма не создаёт дублей. Возвращает True, только
    если строка записана.
    """
    if name not in _FUNNEL_EVENT_NAMES:
        return False
    if surface not in _FUNNEL_SURFACES:
        return False
    safe_session = _safe_session_id(session_id)
    if not safe_session:
        return False
    if source not in _FUNNEL_SOURCES:
        source = "unknown"
    if medium not in _FUNNEL_MEDIUMS:
        medium = "unknown"

    props: dict = {"source": source, "medium": medium}
    if campaign:
        # campaign из utm — короткий ascii-токен, всё прочее отбрасываем.
        campaign = str(campaign).strip()
        if campaign and len(campaign) <= 64 and all(
                char.isalnum() or char in "_-." for char in campaign):
            props["campaign"] = campaign
    if path:
        path = str(path).strip()
        # Путь страницы без query: query несёт нефильтрованные данные и может
        # содержать PII (email в utm и т.п.). Длина ограничена, разделители
        # путей разрешены.
        if path and len(path) <= 128 and all(
                char.isalnum() or char in "/_-." for char in path):
            props["path"] = path
    if name == E_SIGNUP and signup_method:
        method = str(signup_method).strip()
        if method and len(method) <= 32 and all(char.isalnum() or char in "_"
                                                for char in method):
            props["signup_method"] = method
    if name == E_ACTIVATION:
        # action — обязательный prop: activation без ключевого действия
        # бесполезен для KPI «активации ≥25% регистраций».
        if not activation_action or activation_action not in _FUNNEL_ACTIVATION_ACTIONS:
            return False
        props["action"] = activation_action
    if name in (E_SIGNUP, E_ACTIVATION) and tg_id is not None:
        props["linked"] = "1"

    now = datetime.now(timezone.utc)
    async with transaction(db):
        cur = await db.execute(
            "INSERT INTO events(tg_id, name, props_json, surface, session_id, "
            "day, created_at) VALUES(:tg_id, :name, :props_json, :surface, "
            ":session_id, :day, :created_at) "
            # Инференс частичного индекса требует явного предиката.
            "ON CONFLICT (session_id, name) WHERE session_id IS NOT NULL "
            "DO NOTHING",
            {
                "tg_id": tg_id,
                "name": name,
                "props_json": json.dumps(props, ensure_ascii=False),
                "surface": surface,
                "session_id": safe_session,
                "day": now.strftime("%Y-%m-%d"),
                "created_at": now.isoformat(),
            },
        )
        inserted = (cur.rowcount or 0) > 0
    return inserted


async def track_session_link(db, *, session_id: str, tg_id: int,
                             surface: str = "miniapp") -> bool:
    """Мост session→user: одна строка session_linked на (session_id, tg_id).

    Идентификаторы кладутся в колонки (tg_id — в авторскую колонку events,
    не в props), поэтому SQL спеки §2 связывает visit-сессию с пользователем
    простым join, а дедупликация достаётся существующим частичным индексом
    миграции 0008. Невалидный sid — False, не исключение: вызов идёт из
    аутентифицированного пути и не должен его ронять.
    """
    if tg_id is None:
        return False
    safe_session = _safe_session_id(session_id)
    if not safe_session:
        return False
    now = datetime.now(timezone.utc)
    async with transaction(db):
        cur = await db.execute(
            "INSERT INTO events(tg_id, name, surface, session_id, day, created_at) "
            "VALUES(:tg_id, :name, :surface, :session_id, :day, :created_at) "
            "ON CONFLICT (session_id, name) WHERE session_id IS NOT NULL "
            "DO NOTHING",
            {
                "tg_id": tg_id,
                "name": E_SESSION_LINKED,
                "surface": surface,
                "session_id": safe_session,
                "day": now.strftime("%Y-%m-%d"),
                "created_at": now.isoformat(),
            },
        )
        inserted = (cur.rowcount or 0) > 0
    return inserted


def _safe_cost_token(value: str | None, *, limit: int = 96) -> str | None:
    if value is None:
        return None
    value = str(value).strip()
    if not value or len(value) > limit:
        return None
    if not all(char.isalnum() or char in "_-.:/" for char in value):
        return None
    return value


# Web-funnel props (BUS-116): utm/referrer попадают в allowlist по ключу,
# значения — короткие ascii-токены. Всё прочее отбрасывается, PII не пишется.
_WEB_SOURCE_LIMIT = 48
_ASCII_TOKEN_RE = re.compile(r"^[a-z0-9][a-z0-9_\-.]*$")


def _safe_web_source(value: str | None, *, limit: int = _WEB_SOURCE_LIMIT) -> str | None:
    if value is None:
        return None
    value = str(value).strip().lower()
    if not value or len(value) > limit:
        return None
    # isalnum() пропускает юникод, а props должны быть ascii-токенами.
    if not _ASCII_TOKEN_RE.match(value):
        return None
    return value



async def record_product_cost_event(
    db, *, event_kind: str, tg_id: int | None = None, sku: str | None,
    catalog_version: str = "legacy", channel: str = "system",
    purpose: str | None = None, provider: str | None = None,
    model: str | None = None, result_category: str | None = None,
    status: str = "succeeded", units: int = 1, input_tokens: int = 0,
    output_tokens: int = 0, retry_count: int = 0, latency_ms: int = 0,
    duration_ms: int = 0, artifact_bytes: int = 0,
    cost_usd: float | None = None, reference_id: str | None = None,
    order_id: int | None = None, reason: str | None = None,
    price_variant: str | None = None) -> None:
    """Persist server-owned cost evidence without free-form user content."""
    if event_kind not in _COST_EVENT_KINDS:
        raise ValueError("unknown product cost event kind")
    if channel not in _COST_CHANNELS:
        raise ValueError("unknown product cost channel")
    if status not in _COST_STATUSES:
        raise ValueError("unknown product cost status")
    safe_sku = _safe_cost_token(sku) or "unattributed"
    safe_catalog = _safe_cost_token(catalog_version, limit=32) or "legacy"
    safe_purpose = _safe_cost_token(purpose)
    safe_provider = _safe_cost_token(provider, limit=48)
    safe_model = _safe_cost_token(model, limit=96)
    safe_result = _safe_cost_token(result_category, limit=48)
    safe_reference = _safe_cost_token(reference_id, limit=96)
    safe_reason = _safe_cost_token(reason, limit=48)
    safe_price_variant = _safe_cost_token(price_variant, limit=48)

    def numeric(value) -> int:
        return max(0, int(value or 0))

    safe_cost = None if cost_usd is None else max(0.0, float(cost_usd))
    now = datetime.now(timezone.utc)
    async with transaction(db):
        await db.execute(
            "INSERT INTO product_cost_events("
            "tg_id,event_kind,sku,catalog_version,channel,purpose,provider,model,"
            "result_category,status,units,input_tokens,output_tokens,retry_count,"
            "latency_ms,duration_ms,artifact_bytes,cost_usd,reference_id,order_id,"
            "reason,price_variant,day,created_at) "
            "VALUES(:tg_id,:event_kind,:sku,:catalog_version,:channel,:purpose,"
            ":provider,:model,:result_category,:status,:units,:input_tokens,"
            ":output_tokens,:retry_count,:latency_ms,:duration_ms,:artifact_bytes,"
            ":cost_usd,:reference_id,:order_id,:reason,:price_variant,:day,"
            ":created_at)",
            {
                "tg_id": tg_id, "event_kind": event_kind, "sku": safe_sku,
                "catalog_version": safe_catalog, "channel": channel,
                "purpose": safe_purpose, "provider": safe_provider,
                "model": safe_model, "result_category": safe_result,
                "status": status, "units": numeric(units),
                "input_tokens": numeric(input_tokens),
                "output_tokens": numeric(output_tokens),
                "retry_count": numeric(retry_count),
                "latency_ms": numeric(latency_ms),
                "duration_ms": numeric(duration_ms),
                "artifact_bytes": numeric(artifact_bytes),
                "cost_usd": safe_cost, "reference_id": safe_reference,
                "order_id": order_id, "reason": safe_reason,
                "price_variant": safe_price_variant,
                "day": now.strftime("%Y-%m-%d"),
                "created_at": now.isoformat(),
            },
        )


async def record_llm_usage(db, params: dict) -> None:
    """Одна строка журнала llm_usage; интерпретация контекста — в core.llm."""
    async with transaction(db):
        await db.execute(
            "INSERT INTO llm_usage(tg_id, provider, model, purpose, "
            "prompt_tokens, completion_tokens, cost_usd, latency_ms, ok, day, "
            "created_at, sku, catalog_version, subscription_code, included_usage, "
            "crystal_spend, overage) VALUES(:tg_id, :provider, :model, :purpose, "
            ":prompt_tokens, :completion_tokens, :cost_usd, :latency_ms, :ok, "
            ":day, :created_at, :sku, :catalog_version, :subscription_code, "
            ":included_usage, :crystal_spend, :overage)",
            params)


async def _scalar(db, sql: str, params: dict | None = None):
    cur = await db.execute(sql, params or {})
    row = await cur.fetchone()
    return (row[0] if row else 0) or 0


async def prune_analytics(db, days: int = 120, *, batch_size: int = 5_000) -> int:
    """Apply bounded retention in small write transactions.

    Product analytics and LLM cost detail use the requested rolling window.
    Crisis incidents, provider evidence and admin audit have explicit longer or
    shorter windows. Batch deletes reduce writer-lock duration on large tables.
    """
    if batch_size < 1:
        raise ValueError("batch_size должен быть положительным")
    windows = {
        "events": max(1, days),
        "llm_usage": max(1, days),
        "product_cost_events": max(1, days),
        "safety_events": min(max(1, days), 90),
        "webhook_events": max(max(1, days), 180),
        "payment_webhook_failures": max(max(1, days), 180),
        "admin_audit": max(max(1, days), 365),
    }
    primary_keys = {
        "events": "id",
        "llm_usage": "id",
        "product_cost_events": "id",
        "safety_events": "id",
        "webhook_events": "event_id",
        "payment_webhook_failures": "id",
        "admin_audit": "id",
    }
    total = 0
    for table, table_days in windows.items():
        key = primary_keys[table]
        before = (datetime.now(timezone.utc)
                  - timedelta(days=table_days)).isoformat()
        while True:
            async with transaction(db):
                cur = await db.execute(
                    # INVARIANT: table and key are drawn from the fixed dicts
                    # above (no user input); named :params carry the values.
                    f"DELETE FROM {table} WHERE {key} IN ("
                    f"SELECT {key} FROM {table} WHERE created_at < :before "
                    f"ORDER BY {key} LIMIT :batch_size)",
                    {"before": before, "batch_size": batch_size},
                )
                removed = cur.rowcount or 0
            total += removed
            if removed < batch_size:
                break
    return total


def _ago(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def _ago_day(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()


async def overview(db) -> dict:
    """Верхние KPI: люди, активность, контент, деньги."""
    return {
        "users_total": await _scalar(db, "SELECT COUNT(*) FROM users"),
        "users_today": await _scalar(
            db, "SELECT COUNT(*) FROM users WHERE created_at>=:since",
            {"since": _ago(1)}),
        "users_7d": await _scalar(
            db, "SELECT COUNT(*) FROM users WHERE created_at>=:since",
            {"since": _ago(7)}),
        "users_30d": await _scalar(
            db, "SELECT COUNT(*) FROM users WHERE created_at>=:since",
            {"since": _ago(30)}),
        "onboarded": await _scalar(db, "SELECT COUNT(*) FROM users WHERE onboarded=1"),
        "subs_active": await _scalar(
            db, "SELECT COUNT(*) FROM users WHERE sub_until>:now",
            {"now": utcnow()}),
        "dau": await _scalar(
            db, "SELECT COUNT(DISTINCT tg_id) FROM events WHERE day>=:since "
                f"AND {not_synthetic_tg_sql('events')}",
            {"since": _ago_day(1)}),
        "wau": await _scalar(
            db, "SELECT COUNT(DISTINCT tg_id) FROM events WHERE day>=:since "
                f"AND {not_synthetic_tg_sql('events')}",
            {"since": _ago_day(7)}),
        "mau": await _scalar(
            db, "SELECT COUNT(DISTINCT tg_id) FROM events WHERE day>=:since "
                f"AND {not_synthetic_tg_sql('events')}",
            {"since": _ago_day(30)}),
        "questions_today": await _scalar(
            db, "SELECT COUNT(*) FROM messages WHERE is_question=1 "
            "AND created_at>=:since", {"since": _ago(1)}),
        "questions_7d": await _scalar(
            db, "SELECT COUNT(*) FROM messages WHERE is_question=1 "
            "AND created_at>=:since", {"since": _ago(7)}),
        "readings_total": await _scalar(db, "SELECT COUNT(*) FROM tarot_readings"),
        "readings_7d": await _scalar(
            db, "SELECT COUNT(*) FROM tarot_readings WHERE created_at>=:since",
            {"since": _ago(7)}),
        "diary_7d": await _scalar(
            db, "SELECT COUNT(*) FROM diary WHERE created_at>=:since",
            {"since": _ago(7)}),
        "stars_total": await _scalar(
            db, "SELECT SUM(amount_stars) FROM payments WHERE status='succeeded'"),
        "stars_30d": await _scalar(
            db, "SELECT SUM(amount_stars) FROM payments WHERE status='succeeded' "
                "AND created_at>=:since", {"since": _ago(30)}),
        "payers": await _scalar(
            db, "SELECT COUNT(DISTINCT tg_id) FROM payments "
            "WHERE status='succeeded'"),
        "crystals_outstanding": await _scalar(
            db, "SELECT SUM(crystals) FROM users"),
    }


async def activation_funnel(db, days: int = 30) -> dict:
    """Privacy-safe Mini App activation/return funnel by first-open cohort."""
    since = _ago(days)
    # Синтетика (smoke 999xxx, legacy 10001/10002) не считается трафиком (BUS-387).
    cohort_sql = (
        "SELECT DISTINCT tg_id FROM events "
        "WHERE name=:cohort_name AND created_at>=:since "
        f"AND {not_synthetic_tg_sql('events')}"
    )
    cohort = await _scalar(
        db, f"SELECT COUNT(*) FROM ({cohort_sql}) AS cohort",
        {"cohort_name": E_MINIAPP_OPEN, "since": since},
    )
    names = [
        ("first_ritual", E_FIRST_RITUAL),
        ("first_question", E_FIRST_QUESTION),
        ("d1_return", E_RETURN_D1),
        ("d7_return", E_RETURN_D7),
    ]
    steps = []
    for label, event_name in names:
        value = await _scalar(
            db,
            "SELECT COUNT(DISTINCT tg_id) FROM events WHERE name=:event_name "
            "AND tg_id IN (" + cohort_sql + ")",
            {"event_name": event_name, "cohort_name": E_MINIAPP_OPEN, "since": since},
        )
        steps.append({
            "step": label,
            "event": event_name,
            "value": value,
            "of_cohort": round(value * 100 / cohort, 1) if cohort else 0.0,
        })
    return {"days": days, "cohort": cohort, "steps": steps}


async def funnel(db, days: int = 30) -> list[dict]:
    """Воронка: пришла → прошла онбординг → задала вопрос → вернулась → заплатила.

    Считаем по пользователям, зарегистрированным в окне: иначе «заплатившие»
    прошлого года завышали бы конверсию свежего трафика.
    """
    since = _ago(days)
    # Синтетика отсечена на входе в users (BUS-387): зайдёт в users — не
    # считается ни «пришла», ни любым последующим шагом.
    total = await _scalar(
        db, "SELECT COUNT(*) FROM users WHERE created_at>=:since "
            f"AND {not_synthetic_tg_sql('users')}",
        {"since": since})
    onboarded = await _scalar(
        db, "SELECT COUNT(*) FROM users WHERE created_at>=:since AND onboarded=1 "
            f"AND {not_synthetic_tg_sql('users')}",
        {"since": since})
    asked = await _scalar(
        db, "SELECT COUNT(DISTINCT m.tg_id) FROM messages m JOIN users u "
            "ON u.tg_id=m.tg_id WHERE u.created_at>=:since AND m.is_question=1 "
            f"AND {not_synthetic_tg_sql('u')}",
        {"since": since})
    retained = await _scalar(
        db, "SELECT COUNT(*) FROM (SELECT m.tg_id FROM messages m JOIN users u "
            "ON u.tg_id=m.tg_id WHERE u.created_at>=:since AND m.is_question=1 "
            f"AND {not_synthetic_tg_sql('u')} "
            "GROUP BY m.tg_id HAVING COUNT(DISTINCT substr(m.created_at,1,10)) >= 2) "
            "AS retained_users",
        {"since": since})
    paid = await _scalar(
        db, "SELECT COUNT(DISTINCT p.tg_id) FROM payments p JOIN users u "
            "ON u.tg_id=p.tg_id WHERE u.created_at>=:since "
            f"AND {not_synthetic_tg_sql('u')} "
            "AND p.status='succeeded'", {"since": since})

    steps = [("Пришли", total), ("Прошли знакомство", onboarded),
             ("Задали вопрос", asked), ("Вернулись на 2-й день", retained),
             ("Заплатили", paid)]
    out = []
    for title, value in steps:
        out.append({
            "step": title,
            "value": value,
            "of_total": round(value * 100 / total, 1) if total else 0.0,
        })
    return out


async def timeseries(db, days: int = 30) -> list[dict]:
    """Ряды по дням для графиков: регистрации, вопросы, расклады, Stars."""
    start = (date.today() - timedelta(days=days - 1)).isoformat()

    async def by_day(sql: str, params: dict) -> dict:
        cur = await db.execute(sql, params)
        return {r[0]: r[1] for r in await cur.fetchall()}

    users = await by_day(
        "SELECT substr(created_at,1,10) d, COUNT(*) FROM users "
        "WHERE substr(created_at,1,10)>=:start GROUP BY d",
        {"start": start})
    questions = await by_day(
        "SELECT substr(created_at,1,10) d, COUNT(*) FROM messages "
        "WHERE is_question=1 AND substr(created_at,1,10)>=:start GROUP BY d",
        {"start": start})
    readings = await by_day(
        "SELECT substr(created_at,1,10) d, COUNT(*) FROM tarot_readings "
        "WHERE substr(created_at,1,10)>=:start GROUP BY d",
        {"start": start})
    stars = await by_day(
        "SELECT substr(created_at,1,10) d, SUM(amount_stars) FROM payments "
        "WHERE status='succeeded' AND substr(created_at,1,10)>=:start GROUP BY d",
        {"start": start})
    active = await by_day(
        "SELECT day d, COUNT(DISTINCT tg_id) FROM events WHERE day>=:start "
        f"AND {not_synthetic_tg_sql('events')} "
        "GROUP BY day",
        {"start": start})
    promos = await by_day(
        "SELECT substr(created_at,1,10) d, COUNT(*) FROM promo_redemptions "
        "WHERE substr(created_at,1,10)>=:start GROUP BY d",
        {"start": start})

    out = []
    for i in range(days):
        day = (date.today() - timedelta(days=days - 1 - i)).isoformat()
        out.append({"day": day,
                    "users": users.get(day, 0),
                    "questions": questions.get(day, 0),
                    "readings": readings.get(day, 0),
                    "stars": stars.get(day, 0) or 0,
                    "promos": promos.get(day, 0),
                    "active": active.get(day, 0)})
    return out


async def retention(db, cohort_days: int = 7) -> list[dict]:
    """Удержание по недельным когортам: доля вернувшихся на день 1/3/7/14/30."""
    out = []
    age_days_sql = (
        "EXTRACT(EPOCH FROM (e.created_at::timestamptz "
        "- u.created_at::timestamptz)) / 86400"
        if getattr(db, "is_postgres", False)
        else "julianday(e.created_at) - julianday(u.created_at)"
    )
    for week in range(cohort_days):
        start = (date.today() - timedelta(days=(week + 1) * 7)).isoformat()
        end = (date.today() - timedelta(days=week * 7)).isoformat()
        size = await _scalar(
            db, "SELECT COUNT(*) FROM users WHERE substr(created_at,1,10)>=:start "
                "AND substr(created_at,1,10)<:end",
            {"start": start, "end": end})
        if not size:
            continue
        row = {"cohort": start, "size": size}
        for day_n in (1, 3, 7, 14, 30):
            back = await _scalar(
                db,
                # INVARIANT: age_days_sql is a fixed dialect-select above, not user input.
                "SELECT COUNT(DISTINCT u.tg_id) FROM users u JOIN events e "
                "ON e.tg_id=u.tg_id WHERE substr(u.created_at,1,10)>=:start "
                "AND substr(u.created_at,1,10)<:end "
                f"AND {age_days_sql} BETWEEN :day_low AND :day_high",
                {"start": start, "end": end,
                 "day_low": day_n, "day_high": day_n + 1})
            row[f"d{day_n}"] = round(back * 100 / size, 1)
        out.append(row)
    return out


async def top_events(db, days: int = 7, limit: int = 25) -> list[dict]:
    cur = await db.execute(
        "SELECT name, COUNT(*) n, COUNT(DISTINCT tg_id) users FROM events "
        "WHERE created_at>=:since GROUP BY name ORDER BY n DESC LIMIT :limit",
        {"since": _ago(days), "limit": limit})
    return [dict(r) for r in await cur.fetchall()]


async def surface_split(db, days: int = 30) -> list[dict]:
    """Где живёт активность — в боте или в Mini App. Решает, куда вкладываться."""
    cur = await db.execute(
        "SELECT COALESCE(surface,'bot') surface, COUNT(*) n, "
        "COUNT(DISTINCT tg_id) users "
        "FROM events WHERE created_at>=:since "
        f"AND {not_synthetic_tg_sql('events')} "
        "GROUP BY surface ORDER BY n DESC",
        {"since": _ago(days)})
    return [dict(r) for r in await cur.fetchall()]


async def user_events(db, tg_id: int, limit: int = 100) -> list[dict]:
    cur = await db.execute(
        "SELECT name, props_json, surface, created_at FROM events "
        "WHERE tg_id=:tg_id ORDER BY id DESC LIMIT :limit",
        {"tg_id": tg_id, "limit": limit})
    return [dict(r) for r in await cur.fetchall()]


async def source_split(db, days: int = 30) -> list[dict]:
    """Каналы привлечения: сколько пришло и сколько из них заплатило."""
    cur = await db.execute(
        "SELECT COALESCE(source,'organic') source, COUNT(*) users, "
        "SUM(CASE WHEN ltv_stars > 0 THEN 1 ELSE 0 END) payers, "
        "COALESCE(SUM(ltv_stars),0) stars FROM users WHERE created_at>=:since "
        "GROUP BY source ORDER BY users DESC",
        {"since": _ago(days)})
    return [dict(r) for r in await cur.fetchall()]


# ─────────────────────── себестоимость и безопасность ────────────────────────

async def llm_costs(db, days: int = 30) -> dict:
    """Сколько стоит продукт в токенах.

    Вся юнит-экономика построена на цифре «≤ $2.5 на платящую в месяц» — без
    этого запроса она остаётся предположением. `per_paying` считаем от числа
    активных подписок: именно они окупают всех остальных.
    """
    since = _ago(days)
    total_cost = await _scalar(
        db, "SELECT SUM(cost_usd) FROM llm_usage WHERE created_at>=:since",
        {"since": since})
    calls = await _scalar(
        db, "SELECT COUNT(*) FROM llm_usage WHERE created_at>=:since",
        {"since": since})
    failed = await _scalar(
        db, "SELECT COUNT(*) FROM llm_usage WHERE ok=0 AND created_at>=:since",
        {"since": since})
    subs = await _scalar(
        db, "SELECT COUNT(*) FROM users WHERE sub_until>:now",
        {"now": utcnow()})

    cur = await db.execute(
        "SELECT purpose, COUNT(*) calls, COALESCE(SUM(prompt_tokens),0) tokens_in, "
        "COALESCE(SUM(completion_tokens),0) tokens_out, "
        "COALESCE(SUM(cost_usd),0) cost, "
        "COALESCE(AVG(latency_ms),0) avg_ms FROM llm_usage "
        "WHERE created_at>=:since GROUP BY purpose ORDER BY cost DESC",
        {"since": since})
    by_purpose = [dict(r) for r in await cur.fetchall()]

    cur = await db.execute(
        "SELECT provider, model, COUNT(*) calls, COALESCE(SUM(cost_usd),0) cost "
        "FROM llm_usage WHERE created_at>=:since GROUP BY provider, model "
        "ORDER BY cost DESC LIMIT 10", {"since": since})
    by_model = [dict(r) for r in await cur.fetchall()]

    return {
        "days": days,
        "cost_usd": round(total_cost, 4),
        "calls": calls,
        "failed": failed,
        "fail_rate": round(failed * 100 / calls, 1) if calls else 0.0,
        "per_paying_usd": round(total_cost / subs, 3) if subs else 0.0,
        "by_purpose": by_purpose,
        "by_model": by_model,
        # Латентность рядом с деньгами (F-3): деградация ответов видна там же,
        # где считают их себестоимость.
        "latency": await latency_percentiles(db, days=days),
    }


async def product_cost_kpis(db, days: int = 30) -> dict:
    """Aggregate variable cost and delivery coverage by trusted product labels.

    Gross Stars are joined only for paid server orders. Net revenue and contribution
    remain unavailable until settlement, tax, refunds and fixed-cost inputs exist.
    """
    since = _ago(days)
    cur = await db.execute(
        "SELECT sku, channel, COUNT(*) event_count, "
        "SUM(CASE WHEN cost_usd IS NOT NULL THEN 1 ELSE 0 END) costed_events, "
        "COALESCE(SUM(cost_usd),0) variable_cost_usd, "
        "COALESCE(SUM(input_tokens),0) input_tokens, "
        "COALESCE(SUM(output_tokens),0) output_tokens, "
        "COALESCE(SUM(retry_count),0) retry_count, "
        "COALESCE(SUM(CASE WHEN event_kind='delivery' THEN 1 ELSE 0 END),0) deliveries, "
        "COALESCE(SUM(CASE WHEN status IN ('failed','pending') THEN 1 ELSE 0 END),0) failures "
        "FROM product_cost_events WHERE created_at>=:since GROUP BY sku, channel "
        "ORDER BY variable_cost_usd DESC, event_count DESC",
        {"since": since})
    rows = [dict(row) for row in await cur.fetchall()]
    paid_cur = await db.execute(
        "SELECT COALESCE(sku, kind) sku, COALESCE(surface, 'system') channel, "
        "COALESCE(SUM(amount_stars),0) gross_stars FROM orders "
        "WHERE status='paid' AND paid_at>=:since "
        "GROUP BY COALESCE(sku, kind), COALESCE(surface, 'system')",
        {"since": since})
    paid_by_product_channel = {
        (row[0], row[1]): int(row[2] or 0)
        for row in await paid_cur.fetchall()
    }
    for row in rows:
        row["gross_booking_stars"] = paid_by_product_channel.get(
            (row["sku"], row["channel"]), 0)
        row["variable_cost_usd"] = round(float(row["variable_cost_usd"] or 0), 6)
        row["cost_coverage_pct"] = round(
            int(row["costed_events"] or 0) * 100 / int(row["event_count"] or 1), 1)
    total_events = sum(int(row["event_count"] or 0) for row in rows)
    costed_events = sum(int(row["costed_events"] or 0) for row in rows)
    total_cost = sum(float(row["variable_cost_usd"] or 0) for row in rows)
    unattributed = sum(
        float(row["variable_cost_usd"] or 0) for row in rows
        if row["sku"] == "unattributed")
    return {
        "days": days,
        "status": "estimated_requires_settlement_inputs",
        "event_count": total_events,
        "costed_event_count": costed_events,
        "cost_coverage_pct": round(costed_events * 100 / total_events, 1)
        if total_events else 0.0,
        "variable_cost_usd": round(total_cost, 6),
        "unattributed_cost_usd": round(unattributed, 6),
        "net_revenue_estimate": None,
        "contribution_margin_estimate": None,
        "by_product": rows,
        "required_inputs": [
            "provider_settlement_realization", "tax_and_withholding_rate",
            "refund_rate_by_channel", "voice_tool_cost", "support_cost",
            "fixed_opex", "paid_marketing",
        ],
    }


async def monetization_kpis(db, days: int = 30) -> dict:
    """Revenue/cost KPI block with an explicit no-fabrication net boundary.

    Stars are reported in their native unit. Net revenue and contribution margin
    stay unavailable until settlement/tax/refund assumptions are reviewed; a
    gross number must never be presented as profit.
    """
    since = _ago(days)
    gross_stars = await _scalar(
        db, "SELECT SUM(amount_stars) FROM payments "
        "WHERE status='succeeded' AND created_at>=:since", {"since": since})
    payers = await _scalar(
        db, "SELECT COUNT(DISTINCT tg_id) FROM payments "
        "WHERE status='succeeded' AND created_at>=:since", {"since": since})
    paid_orders = await _scalar(
        db, "SELECT COUNT(*) FROM orders WHERE status='paid' AND paid_at>=:since",
        {"since": since})
    refunded_orders = await _scalar(
        db, "SELECT COUNT(*) FROM orders WHERE status='refunded' "
        "AND created_at>=:since", {"since": since})
    repeat_payers = await _scalar(
        db, "SELECT COUNT(*) FROM (SELECT tg_id FROM payments "
        "WHERE status='succeeded' AND created_at>=:since GROUP BY tg_id "
        "HAVING COUNT(*)>=2) AS repeat_users", {"since": since})

    async def event_count(name: str) -> int:
        return await _scalar(
            db, "SELECT COUNT(*) FROM events WHERE name=:name AND created_at>=:since",
            {"name": name, "since": since})

    by_sku_cur = await db.execute(
        "SELECT COALESCE(sku, kind) sku, COUNT(*) orders, "
        "COUNT(DISTINCT tg_id) payers, COALESCE(SUM(amount_stars),0) gross_stars "
        "FROM orders WHERE status='paid' AND paid_at>=:since "
        "GROUP BY COALESCE(sku, kind) ORDER BY gross_stars DESC, orders DESC",
        {"since": since})
    by_sku = [dict(row) for row in await by_sku_cur.fetchall()]

    cost_cur = await db.execute(
        "SELECT purpose, provider, model, COUNT(*) calls, "
        "COALESCE(SUM(cost_usd),0) cost_usd, "
        "COALESCE(AVG(latency_ms),0) avg_latency_ms "
        "FROM llm_usage WHERE created_at>=:since GROUP BY purpose, provider, model "
        "ORDER BY cost_usd DESC", {"since": since})
    provider_cost = [dict(row) for row in await cost_cur.fetchall()]
    llm_cost = await _scalar(
        db, "SELECT SUM(cost_usd) FROM llm_usage WHERE created_at>=:since",
        {"since": since})

    return {
        "days": days,
        "status": "estimated_requires_settlement_inputs",
        "gross_booking_stars": int(gross_stars),
        "paid_orders": int(paid_orders),
        "paid_payers": int(payers),
        "paid_arppu_stars": round(gross_stars / payers, 2) if payers else 0.0,
        "repeat_payers": int(repeat_payers),
        "repeat_payer_rate": round(repeat_payers * 100 / payers, 1) if payers else 0.0,
        "refund_orders": int(refunded_orders),
        "refund_rate": round(refunded_orders * 100 / paid_orders, 1)
        if paid_orders else 0.0,
        "credit_pack_checkout_started": await event_count(E_CREDIT_PACK_CHECKOUT_STARTED),
        "credit_pack_paid": await event_count(E_CREDIT_PACK_PAID),
        "credit_spent": await event_count(E_CREDIT_SPENT),
        "reports_delivered": await event_count(E_REPORT_DELIVERED),
        "llm_variable_cost_usd": round(float(llm_cost), 6),
        "net_revenue_estimate": None,
        "contribution_margin_estimate": None,
        "required_inputs": [
            "effective_platform_realization", "tax_and_withholding_rate",
            "refund_rate_by_channel", "voice_tool_cost", "support_referral_cost",
            "fixed_opex", "paid_marketing",
        ],
        "by_sku": by_sku,
        "provider_cost_by_purpose": provider_cost,
        "product_cost": await product_cost_kpis(db, days=days),
    }


async def safety_summary(db, days: int = 30, limit: int = 100) -> dict:
    """Return aggregate safety telemetry without crisis content or identity."""
    since = _ago(days)
    cur = await db.execute(
        "SELECT category, action, COUNT(*) n FROM safety_events "
        "WHERE created_at>=:since GROUP BY category, action ORDER BY n DESC",
        {"since": since})
    summary = [dict(r) for r in await cur.fetchall()]
    cur = await db.execute(
        "SELECT category, action, created_at FROM safety_events "
        "WHERE created_at>=:since ORDER BY id DESC LIMIT :limit",
        {"since": since, "limit": limit})
    return {"summary": summary,
            "recent": [dict(r) for r in await cur.fetchall()],
            "redacted": True}


async def safety_events(db, days: int = 30, limit: int = 100) -> dict:
    """Restricted safety incidents for an explicitly authorized reviewer."""
    since = _ago(days)
    cur = await db.execute(
        "SELECT category, action, COUNT(*) n FROM safety_events "
        "WHERE created_at>=:since GROUP BY category, action ORDER BY n DESC",
        {"since": since})
    summary = [dict(r) for r in await cur.fetchall()]
    cur = await db.execute(
        "SELECT s.tg_id, s.category, s.action, s.excerpt, s.created_at, u.name "
        "FROM safety_events s LEFT JOIN users u ON u.tg_id = s.tg_id "
        "WHERE s.created_at>=:since ORDER BY s.id DESC LIMIT :limit",
        {"since": since, "limit": limit})
    return {"summary": summary,
            "recent": [dict(r) for r in await cur.fetchall()],
            "restricted": True}


async def rollup_day(db, day: str | None = None) -> dict:
    """Складывает снимок метрик за день в `daily_stats` — история не зависит от
    того, что старые события когда-нибудь подчистят ретеншеном."""
    day = day or date.today().isoformat()
    stats = {
        "users_new": await _scalar(
            db, "SELECT COUNT(*) FROM users WHERE substr(created_at,1,10)=:day",
            {"day": day}),
        "active": await _scalar(
            db, "SELECT COUNT(DISTINCT tg_id) FROM events WHERE day=:day",
            {"day": day}),
        "questions": await _scalar(
            db, "SELECT COUNT(*) FROM messages WHERE is_question=1 "
                "AND substr(created_at,1,10)=:day", {"day": day}),
        "readings": await _scalar(
            db, "SELECT COUNT(*) FROM tarot_readings "
                "WHERE substr(created_at,1,10)=:day", {"day": day}),
        "stars": await _scalar(
            db, "SELECT SUM(amount_stars) FROM payments WHERE status='succeeded' "
                "AND substr(created_at,1,10)=:day", {"day": day}),
        "orders": await _scalar(
            db, "SELECT COUNT(*) FROM orders WHERE status='paid' "
                "AND substr(paid_at,1,10)=:day", {"day": day}),
    }
    async with transaction(db):
        await db.execute(
            "INSERT INTO daily_stats(day, stats_json, updated_at) "
            "VALUES(:day, :stats_json, :updated_at) "
            "ON CONFLICT (day) DO UPDATE SET stats_json=excluded.stats_json, "
            "updated_at=excluded.updated_at",
            {"day": day,
             "stats_json": json.dumps(stats, ensure_ascii=False),
             "updated_at": utcnow()})
    return stats


async def goal_split(db) -> dict:
    """Разбивка аудитории по мотивации (G-11 BUS-175): GROUP BY goal.

    Пустой goal → bucket «unset»: NULL в SQL нельзя показать в графике,
    а потерять часть аудитории — исказить все доли. Deleted исключены
    (privacy, как в segment_count). payers — доля платящих в bucket'е.
    """
    cur = await db.execute(
        "SELECT COALESCE(NULLIF(goal, ''), 'unset') AS goal, COUNT(*) users, "
        "SUM(CASE WHEN ltv_stars > 0 THEN 1 ELSE 0 END) payers "
        "FROM users WHERE status <> 'deleted' "
        "GROUP BY COALESCE(NULLIF(goal, ''), 'unset') "
        "ORDER BY users DESC")
    rows = [dict(r) for r in await cur.fetchall()]
    total = sum(r["users"] for r in rows)
    for r in rows:
        r["share_pct"] = round(r["users"] * 100 / total, 1) if total else 0.0
    return {"total": total, "goals": rows}


async def latency_percentiles(db, days: int = 30) -> dict:
    """Перцентили латентности LLM p50/p95 (F-3 BUS-166).

    percentile_cont — PostgreSQL-only: это единственный бэкенд продукта
    (см. app/data/session.py). Окно по created_at, как в llm_costs.
    R9 BUS-168: нет данных в окне → no_data, никогда не ноль — ноль
    выглядел бы как «мгновенные ответы» и скрыл бы деградацию.
    """
    since = _ago(days)
    calls = await _scalar(
        db, "SELECT COUNT(*) FROM llm_usage WHERE created_at>=:since AND ok=1",
        {"since": since})
    if not calls:
        return {"p50_ms": None, "p95_ms": None,
                "status": "no_data", "note": "llm_usage пуст в окне"}
    # Алиасы обязательны: две безымянные percentile_cont дают один ключ
    # row._mapping ("percentile_cont") — вторая колонка теряется.
    cur = await db.execute(
        "SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY latency_ms) AS p50, "
        "percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms) AS p95 "
        "FROM llm_usage WHERE created_at>=:since AND ok=1",
        {"since": since})
    row = await cur.fetchone()
    p50, p95 = row["p50"], row["p95"]
    return {
        "p50_ms": int(round(p50)) if p50 is not None else None,
        "p95_ms": int(round(p95)) if p95 is not None else None,
        "status": "full",
        "calls": calls,
    }


# ─────────────── владелец: воронка / retention / деньги / сегменты ───────────
# BUS-176 §4 (BUS-229). Все функции PostgreSQL-only и возвращают только
# агрегаты: tg_id наружу не идёт (fail-closed, словарь событий).
# Окно дат — по индексированной колонке events.day (TEXT ISO, лексикографика);
# для orders.paid_at — префикс-сравнение [from, to+1d), как в monetization_kpis.

_FUNNEL_STEPS = [
    ("visit", "visit", "session"),
    ("signup", "signup", "session"),
    ("activation", "activation", "session"),
    ("paywall_view", "paywall_view", "user"),
    ("checkout", "invoice_created/credit_pack_checkout_started", "user"),
    ("paid", "orders.paid", "user"),
    ("report_delivered", "report_delivered", "user"),
]


def _props_filters(source: str | None, surface: str | None,
                   campaign: str | None) -> str:
    """WHERE-фрагмент по категориальным props funnel-событий (алиас e).

    props_json — TEXT; для funnel-событий track_funnel всегда пишет валидный
    JSON или NULL, каст ::jsonb безопасен (NULL->>'k' -> NULL).
    """
    parts = []
    if source:
        parts.append("AND e.props_json::jsonb->>'source' = :f_source")
    if surface:
        parts.append("AND e.surface = :f_surface")
    if campaign:
        parts.append("AND e.props_json::jsonb->>'campaign' = :f_campaign")
    return " ".join(parts)


async def owner_funnel(db, *, date_from: str, date_to: str,
                       source: str | None = None, surface: str | None = None,
                       campaign: str | None = None) -> dict:
    """Visit-based воронка по спеке BUS-176 §4.1.

    Когорта — visit-сессии окна (§2.1 правило 4), не registrations-юзеры.
    Этапы visit/signup/activation — DISTINCT session_id; этапы от paywall
    глубже — DISTINCT tg_id через мост session_linked (G2): смена unit —
    задокументированный стык. Фильтры source/surface/campaign применяются
    к props событийных шагов и к users.source для user-шагов; campaign
    наследуется user-шагами от visit-когорты.
    """
    params: dict = {"from": date_from, "to": date_to}
    if source:
        params["f_source"] = source
    if surface:
        params["f_surface"] = surface
    if campaign:
        params["f_campaign"] = campaign
    ev = _props_filters(source, surface, campaign)
    user_source = "AND u.source = :f_source" if source else ""
    user_surface = "AND e.surface = :f_surface" if surface else ""

    sql = f"""
    WITH visit_sessions AS (
        SELECT DISTINCT e.session_id FROM events e
        WHERE e.name='visit' AND e.day >= :from AND e.day <= :to
          AND e.session_id IS NOT NULL {ev}
    ),
    visit_users AS (
        SELECT DISTINCT e.tg_id FROM events e
        JOIN visit_sessions v ON e.session_id = v.session_id
        WHERE e.name = 'session_linked' AND e.tg_id IS NOT NULL
    ),
    user_scope AS (
        SELECT u.tg_id FROM users u JOIN visit_users vu ON vu.tg_id = u.tg_id
        WHERE 1=1 {user_source}
    )
    SELECT
        (SELECT COUNT(*) FROM visit_sessions) AS visit,
        (SELECT COUNT(DISTINCT e.session_id) FROM events e
         JOIN visit_sessions v ON e.session_id = v.session_id
         WHERE e.name='signup' AND e.day >= :from AND e.day <= :to {ev}) AS signup,
        (SELECT COUNT(DISTINCT e.session_id) FROM events e
         JOIN visit_sessions v ON e.session_id = v.session_id
         WHERE e.name='activation' AND e.day >= :from AND e.day <= :to {ev}) AS activation,
        (SELECT COUNT(DISTINCT e.tg_id) FROM events e
         JOIN user_scope s ON s.tg_id = e.tg_id
         WHERE e.name='paywall_view' AND e.day >= :from AND e.day <= :to
         {user_surface}) AS paywall_view,
        (SELECT COUNT(DISTINCT e.tg_id) FROM events e
         JOIN user_scope s ON s.tg_id = e.tg_id
         WHERE e.name IN ('invoice_created', 'credit_pack_checkout_started')
         AND e.day >= :from AND e.day <= :to {user_surface}) AS checkout,
        (SELECT COUNT(DISTINCT o.tg_id) FROM orders o
         JOIN user_scope s ON s.tg_id = o.tg_id
         WHERE o.status='paid' AND o.paid_at >= :from
           AND o.paid_at < :to_exclusive) AS paid,
        (SELECT COUNT(DISTINCT e.tg_id) FROM events e
         JOIN user_scope s ON s.tg_id = e.tg_id
         WHERE e.name='report_delivered' AND e.day >= :from AND e.day <= :to
         {user_surface}) AS report_delivered
    """
    to_exclusive = (date.fromisoformat(date_to) + timedelta(days=1)).isoformat()
    cur = await db.execute(sql, {**params, "to_exclusive": to_exclusive})
    row = dict(await cur.fetchone())

    steps = []
    prev = None
    for step, event, unit in _FUNNEL_STEPS:
        value = int(row[step] or 0)
        steps.append({
            "step": step, "event": event, "value": value, "unit": unit,
            # Нулевой знаменатель → 0.0 (§2.1 правило 3), не null.
            "of_prev": round(value * 100 / prev, 1) if prev else
            (None if prev is None else 0.0),
            "of_start": round(value * 100 / int(row["visit"] or 0), 1)
            if row["visit"] else 0.0,
        })
        prev = value or None

    visit_n = int(row["visit"] or 0)
    top_n = visit_n + int(row["signup"] or 0) + int(row["activation"] or 0)
    deep_n = int(row["paywall_view"] or 0) + int(row["paid"] or 0)
    if top_n and deep_n:
        quality = {"status": "full", "note": None}
    elif deep_n:
        quality = {"status": "unreliable",
                   "note": "visit/signup/activation не деплоированы (BUS-144); "
                           "верх воронки пуст при непустом низе"}
    elif top_n:
        quality = {"status": "partial",
                   "note": "низ воронки пуст в окне — событий paywall/paid нет"}
    else:
        quality = {"status": "no_data",
                   "note": "в окне нет событий воронки"}

    return {
        "period": {"from": date_from, "to": date_to},
        "filters": {"source": source, "surface": surface,
                    "campaign": campaign},
        "steps": steps,
        "data_quality": quality,
    }


async def owner_retention(db, *, date_from: str, date_to: str,
                          granularity: str = "day") -> dict:
    """Milestone-когорты по дню первого miniapp_open (BUS-176 §4.2).

    d1/d7 — milestone return_d1/return_d7 (COUNT DISTINCT tg_id: поздний
    возврат пишет оба milestone в один день). d30 до G1 (BUS-196) —
    activity_fallback: любая событийная активность в [d0+30, d0+31).
    matured — календарная зрелость окна; для week-когорт — только когда
    прошла вся неделя (иначе свежая неделя занизит rate). Когорты старше
    120 дней отдают null: events подчистит ретеншен.
    """
    if granularity == "week":
        d0_expr = "to_char(date_trunc('week', c.d0::date), 'YYYY-MM-DD')"
    else:
        d0_expr = "c.d0"
    sql = f"""
    WITH cohort AS (
        SELECT e.tg_id, MIN(e.day) AS d0 FROM events e
        WHERE e.name='miniapp_open' AND e.tg_id IS NOT NULL
          AND e.day >= :from AND e.day <= :to
        GROUP BY e.tg_id
    ),
    cohort_g AS (
        SELECT {d0_expr} AS bucket, c.tg_id, c.d0 FROM cohort c
    ),
    marks AS (
        SELECT g.bucket, g.tg_id,
            MAX(CASE WHEN e.name='return_d1' THEN 1 ELSE 0 END) AS d1,
            MAX(CASE WHEN e.name='return_d7' THEN 1 ELSE 0 END) AS d7,
            MAX(CASE WHEN e.day::date BETWEEN g.d0::date + 30
                                          AND g.d0::date + 30
                     THEN 1 ELSE 0 END) AS d30_activity
        FROM cohort_g g LEFT JOIN events e ON e.tg_id = g.tg_id
        GROUP BY g.bucket, g.tg_id
    )
    SELECT bucket, COUNT(*) AS size,
           COALESCE(SUM(d1), 0) AS d1, COALESCE(SUM(d7), 0) AS d7,
           COALESCE(SUM(d30_activity), 0) AS d30
    FROM marks GROUP BY bucket ORDER BY bucket
    """
    cur = await db.execute(sql, {"from": date_from, "to": date_to})
    rows = [dict(r) for r in await cur.fetchall()]

    today = date.today()
    retention_horizon = today - timedelta(days=120)

    def matured_for(bucket: str, day_n: int) -> bool:
        b = date.fromisoformat(bucket)
        if granularity == "week":
            return today >= b + timedelta(days=6 + day_n)
        return today >= b + timedelta(days=day_n)

    def mark(bucket: str, size: int, value: int, day_n: int) -> dict:
        if not matured_for(bucket, day_n):
            return {"value": None, "rate": None, "matured": False}
        if date.fromisoformat(bucket) < retention_horizon:
            return {"value": None, "rate": None, "matured": True}
        return {"value": value,
                "rate": round(value * 100 / size, 1) if size else 0.0,
                "matured": True}

    cohorts = []
    for row in rows:
        bucket, size = row["bucket"], int(row["size"])
        cohorts.append({
            "day": bucket,
            "size": size,
            "d1": mark(bucket, size, int(row["d1"] or 0), 1),
            "d7": mark(bucket, size, int(row["d7"] or 0), 7),
            **{"d30": {
                **mark(bucket, size, int(row["d30"] or 0), 30),
                "method": "activity_fallback", "event": None,
            }},
        })

    pruned = [c["day"] for c in cohorts if c["d1"]["value"] is None
              and c["d1"]["matured"]]
    quality = {"status": "full", "note": None}
    if pruned:
        quality = {"status": "partial",
                   "note": "когорты старше 120 дней: события подчистены "
                           f"ретеншеном ({len(pruned)} когорт)"}
    return {
        "period": {"from": date_from, "to": date_to},
        "cohort_anchor": "miniapp_open",
        "granularity": granularity,
        "cohorts": cohorts,
        "data_quality": quality,
    }


async def owner_revenue(db, *, date_from: str, date_to: str,
                        sku: str | None = None) -> dict:
    """Gross-деньги в Stars (BUS-176 §4.3): семантика monetization_kpis.

    gross — payments.succeeded; orders/payers/by_sku — orders.paid по paid_at.
    Net revenue не считается (fail-closed словаря): null до settlement-входов.
    """
    params: dict = {"from": date_from, "to": date_to}
    sku_filter = ""
    if sku:
        params["sku"] = sku
        sku_filter = "AND COALESCE(sku, kind) = :sku"

    gross = await _scalar(
        db, "SELECT COALESCE(SUM(amount_stars),0) FROM payments "
            "WHERE status='succeeded' AND created_at >= :from "
            "AND created_at < :to_exclusive",
        {**params,
         "to_exclusive": (date.fromisoformat(date_to) + timedelta(days=1)).isoformat()})
    payers = await _scalar(
        db, "SELECT COUNT(DISTINCT tg_id) FROM payments "
            "WHERE status='succeeded' AND created_at >= :from "
            "AND created_at < :to_exclusive",
        {**params,
         "to_exclusive": (date.fromisoformat(date_to) + timedelta(days=1)).isoformat()})
    paid_orders = await _scalar(
        db, f"SELECT COUNT(*) FROM orders WHERE status='paid' "
            f"AND paid_at >= :from AND paid_at < :to_exclusive {sku_filter}",
        {**params,
         "to_exclusive": (date.fromisoformat(date_to) + timedelta(days=1)).isoformat()})
    refunded = await _scalar(
        db, f"SELECT COUNT(*) FROM orders WHERE status='refunded' "
            f"AND created_at >= :from AND created_at < :to_exclusive {sku_filter}",
        {**params,
         "to_exclusive": (date.fromisoformat(date_to) + timedelta(days=1)).isoformat()})
    repeat = await _scalar(
        db, "SELECT COUNT(*) FROM (SELECT tg_id FROM payments "
            "WHERE status='succeeded' AND created_at >= :from "
            "AND created_at < :to_exclusive GROUP BY tg_id HAVING COUNT(*)>=2) "
            "AS repeat_users",
        {**params,
         "to_exclusive": (date.fromisoformat(date_to) + timedelta(days=1)).isoformat()})

    cur = await db.execute(
        f"SELECT substr(paid_at,1,10) AS day, COALESCE(SUM(amount_stars),0) AS gross, "
        f"COUNT(*) AS orders, COUNT(DISTINCT tg_id) AS payers "
        f"FROM orders WHERE status='paid' AND paid_at >= :from "
        f"AND paid_at < :to_exclusive {sku_filter} "
        f"GROUP BY substr(paid_at,1,10) ORDER BY day",
        {**params,
         "to_exclusive": (date.fromisoformat(date_to) + timedelta(days=1)).isoformat()})
    by_day = {r["day"]: dict(r) for r in await cur.fetchall()}

    timeseries = []
    d = date.fromisoformat(date_from)
    last = date.fromisoformat(date_to)
    while d <= last:
        key = d.isoformat()
        row = by_day.get(key)
        timeseries.append({
            "day": key,
            "gross_stars": int(row["gross"] or 0) if row else 0,
            "orders": int(row["orders"] or 0) if row else 0,
            "payers": int(row["payers"] or 0) if row else 0,
        })
        d += timedelta(days=1)

    cur = await db.execute(
        f"SELECT COALESCE(sku, kind) AS sku, COUNT(*) AS orders, "
        f"COUNT(DISTINCT tg_id) AS payers, "
        f"COALESCE(SUM(amount_stars),0) AS gross_stars "
        f"FROM orders WHERE status='paid' AND paid_at >= :from "
        f"AND paid_at < :to_exclusive {sku_filter} "
        f"GROUP BY COALESCE(sku, kind) ORDER BY gross_stars DESC, orders DESC",
        {**params,
         "to_exclusive": (date.fromisoformat(date_to) + timedelta(days=1)).isoformat()})
    by_sku = [{**dict(r), "gross_stars": int(r["gross_stars"] or 0)}
              for r in await cur.fetchall()]

    return {
        "period": {"from": date_from, "to": date_to},
        "totals": {
            "gross_booking_stars": int(gross),
            "paid_orders": int(paid_orders),
            "payers": int(payers),
            "arppu_stars": round(gross / payers, 2) if payers else 0.0,
            "repeat_payer_rate": round(repeat * 100 / payers, 1) if payers else 0.0,
            "refund_rate": round(refunded * 100 / paid_orders, 1)
            if paid_orders else 0.0,
            "net_revenue_estimate": None,
            "net_revenue_note": "requires settlement inputs (CFO)",
        },
        "timeseries": timeseries,
        "by_sku": by_sku,
        "data_quality": {"status": "full", "note": None},
    }


_LIFECYCLE_DEFS = [
    ("new", "u.created_at >= :cutoff_new"),
    ("onboarded", "u.onboarded = 1"),
    ("paying", "u.sub_until > :now"),
    ("churned", "u.last_seen IS NOT NULL AND u.last_seen < :cutoff_churned"),
    ("dormant", "(u.last_seen IS NULL OR u.last_seen < :cutoff_dormant)"),
]


async def owner_segments(db, *, by: str, date_from: str | None = None,
                         date_to: str | None = None) -> dict:
    """Сегменты аудитории (BUS-176 §4.4). by=source|tier|surface|lifecycle.

    payers = ltv_stars > 0 (паттерн source_split §2.4). Анти-reid: сегменты
    < 5 users агрегируются в other. В lifecycle сегменты-признаки могут
    пересекаться, поэтому sum(share_pct) > 100 — это честно и задокументировано.
    """
    if by == "surface":
        # Событийный разрез: окно по events.day, users = DISTINCT tg_id.
        params: dict = {}
        window_sql = ""
        if date_from:
            window_sql += "AND e.day >= :window_from "
            params["window_from"] = date_from
        if date_to:
            window_sql += "AND e.day <= :window_to "
            params["window_to"] = date_to
        cur = await db.execute(
            "SELECT COALESCE(e.surface, 'bot') AS key, COUNT(*) AS events, "
            "COUNT(DISTINCT e.tg_id) AS users, "
            "COUNT(DISTINCT CASE WHEN u.ltv_stars > 0 THEN e.tg_id END) AS payers "
            "FROM events e LEFT JOIN users u ON u.tg_id = e.tg_id "
            f"WHERE e.tg_id IS NOT NULL {window_sql}"
            f"AND {not_synthetic_tg_sql('e')} "
            "GROUP BY COALESCE(e.surface, 'bot') ORDER BY events DESC",
            params)
        rows = [dict(r) for r in await cur.fetchall()]
    else:
        params = {"now": utcnow(),
                  "cutoff_new": _ago(7),
                  "cutoff_churned": _ago(14),
                  "cutoff_dormant": _ago(30)}
        window_sql = ""
        if date_from:
            window_sql += "AND u.created_at >= :window_from "
            params["window_from"] = date_from
        if date_to:
            window_sql += "AND u.created_at < :window_to "
            params["window_to"] = (date.fromisoformat(date_to) + timedelta(days=1)).isoformat()

        if by == "source":
            cur = await db.execute(
                "SELECT COALESCE(NULLIF(u.source, ''), 'unknown') AS key, "
                "COUNT(*) AS users, "
                "SUM(CASE WHEN u.ltv_stars > 0 THEN 1 ELSE 0 END) AS payers, "
                "COALESCE(SUM(u.ltv_stars), 0) AS ltv_stars "
                "FROM users u WHERE u.status <> 'deleted' " + window_sql +
                "GROUP BY COALESCE(NULLIF(u.source, ''), 'unknown') "
                "ORDER BY users DESC",
                params)
            rows = [dict(r) for r in await cur.fetchall()]
        elif by == "tier":
            cur = await db.execute(
                "SELECT COALESCE(s.tier_code, 'free') AS key, COUNT(*) AS users, "
                "SUM(CASE WHEN u.ltv_stars > 0 THEN 1 ELSE 0 END) AS payers, "
                "COALESCE(SUM(u.ltv_stars), 0) AS ltv_stars, "
                "SUM(CASE WHEN u.sub_until > :now THEN 1 ELSE 0 END) AS active_subs "
                "FROM users u LEFT JOIN subscription_state s ON s.tg_id = u.tg_id "
                "WHERE u.status <> 'deleted' " + window_sql +
                "GROUP BY COALESCE(s.tier_code, 'free') ORDER BY users DESC",
                params)
            rows = [dict(r) for r in await cur.fetchall()]
        elif by == "lifecycle":
            # Один проход по users: сегменты — признаки (§2.4), могут
            # пересекаться; payers/ltv считаются в том же проходе через CASE.
            payer_cases = ", ".join(
                f"COUNT(CASE WHEN ({cond}) AND u.ltv_stars > 0 THEN 1 END) "
                f"AS seg_{name}_payers, "
                f"COALESCE(SUM(CASE WHEN ({cond}) AND u.ltv_stars > 0 "
                f"THEN u.ltv_stars END), 0) AS seg_{name}_ltv"
                for name, cond in _LIFECYCLE_DEFS)
            user_cases = ", ".join(
                f"COUNT(CASE WHEN {cond} THEN 1 END) AS seg_{name}"
                for name, cond in _LIFECYCLE_DEFS)
            cur = await db.execute(
                "SELECT " + user_cases + ", " + payer_cases +
                " FROM users u WHERE u.status <> 'deleted' " + window_sql,
                params)
            agg = dict(await cur.fetchone())
            rows = [{"key": name,
                     "users": int(agg[f"seg_{name}"] or 0),
                     "payers": int(agg[f"seg_{name}_payers"] or 0),
                     "ltv_stars": int(agg[f"seg_{name}_ltv"] or 0)}
                    for name, _cond in _LIFECYCLE_DEFS]
        else:
            raise ValueError(f"unsupported segment dimension: {by}")

    total = sum(int(r["users"] or 0) for r in rows)
    small = [r for r in rows if int(r["users"] or 0) < 5]
    big = [r for r in rows if int(r["users"] or 0) >= 5]
    if small:
        merged = {"key": "other", "users": 0, "payers": 0, "ltv_stars": 0}
        if by == "surface":
            merged["events"] = 0
        if by == "tier":
            merged["active_subs"] = 0
        for r in small:
            merged["users"] += int(r.get("users") or 0)
            merged["payers"] += int(r.get("payers") or 0)
            merged["ltv_stars"] += int(r.get("ltv_stars") or 0)
            if by == "surface":
                merged["events"] += int(r.get("events") or 0)
            if by == "tier":
                merged["active_subs"] += int(r.get("active_subs") or 0)
        rows = big + [merged]
    for r in rows:
        r["users"] = int(r["users"] or 0)
        r["payers"] = int(r.get("payers") or 0)
        r["ltv_stars"] = int(r.get("ltv_stars") or 0)
        r["share_pct"] = round(r["users"] * 100 / total, 1) if total else 0.0
        if by in ("source", "tier", "surface"):
            r["payer_rate_pct"] = (round(r["payers"] * 100 / r["users"], 1)
                                   if r["users"] else 0.0)

    return {
        "period": {"from": date_from, "to": date_to},
        "by": by,
        "total": total,
        "segments": rows,
        "data_quality": {"status": "full", "note": None},
    }


#: Ключи сценариев волны 3 = kinds из deliveries (дедуп цепочек). Вспомогательные
#: kinds (winback2_code, guardrail, feedback_survey) — не сценарии (контракт §3).
SCENARIO_KEYS = ("welcome_chain", "onboard_nudge", "reactivate",
                 "winback2", "post_limit", "low_balance")

_FREE_PAID_CONVERT_EVENTS = "('payment_success','credit_pack_paid')"


async def owner_scenarios(db, *, date_from: str, date_to: str,
                          scenario: str | None = None) -> dict:
    """Карточки CRM-сценариев R7 (BUS-264): вошло / дошло / конверсия / стопы.

    Ключ карточки = kind из deliveries. «Дошло» — DISTINCT tg_id по kind со
    status='sent' за окно (forbidden не дошёл — BUS-308). «Вошло» — когорта
    входа в сегмент по триггеру цепочки. Конверсия — milestone-события после
    входа; события цепочек не добавляем (постановка §2).

    R9-гэпы (контракт §4, правила шейпа): карточка с неснятым гэпом в
    конверсионной части отдаёт data_status='no_data' + no_data_reason;
    зависимая часть — null, НЕ ноль. Счётчики, от гэпа не зависящие,
    остаются числами: reactivate — только конверсия под G-1 (атрибуция
    push→open разорвана); winback2 — payback-доля под G-2 (renewal; поле
    payback до G-2 отсутствует, redemption-счётчик — не гэп, считается).

    last_seen/sub_until мутируют (возврат/продление стирают прошлое), поэтому
    исторические когорты reactivate/winback2 восстанавливаются по deliveries:
    у reactivate ключ r1:{YYYY-MM} пишется при первом касании цикла (~вход в
    сегмент), у winback2 key = sub_until на момент оффера.
    """
    keys = [scenario] if scenario else list(SCENARIO_KEYS)
    to_exclusive = (date.fromisoformat(date_to) + timedelta(days=1)).isoformat()
    base = {"from": date_from, "to_exclusive": to_exclusive}

    async def _one(sql: str, params: dict) -> dict:
        cur = await db.execute(sql, params)
        row = await cur.fetchone()
        return dict(row) if row else {}

    async def delivery_counts(kind: str) -> dict:
        try:
            r = await _one(
                "SELECT COUNT(DISTINCT CASE WHEN d.status='sent' THEN d.tg_id END) "
                "AS reached, "
                "COUNT(DISTINCT CASE WHEN d.status='forbidden' THEN d.tg_id END) "
                "AS forbidden, "
                "COUNT(DISTINCT CASE WHEN d.status='failed' THEN d.tg_id END) "
                "AS failed "
                "FROM deliveries d WHERE d.kind=:kind "
                "AND d.created_at >= :from AND d.created_at < :to_exclusive",
                {"kind": kind, **base})
            return {"reached": int(r.get("reached") or 0),
                    "forbidden": int(r.get("forbidden") or 0),
                    "failed": int(r.get("failed") or 0)}
        except Exception:  # noqa: BLE001
            # Схема без колонки status (миграции до 0012) — нейтрально: любая
            # запись считается доставленной (fallback already_sent, контракт §6).
            r = await _one(
                "SELECT COUNT(DISTINCT d.tg_id) AS reached "
                "FROM deliveries d WHERE d.kind=:kind "
                "AND d.created_at >= :from AND d.created_at < :to_exclusive",
                {"kind": kind, **base})
            return {"reached": int(r.get("reached") or 0),
                    "forbidden": 0, "failed": 0}

    async def one_card(kind: str) -> dict:
        dl = await delivery_counts(kind)

        if kind == "welcome_chain":
            # Когорта: onboard_done в окне. Стоп §1 — первое first-событие
            # (проверка на существование, без времени). Конверсия —
            # first-value после своего последнего onboard_done.
            r = await _one(
                "SELECT COUNT(*) AS entered, "
                "COUNT(CASE WHEN EXISTS (SELECT 1 FROM events f "
                "  WHERE f.tg_id=u.tg_id AND f.name IN "
                "  ('first_ritual','first_question')) THEN 1 END) AS exited, "
                "COUNT(CASE WHEN EXISTS (SELECT 1 FROM events f "
                "  WHERE f.tg_id=u.tg_id AND f.name IN "
                "  ('first_ritual','first_question') "
                "  AND f.created_at > (SELECT COALESCE(MAX(e2.created_at), "
                "    '1970-01-01T00:00:00+00:00') FROM events e2 "
                "    WHERE e2.tg_id=u.tg_id AND e2.name='onboard_done')) "
                "  THEN 1 END) AS converted "
                "FROM users u WHERE u.status <> 'deleted' "
                "AND EXISTS (SELECT 1 FROM events e WHERE e.tg_id=u.tg_id "
                "AND e.name='onboard_done' AND e.created_at >= :from "
                "AND e.created_at < :to_exclusive)",
                base)
        elif kind == "onboard_nudge":
            # Когорта: ПЕРВОЕ start-событие в окне. Стоп — онбординг завершён
            # (onboard_done; контракт §4 — выход по событию, в проде флаг
            # onboarded=1 и событие атомарны, onboarding.py:779). Конверсия —
            # onboard_done после первого start.
            r = await _one(
                "SELECT COUNT(*) AS entered, "
                "COUNT(CASE WHEN EXISTS (SELECT 1 FROM events f "
                "  WHERE f.tg_id=u.tg_id AND f.name='onboard_done') "
                "  THEN 1 END) AS exited, "
                "COUNT(CASE WHEN EXISTS (SELECT 1 FROM events f "
                "  WHERE f.tg_id=u.tg_id AND f.name='onboard_done' "
                "  AND f.created_at > (SELECT COALESCE(MIN(s.created_at), "
                "    '1970-01-01T00:00:00+00:00') FROM events s "
                "    WHERE s.tg_id=u.tg_id AND s.name='start')) "
                "  THEN 1 END) AS converted "
                "FROM users u WHERE u.status <> 'deleted' "
                "AND EXISTS (SELECT 1 FROM events e WHERE e.tg_id=u.tg_id "
                "AND e.name='start' AND e.created_at >= :from "
                "AND e.created_at < :to_exclusive) "
                "AND NOT EXISTS (SELECT 1 FROM events s WHERE s.tg_id=u.tg_id "
                "AND s.name='start' AND s.created_at < :from)",
                base)
        elif kind == "reactivate":
            # Когорта: R1-доставки в окне — durable-маркер входа в сегмент
            # (fallback-вариант r1:{месяц}:fallback тоже касание — его пишет
            # scheduler.py:1095; повторным входом не считаем, у одного юзера
            # один цикл за месяц). Выход: вернулась (last_seen свежее R1) или
            # сон перевалил за 28д (ушла из окна отбора).
            r = await _one(
                "SELECT COUNT(DISTINCT d.tg_id) AS entered, "
                "COUNT(DISTINCT CASE WHEN u.last_seen > d.created_at "
                "  OR u.last_seen < :sleep_max THEN d.tg_id END) AS exited "
                "FROM deliveries d JOIN users u ON u.tg_id=d.tg_id "
                "WHERE d.kind='reactivate' AND d.key LIKE 'r1:%' "
                "AND d.created_at >= :from AND d.created_at < :to_exclusive",
                {"sleep_max": _ago(28), **base})
        elif kind == "winback2":
            # Когорта (контракт §3): sub_until в окне, уже истёк, тёплый
            # winback видел (expiry_notified=2) — плюс durable-хвост из
            # deliveries (key = sub_until на момент оффера: продлившие
            # теряют след в users, но не в журнале). Выход: подписка снова
            # активна (продлила).
            r = await _one(
                "SELECT COUNT(*) AS entered, "
                "COUNT(CASE WHEN u.sub_until > :now THEN 1 END) AS exited "
                "FROM (SELECT tg_id FROM users "
                "  WHERE status <> 'deleted' AND sub_until IS NOT NULL "
                "  AND sub_until >= :from AND sub_until < :to_exclusive "
                "  AND sub_until < :now AND expiry_notified=2 "
                "  UNION "
                "  SELECT d.tg_id FROM deliveries d WHERE d.kind='winback2' "
                "  AND d.key >= :from AND d.key < :to_exclusive) s "
                "JOIN users u ON u.tg_id=s.tg_id",
                {"now": utcnow(), **base})
        else:  # post_limit / low_balance — событийные триггеры
            ev_name = ("limit_reached" if kind == "post_limit"
                       else "credit_balance_low")
            # Когорта: триггерные события в окне. Конверсия — покупка после
            # своего триггера. Выход — 7д-стоп: триггеру больше 7 дней,
            # покупки так и не было (цепочка отпускает).
            r = await _one(
                "SELECT COUNT(*) AS entered, "
                "COUNT(CASE WHEN e.created_at < :cutoff_7d "
                "  AND NOT EXISTS (SELECT 1 FROM events p "
                "    WHERE p.tg_id=e.tg_id AND p.name IN "
                f"    {_FREE_PAID_CONVERT_EVENTS} "
                "    AND p.created_at > e.created_at) THEN 1 END) AS exited, "
                "COUNT(CASE WHEN EXISTS (SELECT 1 FROM events p "
                "  WHERE p.tg_id=e.tg_id AND p.name IN "
                f"  {_FREE_PAID_CONVERT_EVENTS} "
                "  AND p.created_at > e.created_at) THEN 1 END) AS converted "
                "FROM events e WHERE e.name=:ev AND e.tg_id IS NOT NULL "
                "AND e.created_at >= :from AND e.created_at < :to_exclusive",
                {"ev": ev_name, "cutoff_7d": _ago(7), **base})

        entered = int(r.get("entered") or 0)
        exited = int(r.get("exited") or 0)
        converted_events = r.get("converted")
        converted = (int(converted_events)
                     if converted_events is not None else None)

        # ── конверсия по kind ──
        if kind == "reactivate":
            converted = None          # G-1
        elif kind == "winback2":
            conv = await _one(
                "SELECT COUNT(DISTINCT e.tg_id) AS n FROM events e "
                "WHERE e.name='promo_redeemed' AND e.tg_id IS NOT NULL "
                "AND e.props_json::jsonb->>'batch' LIKE 'winback_%' "
                "AND e.created_at >= :from AND e.created_at < :to_exclusive",
                base)
            converted = int(conv.get("n") or 0)
        elif kind in ("welcome_chain", "onboard_nudge",
                      "post_limit", "low_balance"):
            pass                       # уже посчитано в когортном запросе

        gap = {"reactivate": "G-1", "winback2": "G-2"}.get(kind)
        rate = (round(converted / entered, 2)
                if (converted is not None and entered >= 5) else None)
        card = {"key": kind,
                "entered": entered,
                "reached": dl["reached"],
                "converted": converted,
                "conversion_rate": rate,
                "stops": {"forbidden": dl["forbidden"],
                          "segment_exit": exited,
                          "other": dl["failed"]}}
        if gap:
            if gap == "G-1":
                card["converted"] = None
                card["conversion_rate"] = None
            card["data_status"] = "no_data"
            card["no_data_reason"] = gap
        else:
            card["data_status"] = "ok"
        return card

    cards = [await one_card(k) for k in keys]
    return {"period": {"from": date_from, "to": date_to},
            "scenarios": cards}
