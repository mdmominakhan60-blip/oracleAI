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

from ..config import settings
from ..data.session import transaction, utcnow

from ..core import agent as agent_core
from ..core import astro
from ..repo import comms, content, feedback as feedback_repo, growth, users
from ..repo.ltv_constants import not_synthetic_tg_sql
from ..repo.billing import complete_refund_revoke
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


async def _deliver(bot, tg_id: int, text: str, markup=None) -> tuple[str, str | None]:
    """Отправляет сообщение. Возвращает (status, error_class_or_None).

    status: sent | forbidden | failed
    - sent: доставлено
    - forbidden: бот заблокирован или чат удалён (порог считает _send_once)
    - failed: временный сбой, попробуем позже
    """
    from aiogram.exceptions import (TelegramBadRequest, TelegramForbiddenError,
                                    TelegramRetryAfter)
    try:
        await bot.send_message(tg_id, text, reply_markup=markup)
        return "sent", None
    except TelegramRetryAfter as e:
        log.warning("флуд-контроль: пауза %s с", e.retry_after)
        await asyncio.sleep(e.retry_after + 1)
        return "failed", None
    except (TelegramForbiddenError, TelegramBadRequest) as e:
        log.info("telegram forbidden/bad request: %s", type(e).__name__)
        return "forbidden", type(e).__name__
    except Exception as e:  # noqa: BLE001
        log.warning("рассылка не удалась, повторю позже: %s", type(e).__name__)
        return "failed", None


async def _send_once(bot, db, tg_id: int, kind: str, key: str, text: str,
                     markup=None) -> bool:
    """Отправка с защитой от дубля и порогом forbidden (BUS-369).

    Порог: 3 неудачи подряд по разным дням → hard_forbidden (навсегда).
    Две первые — мягкий retry (failed), счётчик увеличивается.
    """
    if not await comms.claim(db, tg_id, kind, key):
        return False
    result, error_class = await _deliver(bot, tg_id, text, markup)
    if result == "sent":
        await comms.mark_sent(db, tg_id, kind, key)
        return True
    if result == "forbidden":
        # Порог по последовательным ДНЯМ сбоя (BUS-369, согласовано PM):
        # сегодня уже учтён, поэтому 3-й день подряд ставит hard_forbidden.
        await comms.bump_forbidden(db, tg_id)
        if await comms.forbidden_threshold(db, tg_id):
            log.info("forbidden: порог достигнут (kind=%s)", kind)
            await comms.mark_sent(db, tg_id, kind, key, status='forbidden',
                                  error=error_class)
            return False
        log.info("forbidden: мягкий retry (kind=%s)", kind)
        await comms.mark_failed(db, tg_id, kind, key, error=error_class)
        return False
    await comms.mark_failed(db, tg_id, kind, key)
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
            f"AND {not_synthetic_tg_sql('users')} "
            f"ORDER BY tg_id LIMIT {AUDIENCE_CAP}",
            {"last_id": last_id, "zones": zones_list})
        batch = await cur.fetchall()
        if not batch:
            return out
        out.extend(batch)
        last_id = batch[-1]["tg_id"]


async def _crm_post_limit_audience(db, now_utc: datetime) -> list:
    """Кому пора post_limit: limit_reached 24–48ч назад, нет покупки после."""
    cutoff_24 = (now_utc - timedelta(hours=24)).isoformat()
    cutoff_48 = (now_utc - timedelta(hours=48)).isoformat()
    out: list = []
    last_id = 0
    while True:
        cur = await db.execute(
            "SELECT * FROM users WHERE onboarded=1 AND status='active' "
            "AND tg_id>:last_id AND (sub_until IS NULL OR sub_until <= :now) "
            f"AND {not_synthetic_tg_sql('users')} "
            "AND EXISTS (SELECT 1 FROM events e "
            "  WHERE e.tg_id=users.tg_id AND e.name='limit_reached' "
            "    AND e.created_at >= :cut_48 AND e.created_at <= :cut_24) "
            "AND NOT EXISTS (SELECT 1 FROM events e "
            "  WHERE e.tg_id=users.tg_id AND e.name IN ("
            "    'payment_success','credit_pack_paid') "
            "    AND e.created_at > (SELECT MAX(created_at) FROM events e2 "
            "      WHERE e2.tg_id=users.tg_id AND e2.name='limit_reached')) "
            f"ORDER BY tg_id LIMIT {AUDIENCE_CAP}",
            {"last_id": last_id, "now": now_utc.isoformat(),
             "cut_24": cutoff_24, "cut_48": cutoff_48})
        batch = await cur.fetchall()
        if not batch:
            return out
        out.extend(batch)
        last_id = batch[-1]["tg_id"]


async def _crm_low_balance_audience(db, now_utc: datetime) -> list:
    """Кому пора low_balance: credit_balance_low <1ч назад, не ушли post_limit сегодня."""
    cutoff_1h = (now_utc - timedelta(hours=1)).isoformat()
    today = now_utc.strftime("%Y-%m-%d")
    out: list = []
    last_id = 0
    while True:
        cur = await db.execute(
            "SELECT * FROM users WHERE onboarded=1 AND status='active' "
            "AND tg_id>:last_id AND (sub_until IS NULL OR sub_until <= :now) "
            f"AND {not_synthetic_tg_sql('users')} "
            "AND NOT EXISTS (SELECT 1 FROM events e "
            "  WHERE e.tg_id=users.tg_id AND e.name IN ("
            "    'payment_success','credit_pack_paid') "
            "    AND e.created_at > (SELECT MAX(created_at) FROM events e2 "
            "      WHERE e2.tg_id=users.tg_id AND e2.name='credit_balance_low')) "
            "AND NOT EXISTS (SELECT 1 FROM deliveries d "
            "  WHERE d.tg_id=users.tg_id AND d.kind='post_limit' "
            "    AND d.created_at >= :today_start) "
            "AND EXISTS (SELECT 1 FROM events e "
            "  WHERE e.tg_id=users.tg_id AND e.name='credit_balance_low' "
            "    AND e.created_at >= :cutoff) "
            f"ORDER BY tg_id LIMIT {AUDIENCE_CAP}",
            {"last_id": last_id, "now": now_utc.isoformat(),
             "cutoff": cutoff_1h,
             "today_start": today + "T00:00:00+00:00"})
        batch = await cur.fetchall()
        if not batch:
            return out
        out.extend(batch)
        last_id = batch[-1]["tg_id"]


