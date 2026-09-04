"""Таро, натальная карта, Матрица, прогноз дня, совместимость, дневник."""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime
from io import BytesIO

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from ..core import agent as agent_core
from ..core import astro, cards, chart_rendering, memory
from ..core import palm as palm_core
from ..core.matrix import compute_matrix
from ..repo import users
from ..services import access, analytics, bot_flows, catalog, referrals
from ..services import chat as chat_svc
from .chat import _deny, _send_long
from .formatting import tg_esc, tg_rich
from .keyboards import back_menu, main_menu, reading_kb, spread_offer_kb, spreads_kb
from .ui import BotStage, begin_status

log = logging.getLogger("oracle.bot.features")
router = Router()

DATE_IN_TEXT = re.compile(r"(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{4})")


class Diary(StatesGroup):
    writing = State()


class Compat(StatesGroup):
    date = State()


class PalmUpload(StatesGroup):
    photo = State()


async def _menu(db, tg_id: int):
    user = await users.get(db, tg_id)
    return main_menu(is_admin=await access.is_admin(db, tg_id),
                     lang="en" if user and user["lang"] == "en" else "ru")


# ───────────────────────────── ПАЛМ-АГЕНТ МИРА ───────────────────────────────

PALM_TOPIC_LABELS = {
    "heart_line": "Линия сердца", "head_line": "Линия головы",
    "life_line": "Линия жизни", "fate_line": "Линия судьбы",
    "sun_line": "Линия Солнца", "relationship_line": "Линии отношений",
    "mounts": "Холмы", "fingers": "Пальцы",
}


@router.callback_query(F.data == "palm")
async def palm_entry(cb: CallbackQuery, state: FSMContext, db):
    await state.set_state(PalmUpload.photo)
    await state.update_data(agent="chiromant")
    await cb.message.answer(
        "✋ <b>Мира · Проводник ладони</b>\n\n"
        "Чтобы разбор был максимально точным, пришли <b>2 фото</b>:\n\n"
        "📷 <b>① Раскрытая ладонь</b> — целиком, от запястья до кончиков пальцев, ладонью к камере.\n"
        "   Видны: линии жизни, головы, сердца, судьбы, холмы и пальцы.\n"
        "📷 <b>② Ладонь ребром</b> — согни пальцы к центру и поверни кисть боком к камере.\n"
        "   Видны: линии отношений, детей и путешествий.\n\n"
        "Для обоих: ровный свет, камера сверху, без бликов, фильтров, украшений и воды на руках.\n"
        "Пришли сначала одно фото — Мира подскажет, если нужен другой ракурс.\n\n"
        "<i>Мира читает только различимые линии: чем яснее кадр, тем точнее разбор.</i>",
        reply_markup=back_menu())
    await cb.answer()


