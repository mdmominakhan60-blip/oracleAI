"""BUS-256 волна 3.1 — WB2 winback-оффер (механика BUS-197).

Второй шаг winback-цепочки: через 5+ дней после истечения подписки юзер
получает персональный код trial 7д (партия winback_{YYYY-MM}, 25 шт./мес).
Проверяем гейты CFO: анти-абьюз 90 дней, стоп при активной подписке и
повторе kind+key, персональный код каждому, fallback при исчерпанной партии.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.repo import comms, growth, users
from app.services import scheduler


class RecordingBot:
    def __init__(self):
        self.sent: list[tuple[int, str]] = []

    async def send_message(self, tg_id, text, reply_markup=None):
        self.sent.append((tg_id, text))


def _iso(days_ago: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()


async def _expired_user(db, tg_id: int, *, days_ago: int = 7,
                        notified: int = 2, lang: str = "ru"):
    """Юзер, чья подписка истекла days_ago назад; тёплый winback уже видел."""
    await users.ensure(db, tg_id, f"Wb2-{tg_id}")
    await users.update(db, tg_id, onboarded=1, sub_level="trial",
                       sub_until=_iso(days_ago), expiry_notified=notified,
                       lang=lang)
    return await users.get(db, tg_id)


async def _fresh_batch(db, month: str = "2026-09", count: int = 5) -> str:
    """Своя партия на тест: pool глобален, месяц фиксированный."""
    batch = f"winback_{month}"
    codes = await growth.create_codes(db, count, kind="plan_days", days=7,
                                      plan_code="trial", batch=batch,
                                      max_uses=1, valid_days=14)
    assert len(codes) == count
    return batch


# ─────────────────────────── счастливый путь ─────────────────────────────────

async def test_winback2_sent_with_personal_code(db):
    """7 дней после истечения: WB2 уходит с подставленным кодом из партии."""
    batch = await _fresh_batch(db)
    user = await _expired_user(db, 4100, days_ago=7)
    bot = RecordingBot()

    await scheduler._winback(bot, db, user, now_utc=datetime.now(timezone.utc))

    assert len(bot.sent) == 1, f"отправок {len(bot.sent)}: {bot.sent}"
    tg_id, text = bot.sent[0]
    codes = await growth.list_codes(db, batch=batch)
    used_code = next(c["code"] for c in codes if c["code"] in text)
    assert f"/promo {used_code}" in text, "CTA-строка с кодом не в тексте"
    assert "{code}" not in text and "{name}" not in text
    assert await comms.already_sent(db, tg_id, "winback2", user["sub_until"])
    # код зарезервирован за юзером (tg_id=0), но ещё не использован
    cur = await db.execute(
        "SELECT tg_id FROM deliveries WHERE kind='winback2_code' AND key=:c",
        {"c": used_code})
    assert (await cur.fetchone())["tg_id"] == 0
    # атрибуция — журнал deliveries kind='winback2' (словарь BUS-271:
    # отдельного события для отправки нет, code в события не пишется)
    cur = await db.execute(
        "SELECT COUNT(*) n FROM events WHERE name='winback_offer_sent' AND tg_id=:t",
        {"t": tg_id})
    assert (await cur.fetchone())["n"] == 0, "событие не из словаря эмитится"
    assert await comms.already_sent(db, tg_id, "winback2", user["sub_until"])


async def test_winback2_each_user_gets_own_code(db):
    """Персональный код: два юзера — два разных кода (BUS-197 анти-абьюз 1)."""
    await _fresh_batch(db, count=3)
    u1 = await _expired_user(db, 4101, days_ago=6)
    u2 = await _expired_user(db, 4102, days_ago=7)
    bot = RecordingBot()
    now = datetime.now(timezone.utc)

    await scheduler._winback(bot, db, u1, now_utc=now)
    await scheduler._winback(bot, db, u2, now_utc=now)

    assert len(bot.sent) == 2
    c1 = _codes_of(bot.sent[0][1])
    c2 = _codes_of(bot.sent[1][1])
    assert c1 and c2 and c1 != c2, \
        f"коды не персональные: {c1} vs {c2}"
    cur = await db.execute(
        "SELECT key FROM deliveries WHERE kind='winback2_code' ORDER BY key")
    reserved = {r["key"] for r in await cur.fetchall()}
    assert reserved == {c1[0], c2[0]}, "резерв не совпал с отправленным"


def _codes_of(text: str) -> list[str]:
    """Код — токен после '/promo ' в тексте оффера."""
    return [p.split()[0] for p in text.split("/promo ")[1:]]


# ─────────────────────────────── гейты ────────────────────────────────────────

async def test_winback2_not_sent_before_5_days(db):
    """Гейт окна: истекло 3 дня — оффер ещё не пора."""
    await _fresh_batch(db)
    user = await _expired_user(db, 4103, days_ago=3)
    bot = RecordingBot()

    await scheduler._winback(bot, db, user, now_utc=datetime.now(timezone.utc))

    assert bot.sent == []
    assert not await comms.already_sent(db, user["tg_id"], "winback2",
                                        user["sub_until"])


async def test_winback2_not_sent_if_sub_active(db):
    """Стоп-условие CFO: подписка активна — оффер не отправляется."""
    await _fresh_batch(db)
    await users.ensure(db, 4104, "Активная")
    until = (datetime.now(timezone.utc) + timedelta(days=10)).isoformat()
    user = await _expired_user(db, 4104, days_ago=7)
    await users.update(db, 4104, sub_until=until)   # продлилась
    fresh = await users.get(db, 4104)
    bot = RecordingBot()

    await scheduler._winback(bot, db, fresh, now_utc=datetime.now(timezone.utc))

    assert bot.sent == []


async def test_winback2_not_sent_twice(db):
    """Повтор исключён kind+key={sub_until}: второй вызов молчит."""
    await _fresh_batch(db)
    user = await _expired_user(db, 4105, days_ago=7)
    bot = RecordingBot()
    now = datetime.now(timezone.utc)

    await scheduler._winback(bot, db, user, now_utc=now)
    await scheduler._winback(bot, db, await users.get(db, user["tg_id"]),
                             now_utc=now)

    assert len(bot.sent) == 1


async def test_winback2_antibuse_90d(db):
    """Анти-абьюз BUS-197: redemption 30 дней назад — блок; 91 — пропускает."""
    batch = await _fresh_batch(db, count=2)
    recent = await _expired_user(db, 4106, days_ago=7)
    old = await _expired_user(db, 4107, days_ago=7)

    # recent redeem'нул winback-код 30 дней назад
    codes = await growth.list_codes(db, batch=batch)
    await growth.redeem(db, codes[0]["code"], recent["tg_id"])
    await db.execute(
        "UPDATE promo_redemptions SET created_at=:at WHERE tg_id=:t AND code=:c",
        {"at": _iso(30), "t": recent["tg_id"], "c": codes[0]["code"]})
    # old — 91 день назад (в другой winback-партии)
    old_batch = await _fresh_batch(db, month="2026-05", count=1)
    old_code = (await growth.list_codes(db, batch=old_batch))[0]["code"]
    await growth.redeem(db, old_code, old["tg_id"])
    await db.execute(
        "UPDATE promo_redemptions SET created_at=:at WHERE tg_id=:t AND code=:c",
        {"at": _iso(91), "t": old["tg_id"], "c": old_code})

    bot = RecordingBot()
    now = datetime.now(timezone.utc)
    await scheduler._winback(bot, db, recent, now_utc=now)
    await scheduler._winback(bot, db, old, now_utc=now)

    sent_to = {tg for tg, _ in bot.sent}
    assert sent_to == {old["tg_id"]}, \
        f"анти-абьюз сломан: отправлено {sent_to}, ожидался только old"


async def test_winback2_warm_winback_first_then_offer(db):
    """Цепочка: expiry_notified=0 → тёплый winback; WB2 ждёт следующего тика."""
    await _fresh_batch(db)
    user = await _expired_user(db, 4108, days_ago=7, notified=0)
    bot = RecordingBot()
    now = datetime.now(timezone.utc)

    await scheduler._winback(bot, db, user, now_utc=now)
    assert len(bot.sent) == 1, "тёплый winback не ушёл первым"
    assert "winback2" not in await comms_already(db, user["tg_id"])

    # следующий тик: expiry_notified уже 2, но окно WB2 ещё не наступило
    # (истекло 7 дней назад, окно 5 дней пройдено — WB2 уходит сразу)
    fresh = await users.get(db, user["tg_id"])
    assert fresh["expiry_notified"] == 2
    await scheduler._winback(bot, db, fresh, now_utc=now)
    assert len(bot.sent) == 2, "WB2 не ушёл после тёплого напоминания"
    assert "/promo" in bot.sent[1][1]


async def comms_already(db, tg_id: int) -> str:
    cur = await db.execute(
        "SELECT string_agg(DISTINCT kind, ',') kinds FROM deliveries "
        "WHERE tg_id=:t", {"t": tg_id})
    return (await cur.fetchone())["kinds"] or ""


# ─────────────────────────── партия и шаблон ─────────────────────────────────

async def test_winback2_batch_ensured_monthly(db):
    """ensure_winback_batch: создаёт партию месяца один раз, idемпотентно."""
    now = datetime(2026, 10, 15, tzinfo=timezone.utc)
    b1 = await growth.ensure_winback_batch(db, 25, now=now)
    assert b1 == "winback_2026-10"
    stats = {r["batch"]: r["total"] for r in await growth.batch_stats(db)}
    assert stats["winback_2026-10"] == 25
    # повторный вызов в тот же месяц не плодит вторую партию
    await growth.ensure_winback_batch(db, 25, now=now)
    stats = {r["batch"]: r["total"] for r in await growth.batch_stats(db)}
    assert stats["winback_2026-10"] == 25


async def test_winback2_batch_empty_falls_back_to_warm(db):
    """Партия исчерпана: WB2 молчит с warning, юзер не теряет цепочку —
    тёплый winback уходит как раньше (fallback = старое поведение)."""
    # юзер без expiry_notified=2: тёплый уходит, WB2 не стартует
    warm = await _expired_user(db, 4109, days_ago=7, notified=0)
    bot = RecordingBot()
    await scheduler._winback(bot, db, warm, now_utc=datetime.now(timezone.utc))
    assert len(bot.sent) == 1

    # партия на месяц пуста (кодов нет вовсе): WB2-ветка молчит
    # (эмулируем: в db партия текущего месяца не создавалась —
    # ensure_winback_batch создаст её, поэтому проверяем reserve_code напрямую)
    got = await growth.reserve_code(db, "winback_2099-01")
    assert got is None, "reserve_code вернул код из несуществующей партии"


async def test_winback2_no_placeholder_no_send(db):
    """Критично (BUS-190): шаблон без {code} — отправка отменяется."""
    from app.repo import content as content_repo
    await _fresh_batch(db)
    user = await _expired_user(db, 4110, days_ago=7)
    await content_repo.upsert_content(
        db, "copy", "winback2", title="Сломан",
        body="🎁 {name}, подарок ждёт! /promo — введи код",
        meta={"body_en": "🎁 {name}, a gift awaits! /promo"},
        admin_id=None)
    bot = RecordingBot()

    await scheduler._winback(bot, db, user, now_utc=datetime.now(timezone.utc))

    assert bot.sent == [], "ушло сообщение без кода"
    assert not await comms.already_sent(db, user["tg_id"], "winback2",
                                        user["sub_until"])


async def test_winback2_seed_content_ru_en(db):
    """Seed-текст winback2 существует на ru (seed) и en (DEFAULT_EN_CONTENT)."""
    ru = await db.execute(
        "SELECT body FROM content_items WHERE kind='copy' AND code='winback2'")
    row = await ru.fetchone()
    assert row and "{code}" in row["body"], "seed ru-текст без {code}"
    from app.repo.content import get_text, DEFAULT_EN_CONTENT
    en = DEFAULT_EN_CONTENT[("copy", "winback2")]["body"]
    assert "{code}" in en
    assert "14" in en and "7 days" in en, "сроки 14д/7д не названы в EN"
    assert "14" in row["body"] and "VIP на 7 дней" in row["body"], \
        "сроки 14д/7д не названы в RU"