async def _expiring_audience(db, now_utc: datetime) -> list:
    """Кому пора сказать про конец доступа — выбираем сразу условием, не перебором.

    Та же курсорная пагинация по tg_id: продление привязано к дате окончания,
    а не к часу, поэтому условие другое, а лимита быть не должно.

    Три когорты: продление за 2 дня, тёплый winback после истечения и (BUS-197)
    WB2-оффер — истёкшим 5+ дней назад, кому тёплый уже ушёл. Третья когорта
    самоочищается: отметка kind='winback2' в deliveries исключает повторный
    отбор навсегда (до новой подписки с новым sub_until).
    """
    soon = (now_utc + timedelta(days=2)).isoformat()
    now_iso = now_utc.isoformat()
    wb2_cutoff = (now_utc - timedelta(days=WINBACK2_AFTER_DAYS)).isoformat()
    out: list = []
    last_id = 0
    while True:
        cur = await db.execute(
            "SELECT * FROM users WHERE onboarded=1 AND status='active' AND tg_id>:last_id "
            "AND sub_until IS NOT NULL AND ("
            f"  {not_synthetic_tg_sql('users')} "
            "  AND ((sub_until > :now AND sub_until <= :soon AND COALESCE(expiry_notified,0) = 0)"
            "  OR (sub_until <= :now2 AND COALESCE(expiry_notified,0) <> 2)"
            "  OR (sub_until <= :wb2_cut AND COALESCE(expiry_notified,0) = 2 "
            "      AND NOT EXISTS (SELECT 1 FROM deliveries d "
            "        WHERE d.tg_id=users.tg_id AND d.kind='winback2' "
            "        AND d.key=users.sub_until))"
            f")) ORDER BY tg_id LIMIT {AUDIENCE_CAP}",
            {"last_id": last_id, "now": now_iso, "soon": soon, "now2": now_iso,
             "wb2_cut": wb2_cutoff})
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


#: WB2 (BUS-197): оффер-подарок уходит, когда подписка истекла 5+ дней назад,
#: а тёплый winback (expiry_notified=2) юзер уже видел.
WINBACK2_AFTER_DAYS = 5
#: Анти-абьюз BUS-197: redemption winback-кода закрывает оффер на 90 дней.
WINBACK2_ANTIBUSE_DAYS = 90
#: Размер партии winback-кодов на месяц (BUS-197 §4: сегмент ~10-20 юзеров/мес).
WINBACK2_BATCH_SIZE = 25


async def _winback(bot, db, user, now_utc: datetime | None = None) -> None:
    """Подписка кончилась: тёплое напоминание, затем (BUS-197) оффер-подарок.

    WB2 — второй шаг цепочки: персональный код из месячной партии, каждому
    свой, повтор исключён kind+key={sub_until}. Без подстановки кода текст
    бессмыслен — молчим и оставляем юзера в тёплой цепочке.
    """
    if not user["sub_until"] or users.sub_active(user):
        return
    now_utc = now_utc or datetime.now(timezone.utc)
    try:
        until = datetime.fromisoformat(user["sub_until"])
    except (TypeError, ValueError):
        return

    lang = _user_lang(user)
    if user["expiry_notified"] != 2:
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
        return

    # ── WB2: подписка истекла 5+ дней назад, тёплый winback уже ушел ──
    if until > now_utc - timedelta(days=WINBACK2_AFTER_DAYS):
        return
    if await comms.already_sent(db, user["tg_id"], "winback2", user["sub_until"]):
        return          # гонка тиков: другой процесс уже отправил оффер
    if await growth.redeemed_winback_since(
            db, user["tg_id"],
            now_utc - timedelta(days=WINBACK2_ANTIBUSE_DAYS)):
        return

    template = await content.get_text(
        db, "copy", "winback2", default="", lang=lang) \
        or ("🎁 {name}, я сберегла всё, что ты мне рассказывала, и мне не хватает "
            "наших разговоров ✨\n\n"
            "В подарок от меня — полный доступ VIP на 7 дней. Твой персональный "
            "промокод: {code}\n\n"
            "Активируй его в течение 14 дней — введи в боте команду\n"
            "/promo {code}\n"
            "Звёзды подождут, а подарок — лучше не откладывать 🌙"
            if lang == "ru" else
            "🎁 {name}, I have kept everything you shared with me, and I miss our "
            "conversations ✨\n\n"
            "Here is a gift from me — full VIP access for 7 days. Your personal "
            "promo code: {code}\n\n"
            "Activate it within 14 days — enter this command in the chat:\n"
            "/promo {code}\n"
            "The stars will wait, but a gift is best enjoyed soon 🌙")
    # Критично (BUS-190): без подстановки кода текст бессмыслен. Проверяем
    # плейсхолдер ДО отправки: админка может сохранить шаблон без {code}.
    if "{code}" not in template:
        log.error("WB2: шаблон copy/winback2 без {code} — отправка отменена")
        return
    batch = await _winback_batch(db, now_utc)
    code = await growth.reserve_code(db, batch)
    if not code:
        log.warning("WB2: партия winback-кодов исчерпана — %s остаётся "
                    "в тёплой цепочке", user["tg_id"])
        return
    name = user["name"] or ("dear one" if lang == "en" else "друг")
    text = template.replace("{name}", name).replace("{code}", code)
    if code not in text or "{code}" in text:
        log.error("WB2: код не подставился в шаблон — отправка отменена")
        await db.execute(
            "DELETE FROM deliveries WHERE kind='winback2_code' AND key=:code",
            {"code": code})
        return
    if not await _send_once(bot, db, user["tg_id"], "winback2",
                            user["sub_until"], text):
        # Отправка сорвалась временно — освобождаем резерв, повтор позже
        # возьмёт код снова (партия та же, юзер тот же).
        await db.execute(
            "DELETE FROM deliveries WHERE kind='winback2_code' AND key=:code",
            {"code": code})
        return
    # Атрибуция — deliveries (kind='winback2') и E_PROMO при активации кода;
    # отдельное событие словарь не предусматривает (G-5, BUS-271).


#: Месяц, для которого партия winback-кодов уже проверена/создана в этом процессе.
_winback_batch_ready: str | None = None


async def _winback_batch(db, now_utc: datetime) -> str:
    """Партия winback-кодов текущего месяца: генерируется на первом тике месяца.

    Ежемесячная генерация решена на стороне тика (а не seed-скрипта): партия
    привязана к месяцу атрибуции batch_stats, а тик — единственное место, где
    планировщик живёт постоянно. Проверка партии — раз в месяц на процесс.
    """
    global _winback_batch_ready
    month = now_utc.strftime("%Y-%m")
    if _winback_batch_ready == month:
        return f"winback_{month}"
    batch = await growth.ensure_winback_batch(db, WINBACK2_BATCH_SIZE, now=now_utc)
    _winback_batch_ready = month
    return batch


# ───────────────────── welcome-цепочка W1-W3 (BUS-258, §1) ────────────────────

