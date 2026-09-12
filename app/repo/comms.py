"""Исходящие коммуникации: журнал доставок и рассылки.

`deliveries` — защита от повторной отправки. Статусы: sent / failed / forbidden.
Отметка ставится ДО отправки (claim → sending). После доставки — sent.
Временный сбой → failed (можно пере-занять на следующем тике).
Forbidden/удаление канала → forbidden (навсегда, без повторов).
"""
from __future__ import annotations

import json
import secrets
from datetime import datetime, timedelta, timezone

from ..data.session import transaction, utcnow
from . import content as content_repo

# 16 hex chars → 2^64 space, коллизия пренебрежима.
_CLAIM_TOKEN_BYTES = 8


def _claim_token() -> str:
    return secrets.token_hex(_CLAIM_TOKEN_BYTES)


# ─────────────────────────── журнал доставок ─────────────────────────────────


async def already_sent(db, tg_id: int, kind: str, key: str) -> bool:
    """True — доставка в терминальном состоянии (sent или forbidden).

    Поддерживает обе схемы deliveries: со status (BUS-308) и без (старые миграции).
    """
    try:
        cur = await db.execute(
            "SELECT 1 FROM deliveries "
            "WHERE tg_id=:tg_id AND kind=:kind AND key=:key "
            "AND status IN ('sent','forbidden')",
            {"tg_id": tg_id, "kind": kind, "key": key})
        return await cur.fetchone() is not None
    except Exception:  # noqa: BLE001
        # Схема без колонки status (миграции до 0012) — любая запись = отправлено.
        cur = await db.execute(
            "SELECT 1 FROM deliveries "
            "WHERE tg_id=:tg_id AND kind=:kind AND key=:key",
            {"tg_id": tg_id, "kind": kind, "key": key})
        return await cur.fetchone() is not None


async def mark_sent(db, tg_id: int, kind: str, key: str,
                    status: str = 'sent', error: str | None = None) -> bool:
    """Ставит/обновляет отметку. False — не наш claim."""
    try:
        async with transaction(db):
            cur = await db.execute(
                "INSERT INTO deliveries(tg_id, kind, key, status, error, created_at) "
                "VALUES(:tg_id, :kind, :key, :status, :error, :now) "
                "ON CONFLICT (tg_id, kind, key) DO UPDATE SET "
                "  status=:status, error=:error, created_at=:now "
                "WHERE deliveries.status='sending'",
                {"tg_id": tg_id, "kind": kind, "key": key,
                 "status": status, "error": error, "now": utcnow()})
            return bool(cur.rowcount)
    except Exception:  # noqa: BLE001
        # Схема без status (миграции до 0012)
        async with transaction(db):
            cur = await db.execute(
                "INSERT INTO deliveries(tg_id, kind, key, created_at) "
                "VALUES(:tg_id, :kind, :key, :now) "
                "ON CONFLICT (tg_id, kind, key) DO UPDATE SET "
                "  created_at=:now",
                {"tg_id": tg_id, "kind": kind, "key": key, "now": utcnow()})
            return bool(cur.rowcount)


async def claim(db, tg_id: int, kind: str, key: str) -> bool:
    """Атомарно занимает право на отправку. True — отправляем, False — занято/уже ушло.

    Поддерживает обе схемы deliveries: со status (BUS-308) и без (старые миграции).
    """
    token = _claim_token()
    try:
        async with transaction(db):
            cur = await db.execute(
                "INSERT INTO deliveries(tg_id, kind, key, status, error, "
                "  created_at, claimed_at) "
                "VALUES(:tg_id, :kind, :key, 'sending', :token, :now, :now) "
                "ON CONFLICT (tg_id, kind, key) DO UPDATE SET "
                "  status='sending', error=:token, claimed_at=:now "
                "WHERE deliveries.status='failed'",
                {"tg_id": tg_id, "kind": kind, "key": key,
                 "token": token, "now": utcnow()})
            return bool(cur.rowcount)
    except Exception:  # noqa: BLE001
        # Схема без status (миграции до 0012) — простая идемпотентная вставка.
        async with transaction(db):
            cur = await db.execute(
                "INSERT INTO deliveries(tg_id, kind, key, created_at) "
                "VALUES(:tg_id, :kind, :key, :now) "
                "ON CONFLICT (tg_id, kind, key) DO NOTHING",
                {"tg_id": tg_id, "kind": kind, "key": key, "now": utcnow()})
            return bool(cur.rowcount)


