"""Готовые сценарии генерации: прогноз дня, трактовки, разборы, отчёты.

Свободный диалог живёт в `core/agents/` — там агент сам решает, какие инструменты
позвать. Здесь наоборот: сценарии с фиксированной структурой, где карты, планеты
и арканы уже выбраны кодом, а модель только пишет текст. Такое разделение
экономит токены (не нужен tool-use цикл) и делает результат предсказуемым.

Публичное API (используется ботом, Mini App и планировщиком):
    ask_oracle, interpret_reading, daily_forecast_cached, interpret_compat,
    build_report, monthly_report, extract_memory_llm
"""
from __future__ import annotations

import asyncio
import json
import logging
import random
from collections import Counter
from datetime import date, datetime, timedelta, timezone

from ...repo import dialog as dialog_repo
from ...repo import readings as readings_repo
from ...repo import users as users_repo
from .. import agents, astro, chart_interpretation, chart_products, interpretation, llm, memory, shared_context, tarot
from .. import tool_registry as skills
from ..stable import stable_seed

log = logging.getLogger("oracle.agent")


def _gendered(user, feminine: str, masculine: str, neutral: str) -> str:
    """Возвращает русскую форму обращения, сохраняя нейтральный fallback."""
    try:
        gender = user["gender"]
    except (IndexError, KeyError):
        gender = None
    if gender == "f":
        return feminine
    if gender == "m":
        return masculine
    return neutral


def _name_prefix(user) -> str:
    """Формирует безопасное обращение без гендерного имени по умолчанию."""
    return f"{user['name']}, " if user["name"] else ""


def _user_lang(user) -> str:
    """Нормализует язык и поддерживает старые неполные профили."""
    try:
        return user["lang"] if user["lang"] in ("ru", "en") else "ru"
    except (IndexError, KeyError):
        return "ru"


# ---------------------------------------------------------------- вопрос

async def ask_oracle(db, user, question: str, *, agent: str = "oracle",
                     thread_id: int | None = None,
                     allowance_line: str = "",
                     extra_rules: str = "",
                     trace: list[str] | None = None) -> str:
    """Свободный вопрос агенту. Совместимая точка входа для бота и API."""
    return await agents.answer(db, user, question, agent=agent,
                               thread_id=thread_id, allowance_line=allowance_line,
                               extra_rules=extra_rules, trace=trace)


# ---------------------------------------------------------------- таро

async def interpret_reading(db, user, title: str, cards: list[dict],
                            positions: list[str],
                            question: str | None = None) -> str:
    """Трактовка КОНКРЕТНЫХ вытянутых карт (карты выбрал код, не модель).

    `question` — формулировка пользователя «что спросить у карт»: карты отвечают на
    конкретное, и трактовка обязана отталкиваться от вопроса, а не быть
    «про жизнь вообще».
    """
    cards_block = tarot.cards_text(cards, positions)
    spread_code = tarot.spread_by_title(title)["code"]
    ledger = tarot.reading_ledger(cards, spread_code, positions=positions)
    evidence = interpretation.tarot_evidence(
        cards, positions, title=title, question=question,
        combinations=ledger["adjacent_combinations"])
    if llm.enabled():
        try:
            system = await agents.system_for(db, user, agents.get("tarot"),
                                             question=question or "")
            summary = await memory.get_summary(db, user["tg_id"])
            mems = await memory.recall(db, user["tg_id"], question or "", limit=3)
            who_block = ""
            if summary:
                who_block += (
                    memory.untrusted_text_block(
                        "Профиль пользователя (фон, не источник карт расклада)",
                        summary,
                        max_chars=3000,
                    )
                    + "\n"
                )
            if mems:
                who_block += f"{memory.prompt_block(mems)}\n"
            user_msg = (
                f"{await skills.guide(db, 'tarot')}\n\n"
                f"{evidence.as_prompt_block()}\n\n"
                f"{interpretation.generation_rules('tarot')}\n\n"
                f"{who_block}Дай тёплую трактовку расклада «{title}»: сначала разберись "
                "с ролью каждой позиции, затем свяжи карты в один сюжет и ответь на вопрос "
                "пользователя. Не пересказывай справочные значения подряд. Не добавляй карты, "
                "сроки, гарантии или утверждения о мыслях третьего человека как факт."
            )
            feedback = ""
            for attempt in (1, 2):
                text = await llm.complete(system, user_msg + feedback, tier="main",
                                          max_tokens=min(1800, 320 * max(3, len(cards))),
                                          purpose="tarot", tg_id=user["tg_id"], db=db)
                grounding = interpretation.validate_tarot_text(text, cards, tarot.DECK)
                if len(text.strip()) >= 120 and grounding.ok:
                    return text
                if attempt == 2:
                    break
                log.info("tarot grounding rejected (attempt=%d): %s",
                         attempt, "; ".join(grounding.issues) or "короткий ответ")
                feedback = (
                    "\n\nПОВТОРНАЯ ГЕНЕРАЦИЯ: предыдущая трактовка не прошла проверку "
                    "фактов расклада." + (" Проблемы: " + "; ".join(grounding.issues) + "."
                                          if grounding.issues else " Ответ был слишком коротким.")
                    + " Напиши трактовку заново: разбирай ТОЛЬКО выпавшие карты и позиции "
                    "из списка, не добавляй не выпавшие карты, сроки или гарантии.")

        except Exception as e:  # noqa: BLE001
            log.warning("трактовка расклада ушла в офлайн: %s", e)
    return _reading_offline(user, title, cards, cards_block, question)


