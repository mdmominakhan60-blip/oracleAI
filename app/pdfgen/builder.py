"""Сбор персонального разбора: расчёты → тексты → HTML.

Разбор строится на тех же расчётах, что и продукт: `core/astro` для карты,
`core/matrix` для арканов, `core/tool_registry.guide` для правил трактовки. Модель
пишет только текст разделов и получает на вход готовые цифры — поэтому PDF не
может «выдумать» планету, которой нет в карте.

Работает и без LLM: тогда разделы собираются из реальных данных без литературной
части. Это честнее, чем не отдать заказ вообще.
"""
from __future__ import annotations

import asyncio
import base64
import logging
from dataclasses import dataclass, field
from datetime import date, datetime

from ..config import settings
from ..core import astro, chart_rendering, geo, llm, tool_registry as skills
from ..core.matrix import compute_matrix
from ..repo import content
from . import layout

log = logging.getLogger("oracle.pdfgen")

#: Структура разбора. Порядок = порядок страниц; менять безопасно.
SECTIONS = [
    ("Кто ты по своей карте",
     "Солнце, Луна и Асцендент: ядро характера, чувства и то, какой тебя видят "
     "впервые. Объясни простыми словами, без терминов без расшифровки."),
    ("Твои сильные стороны",
     "Что даётся тебе легче, чем другим, и на что опираться в трудный момент. "
     "Опирайся на аспекты и положение планет в знаках."),
    ("Сферы жизни: планеты по домам",
     "Где именно в жизни разворачиваются твои главные темы. Если время рождения "
     "неточное — скажи об этом честно и работай по знакам."),
    ("Любовь и близость",
     "Венера и Луна: как ты любишь, что тебе нужно в отношениях и что ты "
     "принимаешь за любовь по ошибке."),
    ("Деньги и дело",
     "Второй и десятый дома, Сатурн, Юпитер: как ты зарабатываешь, что мешает "
     "просить свою цену и в чём твой профессиональный ресурс."),
    ("Матрица Судьбы: предназначение",
     "Арканы: личный, духовный, родовой, аркан судьбы и центр. Каждый — двумя "
     "полюсами (плюс и минус) и переходом из минуса в плюс."),
    ("Линия любви и линия денег",
     "Два аркана Матрицы, которые про отношения и про достаток. Что они дают и "
     "чего требуют."),
    ("Задачи и точки роста",
     "Через что ты растёшь: Сатурн, напряжённые аспекты, кармический вектор. "
     "Покажи эту энергию как задачу, которая превращается в силу через действие."),
    ("Как тебе принимать решения",
     "Практический раздел: по каким признакам ты понимаешь, что решение твоё, "
     "и что делать, когда не понимаешь."),
    ("Год впереди",
     "Ближайшие двенадцать месяцев крупными мазками: главная тема, ключевые окна действия "
     "и ритм пауз. Покажи, как этот период раскрывает главную линию карты."),
]

SECTION_EN = {
    "Кто ты по своей карте": ("Who you are in your chart", "Sun, Moon and Ascendant: your core, feelings and first impression. Explain simply and define every technical term."),
    "Твои сильные стороны": ("Your strengths", "What may come more naturally and what to lean on in difficult moments. Use planets in signs and major aspects."),
    "Сферы жизни: планеты по домам": ("Life areas: planets by houses", "Where the main themes of the chart may unfold. If birth time is uncertain, say so and work by signs."),
    "Любовь и близость": ("Love and closeness", "Venus and Moon: your language of affection, needs and the style of closeness you create."),
    "Деньги и дело": ("Money and work", "Second and tenth houses, Saturn and Jupiter: the resources, standards and professional direction that shape your work."),
    "Матрица Судьбы: предназначение": ("Destiny Matrix: purpose", "Personal, spiritual, ancestral, destiny and centre arcana, with constructive and difficult expressions."),
    "Линия любви и линия денег": ("Love line and money line", "Two Matrix arcana that reveal the architecture of connection and resource flow in your life."),
    "Задачи и точки роста": ("Tasks and growth points", "Saturn, tense aspects and the lunar-node axis as the exact places where your strength is forged."),
    "Как тебе принимать решения": ("How you make decisions", "A practical reflection guide: signals, questions and small reversible experiments when you are unsure."),
    "Год впереди": ("The year ahead", "A twelve-month map of the central theme, active windows and the rhythm that supports your next move."),
    "Сферы жизни: планеты по знакам": ("Life areas: planets by signs", "Where the main themes may be explored through sign placements. Do not use houses or angles when birth time is unconfirmed."),
}

SIGN_EN = {
    "Овен": "Aries", "Телец": "Taurus", "Близнецы": "Gemini", "Рак": "Cancer",
    "Лев": "Leo", "Дева": "Virgo", "Весы": "Libra", "Скорпион": "Scorpio",
    "Стрелец": "Sagittarius", "Козерог": "Capricorn", "Водолей": "Aquarius", "Рыбы": "Pisces",
}
POINT_EN = {
    "Солнце": "Sun", "Луна": "Moon", "Меркурий": "Mercury", "Венера": "Venus",
    "Марс": "Mars", "Юпитер": "Jupiter", "Сатурн": "Saturn", "Уран": "Uranus",
    "Нептун": "Neptune", "Плутон": "Pluto", "Раху (Северный узел)": "Rahu (North Node)",
    "Кету (Южный узел)": "Ketu (South Node)", "Лилит (Чёрная Луна)": "Lilith (Black Moon)",
    "Хирон": "Chiron", "Джуно": "Juno", "Церера": "Ceres", "Веста": "Vesta", "Паллада": "Pallas",
    "Асцендент": "Ascendant", "Середина неба": "Midheaven", "Десцендент": "Descendant", "Имум цели": "Imum Coeli",
}
ELEMENT_EN = {"огонь": "fire", "земля": "earth", "воздух": "air", "вода": "water"}
ARCANA_EN_NAME = {
    "Маг": "The Magician", "Жрица": "The High Priestess", "Императрица": "The Empress", "Император": "The Emperor",
    "Иерофант": "The Hierophant", "Влюблённые": "The Lovers", "Колесница": "The Chariot", "Справедливость": "Justice",
    "Отшельник": "The Hermit", "Колесо Фортуны": "Wheel of Fortune", "Сила": "Strength", "Повешенный": "The Hanged One",
    "Смерть": "Death", "Умеренность": "Temperance", "Дьявол": "The Devil", "Башня": "The Tower",
    "Звезда": "The Star", "Луна": "The Moon", "Солнце": "The Sun", "Суд": "Judgement",
    "Мир": "The World", "Шут": "The Fool",
}
ARCANA_EN_MEANING = {
    "Маг": "will, initiative and the ability to begin", "Жрица": "intuition, hidden knowledge and inner voice",
    "Императрица": "abundance, creativity and generative strength", "Император": "structure, order and leadership",
    "Иерофант": "mentorship, tradition and learning", "Влюблённые": "heart-led choice, partnership and harmony",
    "Колесница": "movement, victory and direction", "Справедливость": "balance, honesty and consequences",
    "Отшельник": "wisdom, self-search and solitude", "Колесо Фортуны": "turning points and changing circumstances",
    "Сила": "gentle strength and the integration of passion", "Повешенный": "a new perspective and growth through a pause",
    "Смерть": "transformation and the completion of cycles", "Умеренность": "balance, integration and proportion",
    "Дьявол": "desire, attachment and the shadow side", "Башня": "release from a false structure",
    "Звезда": "hope, inspiration and orientation", "Луна": "the subconscious, uncertainty and imagination",
    "Солнце": "joy, confidence and recognition", "Суд": "awakening, calling and accountability",
    "Мир": "wholeness and completion of a larger cycle", "Шут": "freedom, trust and a new path",
}
MATRIX_TITLE_EN = {
    "Личный аркан (характер)": "Personal arcana (character)", "Духовный аркан": "Spiritual arcana",
    "Родовая линия": "Ancestral line", "Линия предназначения": "Purpose line", "Центр матрицы": "Matrix centre",
    "Линия любви": "Love line", "Линия денег": "Money line",
}