async def reclaim_stale_sending(db) -> int:
    """Возвращает в очередь зависшие sending-строки (крэш между claim и mark).

    Аналог reclaim у broadcast_targets: строка в status='sending' старше
    CLAIM_TIMEOUT_S — процесс, занявший её, умер, не поставив mark.
    Помечаем failed (не удаляем: дедуп-история сохраняется), следующий
    claim() пере-занят её как обычный retry. Возвращает число строк.

    claim() с момента BUS-313 F1 пишет claimed_at; строки без claimed_at
    (занятые до миграции) считаем по created_at — консервативный фолбэк.
    """
    cutoff = (datetime.now(timezone.utc)
              - timedelta(seconds=CLAIM_TIMEOUT_S)).isoformat()
    try:
        async with transaction(db):
            cur = await db.execute(
                "UPDATE deliveries SET status='failed', "
                "  error='reclaimed', claimed_at=NULL "
                "WHERE status='sending' AND COALESCE(claimed_at, created_at) "
                "  < :cutoff",
                {"cutoff": cutoff})
            return cur.rowcount or 0
    except Exception:  # noqa: BLE001
        # Схема без claimed_at (миграции до 0014) — reclaim невозможен,
        # старое поведение: зависшие sending остаются до prune.
        return 0


async def mark_failed(db, tg_id: int, kind: str, key: str,
                      error: str | None = None) -> None:
    """Снимаем sending → failed. Временный сбой — попробуем позже."""
    async with transaction(db):
        await db.execute(
            "UPDATE deliveries SET status='failed', error=:error "
            "WHERE tg_id=:tg_id AND kind=:kind AND key=:key AND status='sending'",
            {"tg_id": tg_id, "kind": kind, "key": key, "error": error})


# ───────────────────── forbidden: порог 3 дня + авто-очистка ───────────────────

#: Заявка на отправку живёт дольше живой паузы, но не бесконечно: если процесс
#: упал между claim и mark, заявку возвращаем в очередь.
CLAIM_TIMEOUT_S = 600


#: Количество дней подряд с Forbidden до hard-дляbidden (BUS-369 mvp6_w2).
FORBIDDEN_THRESHOLD = 3
#: Окно, за которое считаем неудачи: 7 дней — случайные сбои не накапливаются.
FORBIDDEN_WINDOW_DAYS = 7
#: Chain-виды, которые НЕ удаляем при auto_clean (не доотправляем устаревшие
#: шаги цепочек — требование PM BUS-369 механика A).
FORBIDDEN_CHAIN_KINDS = frozenset({
    "welcome_chain", "onboard_nudge", "reactivate",
    "feedback_survey", "feedback_optout",
    "winback2", "winback2_code",
})


def _forbidden_key(tg_id: int) -> str:
    """settings key для счётчика forbidden-неудач юзера."""
    return f"push.forbidden_count:{tg_id}"


