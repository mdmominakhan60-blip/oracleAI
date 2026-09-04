"""Пользователи: создание, профиль, тарифный уровень, сегменты для CRM."""
from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from ..config import settings
from ..data.session import transaction, utcnow

DEFAULT_TZ = "Europe/Moscow"

# Колонки, которые разрешено писать через update(): защита от опечатки в имени
# поля, которая иначе молча улетела бы в SQL и уронила запрос на живом трафике.
WRITABLE = {
    "name", "username", "lang", "gender", "persona", "oracle_name", "tz",
    "birth_date", "birth_time", "birth_time_known", "birth_time_precision", "birth_city",
    "birth_lat", "birth_lon", "chart_json", "natal_technique", "natal_technique_version", "onboarding_step",
    "sub_level", "sub_until", "crystals",
    "onboarded", "morning_push", "memory_enabled", "ref_by", "goal", "source", "status",
    "ltv_stars", "expiry_notified", "last_seen", "deleted_at",
}

# Возрастная проверка полностью удалена (GAUNTLET v2): дата рождения — просто
# астрономический исходник для расчёта карты, а не аттестация.


async def get(db, tg_id: int):
    cur = await db.execute("SELECT * FROM users WHERE tg_id=:tg_id", {"tg_id": tg_id})
    return await cur.fetchone()


async def by_username(db, username: str):
    cur = await db.execute(
        "SELECT * FROM users WHERE lower(username)=lower(:username)",
        {"username": username.lstrip("@")})
    return await cur.fetchone()


async def ensure(db, tg_id: int, name: str | None = None,
                 username: str | None = None, source: str | None = None,
                 lang: str | None = None):
    """Create a persistent Free user; automatic trial is opt-in via AUTO_TRIAL."""
    user = await get(db, tg_id)
    if user:
        if username and user["username"] != username:
            await update(db, tg_id, username=username)
            return await get(db, tg_id)
        return user

    trial_days = settings.trial_days
    auto_trial = bool(settings.auto_trial)
    crystals = settings.crystals_start if auto_trial else 0
    profile_lang = "en" if (lang or "").lower().startswith("en") else "ru"
    sub_level = "trial" if auto_trial else "free"
    sub_until = ((datetime.now(timezone.utc) + timedelta(days=trial_days)).isoformat()
                 if auto_trial else None)
    # Двойной /start в один момент: оба прошли SELECT выше и оба идут в INSERT.
    # ON CONFLICT (tg_id) DO NOTHING + rowcount снимает гонку — второй INSERT
    # не валит UNIQUE по tg_id и не пишет второй раз welcome в журнал.
    async with transaction(db):
        cur = await db.execute(
            "INSERT INTO users(tg_id, name, username, lang, sub_level, sub_until, "
            "crystals, source, created_at) VALUES(:tg_id, :name, :username, :lang, "
            ":sub_level, :sub_until, :crystals, :source, :created_at) "
            "ON CONFLICT (tg_id) DO NOTHING",
            {"tg_id": tg_id, "name": name, "username": username, "lang": profile_lang,
             "sub_level": sub_level, "sub_until": sub_until, "crystals": crystals,
             "source": source, "created_at": utcnow()})
        if cur.rowcount:
            await db.execute(
                "INSERT INTO crystal_ledger(tg_id, delta, reason, balance, created_at) "
                "VALUES(:tg_id, :delta, 'welcome', :balance, :created_at)",
                {"tg_id": tg_id, "delta": crystals, "balance": crystals, "created_at": utcnow()})
    return await get(db, tg_id)


async def update(db, tg_id: int, **fields) -> None:
    unknown = set(fields) - WRITABLE
    if unknown:
        raise ValueError(f"нельзя писать в колонки users: {', '.join(sorted(unknown))}")
    if not fields:
        return
    keys = ", ".join(f"{k}=:{k}" for k in fields)
    # INVARIANT: keys only from allowlist above — never interpolate user input
    async with transaction(db):
        await db.execute(f"UPDATE users SET {keys} WHERE tg_id=:tg_id",
                         {**fields, "tg_id": tg_id})


