"""Исполнение агента: сборка контекста, tool-use цикл, офлайн-подстраховка.

Продукт обязан отвечать всегда. Поэтому у каждого вызова есть три уровня:
    1. агентный цикл с инструментами (полноценный ответ);
    2. цепочка резервных LLM-провайдеров внутри `core.llm`;
    3. офлайн-трактовка на реальных расчётах — если недоступны все провайдеры.

Третий уровень не заглушка: карты, знак Солнца и арканы в нём настоящие, просто
текст собран шаблоном. Клиентка получает осмысленный ответ, а не «сервис недоступен».
"""
from __future__ import annotations

import json
import logging

from ...repo import billing as billing_repo
from ...repo import content as content_repo
from ...repo import dialog as dialog_repo
from ...repo import users as users_repo
from .. import astro, llm, memory, tarot
from .. import tool_registry as skills
from .. import matrix as mx
from ..personas import persona_style
from .base import build_system_prompt
from .context import build_bounded_history
from .file_loader import skill_context
from .. import shared_context
from ..interpretation import validate_nonfatal_text
from .registry import DEFAULT_AGENT, REGISTRY, get

log = logging.getLogger("oracle.agents")

MIN_ANSWER_LEN = 50


async def resolve(db, code: str | None):
    """Агент по коду с переопределениями из админки (`content_items`)."""
    spec = get(code)
    if db is None:
        return spec, spec.style, spec.rules
    try:
        item = await content_repo.get_content(db, "agent", spec.code)
    except Exception as e:  # noqa: BLE001
        log.warning("настройки агента %s недоступны: %s", spec.code, e)
        item = None
    if not item:
        return spec, spec.style, spec.rules
    meta = content_repo.content_meta(item)
    return spec, item.get("body") or spec.style, meta.get("rules") or spec.rules


async def _context(db, user, spec, question: str = ""):
    """Контекст клиентки: карта, арканы, память — с глубиной по тарифу."""
    chart = users_repo.chart_of(user)
    brief = (astro.chart_brief(chart, time_known=bool(user["birth_time_known"]))
             if chart else "карта ещё не построена")
    matrix_brief = "-"
    if user["birth_date"]:
        try:
            matrix_brief = mx.matrix_brief(mx.compute_matrix(user["birth_date"]))
        except (ValueError, KeyError) as e:
            log.warning("матрица для %s не посчиталась: %s", user["tg_id"], e)

    plan = await billing_repo.get_plan(db, user["sub_level"] or "free")
    depth = plan.get("memory_depth") or 20
    if not users_repo.sub_active(user):
        free = await billing_repo.get_plan(db, "free")
        depth = free.get("memory_depth") or 5

    if not bool(user["memory_enabled"]):
        shared = await shared_context.prompt_block(db, user, question)
        return brief, matrix_brief, [], "", shared
    memories = await memory.recall(db, user["tg_id"], question, limit=depth)
    summary = await memory.get_summary(db, user["tg_id"]) if depth > 5 else ""
    shared = await shared_context.prompt_block(db, user, question)
    return brief, matrix_brief, memories, summary, shared


async def system_for(db, user, spec=None, *, allowance_line: str = "",
                     question: str = "", extra_rules: str = "") -> str:
    """Системный промпт агента для этой клиентки."""
    spec = spec or get(DEFAULT_AGENT)
    spec, style, rules = await resolve(db, spec.code)
    if spec.uses_persona:
        style = await persona_style(db, user)
    context_data = await _context(db, user, spec, question)
    if len(context_data) == 4:
        brief, matrix_brief, memories, summary = context_data
        shared = "[SHARED_CONTEXT] нет доступных динамических фактов."
    else:
        brief, matrix_brief, memories, summary, shared = context_data
    try:
        chart = users_repo.chart_of(user)
    except (KeyError, TypeError, ValueError):
        chart = {}
    try:
        time_known = bool(user["birth_time_known"])
    except (KeyError, TypeError, IndexError):
        time_known = False
    natal_json = shared_context.natal_json(chart, time_known=time_known)
    language_rule = ("Reply in clear, warm English. Keep card and calculation names "
                     "recognisable; never pretend a translation is an exact calculation."
                     if user["lang"] == "en" else "")
    active_skills = skill_context(spec.code, question, limit=spec.skills_max_active)
    layered_rules = "\n\n".join(rule for rule in (rules, active_skills) if rule)
    combined_extra_rules = "\n".join(rule for rule in (extra_rules, language_rule) if rule)
    return build_system_prompt(
        spec, user=user, agent_name=spec.display_name(user), chart_brief=brief,
        matrix_brief=matrix_brief, memories=memories,
        allowance_line=allowance_line, style=style, rules=layered_rules,
        profile_summary=summary, natal_context_json=natal_json,
        shared_context=shared, extra_rules=combined_extra_rules)