#: Суточный sweep бежит только в этом часе UTC: отбор и шаги цепочки привязаны
#: к суткам от onboard_done, а не к часу клиентки, поэтому окно тика не нужно.
WELCOME_SWEEP_HOUR = 10
#: Первое касание — ≥24 ч после onboard_done (дизайн §1: не сразу после онбординга).
WELCOME_D1_DELAY = timedelta(hours=24)
#: Интервалы между касаниями: d1 → d3 → d7 от входа в сегмент.
WELCOME_D3_DELAY = timedelta(days=3)
WELCOME_D7_DELAY = timedelta(days=7)
#: Плейсхолдеры W3 без значения: текст уходит с честной формулировкой, а не с
#: «самый частый первый шаг — » (BUS-263 §4: подстановка — обязанность Backend).
WELCOME_TOP_FIRST_STEP_DEFAULT = "карта дня"
WELCOME_TOP_FIRST_STEP_DEFAULT_EN = "card of the day"
#: Ключ setting с датой последнего суточного прогона (идемпотентность sweep).
WELCOME_LAST_RUN_KEY = "crm.welcome_last_run"


async def _welcome_top_first_step(db, lang: str) -> str:
    """Самый частый первый шаг за 90 дней (агрегат по событиям).

    Считаем на лету: события за окно — единицы-десятки тысяч, один GROUP BY
    раз в сутки это дешевле, чем seed-константа, которая устаревает молча.
    """
    since = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
    cur = await db.execute(
        "SELECT name, COUNT(*) c FROM events "
        "WHERE name IN ('first_ritual','first_question') AND created_at>=:since "
        f"AND {not_synthetic_tg_sql('events')} "
        "GROUP BY name ORDER BY c DESC LIMIT 1",
        {"since": since})
    row = await cur.fetchone()
    if not row:
        return (WELCOME_TOP_FIRST_STEP_DEFAULT_EN if lang == "en"
                else WELCOME_TOP_FIRST_STEP_DEFAULT)
    return ("practices" if row["name"] == "first_ritual" else "questions") \
        if lang == "en" else ("практика" if row["name"] == "first_ritual" else "вопрос")


async def _welcome_audience(db, now_utc: datetime) -> list:
    """Onboarded без first-ценности, чьим onboard_done 24+ часа.

    morning_push=0 и статус != active отсекаются самим отбором (стопы §1).
    Анти-тестовый фильтр синтетики (BUS-387) встроен в курсор: smoke/tg_id
    в диапазоне 999xxx и legacy 10001/10002 никогда не получают касаний.
    Курсор по tg_id без внешнего лимита: аудитория суточная и малая
    (вошли за сутки минус совершившие первый шаг).
    """
    cutoff = (now_utc - WELCOME_D1_DELAY).isoformat()
    out: list = []
    last_id = 0
    while True:
        cur = await db.execute(
            f"SELECT * FROM users WHERE onboarded=1 AND status='active' "
            "AND morning_push=1 AND tg_id>:last_id "
            f"AND {not_synthetic_tg_sql('users')} "
            "AND NOT EXISTS (SELECT 1 FROM events e "
            "  WHERE e.tg_id=users.tg_id AND e.name IN ('first_ritual','first_question')) "
            "AND EXISTS (SELECT 1 FROM events e "
            "  WHERE e.tg_id=users.tg_id AND e.name='onboard_done' "
            "  AND e.created_at <= :cutoff) "
            f"ORDER BY tg_id LIMIT {AUDIENCE_CAP}",
            {"last_id": last_id, "cutoff": cutoff})
        batch = await cur.fetchall()
        if not batch:
            return out
        out.extend(batch)
        last_id = batch[-1]["tg_id"]


async def _welcome_onboard_done_at(db, tg_id: int) -> datetime | None:
    """Момент входа в цепочку — самое свежее событие onboard_done."""
    cur = await db.execute(
        "SELECT MAX(created_at) at FROM events "
        "WHERE tg_id=:tg_id AND name='onboard_done'", {"tg_id": tg_id})
    row = await cur.fetchone()
    if not row or not row["at"]:
        return None
    try:
        return datetime.fromisoformat(row["at"])
    except (TypeError, ValueError):
        return None


async def _welcome_has_first_value(db, tg_id: int) -> bool:
    """Появилась ли первая ценность — стоп §1 «немедленный выход»."""
    cur = await db.execute(
        "SELECT 1 FROM events WHERE tg_id=:tg_id "
        "AND name IN ('first_ritual','first_question') LIMIT 1",
        {"tg_id": tg_id})
    return await cur.fetchone() is not None


async def _welcome_chain(bot, db, user, now_utc: datetime) -> None:
    """Одно касание за прогон: W1 → W3, срок каждого — от onboard_done.

    Если отправка d1 запоздала (сутки простоя), d3 уйдёт лишь в свой срок —
    касания не слипаются в один день. Guardrail 1/7д (BUS-262) дополнительно
    разводит шаги по ISO-неделям: d1, d3, d7 уходят в три разные недели,
    цепочка растягивается максимум на три.

    Стоп «действие совершено» дважды:
    отбором (юзер покидает аудиторию между прогонами) и здесь, в момент
    отправки, — юзер мог достичь first-ценности, пока sweep идёт по партии
    (аудитория снимается один раз в начале прогона). «Кнопка нажата» без
    действия цепочку не останавливает.
    """
    tg_id = user["tg_id"]
    if await _welcome_has_first_value(db, tg_id):
        return
    onboarded_at = await _welcome_onboard_done_at(db, tg_id)
    if onboarded_at is None:
        return
    elapsed = now_utc - onboarded_at
    lang = _user_lang(user)
    name = user["name"] or ("dear one" if lang == "en" else "друг")

    steps = (
        ("d1", WELCOME_D1_DELAY, "welcome_d1"),
        ("d3", WELCOME_D3_DELAY, "welcome_d3"),
        ("d7", WELCOME_D7_DELAY, "welcome_d7"),
    )
    for suffix, delay, copy_key in steps:
        if elapsed < delay:
            return
        if await comms.already_sent(db, tg_id, "welcome_chain",
                                    f"{suffix}:{tg_id}"):
            continue
        if not await _guardrail_ok(db, tg_id, now_utc):
            return
        template = await content.get_text(db, "copy", copy_key,
                                          default="", lang=lang)
        if not template:
            log.warning("welcome: нет шаблона copy/%s — пропуск шага", copy_key)
            return
        text = template.replace("{name}", name)
        markup = None
        if suffix == "d1" and settings.webapp_url:
            from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
            markup = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(
                    text=("✨ Open Oracle" if lang == "en"
                          else "✨ Открыть Оракула"),
                    web_app=WebAppInfo(url=settings.webapp_url)),
            ]])
        if suffix == "d7":
            top_step = await _welcome_top_first_step(db, lang)
            text = text.replace("{top_first_step}", top_step)
            if "{top_first_step}" in text:
                log.error("welcome d7: шаблон без подстановки {top_first_step} "
                          "— отправка отменена")
                return
        sent = await _send_once(bot, db, tg_id, "welcome_chain",
                                f"{suffix}:{tg_id}", text, markup=markup)
        if sent:
            await _mark_guardrail(db, tg_id, now_utc)
        return