#: Когда последний раз писали last_seen клиентке. Точность в минутах достаточна
#: для ретеншена, а рестарт процесса теряет максимум несколько часов.
_last_seen_cache: dict[int, float] = {}
TOUCH_INTERVAL_S = 300     # раз в 5 минут на клиентку


async def touch(db, tg_id: int) -> None:
    """Отметка активности, не чаще раза в 5 минут и в фоне.

    Раньше каждое сообщение и каждый запрос Mini App писали last_seen
    синхронно — на 10k это десятки тысяч лишних UPDATE на горячем пути.
    """
    now = time.time()
    if _last_seen_cache.get(tg_id, 0.0) > now - TOUCH_INTERVAL_S:
        return
    _last_seen_cache[tg_id] = now
    _spawn_last_seen(db, tg_id)


#: Сильная ссылка на фоновые задачи last_seen: без неё сборщик циклов может
#: убить запись до её выполнения (review-фикс G37).
_touch_tasks: set[asyncio.Task] = set()


async def _write_last_seen(db, tg_id: int) -> None:
    try:
        async with transaction(db):
            await db.execute("UPDATE users SET last_seen=:last_seen WHERE tg_id=:tg_id",
                             {"last_seen": utcnow(), "tg_id": tg_id})
    except Exception:  # noqa: BLE001
        pass


def _spawn_last_seen(db, tg_id: int) -> None:
    task = asyncio.get_running_loop().create_task(_write_last_seen(db, tg_id))
    _touch_tasks.add(task)
    task.add_done_callback(_touch_tasks.discard)


async def drain_touch_tasks() -> None:
    """Wait for deferred activity writes before closing the database."""
    if _touch_tasks:
        await asyncio.gather(*_touch_tasks, return_exceptions=True)


# ─────────────────────────── подписка и тариф ────────────────────────────────

def sub_active(user) -> bool:
    """Живая ли подписка. Пустой/битый `sub_until` трактуем как «нет доступа»."""
    if not user or not user["sub_until"]:
        return False
    try:
        return datetime.fromisoformat(user["sub_until"]) > datetime.now(timezone.utc)
    except (TypeError, ValueError):
        return False


def sub_days_left(user) -> int:
    if not sub_active(user):
        return 0
    until = datetime.fromisoformat(user["sub_until"])
    return max(0, (until - datetime.now(timezone.utc)).days)


def user_tz(user) -> ZoneInfo:
    """Таймзона клиентки. Битое значение из БД не должно ломать расчёт дня."""
    try:
        return ZoneInfo(user["tz"] or DEFAULT_TZ)
    except Exception:  # noqa: BLE001
        return ZoneInfo(DEFAULT_TZ)


def user_today(user) -> str:
    return datetime.now(user_tz(user)).strftime("%Y-%m-%d")


def day_start_utc(user) -> str:
    """Начало сегодняшних суток клиентки в UTC — для оконных запросов."""
    local = datetime.now(user_tz(user)).replace(
        hour=0, minute=0, second=0, microsecond=0)
    return local.astimezone(timezone.utc).isoformat()


async def extend_subscription(db, tg_id: int, plan_code: str, days: int) -> str:
    """Продлевает подписку от максимума (сейчас, текущий конец) — оплата не сгорает.

    Все в одной транзакции: параллельные оплаты одной клиентки (Stars в боте +
    Paddle/*в web) накапливают дни, а не перезаписывают друг друга.
    """
    async with transaction(db):
        user = await get(db, tg_id)
        base = datetime.now(timezone.utc)
        if user and user["sub_until"]:
            try:
                base = max(base, datetime.fromisoformat(user["sub_until"]))
            except (TypeError, ValueError):
                pass
        until = (base + timedelta(days=days)).isoformat()
        await db.execute(
            "UPDATE users SET sub_until=:sub_until, sub_level=:sub_level, expiry_notified=0 WHERE tg_id=:tg_id",
            {"sub_until": until, "sub_level": plan_code, "tg_id": tg_id})
    return until


async def set_status(db, tg_id: int, status: str) -> None:
    await update(db, tg_id, status=status)


