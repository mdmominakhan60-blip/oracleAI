"""Admin access and admin analytics policy for presentation layers.

Единственная точка, где presentation (bot / api) узнаёт роль и агрегаты
админки; SQL остаётся в app/repo/admin и app/repo/analytics.
"""
from __future__ import annotations



async def is_admin(db, tg_id: int) -> bool:
    """Роль администратора (owner/manager/...) или отсутствие таковой."""
    from ..repo import admin as admin_repo

    return bool(await admin_repo.resolve_role(db, tg_id))


async def role(db, tg_id: int) -> str | None:
    """Роль администратора или None (для ручных проверок доступа)."""
    from ..repo import admin as admin_repo

    return await admin_repo.resolve_role(db, tg_id)


async def set_brand_setting(db, key: str, value) -> None:
    """Идемпотентная запись настройки бренда (только если изменилась)."""
    from ..repo import content as content_repo

    current = await content_repo.get_setting(db, key, "")
    if current != value:
        await content_repo.set_setting(db, key, value)


async def drain_touch_tasks() -> None:
    """Дождаться отложенных last_seen-записей при остановке процесса."""
    from ..repo import users as users_repo

    await users_repo.drain_touch_tasks()


async def admin_overview(db) -> dict:
    """Сводные метрики для админских экранов (overview + воронка)."""
    from ..repo import analytics as analytics_repo

    return {
        "overview": await analytics_repo.overview(db),
        "funnel": await analytics_repo.funnel(db, 30),
    }
