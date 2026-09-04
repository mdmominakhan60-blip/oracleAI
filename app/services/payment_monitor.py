"""Безопасный мониторинг платёжного контура.

Сервис намеренно отделён от billing: он только читает состояние, сохраняет
агрегированный snapshot без PII/raw webhook payload и отправляет owner alert
при переходе состояния. Выдача прав, изменение балансов и обработка платежей
здесь невозможны.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
from urllib.parse import urlsplit

from aiohttp import ClientSession, ClientTimeout

from ..config import settings
from ..repo import content
from . import cryptobot, telegram

log = logging.getLogger("oracle.payment_monitor")

SETTING_KEY = "system.payment_monitor"
STALE_PENDING_HOURS = 2
ALERT_COOLDOWN_HOURS = 6
DEFAULT_NOTIFICATION_PREFS = {
    "degraded_cooldown_hours": 6,
    "critical_cooldown_hours": 1,
    "quiet_hours_start": "23:00",
    "quiet_hours_end": "07:00",
    "secondary_enabled": False,
}


def _now(value: datetime | None = None) -> datetime:
    return value or datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _safe_dashboard_url(value: str) -> str | None:
    parsed = urlsplit(value or "")
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.password:
        return None
    return value[:500]


async def _scalar(db, sql: str, params: dict | tuple = ()) -> int:
    cur = await db.execute(sql, params)
    row = await cur.fetchone()
    return int((row[0] if row else 0) or 0)


async def _webhook_activity(db, since: str) -> dict:
    cur = await db.execute(
        "SELECT provider, COUNT(*) AS n, MAX(created_at) AS last_at "
        "FROM webhook_events WHERE created_at>=:since GROUP BY provider",
        {"since": since})
    return {
        str(row["provider"] or "unknown"): {
            "events_24h": int(row["n"] or 0),
            "last_event_at": row["last_at"],
        }
        for row in await cur.fetchall()
    }


async def _webhook_failures(db, since: str) -> dict:
    cur = await db.execute(
        "SELECT provider, COUNT(*) AS n FROM payment_webhook_failures "
        "WHERE created_at>=:since GROUP BY provider", {"since": since})
    return {str(row["provider"] or "unknown"): int(row["n"] or 0)
            for row in await cur.fetchall()}


async def _webhook_timeline(db, since: str, limit: int = 30) -> list[dict]:
    """Return safe recent webhook facts without IDs, payloads or PII."""
    cur = await db.execute(
        "SELECT provider, kind, created_at FROM webhook_events "
        "WHERE created_at>=:since ORDER BY created_at DESC LIMIT :limit",
        {"since": since, "limit": limit})
    rows = [{"provider": str(row["provider"] or "unknown")[:32],
             "event": str(row["kind"] or "received")[:48],
             "status": "received", "at": row["created_at"]}
            for row in await cur.fetchall()]
    cur = await db.execute(
        "SELECT provider, code, status_code, created_at FROM payment_webhook_failures "
        "WHERE created_at>=:since ORDER BY created_at DESC LIMIT :limit",
        {"since": since, "limit": limit})
    rows.extend({"provider": str(row["provider"] or "unknown")[:32],
                 "event": str(row["code"] or "failure")[:48],
                 "status": "failed", "status_code": int(row["status_code"] or 0),
                 "at": row["created_at"]}
                for row in await cur.fetchall())
    rows.sort(key=lambda item: str(item.get("at") or ""), reverse=True)
    return rows[:limit]


async def notification_preferences(db) -> dict:
    value = await content.get_setting(db, "system.payment_notifications")
    result = dict(DEFAULT_NOTIFICATION_PREFS)
    if isinstance(value, dict):
        for key in result:
            if key in value:
                result[key] = value[key]
    for key in ("degraded_cooldown_hours", "critical_cooldown_hours"):
        try:
            result[key] = max(1, min(168, int(result[key])))
        except (TypeError, ValueError):
            result[key] = DEFAULT_NOTIFICATION_PREFS[key]
    for key in ("quiet_hours_start", "quiet_hours_end"):
        raw = str(result[key])
        try:
            hour, minute = (int(part) for part in raw.split(":"))
            valid_clock = len(raw) == 5 and raw[2] == ":" and 0 <= hour <= 23 and 0 <= minute <= 59
        except (TypeError, ValueError):
            valid_clock = False
        if not valid_clock:
            result[key] = DEFAULT_NOTIFICATION_PREFS[key]
    result["secondary_enabled"] = result["secondary_enabled"] is True
    result["secondary_configured"] = bool(settings.payment_alert_secondary_url)
    return result


async def save_notification_preferences(db, updates: dict) -> dict:
    current = await notification_preferences(db)
    for key in DEFAULT_NOTIFICATION_PREFS:
        if key in updates:
            current[key] = updates[key]
    # Never persist derived configuration state.
    current.pop("secondary_configured", None)
    await content.set_setting(db, "system.payment_notifications", current)
    return await notification_preferences(db)


def _in_quiet_hours(checked: datetime, prefs: dict) -> bool:
    def minutes(raw: str) -> int:
        hour, minute = (int(part) for part in raw.split(":"))
        return hour * 60 + minute
    try:
        start, end = minutes(prefs["quiet_hours_start"]), minutes(prefs["quiet_hours_end"])
    except (KeyError, TypeError, ValueError):
        return False
    current = checked.hour * 60 + checked.minute
    if start == end:
        return False
    return current >= start or current < end if start > end else start <= current < end


async def _database_checks(db, now: datetime) -> dict:
    since = _iso(now - timedelta(hours=24))
    stale_before = _iso(now - timedelta(hours=STALE_PENDING_HOURS))
    webhook_activity = await _webhook_activity(db, since)
    failures = await _webhook_failures(db, since)
    timeline = await _webhook_timeline(db, since)

    stale_pending = await _scalar(
        db, "SELECT COUNT(*) FROM orders WHERE status='pending' AND created_at<:stale_before",
        {"stale_before": stale_before})
    failed_orders = await _scalar(
        db, "SELECT COUNT(*) FROM orders WHERE status='failed' AND created_at>=:since",
        {"since": since})
    orphan_payments = await _scalar(
        db, "SELECT COUNT(*) FROM payments p LEFT JOIN orders o ON o.id=p.order_id "
        "WHERE o.id IS NULL")
    paid_without_payment = await _scalar(
        db, "SELECT COUNT(*) FROM orders o LEFT JOIN payments p ON p.order_id=o.id "
        "AND p.status='succeeded' WHERE o.status='paid' AND p.id IS NULL")
    duplicate_paid_orders = await _scalar(
        db, "SELECT COUNT(*) FROM (SELECT order_id FROM payments "
        "WHERE status='succeeded' AND order_id IS NOT NULL GROUP BY order_id "
        "HAVING COUNT(*)>1) subq")
    ledger_mismatches = await _scalar(
        db, "SELECT COUNT(*) FROM users u JOIN crystal_ledger l ON l.id=("
        "SELECT MAX(l2.id) FROM crystal_ledger l2 WHERE l2.tg_id=u.tg_id) "
        "WHERE u.crystals != l.balance")

    return {
        "pending_orders_stale": stale_pending,
        "failed_orders_24h": failed_orders,
        "webhook_events_24h": webhook_activity,
        "webhook_failures_24h": failures,
        "webhook_timeline": timeline,
        "reconciliation": {
            "orphan_payments": orphan_payments,
            "paid_orders_without_payment": paid_without_payment,
            "duplicate_paid_orders": duplicate_paid_orders,
            "crystal_ledger_mismatches": ledger_mismatches,
        },
    }


async def _provider_checks(db, now: datetime, *, external: bool) -> dict:
    since = _iso(now - timedelta(hours=24))
    activity = await _webhook_activity(db, since)
    providers: dict[str, dict] = {
        "telegram_stars": {
            "configured": bool(settings.bot_token),
            "transport": "bot_polling",
            "status": "ok" if settings.bot_token else "not_configured",
            "dashboard_url": _safe_dashboard_url(settings.telegram_stars_dashboard_url),
            "payments_24h": await _scalar(
                db, "SELECT COUNT(*) FROM payments WHERE provider='telegram_stars' "
                "AND status='succeeded' AND created_at>=:since", {"since": since}),
        },
        "cryptobot": {
            "configured": bool(settings.cryptobot_api_token),
            "transport": "crypto_pay_webhook",
            "status": "ok" if settings.cryptobot_api_token else "not_configured",
            "dashboard_url": _safe_dashboard_url(settings.cryptobot_dashboard_url),
            "events_24h": activity.get("cryptobot", {}).get("events_24h", 0),
            "last_event_at": activity.get("cryptobot", {}).get("last_event_at"),
        },
        "paddle": {
            "configured": bool(settings.paddle_webhook_secret),
            "transport": "paddle_webhook",
            "status": "ok" if settings.paddle_webhook_secret else "not_configured",
            "dashboard_url": _safe_dashboard_url(settings.paddle_dashboard_url),
            "events_24h": activity.get("paddle", {}).get("events_24h", 0),
            "last_event_at": activity.get("paddle", {}).get("last_event_at"),
        },
    }

    if external and settings.cryptobot_api_token:
        try:
            balances = await cryptobot.get_balance()
            providers["cryptobot"]["balances"] = [
                {"asset": str(item.get("currency_code") or "")[:16],
                 "available": str(item.get("available") or "0")[:64],
                 "onhold": str(item.get("onhold") or "0")[:64]}
                for item in balances if isinstance(item, dict)
            ]
        except Exception as exc:  # noqa: BLE001
            providers["cryptobot"]["status"] = "degraded"
            providers["cryptobot"]["balance_error"] = "provider_unavailable"
            log.warning("Crypto Pay health check failed: %s", type(exc).__name__)
    elif settings.cryptobot_api_token:
        providers["cryptobot"]["balances"] = []

    return providers


def _overall_status(db_checks: dict, providers: dict) -> str:
    reconciliation = db_checks["reconciliation"]
    if any(reconciliation.values()):
        return "critical"
    if db_checks["pending_orders_stale"] or db_checks["failed_orders_24h"]:
        return "degraded"
    if any(item.get("status") == "degraded" for item in providers.values()):
        return "degraded"
    return "ok"


async def build_snapshot(db, *, now: datetime | None = None,
                         external: bool = False) -> dict:
    checked = _now(now)
    db_checks = await _database_checks(db, checked)
    providers = await _provider_checks(db, checked, external=external)
    return {
        "status": _overall_status(db_checks, providers),
        "checked_at": _iso(checked),
        "stale_pending_threshold_hours": STALE_PENDING_HOURS,
        "checks": db_checks,
        "providers": providers,
    }


async def latest(db) -> dict | None:
    value = await content.get_setting(db, SETTING_KEY)
    return value if isinstance(value, dict) else None


def _alert_text(snapshot: dict, *, recovered: bool = False) -> str:
    status = snapshot.get("status")
    if recovered:
        title = "✅ Платёжный контур восстановлен"
    else:
        title = "🚨 Платёжный мониторинг: " + ("CRITICAL" if status == "critical" else "DEGRADED")
    checks = snapshot.get("checks") or {}
    recon = checks.get("reconciliation") or {}
    return (
        f"{title}\n"
        f"Состояние: {status}\n"
        f"Зависшие заказы: {checks.get('pending_orders_stale', 0)}\n"
        f"Ошибки заказов за 24 ч: {checks.get('failed_orders_24h', 0)}\n"
        f"Ошибки webhook за 24 ч: {sum((checks.get('webhook_failures_24h') or {}).values())}\n"
        f"Аномалии сверки: {sum(recon.values())}\n"
        f"Проверено: {snapshot.get('checked_at')}"
    )


async def run(bot, db, *, now: datetime | None = None) -> dict:
    """Run one bounded check, save only aggregate state and alert on transitions."""
    snapshot = await build_snapshot(db, now=now, external=True)
    previous = await latest(db)
    prefs = await notification_preferences(db)
    previous_status = previous.get("status") if previous else None
    previous_alert_at = previous.get("last_alert_at") if previous else None
    current = dict(snapshot)
    current["last_alert_at"] = previous_alert_at

    checked = _now(now)
    should_alert = False
    recovered = previous_status in {"critical", "degraded"} and snapshot["status"] == "ok"
    current["notification_preferences"] = {
        key: value for key, value in prefs.items() if key != "secondary_configured"
    }
    if previous_status is not None and previous_status != snapshot["status"]:
        should_alert = True
    elif snapshot["status"] in {"critical", "degraded"} and previous_alert_at:
        try:
            last_alert = datetime.fromisoformat(previous_alert_at)
            cooldown = (prefs["critical_cooldown_hours"] if snapshot["status"] == "critical"
                        else prefs["degraded_cooldown_hours"])
            should_alert = checked - last_alert >= timedelta(hours=cooldown)
        except ValueError:
            should_alert = True
    elif snapshot["status"] in {"critical", "degraded"}:
        should_alert = True
    if _in_quiet_hours(checked, prefs):
        should_alert = False

    if should_alert and settings.admin_id and settings.bot_token:
        text = _alert_text(snapshot, recovered=recovered)
        delivered = await telegram.send_message(settings.admin_id, text, html=False)
        if prefs["secondary_enabled"] and settings.payment_alert_secondary_url:
            try:
                async with ClientSession(timeout=ClientTimeout(total=5)) as session:
                    async with session.post(settings.payment_alert_secondary_url,
                                            json={"text": text, "status": snapshot["status"]},
                                            headers={"X-Oracle-Event": "payment-health"}) as response:
                        delivered = delivered or response.status < 300
            except Exception as exc:  # noqa: BLE001
                log.warning("secondary payment alert failed: %s", type(exc).__name__)
        if delivered:
            current["last_alert_at"] = snapshot["checked_at"]
    await content.set_setting(db, SETTING_KEY, current)
    return current


async def reconciliation(db) -> dict:
    """Return bounded order anomalies for the owner action screen."""
    items: list[dict] = []
    cur = await db.execute(
        "SELECT id, status, kind, sku, created_at FROM orders "
        "WHERE status='paid' AND NOT EXISTS (SELECT 1 FROM payments p "
        "WHERE p.order_id=orders.id AND p.status='succeeded') ORDER BY id DESC LIMIT 50")
    items.extend({"order_id": int(row["id"]), "issue": "paid_without_payment",
                  "status": row["status"], "kind": row["kind"], "sku": row["sku"],
                  "created_at": row["created_at"]} for row in await cur.fetchall())
    cur = await db.execute(
        "SELECT order_id, COUNT(*) AS n FROM payments WHERE status='succeeded' "
        "AND order_id IS NOT NULL GROUP BY order_id HAVING COUNT(*)>1 LIMIT 50")
    items.extend({"order_id": int(row["order_id"]), "issue": "duplicate_succeeded_payment",
                  "count": int(row["n"])} for row in await cur.fetchall())
    cur = await db.execute(
        "SELECT id, status, kind, sku, created_at FROM orders "
        "WHERE status='pending' AND created_at<:stale ORDER BY id DESC LIMIT 50",
        {"stale": _iso(_now() - timedelta(hours=STALE_PENDING_HOURS))})
    items.extend({"order_id": int(row["id"]), "issue": "stale_pending",
                  "status": row["status"], "kind": row["kind"], "sku": row["sku"],
                  "created_at": row["created_at"]} for row in await cur.fetchall())
    return {"items": items[:100], "count": len(items[:100]),
            "ledger_mismatches": (await _database_checks(db, _now()))["reconciliation"]["crystal_ledger_mismatches"]}


async def recheck_order(db, order_id: int) -> dict:
    cur = await db.execute(
        "SELECT id, status, kind, sku, title, amount_stars, surface, created_at, paid_at, meta_json "
        "FROM orders WHERE id=:id", {"id": order_id})
    order = await cur.fetchone()
    if not order:
        return {"order_id": order_id, "found": False, "issues": []}
    cur = await db.execute(
        "SELECT COUNT(*) AS n, MAX(provider) AS provider, MAX(currency) AS currency, "
        "MAX(status) AS payment_status FROM payments WHERE order_id=:order_id",
        {"order_id": order_id})
    payment = await cur.fetchone()
    issues: list[str] = []
    payment_count = int(payment["n"] or 0)
    if order["status"] == "paid" and payment_count == 0:
        issues.append("paid_without_payment")
    if payment_count > 1:
        issues.append("multiple_payment_rows")
    if order["status"] == "pending":
        try:
            if _now() - datetime.fromisoformat(order["created_at"]) >= timedelta(hours=STALE_PENDING_HOURS):
                issues.append("stale_pending")
        except (TypeError, ValueError):
            pass
    meta = {}
    try:
        import json
        decoded_meta = json.loads(order["meta_json"] or "{}")
        meta = decoded_meta if isinstance(decoded_meta, dict) else {}
    except (TypeError, ValueError):
        pass
    return {"order_id": order_id, "found": True, "status": order["status"],
            "kind": order["kind"], "sku": order["sku"], "title": order["title"],
            "amount_stars": int(order["amount_stars"] or 0), "surface": order["surface"],
            "created_at": order["created_at"], "paid_at": order["paid_at"],
            "payment_count": payment_count, "provider": payment["provider"],
            "currency": payment["currency"], "payment_status": payment["payment_status"],
            "asset": str(meta.get("asset") or "")[:16],
            "review_status": str(meta.get("review_status") or "")[:24], "issues": issues}


async def mark_for_review(db, order_id: int, admin_id: int) -> dict:
    from ..repo import billing as billing_repo
    changed = await billing_repo.set_order_review(db, order_id, admin_id)
    result = await recheck_order(db, order_id)
    result["marked_for_review"] = changed
    return result


async def admin_snapshot(db) -> dict:
    """Return latest persisted snapshot, or a DB-only safe view before first tick."""
    value = await latest(db)
    if value:
        return value
    return await build_snapshot(db, external=False)