async def anonymize(db, tg_id: int) -> None:
    """Delete personal content and pseudonymize records retained for accounting.

    The user row and minimal financial rows remain for reconciliation, but all
    owner-linked content, safety excerpts, analytics identity and operational
    targeting are removed. Since legacy databases have no anonymization marker,
    the operation is intentionally idempotent and safe to repeat.
    """
    async with transaction(db):
        await db.execute(
            "UPDATE users SET name='удалено', username=NULL, birth_date=NULL, "
            "birth_time=NULL, birth_city=NULL, birth_lat=NULL, birth_lon=NULL, "
            "chart_json=NULL, natal_technique='astrology', natal_technique_version='v1', "
            "onboarding_step=NULL, birth_time_precision='unknown', goal=NULL, memory_enabled=0, "
            "status='deleted', deleted_at=:deleted_at, onboarded=0, morning_push=0 "
            "WHERE tg_id=:tg_id",
            {"deleted_at": utcnow(), "tg_id": tg_id})

        # Personal content and targeting records have no retention reason after
        # deletion. Keep the table names static so dynamic SQL cannot be injected.
        for table in (
            "messages", "memories", "profile_summaries", "shared_context_events",
            "shared_context_snapshots", "diary", "forecasts", "tarot_readings",
            "palm_readings", "partners", "synastry_cache",
            "reports", "threads", "deliveries", "practices", "user_notes",
            "user_tags", "broadcast_targets", "promo_redemptions",
        ):
            await db.execute(
                # INVARIANT: keys only from allowlist above — never interpolate user input
                f"DELETE FROM {table} WHERE tg_id=:tg_id", {"tg_id": tg_id})

        await db.execute(
            "DELETE FROM referrals WHERE referrer_id=:referrer_id OR invitee_id=:invitee_id",
            {"referrer_id": tg_id, "invitee_id": tg_id},
        )

        # Analytics and safety rows contain a direct identity or sensitive
        # excerpt, so they are deleted rather than retained under a stable ID.
        await db.execute("DELETE FROM events WHERE tg_id=:tg_id", {"tg_id": tg_id})
        await db.execute("DELETE FROM safety_events WHERE tg_id=:tg_id", {"tg_id": tg_id})
        await db.execute("UPDATE llm_usage SET tg_id=NULL WHERE tg_id=:tg_id", {"tg_id": tg_id})

        # Orders/payments/ledger are retained only as an anonymized accounting
        # trace. Zero is a reserved non-user subject for aggregate reconciliation.
        for table in ("orders", "payments", "entitlements", "crystal_ledger"):
            await db.execute(
                # INVARIANT: keys only from allowlist above — never interpolate user input
                f"UPDATE {table} SET tg_id=0 WHERE tg_id=:tg_id", {"tg_id": tg_id})

        # Retained audit rows are scrubbed by direct marker. Webhook bodies are
        # never needed for settlement or idempotency, so clear every legacy raw
        # payload rather than relying on a provider-specific tg_id field.
        marker = str(tg_id)
        await db.execute(
            "UPDATE admin_audit SET target='deleted-user', payload_json=NULL "
            "WHERE target=:target OR payload_json LIKE :pat1 OR payload_json LIKE :pat2",
            {"target": marker,
             "pat1": f'%"tg_id":{marker}%',
             "pat2": f'%"tg_id": {marker}%'},
        )
        await db.execute("UPDATE webhook_events SET payload=NULL WHERE payload IS NOT NULL")


# ─────────────────────────── выборки и сегменты ──────────────────────────────

SEGMENTS = {
    "all": "1=1",
    "active_sub": "sub_until > :now",
    "expired": "(sub_until IS NULL OR sub_until <= :now)",
    "onboarded": "onboarded = 1",
    "not_onboarded": "onboarded = 0",
    "paying": "ltv_stars > 0",
    "never_paid": "ltv_stars = 0",
    "push_on": "morning_push = 1",
    "active_7d": "last_seen >= :week_ago",
    "sleeping_14d": "(last_seen IS NULL OR last_seen < :two_weeks_ago)",
    "expiring_3d": "sub_until > :now AND sub_until <= :in_3d",
}