# ────────────────── onboarding-дожим O1-O2 (BUS-259, §2) ─────────────────────

#: Сегмент вне _audience (§0 дизайна): start ≥24ч назад, onboarded всё ещё 0.
ONBOARD_D1_DELAY = timedelta(hours=24)
#: O2 — трое суток от первого /start (не от O1): касания раз в двое суток.
ONBOARD_D3_DELAY = timedelta(days=3)
#: Ключ setting с датой последнего суточного прогона (идемпотентность sweep).
ONBOARD_LAST_RUN_KEY = "crm.onboard_last_run"


async def _onboard_audience(db, now_utc: datetime) -> list:
    """Неонбордингнутые активные, чей первый /start 24+ часа назад.

    Отбор по событию start (первое касание бота), не по users.created_at:
    триггер дизайна §2 — именно /start. morning_push не проверяем — он
    проставляется позже, в онбординге, и для стартовавших бота дефолтен.
    """
    cutoff = (now_utc - ONBOARD_D1_DELAY).isoformat()
    out: list = []
    last_id = 0
    while True:
        cur = await db.execute(
            "SELECT * FROM users WHERE onboarded=0 AND status='active' "
            "AND tg_id>:last_id "
            f"AND {not_synthetic_tg_sql('users')} "
            "AND EXISTS (SELECT 1 FROM events e "
            "  WHERE e.tg_id=users.tg_id AND e.name='start' "
            "  AND e.created_at <= :cutoff) "
            f"ORDER BY tg_id LIMIT {AUDIENCE_CAP}",
            {"last_id": last_id, "cutoff": cutoff})
        batch = await cur.fetchall()
        if not batch:
            return out
        out.extend(batch)
        last_id = batch[-1]["tg_id"]


async def _onboard_start_at(db, tg_id: int) -> datetime | None:
    """Момент входа в цепочку — самое первое событие start."""
    cur = await db.execute(
        "SELECT MIN(created_at) at FROM events "
        "WHERE tg_id=:tg_id AND name='start'", {"tg_id": tg_id})
    row = await cur.fetchone()
    if not row or not row["at"]:
        return None
    try:
        return datetime.fromisoformat(row["at"])
    except (TypeError, ValueError):
        return None


async def _onboard_chain(bot, db, user, now_utc: datetime) -> None:
    """O1 (день 1) и O2 (день 3) — затем сегмент заморожен навсегда.

    Заморозка держится на дедупе kind+key в deliveries: O2 уходит ровно один
    раз, новых шагов у цепочки нет (урок BUS-124 — не преследуем неактивиро-
    ванных). Fail-closed: даже прямой вызов цепочки не шлёт, если onboarded=1.
    """
    tg_id = user["tg_id"]
    if user.get("onboarded"):
        return
    start_at = await _onboard_start_at(db, tg_id)
    if start_at is None:
        return
    elapsed = now_utc - start_at
    lang = _user_lang(user)

    # O2 — финальное: после него касаний больше не планируется никаких.
    if elapsed >= ONBOARD_D3_DELAY:
        if await comms.already_sent(db, tg_id, "onboard_nudge", f"d3:{tg_id}"):
            return
        template = await content.get_text(db, "copy", "onboard_d3",
                                          default="", lang=lang)
        if not template:
            log.warning("onboard: нет шаблона copy/onboard_d3 — пропуск")
            return
        await _send_once(bot, db, tg_id, "onboard_nudge",
                         f"d3:{tg_id}", template)
        return

    if elapsed >= ONBOARD_D1_DELAY:
        if await comms.already_sent(db, tg_id, "onboard_nudge", f"d1:{tg_id}"):
            return
        template = await content.get_text(db, "copy", "onboard_d1",
                                          default="", lang=lang)
        if not template:
            log.warning("onboard: нет шаблона copy/onboard_d1 — пропуск")
            return
        markup = None
        if settings.webapp_url:
            from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
            btn_label = await content.get_text(db, "copy", "onboard_btn_continue",
                                               default="", lang=lang)
            markup = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(
                    text=btn_label or ("✨ Continue" if lang == "en"
                                       else "✨ Продолжить"),
                    web_app=WebAppInfo(url=settings.webapp_url)),
            ]])
        await _send_once(bot, db, tg_id, "onboard_nudge",
                         f"d1:{tg_id}", template, markup=markup)


# ─────────────── реактивация спящих R1-R2 (BUS-260, §3) ──────────────────────

#: Окно входа в спячку: последняя активность 14–21 день назад. Свежее 14д —
#: «только что уснул, не трогаем» (дизайн §3).
REACTIVATE_MIN_SLEEP = timedelta(days=14)
REACTIVATE_MAX_SLEEP = timedelta(days=21)
#: R2 — через 7 дней после R1 при отсутствии ответа.
REACTIVATE_R2_DELAY = timedelta(days=7)
#: Повторный вход в цепочку после отработанного цикла — не раньше 60 дней
#: (дизайн §3: «возврат в сегмент возможен не ранее чем через 60 дней»).
REACTIVATE_COOLDOWN = timedelta(days=60)
#: Верхняя граница отбора: R2 уходит на r1+7д, т.е. до 28-го дня сна; после
#: 28д цепочка завершена, юзер вне досягаемости до новой активности.
REACTIVATE_AUDIENCE_MAX_SLEEP = timedelta(days=28)
#: Ключ setting с датой последнего суточного прогона (идемпотентность sweep).
REACTIVATE_LAST_RUN_KEY = "crm.reactivate_last_run"


#: Ключ setting для суточного пробега отзыва refund/chargeback (BUS-376).
_REFUND_REVOKE_LAST_RUN_KEY = "billing.refund_revoke_last_run"


async def _revoke_audience(db) -> list[dict]:
    """Paid orders queued for entitlement revoke by full refund/chargeback.

    Returns the most recent queued order per user. The sweep processes
    each user once per day.
    """
    rows = []
    cur = await db.execute(
        "SELECT o.tg_id, o.id AS order_id, o.sku, o.paid_at, o.meta_json, "
        "u.name, u.lang, u.sub_until "
        "FROM orders o "
        "JOIN users u ON u.tg_id=o.tg_id "
        "WHERE o.status='refund_pending' "
        "AND o.tg_id IS NOT NULL "
        f"AND {not_synthetic_tg_sql('o')} "
        "AND o.meta_json LIKE :flag "
        "AND o.paid_at IS NOT NULL "
        "ORDER BY o.paid_at DESC",
        {"flag": '%"revoke_pending": true%'})
    seen: set[int] = set()
    for row in await cur.fetchall():
        tg_id = int(row["tg_id"])
        if tg_id in seen:
            continue
        seen.add(tg_id)
        rows.append(dict(row))
    return rows


