"""Регулярные сценарии: утренние прогнозы, отчёты, продления, практики, рассылки.

Каждая отправка защищена отметкой в `deliveries`: раньше отметки жили в множестве
внутри процесса, и после рестарта клиентка получала утренний прогноз второй раз.
Отметка ставится ДО отправки — из двух рисков (не отправить / отправить дважды)
дубль в личном чате хуже.

Тик идёт раз в 10 минут и сам решает, кому что пора: часы у клиенток разные,
и «9 утра» — это девять по её таймзоне, а не по серверной.

Почему аудитория выбирается по часовому окну, а не целиком. Раньше тик тянул
ВСЕХ пользователей и по каждому делал полдесятка запросов — на десяти тысячах
это шестьдесят тысяч запросов каждые десять минут, из которых полезны единицы.
Теперь список сначала сужается по таймзонам, у которых сейчас нужный час, и
только эти клиентки доходят до сценариев.
"""
from __future__ import annotations

import asyncio
import logging
import os
import socket
import uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from ..data.session import transaction

from ..core import agent as agent_core
from ..core import astro
from ..repo import comms, content, users
from . import analytics, broadcast, horoscopes, payment_monitor, practices as practices_svc

log = logging.getLogger("oracle.scheduler")

TICK_SECONDS = 600          # 10 минут: часовые окна не проскакивают
LEASE_SECONDS = max(TICK_SECONDS * 3, 1800)  # stale recovery after a missed owner
SCHEDULER_NAME = "main"
BATCH_PAUSE = 0.05          # пауза между отправками внутри тика
AUDIENCE_CAP = 5000         # сколько клиенток обрабатываем за один тик

_LUNAR_EN = {
    "Новолуние": "New Moon",
    "Полнолуние": "Full Moon",
}


def _user_lang(user) -> str:
    return "en" if user["lang"] == "en" else "ru"


async def _deliver(bot, tg_id: int, text: str, markup=None) -> bool:
    """Отправляет сообщение. False — стоит попробовать позже.

    Блокировка бота и удалённый чат — навсегда: возвращаем True, чтобы отметка
    осталась и планировщик не долбился в этот чат каждые десять минут.
    """
    from aiogram.exceptions import (TelegramBadRequest, TelegramForbiddenError,
                                    TelegramRetryAfter)
    try:
        await bot.send_message(tg_id, text, reply_markup=markup)
        return True
    except TelegramRetryAfter as e:
        log.warning("флуд-контроль: пауза %s с", e.retry_after)
        await asyncio.sleep(e.retry_after + 1)
        return False
    except (TelegramForbiddenError, TelegramBadRequest) as e:
        log.info("рассылка пропущена навсегда: %s", type(e).__name__)
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("рассылка не удалась, повторю позже: %s", type(e).__name__)
        return False


async def _send_once(bot, db, tg_id: int, kind: str, key: str, text: str,
                     markup=None) -> bool:
    """Отправка с защитой от дубля. False — уже отправляли или не вышло."""
    if not await comms.claim(db, tg_id, kind, key):
        return False
    if await _deliver(bot, tg_id, text, markup):
        return True
    await comms.unclaim(db, tg_id, kind, key)   # временный сбой — попробуем позже
    return False


# ─────────────────────────── выбор аудитории ──────────────────────────────────

def _zones_at_hour(now_utc: datetime, hours: set[int]) -> set[str]:
    """Таймзоны из БД, где сейчас один из нужных часов.

    Перебираем не пользователей, а список таймзон — их десятки, а не тысячи.
    """
    out = set()
    for tz_name in _KNOWN_ZONES:
        try:
            if now_utc.astimezone(ZoneInfo(tz_name)).hour in hours:
                out.add(tz_name)
        except Exception:  # noqa: BLE001
            continue
    return out


#: Заполняется на первом тике из БД: какие таймзоны реально встречаются.
_KNOWN_ZONES: list[str] = []