@router.message(PalmUpload.photo, F.photo)
async def palm_photo(message: Message, state: FSMContext, db):
    user = await users.get(db, message.from_user.id)
    status = await begin_status(message, user, BotStage.USING_TOOL,
                                "Мира проверяет качество снимка…" if user["lang"] != "en" else "Mira is checking the photo quality…")
    buf = BytesIO()
    try:
        await message.bot.download(message.photo[-1].file_id, destination=buf)
        result = await palm_core.analyze_and_save(db, user, buf.getvalue(), surface="bot")
    except ValueError as exc:
        await status.set(BotStage.RECOVERABLE_ERROR,
                         "Try a clearer photo" if user["lang"] == "en"
                         else "Проверь кадр и попробуй снова")
        await message.answer(
            f"✋ Не получилось подготовить снимок: {tg_esc(str(exc))}\n\n"
            "Попробуй фото одной ладони целиком при ровном свете.", reply_markup=back_menu())
        return
    except Exception as exc:  # noqa: BLE001
        log.warning("palm photo analysis failed: %s", exc)
        await status.set(BotStage.RECOVERABLE_ERROR, "Try a clearer photo" if user["lang"] == "en" else "Попробуй более чёткий снимок")
        await message.answer("✋ Mira could not finish this reading. Try one clear photo of the whole palm." if user["lang"] == "en" else "✋ Мира пока не смогла завершить чтение. Попробуй ещё раз с более чётким снимком.",
                             reply_markup=back_menu())
        return
    await status.set(BotStage.SUCCESS)
    observations = result.get("observations") or []
    narrative = (result.get("narrative") or "").strip()
    prompts = result.get("interpretive_prompts") or []
    reflection = f"\n\n<b>Вопрос к себе</b>\n{tg_esc(str(prompts[0]))}" if prompts else ""
    safety = "\n\n<i>Это описание видимого в кадре, не диагноз и не прогноз.</i>"
    if result.get("status") == "needs_photo":
        limits = "\n".join(f"• {tg_esc(str(item))}" for item in (result.get("limitations") or [])[:3])
        if narrative:
            text = f"✋ <b>Мира · Карта наблюдений</b>\n\n{tg_esc(narrative)}\n\n<b>Нужен дополнительный кадр</b>\n{limits}{reflection}{safety}"
        else:
            text = f"✋ <b>Мире нужен более ясный кадр</b>\n\n{limits or 'Пересними ладонь целиком при ровном свете.'}{safety}"
    else:
        if narrative:
            text = f"✋ <b>Мира · Карта наблюдений</b>\n\n{tg_esc(narrative)}{reflection}{safety}"
        else:
            rows = []
            for item in observations[:4]:
                label = PALM_TOPIC_LABELS.get(str(item.get("topic") or ""), "Наблюдение")
                confidence = int(round(float(item.get("confidence") or 0) * 100))
                rows.append(f"• <b>{tg_esc(label)}</b> · {confidence}%\n{tg_esc(str(item.get('summary') or 'без описания'))}")
            text = (f"✋ <b>Карта видимых зон от Миры</b>\n\n" +
                    "\n\n".join(rows) + reflection + safety)
    await state.clear()
    await message.answer(text, reply_markup=back_menu())


# ─────────────────────────────── ТАРО ─────────────────────────────────────────

@router.callback_query(F.data == "tarot")
async def tarot_menu(cb: CallbackQuery, db):
    user = await users.get(db, cb.from_user.id)
    spreads = await catalog.spread_list(db, user)
    await cb.message.answer(
        "🎴 <b>Выбери расклад</b>\n\n"
        "<i>Первые три входят в твой доступ. Остальные — большие расклады, "
        "их открывают отдельно.</i>",
        reply_markup=spreads_kb(spreads))
    await cb.answer()


@router.callback_query(F.data.startswith("spread:"))
async def tarot_spread(cb: CallbackQuery, db):
    code = cb.data.split(":", 1)[1]
    user = await users.get(db, cb.from_user.id)
    item = await catalog.get_spread(db, code)

    # платный расклад без права — не отказ, а предложение
    if item["tier"] == "premium" and not await catalog.is_available(db, user, code):
        offer = next((s for s in await catalog.spread_list(db, user)
                      if s["code"] == code), None)
        await cb.answer()
        await cb.message.answer(
            f"{item.get('emoji', '🎴')} <b>{item['title']}</b>\n"
            f"{item.get('hint', '')}\n\n"
            f"Карт в раскладе: {len(item['positions'])}. "
            f"Это большой расклад — он открывается отдельно.",
            reply_markup=spread_offer_kb(offer or {}))
        return

    await cb.answer()
    try:
        drawn = await chat_svc.draw(db, user, code, surface="bot")
    except chat_svc.ChatDenied as e:
        await _deny(cb.message, db, e.verdict)
        return

    cards, positions, title = drawn["cards"], drawn["positions"], drawn["title"]
    revealed = await _animate_reveal(cb.message, title, cards, positions)
    answer = await chat_svc.interpret(db, user, drawn["reading_id"], surface="bot")
    await revealed.edit_text(f"<b>{title}</b>\n\n" + _cards_lines(cards, positions))

    me = await cb.bot.get_me()
    from ..core import cards as cards_renderer
    if cards_renderer.available():
        try:
            image = await asyncio.to_thread(
                cards_renderer.reading_card, title, cards, positions,
                name=user["name"] or "", bot_username=me.username or "",
                seed=drawn["reading_id"],
            )
            if image:
                from aiogram.types import BufferedInputFile
                await cb.message.answer_photo(
                    BufferedInputFile(image, filename=f"oracle-reading-{drawn['reading_id']}.png"),
                    caption="Your reading card" if user["lang"] == "en" else "Карточка твоего расклада",
                )
        except Exception as exc:  # noqa: BLE001
            log.info("bot Tarot visual unavailable: %s", exc)
    link = referrals.link_for(me.username, user["tg_id"])
    share_text = (f"🔮 Мой AI-Оракул разложил «{title}»:\n" +
                  "\n".join(f"{c['emoji']} {c['name']}" for c in cards) +
                  "\n\nОн знает мою натальную карту и помнит всё обо мне ✨ Попробуй:")
    from urllib.parse import quote
    share_url = ("https://t.me/share/url?url=" + quote(link) +
                 "&text=" + quote(share_text))
    await _send_long(cb.message, answer,
                     reply_markup=reading_kb(drawn["reading_id"], share_url,
                                             with_card=cards_renderer.available()))


