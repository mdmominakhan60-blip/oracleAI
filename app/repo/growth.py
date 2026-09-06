"""Рост: промокоды («золотые билеты» с Etsy) и двухуровневая рефералка."""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from ..data.session import transaction, utcnow

ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # без похожих 0/O, 1/I/L


def generate_code(prefix: str = "", length: int = 8) -> str:
    body = "".join(secrets.choice(ALPHABET) for _ in range(length))
    return f"{prefix}{body}" if prefix else body


# ─────────────────────────────── промокоды ────────────────────────────────────

async def create_codes(db, count: int, *, kind: str = "plan_days", days: int = 30,
                       plan_code: str = "vip", crystals: int = 0,
                       sku: str | None = None, batch: str = "",
                       max_uses: int = 1, valid_days: int | None = None,
                       created_by: int | None = None,
                       prefix: str = "") -> list[str]:
    """Генерирует партию кодов. Партия = листинг/канал, по ней считаем аналитику."""
    expires = None
    if valid_days:
        expires = (datetime.now(timezone.utc) + timedelta(days=valid_days)).isoformat()
    codes: list[str] = []
    async with transaction(db):
        while len(codes) < count:
            code = generate_code(prefix)
            cur = await db.execute(
                "INSERT INTO promo_codes(code, kind, days, plan_code, crystals, "
                "sku, batch, max_uses, used_count, expires_at, created_by, created_at) "
                "VALUES(:code, :kind, :days, :plan_code, :crystals, "
                ":sku, :batch, :max_uses, 0, :expires_at, :created_by, :created_at) "
                "ON CONFLICT (code) DO NOTHING",
                {"code": code, "kind": kind, "days": days, "plan_code": plan_code,
                 "crystals": crystals, "sku": sku, "batch": batch,
                 "max_uses": max_uses, "expires_at": expires,
                 "created_by": created_by, "created_at": utcnow()})
            if cur.rowcount:            # коллизия кода — просто берём следующий
                codes.append(code)
    return codes


async def get_code(db, code: str):
    cur = await db.execute(
        "SELECT * FROM promo_codes WHERE code=:code",
        {"code": (code or "").strip().upper()})
    return await cur.fetchone()


async def redeem(db, code: str, tg_id: int) -> dict | None:
    """Активирует код. Возвращает описание выдачи или None.

    Проверки (срок, лимит использований, отзыв кода, повторная активация
    одним человеком) и инкремент счётчика — в одной транзакции: иначе код с
    `max_uses=1`, отправленный двумя сообщениями подряд, активировался бы дважды.
    """
    code = (code or "").strip().upper()
    if not code:
        return None
    async with transaction(db):
        cur = await db.execute(
            "SELECT * FROM promo_codes WHERE code=:code", {"code": code})
        promo = await cur.fetchone()
        if not promo:
            return None
        if promo["expires_at"] and promo["expires_at"] <= utcnow():
            return None
        if promo["is_active"] == 0:
            return None                          # отозван (kill switch, G3)
        max_uses = promo["max_uses"] or 1
        if (promo["used_count"] or 0) >= max_uses:
            return None
        cur = await db.execute(
            "SELECT 1 FROM promo_redemptions WHERE code=:code AND tg_id=:tg_id",
            {"code": code, "tg_id": tg_id})
        if await cur.fetchone():
            return None                          # этот человек код уже применял

        cur = await db.execute(
            "UPDATE promo_codes SET used_count=COALESCE(used_count,0)+1, "
            "used_by=COALESCE(used_by, :tg_id), used_at=COALESCE(used_at, :now) "
            "WHERE code=:code AND COALESCE(used_count,0) < :max_uses",
            {"tg_id": tg_id, "now": utcnow(), "code": code, "max_uses": max_uses})
        if not cur.rowcount:
            return None
        # Plain INSERT: SELECT guard + enclosing transaction prevent duplicates.
        # promo_redemptions has no UNIQUE(code, tg_id) constraint in the schema.
        await db.execute(
            "INSERT INTO promo_redemptions(code, tg_id, created_at) "
            "VALUES(:code, :tg_id, :created_at)",
            {"code": code, "tg_id": tg_id, "created_at": utcnow()})

    return {"code": code, "kind": promo["kind"] or "plan_days",
            "days": promo["days"] or 0, "plan_code": promo["plan_code"] or "vip",
            "crystals": promo["crystals"] or 0, "sku": promo["sku"],
            "batch": promo["batch"]}