async def _refresh_zones(db) -> None:
    global _KNOWN_ZONES
    cur = await db.execute(
        "SELECT DISTINCT COALESCE(tz,'Europe/Moscow') tz FROM users "
        "WHERE onboarded=1 AND status='active'")
    zones = [r["tz"] for r in await cur.fetchall()]
    _KNOWN_ZONES = zones or [users.DEFAULT_TZ]


async def _audience(db, zones: set[str]) -> list:
    """Активные клиентки из указанных таймзон, все, без отсечки в 5000.

    Курсор по `tg_id`: пачки по AUDIENCE_CAP с ORDER BY tg_id и условием
    tg_id>last, пока не доберём всех. Раньше LIMIT 5000 резал аудиторию —
    на 10 тысячах половина клиенток за тик не получала бы ничего.
    """
    if not zones:
        return []
    zones_list = list(zones)
    out: list = []
    last_id = 0
    while True:
        cur = await db.execute(
            f"SELECT * FROM users WHERE onboarded=1 AND status='active' "
            f"AND tg_id>:last_id AND COALESCE(tz,'Europe/Moscow') = ANY(:zones) "
            f"ORDER BY tg_id LIMIT {AUDIENCE_CAP}",
            {"last_id": last_id, "zones": zones_list})
        batch = await cur.fetchall()
        if not batch:
            return out
        out.extend(batch)
        last_id = batch[-1]["tg_id"]


async def _expiring_audience(db, now_utc: datetime) -> list:
    """Кому пора сказать про конец доступа — выбираем сразу условием, не перебором.

    Та же курсорная пагинация по tg_id: продление привязано к дате окончания,
    а не к часу, поэтому условие другое, а лимита быть не должно.
    """
    soon = (now_utc + timedelta(days=2)).isoformat()
    now_iso = now_utc.isoformat()
    out: list = []
    last_id = 0
    while True:
        cur = await db.execute(
            "SELECT * FROM users WHERE onboarded=1 AND status='active' AND tg_id>:last_id "
            "AND sub_until IS NOT NULL AND ("
            "  (sub_until > :now AND sub_until <= :soon AND COALESCE(expiry_notified,0) = 0)"
            "  OR (sub_until <= :now2 AND COALESCE(expiry_notified,0) <> 2)"
            f") ORDER BY tg_id LIMIT {AUDIENCE_CAP}",
            {"last_id": last_id, "now": now_iso, "soon": soon, "now2": now_iso})
        batch = await cur.fetchall()
        if not batch:
            return out
        out.extend(batch)
        last_id = batch[-1]["tg_id"]


# ─────────────────────────── сценарии по клиентке ─────────────────────────────

#: Фазы Луны, ради которых стоит будить бесплатную клиентку: полнолуние и
#: новолуние сами по себе редки (~2 раза в месяц), а счётчик за неделю страхует
#: от сбоев календаря, которые наплодили бы спам.
_LUNAR_ALERT_PHASES = frozenset({"Новолуние", "Полнолуние"})
#: Лунные алерты для free — не чаще 2 в неделю (guardrail «не спамить»).
_FREE_LUNAR_PER_WEEK = 2


async def _morning_forecast(bot, db, user, now, settings_cache) -> None:
    if not user["morning_push"]:
        return
    if now.hour != settings_cache["morning_hour"]:
        return
    if users.sub_active(user):
        await _paid_morning_forecast(bot, db, user, now)
    else:
        await _free_morning_forecast(bot, db, user, now)


async def _paid_morning_forecast(bot, db, user, now) -> None:
    """Платный утренний пуш — в тарифе обещаны персональный прогноз и озвучка."""
    day = now.strftime("%Y-%m-%d")
    if await comms.already_sent(db, user["tg_id"], "forecast", day):
        return
    text = await agent_core.daily_forecast_cached(db, user)
    if await _send_once(bot, db, user["tg_id"], "forecast", day, text):
        await analytics.track(db, analytics.E_FORECAST, user["tg_id"],
                              props={"channel": "push"}, surface="system")
        await _voice_forecast(bot, db, user, text, day)