async def answer(db, user, question: str, *, agent: str = DEFAULT_AGENT,
                 thread_id: int | None = None, allowance_line: str = "",
                 extra_rules: str = "", trace: list[str] | None = None) -> str:
    """Ответ агента на вопрос. Никогда не поднимает исключение наружу."""
    spec = get(agent)
    if llm.enabled():
        try:
            system = await system_for(db, user, spec, allowance_line=allowance_line,
                                      question=question, extra_rules=extra_rules)
            premium = users_repo.sub_active(user) if db else False
            history_limit = (max(spec.history_limit, 20) if premium else spec.history_limit)
            history = await dialog_repo.history(
                db, user["tg_id"], limit=history_limit * 3, thread_id=thread_id)
            messages = build_bounded_history(history, question, recent_limit=history_limit)
            allowed_tools = frozenset(spec.skills)

            async def executor(name: str, args: dict) -> str:
                if name not in allowed_tools:
                    log.warning("агент %s запросил запрещённый инструмент %s", spec.code, name)
                    return "инструмент не разрешён для этого проводника — продолжи без него"
                tool_args = dict(args or {})
                if name == "activate_skill":
                    tool_args["_agent_code"] = spec.code
                result = await skills.execute(db, user, name, tool_args)
                if trace is not None and name not in trace:
                    trace.append(name)
                return result

            feedback = ""
            for attempt in (1, 2):
                text = await llm.run_agent(
                    system, messages, skills.tools_for(spec.skills), executor,
                    tier=spec.tier, max_tokens=spec.max_tokens,
                    purpose=f"answer:{spec.code}", tg_id=user["tg_id"], db=db,
                    max_iters=spec.max_turns, timeout_s=spec.timeout_s,
                    max_tool_calls=spec.max_tool_calls)
                quality = validate_nonfatal_text(text)
                if not quality.ok:
                    log.warning("агент %s не прошёл safety gate: %s — попытка %d",
                                spec.code, "; ".join(quality.issues), attempt)
                    feedback = ("\n\nПОВТОРНАЯ ГЕНЕРАЦИЯ: предыдущий ответ не прошёл "
                                "safety gate. Проблемы: " + "; ".join(quality.issues)
                                + ". Перепиши ответ, не нарушая этих правил.")
                elif len(text.strip()) >= MIN_ANSWER_LEN:
                    return text
                else:
                    log.info("агент %s вернул слишком короткий ответ (%d симв) — попытка %d",
                             spec.code, len(text.strip()), attempt)
                    feedback = ("\n\nПОВТОРНАЯ ГЕНЕРАЦИЯ: предыдущий ответ был обрывком. "
                                "Дай полноценный ответ из нескольких абзацев.")
                if attempt == 2:
                    break
                messages.append({"role": "assistant", "content": text})
                messages.append({"role": "user", "content": feedback})
        except Exception as e:  # noqa: BLE001
            log.warning("агент %s не ответил (%s) — офлайн", spec.code, e)

    chart = users_repo.chart_of(user)
    memories = (await dialog_repo.get_memories(db, user["tg_id"], limit=5)
                if bool(user["memory_enabled"]) else [])
    return offline_answer(user, question, chart, memories, spec)