@router.callback_query(F.data.startswith("card:"))
async def reading_card(cb: CallbackQuery, db):
    """Картинка расклада для сторис — рисуем по сохранённым картам, не заново."""
    import json

    reading_id = int(cb.data.split(":", 1)[1])
    row = await bot_flows.reading(db, reading_id, cb.from_user.id)
    if not row:
        await cb.answer("Расклад не найден", show_alert=True)
        return
    try:
        drawn = json.loads(row["cards_json"] or "[]")
    except ValueError:
        drawn = []
    if not drawn:
        await cb.answer("В раскладе нет карт", show_alert=True)
        return

    await cb.answer("Рисую... 🎨")
    user = await users.get(db, cb.from_user.id)
    spread = await catalog.get_spread(db, row["spread"] or "")
    me = await cb.bot.get_me()
    # отрисовка синхронная и упирается в процессор — уводим в поток
    image = await asyncio.to_thread(
        cards.reading_card, spread["title"], drawn, spread["positions"],
        name=user["name"] or "", bot_username=me.username or "", seed=reading_id)
    if not image:
        await cb.message.answer("Картинка сейчас не собирается — "
                                "поделись ссылкой, она тоже работает 🌙")
        return
    from aiogram.types import BufferedInputFile
    await cb.message.answer_photo(
        BufferedInputFile(image, filename=f"oracle-{reading_id}.png"),
        caption="Сохрани и выложи в сторис ✨")
    await analytics.track(db, "share_card", cb.from_user.id,
                          props={"kind": "reading"})


def _cards_lines(cards: list[dict], positions: list[str]) -> str:
    out = []
    for i, card in enumerate(cards):
        pos = positions[i] if i < len(positions) else f"Карта {i + 1}"
        rev = " ↩️" if card["reversed"] else ""
        out.append(f"{pos}: {card['emoji']} <b>{card['name']}</b>{rev}")
    return "\n".join(out)


async def _animate_reveal(message: Message, title: str, cards: list[dict],
                          positions: list[str]) -> Message:
    """Поочерёдное открытие карт.

    Ожидание здесь — часть ценности: мгновенный ответ читается как «сгенерировано»,
    а пауза — как «раскладывают». Для больших раскладов темп ускоряем, иначе
    двенадцать карт открывались бы полминуты.
    """
    backs = " ".join(["🂠"] * len(cards))
    msg = await message.answer(f"<b>{title}</b>\n\n{backs}\n\n<i>Тасую колоду...</i>")
    await asyncio.sleep(1.1)

    pause = 1.0 if len(cards) <= 4 else 0.45
    step = 1 if len(cards) <= 6 else 2      # длинные расклады открываем парами
    shown: list[str] = []
    for i in range(0, len(cards), step):
        group = cards[i:i + step]
        for j, card in enumerate(group):
            pos = positions[i + j] if i + j < len(positions) else f"Карта {i + j + 1}"
            rev = " ↩️" if card["reversed"] else ""
            shown.append(f"{pos}: {card['emoji']} <b>{card['name']}</b>{rev}")
        rest = " ".join(["🂠"] * (len(cards) - i - len(group)))
        try:
            await msg.edit_text(
                f"<b>{title}</b>\n\n" + "\n".join(shown) +
                (f"\n{rest}" if rest else "") + "\n\n<i>Вглядываюсь в символы...</i>")
        except Exception as e:  # noqa: BLE001
            log.debug("анимация расклада прервана: %s", e)
            break
        await asyncio.sleep(pause)
    return msg