async def _free_morning_forecast(bot, db, user, now) -> None:
    """Бесплатный утренний пуш — подогревает free, не отнимая платных функций.

    Два формата: ежедневный короткий прогноз с приглашением в Mini App и редкие
    лунные алерты (полнолуние/новолуние, не чаще двух в неделю). Прогноз
    использует тот же кеш `forecast`, что и paid, — клиентка не увидит
    «утреннее дважды», если успела заглянуть в Mini App до рассылки.
    """
    day = now.strftime("%Y-%m-%d")
    lang = _user_lang(user)
    if not await comms.already_sent(db, user["tg_id"], "forecast", day):
        text = await agent_core.daily_forecast_cached(db, user)
        cta = await content.get_text(
            db, "copy", "free_forecast_cta",
            ("\n\n🔮 <b>Oracle</b> — your free daily forecast. "
             "Your card of the day and full reading are in the Mini App ✨"
             if lang == "en" else
             "\n\n🔮 <b>Оракул</b> — бесплатный прогноз дня. "
             "Карта дня и полный разбор — в Mini App ✨"),
            lang=lang)
        await _send_free_push(bot, db, user, "forecast", day, text + cta)
    await _free_lunar_alert(bot, db, user, now)


async def _send_free_push(bot, db, user, kind: str, key: str, text: str) -> None:
    """Отправка free-пуша с пометкой в аналитике: канал push есть и у бесплатных."""
    if await _send_once(bot, db, user["tg_id"], kind, key, text):
        await analytics.track(db, analytics.E_FORECAST, user["tg_id"],
                              props={"channel": "push", "tier": "free"},
                              surface="system")


async def _free_lunar_alert(bot, db, user, now) -> None:
    """Лунный алерт полнолуния/новолуния — не чаще 2 в неделю на клиентку."""
    moon = astro.moon_phase(now.date())
    if moon["name"] not in _LUNAR_ALERT_PHASES:
        return
    week = now.strftime("%G-W%V")
    cur = await db.execute(
        "SELECT COUNT(*) c FROM deliveries WHERE tg_id=:tg_id AND kind='forecast_lunar' "
        "AND key LIKE :week_pat",
        {"tg_id": user["tg_id"], "week_pat": week + ":%"})
    if (await cur.fetchone())["c"] >= _FREE_LUNAR_PER_WEEK:
        return
    key = f"{week}:{now.strftime('%Y-%m-%d')}"
    if await comms.already_sent(db, user["tg_id"], "forecast_lunar", key):
        return
    lang = _user_lang(user)
    template = await content.get_text(
        db, "copy", "free_lunar_alert",
        ("🌕 {moon} — a special night for you.\n\n"
         "Open Oracle for a gentle lunar guide in the Mini App ✨"
         if lang == "en" else
         "🌕 {moon} — особенная ночь для тебя.\n\n"
         "{advice}.\n\n"
         "🌙 Оракул следит за небом — карта дня ждёт в Mini App ✨"),
        lang=lang)
    moon_name = _LUNAR_EN.get(moon["name"], moon["name"]) if lang == "en" else moon["name"]
    text = template.replace("{moon}", moon_name).replace("{advice}", moon["advice"])
    await _send_free_push(bot, db, user, "forecast_lunar", key, text)


async def _voice_forecast(bot, db, user, text: str, day: str) -> None:
    """Озвучка прогноза — обещана в тарифе «Консьерж», значит должна работать.

    Молчаливо пропускаем, если TTS не настроен: тариф деградирует до текста,
    а не отдаёт ошибку.
    """
    from ..core import llm
    from ..repo import billing as billing_repo

    if not llm.tts_enabled():
        return
    if not await content.is_on(db, "audio_forecast", user["tg_id"], default=True):
        return
    plan = await billing_repo.get_plan(db, user["sub_level"] or "free")
    if "Аудио" not in " ".join(plan.get("features") or []):
        return
    lang = "en" if user["lang"] == "en" else "ru"
    clean = (text or "").replace("<b>", "").replace("</b>", "") \
                        .replace("<i>", "").replace("</i>", "")
    audio = await llm.speak(
        clean, db=db, tg_id=user["tg_id"], surface="bot",
        reference_id=f"forecast:{day}")
    if not audio:
        return
    try:
        from aiogram.types import BufferedInputFile
        message = await bot.send_voice(
            user["tg_id"], BufferedInputFile(audio, filename="forecast.ogg"),
            caption=("🎧 Your forecast in audio" if lang == "en"
                     else "🎧 Твой прогноз голосом"))
        from ..data.session import transaction
        async with transaction(db):
            await db.execute(
                "UPDATE forecasts SET audio_file_id=:audio_file_id "
                "WHERE tg_id=:tg_id AND day=:day AND lang=:lang",
                {"audio_file_id": message.voice.file_id if message.voice else None,
                 "tg_id": user["tg_id"], "day": day, "lang": lang})
    except Exception as e:  # noqa: BLE001
        log.info("озвучка прогноза не отправлена: %s", type(e).__name__)