def _segment_params() -> dict:
    now = datetime.now(timezone.utc)
    return {
        "now": now.isoformat(),
        "week_ago": (now - timedelta(days=7)).isoformat(),
        "two_weeks_ago": (now - timedelta(days=14)).isoformat(),
        "in_3d": (now + timedelta(days=3)).isoformat(),
    }


def _segment_sql(segment: str) -> tuple[str, dict]:
    """Разворачивает имя сегмента в SQL-условие с именованными параметрами."""
    where = SEGMENTS.get(segment or "all", SEGMENTS["all"])
    values = _segment_params()
    # Отбираем только те параметры, которые реально используются в WHERE-условии
    params = {name: value for name, value in values.items() if f":{name}" in where}
    return where, params


async def segment_ids(db, segment: str, *, exclude_deleted: bool = True) -> list[int]:
    where, params = _segment_sql(segment)
    extra = " AND status <> 'deleted'" if exclude_deleted else ""
    cur = await db.execute(
        f"SELECT tg_id FROM users WHERE ({where}){extra}", params)
    return [r["tg_id"] for r in await cur.fetchall()]


async def segment_count(db, segment: str) -> int:
    where, params = _segment_sql(segment)
    cur = await db.execute(
        f"SELECT COUNT(*) c FROM users WHERE ({where}) AND status <> 'deleted'", params)
    return (await cur.fetchone())["c"]


def _like_pattern(query: str) -> str:
    """Экранирует спецсимволы LIKE (аудит DB-015): иначе «_» в запросе CRM
    матчил любой символ, а «%» — любую подстроку."""
    import re as _re
    escaped = _re.sub(r"([%_\\])", lambda m: "\\" + m.group(1),
                      query.lstrip("@"))
    return f"%{escaped}%"


async def search(db, query: str = "", segment: str = "all", *,
                 limit: int = 50, offset: int = 0,
                 order: str = "created_at") -> list[dict]:
    """Список пользователей для CRM: поиск по имени/username/id + сегмент."""
    where, params = _segment_sql(segment)
    sql = [f"SELECT * FROM users WHERE ({where})"]
    query = (query or "").strip()
    if query:
        sql.append("AND (name LIKE :like_q ESCAPE '\\' OR username LIKE :like_q ESCAPE '\\' "
                   "OR CAST(tg_id AS TEXT) LIKE :like_q ESCAPE '\\')")
        params["like_q"] = _like_pattern(query)
    orders = {"created_at": "created_at DESC", "last_seen": "last_seen DESC",
              # DB-003: COLLATE NOCASE — SQLite-изм, на PostgreSQL это runtime
              # error; LOWER() даёт тот же case-insensitive порядок переносимо.
              "ltv": "ltv_stars DESC", "name": "LOWER(name)"}
    sql.append(f"ORDER BY {orders.get(order, orders['created_at'])}")
    sql.append("LIMIT :limit OFFSET :offset")
    params["limit"] = limit
    params["offset"] = offset
    cur = await db.execute(" ".join(sql), params)
    return [dict(r) for r in await cur.fetchall()]


async def count(db, query: str = "", segment: str = "all") -> int:
    where, params = _segment_sql(segment)
    sql = [f"SELECT COUNT(*) c FROM users WHERE ({where})"]
    query = (query or "").strip()
    if query:
        sql.append("AND (name LIKE :like_q ESCAPE '\\' OR username LIKE :like_q ESCAPE '\\' "
                   "OR CAST(tg_id AS TEXT) LIKE :like_q ESCAPE '\\')")
        params["like_q"] = _like_pattern(query)
    cur = await db.execute(" ".join(sql), params)
    return (await cur.fetchone())["c"]


async def push_targets(db) -> list:
    """Кому вообще может прийти запланированное сообщение (для планировщика)."""
    cur = await db.execute(
        "SELECT * FROM users WHERE onboarded=1 AND status='active'")
    return await cur.fetchall()


def chart_of(user) -> dict:
    try:
        return json.loads(user["chart_json"] or "{}")
    except (TypeError, ValueError):
        return {}