TEXT = {
    "ru": {
        "title": "Полный отчёт натальной карты и Матрицы Судьбы",
        "summary": "Карта в цифрах",
        "reference": "Натальная карта: полный расчёт",
        "facts": ("Дата рождения", "Время рождения", "Место рождения", "Солнце", "Асцендент", "Луна", "Rahu / Раху", "Ketu / Кету", "Аркан судьбы"),
        "eyebrow": "ПЕРСОНАЛЬНЫЙ НАТАЛЬНЫЙ ОТЧЁТ", "perspective": "Перспектива", "node_mode": "Режим узлов",
        "engine": "Эфемеридный движок", "zodiac": "Зодиак", "houses": "Система домов", "precision": "Точность",
        "contract": "Контракт расчёта", "aspect_policy": "Политика аспектов",
        "planets": "Планеты", "nodes": "Лунные узлы: Rahu и Ketu", "additional": "Дополнительные точки",
        "cusps": "Куспиды домов", "aspects": "Ключевые аспекты", "object": "Объект", "sign": "Знак",
        "degree": "Градус", "house": "Дом", "status": "Статус", "link": "Открыть проект",
        "exact_note": "Округлённые значения удобны для чтения, точные значения в скобках сохранены для проверки.",
        "true_node": "True Node", "direct": "директный", "retro": "ретроградный", "unknown": "неизвестно (карта по знакам)",
        "matrix": "Матрица Судьбы", "disclaimer": "Твоя карта уже собрана в единый узор: возвращайся к этому чтению, когда понадобится увидеть направление яснее.",
        "ticket": "Твой золотой билет", "ticket_body": "30 дней полного доступа к личному AI-Оракулу.",
        "open_link": "Открой ссылку", "promo_help": "Введи код в боте командой /promo", "composed": "Составлено",
    },
    "en": {
        "title": "Full natal chart and Destiny Matrix report",
        "summary": "Your chart in numbers",
        "reference": "Natal chart: full calculation",
        "facts": ("Birth date", "Birth time", "Birth place", "Sun", "Ascendant", "Moon", "Rahu", "Ketu", "Destiny arcana"),
        "eyebrow": "PERSONAL NATAL REPORT", "perspective": "Perspective", "node_mode": "Node mode",
        "engine": "Ephemeris engine", "zodiac": "Zodiac", "houses": "House system", "precision": "Precision",
        "contract": "Calculation contract", "aspect_policy": "Aspect policy",
        "planets": "Planets", "nodes": "Lunar nodes: Rahu and Ketu", "additional": "Additional points",
        "cusps": "House cusps", "aspects": "Key aspects", "object": "Point", "sign": "Sign",
        "degree": "Degree", "house": "House", "status": "Status", "link": "Open project",
        "exact_note": "Rounded values are easier to read; exact values are kept in parentheses for verification.",
        "true_node": "True Node", "direct": "direct", "retro": "retrograde", "unknown": "unknown (sign-based chart)",
        "matrix": "Destiny Matrix", "disclaimer": "Your chart forms a coherent pattern: return to this reading whenever you need to see your direction with greater clarity.",
        "ticket": "Your golden ticket", "ticket_body": "30 days of full access to your personal AI Oracle.",
        "open_link": "Open this link", "promo_help": "Enter the code in the bot with /promo", "composed": "Prepared",
    },
}


def _lang(value: str | None) -> str:
    return "en" if (value or "").lower().startswith("en") else "ru"


def _text(lang: str, key: str):
    return TEXT[_lang(lang)][key]


def _section_title(title: str, lang: str) -> str:
    return SECTION_EN.get(title, (title, ""))[0] if _lang(lang) == "en" else title


def _section_brief(title: str, brief: str, lang: str) -> str:
    return SECTION_EN.get(title, (title, brief))[1] if _lang(lang) == "en" else brief


def _display_point(name: str, lang: str) -> str:
    return POINT_EN.get(name, name) if _lang(lang) == "en" else name


def _display_sign(sign: str, lang: str) -> str:
    return SIGN_EN.get(sign, sign) if _lang(lang) == "en" else sign


def _matrix_display(item: dict, lang: str) -> tuple[str, str, str]:
    if _lang(lang) != "en":
        return item.get("title", ""), item.get("arcana", ""), item.get("meaning", "")
    arcana = item.get("arcana", "")
    return (MATRIX_TITLE_EN.get(item.get("title", ""), item.get("title", "")),
            ARCANA_EN_NAME.get(arcana, arcana),
            ARCANA_EN_MEANING.get(arcana, item.get("meaning", "")))


def _display_precision(value: str, lang: str) -> str:
    if _lang(lang) == "ru":
        return value
    return {"exact": "exact", "date_only": "date only", "interval": "interval", "time_without_location": "time without location", "sun_only": "Sun only"}.get(value, value)


@dataclass
class Order:
    """Заказ на разбор: то, что приходит из CSV площадки или из CLI."""

    name: str
    birth_date: str                      # YYYY-MM-DD
    birth_time: str | None = None        # HH:MM, None — время неизвестно
    birth_city: str | None = None
    promo_code: str | None = None
    email: str = ""
    listing: str = ""
    lang: str = "ru"
    extras: dict = field(default_factory=dict)

    @property
    def time_known(self) -> bool:
        return bool(self.birth_time)


async def build_report_data(order: Order) -> dict:
    """Считает всё, что нужно разбору: карту, арканы, небо. Без модели."""
    lat = lon = None
    tz = None
    geo_info = {"coordinate_source": "unknown", "coordinate_confidence": 0.0,
                "timezone_source": "missing"}
    if order.birth_city:
        geo_info = await geo.resolve_city_info_async(order.birth_city)
        lat, lon, tz = geo_info["lat"], geo_info["lon"], geo_info["tz"]
    chart = await astro.compute_chart_async(
        order.birth_date, order.birth_time or "12:00", order.birth_city,
        lat, lon, tz, time_known=order.time_known,
        coordinate_source=geo_info["coordinate_source"],
        coordinate_confidence=geo_info["coordinate_confidence"],
        timezone_source=geo_info["timezone_source"],
    )
    matrix = compute_matrix(order.birth_date)
    return {
        "chart": chart,
        "matrix": matrix,
        "sky": astro.today_sky(),
        "tz": tz,
        "lat": lat,
        "lon": lon,
        "brief": astro.chart_brief(chart, time_known=order.time_known),
    }