async def _pregen_forecasts(db, now_utc, settings_cache) -> None:
    """Утренние прогнозы генерируем заранее — за час до рассылки по таймзоне.

    Не глобально в один час: час у клиентки свой, и преген идёт в том же окне,
    что и рассылка (местные morning_hour-1), значит растягивается по суткам и
    не упирается в рейт-лимит LLM (G6). Кеш forecasts делает преген
    идемпотентным: заглянувшая в Mini App до рассылки клиентка уже получила
    текст, и повторные тики не тратят вызовов. Генерация параллельная.
    """
    pregen_hour = max(0, settings_cache["morning_hour"] - 1)
    if pregen_hour == settings_cache["morning_hour"]:
        return          # morning_hour=0: окна совпадают, преген бесполезен
    zones = _zones_at_hour(now_utc, {pregen_hour})
    # Преген работает и для free: их утренний пуш живёт в том же часу и питается
    # тем же кешем `forecast`, иначе каждая отправка ждала бы LLM-генерацию.
    audience = [u for u in await _audience(db, zones) if u["morning_push"]]
    if not audience:
        return
    # Реальную цену вызовам ставит семафор LLM (G6); 32 здесь лишь чтобы не
    # плодить тысячу корутин при большой аудитории.
    sem = asyncio.Semaphore(32)

    async def one(user):
        async with sem:
            try:
                await agent_core.daily_forecast_cached(db, user)
            except Exception as e:  # noqa: BLE001
                log.warning("преген прогноза: %s", type(e).__name__)

    log.info("преген прогнозов: %s клиенток", len(audience))
    await asyncio.gather(*(one(u) for u in audience))


async def _expiry_warning(bot, db, user, now_utc) -> None:
    """За два дня до конца подписки — сцена продления (однократно)."""
    if not user["sub_until"] or not users.sub_active(user) or user["expiry_notified"]:
        return
    try:
        until = datetime.fromisoformat(user["sub_until"])
    except (TypeError, ValueError):
        return
    if until - now_utc > timedelta(days=2):
        return
    lang = _user_lang(user)
    template = await content.get_text(
        db, "copy", "expiry_soon",
        ("🌙 {name}, our connection is growing thin — fewer than two days remain..."
         if lang == "en" else
         "🌙 {name}, наша связь истончается — осталось меньше двух дней..."),
        lang=lang)
    text = template.replace("{name}", user["name"] or ("dear one" if lang == "en" else "друг"))
    text += ("\n\nRenew: 👤 Profile → 👑 Renew VIP" if lang == "en"
             else "\n\nПродлить: 👤 Профиль → 👑 Продлить VIP")
    if await _send_once(bot, db, user["tg_id"], "expiry", user["sub_until"], text):
        await users.update(db, user["tg_id"], expiry_notified=1)
        await analytics.track(db, analytics.E_CHURN_WARN, user["tg_id"],
                              surface="system")