async def list_redemptions(db, *, batch: str | None = None,
                           limit: int = 200) -> list[dict]:
    """Кто и когда активировал купоны — для панели админа."""
    sql = ["SELECT r.code, r.tg_id, r.created_at, c.batch, c.kind, "
           "c.crystals, c.days, c.sku, u.name, u.username "
           "FROM promo_redemptions r "
           "JOIN promo_codes c ON c.code=r.code "
           "LEFT JOIN users u ON u.tg_id=r.tg_id WHERE 1=1"]
    params: dict = {}
    if batch:
        sql.append("AND c.batch=:batch")
        params["batch"] = batch
    sql.append("ORDER BY r.created_at DESC LIMIT :limit")
    params["limit"] = limit
    cur = await db.execute(" ".join(sql), params)
    return [dict(r) for r in await cur.fetchall()]


async def batch_stats(db) -> list[dict]:
    cur = await db.execute(
        "SELECT COALESCE(batch,'(без партии)') batch, COUNT(*) total, "
        "SUM(CASE WHEN COALESCE(used_count,0) > 0 THEN 1 ELSE 0 END) used, "
        "SUM(CASE WHEN COALESCE(is_active,1)=0 THEN 1 ELSE 0 END) inactive_count, "
        "MIN(created_at) created_at FROM promo_codes GROUP BY batch "
        "ORDER BY created_at DESC")
    return [dict(r) for r in await cur.fetchall()]


async def ensure_winback_batch(db, count: int, *, now: datetime) -> str:
    """Партия winback-кодов месяца (BUS-197): 25 кодов trial 7д/14д, 1 раз/мес.

    Ежемесячная генерация на первом тике: партия = месяц атрибуции
    (batch_stats). Пустой месяц — партия не создана; у неё месяц в имени.
    """
    batch = f"winback_{now.strftime('%Y-%m')}"
    cur = await db.execute(
        "SELECT COUNT(*) n FROM promo_codes WHERE batch=:batch",
        {"batch": batch})
    if (await cur.fetchone())["n"]:
        return batch
    await create_codes(db, count, kind="plan_days", days=7, plan_code="trial",
                       batch=batch, max_uses=1, valid_days=14)
    return batch


async def reserve_code(db, batch: str) -> str | None:
    """Резервирует код из партии для одного юзера (каждому — свой).

    Проверка-запись в транзакции: два параллельных тика не получают один код.
    None — партия исчерпана: warning наверху, юзерам уходит тёплый winback.
    """
    async with transaction(db):
        cur = await db.execute(
            "SELECT c.code FROM promo_codes c "
            "WHERE c.batch=:batch AND COALESCE(c.used_count,0)=0 "
            "AND (c.expires_at IS NULL OR c.expires_at > :now) "
            "AND NOT EXISTS (SELECT 1 FROM deliveries d "
            "  WHERE d.kind='winback2_code' AND d.key=c.code) "
            "ORDER BY c.code LIMIT 1 "
            "FOR UPDATE OF c SKIP LOCKED",
            {"batch": batch, "now": utcnow()})
        row = await cur.fetchone()
        if not row:
            return None
        code = row["code"]
        cur = await db.execute(
            "INSERT INTO deliveries(tg_id, kind, key, created_at) "
            "VALUES(0, 'winback2_code', :code, :created_at) "
            "ON CONFLICT (tg_id, kind, key) DO NOTHING",
            {"code": code, "created_at": utcnow()})
        if not cur.rowcount:
            return None
        return code


async def redeemed_winback_since(db, tg_id: int, since: datetime) -> bool:
    """True — юзер активировал winback-код не позже `since` (анти-абьюз 90д).

    Проверка одной строкой в SQL-отборе, без отдельного запроса на юзера.
    """
    cur = await db.execute(
        "SELECT 1 FROM promo_redemptions r JOIN promo_codes c ON c.code=r.code "
        "WHERE r.tg_id=:tg_id AND c.batch LIKE 'winback_%' "
        "AND r.created_at >= :since LIMIT 1",
        {"tg_id": tg_id, "since": since.isoformat()})
    return await cur.fetchone() is not None


async def list_codes(db, *, batch: str | None = None, unused_only: bool = False,
                     code: str | None = None, limit: int = 200) -> list[dict]:
    sql = ["SELECT * FROM promo_codes WHERE 1=1"]
    params: dict = {}
    if batch:
        sql.append("AND batch=:batch")
        params["batch"] = batch
    if unused_only:
        sql.append("AND COALESCE(used_count,0)=0")
    if code:
        sql.append("AND code=:code")          # точный код, CS-поиск (G2)
        params["code"] = (code or "").strip().upper()
    sql.append("ORDER BY created_at DESC, code LIMIT :limit")
    params["limit"] = limit
    cur = await db.execute(" ".join(sql), params)
    return [dict(r) for r in await cur.fetchall()]