async def _revoke_entitlement(bot, db, user: dict, now_utc: datetime) -> None:
    """Revoke subscription for a user queued by full refund/chargeback.

    Fail-closed: only runs when the order was explicitly flagged
    (meta_json.revoke_pending=True). Idempotent: calling again after
    completion is a no-op because the order is already 'refunded'.
    """
    tg_id = int(user["tg_id"])
    lang = _user_lang(user)
    name = user["name"] or ("dear one" if lang == "en" else "друг")
    order_id = user["order_id"]

    completed = await complete_refund_revoke(db, order_id, tg_id=tg_id)
    if not completed:
        return
    await analytics.track(db, analytics.E_REFUND_COMPLETED, tg_id,
                          props={"order_id": order_id,
                                 "plan": user.get("sku"),
                                 "reason": "provider_refund",
                                 "provider": "paddle"},
                          surface="web")
    template = await content.get_text(
        db, "copy", "refund_revoke",
        ("🌙 {name}, your subscription has been closed following a full "
         "refund. I have kept everything you shared — return whenever you "
         "are ready." if lang == "en" else
         "🌙 {name}, подписка закрыта по полному возврату. Я сохранила "
         "всё, что ты мне рассказывала — возвращайся, когда будешь готова."),
        lang=lang)
    text = template.replace("{name}", name)
    await _send_once(bot, db, tg_id, "refund_revoke",
                     user.get("sub_until") or str(order_id), text)


async def _reactivate_audience(db, now_utc: datetime) -> list:
    """Спящие с push, вошедшие в спячку 14-28 день назад.

    Отбор не по композитному сегменту `sleeping_14d_push` (его предикат —
    last_seen < 14д, без верхней границы): окно «14-21 день» — точка входа
    в спячку для R1, а R2 уходит до 28-го дня сна — обе ветки держит один
    отбор с верхней границей 28д. onboarded=1: «спящий» — тот, кто был
    активен и уснул; неонбордингнутых цепочка не трогает (их канал —
    onboard-дожим §2). active и morning_push=1 — из композита.
    Курсор по tg_id (патиция AUDIENCE_CAP) — как в welcome/onboard.
    """
    sleep_from = (now_utc - REACTIVATE_AUDIENCE_MAX_SLEEP).isoformat()
    sleep_to = (now_utc - REACTIVATE_MIN_SLEEP).isoformat()
    out: list = []
    last_id = 0
    while True:
        cur = await db.execute(
            "SELECT * FROM users WHERE status='active' AND onboarded=1 "
            "AND morning_push=1 AND last_seen IS NOT NULL "
            "AND last_seen >= :sleep_from AND last_seen < :sleep_to "
            "AND tg_id>:last_id "
            f"AND {not_synthetic_tg_sql('users')} "
            f"ORDER BY tg_id LIMIT {AUDIENCE_CAP}",
            {"sleep_from": sleep_from, "sleep_to": sleep_to, "last_id": last_id})
        batch = await cur.fetchall()
        if not batch:
            return out
        out.extend(batch)
        last_id = batch[-1]["tg_id"]


async def _reactivate_last_practice(db, user) -> tuple[str, int] | None:
    """Последняя незавершённая практика: (title, day_index) для R1.

    Паттерн practice_reminder: первый элемент started и не finished из
    list_for_user (идущие — первыми). list_for_user отдаёт title из каталога
    (практики хранят только code). Нет незавершённой практики — None.
    """
    try:
        items = await practices_svc.list_for_user(db, user)
    except Exception as e:  # noqa: BLE001
        log.warning("reactivate: каталог практик недоступен: %s", type(e).__name__)
        return None
    running = [p for p in items if p["started"] and not p["finished"]]
    if not running:
        return None
    item = running[0]
    return item["title"], int(item["day_index"] or 0)


async def _reactivate_fresh_last_seen(db, tg_id: int):
    """Текущий last_seen из БД — двойной стоп: юзер мог вернуться,
    пока sweep идёт по партии (аудитория снимается один раз в начале)."""
    cur = await db.execute(
        "SELECT last_seen FROM users WHERE tg_id=:tg_id", {"tg_id": tg_id})
    row = await cur.fetchone()
    if not row or not row["last_seen"]:
        return None
    try:
        return datetime.fromisoformat(row["last_seen"])
    except (TypeError, ValueError):
        return None


async def _reactivate_delivery_at(db, tg_id: int, key: str):
    """Момент доставки R1/R2 из deliveries — точка отсчёта R2 (+7д)."""
    cur = await db.execute(
        "SELECT created_at FROM deliveries "
        "WHERE tg_id=:tg_id AND kind=:kind AND key=:key "
        "AND status IN ('sent','forbidden')",
        {"tg_id": tg_id, "kind": "reactivate", "key": key})
    row = await cur.fetchone()
    if not row or not row["created_at"]:
        return None
    try:
        return datetime.fromisoformat(row["created_at"])
    except (TypeError, ValueError):
        return None


async def _reactivate_recent_touch(db, tg_id: int, now_utc: datetime) -> bool:
    """Было ли касание reactivate за последние 60 дней (любой шаг).

    Проверка «возврат в сегмент не ранее чем через 60 дней» (§3): после
    отработанного цикла (в т.ч. только R1-fallback) новый цикл не раньше,
    чем через 60 дней. Continuous sleep отдельной проверки не требует:
    key от даты входа в спячку неизменен, дедуп не пустит повтор.
    """
    cutoff = (now_utc - REACTIVATE_COOLDOWN).isoformat()
    cur = await db.execute(
        "SELECT 1 FROM deliveries WHERE tg_id=:tg_id AND kind='reactivate' "
        "AND created_at >= :cutoff LIMIT 1",
        {"tg_id": tg_id, "cutoff": cutoff})
    return await cur.fetchone() is not None