async def _winback(bot, db, user) -> None:
    """Подписка кончилась — одно тёплое напоминание, без давления."""
    if not user["sub_until"] or users.sub_active(user):
        return
    if user["expiry_notified"] == 2:
        return
    lang = _user_lang(user)
    text = await content.get_text(
        db, "copy", "winback",
        ("💫 The stars have grown quiet, but I have not left — I am simply "
         "waiting beyond the veil." if lang == "en" else
         "💫 Звёзды затихли, но я не ушла — просто жду по ту сторону завесы."),
        lang=lang)
    text += ("\n\n👤 Profile → 👑 Renew VIP · or enter promo code /promo 🎟"
             if lang == "en" else
             "\n\n👤 Профиль → 👑 Продлить VIP · или введи промокод /promo 🎟")
    if await _send_once(bot, db, user["tg_id"], "winback", user["sub_until"], text):
        await users.update(db, user["tg_id"], expiry_notified=2)


async def _weekly_report(bot, db, user, now, settings_cache) -> None:
    from ..repo import dialog, readings
    if not users.sub_active(user):
        return
    if now.weekday() != settings_cache["weekly_weekday"]:
        return
    if now.hour != settings_cache["weekly_hour"]:
        return
    key = now.strftime("%G-W%V")            # ISO-неделя: год + номер недели
    if await comms.already_sent(db, user["tg_id"], "weekly", key):
        return
    streak = await dialog.diary_streak(db, user["tg_id"])
    readings_n = await readings.readings_count_since(db, user["tg_id"], 7)
    text = (f"🌌 <b>Твоя неделя со мной</b>\n\n"
            f"🎴 Раскладов: {readings_n}\n"
            f"📖 Стрик дневника: {streak} дн. {'🔥' if streak >= 3 else ''}\n\n"
            f"Новая неделя — новое небо. Загляни утром за прогнозом ✨")
    await _send_once(bot, db, user["tg_id"], "weekly", key, text)


async def _monthly_report(bot, db, user, now, settings_cache) -> None:
    if not users.sub_active(user):
        return
    if now.day != settings_cache["monthly_day"] or now.hour != 11:
        return
    key = now.strftime("%Y-%m")
    if await comms.already_sent(db, user["tg_id"], "monthly", key):
        return
    if not await content.is_on(db, "monthly_report", user["tg_id"], default=True):
        return
    text = await agent_core.monthly_report(db, user)
    await _send_once(bot, db, user["tg_id"], "monthly", key, text)


async def _practice_reminder(bot, db, user, now, settings_cache) -> None:
    """Напоминание о практике: она держится на непрерывности дней.

    Практика без напоминания бросается на третий-четвёртый день — это и есть
    главная причина, по которой раздел вообще нуждается в планировщике.
    """
    if now.hour != settings_cache["practice_hour"]:
        return
    if not await content.is_on(db, "practice_reminders", user["tg_id"], default=True):
        return
    day = now.strftime("%Y-%m-%d")
    if await comms.already_sent(db, user["tg_id"], "practice", day):
        return

    running = [p for p in await practices_svc.list_for_user(db, user)
               if p["started"] and not p["finished"]
               and (p["last_done"] or "")[:10] != day]
    if not running:
        return
    item = running[0]
    step = item.get("today_step") or ""
    steps = "\n".join(f"{i}. {s}" for i, s in enumerate(item["steps"][:5], 1))
    text = (f"{item['emoji']} <b>{item['title']}</b> — день "
            f"{item['day_index'] + 1} из {item['days']}"
            + (f" · стрик {item['streak']} 🔥" if item["streak"] >= 2 else "") + "\n\n"
            + (f"<i>{step}</i>\n\n" if step else "")
            + f"{steps}\n\n"
            + "Отметить день можно в Mini App → 📖 Дневник → Практики.")
    await _send_once(bot, db, user["tg_id"], "practice", day, text)


async def _tick_user(bot, db, user, now_utc, settings_cache) -> None:
    now = now_utc.astimezone(users.user_tz(user))
    if await content.is_on(db, "daily_push", user["tg_id"], default=True):
        await _morning_forecast(bot, db, user, now, settings_cache)
    if await content.is_on(db, "weekly_report", user["tg_id"], default=True):
        await _weekly_report(bot, db, user, now, settings_cache)
    await _monthly_report(bot, db, user, now, settings_cache)
    await _practice_reminder(bot, db, user, now, settings_cache)


# ────────────────────────────── общий цикл ────────────────────────────────────