async def bump_forbidden(db, tg_id: int) -> None:
    """Добавляет сегодня в список дат forbidden-неудач. Окно — 7 дней."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    key = _forbidden_key(tg_id)
    try:
        cur = await db.execute(
            "SELECT value_json FROM settings WHERE key=:key",
            {"key": key})
        row = await cur.fetchone()
        if row:
            data = json.loads(row["value_json"])
            events: list[str] = data.get("events", [])
        else:
            events = []
        if today not in events:
            events.append(today)
        cutoff = (datetime.now(timezone.utc) - timedelta(days=FORBIDDEN_WINDOW_DAYS)).strftime("%Y-%m-%d")
        events = [d for d in events if d >= cutoff]
        await content_repo.set_setting(db, key, {"events": events})
    except Exception:  # noqa: BLE001
        pass  # settings не критичны для доставки


async def forbidden_threshold(db, tg_id: int) -> bool:
    """True — порог FORBIDDEN_THRESHOLD дней подряд сбоя достигнут."""
    days = await _forbidden_days(db, tg_id)
    return len(days) >= FORBIDDEN_THRESHOLD


async def _forbidden_days(db, tg_id: int) -> list[str]:
    """Дни подряд (последовательные) с Forbidden в окне 7 дней."""
    key = _forbidden_key(tg_id)
    try:
        cur = await db.execute(
            "SELECT value_json FROM settings WHERE key=:key",
            {"key": key})
        row = await cur.fetchone()
        if not row:
            return []
        events: list[str] = json.loads(row["value_json"]).get("events", [])
    except Exception:  # noqa: BLE001
        return []
    if not events:
        return []
    # Нам нужны последовательные дни — сортируем и ищем подряд.
    sorted_days = sorted(events)
    streak = [sorted_days[0]]
    for d in sorted_days[1:]:
        prev = datetime.fromisoformat(streak[-1])
        curr = datetime.fromisoformat(d)
        if (curr - prev).days == 1:
            streak.append(d)
        else:
            streak = [d]
    return streak


async def clean_forbidden(db, tg_id: int) -> int:
    """Удаляет forbidden-записи юзера (кроме chain-видов). Возвращает удалено строк.

    Вызывается при первом успешном контакте (/start, /api/me с auth):
    повторно активный пользователь снова получает пуш-доставку. Chain-виды
    не трогаем — их шаги отработаны, доотправлять не нужно (PM BUS-369).
    """
    async with transaction(db):
        # Список исключений — из FORBIDDEN_CHAIN_KINDS; значения только из
        # константы кода (не из пользовательского ввода), поэтому подстановка
        # через запятую безопасна.
        kinds_sql = ", ".join(f"'{k}'" for k in sorted(FORBIDDEN_CHAIN_KINDS))
        cur = await db.execute(
            "DELETE FROM deliveries "
            "WHERE tg_id=:tg_id AND status='forbidden' "
            f"AND kind NOT IN ({kinds_sql})",
            {"tg_id": tg_id})
        removed = cur.rowcount or 0
        # Сбрасываем счётчик forbidden: порог начинается с чистого листа.
        key = _forbidden_key(tg_id)
        await db.execute(
            "DELETE FROM settings WHERE key=:key",
            {"key": key})
        return removed


# unclaim() удалён: с failed-статусом дедуп-строка живёт, retry пере-занимает
# через claim() (он обновляет failed → sending атомарно).


async def sent_since(db, tg_id: int, kind: str, since: str) -> bool:
    """True — есть запись deliveries для kind с created_at >= since.

    Поддерживает обе схемы deliveries: со status (BUS-308) и без (старые миграции).
    """
    try:
        cur = await db.execute(
            "SELECT 1 FROM deliveries WHERE tg_id=:tg_id AND kind=:kind "
            "AND created_at >= :since LIMIT 1",
            {"tg_id": tg_id, "kind": kind, "since": since})
        return await cur.fetchone() is not None
    except Exception:  # noqa: BLE001
        cur = await db.execute(
            "SELECT 1 FROM deliveries WHERE tg_id=:tg_id AND kind=:kind "
            "AND created_at >= :since LIMIT 1",
            {"tg_id": tg_id, "kind": kind, "since": since})
        return await cur.fetchone() is not None


async def prune(db, days: int = 120) -> int:
    """Журнал нужен только пока актуален повод — старое удаляем."""
    before = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    async with transaction(db):
        cur = await db.execute(
            "DELETE FROM deliveries WHERE created_at < :before", {"before": before})
        return cur.rowcount or 0


# ─────────────────────────────── рассылки ─────────────────────────────────────


async def create_broadcast(db, title: str, body: str, *, segment: str = "all",
                           button_text: str | None = None,
                           button_url: str | None = None,
                           scheduled_at: str | None = None,
                           created_by: int | None = None) -> int:
    async with transaction(db):
        cur = await db.execute(
            "INSERT INTO broadcasts(title, body, button_text, button_url, segment_json, "
            "status, scheduled_at, created_by, created_at) "
            "VALUES(:title, :body, :button_text, :button_url, :segment_json, "
            ":status, :scheduled_at, :created_by, :created_at) RETURNING id",
            {"title": title, "body": body, "button_text": button_text,
             "button_url": button_url,
             "segment_json": json.dumps({"segment": segment}, ensure_ascii=False),
             "status": "scheduled" if scheduled_at else "draft",
             "scheduled_at": scheduled_at, "created_by": created_by,
             "created_at": utcnow()})
        row = await cur.fetchone()
        return row["id"]


async def get_broadcast(db, broadcast_id: int):
    cur = await db.execute(
        "SELECT * FROM broadcasts WHERE id=:id", {"id": broadcast_id})
    return await cur.fetchone()


async def list_broadcasts(db, limit: int = 50) -> list[dict]:
    cur = await db.execute(
        "SELECT * FROM broadcasts ORDER BY id DESC LIMIT :limit", {"limit": limit})
    return [dict(r) for r in await cur.fetchall()]


async def set_broadcast_status(db, broadcast_id: int, status: str, **fields) -> None:
    allowed = {"total", "sent", "failed", "started_at", "finished_at", "scheduled_at"}
    fields = {k: v for k, v in fields.items() if k in allowed}
    keys = "".join(f", {k}=:{k}" for k in fields)
    async with transaction(db):
        await db.execute(
            f"UPDATE broadcasts SET status=:status{keys} WHERE id=:id",
            {"status": status, **fields, "id": broadcast_id})


async def enqueue_targets(db, broadcast_id: int, ids: list[int]) -> int:
    if not ids:
        return 0
    async with transaction(db):
        await db.executemany(
            "INSERT INTO broadcast_targets(broadcast_id, tg_id, status) "
            "VALUES(:broadcast_id, :tg_id, 'pending') "
            "ON CONFLICT (broadcast_id, tg_id) DO NOTHING",
            [{"broadcast_id": broadcast_id, "tg_id": uid} for uid in ids])
        await db.execute(
            "UPDATE broadcasts SET total=:total WHERE id=:id",
            {"total": len(ids), "id": broadcast_id})
    return len(ids)


async def next_targets(db, broadcast_id: int, limit: int = 100) -> list[int]:
    """Пачка целей к отправке. Брошенные заявки (крэш) возвращает в pending.

    Захват (claim) — не здесь, а по одной цели перед отправкой: пачка из
    `pending` может перекрыться у двух параллельных запусков, а вот `claim` с
    условием `status='pending'` атомарен и отдаёт цель ровно одному.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(seconds=CLAIM_TIMEOUT_S)
              ).isoformat()
    async with transaction(db):
        await db.execute(
            "UPDATE broadcast_targets SET status='pending', claimed_at=NULL, error=NULL "
            "WHERE broadcast_id=:broadcast_id AND status='claiming' AND claimed_at < :cutoff",
            {"broadcast_id": broadcast_id, "cutoff": cutoff})
        cur = await db.execute(
            "SELECT tg_id FROM broadcast_targets WHERE broadcast_id=:broadcast_id "
            "AND status='pending' LIMIT :limit",
            {"broadcast_id": broadcast_id, "limit": limit})
        return [r["tg_id"] for r in await cur.fetchall()]