async def _reactivate_chain(bot, db, user, now_utc: datetime) -> None:
    """R1 (вход в спячку 14-21д) → R2 (+7д без ответа) → жёсткий стоп.

    «Ответ» на касание — активность юзера (last_seen обновляется touch() на
    любом сообщении/запросе Mini App). Проверять её по events НЕЛЬЗЯ: спящие
    с morning_push=1 получают утренний push-прогноз ежедневно, и каждый
    system-push пишет E_FORECAST — events после R1 есть всегда. Поэтому
    ответ = fresh last_seen из БД, новее точки отсчёта.

    Дедуп kind+key в deliveries — держатель истории: key = месяц даты входа
    в спячку (last_seen), не текущий месяц — иначе повторный вход в сегмент
    в новом месяце дал бы повторную отправку (постановка BUS-260 п.4;
    при непрерывном сне last_seen не меняется → key неизменен → повтора
    нет ни через месяц, ни когда-либо).

    Персонализация R1: последняя незавершённая практика. Если её нет —
    fallback без персонализации: текст reactivate_r2 (утверждённый каркас
    «другого типа ценности», копирайт BUS-263 §6) уходит ОДИН раз под
    ключом r1, и цикл на этом завершён — R2 не шлём, чтобы не дублировать
    тот же текст. Разделение в R2-ветке — по наличию незавершённой практики
    (за время сна состояние практик не меняется: юзер неактивен).

    Стоп после R2 жёсткий (урок BUS-124): новых шагов нет; юзер выходит из
    отбора на 28-й день сна, а новый цикл начинается только после 60 дней
    с последнего касания (_reactivate_recent_touch).
    """
    tg_id = user["tg_id"]
    lang = _user_lang(user)
    name = user["name"] or ("dear one" if lang == "en" else "друг")

    last_seen = user.get("last_seen")
    if not last_seen:
        return
    try:
        seen_at = datetime.fromisoformat(last_seen)
    except (TypeError, ValueError):
        return
    sleep_days = now_utc - seen_at

    r1_key = f"r1:{seen_at.strftime('%Y-%m')}"
    r2_key = f"r2:{seen_at.strftime('%Y-%m')}"

    r1_sent_at = await _reactivate_delivery_at(db, tg_id, r1_key)
    if r1_sent_at is None:
        # Новый цикл: спим в окне [14, 21) дней от входа в спячку.
        if not (REACTIVATE_MIN_SLEEP <= sleep_days < REACTIVATE_MAX_SLEEP):
            return
        # Возврат в сегмент не раньше чем через 60 дней после прошлого цикла.
        if await _reactivate_recent_touch(db, tg_id, now_utc):
            return
        # Двойной стоп: вернулся, пока sweep шёл по партии.
        fresh = await _reactivate_fresh_last_seen(db, tg_id)
        if fresh and fresh > seen_at:
            return
        # Guardrail 1/7д (BUS-262): R1 — маркетинговое касание, слот недели.
        if not await _guardrail_ok(db, tg_id, now_utc):
            return
        template = await content.get_text(db, "copy", "reactivate_r1",
                                          default="", lang=lang)
        if not template:
            log.warning("reactivate: нет шаблона copy/reactivate_r1 — пропуск")
            return
        personal = await _reactivate_last_practice(db, user)
        if personal:
            title, day_index = personal
            text = (template
                    .replace("{name}", name)
                    .replace("{practice_title}", title)
                    .replace("{day_index}", str(day_index)))
            if await _send_once(bot, db, tg_id, "reactivate", r1_key, text):
                await _mark_guardrail(db, tg_id, now_utc)
        else:
            # Fallback-каркас без персонализации (утверждённый текст r2).
            fallback = await content.get_text(db, "copy", "reactivate_r2",
                                              default="", lang=lang)
            if not fallback:
                log.warning("reactivate: нет шаблона copy/reactivate_r2 "
                            "для fallback — пропуск")
                return
            text = fallback.replace("{name}", name)
            # Fallback идёт под отдельным ключом: R2 за ним не follows —
            # «другая ценность» уже доставлена, дубль не нужен.
            if await _send_once(bot, db, tg_id, "reactivate",
                                f"{r1_key}:fallback", text):
                await _mark_guardrail(db, tg_id, now_utc)
        return

    # R1 ушёл. R2: +7 дней после R1, ответа (last_seen newer R1) нет.
    if now_utc - r1_sent_at < REACTIVATE_R2_DELAY:
        return
    # 60д-стоп для нового цикла уже отработан на R1; R2 — продолжение.
    # R1 был fallback (без практики) — R2 не шлём (дубль «другой ценности»).
    if await _reactivate_delivery_at(db, tg_id, f"{r1_key}:fallback"):
        return
    fresh = await _reactivate_fresh_last_seen(db, tg_id)
    if fresh and fresh > r1_sent_at:
        return  # ответил на R1 — цепочка свою работу сделала
    # R2 уходит только если R1 был персональным (запись без :fallback).
    r2_sent_at = await _reactivate_delivery_at(db, tg_id, r2_key)
    if r2_sent_at is not None:
        return
    template = await content.get_text(db, "copy", "reactivate_r2",
                                      default="", lang=lang)
    if not template:
        log.warning("reactivate: нет шаблона copy/reactivate_r2 — пропуск")
        return
    text = template.replace("{name}", name)
    # R2 шлётся минимум через 7д после R1 → новая ISO-неделя, guardrail
    # свободен; проверка на месте для симметрии с welcome_chain и на случай
    # будущих изменений REACTIVATE_R2_DELAY.
    if not await _guardrail_ok(db, tg_id, now_utc):
        return
    if await _send_once(bot, db, tg_id, "reactivate", r2_key, text):
        await _mark_guardrail(db, tg_id, now_utc)



# ────────────────────── общий суточный sweep (BUS-190 §2) ─────────────────────

async def _daily_sweep_due(db, key: str, now_utc: datetime) -> bool:
    """True — раз в сутки: суточные отборы не должны жить в почасовом тике.

    Отметка дня пишется до отбора: повтор в тот же день исключён даже при
    падении между отметкой и отправкой (дубли касаний всё равно исключает
    _send_once по deliveries). setting-ключи: crm.welcome_last_run и далее
    crm.onboard_last_run / crm.reactivate_last_run (задачи 3.4/3.5).
    """
    today = now_utc.strftime("%Y-%m-%d")
    if await content.get_setting(db, key) == today:
        return False
    await content.set_setting(db, key, today)
    return True


