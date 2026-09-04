"""Аналитика: события воронки, временные ряды, удержание, агрегаты для админки.

События пишутся из бота и API через `services.analytics.track`. Здесь только
чтение и запись строк — вся интерпретация в сервисном слое и панели.

Колонка `day` дублирует дату из `created_at` намеренно: группировка по
`substr(created_at,1,10)` не может использовать индекс, и на сотнях тысяч
событий дашборд начинал ощутимо тормозить.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone

from ..data.session import transaction, utcnow

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
E_REFERRAL = "referral_joined"
E_MINIAPP_OPEN = "miniapp_open"
E_CHURN_WARN = "expiry_notified"
# Privacy-safe activation/retention milestones. Props for these events must stay
# categorical and never contain user text, memory, birth data or model output.
E_FIRST_RITUAL = "first_ritual"
E_FIRST_QUESTION = "first_question"
E_RETURN_D1 = "return_d1"
E_RETURN_D7 = "return_d7"

# Monetization milestones. These names and props are server-owned; clients cannot
# create arbitrary revenue events or attach payment/content data.
E_PAYWALL_VIEW = "paywall_view"
E_PAYWALL_CHOICE = "paywall_choice"
E_CREDIT_PACK_CHECKOUT_STARTED = "credit_pack_checkout_started"
E_CREDIT_PACK_PAID = "credit_pack_paid"
E_CREDIT_SPENT = "credit_spent"
E_CREDIT_BALANCE_LOW = "credit_balance_low"
E_REPORT_DELIVERED = "report_delivered"
E_REFUND_REQUESTED = "refund_requested"
E_REFUND_COMPLETED = "refund_completed"


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


def _safe_cost_token(value: str | None, *, limit: int = 96) -> str | None:
    if value is None:
        return None
    value = str(value).strip()
    if not value or len(value) > limit:
        return None
    if not all(char.isalnum() or char in "_-.:/" for char in value):
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
            db, "SELECT COUNT(DISTINCT tg_id) FROM events WHERE day>=:since",
            {"since": _ago_day(1)}),
        "wau": await _scalar(
            db, "SELECT COUNT(DISTINCT tg_id) FROM events WHERE day>=:since",
            {"since": _ago_day(7)}),
        "mau": await _scalar(
            db, "SELECT COUNT(DISTINCT tg_id) FROM events WHERE day>=:since",
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
    cohort_sql = (
        "SELECT DISTINCT tg_id FROM events "
        "WHERE name=:cohort_name AND tg_id IS NOT NULL AND created_at>=:since"
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
    total = await _scalar(
        db, "SELECT COUNT(*) FROM users WHERE created_at>=:since",
        {"since": since})
    onboarded = await _scalar(
        db, "SELECT COUNT(*) FROM users WHERE created_at>=:since AND onboarded=1",
        {"since": since})
    asked = await _scalar(
        db, "SELECT COUNT(DISTINCT m.tg_id) FROM messages m JOIN users u "
            "ON u.tg_id=m.tg_id WHERE u.created_at>=:since AND m.is_question=1",
        {"since": since})
    retained = await _scalar(
        db, "SELECT COUNT(*) FROM (SELECT m.tg_id FROM messages m JOIN users u "
            "ON u.tg_id=m.tg_id WHERE u.created_at>=:since AND m.is_question=1 "
            "GROUP BY m.tg_id HAVING COUNT(DISTINCT substr(m.created_at,1,10)) >= 2) "
            "AS retained_users",
        {"since": since})
    paid = await _scalar(
        db, "SELECT COUNT(DISTINCT p.tg_id) FROM payments p JOIN users u "
            "ON u.tg_id=p.tg_id WHERE u.created_at>=:since "
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
        "FROM events WHERE created_at>=:since GROUP BY surface ORDER BY n DESC",
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