def _reading_offline(user, title: str, cards: list[dict], cards_block: str,
                     question: str | None = None) -> str:
    prefix = _name_prefix(user)
    key = cards[len(cards) // 2]
    reversed_note = ("Перевёрнутые карты просят не торопиться. "
                     if any(c["reversed"] for c in cards) else "")
    q_line = f"\n\nТвой вопрос: «{question}»." if question else ""
    return (
        f"🎴 <b>{title}</b>\n\n{cards_block}{q_line}\n\n"
        f"{prefix}опорная карта этого расклада — {key['emoji']} <b>{key['name']}</b>: "
        f"{key['meaning']}. Прочитай её не как приговор, а как тему, которую стоит "
        f"заметить в текущей ситуации. {reversed_note}"
        "Сделай один маленький шаг: запиши, где эта тема уже проявилась сегодня и "
        "какой выбор остаётся в твоей власти. 🌙"
    )


# ---------------------------------------------------------------- прогноз дня

#: Генерация прогноза — LLM-вызов; Mini App и бот могут спросить прогноз на
#: одно утро одновременно. Замок по (event loop, пользователь, день, язык):
#: второй ждущий после замка перепроверяет кэш и берёт готовый текст, не
#: генерируя дубликат. Привязка к loop обязательна: asyncio.Lock нельзя
#: безопасно ожидать из нового loop после тестового/серверного перезапуска.
_forecast_locks: dict[tuple[int, int, str, str], asyncio.Lock] = {}


async def daily_forecast_cached(db, user, chart: dict | None = None) -> str:
    """Прогноз дня — один раз в сутки для пользователя и языка.

    Без кэша каждое открытие Mini App заново оплачивало бы генерацию и показывало
    другой прогноз на тот же день; бот и приложение обязаны говорить одно и то же.
    """
    day = users_repo.user_today(user)
    lang = _user_lang(user)
    cached = await readings_repo.get_forecast(db, user["tg_id"], day, lang=lang)
    if cached:
        return cached
    loop_id = id(asyncio.get_running_loop())
    if len(_forecast_locks) > 5000:
        # Не сбрасываем живые локи: иначе одновременно запущенные запросы могут
        # пройти через разные замки и оплатить два LLM-вызова. Убираем только
        # неактивные ключи прошлого дня или другого event loop.
        for key, candidate in list(_forecast_locks.items()):
            if (key[0] != loop_id or key[2] != day) and not candidate.locked():
                _forecast_locks.pop(key, None)
    lock_key = (loop_id, user["tg_id"], day, lang)
    lock = _forecast_locks.setdefault(lock_key, asyncio.Lock())
    async with lock:
        cached = await readings_repo.get_forecast(db, user["tg_id"], day, lang=lang)
        if cached:
            return cached
        text = await daily_forecast(db, user, chart if chart is not None
                                   else users_repo.chart_of(user))
        await readings_repo.save_forecast(db, user["tg_id"], day, text, lang=lang)
        await shared_context.record_recommendation(
            db, user, agent="oracle", text=text, source_ref=f"forecast:{day}"
        )
        return text


async def daily_forecast(db, user, chart: dict) -> str:
    sky = astro.today_sky()
    if llm.enabled():
        try:
            system = await agents.system_for(
                db, user, agents.get("oracle"), question="прогноз дня",
                extra_rules=(
                    "Для прогноза используй только переданное детерминированное небо и карту дня; "
                    "при конфликте дат не выбирай победителя, а опирайся на канонический снимок."
                ),
            )
            card = card_of_day(user)
            sphere_title, sphere_hint = _sphere_slot(user)
            moon = sky["moon"]
            user_msg = (f"Небо сегодня: Луна {moon['emoji']} {moon['name']} "
                        f"({moon['advice']}), лунный день ~{moon['day']}, Солнце в "
                        f"{sky['sun_season']['sign']}.\n"
                        f"Карта дня: {card['emoji']} {card['name']}"
                        f"{' (перевёрнутая)' if card['reversed'] else ''} — "
                        f"{card['meaning']}.\n"
                        f"Сфера внимания сегодня: {sphere_title} — {sphere_hint}.\n"
                        f"Напиши мою персональную утреннюю карточку на сегодня, "
                        f"4-6 строк, тепло и по-человечески: обыграй карту дня, "
                        f"отметь лунный день, один конкретный совет завяжи на "
                        f"сферу внимания. Начни с 🌅, обратись ко мне по имени.")
            feedback = ""
            for attempt in (1, 2):
                text = await llm.complete(system, user_msg + feedback, tier="lite",
                                          max_tokens=400, purpose="forecast",
                                          tg_id=user["tg_id"], db=db)
                if text.strip() and len(text.strip()) >= 120:
                    return text
                log.info("прогноз дня отклонён quality gate: attempt=%d len=%d",
                         attempt, len(text.strip()))
                feedback = ("\n\nПОВТОРНАЯ ГЕНЕРАЦИЯ: предыдущий текст был пустым "
                            "или обрывком. Напиши полную утреннюю карточку: 4-6 строк, "
                            "с картой дня, лунным днём и советом по сфере внимания.")
        except Exception as e:  # noqa: BLE001
            log.warning("прогноз дня ушёл в офлайн: %s", e)
    return _forecast_offline(user, chart, sky)


def _forecast_offline(user, chart: dict, sky: dict) -> str:
    """Надёжный локализованный запасной прогноз без вызова модели."""
    rnd = random.Random(stable_seed(date.today().isoformat(), user["tg_id"]))
    moon = sky["moon"]
    card = card_of_day(user)
    if _user_lang(user) == "en":
        prefix = f"{user['name']}, " if user["name"] else ""
        moods = ["clarity", "quiet strength", "meaningful signs", "a conscious choice",
                 "giving and receiving"]
        direction = ("Take the softer route today: slow down and leave room to adjust."
                     if card["reversed"] else
                     "Make one brave, practical move while your energy is fresh.")
        return (
            f"🌅 {prefix}good morning. Today invites {rnd.choice(moods)}.\n"
            f"{moon['emoji']} Let your feelings inform you, but keep your footing in what is real.\n"
            f"Your card of the day is {card['emoji']} — notice what it reflects back to you.\n"
            f"{direction}\n"
            "Come back this evening for a deeper reading. ✨"
        )

    sun = (chart or {}).get("sun") or {}
    sign = sun.get("sign", "твоего знака")
    sign_for = {
        "Овен": "Овна", "Телец": "Тельца", "Близнецы": "Близнецов",
        "Рак": "Рака", "Лев": "Льва", "Дева": "Девы",
        "Весы": "Весов", "Скорпион": "Скорпиона", "Стрелец": "Стрельца",
        "Козерог": "Козерога", "Водолей": "Водолея", "Рыбы": "Рыб",
    }.get(sign, sign)
    prefix = _name_prefix(user)
    sphere_title, _hint = _sphere_slot(user)
    moods = ["день ясности", "день тихой силы", "день знаков", "день выбора",
             "день отдачи"]
    rev = ("Карта идёт перевёрнутой — сегодня мягче, без гонки и лишних решений."
           if card["reversed"] else
           "Карта прямого хода — смелый шаг в первой половине дня принесёт больше.")
    return (
        f"🌅 {prefix}доброе утро! Сегодня для {sign_for} — {rnd.choice(moods)}.\n"
        f"{moon['emoji']} Луна {moon['name']} (~{moon['day']} лунный день): "
        f"{moon['advice']}.\n"
        f"Карта дня: {card['emoji']} <b>{card['name']}</b> — {card['meaning']}.\n"
        f"Зона внимания — <b>{sphere_title}</b>. {rev}\n"
        f"Загляни вечером — разложу карты подробнее. ✨"
    )


def card_of_day(user) -> dict:
    """Карта дня: детерминирована датой и клиенткой — одна в боте и в Mini App.

    Перевёрнутость тоже имитирует честную тасовку (~50/50), но сохраняет
    стабильность для одного дня: клиентка видит ту же карту утром и вечером.
    """
    rnd = random.Random(stable_seed(users_repo.user_today(user), user["tg_id"]))
    card = dict(tarot.DECK[rnd.randrange(len(tarot.DECK))])
    card["reversed"] = bool(rnd.getrandbits(1))
    return card


#: Сфера внимания дня. Инвариант как у карты: слот выбирает код (одна и та же
#: колода — детерминированный слот на день на клиентку), раскрывает LLM.
_SPHERE_SLOTS = [
    ("любовь и отношения", "близкие, пара, чувства к себе"),
    ("работа и дела", "задачи, деньги, твоё место в общем деле"),
    ("энергия и состояние", "силы, настроение, забота о себе"),
]


def _sphere_slot(user) -> tuple[str, str]:
    rnd = random.Random(stable_seed(users_repo.user_today(user), user["tg_id"], "sphere"))
    return _SPHERE_SLOTS[rnd.randrange(len(_SPHERE_SLOTS))]


def daily_sphere(user) -> str:
    """Сфера внимания дня: «любовь и отношения» / «работа и дела» / «энергия и
    состояние». Код выбирает одну — та же у бота и в Mini App."""
    return _sphere_slot(user)[0]


# ---------------------------------------------------------------- совместимость

async def _synastry_data(db, user, partner_date: str) -> str | None:
    """Блок настоящей синастрии: карты обеих + аспекты пары.

    None — если хотя бы одна карта не полная (тогда остаётся только базовый
    разбор по датам). Карта партнёра берётся из сохранённых людей по дате,
    полную мы строим, когда клиентка указывала город/время.
    """
    try:
        chart = json.loads(user["chart_json"] or "{}")
        if chart.get("mode") != "full" or not chart.get("planets"):
            return None
        partner = await readings_repo.find_partner_by_date(
            db, user["tg_id"], partner_date)
        if not partner:
            return None
        pchart = json.loads(partner["chart_json"] or "{}") if partner["chart_json"] else {}
        if pchart.get("mode") != "full" or not pchart.get("planets"):
            return None
        product = chart_products.build_synastry_contract(
            chart, pchart, partner_id=int(partner["id"]),
            partner_label=str(partner["name"] or "Партнёр"),
        )
        aspects = astro.synastry_aspects(chart["planets"], pchart["planets"])
        lines = [
            "Карта пользователя:",
            astro.chart_brief(chart, time_known=bool(user["birth_time_known"])),
            "",
            f"Карта {partner['name'] or 'партнёра'}:",
            astro.chart_brief(pchart,
                              time_known=bool(partner["birth_time"])),
            "",
            "Синастрические аспекты пары:",
        ]
        if aspects:
            lines.append(astro.synastry_aspects_text(aspects))
            bonus = skills.synastry_bonus(aspects)
            if bonus:
                lines.append(f"Вклад аспектов в балл пары: {bonus:+d}")
        else:
            lines.append("(орбных аспектов между картами не найдено)")
        lines.extend([
            "",
            "[Детерминированный synastry contract — трактуй только эти значения]",
            json.dumps(product, ensure_ascii=False, indent=2),
        ])
        return "\n".join(lines)
    except (TypeError, ValueError):
        return None


#: Кеш синастрии живёт сутки. Балл детерминирован данными пары, и пара за день не
#: меняется; дольше — пересобираем, чтобы добавление полной карты партнёра не
#: пряталось под старым ответом навсегда.
SYNASTRY_TTL = timedelta(hours=24)


def _synastry_fresh(cached) -> bool:
    """Свежий ли кеш синастрии. Сломанная дата — мисс: пересоберём без риска."""
    created = cached["created_at"] or ""
    try:
        age = datetime.now(timezone.utc) - datetime.fromisoformat(created)
        return age <= SYNASTRY_TTL
    except ValueError:
        return False


async def interpret_compat(db, user, partner_date: str,
                           partner_name: str = "", *,
                           relation: str = "love") -> str:
    """Полный разбор пары. Настоящая синастрия берётся из сохранённых карт,
    если они есть; иначе — разбор по датам (Солнце/Луна/Венера).

    Если в расчёте появились ключи `spheres` (список {slug,title,value,note}) и
    `relation` (love/friend/work/family) — просим модель разобрать пару ПО СФЕРАМ
    и типу связи, а не только общим баллом. Ключи опциональны: их нет — прежнее
    поведение.

    `relation` и синастрические аспекты считаются как в `/compat` и чате
    (`skills._compat`), чтобы Mini App и бот называли один балл на одну пару.
    Версия ключа кеша зависит от наличия полных карт: добавили карту партнёра —
    балл пересобирается сразу, а не «залипает» старый.
    """
    who = partner_name or "партнёр"
    relation = relation if relation in skills.RELATIONS else "love"
    aspects = await skills._pair_aspects(db, user, partner_date)
    version = "full" if aspects is not None else "lite"
    key = f"syn:{partner_date}:{partner_name}:{relation}:{version}"
    cached = await readings_repo.get_synastry(db, user["tg_id"], key)
    if cached and cached["answer"] and _synastry_fresh(cached):
        return cached["answer"]

    data = skills._compat(user["birth_date"], partner_date, relation=relation,
                          aspects=aspects)
    block = await _synastry_data(db, user, partner_date)

    relation_label = {
        "love": "любовный союз", "friend": "дружба", "work": "работа/дело",
        "family": "семья",
    }.get(data.get("relation") or relation, "отношения")
    evidence = interpretation.compatibility_evidence(
        data, partner_name=who, relation_label=relation_label, synastry_block=block,
    )

    text = ""
    if llm.enabled():
        try:
            system = await agents.system_for(db, user, agents.get("astro"),
                                             question=f"Совместимость: {who}")
            user_msg = (
                f"{await skills.guide(db, 'compat')}\n\n{evidence.as_prompt_block()}\n\n"
                f"{interpretation.generation_rules('compatibility')}\n"
                "Разбери каждую доступную сферу отдельно: ресурс, возможное трение и "
                "один наблюдаемый способ укрепить контакт. Общий балл — ориентир, не "
                "вердикт. Пиши тепло, конкретно, 5–7 коротких абзацев."
            )
            candidate = await llm.complete(system, user_msg, tier="main", max_tokens=1000,
                                           purpose="compat", tg_id=user["tg_id"], db=db)
            check = interpretation.validate_compatibility_text(candidate, evidence)
            if check.ok:
                text = candidate
            else:
                log.warning("разбор пары отклонён quality guardrail: %s", "; ".join(check.issues))
        except Exception as e:  # noqa: BLE001
            log.warning("разбор пары ушёл в офлайн: %s", e)
    if len(text.strip()) < 120:
        text = (
            f"💞 Совместимость\n\n"
            f"Ты — {data['you']['sign']} ({data['you']['element']}), "
            f"{who} — {data['partner']['sign']} ({data['partner']['element']}).\n"
            f"Балл пары: {data['score']}/100 — {data['verdict']}.\n\n"
            f"Стихии подсказывают: не пытайся переделать партнёра, а используй разность как "
            f"опору. Спроси меня про конкретную ситуацию между вами — разложу "
            f"карты. 🌙")
    await readings_repo.cache_synastry(db, user["tg_id"], key, data["score"],
                                       data["breakdown"], text)
    return text


def _chart_brief(chart: dict) -> str:
    """Компактное текстовое представление карты для промпта."""
    bits = []
    sun = chart.get("sun") or {}
    asc = chart.get("ascendant") or {}
    mc = chart.get("mc") or {}
    bits.append(f"Солнце — {sun.get('sign','?')} ({sun.get('element','')}), "
                f"Асцендент — {asc.get('sign','?')} ({asc.get('deg','')}°), "
                f"MC — {mc.get('sign','?')}")
    pl = []
    for p in chart.get("planets", []):
        r = " ℞" if p.get("retro") else ""
        h = p.get("house")
        pl.append(f"{p.get('name')} {p.get('sign')} {p.get('deg','')}°"
                  f"{r}" + (f" (дом {h})" if h else ""))
    if pl:
        bits.append("Планеты: " + "; ".join(pl))
    hs = chart.get("houses", [])
    if hs:
        bits.append("Дома: " + "; ".join(
            f"{h.get('n')} — {h.get('sign')}" for h in hs))
    for n in chart.get("nodes", []):
        h = n.get("house")
        bits.append(f"{n.get('name')} — {n.get('sign')} {n.get('deg','')}°"
                    f"{' ℞' if n.get('retro') else ''}"
                    + (f" (дом {h})" if h else ""))
    asp = chart.get("aspects", [])
    if asp:
        bits.append("Аспекты: " + "; ".join(
            f"{a.get('p1')} {a.get('glyph','')} {a.get('p2')} "
            f"(орб {a.get('orb')}°)" for a in asp[:14]))
    return "\n".join(bits)


_CHART_INTERPRET_ATTEMPTS = 3


def _chart_planet(chart: dict, name: str) -> dict:
    for planet in chart.get("planets") or []:
        if str(planet.get("name") or "").strip() == name:
            return planet
    return {}


def _chart_node(chart: dict, prefix: str) -> dict:
    for node in chart.get("nodes") or []:
        if prefix in str(node.get("name") or ""):
            return node
    return {}


def _chart_house(chart: dict, number: int) -> dict:
    for house in chart.get("houses") or []:
        if str(house.get("n")) == str(number):
            return house
    return {}


def _placement_line(label: str, item: dict) -> str:
    sign = item.get("sign") or "данные недоступны"
    house = f", {item['house']}-й дом" if item.get("house") else ""
    retro = ", ретроградный" if item.get("retro") else ""
    return f"{label} в {sign}{house}{retro}"


def _chart_required_coverage(text: str, chart: dict, *, time_known: bool) -> tuple[str, ...]:
    """Проверяет наличие обязательных тем, доступных в конкретной карте."""
    lowered = (text or "").lower()
    checks: list[tuple[str, tuple[str, ...], bool]] = [
        ("Солнце", ("солнц",), bool(chart.get("sun"))),
        ("Луна", ("лун",), bool(_chart_planet(chart, "Луна"))),
        ("Меркурий", ("меркур",), bool(_chart_planet(chart, "Меркурий"))),
        ("Марс", ("марс",), bool(_chart_planet(chart, "Марс"))),
        ("Венера", ("венер",), bool(_chart_planet(chart, "Венера"))),
        ("Кету", ("кету",), bool(_chart_node(chart, "Кету"))),
        ("Раху", ("раху",), bool(_chart_node(chart, "Раху"))),
    ]
    if time_known:
        checks.extend([
            ("Асцендент", ("асценд", "восходящ"), bool(chart.get("ascendant"))),
            ("7-й дом", ("7-й дом", "7 й дом", "партнёрств", "партнерств"), bool(_chart_house(chart, 7))),
            ("карьера", ("карьер", "10-й дом", "10 й дом", "професс"), bool(chart.get("mc") or _chart_house(chart, 10))),
            ("финансы", ("финанс", "деньг", "2-й дом", "2 й дом"), bool(_chart_house(chart, 2))),
        ])
    return tuple(label for label, needles, available in checks
                 if available and not any(needle in lowered for needle in needles))


def _report_missing_sections(text: str, sections: list[str]) -> tuple[str, ...]:
    """Проверяет, что каждый заданный раздел отчёта раскрыт в тексте."""
    lowered = (text or "").lower()
    return tuple(title for title in sections
                 if title.lower() not in lowered)


def _full_chart_fallback(chart: dict, *, time_known: bool) -> str:
    """Подробный deterministic fallback, который сохраняет все доступные темы."""
    sun = chart.get("sun") or {}
    moon = _chart_planet(chart, "Луна")
    mercury = _chart_planet(chart, "Меркурий")
    mars = _chart_planet(chart, "Марс")
    venus = _chart_planet(chart, "Венера")
    asc = chart.get("ascendant") or {}
    mc = chart.get("mc") or {}
    ketu = _chart_node(chart, "Кету")
    rahu = _chart_node(chart, "Раху")
    house7 = _chart_house(chart, 7)
    house10 = _chart_house(chart, 10)
    house6 = _chart_house(chart, 6)
    house2 = _chart_house(chart, 2)
    sections = [
        "**1. Ядро личности и маска**\n"
        f"{_placement_line('Солнце', sun)}. Это внутренняя опора самоощущения и способа проявлять волю. "
        f"{_placement_line('Луна', moon)} — тема эмоционального ритма и внутреннего комфорта. "
        + (f"{_placement_line('Асцендент', asc)} показывает первое впечатление и социальную маску. "
           if time_known and asc else "Асцендент и первое впечатление нельзя надёжно разобрать без точного времени рождения. ")
        + "Наблюдение: где внешний образ совпадает с тем, что действительно помогает тебе восстановиться?",
        "**2. Интеллект и общение**\n"
        f"{_placement_line('Меркурий', mercury)}. Эта позиция показывает стиль мышления, формулировок и юмора. "
        "Проверяй трактовку через реальные разговоры: где эта настройка помогает тебе точнее слышать себя и собеседника?",
        "**3. Действие и конфликт**\n"
        f"{_placement_line('Марс', mars)}. Эта позиция показывает твой способ добиваться своего, выдерживать напряжение и обозначать границы. "
        "Полезный шаг — заметить, когда напор помогает задаче, а когда короткая пауза делает действие точнее.",
        "**4. Карьера и финансы**\n"
        f"MC: {_placement_line('MC', mc) if mc else 'данные недоступны'}; "
        f"{_placement_line('10-й дом', house10) if house10 else '10-й дом: данные недоступны'}; "
        f"{_placement_line('6-й дом', house6) if house6 else '6-й дом: данные недоступны'}; "
        f"{_placement_line('2-й дом', house2) if house2 else '2-й дом: данные недоступны'}. "
        "Эти положения показывают твой профессиональный стиль, ежедневный ритм и отношение к ресурсам. "
        "Наблюдение: какой один измеримый навык можно укрепить в ближайшие семь дней?",
        "**5. Любовь и язык чувств**\n"
        f"{_placement_line('Венера', venus)}. Это твой язык близости, эстетики и способов проявлять симпатию. "
        "Ориентир — не идеальный типаж, а взаимность, ясные договорённости и уважение границ.",
        "**6. Партнёрство**\n"
        + (f"{_placement_line('7-й дом', house7)}. Это зона серьёзных договорённостей и зеркала в отношениях; "
           if time_known and house7 else "7-й дом недоступен без точного времени рождения; не буду выдумывать характеристики партнёра. ")
        + "Наблюдение: какую договорённость в отношениях можно сделать яснее?",
        "**7. Кармические узлы: привычная сила и вектор роста**\n"
        f"{_placement_line('Кету', ketu)} можно читать как привычный багаж и знакомую стратегию, "
        f"а {_placement_line('Раху', rahu)} — как направление любопытства и роста. "
        "Здесь встречаются знакомая сила и новый опыт, который раскрывает следующий уровень карты. "
        "Наблюдение: где привычный сценарий уже не помогает, а новый опыт можно попробовать малым шагом?",
        "**8. Синтез**\n"
        "Карта собирает твои реакции, способ действия и реальные договорённости в один ясный узор. Сопоставь эмоциональную реакцию Луны, "
        "способ действия Марса и реальные договорённости в отношениях и работе. Выбери один проверяемый шаг, "
        "а через неделю сравни ожидание с наблюдаемым результатом. 🌙",
    ]
    return "\n\n".join(sections)


async def interpret_chart(db, user, chart: dict) -> tuple[str, bool]:
    """Генерирует полный разбор карты с semantic retry и coverage gate."""
    time_known = bool(user and user["birth_time_known"])
    evidence = interpretation.chart_evidence(chart, time_known=time_known)
    text = ""
    live = False

    # Preferred path: strict structured contract. The legacy Markdown path below
    # remains a compatibility fallback for providers that cannot return valid JSON.
    if llm.enabled() and chart.get("calculation"):
        try:
            system = await agents.system_for(db, user, agents.get("astro"))
            candidate = await llm.complete(
                system,
                chart_interpretation.prompt(
                    evidence.as_prompt_block(), await skills.guide(db, "natal")
                ),
                tier="main", max_tokens=3200, purpose="chart_interpret_structured",
                tg_id=user["tg_id"], db=db,
            )
            payload = chart_interpretation.parse_json_object(candidate)
            issues = chart_interpretation.validate_payload(
                payload, chart=chart, time_known=time_known
            )
            if not issues:
                chart["interpretation_structured"] = payload
                return chart_interpretation.render_text(payload), True
            log.info("structured chart interpretation rejected: %s", "; ".join(issues[:8]))
        except Exception as e:  # noqa: BLE001
            log.info("structured chart interpretation unavailable: %s", type(e).__name__)
    if llm.enabled():
        try:
            system = await agents.system_for(db, user, agents.get("astro"))
            base_prompt = (
                f"{await skills.guide(db, 'natal')}\n\n"
                f"{evidence.as_prompt_block()}\n\n"
                f"{interpretation.generation_rules('chart')}\n\n"
                "Сделай полный детальный разбор на русском языке, на «ты», а не короткий портрет. "
                "Сохрани ровно 8 нумерованных разделов: "
                "1) ядро личности — Солнце, Луна, Асцендент; "
                "2) интеллект и общение — Меркурий; "
                "3) действие и конфликты — Марс; "
                "4) карьера и финансы — MC, 10-й, 6-й и 2-й дома; "
                "5) любовь — Венера; 6) партнёрство — 7-й дом; "
                "7) узлы — Кету как знакомый паттерн и Раху как направление роста; "
                "8) синтез и практический следующий шаг. "
                "В каждом разделе сначала назови placement-факт из evidence, затем объясни его простыми словами "
                "и добавь конкретный вопрос для самонаблюдения. Не назначай диагнозов, не обещай финансовую удачу, "
                "идеального партнёра или события. Покажи пространство выбора и роста; узлы раскрывай через конкретные placements, "
                "и не превращай их в жёсткий сценарий или обязательную миссию. Если времени рождения нет, честно назови ASC, "
                "MC и дома недоступными и не выдумывай их."
            )
            feedback = ""
            for attempt in range(_CHART_INTERPRET_ATTEMPTS):
                candidate = await llm.complete(
                    system,
                    base_prompt + feedback,
                    tier="main", max_tokens=2600, purpose="chart_interpret",
                    tg_id=user["tg_id"], db=db,
                )
                grounding = interpretation.validate_chart_text(candidate, evidence)
                missing = _chart_required_coverage(candidate, chart, time_known=time_known)
                if len(candidate.strip()) >= 900 and grounding.ok and not missing:
                    text = candidate.strip()
                    live = True
                    break
                issues = list(grounding.issues) + (["не раскрыты темы: " + ", ".join(missing)] if missing else [])
                log.info("chart interpretation quality gate rejected attempt=%d issues=%s",
                         attempt + 1, "; ".join(issues[:8]))
                feedback = (
                    "\n\nПОВТОРНАЯ ГЕНЕРАЦИЯ: предыдущий текст не прошёл quality gate. "
                    "Не сокращай ответ. Обязательно раскрой каждую доступную тему: "
                    + ", ".join(missing or ("все обязательные секции",))
                    + ". Верни полный текст из 8 нумерованных разделов и не добавляй фактов вне evidence."
                )
        except Exception as e:  # noqa: BLE001
            log.warning("разбор карты ушёл в offline quality fallback: %s", type(e).__name__)
    if not live:
        text = _full_chart_fallback(chart, time_known=time_known)
    return text, live


# ---------------------------------------------------------------- отчёты

#: Купленные разборы. Каждый — длинный структурированный текст, который остаётся
#: в профиле навсегда (в отличие от ответа в чате).
REPORTS = {
    "natal": {
        "title": "Полный разбор натальной карты",
        "agent": "astro",
        "guide": "natal",
        "sections": ["Кто ты по своей карте (Солнце, Луна, Асцендент)",
                     "Твои сильные стороны и таланты",
                     "Личность и характер: планеты в знаках",
                     "Сферы жизни: планеты по домам",
                     "Ключевые аспекты и что они дают",
                     "Задачи и точки роста",
                     "Как тебе принимать решения"],
    },
    "matrix": {
        "title": "Матрица Судьбы — полный разбор",
        "agent": "oracle",
        "guide": "matrix",
        "sections": ["Личный аркан: твой характер",
                     "Духовный аркан: внутренняя опора",
                     "Родовой аркан: что пришло из семьи",
                     "Аркан судьбы: главный вектор жизни",
                     "Центр матрицы: зона комфорта",
                     "Линия любви", "Линия денег",
                     "Как выходить в плюс каждого аркана"],
    },
    "synastry": {
        "title": "Синастрия: совместимость пары",
        "agent": "astro",
        "guide": "compat",
        "sections": ["Что вас притянуло", "Как вы говорите друг с другом",
                     "Где будет трение", "Чувства и близость",
                     "Быт и деньги", "Перспектива союза",
                     "Что укрепит вас двоих"],
    },
    "solar": {
        # честно про метод: это прогноз года по карте и текущему небу, а не
        # астрономический соляр (момент возврата Солнца в натальный градус)
        "title": "Годовой прогноз по картам",
        "agent": "astro",
        "guide": "transit",
        "sections": ["Главная тема года", "Первые три месяца",
                     "Середина года", "Финал года",
                     "Лучшие месяцы для решений", "Что стоит отпустить",
                     "Один совет на весь год"],
    },
    "career": {
        "title": "Карьера и предназначение",
        "agent": "astro",
        "guide": "career",
        "sections": ["Твоё предназначение: к чему ты предрасположена",
                     "Как ты работаешь: сильные стороны и режим",
                     "Что тебя тормозит в профессии",
                     "Среда и люди: с кем тебе легко, с кем тяжело",
                     "Деньги и самооценка: как ты назначаешь себе цену",
                     "Когда действовать: периоды роста и периоды паузы",
                     "Ближайший шаг: что сделать в этом месяце"],
    },
}


async def build_report(db, user, kind: str, *, partner_date: str | None = None,
                       partner_name: str = "", force: bool = False) -> dict:
    """Собирает купленный разбор и сохраняет его в профиль.

    Готовый отчёт переиспользуется: разбор натальной карты не меняется, и
    генерировать его заново значит платить за токены дважды. Соляр и месячный
    отчёт привязаны к периоду и потому пересобираются на новый период.
    """
    spec = REPORTS.get(kind)
    if not spec:
        raise ValueError(f"неизвестный разбор: {kind}")
    period = None
    if kind == "solar":
        period = str(date.today().year)
    if kind == "synastry" and partner_date:
        period = partner_date

    if not force:
        existing = await readings_repo.get_report(db, user["tg_id"], kind, period)
        if existing and existing["body"]:
            return {"title": existing["title"], "body": existing["body"],
                     "kind": kind, "period": period, "cached": True}

    data_block = await _report_data(db, user, kind, partner_date, partner_name)
    evidence = interpretation.narrative_evidence(
        "report", [data_block],
        limits=(
            "Сохраняй заданные разделы, но не заполняй их шаблонной водой: если факта для раздела нет, честно назови предел расчёта.",
            "Фразы о предназначении, деньгах, любви или периодах связывай с конкретными фактами и вариантами действия; не добавляй неподтверждённых событий.",
        ),
    )
    body = ""
    if llm.enabled():
        try:
            system = await agents.system_for(db, user, agents.get(spec["agent"]))
            sections = "\n".join(f"{i}. {s}" for i, s in enumerate(spec["sections"], 1))
            user_msg = (
                f"{await skills.guide(db, spec['guide'])}\n\n"
                f"{evidence.as_prompt_block()}\n\n"
                f"{interpretation.generation_rules('report')}\n\n"
                f"Напиши для меня «{spec['title']}» строго по этим разделам:\n"
                f"{sections}\n\n"
                f"Каждый раздел — заголовок в теге <b> и 2-4 коротких связанных абзаца. "
                f"Не пересказывай источник и не выдумывай отсутствующие факты. Пиши лично, "
                f"тепло и конкретно; последний раздел заверши одним наблюдаемым шагом.")
            feedback = ""
            for attempt in (1, 2):
                candidate = await llm.complete(system, user_msg + feedback,
                                               tier="main", max_tokens=4000,
                                               purpose=f"report:{kind}",
                                               tg_id=user["tg_id"], db=db)
                check = interpretation.validate_nonfatal_text(candidate)
                missing = _report_missing_sections(candidate, spec["sections"])
                if check.ok and not missing:
                    body = candidate
                    break
                issues = list(check.issues) + (
                    [f"не раскрыты разделы: {', '.join(missing)}"] if missing else [])
                log.warning("разбор %s отклонён quality guardrail: attempt=%d issues=%s",
                            kind, attempt, "; ".join(issues))
                feedback = (
                    "\n\nПОВТОРНАЯ ГЕНЕРАЦИЯ: предыдущий текст не прошёл quality gate. "
                    "Проблемы: " + "; ".join(issues[:6])
                    + ". Обязательно раскрой каждый раздел из списка, сохрани "
                      "заголовки в теге <b> и не добавляй фактов вне evidence.")
        except Exception as e:  # noqa: BLE001
            log.warning("разбор %s ушёл в офлайн: %s", kind, e)
    if len(body.strip()) < 200:
        body = _report_offline(user, spec, data_block)

    report_id = await readings_repo.save_report(
        db, user["tg_id"], kind, spec["title"], body,
        period=period,
        meta={
            "partner": partner_name or None,
            "deterministic_source": data_block,
            "evidence_kind": evidence.kind,
            "evidence_limits": list(evidence.limits),
        })
    return {"title": spec["title"], "body": body, "kind": kind, "period": period,
            "cached": False, "report_id": report_id}


async def _report_data(db, user, kind: str, partner_date: str | None,
                       partner_name: str) -> str:
    """Детерминированные данные для разбора — их считает код."""
    if kind == "natal":
        return await skills.execute(db, user, "get_chart", {})
    if kind == "matrix":
        return await skills.execute(db, user, "get_matrix", {})
    if kind == "synastry":
        if not partner_date:
            raise ValueError("для синастрии нужна дата партнёра")
        compat = skills._compat(user["birth_date"], partner_date)
        chart = await skills.execute(db, user, "get_chart", {})
        core = (f"{chart}\n\nПартнёр: {partner_name or 'без имени'}, "
                f"{compat['partner']['sign']} ({compat['partner']['element']}), "
                f"дата {partner_date}. Балл пары: {compat['score']}/100 — "
                f"{compat['verdict']}.")
        block = await _synastry_data(db, user, partner_date)
        return core + ("\n\n" + block if block else "")
    if kind == "solar":
        chart = await skills.execute(db, user, "get_chart", {})
        sky = astro.today_sky()
        return (f"{chart}\n\nГод: {date.today().year}. Сейчас Солнце в "
                f"{sky['sun_season']['sign']}, Луна {sky['moon']['name']}. "
                f"День рождения: {user['birth_date']}.")
    if kind == "career":
        # Карьерный разбор строится на трёх источниках сразу: 10-й дом и Сатурн
        # из карты, аркан судьбы из Матрицы и ближайшие деловые окна по Луне.
        chart = await skills.execute(db, user, "get_chart", {})
        matrix = await skills.execute(db, user, "get_matrix", {})
        windows = await skills.execute(db, user, "get_career_windows", {})
        return f"{chart}\n\n{matrix}\n\n{windows}"
    return ""


def _report_offline(user, spec: dict, data_block: str) -> str:
    """Разбор без модели: структура и реальные данные, без «воды» от LLM."""
    prefix = _name_prefix(user)
    parts = [f"<b>{spec['title']}</b>", "",
             f"{prefix}вот что говорят твои расчёты.", "",
             "<i>Данные карты:</i>", data_block, "",
             "<b>Разделы разбора</b>"]
    parts += [f"• {s}" for s in spec["sections"]]
    parts += ["", "Связь со звёздами сейчас неровная — подробный текст по этим "
                  "разделам придёт, как только она восстановится. Расчёты уже "
                  "сохранены и не изменятся. 🌙"]
    return "\n".join(parts)


async def monthly_report(db, user) -> str:
    """Итог месяца: сколько всего было и что из этого следует."""
    period = datetime.now(timezone.utc).strftime("%Y-%m")
    existing = await readings_repo.get_report(db, user["tg_id"], "monthly", period)
    if existing and existing["body"]:
        return existing["body"]

    readings_n = await readings_repo.readings_count_since(db, user["tg_id"], 30)
    diary_n = await dialog_repo.diary_count_since(db, user["tg_id"], 30)
    streak = await dialog_repo.diary_streak(db, user["tg_id"])
    memory_enabled = bool(user["memory_enabled"])
    memories = (await dialog_repo.get_memories(db, user["tg_id"], limit=12)
                if memory_enabled else [])
    recent = await readings_repo.recent_readings(db, user["tg_id"], limit=10)
    diary_entries = (await dialog_repo.get_diary(db, user["tg_id"], limit=12)
                     if memory_enabled else [])

    # Повторы: один и тот же вопрос в раскладах звучал не раз — тема, что тревожит.
    qcounts = Counter(q.strip().lower() for r in recent
                      for q in [r.get("question") or ""] if q.strip())
    repeats = [f"«{q.strip()}» ×{n}" for q, n in qcounts.items() if n > 1]
    reads_block = "\n".join(f"- {r.get('question') or '…'}" for r in recent) or "-"
    diary_block = "\n".join(f"- {e['text'][:90]}" for e in diary_entries[:8]) or "-"

    monthly_evidence = interpretation.narrative_evidence(
        "monthly",
        [
            f"За месяц: раскладов {readings_n}, записей в дневнике {diary_n}, стрик {streak} дн.",
            f"Вопросы к картам:\n{reads_block}",
            f"Повторяющиеся запросы: {'; '.join(repeats) or '-'}.",
            f"Дневник (только при действующем согласии):\n{diary_block}",
            f"Сохранённые факты (только при действующем согласии): {'; '.join(memories) or '-'}.",
        ],
        limits=(
            "Если память отключена, не делай выводов о дневнике, личных записях или внутреннем состоянии: доступны только счётчики и заданные вопросы к картам.",
            "Называй повторяющейся только тему, которая явно повторяется во входных вопросах или записях.",
        ),
    )
    body = ""
    if llm.enabled() and (readings_n or diary_n or memories):
        try:
            system = await agents.system_for(db, user, agents.get("oracle"))
            user_msg = (
                f"{monthly_evidence.as_prompt_block()}\n\n"
                f"{interpretation.generation_rules('monthly')}\n\n"
                "Напиши тёплый итог месяца в 5–7 коротких абзацах, начни с 🌙. "
                "Отделяй наблюдение из фактов от мягкой гипотезы; не называй личные "
                "записи при отключённой памяти и не приписывай пользователю невысказанные переживания."
            )
            candidate = await llm.complete(system, user_msg, tier="main", max_tokens=1200,
                                           purpose="report:monthly", tg_id=user["tg_id"],
                                           db=db)
            check = interpretation.validate_nonfatal_text(candidate)
            if check.ok:
                body = candidate
            else:
                log.warning("месячный отчёт отклонён quality guardrail: %s", "; ".join(check.issues))
        except Exception as e:  # noqa: BLE001
            log.warning("месячный отчёт ушёл в офлайн: %s", e)
    if len(body.strip()) < 100:
        body = (f"🌙 <b>Твой месяц</b>\n\n"
                f"🎴 Раскладов: {readings_n}\n"
                f"📖 Записей в дневнике: {diary_n} (стрик {streak} дн.)\n"
                f"✦ Я запомнила о тебе {len(memories)} важных вещей.\n\n"
                f"Новый месяц — новое небо. Загляни утром за прогнозом ✨")

    await readings_repo.save_report(
        db, user["tg_id"], "monthly", "Итог месяца", body, period=period,
        meta={
            "evidence_schema_version": "monthly-evidence-v1",
            "evidence_kind": monthly_evidence.kind,
            "window_days": 30,
            "readings_count": readings_n,
            "diary_count": diary_n,
            "streak_days": streak,
            "memory_enabled": memory_enabled,
            "recent_question_count": len(recent),
            "repeated_question_count": len(repeats),
            "privacy_note": "raw diary, memory and question text are not copied into report metadata",
            "evidence_limits": list(monthly_evidence.limits),
        },
    )
    return body


# ---------------------------------------------------------------- память

def _memory_extract_prompt(user) -> str:
    """Даёт экстрактору форму третьего лица, не навязывая пользователю пол."""
    example = _gendered(
        user,
        "«её партнёра зовут Дима»",
        "«его партнёра зовут Дима»",
        "«у пользователя есть партнёр по имени Дима»",
    )
    return (
        "Ты ведёшь досье пользователя для личного астролога. Извлеки из сообщения "
        "0-3 факта, которые стоит помнить через месяц: люди и их имена, события, "
        "страхи, цели, важные даты, работа, здоровье.\n"
        f"Правила: пиши фактами в третьем лице (например, {example}), без оценок; "
        "не сохраняй сам вопрос, вежливости и общие слова; если помнить нечего — "
        "верни пустой массив.\n"
        "Ответ — ТОЛЬКО JSON-массив строк, без пояснений и без markdown."
    )

#: Короче этого ответа lite-вызов экстракции не окупается (G23): реплики в духе
#: «поняла 🌙» фактов не несут, а стоимость — вызов модели и эмбеддинги.
EXTRACT_MIN_ANSWER = 120


def _parse_facts(raw: str) -> list[str]:
    """Достаёт массив строк из ответа модели, даже если он в ```-блоке."""
    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text.split("\n", 1)[1] if "\n" in text else text
    text = text.removeprefix("json").strip()
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end <= start:
        return []
    try:
        facts = json.loads(text[start:end + 1])
    except (json.JSONDecodeError, ValueError):
        return []
    if not isinstance(facts, list):
        return []
    return [f.strip() for f in facts
            if isinstance(f, str) and 3 < len(f.strip()) < 300]


async def extract_memory_llm(db, user, question: str, answer: str) -> None:
    """Фоновая экстракция фактов (дешёвая модель). Тихо пропускается без ключа.

    Сохраняем через `core.memory`: он склеивает переформулировки одного и того же
    факта по близости векторов, иначе память быстро забивалась повторами.
    """
    if not bool(user["memory_enabled"]):
        return
    if not llm.enabled():
        return
    if len((answer or "").strip()) < EXTRACT_MIN_ANSWER:
        return                     # короткая реплика — без lite-вызова (G23)
    try:
        raw = await llm.complete(_memory_extract_prompt(user), question, tier="lite",
                                 max_tokens=300, purpose="memory_extract",
                                 tg_id=user["tg_id"], db=db)
    except Exception as e:  # noqa: BLE001
        log.debug("экстракция памяти пропущена: %s", e)
        return

    try:
        # один эмбеддинг-запрос на все факты, а не по одному на каждый (G23)
        await memory.remember_many(db, user["tg_id"], _parse_facts(raw)[:3])
    except Exception as e:  # noqa: BLE001
        log.debug("факты не сохранены: %s", e)

    # сводка «кто она» пересобирается редко и только когда фактов реально прибавилось
    try:
        if await memory.needs_summary(db, user["tg_id"]):
            await memory.build_summary(db, user)
    except Exception as e:  # noqa: BLE001
        log.debug("сводка профиля не обновлена: %s", e)