async def _daily_sweeps(bot, db, now_utc: datetime) -> None:
    """Суточные CRM-цепочки вне почасовых сценариев (welcome, onboard 3.4, 3.5).

    Каждая цепочка имеет собственную отметку дня: сбой/пропуск одной не глушит
    остальные (BUS-190 §0 — expand-migrate-contract).
    """
    if now_utc.hour != WELCOME_SWEEP_HOUR:
        return

    # Welcome-цепочка (BUS-258 §1) — независимая отметка дня.
    if await _daily_sweep_due(db, WELCOME_LAST_RUN_KEY, now_utc):
        for user in await _welcome_audience(db, now_utc):
            try:
                await _welcome_chain(bot, db, user, now_utc)
            except Exception as e:  # noqa: BLE001
                log.warning("ошибка welcome-цепочки: %s", type(e).__name__)
            await asyncio.sleep(BATCH_PAUSE)

    # Onboarding-дожим (BUS-259 §2): сегмент вне _audience, отбор по start.
    if await _daily_sweep_due(db, ONBOARD_LAST_RUN_KEY, now_utc):
        for user in await _onboard_audience(db, now_utc):
            try:
                await _onboard_chain(bot, db, user, now_utc)
            except Exception as e:  # noqa: BLE001
                log.warning("ошибка onboard-цепочки: %s", type(e).__name__)
            await asyncio.sleep(BATCH_PAUSE)

    # Реактивация спящих R1-R2 (BUS-260 §3): окно входа в спячку 14-21 день.
    if await _daily_sweep_due(db, REACTIVATE_LAST_RUN_KEY, now_utc):
        for user in await _reactivate_audience(db, now_utc):
            try:
                await _reactivate_chain(bot, db, user, now_utc)
            except Exception as e:  # noqa: BLE001
                log.warning("ошибка reactivate-цепочки: %s", type(e).__name__)
            await asyncio.sleep(BATCH_PAUSE)


# ─────────────────────────── free→paid по событию (BUS-257 §5) ───────────────

async def _crm_free_paid(bot, db, user, now_utc: datetime) -> None:
    """post_limit (+24ч после limit_reached) и low_balance (<1ч).

    Оба канала — событийные, вне guardrail 1/7д. Между собой разводим:
    если post_limit ушёл сегодня, low_balance переносится на завтра
    (требование BUS-190 §5).
    """
    if users.sub_active(user):
        return
    today_start = now_utc.strftime("%Y-%m-%d") + "T00:00:00+00:00"
    tg_id = user["tg_id"]
    lang = _user_lang(user)
    name = user["name"] or ("dear one" if lang == "en" else "друг")

    # ── post_limit: последний limit_reached 24–48ч назад, покупки после него нет ──
    cur = await db.execute(
        "SELECT MAX(created_at) last_limit FROM events "
        "WHERE tg_id=:tg_id AND name='limit_reached'",
        {"tg_id": tg_id})
    row = await cur.fetchone()
    last_limit = row["last_limit"] if row else None
    if last_limit:
        try:
            limit_dt = datetime.fromisoformat(last_limit)
        except (TypeError, ValueError):
            limit_dt = None
        if limit_dt and timedelta(hours=24) <= now_utc - limit_dt < timedelta(hours=48):
            event_date = limit_dt.strftime("%Y-%m-%d")
            # покупки после лимита — стоп
            cur = await db.execute(
                "SELECT 1 FROM events WHERE tg_id=:tg_id "
                "AND name IN ('payment_success','credit_pack_paid') "
                "AND created_at > :since LIMIT 1",
                {"tg_id": tg_id, "since": last_limit})
            if not await cur.fetchone():
                # 7д стоп поканальный: не чаще раза в 7 дней
                cutoff_7d = (now_utc - timedelta(days=7)).isoformat()
                cur = await db.execute(
                    "SELECT 1 FROM deliveries WHERE tg_id=:tg_id AND kind='post_limit' "
                    "AND created_at >= :cutoff_7d LIMIT 1",
                    {"tg_id": tg_id, "cutoff_7d": cutoff_7d})
                if await cur.fetchone():
                    pass
                elif await comms.already_sent(db, tg_id, "post_limit", event_date):
                    pass
                else:
                    template = await content.get_text(
                        db, "copy", "post_limit", default="", lang=lang)
                    if template:
                        text = template.replace("{name}", name)
                        if await _send_once(bot, db, tg_id, "post_limit", event_date, text):
                            await analytics.track(
                                db, analytics.E_POST_LIMIT, tg_id, surface="system")

    # ── low_balance: credit_balance_low <1ч назад, покупок после нет, post_limit не сегодня ──
    cur = await db.execute(
        "SELECT MAX(created_at) last_low FROM events "
        "WHERE tg_id=:tg_id AND name='credit_balance_low'",
        {"tg_id": tg_id})
    row = await cur.fetchone()
    last_low = row["last_low"] if row else None
    if last_low:
        try:
            low_dt = datetime.fromisoformat(last_low)
        except (TypeError, ValueError):
            low_dt = None
        if low_dt and now_utc - low_dt < timedelta(hours=1):
            event_date = low_dt.strftime("%Y-%m-%d")
            # post_limit ушёл сегодня — переносим на следующий день
            if await comms.sent_since(db, tg_id, "post_limit", today_start):
                return
            # покупки после low_balance — стоп
            cur = await db.execute(
                "SELECT 1 FROM events WHERE tg_id=:tg_id "
                "AND name IN ('payment_success','credit_pack_paid') "
                "AND created_at > :since LIMIT 1",
                {"tg_id": tg_id, "since": last_low})
            if await cur.fetchone():
                return
            # 7д стоп поканальный
            cutoff_7d = (now_utc - timedelta(days=7)).isoformat()
            cur = await db.execute(
                "SELECT 1 FROM deliveries WHERE tg_id=:tg_id AND kind='low_balance' "
                "AND created_at >= :cutoff_7d LIMIT 1",
                {"tg_id": tg_id, "cutoff_7d": cutoff_7d})
            if await cur.fetchone():
                return
            if await comms.already_sent(db, tg_id, "low_balance", event_date):
                return
            template = await content.get_text(
                db, "copy", "low_balance", default="", lang=lang)
            if not template:
                return
            text = template.replace("{name}", name)
            if await _send_once(bot, db, tg_id, "low_balance", event_date, text):
                await analytics.track(
                    db, analytics.E_LOW_BALANCE_SENT, tg_id, surface="system")


async def _guardrail_ok(db, tg_id: int, now_utc: datetime) -> bool:
    """Guardrail 1/7д: не более одной маркетинговой коммуникации в неделю.

    Ключ недели — ISO '%G-W%V' (как _weekly_report). Событийные сообщения
    (winback2, post_limit, low_balance) — вне лимита, но разводятся
    между собой по дням через comms.already_sent по kind+event_date.

    True — можно отправить маркетинговое (welcome_chain, reactivate).
    """
    week_key = now_utc.strftime("%G-W%V")
    return not await comms.already_sent(db, tg_id, "guardrail", week_key)


async def _mark_guardrail(db, tg_id: int, now_utc: datetime) -> None:
    """Резервирует guardrail-слот на неделю."""
    week_key = now_utc.strftime("%G-W%V")
    async with transaction(db):
        await db.execute(
            "INSERT INTO deliveries(tg_id, kind, key, created_at) "
            "VALUES(:tg_id, 'guardrail', :key, :created_at) "
            "ON CONFLICT (tg_id, kind, key) DO NOTHING",
            {"tg_id": tg_id, "key": week_key, "created_at": utcnow()})


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