async def set_codes_active(db, *, batch: str | None = None,
                           code: str | None = None, active: bool) -> int:
    """Отзыв/возврат в строй партии или одного кода (kill switch, G3).

    Ровно один из аргументов batch/code задан — endpoint валидирует,
    repo-функция не оставляет шанс обновить «всё сразу».
    """
    assert (batch is None) != (code is None), "нужен batch или code"
    async with transaction(db):
        cur = await db.execute(
            "UPDATE promo_codes SET is_active=:active WHERE batch=:batch"
            if batch else
            "UPDATE promo_codes SET is_active=:active WHERE code=:code",
            {"active": 1 if active else 0,
             "batch": batch, "code": (code or "").strip().upper()})
        return cur.rowcount


async def batch_codes(db, batch: str) -> list[dict]:
    """Коды партии в стабильном порядке — для CSV-экспорта (G1)."""
    cur = await db.execute(
        "SELECT code, kind, days, plan_code, crystals, sku, batch, "
        "max_uses, used_count, expires_at, created_at, is_active "
        "FROM promo_codes WHERE batch=:batch ORDER BY created_at, code",
        {"batch": batch})
    return [dict(r) for r in await cur.fetchall()]


# ────────────── операторские подарки (BUS-310, BUS-284 §4) ───────────────────

async def reserve_op_gift(db, days: int) -> str | None:
    """Резервирует неиспользованный код из партии op_* на days дней.

    Партии op_{tier}_{YYYY-MM} выпускаются заранее под правом promo;
    endpoint подарка только выдаёт готовые коды. Выбор свежей партии месяца
    (ORDER BY batch DESC) вместо произвольной — атрибуция отчёта §5 остаётся
    предсказуемой. Служебная запись в deliveries(tg_id=0) резервирует код,
    не создавая ложного касания конкретной клиентки; факт выдачи конкретной
    клиентке пишет endpoint отдельной записью (tg_id, op_gift).
    """
    async with transaction(db):
        cur = await db.execute(
            "SELECT c.code FROM promo_codes c "
            "WHERE c.batch LIKE 'op\\_%' ESCAPE '\\' "
            "AND c.days=:days AND c.kind='plan_days' AND c.plan_code='trial' "
            "AND COALESCE(c.used_count,0)=0 AND COALESCE(c.is_active,1)=1 "
            "AND (c.expires_at IS NULL OR c.expires_at > :now) "
            "AND NOT EXISTS (SELECT 1 FROM deliveries d "
            "  WHERE d.kind='op_gift_code' AND d.key=c.code) "
            "ORDER BY c.batch DESC, c.code LIMIT 1 "
            "FOR UPDATE OF c SKIP LOCKED",
            {"days": days, "now": utcnow()})
        row = await cur.fetchone()
        if not row:
            return None
        code = row["code"]
        cur = await db.execute(
            "INSERT INTO deliveries(tg_id, kind, key, created_at) "
            "VALUES(0, 'op_gift_code', :code, :created_at) "
            "ON CONFLICT (tg_id, kind, key) DO NOTHING",
            {"code": code, "created_at": utcnow()})
        if not cur.rowcount:
            return None
        return code


async def last_op_gift_at(db, tg_id: int) -> str | None:
    """ISO-дата последнего операторского подарка клиентки (анти-абьюз §4.1.3).

    Источник — запись выдачи в deliveries: момент выдачи оператором, а не
    момент активации клиенткой (иначе неподактивированный код не держит окно).
    Учитываются и прямые redemptions из партий op_* (клиентка могла получить
    код вне эндпоинта) — берём максимум двух источников.
    """
    cur = await db.execute(
        "SELECT MAX(at) last_at FROM ("
        "  SELECT MAX(d.created_at) at FROM deliveries d "
        "   WHERE d.tg_id=:tg_id AND d.kind='op_gift' "
        "  UNION ALL "
        "  SELECT MAX(r.created_at) FROM promo_redemptions r "
        "   JOIN promo_codes c ON c.code=r.code "
        "   WHERE r.tg_id=:tg_id AND c.batch LIKE 'op\\_%' ESCAPE '\\'"
        ") t", {"tg_id": tg_id})
    row = await cur.fetchone()
    return row["last_at"] if row else None


async def last_op_gift_days(db, tg_id: int) -> int | None:
    """Дни последнего выданного op-подарка — окно анти-абьюза (60/90)."""
    cur = await db.execute(
        "SELECT c.days FROM deliveries d JOIN promo_codes c ON c.code=d.key "
        "WHERE d.tg_id=:tg_id AND d.kind='op_gift' "
        "ORDER BY d.created_at DESC LIMIT 1", {"tg_id": tg_id})
    row = await cur.fetchone()
    return row["days"] if row else None