@router.callback_query(F.data.startswith("outcome:"))
async def reading_outcome(cb: CallbackQuery, db):
    """Отметка «сбылось» — обратная связь и доказательство ценности."""
    _, reading_id, outcome = cb.data.split(":", 2)
    ok = await bot_flows.set_reading_outcome(db, int(reading_id), cb.from_user.id, outcome)
    if ok:
        await analytics.track(db, "reading_outcome", cb.from_user.id,
                              props={"outcome": outcome})
        await cb.answer("Спасибо, я запомнила 🌙" if outcome == "came_true"
                        else "Записала. Это помогает мне точнее читать твои карты")
    else:
        await cb.answer("Не получилось отметить")


# ─────────────────────────── МОЯ КАРТА ────────────────────────────────────────

@router.callback_query(F.data == "chart")
async def chart_view(cb: CallbackQuery, db):
    user = await users.get(db, cb.from_user.id)
    chart = users.chart_of(user)
    if not chart:
        await cb.answer("Сначала пройди знакомство: /start", show_alert=True)
        return
    sun = chart["sun"]
    lines = ["🌌 <b>Твоя натальная карта</b>",
             f"{sun['symbol']} Солнце в <b>{sun['sign']}</b> · стихия {sun['element']}"]
    asc = chart.get("ascendant")
    if asc:
        lines.append(f"↗️ Асцендент в <b>{asc['sign']}</b> {asc['deg']}° — "
                     f"каким тебя видят с первого взгляда")
    if not user["birth_time_known"]:
        lines.append("<i>Время рождения неточное — дома и асцендент показываю "
                     "как ориентир.</i>")
    lines.append("")

    if chart.get("planets"):
        for planet in chart["planets"]:
            retro = " ↩️R" if planet.get("retro") else ""
            house = f" · {planet['house']} дом" if planet.get("house") else ""
            lines.append(f"• {planet['name']} в {planet['sign']} "
                         f"{planet['deg']}°{house}{retro}")
        aspects = chart.get("aspects") or []
        if aspects:
            lines.append("\n<b>Главные аспекты:</b>")
            for aspect in aspects[:5]:
                lines.append(f"• {aspect['p1']} {aspect['glyph']} {aspect['p2']} — "
                             f"{aspect['aspect']} (орб {aspect['orb']}°)")
    else:
        lines.append(f"<i>{chart.get('note', '')}</i>")
    lines.append("\nСпроси меня о любой планете или аспекте — расскажу, "
                 "что он значит именно для тебя 💫")
    await cb.answer()
    # Отправляем PDF-разбор вместо маленького колеса
    try:
        from ..pdfgen import builder, render
        pdf = await builder.build_natal_pdf_bytes(db, user)
        from aiogram.types import BufferedInputFile
        await cb.message.answer_document(
            BufferedInputFile(pdf, filename="oracle-natal-chart.pdf"),
            caption="Твой PDF-разбор натальной карты" if user["lang"] != "en" else "Your natal chart PDF report",
        )
    except (render.PdfUnavailable, Exception) as exc:
        log.info("PDF для чата недоступен (%s), отправляю текстовую карту", exc)
        try:
            image, _spec, _cached, _key = await asyncio.to_thread(
                chart_rendering.render_chart_image,
                chart,
                birth_date=user["birth_date"], birth_time=user["birth_time"],
                lat=user["birth_lat"], lon=user["birth_lon"], tz=user["tz"],
                variant="compact", locale="en" if user["lang"] == "en" else "ru",
            )
            from aiogram.types import BufferedInputFile
            await cb.message.answer_photo(
                BufferedInputFile(image, filename="oracle-natal-chart.png"),
                caption="Your natal chart" if user["lang"] == "en" else "Твоя натальная карта",
            )
        except Exception as exc2:  # noqa: BLE001
            log.info("bot chart visual also unavailable: %s", exc2)
    await _send_long(cb.message, "\n".join(lines),
                     reply_markup=back_menu(ask=True))


