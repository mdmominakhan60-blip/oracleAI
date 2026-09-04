"""Рефералка: приглашения, бонусы, ссылки и статистика.

Два уровня. Первый — подруга по ссылке, второй — подруга подруги: он делает
раздачу ссылок выгодной не один раз, а на длинной дистанции. Второй уровень
выключается флагом `referral_two_levels`, если начнёт разгонять себестоимость.

Защита от накрутки: бонус за регистрацию небольшой, а основной приходит
с первой оплаты приглашённой (`services.billing`). Самого себя пригласить
нельзя, повторно засчитать приглашение — тоже (UNIQUE в `referrals`).
"""
from __future__ import annotations

import logging

from ..repo import analytics, billing, content, growth, users

log = logging.getLogger("oracle.referrals")

REF_PREFIX = "ref_"


def link_for(bot_username: str, tg_id: int) -> str:
    return f"https://t.me/{bot_username}?start={REF_PREFIX}{tg_id}"


def parse_ref(arg: str) -> int | None:
    """`ref_123456` → 123456. Всё остальное — не реферальная ссылка."""
    if not arg or not arg.startswith(REF_PREFIX):
        return None
    try:
        value = int(arg[len(REF_PREFIX):])
    except ValueError:
        return None
    return value if value > 0 else None


async def apply(db, invitee_id: int, referrer_id: int) -> dict | None:
    """Засчитывает приглашение и начисляет бонусы. None — приглашение не годится.

    Причины отказа: приглашение самой себя, приглашающей нет в базе, у клиентки
    уже есть пригласившая.
    """
    if invitee_id == referrer_id:
        return None
    invitee = await users.get(db, invitee_id)
    referrer = await users.get(db, referrer_id)
    if not invitee or not referrer:
        return None
    if await growth.referrer_of(db, invitee_id):
        return None
    # Цикл (аудит 2.2): A→B и B→A дают самосебе-реферала с level-2 бонусом.
    # Идём вверх по цепочке пригласивших; встретили приглашённую — отказ.
    walker = referrer_id
    while walker:
        walker = await growth.referrer_of(db, walker)
        if walker == invitee_id:
            return None

    bonus = int(await content.get_setting(db, "referral.bonus", 15) or 0)
    if not await growth.record_referral(db, referrer_id, invitee_id,
                                        level=1, bonus=bonus):
        return None

    await users.update(db, invitee_id, ref_by=referrer_id)
    if not invitee["source"]:
        await users.update(db, invitee_id, source="referral")
    if bonus:
        await billing.add_crystals(db, invitee_id, bonus, "ref_welcome",
                                   ref=str(referrer_id))
        await billing.add_crystals(db, referrer_id, bonus, "ref_invite",
                                   ref=str(invitee_id))

    result = {"referrer_id": referrer_id, "bonus": bonus, "level2": None}

    # второй уровень: тому, кто привёл пригласившую
    if await content.is_on(db, "referral_two_levels", default=True):
        grandparent = await growth.referrer_of(db, referrer_id)
        bonus2 = int(await content.get_setting(db, "referral.bonus_level2", 5) or 0)
        if grandparent and grandparent != invitee_id and bonus2:
            if await growth.record_referral(db, grandparent, invitee_id,
                                            level=2, bonus=bonus2):
                await billing.add_crystals(db, grandparent, bonus2, "ref_level2",
                                           ref=str(invitee_id))
                result["level2"] = {"tg_id": grandparent, "bonus": bonus2}

    await analytics.track(db, analytics.E_REFERRAL, invitee_id,
                          props={"referrer": referrer_id, "bonus": bonus})
    return result


async def stats(db, tg_id: int) -> dict:
    data = await growth.referral_stats(db, tg_id)
    data["bonus_per_invite"] = int(
        await content.get_setting(db, "referral.bonus", 15) or 0)
    data["revenue_share"] = int(
        await content.get_setting(db, "referral.revenue_share_crystals", 30) or 0)
    return data


def share_text(bonus: int, lang: str = "ru") -> str:
    """Return invite copy in the profile language without using gendered forms."""
    if lang == "en":
        return ("My personal AI Oracle knows my natal chart, reads Tarot and remembers "
                f"what I choose to share 🔮 Try it with my link — we both receive ✦{bonus} ✨")
    return ("Мой личный AI-Оракул: знает мою натальную карту, раскладывает Таро "
            f"и помнит всё, что я ему рассказываю 🔮 Попробуй — по моей ссылке "
            f"каждому по ✦{bonus} ✨")
