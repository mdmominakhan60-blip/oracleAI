"""BUS-1511/1527: _expiring_audience отбирает платных юзеров без onboarded.

До правки условие было `onboarded=1 AND ...`, поэтому оплативший подписку, но не
прошедший онбординг юзер (onboarded=0) навсегда выпадал из когорты уведомлений
об истечении — coverage-дефект, не аут планировщика. Платный tier хватает для
отбора сам по себе.

Также проверяем, что SQL-фрагмент `sub_level IN (...)` резолвится в БД (до
правки он содержал `:paid_levels`, который не передавался в params и asyncpg
не поддерживает `IN :param` — запрос падал бы на проде).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.repo import users
from app.services import scheduler


async def _paid_user(db, tg_id: int, sub_level: str, sub_until: str, *,
                     onboarded: int = 0) -> int:
    await users.ensure(db, tg_id, f"Пользователь {tg_id}")
    await users.update(db, tg_id, onboarded=onboarded, status="active",
                       sub_level=sub_level, sub_until=sub_until)
    return tg_id


async def test_paid_unonboarded_user_is_selected(db):
    """Платный юзер без onboarded попадает в expiring-аудиторию."""
    now = datetime.now(timezone.utc)
    soon = (now + timedelta(days=1)).isoformat()
    tg = await _paid_user(db, 777_000_001, "pro", soon)

    audience = await scheduler._expiring_audience(db, now)

    assert any(u["tg_id"] == tg for u in audience), (
        "оплативший подписку юзер без onboarded должен быть в когорте уведомлений"
    )


async def test_free_trial_user_is_not_selected(db):
    """Бесплатный/триальный юзер без onboarded не попадает — платный tier нужен."""
    now = datetime.now(timezone.utc)
    soon = (now + timedelta(days=1)).isoformat()
    await _paid_user(db, 777_000_002, "trial", soon)
    await _paid_user(db, 777_000_003, "free", soon)

    audience = await scheduler._expiring_audience(db, now)

    assert not any(u["tg_id"] in (777_000_002, 777_000_003) for u in audience), (
        "бесплатный/триальный tier не даёт права на уведомление об истечении"
    )


async def test_onboarded_free_user_still_selected(db):
    """Regression: onboarded=1 по-прежнему даёт право на уведомление.

    BUS-1511/1527 расширяет отбор ( добавляет платные tier), не заменяет его:
    `onboarded=1 OR sub_level IN (...)` — onboarded=1 остаётся достаточным
    условием, и free-юзер, прошедший онбординг, не должен выпасть.
    """
    now = datetime.now(timezone.utc)
    soon = (now + timedelta(days=1)).isoformat()
    tg = await _paid_user(db, 777_000_004, "free", soon, onboarded=1)

    audience = await scheduler._expiring_audience(db, now)

    assert any(u["tg_id"] == tg for u in audience), (
        "onboarded=1 + free tier — исходное поведение, юзер должен остаться в когорте"
    )


async def test_legacy_paid_aliases_are_selected(db):
    """Legacy-коды (vip/vip_year/guide) резвлятся в платные — отбираются."""
    now = datetime.now(timezone.utc)
    soon = (now + timedelta(days=1)).isoformat()
    tg_vip = await _paid_user(db, 777_000_005, "vip", soon)
    tg_vip_year = await _paid_user(db, 777_000_006, "vip_year", soon)
    tg_guide = await _paid_user(db, 777_000_007, "guide", soon)

    audience = await scheduler._expiring_audience(db, now)
    ids = {u["tg_id"] for u in audience}

    assert {tg_vip, tg_vip_year, tg_guide} <= ids, (
        "legacy-пейды vip/vip_year/guide должны отбираться как платные"
    )


async def test_inactive_user_is_not_selected(db):
    """status='active' остаётся необходимым условием."""
    now = datetime.now(timezone.utc)
    soon = (now + timedelta(days=1)).isoformat()
    await _paid_user(db, 777_000_008, "pro", soon)
    await users.update(db, 777_000_008, status="frozen")

    audience = await scheduler._expiring_audience(db, now)

    assert not any(u["tg_id"] == 777_000_008 for u in audience)