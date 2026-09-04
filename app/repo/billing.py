"""Деньги: тарифы, товары, заказы, платежи, права доступа, Кристаллы.

Три правила, из которых вырос этот модуль.

1. **Заказ создаётся до оплаты.** У каждого инвойса есть строка в `orders` с
   уникальным `payload`. Telegram может доставить `successful_payment` повторно
   (ретрай при обрыве связи) — по `payload` мы видим, что заказ уже оплачен, и
   не выдаём товар второй раз.
2. **Баланс ✦ меняется только вместе с записью в журнал.** `users.crystals` —
   быстрый счётчик, `crystal_ledger` — источник правды для аудита. Обе записи
   в одной транзакции, поэтому разъехаться не могут.
3. **Списание проверяет баланс тем же запросом, что и меняет его.** Проверка
   «хватает ли» отдельным SELECT — это гонка: два одновременных экстренных
   расклада уводили баланс в минус.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from ..data.session import transaction, utcnow

# ─────────────────────────────── тарифы ───────────────────────────────────────

FREE_PLAN = {
    "code": "free", "title": "✦ Искра", "tagline": "",
    "price_stars": 0, "price_usd": 0.0, "period_days": 36500,
    "daily_questions": 0, "weekly_questions": 1, "memory_depth": 5,
    "crystals_grant": 0, "features": [], "badge": None,
}


def _plan_dict(row) -> dict:
    plan = dict(row)
    try:
        plan["features"] = json.loads(plan.pop("features_json", None) or "[]")
    except ValueError:
        plan["features"] = []
    return plan


async def get_plan(db, code: str) -> dict:
    cur = await db.execute(
        "SELECT * FROM plans WHERE code=:code", {"code": code or ""})
    row = await cur.fetchone()
    return _plan_dict(row) if row else dict(FREE_PLAN)


async def list_plans(db, *, public_only: bool = True) -> list[dict]:
    sql = "SELECT * FROM plans WHERE is_active=1"
    if public_only:
        sql += " AND is_public=1"
    sql += " ORDER BY sort, price_stars"
    cur = await db.execute(sql)
    return [_plan_dict(r) for r in await cur.fetchall()]


async def upsert_plan(db, code: str, **fields) -> None:
    allowed = {"title", "tagline", "price_stars", "price_usd", "period_days",
               "daily_questions", "weekly_questions", "memory_depth",
               "crystals_grant", "features_json", "badge", "sort",
               "is_active", "is_public"}
    fields = {k: v for k, v in fields.items() if k in allowed}
    async with transaction(db):
        await db.execute(
            "INSERT INTO plans(code, title, created_at, updated_at) "
            "VALUES(:code, :title, :created_at, :updated_at) "
            "ON CONFLICT (code) DO NOTHING",
            {"code": code, "title": fields.get("title", code),
             "created_at": utcnow(), "updated_at": utcnow()})
        if fields:
            keys = ", ".join(f"{k}=:{k}" for k in fields)
            # INVARIANT: keys only from allowlist above — never interpolate user input
            await db.execute(
                f"UPDATE plans SET {keys}, updated_at=:updated_at WHERE code=:code",
                {**fields, "updated_at": utcnow(), "code": code})


# ─────────────────────────────── товары ───────────────────────────────────────

async def get_product(db, sku: str):
    cur = await db.execute(
        "SELECT * FROM products WHERE sku=:sku AND is_active=1", {"sku": sku})
    return await cur.fetchone()


async def list_products(db, kind: str | None = None, *,
                        active_only: bool = True) -> list[dict]:
    sql = ["SELECT * FROM products WHERE 1=1"]
    params: dict = {}
    if active_only:
        sql.append("AND is_active=1")
    if kind:
        sql.append("AND kind=:kind")
        params["kind"] = kind
    sql.append("ORDER BY sort, price_stars")
    cur = await db.execute(" ".join(sql), params)
    return [dict(r) for r in await cur.fetchall()]


async def upsert_product(db, sku: str, **fields) -> None:
    allowed = {"kind", "title", "description", "price_stars", "price_crystals",
               "grant_kind", "grant_code", "grant_qty", "valid_days", "sort",
               "is_active"}
    fields = {k: v for k, v in fields.items() if k in allowed}
    async with transaction(db):
        await db.execute(
            "INSERT INTO products(sku, kind, title, created_at, updated_at) "
            "VALUES(:sku, :kind, :title, :created_at, :updated_at) "
            "ON CONFLICT (sku) DO NOTHING",
            {"sku": sku, "kind": fields.get("kind", "product"),
             "title": fields.get("title", sku),
             "created_at": utcnow(), "updated_at": utcnow()})
        if fields:
            keys = ", ".join(f"{k}=:{k}" for k in fields)
            # INVARIANT: keys only from allowlist above — never interpolate user input
            await db.execute(
                f"UPDATE products SET {keys}, updated_at=:updated_at WHERE sku=:sku",
                {**fields, "updated_at": utcnow(), "sku": sku})


# ─────────────────────────────── заказы ───────────────────────────────────────

async def create_order(db, tg_id: int, kind: str, *, sku: str | None = None,
                       title: str = "", amount_stars: int = 0,
                       amount_crystals: int = 0, surface: str = "bot",
                       meta: dict | None = None) -> dict:
    """Создаёт заказ в статусе pending и присваивает уникальный payload.

    payload уходит в инвойс Telegram и возвращается в `successful_payment` —
    это наш ключ идемпотентности, поэтому он и уникален на уровне БД.
    """
    async with transaction(db):
        cur = await db.execute(
            "INSERT INTO orders(tg_id, kind, sku, title, amount_stars, "
            "amount_crystals, status, surface, meta_json, created_at) "
            "VALUES(:tg_id, :kind, :sku, :title, :amount_stars, "
            ":amount_crystals, 'pending', :surface, :meta_json, :created_at) RETURNING id",
            {"tg_id": tg_id, "kind": kind, "sku": sku, "title": title,
             "amount_stars": amount_stars, "amount_crystals": amount_crystals,
             "surface": surface,
             "meta_json": json.dumps(meta, ensure_ascii=False) if meta else None,
             "created_at": utcnow()})
        row = await cur.fetchone()
        order_id = row["id"]
        payload = f"o{order_id}:{kind}:{sku or '-'}"[:120]
        await db.execute(
            "UPDATE orders SET payload=:payload WHERE id=:id",
            {"payload": payload, "id": order_id})
    return {"id": order_id, "payload": payload, "kind": kind, "sku": sku,
            "amount_stars": amount_stars, "amount_crystals": amount_crystals,
            "title": title}


async def get_order(db, order_id: int):
    cur = await db.execute(
        "SELECT * FROM orders WHERE id=:id", {"id": order_id})
    return await cur.fetchone()


async def order_by_payload(db, payload: str):
    cur = await db.execute(
        "SELECT * FROM orders WHERE payload=:payload", {"payload": payload})
    return await cur.fetchone()


async def mark_order_paid(db, payload: str, *, charge_id: str | None = None,
                          amount_stars: int | None = None,
                          provider: str = "telegram_stars",
                          currency: str = "XTR"):
    """Помечает заказ оплаченным. Возвращает строку заказа или None.

    None означает «обрабатывать нечего»: либо payload неизвестен, либо заказ уже
    оплачен ранее. Второе — нормальная ситуация при ретрае вебхука, и товар
    повторно выдавать нельзя.
    """
    async with transaction(db):
        cur = await db.execute(
            "SELECT * FROM orders WHERE payload=:payload AND status='pending'",
            {"payload": payload})
        order = await cur.fetchone()
        if not order:
            return None
        stars = amount_stars if amount_stars is not None else order["amount_stars"]
        # Сверка суммы (аудит 2.1): цена могла смениться между инвойсом и
        # оплатой — не выдаём полный грант за меньшую сумму Stars.
        if provider == "telegram_stars" and stars < (order["amount_stars"] or 0):
            return None
        # Чистый условный UPDATE с RETURNING (DB-001 w2): TOCTOU закрыт тем, что
        # status='pending' проверяется в самом UPDATE — при параллельной доставке
        # вебхука ровно один вызов получит строку, остальные — ничего.
        cur = await db.execute(
            "UPDATE orders SET status='paid', paid_at=:paid_at "
            "WHERE id=:id AND status='pending' RETURNING *",
            {"paid_at": utcnow(), "id": order["id"]})
        updated_order = await cur.fetchone()
        if not updated_order:
            return None
        await db.execute(
            "INSERT INTO payments(order_id, tg_id, amount_stars, currency, charge_id, "
            "provider, status, created_at) VALUES(:order_id, :tg_id, :amount_stars, "
            ":currency, :charge_id, :provider, 'succeeded', :created_at)",
            {"order_id": order["id"], "tg_id": order["tg_id"],
             "amount_stars": stars, "currency": currency[:8],
             "charge_id": charge_id, "provider": provider[:32],
             "created_at": utcnow()})
        if stars:
            await db.execute(
                "UPDATE users SET ltv_stars=ltv_stars+:stars WHERE tg_id=:tg_id",
                {"stars": stars, "tg_id": order["tg_id"]})
    return order


async def mark_order_failed(db, payload: str) -> bool:
    async with transaction(db):
        cur = await db.execute(
            "UPDATE orders SET status='failed' "
            "WHERE payload=:payload AND status='pending'",
            {"payload": payload})
        return bool(cur.rowcount)


async def set_order_meta(db, payload: str, **updates) -> bool:
    """Merge trusted provider references into a pending order."""
    async with transaction(db):
        cur = await db.execute(
            "SELECT meta_json FROM orders WHERE payload=:payload AND status='pending'",
            {"payload": payload})
        row = await cur.fetchone()
        if not row:
            return False
        try:
            meta = json.loads(row["meta_json"] or "{}")
        except (TypeError, ValueError):
            meta = {}
        meta.update(updates)
        cur = await db.execute(
            "UPDATE orders SET meta_json=:meta_json WHERE payload=:payload AND status='pending'",
            {"meta_json": json.dumps(meta, ensure_ascii=False), "payload": payload})
        return bool(cur.rowcount)


async def refund_order(db, order_id: int) -> bool:
    async with transaction(db):
        cur = await db.execute(
            "SELECT * FROM orders WHERE id=:id AND status='paid'", {"id": order_id})
        order = await cur.fetchone()
        if not order:
            return False
        await db.execute(
            "UPDATE orders SET status='refunded' WHERE id=:id", {"id": order_id})
        await db.execute(
            "UPDATE payments SET status='refunded' WHERE order_id=:order_id",
            {"order_id": order_id})
        await db.execute(
            "UPDATE users SET ltv_stars=GREATEST(0, ltv_stars-:stars) WHERE tg_id=:tg_id",
            {"stars": order["amount_stars"] or 0, "tg_id": order["tg_id"]})
    return True


async def payment_charge_id(db, order_id: int) -> str | None:
    """Идентификатор платежа Telegram — нужен для возврата Stars."""
    cur = await db.execute(
        "SELECT charge_id FROM payments WHERE order_id=:order_id AND status='succeeded' "
        "ORDER BY id DESC LIMIT 1", {"order_id": order_id})
    row = await cur.fetchone()
    return row["charge_id"] if row else None


async def user_orders(db, tg_id: int, limit: int = 50) -> list[dict]:
    cur = await db.execute(
        "SELECT * FROM orders WHERE tg_id=:tg_id ORDER BY id DESC LIMIT :limit",
        {"tg_id": tg_id, "limit": limit})
    return [dict(r) for r in await cur.fetchall()]


async def payment_history(db, tg_id: int, limit: int = 30) -> list[dict]:
    """User-safe order history with stages derived only from server records."""
    cur = await db.execute(
        "SELECT o.id, o.kind, o.sku, o.title, o.amount_stars, o.status, o.surface, "
        "o.created_at, o.paid_at, p.provider, p.currency, p.created_at AS payment_at, "
        "(SELECT COUNT(*) FROM entitlements e WHERE e.order_id=o.id) AS grants "
        "FROM orders o LEFT JOIN payments p ON p.id=(SELECT MAX(p2.id) FROM payments p2 "
        "WHERE p2.order_id=o.id) WHERE o.tg_id=:tg_id ORDER BY o.id DESC LIMIT :limit",
        {"tg_id": tg_id, "limit": limit})
    result = []
    for row in await cur.fetchall():
        item = dict(row)
        stages = [{"key": "created", "at": item["created_at"], "state": "done"}]
        if item["status"] in {"paid", "refunded"} and item["paid_at"]:
            stages.append({"key": "paid", "at": item["paid_at"], "state": "done"})
            if item["grants"] or item["kind"] in {"plan", "crystals"}:
                stages.append({"key": "entitlement", "at": item["paid_at"], "state": "done"})
            if item["status"] == "refunded":
                stages.append({"key": "refunded", "at": item["paid_at"], "state": "done"})
        elif item["status"] == "failed":
            stages.append({"key": "paid", "at": None, "state": "failed"})
        else:
            stages.append({"key": "paid", "at": None, "state": "pending"})
        item["stages"] = stages
        item["amount_stars"] = int(item["amount_stars"] or 0)
        item["grant_recorded"] = bool(item["grants"] or item["kind"] in {"plan", "crystals"}
                                      and item["status"] in {"paid", "refunded"})
        # Do not expose internal join/count implementation details.
        item.pop("grants", None)
        result.append(item)
    return result


async def set_order_review(db, order_id: int, admin_id: int | None = None) -> bool:
    """Mark only review metadata; never changes payment/order state."""
    from datetime import datetime, timezone
    import json
    async with transaction(db):
        cur = await db.execute(
            "SELECT meta_json FROM orders WHERE id=:id", {"id": order_id})
        row = await cur.fetchone()
        if not row:
            return False
        try:
            decoded_meta = json.loads(row["meta_json"] or "{}")
            meta = decoded_meta if isinstance(decoded_meta, dict) else {}
        except (TypeError, ValueError):
            meta = {}
        if meta.get("review_status") == "manual_review":
            return False
        meta.update({"review_status": "manual_review",
                     "reviewed_at": datetime.now(timezone.utc).isoformat()})
        cur = await db.execute(
            "UPDATE orders SET meta_json=:meta_json WHERE id=:id",
            {"meta_json": json.dumps(meta, ensure_ascii=False), "id": order_id})
        return bool(cur.rowcount)


async def recent_orders(db, *, status: str | None = None, limit: int = 100) -> list[dict]:
    sql = ["SELECT o.*, u.name, u.username FROM orders o "
           "LEFT JOIN users u ON u.tg_id = o.tg_id WHERE 1=1"]
    params: dict = {}
    if status:
        sql.append("AND o.status=:status")
        params["status"] = status
    sql.append("ORDER BY o.id DESC LIMIT :limit")
    params["limit"] = limit
    cur = await db.execute(" ".join(sql), params)
    return [dict(r) for r in await cur.fetchall()]


# ─────────────────────────────── Кристаллы ────────────────────────────────────

async def add_crystals(db, tg_id: int, delta: int, reason: str,
                       ref: str | None = None) -> int:
    """Начисление/списание без проверки баланса (для начислений и админки)."""
    async with transaction(db):
        await db.execute(
            "UPDATE users SET crystals=crystals+:delta WHERE tg_id=:tg_id",
            {"delta": delta, "tg_id": tg_id})
        cur = await db.execute(
            "SELECT crystals FROM users WHERE tg_id=:tg_id", {"tg_id": tg_id})
        row = await cur.fetchone()
        balance = row["crystals"] if row else 0
        await db.execute(
            "INSERT INTO crystal_ledger(tg_id, delta, reason, balance, ref, created_at) "
            "VALUES(:tg_id, :delta, :reason, :balance, :ref, :created_at)",
            {"tg_id": tg_id, "delta": delta, "reason": reason,
             "balance": balance, "ref": ref, "created_at": utcnow()})
    return balance


async def spend_crystals(db, tg_id: int, amount: int, reason: str,
                         ref: str | None = None) -> bool:
    """Atomically spend the total balance and allocate expiring lots first.

    The legacy ``users.crystals`` counter remains the fast aggregate. New v2
    grants additionally create lots, while an existing unallocated balance is
    represented as a non-expiring ``legacy`` lot on first spend. This preserves
    old balances and gives v2 bonus crystals deterministic expiry semantics.
    """
    if amount <= 0:
        return True
    async with transaction(db):
        cur = await db.execute(
            "SELECT crystals FROM users WHERE tg_id=:tg_id", {"tg_id": tg_id})
        user_row = await cur.fetchone()
        if not user_row or int(user_row["crystals"] or 0) < amount:
            return False
        now = utcnow()
        await db.execute(
            "UPDATE crystal_lots SET remaining_qty=0 WHERE tg_id=:tg_id AND remaining_qty>0 "
            "AND expires_at IS NOT NULL AND expires_at<=:now",
            {"tg_id": tg_id, "now": now})
        cur = await db.execute(
            "SELECT COALESCE(SUM(remaining_qty),0) n FROM crystal_lots WHERE tg_id=:tg_id AND remaining_qty>0",
            {"tg_id": tg_id})
        allocated = int((await cur.fetchone())["n"] or 0)
        balance_before = int(user_row["crystals"] or 0)
        if allocated < balance_before:
            missing = balance_before - allocated
            await db.execute(
                "INSERT INTO crystal_lots(tg_id,source,original_qty,remaining_qty,created_at) "
                "VALUES(:tg_id, 'legacy', :qty, :qty, :now)",
                {"tg_id": tg_id, "qty": missing, "now": now})
        remaining = amount
        cur = await db.execute(
            "SELECT id, remaining_qty FROM crystal_lots WHERE tg_id=:tg_id AND remaining_qty>0 "
            "ORDER BY (expires_at IS NULL), expires_at, id", {"tg_id": tg_id})
        for lot in await cur.fetchall():
            if remaining <= 0:
                break
            take = min(remaining, int(lot["remaining_qty"]))
            updated = await db.execute(
                "UPDATE crystal_lots SET remaining_qty=remaining_qty-:take "
                "WHERE id=:id AND remaining_qty>=:take",
                {"take": take, "id": lot["id"]})
            if updated.rowcount:
                remaining -= take
        if remaining:
            return False
        cur = await db.execute(
            "UPDATE users SET crystals=crystals-:amount WHERE tg_id=:tg_id AND crystals>=:amount",
            {"amount": amount, "tg_id": tg_id})
        if not cur.rowcount:
            return False
        cur = await db.execute(
            "SELECT crystals FROM users WHERE tg_id=:tg_id", {"tg_id": tg_id})
        row = await cur.fetchone()
        balance = row["crystals"] if row else 0
        await db.execute(
            "INSERT INTO crystal_ledger(tg_id, delta, reason, balance, ref, created_at) "
            "VALUES(:tg_id, :delta, :reason, :balance, :ref, :created_at)",
            {"tg_id": tg_id, "delta": -amount, "reason": reason,
             "balance": balance, "ref": ref, "created_at": utcnow()})
    return True


async def crystal_history(db, tg_id: int, limit: int = 50) -> list[dict]:
    cur = await db.execute(
        "SELECT delta, reason, balance, created_at FROM crystal_ledger "
        "WHERE tg_id=:tg_id ORDER BY id DESC LIMIT :limit",
        {"tg_id": tg_id, "limit": limit})
    return [dict(r) for r in await cur.fetchall()]


# ──────────────────────── права доступа (entitlements) ────────────────────────

async def grant_entitlement(db, tg_id: int, kind: str, code: str | None = None, *,
                            qty: int = 1, valid_days: int | None = None,
                            source: str = "purchase",
                            order_id: int | None = None) -> int:
    expires = None
    if valid_days:
        expires = (datetime.now(timezone.utc) + timedelta(days=valid_days)).isoformat()
    async with transaction(db):
        cur = await db.execute(
            "INSERT INTO entitlements(tg_id, kind, code, qty_total, qty_used, "
            "expires_at, source, order_id, created_at) VALUES(:tg_id, :kind, :code, "
            ":qty_total, 0, :expires_at, :source, :order_id, :created_at) RETURNING id",
            {"tg_id": tg_id, "kind": kind, "code": code, "qty_total": qty,
             "expires_at": expires, "source": source,
             "order_id": order_id, "created_at": utcnow()})
        row = await cur.fetchone()
        ent_id = row["id"]
    return ent_id


async def available_entitlements(db, tg_id: int, kind: str,
                                 code: str | None = None) -> int:
    """Сколько неиспользованных прав есть. `code='*'` в БД покрывает любой код."""
    now = utcnow()
    params: dict = {"tg_id": tg_id, "kind": kind, "now": now}
    clause = ""
    if code:
        clause = " AND (code=:code OR code='*' OR code IS NULL)"
        params["code"] = code
    cur = await db.execute(
        "SELECT COALESCE(SUM(qty_total - qty_used), 0) n FROM entitlements "
        "WHERE tg_id=:tg_id AND kind=:kind AND qty_used < qty_total "
        f"AND (expires_at IS NULL OR expires_at > :now){clause}", params)
    return (await cur.fetchone())["n"]


async def consume_entitlement(db, tg_id: int, kind: str,
                              code: str | None = None) -> bool:
    """Тратит одно право. Берём то, что истекает раньше — иначе оно сгорит зря."""
    now = utcnow()
    params: dict = {"tg_id": tg_id, "kind": kind, "now": now}
    clause = ""
    if code:
        clause = " AND (code=:code OR code='*' OR code IS NULL)"
        params["code"] = code
    async with transaction(db):
        cur = await db.execute(
            "SELECT id FROM entitlements WHERE tg_id=:tg_id AND kind=:kind "
            "AND qty_used < qty_total AND (expires_at IS NULL OR expires_at > :now)"
            f"{clause} ORDER BY (expires_at IS NULL), expires_at, id LIMIT 1", params)
        row = await cur.fetchone()
        if not row:
            return False
        cur = await db.execute(
            "UPDATE entitlements SET qty_used=qty_used+1 "
            "WHERE id=:id AND qty_used < qty_total", {"id": row["id"]})
        return bool(cur.rowcount)


async def list_entitlements(db, tg_id: int) -> list[dict]:
    cur = await db.execute(
        "SELECT * FROM entitlements WHERE tg_id=:tg_id AND qty_used < qty_total "
        "AND (expires_at IS NULL OR expires_at > :now) ORDER BY id DESC",
        {"tg_id": tg_id, "now": utcnow()})
    return [dict(r) for r in await cur.fetchall()]


# ─────────────────────────────── сводки ───────────────────────────────────────

async def revenue(db, *, days: int = 30) -> dict:
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    async def scalar(sql, params=()):
        cur = await db.execute(sql, params)
        row = await cur.fetchone()
        return row[0] or 0

    return {
        "stars_total": await scalar(
            "SELECT SUM(amount_stars) FROM payments WHERE status='succeeded'"),
        "stars_period": await scalar(
            "SELECT SUM(amount_stars) FROM payments WHERE status='succeeded' "
            "AND created_at>=:since", {"since": since}),
        "orders_paid": await scalar(
            "SELECT COUNT(*) FROM orders WHERE status='paid'"),
        "orders_period": await scalar(
            "SELECT COUNT(*) FROM orders WHERE status='paid' AND paid_at>=:since",
            {"since": since}),
        "payers": await scalar(
            "SELECT COUNT(DISTINCT tg_id) FROM payments WHERE status='succeeded'"),
        "refunds": await scalar(
            "SELECT COUNT(*) FROM orders WHERE status='refunded'"),
    }


async def top_products(db, *, days: int = 30, limit: int = 10) -> list[dict]:
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    cur = await db.execute(
        "SELECT COALESCE(sku, kind) sku, MAX(title) title, COUNT(*) sales, "
        "SUM(amount_stars) stars FROM orders WHERE status='paid' AND paid_at>=:since "
        "GROUP BY COALESCE(sku, kind) ORDER BY stars DESC LIMIT :limit",
        {"since": since, "limit": limit})
    return [dict(r) for r in await cur.fetchall()]