async def claim_target(db, broadcast_id: int, tg_id: int) -> bool:
    """Атомарно занимает цель. False — её уже забрал другой процесс.

    Условие `status='pending'` в UPDATE и есть гарантия: из двух параллельных
    `run()` ровно один получит rowcount 1, второй — 0 и пропустит цель.
    """
    async with transaction(db):
        cur = await db.execute(
            "UPDATE broadcast_targets SET status='claiming', claimed_at=:now, error=NULL "
            "WHERE broadcast_id=:broadcast_id AND tg_id=:tg_id AND status='pending'",
            {"now": utcnow(), "broadcast_id": broadcast_id, "tg_id": tg_id})
        return bool(cur.rowcount)


async def release_target(db, broadcast_id: int, tg_id: int) -> None:
    """Возврат цели в очередь — временный сбой (флуд-контроль, сеть)."""
    async with transaction(db):
        await db.execute(
            "UPDATE broadcast_targets SET status='pending', claimed_at=NULL "
            "WHERE broadcast_id=:broadcast_id AND tg_id=:tg_id AND status='claiming'",
            {"broadcast_id": broadcast_id, "tg_id": tg_id})


async def mark_target(db, broadcast_id: int, tg_id: int, status: str,
                      error: str | None = None) -> None:
    async with transaction(db):
        # Условие status='claiming': после reclaim (>CLAIM_TIMEOUT_S) цель может
        # забрать другой run — первая (опоздавшая) отметка не должна засчитаться
        # или задвоить broadcasts.sent.
        cur = await db.execute(
            "UPDATE broadcast_targets SET status=:status, error=:error, sent_at=:now "
            "WHERE broadcast_id=:broadcast_id AND tg_id=:tg_id AND status='claiming'",
            {"status": status, "error": error, "now": utcnow(),
             "broadcast_id": broadcast_id, "tg_id": tg_id})
        if not cur.rowcount:
            return
        column = "sent" if status == "sent" else "failed"
        # INVARIANT: keys only from allowlist above — never interpolate user input
        await db.execute(
            f"UPDATE broadcasts SET {column} = COALESCE({column},0) + 1 WHERE id=:id",
            {"id": broadcast_id})


async def broadcast_progress(db, broadcast_id: int) -> dict:
    cur = await db.execute(
        "SELECT status, COUNT(*) n FROM broadcast_targets WHERE broadcast_id=:broadcast_id "
        "GROUP BY status", {"broadcast_id": broadcast_id})
    rows = {r["status"]: r["n"] for r in await cur.fetchall()}
    return {"pending": rows.get("pending", 0), "claiming": rows.get("claiming", 0),
            "sent": rows.get("sent", 0), "failed": rows.get("failed", 0),
            "skipped": rows.get("skipped", 0)}


async def due_broadcasts(db) -> list[dict]:
    """Рассылки, которым пора уйти (запланированные и незавершённые running)."""
    cur = await db.execute(
        "SELECT * FROM broadcasts WHERE (status='scheduled' AND scheduled_at<=:now) "
        "OR status='running' ORDER BY id", {"now": utcnow()})
    return [dict(r) for r in await cur.fetchall()]