async def op_batches_report(db, months: int = 6) -> list[dict]:
    """Месячный отчёт по партиям op_* (§4.3, KPI §5): redemption rate + конверсия.

    Конверсия — доля активировавших подарок клиенток, оплативших что-нибудь
    после активации (любой paid-заказ, не только подписка): устойчиво к
    бесплатным активациям и не требует склейки по SKU.
    """
    cur = await db.execute(
        "SELECT c.batch, c.days, COUNT(*) codes, "
        "  SUM(CASE WHEN COALESCE(c.used_count,0)>0 THEN 1 ELSE 0 END) used, "
        "  SUM(CASE WHEN COALESCE(c.is_active,1)=0 THEN 1 ELSE 0 END) inactive, "
        "  MIN(c.created_at) created_at "
        "FROM promo_codes c WHERE c.batch LIKE 'op\\_%' ESCAPE '\\' "
        "GROUP BY c.batch, c.days "
        "ORDER BY c.batch DESC LIMIT :months", {"months": months})
    batches = [dict(r) for r in await cur.fetchall()]
    for b in batches:
        cur = await db.execute(
            "SELECT COUNT(DISTINCT r.tg_id) redeemers, "
            "  COUNT(DISTINCT CASE WHEN EXISTS ("
            "    SELECT 1 FROM orders o WHERE o.tg_id=r.tg_id "
            "    AND o.status='paid' AND o.paid_at >= r.created_at"
            "  ) THEN r.tg_id END) converted "
            "FROM promo_redemptions r JOIN promo_codes c ON c.code=r.code "
            "WHERE c.batch=:batch", {"batch": b["batch"]})
        conv = await cur.fetchone()
        b["redeemers"] = conv["redeemers"]
        b["converted"] = conv["converted"]
        b["redemption_rate"] = round(conv["redeemers"] / b["codes"], 4) if b["codes"] else 0
        b["conversion_rate"] = round(conv["converted"] / conv["redeemers"], 4) if conv["redeemers"] else 0
    return batches


# ─────────────────────────────── рефералы ─────────────────────────────────────

async def record_referral(db, referrer_id: int, invitee_id: int, *,
                          level: int = 1, bonus: int = 0) -> bool:
    """Фиксирует приглашение. False — такое уже записано (UNIQUE-ключ)."""
    async with transaction(db):
        cur = await db.execute(
            "INSERT INTO referrals(referrer_id, invitee_id, level, bonus, "
            "created_at) VALUES(:referrer_id, :invitee_id, :level, :bonus, :created_at) "
            "ON CONFLICT (referrer_id, invitee_id, level) DO NOTHING",
            {"referrer_id": referrer_id, "invitee_id": invitee_id,
             "level": level, "bonus": bonus, "created_at": utcnow()})
        return bool(cur.rowcount)


async def referrer_of(db, tg_id: int) -> int | None:
    cur = await db.execute(
        "SELECT referrer_id FROM referrals WHERE invitee_id=:tg_id AND level=1",
        {"tg_id": tg_id})
    row = await cur.fetchone()
    return row["referrer_id"] if row else None


async def referral_stats(db, tg_id: int) -> dict:
    cur = await db.execute(
        "SELECT level, COUNT(*) n, COALESCE(SUM(bonus),0) bonus FROM referrals "
        "WHERE referrer_id=:tg_id GROUP BY level", {"tg_id": tg_id})
    rows = {r["level"]: dict(r) for r in await cur.fetchall()}
    # сколько приглашённых дошли до оплаты — главный аргумент делиться ссылкой
    cur = await db.execute(
        "SELECT COUNT(*) n FROM referrals r JOIN users u ON u.tg_id = r.invitee_id "
        "WHERE r.referrer_id=:tg_id AND r.level=1 AND u.ltv_stars > 0", {"tg_id": tg_id})
    paying = (await cur.fetchone())["n"]
    return {
        "level1": rows.get(1, {}).get("n", 0),
        "level2": rows.get(2, {}).get("n", 0),
        "bonus_total": sum(r["bonus"] for r in rows.values()),
        "paying": paying,
    }


async def top_referrers(db, limit: int = 20) -> list[dict]:
    cur = await db.execute(
        "SELECT r.referrer_id tg_id, MAX(u.name) name, MAX(u.username) username, "
        "COUNT(*) invited, COALESCE(SUM(r.bonus),0) bonus FROM referrals r "
        "LEFT JOIN users u ON u.tg_id = r.referrer_id WHERE r.level=1 "
        "GROUP BY r.referrer_id, u.name, u.username "
        "ORDER BY invited DESC LIMIT :limit", {"limit": limit})
    return [dict(r) for r in await cur.fetchall()]