async def _feedback_survey(bot, db, user, now_utc: datetime) -> None:
    """Day-7 опрос: приглашение на день 7, напоминание на день 10.

    Opt-out — через deliveries kind='feedback_optout' (key=str(tg_id)):
    после этого опрос никогда не отправляется. Напоминание уходит только
    если приглашение уже ушло И ответов ещё нет (feedback_responses).
    """
    tg_id = user["tg_id"]
    if await comms.already_sent(db, tg_id, "feedback_optout", str(tg_id)):
        return
    if not await content.is_on(db, "feedback_survey", tg_id, default=True):
        return
    if not settings.webapp_url:
        return

    try:
        created = datetime.fromisoformat(user["created_at"])
    except (TypeError, ValueError):
        return

    now_user = now_utc.astimezone(users.user_tz(user))
    if now_user.hour < 10 or now_user.hour > 21:
        return

    invite_key = "day7_v1"
    remind_key = "day7_v1_remind"
    sent_invite = await comms.already_sent(db, tg_id,
                                            "feedback_survey", invite_key)
    sent_remind = await comms.already_sent(db, tg_id,
                                           "feedback_survey", remind_key)
    answered = await feedback_repo.get_response(db, tg_id) is not None

    # День 7: приглашение (однократно).
    if not sent_invite and not answered and now_utc >= created + timedelta(days=7):
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
        lang = _user_lang(user)
        name = user["name"] or ("dear one" if lang == "en" else "друг")
        text = await content.get_text(
            db, "copy", "feedback_survey_invite",
            ("{name}, a week with me — time to look back.\n"
             "Tell me how you're finding Oracle — it takes a minute, "
             "and I'll gift you 40 Crystals ✦"
             if lang == "en" else
             "{name}, неделя с нами — время оглянуться 🌙\n"
             "Расскажи, как тебе Оракул — это займёт минуту, "
             "а взамен подарю 40 кристаллов ✦"),
            lang=lang)
        text = text.replace("{name}", name)
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text=await content.get_text(
                    db, "copy", "feedback_btn_webapp",
                    "Answer and get 40 Crystals" if lang == "en"
                    else "Ответить и получить 40 кристаллов",
                    lang=lang),
                web_app=WebAppInfo(url=settings.webapp_url + "/survey"))],
            [InlineKeyboardButton(
                text=await content.get_text(
                    db, "copy", "feedback_btn_later",
                    "Not now" if lang == "en" else "Не сейчас",
                    lang=lang),
                callback_data="feedback_later")],
        ])
        if await _send_once(bot, db, tg_id, "feedback_survey",
                            invite_key, text, markup=markup):
            await analytics.track(
                db, analytics.E_FEEDBACK_SURVEY_SENT, tg_id,
                props={"survey_code": feedback_repo.SURVEY_CODE,
                       "delivery_key": invite_key},
                surface="system")
        return

    # День 10: одно напоминание (только если приглашение ушло, ответов нет,
    # напоминание ещё не уходило и final opt-out не нажимался).
    if not sent_remind and sent_invite and not answered \
            and now_utc >= created + timedelta(days=10):
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
        lang = _user_lang(user)
        name = user["name"] or ("dear one" if lang == "en" else "друг")
        text = await content.get_text(
            db, "copy", "feedback_survey_remind",
            ("{name}, I'm still gathering first-week impressions. "
             "A couple of your minutes = 40 Crystals ✦"
             if lang == "en" else
             "{name}, я всё ещё собираю впечатления о первой неделе. "
             "Твоя пара минут = 40 кристаллов ✦"),
            lang=lang)
        text = text.replace("{name}", name)
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text=await content.get_text(
                    db, "copy", "feedback_btn_webapp",
                    "Answer and get 40 Crystals" if lang == "en"
                    else "Ответить и получить 40 кристаллов",
                    lang=lang),
                web_app=WebAppInfo(url=settings.webapp_url + "/survey"))],
            [InlineKeyboardButton(
                text=await content.get_text(
                    db, "copy", "feedback_btn_never",
                    "Don't ask again" if lang == "en" else "Не спрашивать",
                    lang=lang),
                callback_data="feedback_never")],
        ])
        if await _send_once(bot, db, tg_id, "feedback_survey",
                            remind_key, text, markup=markup):
            await analytics.track(
                db, analytics.E_FEEDBACK_SURVEY_SENT, tg_id,
                props={"survey_code": feedback_repo.SURVEY_CODE,
                       "delivery_key": remind_key},
                surface="system")


async def _tick_user(bot, db, user, now_utc, settings_cache) -> None:
    now = now_utc.astimezone(users.user_tz(user))
    if await content.is_on(db, "daily_push", user["tg_id"], default=True):
        await _morning_forecast(bot, db, user, now, settings_cache)
    if await content.is_on(db, "weekly_report", user["tg_id"], default=True):
        await _weekly_report(bot, db, user, now, settings_cache)
    await _monthly_report(bot, db, user, now, settings_cache)
    await _practice_reminder(bot, db, user, now, settings_cache)
    await _feedback_survey(bot, db, user, now_utc)


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
            await _winback(bot, db, user, now_utc=now_utc)
        except Exception as e:  # noqa: BLE001
            log.warning("ошибка сценария продления: %s", type(e).__name__)
        await asyncio.sleep(BATCH_PAUSE)

    # free→paid по событию (BUS-257 §5): post_limit (+24ч) + low_balance (<1ч)
    for user in await _crm_post_limit_audience(db, now_utc):
        try:
            await _crm_free_paid(bot, db, user, now_utc)
        except Exception as e:  # noqa: BLE001
            log.warning("ошибка free→paid post_limit: %s", type(e).__name__)
        await asyncio.sleep(BATCH_PAUSE)

    for user in await _crm_low_balance_audience(db, now_utc):
        try:
            await _crm_free_paid(bot, db, user, now_utc)
        except Exception as e:  # noqa: BLE001
            log.warning("ошибка free→paid low_balance: %s", type(e).__name__)
        await asyncio.sleep(BATCH_PAUSE)

    # Суточный пробег отзыва refund/chargeback (BUS-376): гасим подписку
    # у пользователей с pending-отзывом от полного возврата Paddle.
    if await _daily_sweep_due(db, _REFUND_REVOKE_LAST_RUN_KEY, now_utc):
        for user in await _revoke_audience(db):
            try:
                await _revoke_entitlement(bot, db, user, now_utc)
            except Exception as e:  # noqa: BLE001
                log.warning("ошибка refund-revoke: %s", type(e).__name__)
            await asyncio.sleep(BATCH_PAUSE)

    # Суточные CRM-цепочки (BUS-258): welcome-дожим вне почасовых сценариев
    try:
        await _daily_sweeps(bot, db, now_utc)
    except Exception as e:  # noqa: BLE001
        log.error("суточные CRM-sweeps: %s", e)

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