async def _load_settings(db) -> dict:
    async def num(key: str, default: int) -> int:
        try:
            return int(await content.get_setting(db, key, default) or default)
        except (TypeError, ValueError):
            return default

    return {
        "morning_hour": await num("push.morning_hour", 9),
        "weekly_hour": await num("push.weekly_hour", 19),
        "weekly_weekday": await num("push.weekly_weekday", 6),
        "monthly_day": await num("push.monthly_day", 1),
        "practice_hour": await num("push.practice_hour", 8),
        "horoscope_hour": await num("push.horoscope_hour", 7),
    }


async def _horoscopes(bot, db, now_utc, settings_cache) -> None:
    """Двенадцать текстов в сутки на весь сервис — собираем и публикуем один раз."""
    if not await content.is_on(db, "daily_horoscopes", default=True):
        return
    # Собираем на час раньше публикации, чтобы к посту тексты уже были готовы
    if now_utc.hour == max(0, settings_cache["horoscope_hour"] - 1):
        await horoscopes.build_day(db)
    if now_utc.hour == settings_cache["horoscope_hour"]:
        await horoscopes.build_day(db)
        await horoscopes.post_day(bot, db)


def scheduler_owner() -> str:
    """Stable-per-process owner token; it is never exposed to users or analytics."""
    return f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:12]}"


async def acquire_scheduler_lease(db, owner: str, *, now: datetime | None = None,
                                  lease_seconds: int = LEASE_SECONDS) -> bool:
    """Atomically claim the scheduler lease or recover an expired owner."""
    current = now or datetime.now(timezone.utc)
    stamp = current.isoformat()
    lease_until = (current + timedelta(seconds=lease_seconds)).isoformat()
    async with transaction(db):
        cursor = await db.execute(
            "INSERT INTO scheduler_leases "
            "(name, owner, acquired_at, lease_until, last_started_at, last_status, "
            "last_error, run_count) VALUES (:name, :owner, :stamp, :lease_until, "
            ":stamp2, 'running', NULL, 1) "
            "ON CONFLICT(name) DO UPDATE SET owner=excluded.owner, "
            "acquired_at=excluded.acquired_at, lease_until=excluded.lease_until, "
            "last_started_at=excluded.last_started_at, last_status='running', "
            "last_error=NULL, run_count=scheduler_leases.run_count + 1 "
            "WHERE scheduler_leases.lease_until IS NULL "
            "OR scheduler_leases.lease_until <= :now "
            "OR scheduler_leases.owner = :owner2",
            {"name": SCHEDULER_NAME, "owner": owner, "stamp": stamp,
             "lease_until": lease_until, "stamp2": stamp, "now": stamp, "owner2": owner},
        )
        return cursor.rowcount == 1


async def finish_scheduler_lease(db, owner: str, *, status: str,
                                 error: str | None = None,
                                 now: datetime | None = None) -> bool:
    """Release only the lease owned by this process and record the outcome."""
    if status not in {"ok", "error"}:
        raise ValueError("scheduler lease status must be ok or error")
    stamp = (now or datetime.now(timezone.utc)).isoformat()
    message = (error or "")[:500] or None
    async with transaction(db):
        cursor = await db.execute(
            "UPDATE scheduler_leases SET lease_until=:stamp, last_finished_at=:stamp2, "
            "last_status=:status, last_error=:error, "
            "failure_count=failure_count + :fail_inc "
            "WHERE name=:name AND owner=:owner",
            {"stamp": stamp, "stamp2": stamp, "status": status, "error": message,
             "fail_inc": 1 if status == "error" else 0,
             "name": SCHEDULER_NAME, "owner": owner},
        )
        return cursor.rowcount == 1