_OPENINGS = [
    "Я слышу твой вопрос, {name}... Нити уже задрожали.",
    "{name}, я всмотрелась в твою карту, прежде чем ответить.",
    "Звёзды наклонились ближе, {name}. Слушай.",
]
_CLOSINGS = [
    "Запиши это в дневник — через неделю поймёшь, о чём я. 🌙",
    "Доверься этому знаку. Я рядом, когда захочешь спросить ещё. ✨",
    "И помни: карты показывают дорогу, но идёшь по ней ты. 💫",
]
_ADVICE_BY_ELEMENT = {
    "огонь": "действуй смело, твоя стихия — огонь, промедление гасит его",
    "вода": "слушай чувства, твоя стихия — вода: она всегда знает, куда течь",
    "воздух": "поговори об этом вслух — воздуху нужно движение слов",
    "земля": "сделай один маленький практический шаг — земля любит опору",
}


def _sign_for_language(sign: str, lang: str) -> str:
    if lang != "en":
        return sign
    return {
        "Овен": "Aries", "Телец": "Taurus", "Близнецы": "Gemini", "Рак": "Cancer",
        "Лев": "Leo", "Дева": "Virgo", "Весы": "Libra", "Скорпион": "Scorpio",
        "Стрелец": "Sagittarius", "Козерог": "Capricorn", "Водолей": "Aquarius",
        "Рыбы": "Pisces",
    }.get(sign, sign)


def _node(chart: dict, label: str) -> dict:
    nodes = chart.get("nodes") or []
    return next((item for item in nodes if str(item.get("name", "")).startswith(label)), {})


def _offline_astro(user, question: str, chart: dict) -> str:
    lang = user["lang"] if user["lang"] in ("ru", "en") else "ru"
    if not chart:
        return ("I need a saved birth chart before I can give a grounded astrology reflection."
                if lang == "en" else
                "Мне нужна сохранённая натальная карта, чтобы дать разбор на основе расчёта.")
    sun = chart.get("sun") or {}
    moon = next((p for p in chart.get("planets") or [] if p.get("name") == "Луна"), {})
    rahu = chart.get("lunar_nodes", {}).get("rahu") or _node(chart, "Раху")
    ketu = chart.get("lunar_nodes", {}).get("ketu") or _node(chart, "Кету")
    precision = chart.get("precision", "unknown")
    if lang == "en":
        facts = [f"Sun: {_sign_for_language(sun.get('sign', 'unknown'), lang)}"]
        if moon:
            facts.append(f"Moon: {_sign_for_language(moon.get('sign', 'unknown'), lang)}")
        if rahu:
            facts.append(f"Rahu / north node: {_sign_for_language(rahu.get('sign', 'unknown'), lang)}")
        if ketu:
            facts.append(f"Ketu / south node: {_sign_for_language(ketu.get('sign', 'unknown'), lang)}")
        limitation = ("Birth time is not confirmed, so houses, Ascendant and MC are not used."
                      if precision != "exact" else "The chart includes a confirmed birth time and house framework.")
        return (f"I checked the saved natal calculation before answering. {', '.join(facts[:4])}.\n\n"
                f"These placements reveal the central pattern of your current reading. {limitation}\n\n"
                "Notice which theme is ready to become a concrete choice this week, and begin there.")
    facts = [f"Солнце: {sun.get('sign', 'знак не указан')}"]
    if moon:
        facts.append(f"Луна: {moon.get('sign', 'знак не указан')}")
    if rahu:
        facts.append(f"Раху: {rahu.get('sign', 'знак не указан')}")
    if ketu:
        facts.append(f"Кету: {ketu.get('sign', 'знак не указан')}")
    limitation = ("Время рождения не подтверждено, поэтому дома, Асцендент и MC не используются."
                  if precision != "exact" else "В карте есть подтверждённое время рождения и домовая система.")
    return (f"Я проверила сохранённый натальный расчёт. {'; '.join(facts[:4])}.\n\n"
            "Эти положения раскрывают главный узор твоего текущего чтения. "
            f"{limitation}\n\n"
            "Заметь, какая тема готова превратиться в конкретный выбор на этой неделе, и начни с неё.")