async def _brand_context(db, lang: str) -> dict[str, str]:
    """Read editable project branding, with deterministic offline defaults."""
    language = _lang(lang)
    defaults = {
        "name": "OracleAI" if language == "en" else "Оракул",
        "tagline": ("A personal AI astrologer that knows you" if language == "en"
                    else "Личный AI-астролог, который знает именно тебя"),
        "project_url": (settings.public_url or settings.webapp_url
                        or "https://github.com/astartv1ai-del/oracleAI"),
        "disclaimer": (_text(language, "disclaimer")),
    }
    if db is None:
        return defaults
    try:
        name_key = "brand.name_en" if language == "en" else "brand.name"
        tagline_key = "brand.tagline_en" if language == "en" else "brand.tagline"
        name = await content.get_setting(db, name_key, defaults["name"])
        tagline = await content.get_setting(db, tagline_key, defaults["tagline"])
        project_url = await content.get_setting(db, "brand.project_url", defaults["project_url"])
        disclaimer_key = "disclaimer_en" if language == "en" else "disclaimer"
        disclaimer = await content.get_setting(db, disclaimer_key, defaults["disclaimer"])
        return {
            "name": str(name or defaults["name"]),
            "tagline": str(tagline or defaults["tagline"]),
            "project_url": str(project_url or defaults["project_url"]),
            "disclaimer": str(disclaimer or defaults["disclaimer"]),
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("не удалось прочитать brand settings для PDF: %s", exc)
        return defaults


def _element_balance_block(chart: dict, language: str) -> str:
    """Render a compact count-based element balance from canonical planet signs."""
    element_by_sign = {name: element for name, _glyph, element in astro.SIGNS}
    labels = {
        "огонь": "Огонь" if language == "ru" else "Fire",
        "земля": "Земля" if language == "ru" else "Earth",
        "воздух": "Воздух" if language == "ru" else "Air",
        "вода": "Вода" if language == "ru" else "Water",
    }
    accents = {"огонь": "#f08a9b", "земля": "#e8c56b", "воздух": "#65c7f0", "вода": "#b9a6ff"}
    counts = {element: 0 for element in labels}
    for point in chart.get("planets") or []:
        element = element_by_sign.get(point.get("sign"))
        if element in counts:
            counts[element] += 1
    total = sum(counts.values())
    if not total:
        return ""
    rows = []
    for element in ("огонь", "земля", "воздух", "вода"):
        count = counts[element]
        width = round((count / total) * 100) if total else 0
        rows.append(
            f'<div class="element-row"><span class="element-row__label">{layout.esc(labels[element])}</span>'
            f'<span class="element-row__track"><i style="width:{width}%;background:{accents[element]}"></i></span>'
            f'<b>{count if count else "—"}</b></div>'
        )
    return (f'<div class="element-balance"><div class="element-balance__header">'
            f'<span>{layout.esc("Баланс стихий" if language == "ru" else "Element balance")}</span>'
            f'<small>{layout.esc("планеты по знакам" if language == "ru" else "planets by sign")}</small></div>'
            f'<div class="element-rows">{"".join(rows)}</div></div>')


def _facts_block(order: Order, data: dict, lang: str) -> str:
    """Branded numeric overview: a sun-centered core with readable fact tiles."""
    language = _lang(lang)
    chart = data["chart"]
    sun = chart.get("sun") or {}
    asc = chart.get("ascendant") or {}
    labels = _text(language, "facts")
    element = sun.get("element", "—")
    element = ELEMENT_EN.get(element, element) if language == "en" else element
    rows = [
        (labels[0], _human_date(order.birth_date)),
        (labels[1], order.birth_time if order.time_known else _text(language, "unknown")),
        (labels[2], order.birth_city or ("not specified" if language == "en" else "не указано")),
        (labels[3], f"{_display_sign(sun.get('sign', '—'), language)} · {element}"),
    ]
    if asc:
        rows.append((labels[4], f"{_display_sign(asc.get('sign', '—'), language)} {asc.get('deg', '')}°"))
    moon = next((p for p in chart.get("planets", []) if p["name"] == "Луна"), None)
    if moon:
        rows.append((labels[5], f"{_display_sign(moon['sign'], language)} {moon['deg']}°"))
    lunar_nodes = chart.get("lunar_nodes") or {}
    rahu = lunar_nodes.get("rahu") or next((n for n in chart.get("nodes", []) if n.get("name", "").startswith("Раху")), None)
    ketu = lunar_nodes.get("ketu") or next((n for n in chart.get("nodes", []) if n.get("name", "").startswith("Кету")), None)
    if rahu:
        rows.append((labels[6], f"{_display_sign(rahu.get('sign', '—'), language)} {rahu.get('deg', '—')}°"))
    if ketu:
        rows.append((labels[7], f"{_display_sign(ketu.get('sign', '—'), language)} {ketu.get('deg', '—')}°"))
    lilith = next((n for n in chart.get("nodes", []) if n.get("name", "").startswith("Лилит")), None)
    if lilith:
        lilith_label = "Лилит · Чёрная Луна" if language == "ru" else "Lilith · Black Moon"
        rows.append((lilith_label, f"{_display_sign(lilith.get('sign', '—'), language)} {lilith.get('deg', '—')}°"))
    _, destiny_arcana, _ = _matrix_display(data["matrix"]["destiny"], language)
    rows.append((labels[8], f"{data['matrix']['destiny']['n']} — {destiny_arcana}"))

    profile_cells = "".join(
        f'<div class="facts-profile-cell"><span>{layout.esc(k)}</span><b>{layout.esc(v)}</b></div>'
        for k, v in rows[:3]
    )
    sun_label, sun_value = rows[3]
    placement_cells = "".join(
        f'<div class="facts-placement"><span>{layout.esc(k)}</span><b>{layout.esc(v)}</b></div>'
        for k, v in rows[4:]
    )
    element_balance = _element_balance_block(chart, language)
    return (
        '<div class="facts-constellation">'
        f'<div class="facts-constellation__header"><span>{layout.esc("Главные опоры" if language == "ru" else "Core anchors")}</span>'
        f'<small>{layout.esc("точки, с которых начинается чтение" if language == "ru" else "the points where the reading begins")}</small></div>'
        '<div class="facts-core">'
        '<div class="facts-core__halo"><strong>✦</strong></div>'
        f'<span>{layout.esc(sun_label)}</span><b>{layout.esc(sun_value)}</b>'
        '</div>'
        f'<div class="facts-profile">{profile_cells}</div>'
        f'<div class="facts-placements">{placement_cells}</div>'
        f'{element_balance}'
        '</div>'
    )


def _human_date(iso: str) -> str:
    try:
        return datetime.strptime(iso, "%Y-%m-%d").strftime("%d.%m.%Y")
    except ValueError:
        return iso


async def _section_text(db, order: Order, data: dict, title: str,
                        brief: str) -> str:
    """Generate one section in the selected report language."""
    language = _lang(order.lang)
    if not llm.enabled():
        return _offline_section(title, data, language)
    chart_facts = data["brief"]
    matrix_facts = "; ".join(
        f"{v['title']}: {v['n']} {v['arcana']} — {v['meaning']}"
        for v in data["matrix"].values())
    if language == "en":
        system = (
            "You are a careful astrologer and numerologist writing a personal printable report. "
            "Use only the supplied calculations; never invent a planet, point, aspect or arcana. "
            "Explain technical terms in a confident, immersive voice and connect every insight to the supplied chart. "
            "Preserve the separate safety protocol for medical, legal and financial requests. Write in English. "
            "Keep the report immersive and evidence-first; use direct traditional language and move safety boundaries to the dedicated safety layer."
        )
        time_note = ("Birth time is known; houses and Ascendant may be used."
                     if order.time_known else
                     "Birth time is unknown; do not make house or Ascendant claims.")
        user_msg = (
            f"Client: {order.name}, birth date {_human_date(order.birth_date)}"
            f"{', ' + order.birth_city if order.birth_city else ''}.\n{time_note}\n\n"
            f"Natal chart facts: {chart_facts}\n\nDestiny Matrix facts: {matrix_facts}\n\n"
            f"Write the section '{_section_title(title, language)}'.\n"
            f"Task: {_section_brief(title, brief, language)}\n\n"
            "Write 2-3 substantial paragraphs, without lists or a heading. Make every paragraph dense and personal; do not repeat the facts table."
        )
    else:
        system = (
            "Ты — практикующий астролог и нумеролог, пишешь персональный разбор для печати. "
            "Обращаешься к клиентке на «ты», тепло и уважительно. Пишешь живым языком, без "
            "эзотерического жаргона без объяснений. Опираешься ТОЛЬКО на приведённые расчёты и "
            "ничего не выдумываешь: не называешь планет и арканов, которых нет в данных. Не даёшь "
            "дистанцирующих метакомментариев. Для медицинских, юридических и финансовых "
            "тем сохраняй отдельный safety-протокол и опирайся на точные данные отчёта."
        )
        time_note = ("Время рождения известно точно — дома и Асцендент использовать можно."
                     if order.time_known else
                     "Время рождения НЕИЗВЕСТНО — про дома и Асцендент выводов не делай.")
        user_msg = (
            f"{await skills.guide(db, 'natal')}\n\n{await skills.guide(db, 'matrix')}\n\n"
            f"Клиентка: {order.name}, дата рождения {_human_date(order.birth_date)}"
            f"{', ' + order.birth_city if order.birth_city else ''}.\n{time_note}\n\n"
            f"Натальная карта: {chart_facts}\n\nМатрица Судьбы: {matrix_facts}\n\n"
            f"Напиши раздел разбора «{title}».\nЗадача раздела: {brief}\n\n"
            "Объём — 2-3 плотных абзаца сплошного текста, без списков и без заголовка "
            "(заголовок уже стоит на странице). Пиши обо мне лично и по делу в 2-3 плотных абзацах, без повторов."
        )
    try:
        return await llm.complete(system, user_msg, tier="main", max_tokens=1200,
                                  purpose="pdf_section", db=db)
    except Exception as e:  # noqa: BLE001
        log.warning("раздел «%s» ушёл в офлайн: %s", title, e)
        return _offline_section(title, data, language)


def _offline_section_en(title: str, data: dict) -> str:
    chart = data["chart"]
    planets = chart.get("planets") or []
    nodes = chart.get("nodes") or []
    all_points = planets + nodes + (chart.get("additional_points") or [])

    def point(name: str) -> dict:
        return next((item for item in all_points if item.get("name") == name), {})

    date_only = chart.get("precision") != "exact"

    def position(name: str) -> str:
        item = point(name)
        if not item:
            return f"{_display_point(name, 'en')}: no data"
        house = f", house {item['house']}" if item.get("house") and not date_only else ""
        retro = ", retrograde" if item.get("retro") else ""
        return f"{_display_point(name, 'en')} in {_display_sign(item.get('sign', '—'), 'en')}, {item.get('deg', '—')}°{house}{retro}"

    def house(number: int) -> str:
        item = next((h for h in chart.get("houses") or [] if h.get("n") == number), {})
        if not item:
            return f"House {number} is unavailable without confirmed birth time and coordinates"
        return f"House {number} in {_display_sign(item.get('sign', '—'), 'en')} ({item.get('deg', '—')}°)"

    aspect_text = "; ".join(
        f"{_display_point(a.get('p1', '—'), 'en')} {a.get('glyph', '')} {_display_point(a.get('p2', '—'), 'en')} — {a.get('aspect', '—')} (orb {a.get('orb', '—')}°)"
        for a in (chart.get("aspects") or [])[:5]
    ) or "No key aspects were selected in the available calculation."
    matrix = data["matrix"]

    if title.startswith("Кто ты"):
        return "\n\n".join([
            f"{position('Солнце')}. This placement defines the style of self-expression and the intentions that keep you steady. {position('Луна')} maps your needs, emotional rhythm and recovery.",
            ("Ascendant is not calculated because the birth time is unconfirmed; this report uses only sign placements, not angles or houses."
             if date_only else
             f"Ascendant in {_display_sign((chart.get('ascendant') or {}).get('sign', '—'), 'en')} — {(chart.get('ascendant') or {}).get('deg', '—')}°. It is the way your presence enters a situation."),
        ])
    if "сильные" in title.lower():
        return "\n\n".join([
            f"Key patterns to study: {aspect_text}. Supportive placements: {position('Юпитер')}; {position('Сатурн')}; {position('Марс')}.",
            "Give each resource a concrete expression this week: name where it already works and choose the next level it needs.",
        ])
    if "сферы жизни" in title.lower():
        if date_only:
            sign_positions = "; ".join(position(p.get("name", "—")) for p in planets[:6])
            return "\n\n".join([
                f"Sign-based focus areas: {sign_positions}.",
                "Birth time is unconfirmed, so houses and angles are intentionally omitted. Use these sign placements as reflective themes rather than precise life-area claims.",
            ])
        return "\n\n".join([
            f"Focus areas: {house(2)}; {house(6)}; {house(10)}. Planets by house: {'; '.join(position(p.get('name', '—')) for p in planets[:6])}.",
            "Houses are meaningful only when birth time and coordinates are confirmed.",
        ])
    if "любовь" in title.lower() or "близость" in title.lower():
        return "\n\n".join([
            f"{position('Венера')}. This placement shapes your values, pleasure and instinct for reciprocity. {position('Луна')} maps the conditions that help you feel safe and present in closeness.",
            ("Birth time is unconfirmed, so this section does not use a seventh-house claim. Turn the sign-based relationship themes into one clear agreement with a partner."
             if date_only else
             f"{house(7)}. Turn this relationship pattern into one clear agreement with a partner."),
        ])
    if "деньги" in title.lower() or "дело" in title.lower():
        return "\n\n".join([
            (f"Sign-based resource themes: {position('Юпитер')}; {position('Сатурн')}; {position('Марс')}."
             if date_only else
             f"Resource areas: {house(2)}; {house(6)}; {house(10)}. Growth and discipline themes: {position('Юпитер')}; {position('Сатурн')}."),
            "Translate these resource themes into a budget, a measured experiment or a clear conversation about value; for high-stakes decisions, pair the reading with qualified professional advice.",
        ])
    if "Матрица" in title or "предназначен" in title.lower():
        return "; ".join(
            f"{value['title']}: {value['n']} — {value['arcana']}. {value['meaning']}."
            for value in matrix.values()
        )
    if "Линия" in title:
        return "\n\n".join([
            f"Love line: {matrix.get('love', {}).get('n', '—')} — {matrix.get('love', {}).get('arcana', '—')}.",
            f"Money line: {matrix.get('money', {}).get('n', '—')} — {matrix.get('money', {}).get('arcana', '—')}.",
            "This line maps the way connection and resources move through your choices; give it form through one concrete conversation and one measurable step.",
        ])
    if "задач" in title.lower() or "точки роста" in title.lower():
        return "\n\n".join([
            f"Within the tradition, the lunar-node axis is {position('Раху (Северный узел)')} and {position('Кету (Южный узел)')}. Boundaries and practice: {position('Сатурн')}; patterns to examine: {aspect_text}.",
            "The lunar-node axis names the pattern you know well and the strength you are learning to claim next; give it one concrete expression this week.",
        ])
    if "решения" in title.lower():
        return "\n\n".join([
            f"Name the question and separate facts from interpretation: {position('Меркурий')}. Check your need for safety and recovery: {position('Луна')}.",
            f"Run a small reversible experiment: {position('Марс')}. Review the result using observable evidence.",
        ])
    if "год впереди" in title.lower():
        return "\n\n".join([
            f"The year section is a twelve-month map of the chart’s central themes and the rhythm that supports your next move. Natal anchors: {position('Солнце')}; {position('Сатурн')}; {position('Юпитер')}.",
            "Choose one theme for a month, record the starting point and assess change through facts rather than coincidences.",
        ])
    return "This chapter brings the calculated chart into one clear, practical direction.",


def _offline_section(title: str, data: dict, lang: str = "ru") -> str:
    """Section-specific fallback grounded only in deterministic chart facts."""
    if _lang(lang) == "en":
        return _offline_section_en(title, data)
    chart = data["chart"]
    matrix = data["matrix"]
    date_only = chart.get("precision") != "exact"
    planets = chart.get("planets") or []
    nodes = chart.get("nodes") or []
    all_points = planets + nodes + (chart.get("additional_points") or [])

    def point(name: str) -> dict:
        return next((item for item in all_points if item.get("name") == name), {})

    def position(name: str) -> str:
        item = point(name)
        if not item:
            return f"{name}: данных нет"
        house = f", {item['house']} дом" if item.get("house") and not date_only else ""
        retro = ", ретроградный" if item.get("retro") else ""
        return f"{name} в {item.get('sign', '—')}, {item.get('deg', '—')}°{house}{retro}"

    def house(number: int) -> str:
        item = next((h for h in chart.get("houses") or [] if h.get("n") == number), {})
        if not item:
            return f"{number}-й дом недоступен без точного времени и координат"
        return f"{number}-й дом в {item.get('sign', '—')} ({item.get('deg', '—')}°)"

    aspect_text = "; ".join(
        f"{a['p1']} {a['glyph']} {a['p2']} — {a['aspect']} (орб {a['orb']}°)"
        for a in (chart.get("aspects") or [])[:5]
    ) or "Ключевые аспекты не выделены в доступном расчёте."
    asc = chart.get("ascendant") or {}
    rahu = next((n for n in nodes if n.get("name", "").startswith("Раху")), {})
    ketu = next((n for n in nodes if n.get("name", "").startswith("Кету")), {})

    if title.startswith("Кто ты"):
        return "\n\n".join([
            f"{position('Солнце')}. Это ядро самовыражения и устойчивых намерений.",
            f"{position('Луна')}. Это карта потребностей, эмоционального ритма и восстановления.",
            ("Асцендент не рассчитывается: подтверждённого времени рождения нет. В этом отчёте используются только положения по знакам, без углов и домов."
             if date_only else
             f"Асцендент в {asc.get('sign', '—')} — {asc.get('deg', '—')}°. Это способ входить в ситуации и проявлять присутствие."),
        ])
    if "сильные" in title.lower():
        return "\n\n".join([
            f"Главные связки, которые стоит изучить: {aspect_text}",
            f"Опорные положения: {position('Юпитер')}; {position('Сатурн')}; {position('Марс')}.",
            "Свяжи каждую сильную сторону с конкретным опытом: где этот ресурс уже работает и какой следующий уровень ему нужен.",
        ])
    if "сферы жизни" in title.lower():
        if date_only:
            sign_positions = "; ".join(position(p.get("name", "—")) for p in planets[:6])
            return "\n\n".join([
                f"Фокус по знакам: {sign_positions}.",
                "Подтверждённого времени рождения нет, поэтому дома и углы намеренно исключены. Читай эти положения как темы для рефлексии, а не как точные области жизни.",
            ])
        return "\n\n".join([
            f"{house(2)}; {house(6)}; {house(10)}.",
            f"Планеты по домам: {'; '.join(position(p.get('name', '—')) for p in planets[:6])}.",
            "Дома доступны только при точном времени и координатах.",
        ])
    if "любовь" in title.lower() or "близость" in title.lower():
        return "\n\n".join([
            f"{position('Венера')}. Это язык ценностей, удовольствия и взаимности в близости.",
            f"{position('Луна')}. Наблюдай, какие условия помогают чувствовать безопасность в близости.",
            ("Подтверждённого времени рождения нет, поэтому 7-й дом не используется. Переведи темы по знакам в одну ясную договорённость с партнёром."
             if date_only else
             f"{house(7)}. Переведи эту тему в одну ясную договорённость с партнёром."),
        ])
    if "деньги" in title.lower() or "дело" in title.lower():
        return "\n\n".join([
            (f"Ресурсные темы по знакам: {position('Юпитер')}; {position('Сатурн')}; {position('Марс')}."
             if date_only else
             f"Ресурсные зоны карты: {house(2)}; {house(6)}; {house(10)}."),
            f"Темы роста и дисциплины: {position('Юпитер')}; {position('Сатурн')}. Переводи их в бюджет, измеримый эксперимент или разговор о цене; для важных решений подключай профильного специалиста.",
        ])
    if "Матрица" in title or "предназначен" in title.lower():
        return "; ".join(
            f"{value['title']}: {value['n']} — {value['arcana']}. {value['meaning']}."
            for value in matrix.values()
        )
    if "Линия" in title:
        return "\n\n".join([
            f"{matrix.get('love', {}).get('title', 'Линия любви')}: {matrix.get('love', {}).get('n', '—')} — {matrix.get('love', {}).get('arcana', '—')}.",
            f"{matrix.get('money', {}).get('title', 'Линия денег')}: {matrix.get('money', {}).get('n', '—')} — {matrix.get('money', {}).get('arcana', '—')}.",
            "Эта линия показывает, как через твои решения движутся близость и ресурсы; закрепи её одним разговором и одним измеримым шагом.",
        ])
    if "задач" in title.lower() or "точки роста" in title.lower():
        return "\n\n".join([
            f"Кармическая ось в рамках традиции: {rahu.get('name', 'Раху')} в {rahu.get('sign', '—')} и {ketu.get('name', 'Кету')} в {ketu.get('sign', '—')}. Граница и навык: {position('Сатурн')}; напряжённые связки: {aspect_text}.",
            "Эта ось показывает знакомую силу и направление роста; дай ей одно конкретное выражение на этой неделе.",
        ])
    if "решения" in title.lower():
        return "\n\n".join([
            f"Сначала назови вопрос и отдели факт от интерпретации: {position('Меркурий')}. Проверь телесную реакцию и потребность в безопасности: {position('Луна')}.",
            f"Сделай маленький обратимый эксперимент: {position('Марс')}. Через неделю оцени результат по наблюдаемым признакам.",
        ])
    if "год впереди" in title.lower():
        return "\n\n".join([
            f"Этот раздел собирает двенадцатимесячную карту главных тем и ритма, который поддерживает следующий шаг. Натальные опоры: {position('Солнце')}; {position('Сатурн')}; {position('Юпитер')}.",
            "Выбери одну тему на месяц, зафиксируй исходную точку и оцени изменения по фактам, а не по совпадениям.",
        ])
    return data["brief"]


def _aspect_legend(chart: dict, lang: str) -> str:
    """Compact legend for the semantic aspect-line styles used by the wheel."""
    if not (chart.get("aspects") or []):
        return ""
    language = _lang(lang)
    labels = {
        "соединение": ("☌ соединение", "☌ conjunction", "conjunction"),
        "оппозиция": ("☍ оппозиция", "☍ opposition", "opposition"),
        "трин": ("△ трин", "△ trine", "trine"),
        "квадрат": ("□ квадрат", "□ square", "square"),
        "секстиль": ("⚹ секстиль", "⚹ sextile", "sextile"),
    }
    seen = []
    for aspect in chart.get("aspects") or []:
        code = aspect.get("aspect")
        if code in labels and code not in seen:
            seen.append(code)
    chips = "".join(
        f'<span class="aspect-chip aspect-{layout.esc(code)}">'
        f'{layout.esc(labels[code][1 if language == "en" else 0])}</span>'
        for code in seen
    )
    return f'<div class="aspect-legend"><span class="small muted">{layout.esc("Линии аспектов" if language == "ru" else "Aspect lines")}</span>{chips}</div>'


def _ticket_block(promo_code: str | None, bot_username: str, lang: str) -> str:
    """Promo block linking the generated report back to the project."""
    if not promo_code:
        return ""
    language = _lang(lang)
    link = (f"https://t.me/{bot_username}?start={promo_code}" if bot_username else "")
    where = (f'<p class="small muted">{_text(language, "open_link")}: {layout.esc(link)}</p>'
             if link else f'<p class="small muted">{_text(language, "promo_help")}</p>')
    return (
        '<div class="ticket">'
        f'<h2 style="border:none;margin-bottom:3mm">{_text(language, "ticket")}</h2>'
        f'<p>{_text(language, "ticket_body")}</p>'
        f'<div class="code">{layout.esc(promo_code)}</div>'
        f'{where}</div>')


def _data_table(headers: list[str], rows: list[list[str]]) -> str:
    if not rows:
        return ""
    head = "".join(f"<th>{layout.esc(value)}</th>" for value in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>"
        for row in rows
    )
    return f'<table class="data-table"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>'


def _exact_degree(value) -> str:
    try:
        return f"{float(value):.4f}°"
    except (TypeError, ValueError):
        return "—"


def _point_rows(points: list[dict], lang: str) -> list[list[str]]:
    language = _lang(lang)
    rows = []
    for point in points:
        name = point.get("name", "—")
        glyph = layout.PLANET_GLYPHS.get(name, "•")
        display_name = _display_point(name, language)
        sign = _display_sign(point.get("sign", "—"), language)
        exact = point.get("deg_exact", point.get("deg"))
        degree = f"{point.get('deg', '—')}° <span class=\"muted small\">({_exact_degree(exact)})</span>"
        house = (f"{_text(language, 'house')} {point.get('house')}"
                 if point.get("house") else "—")
        status = _text(language, "retro" if point.get("retro") else "direct")
        rows.append([f"{layout.esc(glyph)} {layout.esc(display_name)}", layout.esc(sign), degree, house, status])
    return rows


def _natal_reference_block(data: dict, lang: str) -> str:
    """Split the technical reference into calm, readable print sections."""
    language = _lang(lang)
    chart = data["chart"]
    def t(key: str):
        return _text(language, key)

    headers = [t("object"), t("sign"), t("degree"), t("house"), t("status")]
    parts = [
        f'<div class="section reference-section"><h2>{t("reference")}</h2>',
        f'<p class="reference-lead">{"Положения планет, лунные узлы, дома и аспекты собраны в отдельных разделах для спокойного и удобного чтения." if language == "ru" else "Planet placements, lunar nodes, houses and aspects are arranged in separate sections for calm, easy reading."}</p>',
        '</div>',
    ]

    placement_parts = [f'<div class="section reference-section placement-reference"><h2>{t("planets")}</h2>', _data_table(headers, _point_rows(chart.get("planets") or [], language))]
    nodes = chart.get("nodes") or []
    if nodes:
        note = ("Rahu is the North Node and Ketu is the South Node. Together they show the axis of inherited patterns and growth."
                if language == "en" else
                "Rahu — Северный лунный узел, Ketu — Южный лунный узел. Вместе они показывают ось привычного опыта и роста.")
        placement_parts.extend([f'<h3>{t("nodes")}</h3>', f'<p>{note}</p>', _data_table(headers, _point_rows(nodes, language))])
    expanded = chart.get("additional_points") or []
    if expanded:
        placement_parts.extend([f'<h3>{t("additional")}</h3>', _data_table(headers, _point_rows(expanded, language))])
    placement_parts.append('</div>')
    parts.extend(placement_parts)

    houses = chart.get("houses") or []
    if houses:
        rows = []
        for house in houses:
            exact = house.get("abs_deg_exact", house.get("abs_deg"))
            degree = f"{house.get('deg', '—')}° <span class=\"muted small\">({_exact_degree(exact)})</span>"
            rows.append([str(house.get("n", "—")), layout.esc(_display_sign(house.get("sign", "—"), language)), degree])
        angle_houses = {item.get("n"): item for item in houses if item.get("n") in {1, 4, 7, 10}}
        angle_labels = {1: ("Асцендент", "Ascendant"), 4: ("IC", "IC"), 7: ("Десцендент", "Descendant"), 10: ("MC", "MC")}
        angle_cards = "".join(
            f'<div class="house-angle"><span>{layout.esc(angle_labels[number][1 if language == "en" else 0])}</span>'
            f'<b>{layout.esc(_display_sign(item.get("sign", "—"), language))}</b>'
            f'<small>{layout.esc(str(item.get("deg", "—")) + "°")}</small></div>'
            for number, item in angle_houses.items()
        )
        parts.extend([
            f'<div class="section reference-section house-reference"><h2>{t("cusps")}</h2>',
            f'<p class="reference-lead">{"Каждый дом — отдельная область опыта; здесь собраны его знак и точная долгота куспида." if language == "ru" else "Each house marks a distinct area of experience; this page lists its sign and exact cusp longitude."}</p>',
            _data_table([t("house"), t("sign"), "Cusp longitude" if language == "en" else "Долгота куспида"], rows),
            f'<div class="house-angle-panel"><div class="house-angle-panel__title">{"Четыре угловые точки" if language == "ru" else "Four angular points"}</div><div class="house-angle-grid">{angle_cards}</div></div>',
            '</div>',
        ])

    aspects = chart.get("aspects") or []
    if aspects:
        aspect_en = {"соединение": "conjunction", "оппозиция": "opposition", "трин": "trine", "квадрат": "square", "секстиль": "sextile"}
        rows = []
        for aspect in aspects:
            orb = aspect.get("orb_exact", aspect.get("orb", "—"))
            p1 = _display_point(aspect.get("p1", "—"), language)
            p2 = _display_point(aspect.get("p2", "—"), language)
            aspect_name = aspect_en.get(aspect.get("aspect", "—"), aspect.get("aspect", "—")) if language == "en" else aspect.get("aspect", "—")
            rows.append([layout.esc(f"{p1} {aspect.get('glyph', '')} {p2}"), layout.esc(aspect_name), f"{aspect.get('orb', '—')}° <span class=\"muted small\">({_exact_degree(orb)})</span>"])
        parts.extend([
            f'<div class="section reference-section aspect-reference"><h2>{t("aspects")}</h2>',
            _data_table(["Pattern" if language == "en" else "Связка", "Aspect" if language == "en" else "Аспект", "Orb" if language == "en" else "Орб"], rows),
            '</div>',
        ])
    return "".join(parts)


def _closing_block(order: Order, data: dict, brand: dict[str, str], lang: str) -> str:
    language = _lang(lang)
    chart = data["chart"]
    nodes = chart.get("lunar_nodes") or {}
    rahu = nodes.get("rahu") or next((n for n in chart.get("nodes", []) if n.get("name", "").startswith("Раху")), {})
    ketu = nodes.get("ketu") or next((n for n in chart.get("nodes", []) if n.get("name", "").startswith("Кету")), {})
    sun = next((p for p in chart.get("planets", []) if p.get("name") == "Солнце"), None) or chart.get("sun") or {}
    asc = chart.get("ascendant") or {}
    _, destiny_arcana, destiny_meaning = _matrix_display(data["matrix"]["destiny"], language)
    rows = [
        ("Rahu / Раху" if language == "ru" else "Rahu", f"{_display_sign(rahu.get('sign', '—'), language)} {rahu.get('deg', '—')}°"),
        ("Ketu / Кету" if language == "ru" else "Ketu", f"{_display_sign(ketu.get('sign', '—'), language)} {ketu.get('deg', '—')}°"),
        (_text(language, "facts")[3], f"{_display_sign(sun.get('sign', '—'), language)} {sun.get('deg', '—')}°"),
        (_text(language, "facts")[4], f"{_display_sign(asc.get('sign', '—'), language)} {asc.get('deg', '—')}°" if asc else _text(language, "unknown")),
        (_text(language, "facts")[8], f"{data['matrix']['destiny']['n']} — {destiny_arcana}"),
    ]
    rows_html = "".join(f'<tr><td class="label">{layout.esc(k)}</td><td>{layout.esc(v)}</td></tr>' for k, v in rows)
    guide_title = "Практический ориентир" if language == "ru" else "Practical guide"
    guide = ("Карта показывает главную тему текущего этапа: выбери одно направление, сформулируй намерение и "
             "сделай первый шаг в ближайшие сутки. Через месяц вернись к этой странице и посмотри, как раскрылась "
             "линия роста."
             if language == "ru" else
             "Your chart highlights the central theme of this stage: choose one direction, set an intention and "
             "take the first step within the next day. Return to this page in a month and see how the growth line unfolded.")
    project = (f'<p class="small"><a href="{layout.esc(brand["project_url"])}">'
               f'{layout.esc(_text(language, "link"))}: {layout.esc(brand["project_url"])}</a></p>'
               if brand["project_url"].startswith(("https://", "http://")) else "")
    return (f'<div class="closing-grid"><div class="card"><h3>{layout.esc("Ключевые позиции" if language == "ru" else "Key placements")}</h3>'
            f'<table>{rows_html}</table></div><div class="card"><h3>{layout.esc(guide_title)}</h3>'
            f'<p>{layout.esc(guide)}</p><p class="small muted">{layout.esc(destiny_meaning)}</p>{project}</div></div>')


def _natal_key_strip(data: dict, language: str) -> str:
    chart = data["chart"]
    planets = chart.get("planets") or []
    sun = chart.get("sun") or next((p for p in planets if p.get("name") == "Солнце"), {})
    moon = next((p for p in planets if p.get("name") == "Луна"), {})
    asc = chart.get("ascendant") or {}
    nodes = chart.get("lunar_nodes") or {}
    rahu = nodes.get("rahu") or next((n for n in chart.get("nodes") or [] if n.get("name", "").startswith("Раху")), {})
    primary = [
        ("☉", ("Солнце" if language == "ru" else "Sun"), f'{_display_sign(sun.get("sign", "—"), language)} {sun.get("deg", "—")}°'),
        ("☾", ("Луна" if language == "ru" else "Moon"), f'{_display_sign(moon.get("sign", "—"), language)} {moon.get("deg", "—")}°'),
        ("As", ("Асцендент" if language == "ru" else "Ascendant"), f'{_display_sign(asc.get("sign", "—"), language)} {asc.get("deg", "—")}°' if asc else _text(language, "unknown")),
    ]
    primary_cells = "".join(
        f'<div class="natal-key-card"><strong>{layout.esc(glyph)}</strong><span>{layout.esc(label)}</span><b>{layout.esc(value)}</b></div>'
        for glyph, label, value in primary
    )
    node_label = "Раху · северный узел" if language == "ru" else "Rahu · north node"
    node_value = f'{_display_sign(rahu.get("sign", "—"), language)} {rahu.get("deg", "—")}°'
    mc = chart.get("mc") or {}
    houses_by_number = {house.get("n"): house for house in chart.get("houses") or []}
    ic = houses_by_number.get(4) or {}
    mc_value = f'MC {_display_sign(mc.get("sign", "—"), language)} {mc.get("deg", "—")}° · IC {_display_sign(ic.get("sign", "—"), language)} {ic.get("deg", "—")}°'
    return (f'<div class="natal-key-strip"><div class="natal-key-strip__title">'
            f'{layout.esc("Три главные опоры" if language == "ru" else "Three core anchors")}</div>'
            f'<div class="natal-key-primary">{primary_cells}</div>'
            f'<div class="natal-key-secondary">'
            f'<div><span>{layout.esc(node_label)}</span><b>{layout.esc(node_value)}</b></div>'
            f'<div><span>{layout.esc("Ось MC / IC" if language == "ru" else "MC / IC axis")}</span><b>{layout.esc(mc_value)}</b></div>'
            f'</div></div>')


async def _natal_print_block(data: dict, order: Order, language: str) -> str:
    """Return a full-width print image or an explicit precision/recovery state."""
    title = "Натальная карта" if language == "ru" else "Natal chart"
    if (data["chart"].get("precision") or "") != "exact":
        copy = ("Изображение колеса не строится без подтверждённого времени, координат и часового пояса. Планеты и таблица положений сохранены ниже."
                if language == "ru" else
                "The wheel image is not generated without confirmed birth time, coordinates and timezone. Planet placements remain in the reference tables below.")
        return f'<div class="section natal-print-section"><h2>{layout.esc(title)}</h2><div class="natal-print-state"><b>{layout.esc(_text(language, "precision"))}</b><p>{layout.esc(copy)}</p></div></div>'
    try:
        image, spec, _, _ = await asyncio.to_thread(
            chart_rendering.render_chart_image,
            data["chart"], birth_date=order.birth_date, birth_time=order.birth_time,
            lat=data.get("lat"), lon=data.get("lon"), tz=data.get("tz"),
            variant="print", image_format="png", locale=language,
        )
    except chart_rendering.ChartRenderError:
        copy = ("Изображение карты временно недоступно; отчёт продолжает содержать проверяемые таблицы положений."
                if language == "ru" else
                "The chart image is temporarily unavailable; the report still contains the verified placement tables.")
        return f'<div class="section natal-print-section"><h2>{layout.esc(title)}</h2><div class="natal-print-state"><p>{layout.esc(copy)}</p></div></div>'
    encoded = base64.b64encode(image).decode("ascii")
    return (f'<div class="section natal-print-section"><h2>{layout.esc(title)}</h2>'
            f'<figure class="natal-print-figure"><img class="natal-print-image" width="{spec.width}" height="{spec.height}" '
            f'src="data:image/png;base64,{encoded}" alt="{layout.esc(title)}" /></figure>'
            f'{_aspect_legend(data["chart"], language)}{_natal_key_strip(data, language)}</div>')


async def generate(db, order: Order, *, bot_username: str = "",
                   concurrency: int = 3) -> str:
    """Build a compact, localized HTML report ready for PDF rendering."""
    language = _lang(order.lang)
    brand = await _brand_context(db, language)
    data = await build_report_data(order)
    semaphore = asyncio.Semaphore(max(1, concurrency))

    sections = [
        ("Сферы жизни: планеты по знакам", SECTION_EN["Сферы жизни: планеты по знакам"][1])
        if not order.time_known and title == "Сферы жизни: планеты по домам"
        else (title, brief)
        for title, brief in SECTIONS
    ]

    async def one(title: str, brief: str) -> str:
        async with semaphore:
            return await _section_text(db, order, data, title, brief)

    texts = await asyncio.gather(*(one(t, b) for t, b in sections))
    project_url = brand["project_url"]
    safe_url = project_url if project_url.startswith(("https://", "http://")) else ""
    matrix_labels = {
        item.get("title", ""): _matrix_display(item, language)[0]
        for item in data["matrix"].values()
    }
    cover_title = _text(language, "title")
    cover_link = (f'<a class="project-link" href="{layout.esc(safe_url)}">'
                  f'{layout.esc(_text(language, "link"))}: {layout.esc(safe_url)}</a>'
                  if safe_url else "")
    born = _human_date(order.birth_date)
    if order.birth_city:
        born += f" · {order.birth_city}"
    blocks = [
        '<div class="cover">'
        f'<div class="brand-mark">{layout.brand_mark_svg()}</div>'
        f'<div class="brand">{layout.esc(brand["name"])}</div>'
        f'<div class="eyebrow">{layout.esc(_text(language, "eyebrow"))}</div>'
        f'<h1>{layout.esc(cover_title)}</h1>'
        f'<p class="sub">{layout.esc(brand["tagline"])}</p>'
        f'<div class="who">{layout.esc(order.name)}</div>'
        f'<div class="born">{layout.esc(born)}</div>'
        f'<p class="sub small">{layout.esc(_text(language, "composed"))} {date.today().strftime("%d.%m.%Y")}</p>'
        f'{cover_link}'
        '</div>',
        f'<div class="section"><h2>{layout.esc(_text(language, "summary"))}</h2>'
        '<div class="overview-grid">'
        f'<div>{_facts_block(order, data, language)}</div>'
        '<div class="overview-visuals">'
        f'<div class="matrix-visual"><div class="matrix-visual__label">{layout.esc(_text(language, "matrix"))}</div>'
        f'<div class="wheel">{layout.matrix_svg(data["matrix"], size=220, labels=matrix_labels)}</div></div>'
        '</div></div></div>',
        await _natal_print_block(data, order, language),
        _natal_reference_block(data, language),
    ]
    for start in range(0, len(sections), 2):
        chapter_blocks = []
        for idx in range(start, min(start + 2, len(sections))):
            title, brief = sections[idx]
            chapter_blocks.append(
                f'<article class="chapter"><h2>{layout.esc(_section_title(title, language))}</h2>'
                f'{layout.paragraphs(texts[idx])}</article>'
            )
        blocks.append(f'<div class="section chapter-pair compact-columns">{"".join(chapter_blocks)}</div>')
    blocks.append(
        f'<div class="section footer-section"><h2>{layout.esc(_text(language, "composed"))}</h2>'
        + _closing_block(order, data, brand, language)
        + _ticket_block(order.promo_code, bot_username, language)
        + f'<p class="disclaimer">{layout.esc(brand["disclaimer"])}</p></div>')
    return layout.document(f"{cover_title} — {order.name}", blocks, lang=language)


async def build_natal_pdf_bytes(db, user: dict) -> bytes:
    """Собрать PDF-разбор натальной карты из профиля пользователя.

    Используется API-эндпоинтом и ботом (ТГ / миниап). Генерирует HTML
    через builder.generate(), затем рендерит PDF через WeasyPrint.
    """
    from . import render
    order = Order(
        name=user["name"] or "—",
        birth_date=user["birth_date"],
        birth_time=user.get("birth_time") or None,
        birth_city=user.get("birth_city") or None,
        lang=user.get("lang") or "ru",
    )
    html = await generate(db, order, bot_username="oracleAI")
    return render.to_pdf_bytes(html)