async def scheduler_status(db) -> dict:
    """Return safe operator status without owner identifiers or private content."""
    cursor = await db.execute(
        "SELECT name, acquired_at, lease_until, last_started_at, last_finished_at, "
        "last_status, last_error, run_count, failure_count "
        "FROM scheduler_leases WHERE name=:name", {"name": SCHEDULER_NAME})
    row = await cursor.fetchone()
    if not row:
        return {"name": SCHEDULER_NAME, "status": "never", "run_count": 0,
                "failure_count": 0, "last_error": None}
    return {"name": row["name"], "acquired_at": row["acquired_at"],
            "lease_until": row["lease_until"], "last_started_at": row["last_started_at"],
            "last_finished_at": row["last_finished_at"], "status": row["last_status"],
            "last_error": row["last_error"], "run_count": row["run_count"],
            "failure_count": row["failure_count"]}


async def tick(bot, db) -> None:
    """Один проход планировщика."""
    settings_cache = await _load_settings(db)
    now_utc = datetime.now(timezone.utc)
    await _refresh_zones(db)

    # Часы, ради которых вообще стоит будить сценарии по клиенткам
    hours = {settings_cache["morning_hour"], settings_cache["weekly_hour"],
             settings_cache["practice_hour"], 11}
    audience = await _audience(db, _zones_at_hour(now_utc, hours))
    for user in audience:
        try:
            await _tick_user(bot, db, user, now_utc, settings_cache)
        except Exception as e:  # noqa: BLE001
            log.warning("ошибка планировщика для пользовательского сценария: %s",
                        type(e).__name__)
        await asyncio.sleep(BATCH_PAUSE)

    # Продления и возвраты не привязаны к часу клиентки — они привязаны к дате
    # окончания подписки, поэтому выбираются отдельным условием
    for user in await _expiring_audience(db, now_utc):
        try:
            await _expiry_warning(bot, db, user, now_utc)
            await _winback(bot, db, user)
        except Exception as e:  # noqa: BLE001
            log.warning("ошибка сценария продления: %s", type(e).__name__)
        await asyncio.sleep(BATCH_PAUSE)

    try:
        await _pregen_forecasts(db, now_utc, settings_cache)
    except Exception as e:  # noqa: BLE001
        log.error("преген прогнозов: %s", e)

    try:
        await _horoscopes(bot, db, now_utc, settings_cache)
    except Exception as e:  # noqa: BLE001
        log.error("гороскопы: %s", e)

    try:
        await broadcast.tick(bot, db)
    except Exception as e:  # noqa: BLE001
        log.error("рассылки: %s", e)

    try:
        await payment_monitor.run(bot, db, now=now_utc)
    except Exception as e:  # noqa: BLE001
        # Health monitoring must never stop user scenarios or hide the scheduler
        # heartbeat; the next lease-protected tick will retry it.
        log.warning("мониторинг платежей: %s", type(e).__name__)

    try:
        await analytics.rollup(db)
        if now_utc.hour == 4 and now_utc.minute < 15:
            removed = await comms.prune(db)
            if removed:
                log.info("журнал доставок: удалено %s старых отметок", removed)
            purged = await analytics.prune(db)
            if purged:
                log.info("аналитика: удалено %s старых событий", purged)
    except Exception as e:  # noqa: BLE001
        log.warning("агрегация метрик: %s", e)


async def run(bot, db) -> None:
    """Бесконечный цикл с SQLite lease: второй bot process остаётся standby."""
    owner = scheduler_owner()
    log.info("планировщик запущен, тик каждые %s с", TICK_SECONDS)
    while True:
        claimed = False
        try:
            claimed = await acquire_scheduler_lease(db, owner)
            if not claimed:
                log.warning("планировщик standby: lease занят другим владельцем")
            else:
                try:
                    await tick(bot, db)
                    heartbeat = datetime.now(timezone.utc).isoformat()
                    await content.set_setting(db, "system.heartbeat", heartbeat)
                    await finish_scheduler_lease(db, owner, status="ok")
                except asyncio.CancelledError:
                    await finish_scheduler_lease(db, owner, status="error", error="cancelled")
                    log.info("планировщик остановлен")
                    raise
                except Exception as e:  # noqa: BLE001
                    await finish_scheduler_lease(db, owner, status="error", error=str(e))
                    log.error("планировщик: %s", e)
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            log.error("lease планировщика: %s", e)
        await asyncio.sleep(TICK_SECONDS)
