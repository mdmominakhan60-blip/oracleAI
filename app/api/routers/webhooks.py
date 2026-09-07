"""Вебхуки внешних платёжных систем (web-оплата подписки).

Зачем это нужно, если есть Telegram Stars. Stars обязательны для покупок внутри
бота (правило платформы), но их эффективная комиссия ~30-40%. Основной чек —
месячная подписка — по бизнес-плану проводится через web-платёжку с комиссией
3-5%: разница в марже кратная. Здесь принимающая сторона этого потока.

Инварианты, без которых деньги теряются или задваиваются:

- подпись проверяется по СЫРОМУ телу запроса: любой повторный `json.dumps`
  меняет байты и ломает HMAC;
- каждое событие пишется в `webhook_events` по своему id — провайдеры честно
  ретраят доставку, и без этой таблицы подписка продлевалась бы дважды;
- выдача идёт через тот же `services.billing`, что и Stars, поэтому «что именно
  клиентка получила» описано в одном месте.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time

from fastapi import APIRouter, Depends, Header, HTTPException, Request

from ...config import settings
from ...data.session import transaction, utcnow
from ...services.repo_gateway import billing as billing_repo
from ...services import analytics
from ...services import billing as billing_svc
from ...services import cryptobot
from ...core.observability import log_event
from ..deps import get_db

log = logging.getLogger("oracle.api.webhooks")

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


async def _failure(db, provider: str, code: str, *,
                   status_code: int | None = None) -> None:
    """Record only bounded provider/code metadata; never store payload or PII."""
    log_event(log, logging.WARNING, "webhook_failure", code,
              operation=provider, status_code=status_code)
    try:
        await db.execute(
            "INSERT INTO payment_webhook_failures(provider, code, status_code, created_at) "
            "VALUES(:provider, :code, :status_code, :created_at)",
            {"provider": provider[:32], "code": code[:96],
             "status_code": status_code, "created_at": utcnow()})
    except Exception as exc:  # noqa: BLE001
        log.error("journal ошибок webhook недоступен: %s", type(exc).__name__)

#: Насколько старую подпись принимаем. Защита от переигрывания перехваченного
#: запроса: подпись сама по себе бессрочна.
MAX_SIGNATURE_AGE = 300
MAX_EVENT_ID_LENGTH = 128
MAX_EVENT_KIND_LENGTH = 64


def _bounded_event_id(value: object, *, label: str) -> str:
    text = str(value or "")
    if not text or len(text) > MAX_EVENT_ID_LENGTH:
        raise ValueError(f"{label}_invalid")
    return text


def _bounded_kind(value: object) -> str:
    return str(value or "unknown")[:MAX_EVENT_KIND_LENGTH]

#: События, после которых доступ открывается. Только то, где реально прошли
#: деньги: `subscription.updated` (смена плана/перенос даты) и
#: `subscription.activated` (старт без нового списания) выдавали бы дни
#: бесплатно при каждом пинге Paddle (review-фикс G37).
GRANTING_EVENTS = {
    "transaction.completed",
}


def _parse_signature(header: str) -> tuple[str, tuple[str, ...]]:
    """`ts=1700000000;h1=abc...;h1=old...` → timestamp and signatures."""
    ts = ""
    digests: list[str] = []
    for chunk in (header or "").split(";"):
        key, _, value = chunk.partition("=")
        if key.strip() == "ts":
            ts = value.strip()
        elif key.strip() == "h1" and value.strip():
            digests.append(value.strip())
    return ts, tuple(digests)


def verify_paddle(raw: bytes, header: str, secret: str) -> bool:
    """Проверяет подпись Paddle: HMAC-SHA256 от «ts:тело» с секретом вебхука."""
    if not secret:
        return False
    ts, digests = _parse_signature(header)
    if not ts or not digests:
        return False
    try:
        age = time.time() - int(ts)
    except ValueError:
        return False
    if age > MAX_SIGNATURE_AGE or age < -MAX_SIGNATURE_AGE:
        log.warning("подпись вебхука просрочена (%.0f с)", age)
        return False
    calc = hmac.new(secret.encode(), f"{ts}:".encode() + raw,
                    hashlib.sha256).hexdigest()
    return any(hmac.compare_digest(calc, digest) for digest in digests)


async def _already_seen(db, event_id: str, provider: str, kind: str,
                        payload: str | None = None) -> bool:
    """True — событие уже обработано; raw provider body is intentionally discarded."""
    try:
        async with transaction(db):
            cur = await db.execute(
                "INSERT INTO webhook_events(event_id, provider, kind, "
                "payload, created_at) VALUES(:event_id, :provider, :kind, "
                "NULL, :created_at) ON CONFLICT (event_id) DO NOTHING",
                {"event_id": event_id[:MAX_EVENT_ID_LENGTH], "provider": provider[:32],
                 "kind": kind[:MAX_EVENT_KIND_LENGTH], "created_at": utcnow()})
        return not cur.rowcount
    except Exception as e:  # noqa: BLE001
        await _failure(db, provider, "idempotency_journal_unavailable", status_code=503)
        log.error("журнал вебхуков недоступен: %s", type(e).__name__)
        return False          # лучше обработать дважды, чем потерять оплату


def _custom_data(body: dict) -> dict:
    data = (body.get("data") or {})
    custom = data.get("custom_data") or {}
    if isinstance(custom, str):
        try:
            custom = json.loads(custom)
        except ValueError:
            custom = {}
    return custom if isinstance(custom, dict) else {}


#: Paddle adjustment event types that can affect entitlement.
#: transaction.completed opens access; refund/chargeback close it.
#: Everything else (subscription.paused, payment.dispute.created without action,
#: invoice.paid без transaction_id) — journal only.
_ADJUSTMENT_REVOKE_KINDS = {
    "adjustment.created",
    "adjustment.updated",
}


def _adjustment_refund_total(data: dict) -> tuple[float, str | None]:
    """Extract refund amount and action from a Paddle adjustment event payload.

    Returns (total_refunded_usd, action). Positive total + refund/chargeback
    action → full revocation candidate. Partial or zero total → journal only.
    If we cannot confidently parse the totals, we return (0.0, None) to
    trigger the fail-closed path.
    """
    action = str(data.get("action") or "").strip().lower()
    totals = data.get("totals") or data.get("payout_totals") or {}
    if not isinstance(totals, dict):
        totals = {}
    total_str = str(totals.get("gross") or totals.get("net")
                     or totals.get("subtotal") or totals.get("amount") or "0")
    try:
        total = float(total_str)
    except (TypeError, ValueError):
        return 0.0, None
    return total, action


def _is_full_refund_or_chargeback(data: dict) -> bool:
    """True only when the event is an explicit full refund/chargeback.

    Fail-closed: ambiguous payloads → False (we do NOT revoke).
    """
    total, action = _adjustment_refund_total(data)
    if total <= 0 or not action:
        return False
    return action in {"refund", "chargeback", "chargeback_won"}


@router.post("/paddle")
async def paddle(request: Request, db=Depends(get_db),
                 paddle_signature: str | None = Header(default=None,
                                                       alias="Paddle-Signature")):
    """Приём оплаты подписки через web. Возвращает 200 на всё, что уже учтено."""
    raw = await request.body()
    if len(raw) > 512 * 1024:
        raise HTTPException(413, "тело вебхука слишком большое")
    if not settings.paddle_webhook_secret:
        await _failure(db, "paddle", "secret_not_configured", status_code=503)
        raise HTTPException(503, "web-оплата не настроена")
    if not verify_paddle(raw, paddle_signature or "", settings.paddle_webhook_secret):
        await _failure(db, "paddle", "signature_rejected", status_code=401)
        raise HTTPException(401, "подпись не подтверждена")

    try:
        body = json.loads(raw.decode("utf-8"))
    except ValueError as e:
        await _failure(db, "paddle", "body_not_json", status_code=400)
        raise HTTPException(400, "тело не JSON") from e
    if not isinstance(body, dict):
        await _failure(db, "paddle", "body_shape_invalid", status_code=400)
        raise HTTPException(400, "некорректная структура тела")

    try:
        event_id = _bounded_event_id(body.get("event_id") or body.get("notification_id"), label="event_id")
    except ValueError:
        await _failure(db, "paddle", "event_id_invalid", status_code=400)
        raise HTTPException(400, "некорректный event_id")
    kind = _bounded_kind(body.get("event_type"))
    # Do not claim the event before the entitlement transaction. If billing
    # fails, Paddle must be able to retry rather than seeing a false duplicate.
    if kind not in GRANTING_EVENTS:
        # Adjustment events (refund/chargeback) for already-paid orders:
        # classify full vs partial and queue revocation for the daily sweep.
        if kind in _ADJUSTMENT_REVOKE_KINDS:
            data = body.get("data") or {}
            if not isinstance(data, dict):
                data = {}
            if _is_full_refund_or_chargeback(data):
                original_txn = str(data.get("original_transaction_id") or "")
                if not original_txn:
                    await _failure(db, "paddle", "adjustment_no_original_txn")
                    return {"ok": True, "ignored": "adjustment_no_original_txn"}
                cur = await db.execute(
                    "SELECT o.*, p.id AS payment_id FROM orders o "
                    "JOIN payments p ON p.order_id=o.id AND p.provider='paddle' "
                    "AND p.status='succeeded' "
                    "WHERE o.status='paid' "
                    "AND (o.meta_json LIKE :txn_pattern "
                    "OR o.payload = :payload) "
                    "LIMIT 1",
                    {"txn_pattern": f"%\"paddle_transaction_id\": \"{original_txn}\"%",
                     "payload": str(data.get("custom_data") or "")[:120]})
                paid_order = await cur.fetchone()
                if paid_order:
                    queued = await billing_repo.queue_refund_revoke(
                        db, paid_order["id"], source="paddle")
                    await analytics.track(
                        db, analytics.E_REFUND_COMPLETED, paid_order["tg_id"],
                        props={"order_id": paid_order["id"],
                               "plan": paid_order["sku"],
                               "reason": "provider_refund",
                               "provider": "paddle"},
                        surface="web")
                    log.info("refund-revoke queued order=%s tg_id=%s queued=%s",
                             paid_order["id"], paid_order["tg_id"], queued)
                else:
                    log.warning("adjustment event: paid order not found txn=%s",
                                original_txn)
            else:
                log.info("partial/zero adjustment journaled, no revocation: kind=%s",
                         kind)
        duplicate = await _already_seen(
            db, event_id, "paddle", kind, raw.decode("utf-8", "ignore"))
        return {"ok": True, "duplicate": True} if duplicate else {"ok": True, "ignored": kind}

    data = body.get("data") or {}
    if not isinstance(data, dict):
        await _failure(db, "paddle", "data_shape_invalid", status_code=400)
        raise HTTPException(400, "некорректная структура data")
    if data.get("status") != "completed":
        log.warning("Paddle webhook имеет неожиданный статус")
        duplicate = await _already_seen(
            db, event_id, "paddle", kind, raw.decode("utf-8", "ignore"))
        return {"ok": True, "duplicate": True} if duplicate else {"ok": True, "ignored": "status"}

    custom = _custom_data(body)
    payload = str(custom.get("order_payload") or "")
    if not payload or len(payload) > 120:
        await _failure(db, "paddle", "order_payload_invalid")
        return {"ok": True, "unmatched": True}
    order = await billing_repo.order_by_payload(db, payload)
    if not order or order["status"] != "pending":
        duplicate = await _already_seen(
            db, event_id, "paddle", kind, raw.decode("utf-8", "ignore"))
        await _failure(db, "paddle", "pending_order_binding_failed")
        return {"ok": True, "duplicate": True} if duplicate else {"ok": True, "unmatched": True}
    if order["surface"] != "web" or order["kind"] != "plan":
        log.error("Paddle webhook с недопустимым типом заказа")
        return {"ok": True, "unmatched": True}
    tg_id = int(order["tg_id"])
    plan = await billing_repo.get_plan(db, order["sku"] or "")
    if not plan or not plan.get("is_active"):
        log.error("Paddle webhook для неактивного тарифа")
        return {"ok": True, "unmatched": True}
    order_meta = billing_svc._order_meta(order)
    expected_transaction = str(order_meta.get("paddle_transaction_id") or "")
    actual_transaction = str(data.get("id") or "")
    if expected_transaction and actual_transaction != expected_transaction:
        log.error("Paddle webhook не совпал с transaction_id заказа")
        return {"ok": True, "unmatched": True}
    expected_price = settings.paddle_price_id(order["sku"] or "")
    if expected_price:
        price_ids = {
            str((item.get("price") or {}).get("id") or item.get("price_id") or "")
            for item in (data.get("items") or []) if isinstance(item, dict)
        }
        if expected_price not in price_ids:
            log.error("Paddle webhook не совпал с price_id тарифа")
            return {"ok": True, "unmatched": True}
    result = await billing_svc.apply_payment(
        db, order["payload"], charge_id=event_id, amount_stars=0,
        provider="paddle", currency=str(data.get("currency_code") or "USD"))
    await analytics.track(db, "web_payment", tg_id,
                          props={"plan": order["sku"], "event": kind}, surface="web")
    duplicate = await _already_seen(
        db, event_id, "paddle", kind, raw.decode("utf-8", "ignore"))
    if duplicate:
        log.info("Paddle webhook уже записан после идемпотентной обработки")
    log.info("web-оплата успешно обработана")
    return {"ok": True, "granted": bool(result), "duplicate": duplicate}


@router.post("/cryptobot")
async def cryptobot_webhook(request: Request, db=Depends(get_db)):
    """Оплата Кристаллов криптой (Crypto Pay). Схема та же, что у Paddle:
    подпись → payload → pending-заказ → apply_payment → журнал идемпотентности.

    Crypto Pay шлёт обновления статусов; выдача — только на `paid`.
    """
    raw = await request.body()
    if len(raw) > 512 * 1024:
        raise HTTPException(413, "тело вебхука слишком большое")
    if not settings.cryptobot_api_token:
        await _failure(db, "cryptobot", "secret_not_configured", status_code=503)
        raise HTTPException(503, "крипто-оплата не настроена")
    if not cryptobot.verify_webhook(raw, request.headers.get("crypto-pay-api-signature")):
        await _failure(db, "cryptobot", "signature_rejected", status_code=401)
        raise HTTPException(401, "подпись не подтверждена")

    try:
        body = json.loads(raw.decode("utf-8"))
    except ValueError as e:
        await _failure(db, "cryptobot", "body_not_json", status_code=400)
        raise HTTPException(400, "тело не JSON") from e
    if not isinstance(body, dict):
        await _failure(db, "cryptobot", "body_shape_invalid", status_code=400)
        raise HTTPException(400, "некорректная структура тела")

    payload_data = body.get("payload") or {}
    if not isinstance(payload_data, dict):
        await _failure(db, "cryptobot", "payload_shape_invalid", status_code=400)
        raise HTTPException(400, "некорректная структура payload")
    update_type = str(payload_data.get("update_type") or "")
    invoice = payload_data.get("payload") or {}
    if not isinstance(invoice, dict):
        invoice = {}
    try:
        invoice_id = str(int(invoice.get("invoice_id")))
        if int(invoice_id) <= 0 or len(invoice_id) > MAX_EVENT_ID_LENGTH:
            raise ValueError
    except (TypeError, ValueError):
        await _failure(db, "cryptobot", "invoice_id_invalid", status_code=400)
        raise HTTPException(400, "некорректный invoice_id")
    update_type = _bounded_kind(update_type)

    if update_type != "invoice_paid":
        event_key = f"{invoice_id}:{update_type}"
        duplicate = await _already_seen(
            db, event_key, "cryptobot", update_type or "unknown",
            raw.decode("utf-8", "ignore"))
        return {"ok": True, "duplicate": True} if duplicate else {"ok": True}

    order_payload = str(invoice.get("payload") or "")
    if not order_payload or len(order_payload) > 120:
        await _failure(db, "cryptobot", "order_payload_invalid")
        return {"ok": True, "unmatched": True}
    order = await billing_repo.order_by_payload(db, order_payload)
    if not order or order["status"] != "pending":
        duplicate = await _already_seen(
            db, f"{invoice_id}:paid", "cryptobot", "invoice_paid",
            raw.decode("utf-8", "ignore"))
        if duplicate:
            return {"ok": True, "granted": False, "duplicate": True}
        return {"ok": True, "unmatched": True}
    if order["kind"] != "crystals" or (order["surface"] or "") == "web":
        log.error("Crypto Pay webhook с недопустимым заказом")
        return {"ok": True, "unmatched": True}

    order_meta = billing_svc._order_meta(order)
    expected_invoice = str(order_meta.get("cryptobot_invoice_id") or "")
    if expected_invoice and expected_invoice != invoice_id:
        log.error("Crypto Pay webhook не совпал с invoice_id заказа")
        return {"ok": True, "unmatched": True}
    expected_asset = str(order_meta.get("asset") or "").upper()
    actual_asset = str(invoice.get("asset") or "").upper()
    if expected_asset and actual_asset and actual_asset != expected_asset:
        log.error("Crypto Pay webhook не совпал с asset заказа")
        return {"ok": True, "unmatched": True}
    if str(invoice.get("status") or "paid").lower() != "paid":
        return {"ok": True, "unmatched": True}

    result = await billing_svc.apply_payment(
        db, order["payload"], charge_id=f"crypto:{invoice_id}",
        amount_stars=0, provider="cryptobot",
        currency=str(invoice.get("fiat") or invoice.get("asset") or "USD"))
    await analytics.track(db, "crypto_payment", order["tg_id"],
                          props={"sku": order["sku"],
                                 "asset": actual_asset or expected_asset or "crypto"},
                          surface="bot")
    duplicate = await _already_seen(
        db, f"{invoice_id}:paid", "cryptobot", "invoice_paid",
        raw.decode("utf-8", "ignore"))
    log.info("крипто-оплата успешно обработана")
    return {"ok": True, "granted": bool(result), "duplicate": duplicate}
