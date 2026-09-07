"""LTV-тиры и очередь внимания (BUS-309, BUS-284 §1/§2).

Публичные функции:
- `ltv_tier(db, tg_id)` — тир клиентки + метрики.
- `attention_queue(db)` — 7 правил, сортировка, счётчики.
- `user_card_ltv(db, tg_id)` — объект `ltv` для `crm.user_card`.

Все функции on-demand, без миграций и фоновых джобов.
Синтетика tg_id 10001/10002 исключается (BUS-183).
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from ..data.session import utcnow
from . import billing, content, dialog, users
from .ltv_constants import (
    FORBIDDEN_EXCLUDE_RULES,
    P1, P2, P3, P1_SLA_HOURS, P2_SLA_DAYS, P3_SLA_DAYS,
    PRIORITY_ORDER, RULE_Q1, RULE_Q2, RULE_Q3, RULE_Q4,
    RULE_Q5, RULE_Q6, RULE_Q7,
    RULE_TO_PLAYBOOK,
    RISK_EXPIRING, RISK_LIMIT_HITS,
    RISK_RECENT_REFUND, RISK_SLEEPING,
    SYNTHETIC_TG_ID_RANGE_HIGH, SYNTHETIC_TG_ID_RANGE_LOW,
    SYNTHETIC_TG_IDS, TIER_A, TIER_B, TIER_C, TIER_D, TIER_NONE,
    TIERS_ORDER,
)

# ──────────────────────────────────────────────────────────────────────────────
# Вспомогательные
# ──────────────────────────────────────────────────────────────────────────────

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _is_synthetic(tg_id: int) -> bool:
    if tg_id in SYNTHETIC_TG_IDS:
        return True
    return SYNTHETIC_TG_ID_RANGE_LOW <= tg_id <= SYNTHETIC_TG_ID_RANGE_HIGH


def _days_since(iso: str | None, ref: datetime | None = None) -> int | None:
    if not iso:
        return None
    ref = ref or _now()
    try:
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return max(0, (ref - dt).days)
    except (TypeError, ValueError):
        return None


def _tier_sort_key(tier: str | None) -> int:
    """Меньше → выше в сортировке."""
    if tier is None:
        return len(TIERS_ORDER)
    try:
        return TIERS_ORDER.index(tier)
    except ValueError:
        return len(TIERS_ORDER)


def _priority_sort_key(p: str) -> int:
    try:
        return PRIORITY_ORDER.index(p)
    except ValueError:
        return len(PRIORITY_ORDER)


# ──────────────────────────────────────────────────────────────────────────────
# LTV-тир
# ──────────────────────────────────────────────────────────────────────────────

async def ltv_tier(db, tg_id: int) -> dict | None:
    """Тир клиентки + метрики.

    Returns:
        {"tier": A|B|C|D|null, "ltv_stars": int, "payments_count": int,
         "avg_check_stars": int, "days_as_payer": int | None}
        None — синтетика или пользователь не найден.
    """
    if _is_synthetic(tg_id):
        return None

    user = await users.get(db, tg_id)
    if not user:
        return None

    ltv_stars = int(user.get("ltv_stars") or 0)
    created_at = user.get("created_at")

    # ── платежи ─────────────────────────────────────────────────────────────
    payments_count, avg_check = await _payment_stats(db, tg_id)

    # ── топ-20% порог (A) ────────────────────────────────────────────────────
    top_threshold = await _top_20_percent_threshold(db)

    # ── miniapp_open за 14 дней (для C) ─────────────────────────────────────
    miniapp_14d = await _event_count(db, tg_id, "miniapp_open", days=14)

    # ── стрик практик (для C) ────────────────────────────────────────────────
    # Стрик трактуем шире diary: практика ≥3 тоже признак активности
    # (консистентно с сегментом ritual_streak_3plus).
    streak = await dialog.diary_streak(db, tg_id)
    if streak < 3:
        cur = await db.execute(
            "SELECT COUNT(*) AS n FROM practices "
            "WHERE tg_id=:tg_id AND streak>=3 AND finished_at IS NULL",
            {"tg_id": tg_id})
        if int((await cur.fetchone())["n"] or 0) > 0:
            streak = max(streak, 3)

    # ── A: топ-20% ИЛИ ≥2 платежа ───────────────────────────────────────────
    # Нулевая база платящих деградирует естественно: A/B не присваиваются
    # (порог не вычислен, платежей нет), C/D остаются достижимы — иначе
    # правило Q6 (тир D) было бы мертво до первого платежа.
    if ltv_stars > 0 and (
            payments_count >= 2
            or (top_threshold is not None and ltv_stars >= top_threshold)):
        days_payer = await _days_as_payer(db, tg_id)
        return {
            "tier": TIER_A,
            "ltv_stars": ltv_stars,
            "payments_count": payments_count,
            "avg_check_stars": avg_check,
            "days_as_payer": days_payer,
        }

    # ── B: ≥1 платёж ────────────────────────────────────────────────────────
    if payments_count >= 1:
        days_payer = await _days_as_payer(db, tg_id)
        return {
            "tier": TIER_B,
            "ltv_stars": ltv_stars,
            "payments_count": payments_count,
            "avg_check_stars": avg_check,
            "days_as_payer": days_payer,
        }

    # ── C: never_paid + ≥3 miniapp_open за 14д ИЛИ стрик ≥3 ────────────────
    if miniapp_14d >= 3 or streak >= 3:
        return {
            "tier": TIER_C,
            "ltv_stars": 0,
            "payments_count": 0,
            "avg_check_stars": 0,
            "days_as_payer": None,
        }

    # ── D: создана ≤7 дней назад ────────────────────────────────────────────
    days_since_created = _days_since(created_at)
    if days_since_created is not None and days_since_created <= 7:
        return {
            "tier": TIER_D,
            "ltv_stars": 0,
            "payments_count": 0,
            "avg_check_stars": 0,
            "days_as_payer": None,
        }

    # ── вне тира ─────────────────────────────────────────────────────────────
    return {
        "tier": TIER_NONE,
        "ltv_stars": ltv_stars,
        "payments_count": 0,
        "avg_check_stars": 0,
        "days_as_payer": None,
    }


async def _payment_stats(db, tg_id: int) -> tuple[int, int]:
    """(payments_count, avg_check_stars) по успешным платежам."""
    cur = await db.execute(
        "SELECT COUNT(*) AS n, COALESCE(AVG(amount_stars),0) AS avg_check "
        "FROM orders WHERE tg_id=:tg_id AND status='paid'",
        {"tg_id": tg_id})
    row = await cur.fetchone()
    return int(row["n"] or 0), int(round(row["avg_check"] or 0))


async def _top_20_percent_threshold(db) -> int | None:
    """Порог ltv_stars для топ-20% платящих.

    Процентиль — настройка `crm.ltv_top_percent` в таблице settings
    (BUS-284 §1: не хардкод), по умолчанию 20. PostgreSQL: percentile_cont.
    SQLite dev: None (деградация — без порога все платящие → B, не A;
    урок BUS-166 F-3).
    """
    percent = 20
    try:
        stored = await content.get_setting(db, "crm.ltv_top_percent", None)
        if stored is not None:
            percent = max(1, min(99, int(stored)))
    except (TypeError, ValueError):
        percent = 20

    url = str(db.url if hasattr(db, "url") else "")
    if url.startswith("sqlite"):
        return None

    try:
        cur = await db.execute(
            f"SELECT percentile_cont({(100 - percent) / 100:.4f}) WITHIN GROUP "
            f"(ORDER BY ltv_stars) AS p FROM users WHERE ltv_stars > 0")
        row = await cur.fetchone()
        val = row["p"] if row else None
        return int(round(val)) if val is not None else None
    except Exception:  # noqa: BLE001
        return None


async def _event_count(db, tg_id: int, name: str, days: int = 14) -> int:
    since = (_now() - timedelta(days=days)).isoformat()
    cur = await db.execute(
        "SELECT COUNT(*) AS n FROM events "
        "WHERE tg_id=:tg_id AND name=:name AND created_at>=:since",
        {"tg_id": tg_id, "name": name, "since": since})
    return int((await cur.fetchone())["n"] or 0)


async def _days_as_payer(db, tg_id: int) -> int | None:
    """Дней с первого платежа (первая paid-дата → сегодня)."""
    cur = await db.execute(
        "SELECT MIN(paid_at) first_paid FROM orders "
        "WHERE tg_id=:tg_id AND status='paid'",
        {"tg_id": tg_id})
    row = await cur.fetchone()
    first = row["first_paid"] if row else None
    if not first:
        return None
    return _days_since(first)


# ──────────────────────────────────────────────────────────────────────────────
# Канал закрыт (from deliveries)
# ──────────────────────────────────────────────────────────────────────────────

async def channel_closed(db, tg_id: int) -> bool:
    """True — последняя известная доставка — forbidden (и не открыта снова).

    Семантика BUS-284 §0.4: закрыт от forbidden-записи до первой успешной
    доставки после неё.
    """
    if _is_synthetic(tg_id):
        return False

    # Схема со status (BUS-308): ищем последнюю запись не-tg_id=0 и не winback2_code.
    cur = await db.execute(
        "SELECT status, created_at FROM deliveries "
        "WHERE tg_id=:tg_id AND kind != 'winback2_code' "
        "ORDER BY created_at DESC LIMIT 5",
        {"tg_id": tg_id})
    rows = await cur.fetchall()

    if not rows:
        return False

    # Если есть успешная доставка ПОСЛЕ последней forbidden — канал открыт.
    # rows отсортированы по created_at DESC, поэтому первый sent перекрывает.
    has_open = any(r["status"] == "sent" for r in rows)
    if has_open:
        return False

    # Нет отправленных, есть forbidden → закрыт.
    has_forbidden = any(r["status"] == "forbidden" for r in rows)
    return has_forbidden


# ──────────────────────────────────────────────────────────────────────────────
# Очередь внимания (7 правил)
# ──────────────────────────────────────────────────────────────────────────────

# Окно правил (часы/дни)
Q1_WINDOW_HOURS = 48
Q2_SUB_EXPIRED_DAYS = 5
Q3_OFFER_DAYS = 7
Q4_LIMIT_HITS_DAYS = 7
Q5_FAILED_WINDOW_HOURS = 24
Q6_CREATED_DAYS = 3
Q7_GAP_DAYS = 30
Q7_RETURN_WINDOW_HOURS = 48


async def attention_queue(db, limit: int = 50) -> dict:
    """Очередь внимания: 7 правил, on-demand.

    Returns:
        {"items": [...], "counts": {"p1": N, ...}, "overdue": {...},
         "limit": 50, "truncated": bool}
    """
    if await _is_synthetic_tg_ids_only(db):
        return _empty_queue(limit)

    now = _now()
    q1_ids = await _q1_refund(db, now)
    q2_ids = await _q2_vip_sleeping(db, now)
    q3_ids = await _q3_wb2_no_redemption(db, now)
    q4_ids = await _q4_limit_hits(db, now)
    q5_ids = await _q5_delivery_failed(db, now)
    q6_ids = await _q6_new_not_onboarded(db, now)
    q7_ids = await _q7_return_gap(db, now)

    # forbidden-исключение
    forbidden_ids = await _forbidden_clients(db)
    q2_ids -= forbidden_ids
    q3_ids -= forbidden_ids
    q4_ids -= forbidden_ids
    q6_ids -= forbidden_ids
    q7_ids -= forbidden_ids
    # Q1 не исключается, Q5 — её канал обслуживания

    rule_map = {
        RULE_Q1: q1_ids, RULE_Q2: q2_ids, RULE_Q3: q3_ids,
        RULE_Q4: q4_ids, RULE_Q5: q5_ids, RULE_Q6: q6_ids, RULE_Q7: q7_ids,
    }

    cards = []
    for rule, ids in rule_map.items():
        for tg_id in ids:
            tier_info = await ltv_tier(db, tg_id)
            tier = tier_info["tier"] if tier_info else None
            user = await users.get(db, tg_id)
            if not user:
                continue
            cards.append(await _build_card(db, tg_id, user, tier, rule, now))

    # Сортировка: priority → tier (A раньше) → давность
    cards.sort(key=lambda c: (
        _priority_sort_key(c["priority"]),
        _tier_sort_key(c.get("tier")),
        c.get("triggered_at", ""),
    ))

    truncated = len(cards) > limit
    items = cards[:limit]

    # Счётчики по всей очереди (не по лимиту)
    counts = {P1: 0, P2: 0, P3: 0}
    overdue = {P1: 0, P2: 0, P3: 0}
    for c in cards:
        p = c["priority"]
        counts[p] = counts.get(p, 0) + 1
        if c.get("overdue"):
            overdue[p] = overdue.get(p, 0) + 1

    return {
        "items": items,
        "counts": counts,
        "overdue": overdue,
        "limit": limit,
        "truncated": truncated,
    }


async def _is_synthetic_tg_ids_only(db) -> bool:
    """True если в users только синтетика (деградация нулевой базы)."""
    cur = await db.execute(
        "SELECT COUNT(*) AS n FROM users WHERE tg_id NOT IN (10001, 10002) AND tg_id NOT BETWEEN 999000000 AND 999999999")
    return int((await cur.fetchone())["n"] or 0) == 0


def _empty_queue(limit: int = 50) -> dict:
    return {"items": [], "counts": {P1: 0, P2: 0, P3: 0},
            "overdue": {P1: 0, P2: 0, P3: 0}, "limit": limit, "truncated": False}


# ─────────────────────────── правила Q1..Q7 ──────────────────────────────────

async def _q1_refund(db, now: datetime) -> set[int]:
    """P1: refund_requested/completed за 48ч."""
    since = (now - timedelta(hours=Q1_WINDOW_HOURS)).isoformat()
    cur = await db.execute(
        "SELECT DISTINCT tg_id FROM events "
        "WHERE name IN ('refund_requested', 'refund_completed') "
        "AND tg_id IS NOT NULL AND created_at>=:since "
        "AND tg_id NOT IN (10001, 10002) AND tg_id NOT BETWEEN 999000000 AND 999999999",
        {"since": since})
    return {r["tg_id"] for r in await cur.fetchall()}


async def _q2_vip_sleeping(db, now: datetime) -> set[int]:
    """P1: тир A + (sleeping_14d ИЛИ sub истекла 5+ дней)."""
    tier_a = await _tier_a_ids(db)
    sleeping = await _segment_ids(db, "sleeping_14d")
    expired_5d = await _expired_5d_ids(db, now)
    return (sleeping | expired_5d) & tier_a


async def _q3_wb2_no_redemption(db, now: datetime) -> set[int]:
    """P1: тир A/B, WB2 отправлен 7+ дней, нет redemption, подписка неактивна."""
    tier_ab = await _tier_a_b_ids(db)
    wb2_old = await _wb2_sent_7d_ago_ids(db, now)
    no_redemption = await _no_winback_redemption_90d_ids(db, wb2_old)
    not_active = await _segment_ids(db, "expired")
    return no_redemption & not_active & tier_ab


async def _q4_limit_hits(db, now: datetime) -> set[int]:
    """P2: ≥3 limit_reached за 7 дней."""
    since = (now - timedelta(days=Q4_LIMIT_HITS_DAYS)).isoformat()
    cur = await db.execute(
        "SELECT tg_id, COUNT(*) AS n FROM events "
        "WHERE name='limit_reached' AND tg_id IS NOT NULL "
        "AND created_at>=:since AND tg_id NOT IN (10001, 10002) AND tg_id NOT BETWEEN 999000000 AND 999999999 "
        "GROUP BY tg_id HAVING COUNT(*)>=3",
        {"since": since})
    return {r["tg_id"] for r in await cur.fetchall()}


async def _q5_delivery_failed(db, now: datetime) -> set[int]:
    """P2: deliveries failed/forbidden за 24ч, kind≠winback2_code, одна карточка."""
    since = (now - timedelta(hours=Q5_FAILED_WINDOW_HOURS)).isoformat()
    cur = await db.execute(
        "SELECT DISTINCT tg_id FROM deliveries "
        "WHERE status IN ('failed', 'forbidden') "
        "AND kind != 'winback2_code' "
        "AND tg_id != 0 "
        "AND tg_id NOT IN (10001, 10002) AND tg_id NOT BETWEEN 999000000 AND 999999999 "
        "AND created_at>=:since",
        {"since": since})
    return {r["tg_id"] for r in await cur.fetchall()}


async def _q6_new_not_onboarded(db, now: datetime) -> set[int]:
    """P3: тир D, onboarded=0, created_at ≥3д, O1 ушёл."""
    tier_d = await _tier_d_ids(db)
    not_onboarded = await _segment_ids(db, "not_onboarded")
    o1_sent = await _o1_sent_ids(db)
    return tier_d & not_onboarded & o1_sent


async def _q7_return_gap(db, now: datetime) -> set[int]:
    """P3: возврат — miniapp_open за 48ч, а до него пауза ≥30д.

    Первый-ever open возвратом не считается: должен существовать предыдущий
    open, отстоящий от текущего ≥Q7_GAP_DAYS.
    """
    since_window = (now - timedelta(hours=Q7_RETURN_WINDOW_HOURS)).isoformat()
    gap_before = (now - timedelta(days=Q7_GAP_DAYS)).isoformat()
    cur = await db.execute(
        "SELECT DISTINCT tg_id FROM events cur "
        "WHERE cur.name='miniapp_open' AND cur.tg_id IS NOT NULL "
        "AND cur.created_at>=:since_window "
        "AND cur.tg_id NOT IN (10001, 10002) AND tg_id NOT BETWEEN 999000000 AND 999999999 "
        "AND NOT EXISTS ("
        "  SELECT 1 FROM events mid "
        "  WHERE mid.tg_id=cur.tg_id AND mid.name='miniapp_open' "
        "  AND mid.created_at > :gap_before "
        "  AND mid.created_at < cur.created_at"
        ") "
        "AND EXISTS ("
        "  SELECT 1 FROM events prev "
        "  WHERE prev.tg_id=cur.tg_id AND prev.name='miniapp_open' "
        "  AND prev.created_at <= :gap_before"
        ")",
        {"since_window": since_window, "gap_before": gap_before})
    return {r["tg_id"] for r in await cur.fetchall()}


# ─────────────────────────── forbidden-исключение ────────────────────────────

async def _forbidden_clients(db) -> set[int]:
    """Клиентки, чей последний статус — forbidden (канал закрыт)."""
    cur = await db.execute("""
        SELECT DISTINCT d.tg_id FROM deliveries d
        WHERE d.kind != 'winback2_code' AND d.tg_id != 0
        AND d.tg_id NOT IN (10001, 10002) AND d.tg_id NOT BETWEEN 999000000 AND 999999999
        AND d.status = 'forbidden'
        AND NOT EXISTS (
            SELECT 1 FROM deliveries d2
            WHERE d2.tg_id = d.tg_id
              AND d2.kind != 'winback2_code'
              AND d2.status = 'sent'
              AND d2.created_at > d.created_at
        )
    """)
    return {r["tg_id"] for r in await cur.fetchall()}


# ─────────────────────────── вспомогательные выборки ─────────────────────────

async def _tier_a_ids(db) -> set[int]:
    cur = await db.execute(
        "SELECT tg_id FROM users WHERE ltv_stars > 0 "
        "AND tg_id NOT IN (10001, 10002) AND tg_id NOT BETWEEN 999000000 AND 999999999")
    rows = await cur.fetchall()
    candidates = {r["tg_id"] for r in rows}
    if not candidates:
        return set()
    two_payers = await _users_with_payments(db, min_count=2)
    threshold = await _top_20_percent_threshold(db)
    if threshold is None:
        # SQLite: только правило «≥2 платежа»
        return candidates & two_payers
    return {tg_id for tg_id in candidates
            if await _user_ltv_stars(db, tg_id) >= threshold} | two_payers


async def _tier_a_b_ids(db) -> set[int]:
    cur = await db.execute(
        "SELECT tg_id FROM users WHERE ltv_stars > 0 "
        "AND tg_id NOT IN (10001, 10002) AND tg_id NOT BETWEEN 999000000 AND 999999999")
    return {r["tg_id"] for r in await cur.fetchall()}


async def _tier_d_ids(db) -> set[int]:
    cur = await db.execute(
        "SELECT tg_id, created_at FROM users WHERE onboarded=0 "
        "AND tg_id NOT IN (10001, 10002) AND tg_id NOT BETWEEN 999000000 AND 999999999")
    now = _now()
    result = set()
    for r in await cur.fetchall():
        days = _days_since(r["created_at"], now)
        if days is not None and days >= Q6_CREATED_DAYS:
            result.add(r["tg_id"])
    return result


async def _segment_ids(db, segment: str) -> set[int]:
    """Сегмент через users.segment_ids; синтетика исключена (BUS-183)."""
    try:
        return set(await users.segment_ids(db, segment)) - SYNTHETIC_TG_IDS
    except Exception:  # noqa: BLE001
        return set()


async def _expired_5d_ids(db, now: datetime) -> set[int]:
    cutoff = (now - timedelta(days=Q2_SUB_EXPIRED_DAYS)).isoformat()
    cur = await db.execute(
        "SELECT tg_id FROM users "
        "WHERE sub_until IS NOT NULL AND sub_until <= :cutoff "
        "AND tg_id NOT IN (10001, 10002) AND tg_id NOT BETWEEN 999000000 AND 999999999",
        {"cutoff": cutoff})
    return {r["tg_id"] for r in await cur.fetchall()}


async def _wb2_sent_7d_ago_ids(db, now: datetime) -> set[int]:
    cutoff = (now - timedelta(days=Q3_OFFER_DAYS)).isoformat()
    cur = await db.execute(
        "SELECT DISTINCT tg_id FROM deliveries "
        "WHERE kind='winback2' AND created_at<=:cutoff "
        "AND tg_id NOT IN (10001, 10002) AND tg_id NOT BETWEEN 999000000 AND 999999999",
        {"cutoff": cutoff})
    return {r["tg_id"] for r in await cur.fetchall()}


async def _no_winback_redemption_90d_ids(db, candidates: set[int]) -> set[int]:
    """Из candidates исключаем тех, кто активировал winback за 90д."""
    if not candidates:
        return set()
    since = (_now() - timedelta(days=90)).isoformat()
    ids = sorted(tg_id for tg_id in candidates if isinstance(tg_id, int))
    if not ids:
        return set()
    placeholders = ",".join(f":i{k}" for k in range(len(ids)))
    params = {f"i{k}": v for k, v in enumerate(ids)}
    params["since"] = since
    cur = await db.execute(
        f"SELECT DISTINCT r.tg_id FROM promo_redemptions r "
        f"JOIN promo_codes c ON c.code=r.code "
        f"WHERE c.batch LIKE 'winback_%' AND r.created_at>=:since "
        f"AND r.tg_id IN ({placeholders})",
        params)
    redeemed = {r["tg_id"] for r in await cur.fetchall()}
    return candidates - redeemed


async def _o1_sent_ids(db) -> set[int]:
    """Ушёл ли O1: deliveries с kind, связанным с onboarding.

    Цепочка O1 (onboard_nudge) не реализована в текущем коде, поэтому
    деградация: если таких записей нет — никто не попадает под Q6.
    """
    cur = await db.execute(
        "SELECT DISTINCT tg_id FROM deliveries "
        "WHERE kind IN ('onboard_nudge', 'welcome_chain') "
        "AND key LIKE 'd1:%'")
    return {r["tg_id"] for r in await cur.fetchall()}


async def _users_with_payments(db, min_count: int = 1) -> set[int]:
    cur = await db.execute(
        "SELECT tg_id, COUNT(*) AS n FROM orders "
        "WHERE status='paid' GROUP BY tg_id HAVING COUNT(*)>=:n",
        {"n": min_count})
    return {r["tg_id"] for r in await cur.fetchall()}


async def _user_ltv_stars(db, tg_id: int) -> int:
    cur = await db.execute(
        "SELECT ltv_stars FROM users WHERE tg_id=:tg_id",
        {"tg_id": tg_id})
    row = await cur.fetchone()
    return int(row["ltv_stars"] or 0) if row else 0


# ──────────────────────────────────────────────────────────────────────────────
# Построение карточки
# ──────────────────────────────────────────────────────────────────────────────

async def _build_card(db, tg_id: int, user: dict, tier: str | None,
                      rule: str, now: datetime) -> dict:
    """Одна карточка очереди."""
    priority = _rule_priority(rule)
    playbook = RULE_TO_PLAYBOOK[rule]
    reason_data = await _reason_data(db, tg_id, rule, now)
    ch_closed = await channel_closed(db, tg_id)

    # triggered_at — самое раннее событие, запустившее правило
    triggered_at = await _triggered_at(db, tg_id, rule, now)

    # SLA
    sla_hours = P1_SLA_HOURS if priority == P1 else P2_SLA_DAYS * 24
    sla_due_at = (now + timedelta(hours=sla_hours)).isoformat()
    overdue = _is_overdue(triggered_at, now, priority)

    return {
        "tg_id": tg_id,
        "display": user.get("name") or f"@{user.get('username', tg_id)}",
        "priority": priority,
        "rule": rule,
        "playbook": playbook,
        "tier": tier,
        "reason_data": reason_data,
        "triggered_at": triggered_at,
        "sla_due_at": sla_due_at,
        "overdue": overdue,
        "channel_closed": ch_closed,
    }


def _rule_priority(rule: str) -> str:
    mapping = {RULE_Q1: P1, RULE_Q2: P1, RULE_Q3: P1,
               RULE_Q4: P2, RULE_Q5: P2,
               RULE_Q6: P3, RULE_Q7: P3}
    return mapping.get(rule, P3)


async def _triggered_at(db, tg_id: int, rule: str, now: datetime) -> str | None:
    """Самое раннее событие/запись, запустившая правило."""
    if rule == RULE_Q1:
        since = (now - timedelta(hours=Q1_WINDOW_HOURS)).isoformat()
        cur = await db.execute(
            "SELECT MIN(created_at) at FROM events "
            "WHERE tg_id=:tg_id AND name IN ('refund_requested','refund_completed') "
            "AND created_at>=:since",
            {"tg_id": tg_id, "since": since})
    elif rule == RULE_Q4:
        since = (now - timedelta(days=Q4_LIMIT_HITS_DAYS)).isoformat()
        cur = await db.execute(
            "SELECT MIN(created_at) at FROM events "
            "WHERE tg_id=:tg_id AND name='limit_reached' AND created_at>=:since",
            {"tg_id": tg_id, "since": since})
    elif rule == RULE_Q5:
        since = (now - timedelta(hours=Q5_FAILED_WINDOW_HOURS)).isoformat()
        cur = await db.execute(
            "SELECT MIN(created_at) at FROM deliveries "
            "WHERE tg_id=:tg_id AND status IN ('failed','forbidden') "
            "AND kind!='winback2_code' AND tg_id!=0 AND created_at>=:since",
            {"tg_id": tg_id, "since": since})
    elif rule == RULE_Q7:
        since = (now - timedelta(hours=Q7_RETURN_WINDOW_HOURS)).isoformat()
        cur = await db.execute(
            "SELECT MIN(created_at) at FROM events "
            "WHERE tg_id=:tg_id AND name='miniapp_open' AND created_at>=:since",
            {"tg_id": tg_id, "since": since})
    elif rule == RULE_Q3:
        since = (now - timedelta(days=Q3_OFFER_DAYS)).isoformat()
        cur = await db.execute(
            "SELECT MIN(created_at) at FROM deliveries "
            "WHERE tg_id=:tg_id AND kind='winback2' AND created_at<=:since",
            {"tg_id": tg_id, "since": since})
    else:
        return now.isoformat()
    row = await cur.fetchone()
    return row["at"] if row and row["at"] else now.isoformat()


def _is_overdue(triggered_at: str | None, now: datetime, priority: str) -> bool:
    if not triggered_at:
        return False
    try:
        dt = datetime.fromisoformat(triggered_at)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        if priority == P1:
            return (now - dt).total_seconds() > P1_SLA_HOURS * 3600
        return (now - dt).days > (P2_SLA_DAYS if priority in (P2, P3) else P3_SLA_DAYS)
    except (TypeError, ValueError):
        return False


# ──────────────────────────────────────────────────────────────────────────────
# reason_data по правилам
# ──────────────────────────────────────────────────────────────────────────────

async def _reason_data(db, tg_id: int, rule: str, now: datetime) -> dict:
    if rule == RULE_Q1:
        return await _rd_q1(db, tg_id, now)
    if rule == RULE_Q2:
        return await _rd_q2(db, tg_id, now)
    if rule == RULE_Q3:
        return await _rd_q3(db, tg_id, now)
    if rule == RULE_Q4:
        return await _rd_q4(db, tg_id, now)
    if rule == RULE_Q5:
        return await _rd_q5(db, tg_id, now)
    if rule == RULE_Q6:
        return await _rd_q6(db, tg_id, now)
    if rule == RULE_Q7:
        return await _rd_q7(db, tg_id, now)
    return {}


async def _rd_q1(db, tg_id: int, now: datetime) -> dict:
    since = (now - timedelta(hours=Q1_WINDOW_HOURS)).isoformat()
    cur = await db.execute(
        "SELECT o.id FROM orders o "
        "WHERE o.tg_id=:tg_id AND o.status='refunded' "
        "AND o.paid_at>=:since ORDER BY o.id DESC LIMIT 1",
        {"tg_id": tg_id, "since": since})
    row = await cur.fetchone()
    return {"order_ref": f"#{row['id']}" if row else None}


async def _rd_q2(db, tg_id: int, now: datetime) -> dict:
    sleeping_days = await _segment_sleeping_days(db, tg_id)
    sub_days = await _sub_expired_days(db, tg_id)
    return {
        "sleeping_days": sleeping_days,
        "sub_expired_days": sub_days,
    }


async def _rd_q3(db, tg_id: int, now: datetime) -> dict:
    since = (now - timedelta(days=Q3_OFFER_DAYS)).isoformat()
    cur = await db.execute(
        "SELECT created_at FROM deliveries "
        "WHERE tg_id=:tg_id AND kind='winback2' AND created_at<=:since "
        "ORDER BY created_at DESC LIMIT 1",
        {"tg_id": tg_id, "since": since})
    row = await cur.fetchone()
    offer_sent = row["created_at"] if row else None
    offer_exp = None
    if offer_sent:
        try:
            dt = datetime.fromisoformat(offer_sent)
            offer_exp = (dt + timedelta(days=14)).isoformat()
        except (TypeError, ValueError):
            pass
    return {"offer_sent_at": offer_sent, "offer_expires_at": offer_exp,
            "wb2_kind": "winback2"}


async def _rd_q4(db, tg_id: int, now: datetime) -> dict:
    since = (now - timedelta(days=Q4_LIMIT_HITS_DAYS)).isoformat()
    cur = await db.execute(
        "SELECT COUNT(*) AS n FROM events "
        "WHERE tg_id=:tg_id AND name='limit_reached' AND created_at>=:since",
        {"tg_id": tg_id, "since": since})
    n = int((await cur.fetchone())["n"] or 0)
    user = await users.get(db, tg_id)
    sub_level = (user.get("sub_level") or "free") if user else "free"
    plan_obj = await billing.get_plan(db, sub_level)
    plan = plan_obj.get("code", sub_level) if plan_obj else sub_level
    next_plan = await _next_plan(db, plan)
    deep_link = f"/admin/users/{tg_id}"
    return {
        "limit_hits_count": n,
        "plan": plan,
        "next_plan": next_plan,
        "deep_link": deep_link,
    }


async def _rd_q5(db, tg_id: int, now: datetime) -> dict:
    since = (now - timedelta(hours=Q5_FAILED_WINDOW_HOURS)).isoformat()
    cur = await db.execute(
        "SELECT status, error, kind, created_at FROM deliveries "
        "WHERE tg_id=:tg_id AND status IN ('failed','forbidden') "
        "AND kind!='winback2_code' AND tg_id!=0 AND created_at>=:since "
        "ORDER BY created_at DESC LIMIT 1",
        {"tg_id": tg_id, "since": since})
    row = await cur.fetchone()
    return {
        "delivery_status": row["status"] if row else None,
        "error_class": row["error"] if row else None,
        "delivery_kind": row["kind"] if row else None,
        "delivery_created_at": row["created_at"] if row else None,
    }


async def _rd_q6(db, tg_id: int, now: datetime) -> dict:
    user = await users.get(db, tg_id)
    days = _days_since(user.get("created_at") if user else None, now)
    o1 = tg_id in await _o1_sent_ids(db)
    return {"days_since_created": days, "o1_sent": o1}


async def _rd_q7(db, tg_id: int, now: datetime) -> dict:
    cur = await db.execute(
        "SELECT MIN(created_at) first, MAX(created_at) last FROM events "
        "WHERE tg_id=:tg_id AND name='miniapp_open'",
        {"tg_id": tg_id})
    row = await cur.fetchone()
    first = row["first"] if row else None
    last = row["last"] if row else None
    gap = None
    if first and last and first != last:
        try:
            gap = max(0, (
                datetime.fromisoformat(last) - datetime.fromisoformat(first)
            ).days)
        except (TypeError, ValueError):
            pass
    return {"gap_days": gap}


# ──────────────────────────────────────────────────────────────────────────────
# user_card.ltv
# ──────────────────────────────────────────────────────────────────────────────

async def user_card_ltv(db, tg_id: int) -> dict | None:
    """Объект `ltv` для `crm.user_card` (§6).

    Returns None для синтетики или несуществующего пользователя.
    """
    if _is_synthetic(tg_id):
        return None

    user = await users.get(db, tg_id)
    if not user:
        return None

    tier_info = await ltv_tier(db, tg_id)
    if not tier_info:
        return None

    tier = tier_info["tier"]
    ch_closed = await channel_closed(db, tg_id)

    # Риск-флаги
    risk_flags = await _risk_flags(db, tg_id)

    # Next best action — прямая проверка правил для одной клиентки
    # (пересчёт всей очереди ради одной карточки — слишком дорого)
    next_best = await _next_best_action(db, tg_id)

    # Таймлайн касаний (comms-журнал + deliveries со статусом)
    timeline = await _timeline(db, tg_id)

    return {
        "tier": tier,
        "tier_recalc_at": utcnow(),
        "ltv_stars": tier_info["ltv_stars"],
        "payments_count": tier_info["payments_count"],
        "avg_check_stars": tier_info["avg_check_stars"],
        "days_as_payer": tier_info["days_as_payer"],
        "crystals_bought": await _crystals_bought(db, tg_id),
        "crystals_granted": await _crystals_granted(db, tg_id),
        "risk_flags": risk_flags,
        "channel_closed": ch_closed,
        "next_best_action": next_best,
        "timeline": timeline,
    }


async def _next_best_action(db, tg_id: int) -> dict | None:
    """Карточка очереди для этой клиентки: первое сработавшее правило
    в порядке P1→P2→P3 (тот же порядок, что в attention_queue).
    forbidden-исключение применяется так же, как в очереди."""
    now = _now()
    checks = [
        (RULE_Q1, lambda: _q1_refund(db, now)),
        (RULE_Q2, lambda: _q2_vip_sleeping(db, now)),
        (RULE_Q3, lambda: _q3_wb2_no_redemption(db, now)),
        (RULE_Q4, lambda: _q4_limit_hits(db, now)),
        (RULE_Q5, lambda: _q5_delivery_failed(db, now)),
        (RULE_Q6, lambda: _q6_new_not_onboarded(db, now)),
        (RULE_Q7, lambda: _q7_return_gap(db, now)),
    ]
    forbidden = await _forbidden_clients(db)
    for rule, ids_fn in checks:
        try:
            ids = await ids_fn()
        except Exception:  # noqa: BLE001
            continue
        if tg_id not in ids:
            continue
        if rule in FORBIDDEN_EXCLUDE_RULES and tg_id in forbidden:
            continue
        return {"rule": rule, "playbook": RULE_TO_PLAYBOOK[rule]}
    return None


async def _risk_flags(db, tg_id: int) -> list[str]:
    """Флаги риска — enum-ключи, метки на клиенте."""
    flags = []
    try:
        if tg_id in set(await users.segment_ids(db, "sleeping_14d") or []):
            flags.append(RISK_SLEEPING)
    except Exception:  # noqa: BLE001
        pass
    try:
        if tg_id in set(await users.segment_ids(db, "expiring_3d") or []):
            flags.append(RISK_EXPIRING)
    except Exception:  # noqa: BLE001
        pass
    try:
        if tg_id in set(await users.segment_ids(db, "limit_hitters") or []):
            flags.append(RISK_LIMIT_HITS)
    except Exception:  # noqa: BLE001
        pass
    cur = await db.execute(
        "SELECT 1 FROM events WHERE tg_id=:tg_id "
        "AND name IN ('refund_requested','refund_completed') "
        "AND created_at>=:since LIMIT 1",
        {"tg_id": tg_id,
         "since": (_now() - timedelta(days=7)).isoformat()})
    if await cur.fetchone():
        flags.append(RISK_RECENT_REFUND)
    return flags


async def _timeline(db, tg_id: int) -> list[dict]:
    """Единый таймлайн: deliveries со статусом + ручные notes/messages."""
    items: list[dict] = []

    # deliveries со статусом (BUS-308)
    cur = await db.execute(
        "SELECT kind, key, status, error, created_at FROM deliveries "
        "WHERE tg_id=:tg_id AND kind != 'winback2_code' "
        "ORDER BY created_at DESC LIMIT 30",
        {"tg_id": tg_id})
    for r in await cur.fetchall():
        items.append({
            "kind": "auto",
            "type": "delivery",
            "key": f"{r['kind']}:{r['key']}",
            "at": r["created_at"],
            "status": r["status"],
            "error_class": r["error"],
        })

    # notes
    cur = await db.execute(
        "SELECT id, text, created_at FROM user_notes "
        "WHERE tg_id=:tg_id ORDER BY created_at DESC LIMIT 20",
        {"tg_id": tg_id})
    for r in await cur.fetchall():
        items.append({
            "kind": "manual",
            "type": "note",
            "key": f"note:{r['id']}",
            "at": r["created_at"],
            "text": r["text"][:200],
        })

    # admin_audit → messages (user.message)
    cur = await db.execute(
        "SELECT created_at, payload_json FROM admin_audit "
        "WHERE action='user.message' AND target=:tg_id "
        "ORDER BY created_at DESC LIMIT 20",
        {"tg_id": str(tg_id)})
    for r in await cur.fetchall():
        try:
            payload = json.loads(r["payload_json"] or "{}")
        except (TypeError, ValueError):
            payload = {}
        items.append({
            "kind": "manual",
            "type": "message",
            "key": "operator:message",
            "at": r["created_at"],
            "status": "sent" if payload.get("ok") else "failed",
        })

    items.sort(key=lambda x: x.get("at", ""), reverse=True)
    return items[:40]


async def _crystals_bought(db, tg_id: int) -> int:
    cur = await db.execute(
        "SELECT COALESCE(SUM(delta),0) AS total FROM crystal_ledger "
        "WHERE tg_id=:tg_id AND delta>0 AND reason='purchase'",
        {"tg_id": tg_id})
    return int((await cur.fetchone())["total"] or 0)


async def _crystals_granted(db, tg_id: int) -> int:
    cur = await db.execute(
        "SELECT COALESCE(SUM(delta),0) AS total FROM crystal_ledger "
        "WHERE tg_id=:tg_id AND delta>0 AND reason!='purchase'",
        {"tg_id": tg_id})
    return int((await cur.fetchone())["total"] or 0)


async def _next_plan(db, current_plan: str) -> str | None:
    """Следующий план по сортировке (для upsell в Q4).

    list_plans уже возвращает отсортированный по (sort, price_stars) список —
    ищем первый план строго «дороже» текущего по сорту. FREE_PLAN не имеет
    колонки sort, поэтому для 'free' берём 0 (всё платное — апгрейд)."""
    try:
        current_sort = await _plan_sort(db, current_plan)
        for p in await billing.list_plans(db):
            if p.get("sort", 100) > current_sort:
                return p.get("code")
    except Exception:  # noqa: BLE001
        pass
    return None


async def _plan_sort(db, plan_code: str) -> int:
    try:
        plan = await billing.get_plan(db, plan_code)
        return int(plan.get("sort", 0) or 0)
    except Exception:  # noqa: BLE001
        return 0


async def _sub_expired_days(db, tg_id: int) -> int | None:
    user = await users.get(db, tg_id)
    if not user or not user.get("sub_until"):
        return None
    try:
        until = datetime.fromisoformat(user["sub_until"])
        delta = (_now() - until).days
        return max(0, delta)
    except (TypeError, ValueError):
        return None


async def _segment_sleeping_days(db, tg_id: int) -> int | None:
    user = await users.get(db, tg_id)
    if not user or not user.get("last_seen"):
        return None
    try:
        last = datetime.fromisoformat(user["last_seen"])
        return max(0, (_now() - last).days)
    except (TypeError, ValueError):
        return None