# ─────────────────────── МАТРИЦА СУДЬБЫ ──────────────────────────────────────

@router.callback_query(F.data == "matrix")
async def matrix_view(cb: CallbackQuery, db):
    user = await users.get(db, cb.from_user.id)
    if not user["birth_date"]:
        await cb.answer("Сначала пройди знакомство: /start", show_alert=True)
        return
    matrix = compute_matrix(user["birth_date"])
    lines = ["🔢 <b>Твоя Матрица Судьбы</b>", ""]
    for item in matrix.values():
        lines.append(f"• {item['title']}: <b>{item['n']} — {item['arcana']}</b>\n"
                     f"  <i>{item['meaning']}</i>")
    lines.append("\nХочешь разбор любой позиции — просто спроси 💫")
    await _send_long(cb.message, "\n".join(lines), reply_markup=back_menu(ask=True))
    await cb.answer()


# ─────────────────────────── ПРОГНОЗ ДНЯ ─────────────────────────────────────

async def _send_today(target: Message, db, tg_id: int) -> None:
    user = await users.get(db, tg_id)
    if not user or not user["onboarded"]:
        await target.answer("Сначала /start 🌙")
        return
    if not users.sub_active(user):
        from .keyboards import limit_kb
        await target.answer(
            "🌘 Прогноз дня входит в подписку. Продли доступ — и я снова буду "
            "встречать тебя утром ✨",
            reply_markup=limit_kb(0, has_crystals=False))
        return
    text = await agent_core.daily_forecast_cached(db, user)
    sky = astro.today_sky()
    card = agent_core.card_of_day(user)
    await analytics.track(db, analytics.E_FORECAST, tg_id, props={"channel": "bot"})

    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    rows = []
    if cards.available():
        rows.append([InlineKeyboardButton(text="🖼 Картинка для сторис",
                                          callback_data="card_today")])
    rows.append([InlineKeyboardButton(text="✨ Гороскоп знака",
                                      callback_data="horoscope")])
    rows.append([InlineKeyboardButton(text="← Меню", callback_data="menu")])
    await target.answer(
        f"{tg_rich(text)}\n\n"
        f"🎴 <b>Карта дня:</b> {card['emoji']} {card['name']} — {card['meaning']}\n"
        f"{sky['moon']['emoji']} {sky['moon']['name']}, "
        f"{sky['moon']['day']}-й лунный день",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(F.data == "card_today")
async def today_card(cb: CallbackQuery, db):
    """Карточка прогноза дня — самый частый повод поделиться утром."""
    user = await users.get(db, cb.from_user.id)
    if not user or not users.sub_active(user):
        await cb.answer("Прогноз входит в подписку", show_alert=True)
        return
    await cb.answer("Рисую... 🎨")
    chart = users.chart_of(user)
    sun = chart.get("sun") or {}
    text = await agent_core.daily_forecast_cached(db, user, chart)
    card = agent_core.card_of_day(user)
    me = await cb.bot.get_me()
    image = await asyncio.to_thread(
        cards.forecast_card, text, sign=sun.get("sign", ""),
        symbol=sun.get("symbol", ""), card_name=card["name"],
        name=user["name"] or "", bot_username=me.username or "",
        day=users.user_today(user))
    if not image:
        await cb.message.answer("Картинка сейчас не собирается 🌙")
        return
    from aiogram.types import BufferedInputFile
    await cb.message.answer_photo(
        BufferedInputFile(image, filename="oracle-today.png"),
        caption="Твоё утро ✨")
    await analytics.track(db, "share_card", cb.from_user.id,
                          props={"kind": "today"})


@router.message(Command("today"))
async def today_cmd(message: Message, db):
    await _send_today(message, db, message.from_user.id)


@router.callback_query(F.data == "today")
async def today_cb(cb: CallbackQuery, db):
    await cb.answer("Смотрю на небо... 🌙")
    await _send_today(cb.message, db, cb.from_user.id)


# ────────────────────────── СОВМЕСТИМОСТЬ ─────────────────────────────────────

@router.callback_query(F.data == "compat")
async def compat_start(cb: CallbackQuery, state: FSMContext, db):
    saved = await bot_flows.partners(db, cb.from_user.id)
    hint = ""
    if saved:
        hint = ("\n\n<i>Уже сохранены: " +
                ", ".join(f"{tg_esc(p['name'])} ({p['birth_date']})" for p in saved[:3]) +
                "</i>")
    await state.set_state(Compat.date)
    await cb.message.answer(
        "💞 Проверим ваши стихии.\n"
        "Напиши <b>дату рождения партнёра</b> (ДД.ММ.ГГГГ), можно с именем:\n"
        "<i>например: 03.11.1996 Дима</i>" + hint)
    await cb.answer()


@router.message(Compat.date, F.text)
async def compat_date(message: Message, state: FSMContext, db):
    match = DATE_IN_TEXT.search(message.text)
    if not match:
        await message.answer("Нужна дата как <b>ДД.ММ.ГГГГ</b> 🙏")
        return
    try:
        partner_date = (f"{int(match.group(3)):04d}-{int(match.group(2)):02d}-"
                        f"{int(match.group(1)):02d}")
        datetime.strptime(partner_date, "%Y-%m-%d")
    except ValueError:
        await message.answer("Такой даты не существует... проверь 🌙")
        return
    await state.clear()

    name = message.text.replace(match.group(0), "").strip()[:30]
    user = await users.get(db, message.from_user.id)
    if not user["birth_date"]:
        await message.answer("Сначала пройди знакомство: /start 🌙")
        return

    from ..core import tool_registry as skills
    from ..services import limits
    data = skills._compat(user["birth_date"], partner_date)
    bar = "▰" * round(data["score"] / 10) + "▱" * (10 - round(data["score"] / 10))
    await message.answer(
        f"💞 <b>Спидометр любви</b>\n\n"
        f"Ты — {data['you']['sign']} ({data['you']['element']})\n"
        f"{tg_esc(name or 'Партнёр')} — {data['partner']['sign']} ({data['partner']['element']})\n\n"
        f"{bar}  <b>{data['score']}/100</b>\n"
        f"<i>{data['verdict']}</i>")
    if cards.available():
        try:
            me = await message.bot.get_me()
            image = await asyncio.to_thread(
                cards.compat_card, you=data["you"], partner=data["partner"],
                total=data["score"], verdict=data["verdict"],
                relation=name or "Партнёр", bot_username=me.username or "",
            )
            if image:
                from aiogram.types import BufferedInputFile
                await message.answer_photo(
                    BufferedInputFile(image, filename="oracle-compatibility.png"),
                    caption="Compatibility snapshot" if user["lang"] == "en" else "Карточка совместимости",
                )
        except Exception as exc:  # noqa: BLE001
            log.info("compatibility visual unavailable: %s", exc)

    verdict = await limits.check(db, user)
    if not verdict.allowed:
        await _deny(message, db, verdict)
        return

    wait = await message.answer("💫 <i>Слушаю, как звучат ваши стихии вместе...</i>")
    if not await limits.consume(db, user, verdict):
        await _deny(message, db, verdict)
        return
    text = await agent_core.interpret_compat(db, user, partner_date, name)
    thread = await bot_flows.astro_thread(db, user["tg_id"])
    await bot_flows.save_exchange(
        db, user["tg_id"], f"Совместимость с {name or 'партнёром'}", text,
        thread_id=thread["id"], agent="astro",
        is_question=limits.counts_toward_limit(verdict))
    if name:
        if bool(user["memory_enabled"]):
            await memory.remember(db, user["tg_id"],
                                  f"Партнёр {name}, дата рождения {partner_date}",
                                  kind="person")
        await bot_flows.add_partner(db, user["tg_id"], name, partner_date)

    try:
        await wait.delete()
    except Exception:  # noqa: BLE001
        pass
    await _send_long(message, text, reply_markup=await _menu(db, message.from_user.id))


# ───────────────────────────── ДНЕВНИК ────────────────────────────────────────

@router.callback_query(F.data == "diary")
async def diary_menu(cb: CallbackQuery, state: FSMContext, db):
    diary = await bot_flows.diary_view(db, cb.from_user.id)
    entries, streak = diary["entries"], diary["streak"]
    user = await users.get(db, cb.from_user.id)
    memory_copy = ("Запишу её в твою книгу и учту в прогнозах."
                   if user and bool(user["memory_enabled"])
                   else "Запись останется в дневнике; память Оракула сейчас на паузе.")
    lines = ["📖 <b>Твой дневник</b>"
             + (f" · стрик {streak} дн. 🔥" if streak >= 2 else ""), ""]
    if entries:
        for entry in entries:
            when = datetime.fromisoformat(entry["created_at"]).strftime("%d.%m")
            lines.append(f"<i>{when}</i> — {tg_esc(entry['text'][:80])}")
    else:
        lines.append("<i>Пока пусто. Первая запись — самая важная.</i>")
    lines.append(f"\n✍️ Напиши, как прошёл твой день — {memory_copy}")
    await state.set_state(Diary.writing)
    await cb.message.answer("\n".join(lines), reply_markup=back_menu())
    await cb.answer()


@router.message(Diary.writing, F.text & ~F.text.startswith("/"))
async def diary_write(message: Message, state: FSMContext, db):
    await state.clear()
    text = message.text.strip()[:1000]
    streak_after = await bot_flows.diary_add(db, message.from_user.id, text)
    user = await users.get(db, message.from_user.id)
    if user and bool(user["memory_enabled"]):
        await memory.remember(db, message.from_user.id, f"Из дневника: {text[:150]}",
                              kind="event")
    await analytics.track(db, "diary_write", message.from_user.id,
                          props={"streak": streak_after})
    tail = (f"\n🔥 Ты пишешь {streak_after} дней подряд — я вижу, как ты меняешься."
            if streak_after >= 3 else "")
    await message.answer(
        f"Записала в твою книгу судьбы 📖✨ Завтра утром учту это в прогнозе.{tail}",
        reply_markup=await _menu(db, message.from_user.id))


# ─────────────────────────── ЛУННЫЙ КАЛЕНДАРЬ ─────────────────────────────────

@router.message(Command("moon"))
async def moon_cmd(message: Message, db):
    from datetime import date, timedelta
    lines = ["🌙 <b>Лунная неделя</b>", ""]
    for i in range(7):
        day = date.today() + timedelta(days=i)
        phase = astro.moon_phase(day)
        mark = "→ " if i == 0 else "   "
        lines.append(f"{mark}{day.strftime('%d.%m')} {phase['emoji']} "
                     f"{phase['name']} — {phase['advice']}")
    lines.append("\n<i>Спроси Астролога, какой день лучше для твоего решения 🌌</i>")
    await message.answer("\n".join(lines),
                         reply_markup=await _menu(db, message.from_user.id))


@router.message(Command("stats"))
async def admin_stats(message: Message, db):
    """Короткая сводка владельцу. Полная аналитика — в веб-панели."""
    role = await access.role(db, message.from_user.id)
    if not role:
        return
    o = (await access.admin_overview(db))['overview']
    await message.answer(
        "📊 <b>Оракул сегодня</b>\n\n"
        f"👥 Клиенток: {o['users_total']} (+{o['users_today']} за сутки)\n"
        f"🔥 Активны: {o['dau']} за день · {o['wau']} за неделю\n"
        f"💫 Живых подписок: {o['subs_active']}\n"
        f"💬 Вопросов за 7 дн: {o['questions_7d']}\n"
        f"🎴 Раскладов всего: {o['readings_total']}\n"
        f"⭐ Stars всего: {o['stars_total']} от {o['payers']} плательщиц\n\n"
        "📊 Воронка, CRM, рассылки и контент — в панели управления "
        "(кнопка в меню).")


@router.message(Command("admin"))
async def admin_panel(message: Message, db):
    """Открыть веб-панель. Доступна только администраторам."""
    role = await access.role(db, message.from_user.id)
    if not role:
        return
    from .keyboards import main_menu
    user = await users.get(db, message.from_user.id)
    kb = main_menu(is_admin=True, lang="en" if user and user["lang"] == "en" else "ru")
    await message.answer("📊 Открываю панель управления…", reply_markup=kb)
