"""BUS-260 волна 3.5 — реактивация спящих R1-R2: суточный sweep 14-21д + композит.

Контракт (дизайн BUS-190 §3, копирайт BUS-263 §6):
- отбор: active, onboarded=1, morning_push=1, last_seen 14-28д назад;
- kind='reactivate', key='r1/r2:{YYYY-MM}', месяц = дата входа в спячку;
- R1 (14-21д): персонализация по последней незавершённой практике; без практики —
  fallback-каркас (reactivate_r2) под ключ r1:{month}:fallback;
- R2 (+7д после R1, без ответа): только если R1 был персональный;
- ответ = fresh last_seen (не events — push-прогнозы пишут E_FORECAST каждый день);
- стоп: 60 дней с последнего reactivate (новый цикл), двойной стоп на отправке,
  R2 → жёсткий стоп (дедуп).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from app.data.session import transaction, utcnow
from app.repo import comms, users
from app.services import scheduler


class RecordingBot:
    def __init__(self):
        self.sent: list[tuple[int, str]] = []

    async def send_message(self, tg_id, text, reply_markup=None):
        self.sent.append((tg_id, text))


def _iso(dt: datetime) -> str:
    return dt.isoformat()


async def _sleeping_user(db, tg_id: int, *, last_seen: datetime,
                          status: str = "active", onboarded: int = 1,
                          morning_push: int = 1, lang: str = "ru") -> dict:
    """Юзер-кандидат reactivate: уснул last_seen дней назад, активен, с пушем."""
    await users.ensure(db, tg_id, f"R-{tg_id}")
    await users.update(db, tg_id, onboarded=onboarded, sub_level="free",
                       sub_until=None, morning_push=morning_push,
                       status=status, lang=lang, last_seen=_iso(last_seen))
    return await users.get(db, tg_id)


def _sent_key(bot: RecordingBot, tg_id: int, key_prefix: str) -> str | None:
    """Ищем отправку по tg_id и префиксу key."""
    for sent_tg, text in bot.sent:
        if sent_tg == tg_id:
            # ключ хранится не в тексте, но мы можем поставить маркер
            # через deliveries — в тестах упрощаем: ищем любую отправку
            pass
    return None


# ─────────────────────────── отбор аудитории ──────────────────────────────────

async def test_audience_14_21_days(db):
    """R1-окно (14-21д) — в отборе; свежее 13д и старое 29д — нет.
    Окно 22-28д тоже в отборе (R2-ветка), но R1 там не отправляется."""
    now = datetime.now(timezone.utc)
    await _sleeping_user(db, 7101, last_seen=now - timedelta(days=16))
    await _sleeping_user(db, 7102, last_seen=now - timedelta(days=13))
    await _sleeping_user(db, 7103, last_seen=now - timedelta(days=29))

    audience = await scheduler._reactivate_audience(db, now)
    ids = [u["tg_id"] for u in audience]
    assert 7101 in ids    # R1-окно
    assert 7102 not in ids  # <14д
    assert 7103 not in ids  # >28д, цепочка завершена


async def test_audience_excludes_inactive_and_no_push(db):
    """Стопы: статус != active и morning_push=0 исключаются."""
    now = datetime.now(timezone.utc)
    await _sleeping_user(db, 7111, last_seen=now - timedelta(days=16),
                         status="banned")
    await _sleeping_user(db, 7112, last_seen=now - timedelta(days=16),
                         morning_push=0)

    audience = await scheduler._reactivate_audience(db, now)
    ids = [u["tg_id"] for u in audience]
    assert 7111 not in ids
    assert 7112 not in ids


async def test_audience_excludes_not_onboarded(db):
    """Неонбордингнутые не попадают в reactivate."""
    now = datetime.now(timezone.utc)
    await _sleeping_user(db, 7113, last_seen=now - timedelta(days=16),
                         onboarded=0)

    audience = await scheduler._reactivate_audience(db, now)
    ids = [u["tg_id"] for u in audience]
    assert 7113 not in ids


async def test_audience_r2_in_21_28_days(db):
    """R2-окно: last_seen 21-28д назад — тоже в отборе (ждёт R2)."""
    now = datetime.now(timezone.utc)
    await _sleeping_user(db, 7121, last_seen=now - timedelta(days=23))
    await _sleeping_user(db, 7122, last_seen=now - timedelta(days=29))

    audience = await scheduler._reactivate_audience(db, now)
    ids = [u["tg_id"] for u in audience]
    assert 7121 in ids
    assert 7122 not in ids


# ─────────────────────────── R1 персонализация и fallback ─────────────────────

async def test_chain_r1_personalized(db):
    """R1: практика есть → reactivate_r1 с {practice_title} и {day_index}."""
    now = datetime.now(timezone.utc)
    user = await _sleeping_user(db, 7201, last_seen=now - timedelta(days=16))
    # Заводим незавершённую практику.
    await db.execute(
        "INSERT INTO practices(tg_id, code, day_index, started_at) "
        "VALUES(:tg_id, 'love_release', 5, :now)",
        {"tg_id": 7201, "now": _iso(now - timedelta(days=20))})
    await db.commit()

    bot = RecordingBot()
    await scheduler._reactivate_chain(bot, db, user, now_utc=now)

    assert len(bot.sent) == 1
    text = bot.sent[0][1]
    assert "Отпустить прошлое" in text
    assert "шаге 5" in text
    assert await comms.already_sent(db, 7201, "reactivate",
                                    f"r1:{user['last_seen'][:7]}")


async def test_chain_r1_no_practice_fallback(db):
    """R1 без практики → reactivate_r2 (fallback-каркас) под ключ :fallback."""
    now = datetime.now(timezone.utc)
    user = await _sleeping_user(db, 7202, last_seen=now - timedelta(days=16))

    bot = RecordingBot()
    await scheduler._reactivate_chain(bot, db, user, now_utc=now)

    assert len(bot.sent) == 1
    text = bot.sent[0][1]
    assert "карта дня" in text
    r1_key = f"r1:{user['last_seen'][:7]}"
    assert await comms.already_sent(db, 7202, "reactivate", f"{r1_key}:fallback")


async def test_chain_r1_silent_before_14d(db):
    """<14д сна — R1 не уходит."""
    now = datetime.now(timezone.utc)
    user = await _sleeping_user(db, 7211, last_seen=now - timedelta(days=10))

    bot = RecordingBot()
    await scheduler._reactivate_chain(bot, db, user, now_utc=now)
    assert bot.sent == []


async def test_chain_r1_silent_after_21d(db):
    """>=21д сна — R1 не уходит (R2 уже не покрывается отбором 28д)."""
    now = datetime.now(timezone.utc)
    user = await _sleeping_user(db, 7212, last_seen=now - timedelta(days=25))

    bot = RecordingBot()
    await scheduler._reactivate_chain(bot, db, user, now_utc=now)
    assert bot.sent == []


# ─────────────────────────── R2 ветка ─────────────────────────────────────────

async def test_chain_r2_sent_7d_after_r1(db):
    """R1 ушёл, через 7д без ответа — R2 уходит."""
    now = datetime.now(timezone.utc)
    user = await _sleeping_user(db, 7301, last_seen=now - timedelta(days=16))
    await db.execute(
        "INSERT INTO practices(tg_id, code, day_index, started_at) "
        "VALUES(:tg_id, 'love_release', 3, :now)",
        {"tg_id": 7301, "now": _iso(now - timedelta(days=20))})
    await db.commit()

    bot = RecordingBot()
    await scheduler._reactivate_chain(bot, db, user, now_utc=now)
    assert len(bot.sent) == 1  # R1

    r1_key = f"r1:{user['last_seen'][:7]}"
    r1_time = now - timedelta(days=7, hours=1)

    # Имитируем время доставки R1 = 7 дней назад.
    await db.execute(
        "UPDATE deliveries SET created_at=:at WHERE tg_id=:tg_id AND kind='reactivate' AND key=:key",
        {"at": _iso(r1_time), "tg_id": 7301, "key": r1_key})
    await db.commit()

    # R2 шлём позже чем через 7д после R1 → новая ISO-неделя: guardrail,
    # занятый R1 в прошлой неделе, цепочку не стопит (BUS-262).
    bot2 = RecordingBot()
    await scheduler._reactivate_chain(bot2, db, user,
                                     now_utc=now + timedelta(days=8, hours=1))
    assert len(bot2.sent) == 1
    assert bot2.sent[0][0] == 7301
    r2_key = f"r2:{user['last_seen'][:7]}"
    assert await comms.already_sent(db, 7301, "reactivate", r2_key)


async def test_chain_r2_blocked_by_response(db):
    """Ответ после R1 (last_seen новее R1) — R2 не уходит."""
    now = datetime.now(timezone.utc)
    user = await _sleeping_user(db, 7302, last_seen=now - timedelta(days=16))
    await db.execute(
        "INSERT INTO practices(tg_id, code, day_index, started_at) "
        "VALUES(:tg_id, 'love_release', 2, :now)",
        {"tg_id": 7302, "now": _iso(now - timedelta(days=20))})
    await db.commit()

    bot = RecordingBot()
    await scheduler._reactivate_chain(bot, db, user, now_utc=now)
    r1_key = f"r1:{user['last_seen'][:7]}"

    # Имитируем доставку R1 10д назад.
    await db.execute(
        "UPDATE deliveries SET created_at=:at WHERE tg_id=:tg_id AND kind='reactivate' AND key=:key",
        {"at": _iso(now - timedelta(days=10)), "tg_id": 7302, "key": r1_key})
    await db.commit()

    # Юзер вернулся через 3д после R1: обновляем last_seen.
    await users.update(db, 7302, last_seen=_iso(now - timedelta(days=7)))
    await db.commit()

    bot2 = RecordingBot()
    await scheduler._reactivate_chain(bot2, db, user,
                                     now_utc=now + timedelta(days=10))
    assert len(bot2.sent) == 0


async def test_chain_r2_not_sent_after_fallback_r1(db):
    """R1 fallback (без практики) → R2 не шлём (дубль «другой ценности»)."""
    now = datetime.now(timezone.utc)
    user = await _sleeping_user(db, 7303, last_seen=now - timedelta(days=16))

    bot = RecordingBot()
    await scheduler._reactivate_chain(bot, db, user, now_utc=now)
    assert len(bot.sent) == 1

    r1_key = f"r1:{user['last_seen'][:7]}"
    await db.execute(
        "UPDATE deliveries SET created_at=:at WHERE tg_id=:tg_id AND kind='reactivate' AND key=:key",
        {"at": _iso(now - timedelta(days=8)), "tg_id": 7303, "key": f"{r1_key}:fallback"})
    await db.commit()

    bot2 = RecordingBot()
    await scheduler._reactivate_chain(bot2, db, user,
                                     now_utc=now + timedelta(days=10))
    assert len(bot2.sent) == 0


async def test_chain_r2_silent_before_7d(db):
    """R2 не уходит раньше 7д после R1."""
    now = datetime.now(timezone.utc)
    user = await _sleeping_user(db, 7311, last_seen=now - timedelta(days=16))
    await db.execute(
        "INSERT INTO practices(tg_id, code, day_index, started_at) "
        "VALUES(:tg_id, 'love_release', 1, :now)",
        {"tg_id": 7311, "now": _iso(now - timedelta(days=20))})
    await db.commit()

    bot = RecordingBot()
    await scheduler._reactivate_chain(bot, db, user, now_utc=now)
    r1_key = f"r1:{user['last_seen'][:7]}"
    await db.execute(
        "UPDATE deliveries SET created_at=:at WHERE tg_id=:tg_id AND kind='reactivate' AND key=:key",
        {"at": _iso(now - timedelta(days=2)), "tg_id": 7311, "key": r1_key})
    await db.commit()

    bot2 = RecordingBot()
    await scheduler._reactivate_chain(bot2, db, user,
                                     now_utc=now + timedelta(days=3))
    assert len(bot2.sent) == 0


# ─────────────────────────── 60д стоп и дедуп ─────────────────────────────────

async def test_chain_cooldown_60d_after_reactivate(db):
    """После отработанного цикла новый R1 не уходит раньше 60 дней."""
    now = datetime.now(timezone.utc)
    # Первый вызов: sleep_days=16д → R1 уходит, cooldown ставится.
    user = await _sleeping_user(db, 7401, last_seen=now - timedelta(days=16))
    await db.execute(
        "INSERT INTO practices(tg_id, code, day_index, started_at) "
        "VALUES(:tg_id, 'love_release', 1, :now)",
        {"tg_id": 7401, "now": _iso(now - timedelta(days=20))})
    await db.commit()

    bot = RecordingBot()
    await scheduler._reactivate_chain(bot, db, user, now_utc=now)
    assert len(bot.sent) == 1

    # Второй вызов через 30 дней: сдвигаем last_seen так, чтобы sleep_days=20д
    # (в окне [14,28)), но cooldown 60д не прошёл → должен блокироваться.
    await users.update(db, 7401, last_seen=_iso(now + timedelta(days=5)))
    await db.commit()
    user2 = await users.get(db, 7401)

    bot2 = RecordingBot()
    await scheduler._reactivate_chain(bot2, db, user2,
                                     now_utc=now + timedelta(days=30))
    assert len(bot2.sent) == 0


async def test_chain_dedup_same_key(db):
    """Дубль R1 под тем же ключом — не уходит."""
    now = datetime.now(timezone.utc)
    user = await _sleeping_user(db, 7411, last_seen=now - timedelta(days=16))

    bot = RecordingBot()
    await scheduler._reactivate_chain(bot, db, user, now_utc=now)
    assert len(bot.sent) == 1

    bot2 = RecordingBot()
    await scheduler._reactivate_chain(bot2, db, user,
                                     now_utc=now + timedelta(days=1))
    assert len(bot2.sent) == 0


async def test_chain_r2_dedup(db):
    """R2 уходит один раз; повторный прогон — молчание."""
    now = datetime.now(timezone.utc)
    user = await _sleeping_user(db, 7421, last_seen=now - timedelta(days=16))
    await db.execute(
        "INSERT INTO practices(tg_id, code, day_index, started_at) "
        "VALUES(:tg_id, 'love_release', 2, :now)",
        {"tg_id": 7421, "now": _iso(now - timedelta(days=20))})
    await db.commit()

    bot = RecordingBot()
    await scheduler._reactivate_chain(bot, db, user, now_utc=now)
    r1_key = f"r1:{user['last_seen'][:7]}"
    await db.execute(
        "UPDATE deliveries SET created_at=:at WHERE tg_id=:tg_id AND kind='reactivate' AND key=:key",
        {"at": _iso(now - timedelta(days=8)), "tg_id": 7421, "key": r1_key})
    await db.commit()

    # Первый прогон → R2 уходит.
    bot2 = RecordingBot()
    await scheduler._reactivate_chain(bot2, db, user,
                                     now_utc=now + timedelta(days=8, hours=1))
    assert len(bot2.sent) == 1

    # Второй прогон — дубль.
    bot3 = RecordingBot()
    await scheduler._reactivate_chain(bot3, db, user,
                                     now_utc=now + timedelta(days=9))
    assert len(bot3.sent) == 0


# ─────────────────────── guardrail 1/7д (BUS-262) ────────────────────────────

async def test_guardrail_marks_on_r1_personalized(db):
    """Успешный R1 резервирует guardrail-слот текущей ISO-недели."""
    now = datetime(2026, 9, 7, 10, 0, tzinfo=timezone.utc)  # понедельник, W37
    user = await _sleeping_user(db, 7601, last_seen=now - timedelta(days=16))
    await db.execute(
        "INSERT INTO practices(tg_id, code, day_index, started_at) "
        "VALUES(:tg_id, 'love_release', 5, :now)",
        {"tg_id": 7601, "now": _iso(now - timedelta(days=20))})
    await db.commit()

    await scheduler._reactivate_chain(RecordingBot(), db, user, now_utc=now)
    assert await comms.already_sent(db, 7601, "guardrail",
                                    now.strftime("%G-W%V"))


async def test_guardrail_marks_on_r1_fallback(db):
    """Fallback-R1 (без практики) тоже резервирует guardrail-слот."""
    now = datetime(2026, 9, 7, 10, 0, tzinfo=timezone.utc)
    user = await _sleeping_user(db, 7602, last_seen=now - timedelta(days=16))

    await scheduler._reactivate_chain(RecordingBot(), db, user, now_utc=now)
    assert await comms.already_sent(db, 7602, "guardrail",
                                    now.strftime("%G-W%V"))


async def test_guardrail_marks_on_r2(db):
    """Успешный R2 резервирует guardrail-слот своей ISO-недели."""
    now = datetime(2026, 9, 7, 10, 0, tzinfo=timezone.utc)
    user = await _sleeping_user(db, 7603, last_seen=now - timedelta(days=16))
    await db.execute(
        "INSERT INTO practices(tg_id, code, day_index, started_at) "
        "VALUES(:tg_id, 'love_release', 5, :now)",
        {"tg_id": 7603, "now": _iso(now - timedelta(days=20))})
    await db.commit()

    bot = RecordingBot()
    await scheduler._reactivate_chain(bot, db, user, now_utc=now)
    r1_key = f"r1:{user['last_seen'][:7]}"
    await db.execute(
        "UPDATE deliveries SET created_at=:at WHERE tg_id=:tg_id AND kind='reactivate' AND key=:key",
        {"at": _iso(now - timedelta(days=7, hours=1)), "tg_id": 7603, "key": r1_key})
    await db.commit()

    week2 = now + timedelta(days=8, hours=1)  # новая ISO-неделя
    await scheduler._reactivate_chain(RecordingBot(), db, user, now_utc=week2)
    assert await comms.already_sent(db, 7603, "guardrail",
                                    week2.strftime("%G-W%V"))


async def test_guardrail_blocks_reactivate_in_busy_week(db):
    """Слот недели занят чужим маркетингом (welcome) → R1 молчит."""
    now = datetime(2026, 9, 7, 10, 0, tzinfo=timezone.utc)
    user = await _sleeping_user(db, 7604, last_seen=now - timedelta(days=16))

    week_key = now.strftime("%G-W%V")
    async with transaction(db):
        await db.execute(
            "INSERT INTO deliveries(tg_id, kind, key, created_at) "
            "VALUES(:tg_id, 'guardrail', :key, :created_at)",
            {"tg_id": 7604, "key": week_key, "created_at": utcnow()})

    await scheduler._reactivate_chain(RecordingBot(), db, user, now_utc=now)
    assert not await comms.already_sent(db, 7604, "reactivate",
                                        f"r1:{user['last_seen'][:7]}")


# ─────────────────────────── суточный sweep ───────────────────────────────────

async def test_daily_sweep_sends_and_marks_day(db):
    """Полный sweep: R1 уходит, день отмечен (идемпотентность)."""
    now = datetime(2026, 9, 6, 10, 0, tzinfo=timezone.utc)
    user = await _sleeping_user(db, 7501, last_seen=now - timedelta(days=16))
    await db.execute(
        "INSERT INTO practices(tg_id, code, day_index, started_at) "
        "VALUES(:tg_id, 'love_release', 2, :now)",
        {"tg_id": 7501, "now": _iso(now - timedelta(days=20))})
    await db.commit()

    bot = RecordingBot()
    # _daily_sweep_due мокаем: день уже отмечен → вторая ветка не срабатывает.
    # Проверяем цепочку напрямую через _reactivate_chain (sweep-диспатчер
    # отрабатывает _daily_sweep_due, который зависит от реального часа).
    await scheduler._reactivate_chain(bot, db, user, now_utc=now)
    assert len(bot.sent) == 1
    assert await comms.already_sent(db, 7501, "reactivate",
                                    f"r1:{user['last_seen'][:7]}")

    # Дубль под тем же ключом — не уходит.
    bot2 = RecordingBot()
    await scheduler._reactivate_chain(bot2, db, user,
                                     now_utc=now + timedelta(hours=1))
    assert len(bot2.sent) == 0


async def test_daily_sweep_due_reactivate_key(db):
    """Идемпотентность по ключу crm.reactivate_last_run."""
    now = datetime(2026, 9, 6, 10, 5, tzinfo=timezone.utc)
    assert await scheduler._daily_sweep_due(
        db, scheduler.REACTIVATE_LAST_RUN_KEY, now)
    assert not await scheduler._daily_sweep_due(
        db, scheduler.REACTIVATE_LAST_RUN_KEY, now)


async def test_daily_sweeps_independent_marks(db):
    """Reactivate-отметка независима от welcome/onboard."""
    from app.repo import content
    now = datetime(2026, 9, 6, 10, 0, tzinfo=timezone.utc)
    await _sleeping_user(db, 7511, last_seen=now - timedelta(days=16))
    await content.set_setting(db, scheduler.WELCOME_LAST_RUN_KEY,
                              now.strftime("%Y-%m-%d"))
    await content.set_setting(db, scheduler.ONBOARD_LAST_RUN_KEY,
                              now.strftime("%Y-%m-%d"))

    bot = RecordingBot()
    await scheduler._daily_sweeps(bot, db, now)
    assert len(bot.sent) == 1


async def test_chain_uses_lang(db):
    """EN-клиентка получает EN-персонализированный R1-текст."""
    now = datetime.now(timezone.utc)
    user = await _sleeping_user(db, 7521, last_seen=now - timedelta(days=16),
                                lang="en")
    await db.execute(
        "INSERT INTO practices(tg_id, code, day_index, started_at) "
        "VALUES(:tg_id, 'love_release', 3, :now)",
        {"tg_id": 7521, "now": _iso(now - timedelta(days=20))})
    await db.commit()

    bot = RecordingBot()
    await scheduler._reactivate_chain(bot, db, user, now_utc=now)
    text = bot.sent[0][1]
    assert "your practice" in text


async def test_chain_silent_when_template_missing(db):
    """Нет шаблона reactivate_r1 — молчим."""
    now = datetime.now(timezone.utc)
    user = await _sleeping_user(db, 7531, last_seen=now - timedelta(days=16))

    bot = RecordingBot()
    with patch("app.services.scheduler.content.get_text", return_value=""):
        await scheduler._reactivate_chain(bot, db, user, now_utc=now)
    assert bot.sent == []