def _offline_oracle(user, question: str, chart: dict, memories: list[str]) -> str:
    lang = user["lang"] if user["lang"] in ("ru", "en") else "ru"
    name = user["name"] or ("there" if lang == "en" else "дорогая")
    destiny = ""
    if user["birth_date"]:
        try:
            m = mx.compute_matrix(user["birth_date"])
            destiny = (f"Your life-path arcana is {m['destiny']['n']} ({m['destiny']['arcana']})."
                       if lang == "en" else f"Твой аркан судьбы — {m['destiny']['n']} ({m['destiny']['arcana']}).")
        except (ValueError, KeyError):
            pass
    memory_line = ("I am keeping one thing you chose to share in mind. " if lang == "en" and memories else
                   "Я держу в уме одну вещь, которой ты сама решила поделиться. " if memories else "")
    if lang == "en":
        return (f"I hear your question, {name}. Let’s slow it down and make it concrete.\n\n"
                f"{destiny} {memory_line}I will turn the pattern into a clear reflection prompt. "
                "Name one repeated situation you want to understand, then choose one small action you can observe today.")
    return (f"Я слышу твой вопрос, {name}. Давай замедлимся и сделаем его конкретным.\n\n"
            f"{destiny} {memory_line}Я перевожу этот узор в ясный вопрос для самонаблюдения. "
            "Назови одну повторяющуюся ситуацию, которую хочешь понять, и выбери один маленький шаг, результат которого можно заметить сегодня.")


def _offline_tarot(user, question: str) -> str:
    lang = user["lang"] if user["lang"] in ("ru", "en") else "ru"
    cards = tarot.draw(3)
    if lang == "en":
        positions = ["Past", "Present", "Next perspective"]
        cards_block = "\n".join(f"- {position}: {card['name']}" for position, card in zip(positions, cards))
        return (f"I drew three cards for your question: {question}.\n\n{cards_block}\n\n"
                f"The centre card is {cards[1]['name']}. Use its imagery as a reflective prompt, "
                "and turn it into a concrete next step. Choose one small action that lets you test the theme in real life.")
    positions = ["Прошлое", "Настоящее", "Следующий взгляд"]
    cards_block = "\n".join(f"- {position}: {card['name']}" for position, card in zip(positions, cards))
    return (f"Я вытянула три карты на твой вопрос: {question}.\n\n{cards_block}\n\n"
            f"Центральная карта — {cards[1]['name']}. Используй её образ как вопрос для самонаблюдения, "
            "и преврати её в конкретный следующий шаг. Выбери один маленький шаг и проверь тему в реальной жизни.")


def offline_answer(user, question: str, chart: dict, memories: list[str], spec=None) -> str:
    """Ответ на реальных расчётах, собранный без модели."""
    spec = spec or get(DEFAULT_AGENT)
    if spec.code == "chiromant":
        return ("I need a saved palm-evidence reading before I can interpret a hand.\n\n"
                "Upload one whole palm in even light; I will describe only visible zones, "
                "show image limits and offer one self-reflection question tied to the visible lines."
                if user["lang"] == "en" else
                "Для ответа мне нужно сохранённое evidence-чтение по фотографии ладони.\n\n"
                "Загрузи одну ладонь целиком при ровном свете — я покажу только различимые зоны, "
                "границы снимка и предложу один вопрос для саморефлексии, связанный с видимыми линиями.")
    if spec.code == "astro":
        return _offline_astro(user, question, chart)
    if spec.code == "tarot":
        return _offline_tarot(user, question)
    return _offline_oracle(user, question, chart, memories)


async def agent_list(db, user) -> list[dict]:
    """Список агентов для интерфейса, с описаниями из админки."""
    out = []
    for code in REGISTRY:
        spec, style, _ = await resolve(db, code)
        item = spec.as_dict(user)
        try:
            content = await content_repo.get_content(db, "agent", code)
        except Exception:  # noqa: BLE001
            content = None
        if content:
            meta = content_repo.content_meta(content)
            item["title"] = content.get("title") or item["title"]
            item["tagline"] = meta.get("tagline") or item["tagline"]
        out.append(item)
    return out


def as_json(user, code: str) -> str:
    return json.dumps(get(code).as_dict(user), ensure_ascii=False)
