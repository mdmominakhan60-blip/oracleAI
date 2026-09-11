"""G-10 (BUS-809): транзакционная синхронизация users.sub_level ↔ subscription_state.tier_code.

Источник истины по правам — subscription_state.tier_code (канон волны A, BUS-735 r2;
решение BUS-411 «канон = users.sub_level» относилось к отчётам волны 2 и superseded
для волны A). users.sub_level остаётся legacy-полем для старых путей чтения
(runtime.py:64, ltv_tier.py:768) и поддерживается в актуальном состоянии в той же
транзакции, где меняется state.
"""
from __future__ import annotations

from ..data.session import transaction


async def sync_sub_level(db, tg_id: int) -> str | None:
    """Выравнивает users.sub_level по subscription_state.tier_code.

    Вызывать ВНУТРИ транзакции, изменившей subscription_state (вложенный
    transaction() той же задачи не открывает второй коммит). Возвращает
    записанный tier_code; None, если строки state нет — отсутствие state
    означает «legacy-клиентка, канон по-прежнему users.sub_level», трогать
    users в этом случае нельзя (можно погасить легальную платную подписку).
    """
    cur = await db.execute(
        "SELECT tier_code FROM subscription_state WHERE tg_id=:tg_id",
        {"tg_id": tg_id})
    row = await cur.fetchone()
    if row is None:
        return None
    tier_code = row["tier_code"]
    await db.execute(
        "UPDATE users SET sub_level=:tier WHERE tg_id=:tg_id",
        {"tier": tier_code, "tg_id": tg_id})
    return tier_code


async def find_divergences(db, *, limit: int = 500) -> list[dict]:
    """Клиентки с расхождением users.sub_level vs subscription_state.tier_code.

    Только те, у кого строка state существует (см. sync_sub_level про legacy).
    """
    cur = await db.execute(
        "SELECT u.tg_id, u.sub_level AS user_level, s.tier_code AS state_tier "
        "FROM users u JOIN subscription_state s ON s.tg_id = u.tg_id "
        "WHERE u.sub_level IS DISTINCT FROM s.tier_code "
        "ORDER BY u.tg_id LIMIT :limit",
        {"limit": max(1, int(limit))})
    return [dict(r) for r in await cur.fetchall()]


async def reconcile(db, *, dry_run: bool = True, limit: int = 500) -> dict:
    """Один pass сверки users.sub_level с subscription_state.tier_code.

    dry_run=True — только отчёт; dry_run=False — выравнивает users.sub_level
    по канону (tier_code) одной транзакцией. Итог второй прогонки — 0 расхождений.
    """
    divergences = await find_divergences(db, limit=limit)
    report: dict = {"divergent": len(divergences), "dry_run": dry_run,
                    "sample": divergences[:20]}
    if dry_run or not divergences:
        report["fixed"] = 0
        return report
    async with transaction(db):
        cur = await db.execute(
            "UPDATE users u SET sub_level = s.tier_code "
            "FROM subscription_state s "
            "WHERE s.tg_id = u.tg_id AND u.sub_level IS DISTINCT FROM s.tier_code")
        report["fixed"] = cur.rowcount or 0
    return report
