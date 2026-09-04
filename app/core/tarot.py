"""Колода Таро: 78 карт (22 старших вручную + 56 младших генерируются).

Выбор карт — криптографический рандом (secrets), LLM только трактует.
"""
from __future__ import annotations

import hashlib
import json
import random
import secrets

# Старшие арканы. meaning — архетип с ресурсом и тенью (живая формулировка,
# читается фронтом и ботом как есть). short — короткая подпись для чипов UI.
# advice — практический шаг: что сделать, если выпала эта карта. Тень не
# «отменяет» карту, а называет её оборотную сторону — клиентка не должна
# пугаться карт, трактовка остаётся у LLM.
MAJORS = [
    {"name": "Шут", "emoji": "🃏",
     "meaning": "новое начало, чистый лист, доверие пути; тень — безрассудный прыжок вслепую",
     "short": "новое начало",
     "advice": "сделай маленький шаг в неизвестное — карты уже замешаны за тебя"},
    {"name": "Маг", "emoji": "✨",
     "meaning": "воля и инструменты: всё нужное уже в руках; тень — манипуляция и пустые обещания",
     "short": "сила воли",
     "advice": "действуй, а не обещай: собери ресурсы и начни с одного хода"},
    {"name": "Жрица", "emoji": "🌙",
     "meaning": "глубокое знание внутри, голос тишины; тень — самообман и уход в фантазии",
     "short": "интуиция",
     "advice": "задай вопрос и доверься первому ощущению, а не доводам"},
    {"name": "Императрица", "emoji": "🌹",
     "meaning": "расцвет, изобилие, забота и чувственность; тень — растворяться в других, душащая опека",
     "short": "расцвет",
     "advice": "дай себе удовольствие и полей то, что уже растёт"},
    {"name": "Император", "emoji": "🏛",
     "meaning": "опора, порядок, зрелая ответственность; тень — жёсткий контроль и холод власти",
     "short": "опора и порядок",
     "advice": "построй структуру: ясные правила вылечат хаос лучше, чем героизм"},
    {"name": "Иерофант", "emoji": "📜",
     "meaning": "традиция, наставник, проверенный путь; тень — догма и чужая мораль",
     "short": "наставник",
     "advice": "найди учителя или проверенный метод — не изобретай колесо заново"},
    {"name": "Влюблённые", "emoji": "💞",
     "meaning": "выбор сердца, союз, притяжение; тень — зависимость и выбор из страха",
     "short": "выбор сердца",
     "advice": "выбирай по любви, а не по удобству — цена ошибки проявится позже"},
    {"name": "Колесница", "emoji": "🏇",
     "meaning": "движение, победа, воля к цели; тень — гонка и потеря себя в спешке",
     "short": "движение вперёд",
     "advice": "возьми управление: цель уже есть, осталось вести поводья"},
    {"name": "Сила", "emoji": "🦁",
     "meaning": "мягкая сила, терпение, укрощение внутреннего зверя; тень — подавленные импульсы и вспышки",
     "short": "мягкая сила",
     "advice": "обуздай эмоцию не запретом, а вниманием — страсть станет топливом"},
    {"name": "Отшельник", "emoji": "🕯",
     "meaning": "пауза, поиск смысла, свет собственной лампы; тень — изоляция и страх людей",
     "short": "пауза и смысл",
     "advice": "уединись на день и честно спроси себя, чего ты хочешь на самом деле"},
    {"name": "Колесо Фортуны", "emoji": "🎡",
     "meaning": "поворот судьбы, шанс, смена цикла; тень — пассивное «пусть само»",
     "short": "поворот судьбы",
     "advice": "лови волну: дверь открыта сейчас, а не через месяц"},
    {"name": "Справедливость", "emoji": "⚖️",
     "meaning": "равновесие, честность, последствия решений; тень — суд над собой и чужие оценки",
     "short": "честность",
     "advice": "восстанови баланс: признай свой вклад в ситуацию без самобичевания"},
    {"name": "Повешенный", "emoji": "🙃",
     "meaning": "другой взгляд, добровольная пауза, отпускание; тень — жертвенность и застой",
     "short": "пауза и другой взгляд",
     "advice": "переверни вопрос: что изменится, если просто ничего не делать?"},
    {"name": "Смерть", "emoji": "🦋",
     "meaning": "трансформация, завершение цикла, обновление; тень — страх перемен и застревание в прошлом",
     "short": "перемены",
     "advice": "отпусти то, что отжило, — место под новое освободится само"},
    {"name": "Умеренность", "emoji": "🕊",
     "meaning": "баланс, исцеление, золотая середина; тень — размытость и уход от решений",
     "short": "баланс и исцеление",
     "advice": "смешай крайности: сейчас золотая середина — самое смелое решение"},
    {"name": "Дьявол", "emoji": "⛓",
     "meaning": "страсть, притяжение, теневые связи; тень — зависимость и иллюзия, что цепей нет",
     "short": "страсть и зависимость",
     "advice": "честно назови, что держит тебя на цепи, — имя лишает силы"},
    {"name": "Башня", "emoji": "🌩",
     "meaning": "внезапная правда, слом старого, освобождение; тень — страх руин и цепляние за обломки",
     "short": "крутой перелом",
     "advice": "не строй на старом фундаменте: пусть рухнет — освободится земля"},
    {"name": "Звезда", "emoji": "⭐",
     "meaning": "надежда, вдохновение, свет после бури; тень — мечтательность без действия",
     "short": "надежда",
     "advice": "загадай и запиши: надежда обретает форму, когда ей дают план"},
    {"name": "Луна", "emoji": "🌕",
     "meaning": "иллюзии, страхи, подсознание; тень — тревога и неверная оптика",
     "short": "иллюзии и интуиция",
     "advice": "проверь факты: то, что пугает в темноте, часто меньше при свете дня"},
    {"name": "Солнце", "emoji": "☀️",
     "meaning": "радость, ясность, успех; тень — неумение принимать свет и тщеславие",
     "short": "ясность и успех",
     "advice": "выйди в свет: покажи результат — сегодня тебе позволено быть счастливой"},
    {"name": "Суд", "emoji": "🎺",
     "meaning": "пробуждение, второй шанс, призвание; тень — страх осуждения и повтор прошлого",
     "short": "второй шанс",
     "advice": "услышь зов и ответь: прошлое прощено, если ты выносишь из него урок"},
    {"name": "Мир", "emoji": "🌍",
     "meaning": "целостность, итог, гармония; тень — страх завершения и удержание законченного",
     "short": "целостность",
     "advice": "заверши круг и отпразднуй: цель достигнута, пора открывать новую"},
]

SUITS = {
    "Кубков": ("💧", "чувства и отношения"),
    "Пентаклей": ("🪙", "деньги и материя"),
    "Мечей": ("⚔️", "мысли и конфликты"),
    "Жезлов": ("🔥", "энергия и дело"),
}
RANKS = [
    ("Туз", "чистый потенциал"), ("Двойка", "выбор и баланс"), ("Тройка", "рост"),
    ("Четвёрка", "стабильность"), ("Пятёрка", "испытание"), ("Шестёрка", "гармония"),
    ("Семёрка", "оценка пути"), ("Восьмёрка", "движение"), ("Девятка", "близость итога"),
    ("Десятка", "завершение цикла"), ("Паж", "весть, ученичество"),
    ("Рыцарь", "действие, порыв"), ("Королева", "зрелая энергия"), ("Король", "мастерство"),
]

# Минимумы младших арканов по Райдеру-Уэйту. «Тройка Кубков» — это не «рост»,
# а дружба близких; без своих значений названия вводят в заблуждение.
RWS_MINOR: dict[tuple[str, str], str] = {
    ("Туз", "Кубков"): "новое чувство, щедрость сердца, избыток радости",
    ("Двойка", "Кубков"): "взаимность, притяжение, союз двух",
    ("Тройка", "Кубков"): "дружба, праздник, круг близких",
    ("Четвёрка", "Кубков"): "пресыщенность, неприятие дара",
    ("Пятёрка", "Кубков"): "разочарование, взгляд в прошлое вопреки оставшемуся",
    ("Шестёрка", "Кубков"): "ностальгия, детство, щедрость памяти",
    ("Семёрка", "Кубков"): "выбор между иллюзиями, золотые грезы",
    ("Восьмёрка", "Кубков"): "уход от известного к поиску смысла",
    ("Девятка", "Кубков"): "исполнение желаний, удовлетворённость",
    ("Десятка", "Кубков"): "семейная гармония, счастье дома",
    ("Паж", "Кубков"): "вести о чувствах, первое влюблённое письмо",
    ("Рыцарь", "Кубков"): "романтичный порыв, жест сердца",
    ("Королева", "Кубков"): "эмпатия, глубина чувств, забота",
    ("Король", "Кубков"): "эмоциональная зрелость, владение чувствами",
    ("Туз", "Пентаклей"): "новая денежная возможность, плодородная почва",
    ("Двойка", "Пентаклей"): "лавирование, баланс двух дел",
    ("Тройка", "Пентаклей"): "мастерство, признание за труд",
    ("Четвёрка", "Пентаклей"): "удержание, страх потери, жадность",
    ("Пятёрка", "Пентаклей"): "нужда, трудная полоса, помощь извне",
    ("Шестёрка", "Пентаклей"): "щедрость, помощь, справедливый обмен",
    ("Семёрка", "Пентаклей"): "терпеливый труд, ожидание урожая",
    ("Восьмёрка", "Пентаклей"): "прилежание, оттачивание ремесла",
    ("Девятка", "Пентаклей"): "самодостаточность, материальная свобода",
    ("Десятка", "Пентаклей"): "семейный капитал, наследие, укоренённость",
    ("Паж", "Пентаклей"): "новое дело, начало учёбы, изучение денег",
    ("Рыцарь", "Пентаклей"): "надёжный шаг, неспешный прогресс",
    ("Королева", "Пентаклей"): "практичность, забота о достатке",
    ("Король", "Пентаклей"): "изобилие, управление ресурсами",
    ("Туз", "Мечей"): "ясность, прорыв, новый интеллектуальный старт",
    ("Двойка", "Мечей"): "тупик выбора, намеренное невидение",
    ("Тройка", "Мечей"): "боль сердца, внезапная рана",
    ("Четвёрка", "Мечей"): "передышка, покой вне битвы",
    ("Пятёрка", "Мечей"): "победа ценой отношений, поражение в споре",
    ("Шестёрка", "Мечей"): "переход, движение от бури к тишине",
    ("Семёрка", "Мечей"): "обман, уход от прямого конфликта, ловкость",
    ("Восьмёрка", "Мечей"): "скованность, самосозданные ограничения",
    ("Девятка", "Мечей"): "бессонная тревога, страхи наяву",
    ("Десятка", "Мечей"): "конец тяжёлого цикла, точка за точку",
    ("Паж", "Мечей"): "бдительность, слежка, острый ум",
    ("Рыцарь", "Мечей"): "стремительность, прямой удар",
    ("Королева", "Мечей"): "честность к себе, точный анализ",
    ("Король", "Мечей"): "воля ума, принцип выше эмоций",
    ("Туз", "Жезлов"): "вспышка идеи, импульс к старту",
    ("Двойка", "Жезлов"): "планы, взгляд вдаль, выбор большей цели",
    ("Тройка", "Жезлов"): "предприятие набирает ход, дальний свет",
    ("Четвёрка", "Жезлов"): "праздник, дом, закрепление успеха",
    ("Пятёрка", "Жезлов"): "соперничество, проверка сил",
    ("Шестёрка", "Жезлов"): "признание, победа, триумф",
    ("Семёрка", "Жезлов"): "оборона своих позиций, удержание",
    ("Восьмёрка", "Жезлов"): "стремительные вести, действие без задержки",
    ("Девятка", "Жезлов"): "стража, бдительность после битвы",
    ("Десятка", "Жезлов"): "тяжесть ноши, выгорание от дел",
    ("Паж", "Жезлов"): "искра интереса, сообщение о деле",
    ("Рыцарь", "Жезлов"): "энтузиазм, резкое движение вперёд",
    ("Королева", "Жезлов"): "тёплая уверенность, притягательная сила",
    ("Король", "Жезлов"): "видение, харизма, решимость вести",
}


ROMAN = ["0", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X",
         "XI", "XII", "XIII", "XIV", "XV", "XVI", "XVII", "XVIII", "XIX", "XX", "XXI"]


# Слаг картинки Rider-Waite (селфхост в miniapp/img/tarot/{slug}.jpg):
# младшие — Suit+NN (wands01..14), старшие — mNN. Согласуется с
# /tmp/dl_tarot_deck.py и статикой miniapp/img/tarot/.
_SUIT_SHORT = {"Жезлов": "wands", "Кубков": "cups", "Мечей": "swords", "Пентаклей": "pents"}
_RANK_NUM = {"Туз": "01", "Двойка": "02", "Тройка": "03", "Четвёрка": "04", "Пятёрка": "05",
             "Шестёрка": "06", "Семёрка": "07", "Восьмёрка": "08", "Девятка": "09",
             "Десятка": "10", "Паж": "11", "Рыцарь": "12", "Королева": "13", "Король": "14"}


def full_deck() -> list[dict]:
    deck = [
        {"name": m["name"], "emoji": m["emoji"], "meaning": m["meaning"],
         "short": m.get("short"), "advice": m.get("advice"),
         "arcana": "major", "num": ROMAN[i], "suit": None, "img": f"m{i:02d}"}
        for i, m in enumerate(MAJORS)
    ]
    for suit, (emoji, domain) in SUITS.items():
        for ri, (rank, rmean) in enumerate(RANKS):
            deck.append({
                "name": f"{rank} {suit}",
                "emoji": emoji,
                "meaning": RWS_MINOR.get((rank, suit), f"{rmean} в сфере: {domain}"),
                "arcana": "minor",
                "num": str(ri + 1) if ri < 10 else rank,
                "suit": suit,
                "img": f"{_SUIT_SHORT[suit]}{_RANK_NUM[rank]}",
            })
    return deck


DECK = full_deck()
_DECK_BY_ID = {str(card["img"]): card for card in DECK}
_DECK_BY_NAME = {str(card["name"]): card for card in DECK}

# Legacy rows from earlier builds could persist English RWS names without `img`.
# Resolve only this explicit, complete alias set; never redraw or fuzzy-match data.
_EN_MAJOR_NAMES = [
    "The Fool", "The Magician", "The High Priestess", "The Empress", "The Emperor",
    "The Hierophant", "The Lovers", "The Chariot", "Strength", "The Hermit",
    "Wheel of Fortune", "Justice", "The Hanged Man", "Death", "Temperance",
    "The Devil", "The Tower", "The Star", "The Moon", "The Sun", "Judgement", "The World",
]
_EN_RANKS = ["Ace", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten", "Page", "Knight", "Queen", "King"]
_EN_SUITS = {"Cups": "Кубков", "Pentacles": "Пентаклей", "Swords": "Мечей", "Wands": "Жезлов"}
_LEGACY_NAME_ALIASES = {
    english: card["name"] for english, card in zip(_EN_MAJOR_NAMES, DECK[:22])
}
_LEGACY_NAME_ALIASES.update(
    {
        f"{rank} of {suit}": f"{RANKS[ri][0]} {ru_suit}"
        for suit, ru_suit in _EN_SUITS.items()
        for ri, rank in enumerate(_EN_RANKS)
    }
)


def _canonical_cards(cards: list[dict]) -> list[dict]:
    """Validate persisted draw evidence and strip mutable card presentation fields."""
    if not isinstance(cards, list) or not cards:
        raise ValueError("tarot draw must contain at least one card")
    result: list[dict] = []
    seen: set[str] = set()
    for raw in cards:
        if not isinstance(raw, dict):
            raise ValueError("tarot card evidence must be an object")
        card_id = str(raw.get("img") or "")
        name = str(raw.get("name") or "")
        canonical = _DECK_BY_ID.get(card_id) if card_id else (
            _DECK_BY_NAME.get(name) or _DECK_BY_NAME.get(_LEGACY_NAME_ALIASES.get(name, ""))
        )
        if canonical is None:
            raise ValueError("unknown tarot card evidence")
        if card_id and str(canonical["img"]) != card_id:
            raise ValueError("tarot card id mismatch")
        if (name and str(canonical["name"]) != name
                and _LEGACY_NAME_ALIASES.get(name) != str(canonical["name"])):
            raise ValueError("tarot card name mismatch")
        canonical_id = str(canonical["img"])
        if canonical_id in seen:
            raise ValueError("duplicate tarot card evidence")
        orientation = raw.get("reversed", False)
        if not isinstance(orientation, (bool, int)):
            raise ValueError("tarot card orientation must be boolean")
        seen.add(canonical_id)
        result.append({**canonical, "reversed": bool(orientation)})
    return result


# Расклады.
# `tier`: included — входит в тариф (тратит вопрос дня);
# premium — открывается разовой покупкой или Кристаллами (см. seed.PRODUCTS).
# `guide` — короткое описание, зачем расклад, что он показывает клиентке.
SPREADS: dict[str, dict] = {
    "one": {
        "title": "Одна карта",
        "positions": ["Ответ"],
        "tier": "included",
        "emoji": "🂠",
        "hint": "Быстрый честный ответ на один вопрос",
        "guide": "Одна карта — прямой ответ. Хорошо для ежедневного ритуала "
                 "и когда нужно решение, а не анализ.",
    },
    "three": {
        "title": "Прошлое · Настоящее · Будущее",
        "positions": ["Прошлое", "Настоящее", "Будущее"],
        "tier": "included",
        "emoji": "🂠🂠🂠",
        "hint": "Откуда пришло, где ты сейчас, куда ведёт",
        "guide": "Классика трёх карт: видит нить ситуации — как она сложилась, "
                 "что происходит сейчас и куда движется.",
    },
    "love": {
        "title": "На отношения",
        "positions": ["Ты", "Он/ситуация", "Что между вами", "Совет"],
        "tier": "included",
        "emoji": "💞",
        "hint": "Ты, он и то, что между вами",
        "guide": "Карты по ролям: что приносишь ты, что он/ситуация, какая "
                 "энергия между вами и что сделать, чтобы стало теплее.",
    },
    "choice": {
        "title": "Выбор из двух",
        "positions": ["Путь А", "Плод пути А", "Путь Б", "Плод пути Б",
                      "Чего ты не видишь"],
        "tier": "premium",
        "emoji": "🔀",
        "hint": "Два пути, их плоды и слепое пятно",
        "guide": "Когда стоят два явных варианта: показывает цену и плод каждого "
                 "и вскрывает слепое пятно, из-за которого выбор даётся тяжело.",
    },
    "path": {
        "title": "Выбор пути",
        "positions": ["Чего ты хочешь на самом деле", "Что держит",
                      "Куда зовёт", "Что укрепит на пути", "Первый шаг"],
        "tier": "included",
        "emoji": "🛤️",
        "hint": "Услышать свой зов и сделать первый шаг",
        "guide": "Для развилки в жизни, где нет «А или Б»: отделяет голос сердца "
                 "от страха, называет, что пора отпустить, и подсказывает первый шаг.",
    },
    "money": {
        "title": "Деньги и дело",
        "positions": ["Где твой ресурс", "Что тормозит", "Скрытая возможность",
                      "Первый шаг"],
        "tier": "premium",
        "emoji": "🪙",
        "hint": "Ресурс, тормоз и первый шаг",
        "guide": "Финансовая петля целиком: где твой реальный ресурс, какой "
                 "внутренний тормоз съедает доход, какая возможность прячется "
                 "и с чего начать уже сегодня.",
    },
    "career": {
        "title": "Карьера и путь",
        "positions": ["Где ты сейчас", "Твоя сильная сторона", "Что мешает расти",
                      "Куда ведёт этот путь", "Что сделать первым"],
        "tier": "premium",
        "emoji": "🧭",
        "hint": "Точка роста, тормоз и направление",
        "guide": "Профессиональный вектор: где ты на самом деле, на что опереться, "
                 "что тормозит рост и куда ведёт нынешняя траектория.",
    },
    "work": {
        "title": "Проблемы на работе",
        "positions": ["Суть конфликта", "Твоя роль в нём", "Чего ты не видишь",
                      "К кому прислушаться", "Чего избегать", "Как выйти достойно"],
        "tier": "premium",
        "emoji": "⚖️",
        "hint": "Кому верить, чего избегать, как выйти",
        "guide": "Рабочий конфликт до дна: суть, твоя роль, слепое пятно, "
                 "советчики и сценарий достойного выхода без потери лица.",
    },
    "celtic": {
        "title": "Кельтский крест",
        "positions": ["Суть ситуации", "Что мешает", "Подсознание", "Прошлое",
                      "Осознанное", "Ближайшее будущее", "Ты в ситуации",
                      "Окружение", "Надежды и страхи", "Итог"],
        "tier": "premium",
        "emoji": "✝️",
        "hint": "Десять карт — полная картина",
        "guide": "Практически карта жизни на текущий момент: ситуация, подтекст, "
                 "прошлое и окружение — самый глубокий и полный разбор.",
    },
    "year": {
        "title": "Колесо года",
        "positions": ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
                      "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"],
        "tier": "premium",
        "emoji": "🎡",
        "hint": "По карте на каждый месяц",
        "guide": "Атмосфера каждого месяца наступающего года: где энергия, где "
                 "передышка и на какие месяцы планировать важное.",
    },
}

DEFAULT_SPREAD = "three"
TAROT_REPLAY_CONTRACT = {
    "version": "tarot-replay-v1",
    "mode": "immutable_cards",
    "source": "server_persisted_cards_json",
    "deterministic": True,
    "note": "Replay rebuilds the ledger from persisted card IDs, positions and orientations; it never redraws cards.",
}


def spread(code: str) -> dict:
    """Расклад по коду с безопасным значением по умолчанию."""
    item = SPREADS.get(code) or SPREADS[DEFAULT_SPREAD]
    return {**item, "code": code if code in SPREADS else DEFAULT_SPREAD}


def spread_by_title(title: str) -> dict:
    """Обратный поиск: старые записи в БД хранили только название расклада."""
    for code, item in SPREADS.items():
        if item["title"] == title:
            return {**item, "code": code}
    return spread(DEFAULT_SPREAD)


_RNG = secrets.SystemRandom()


def draw(n: int = 3, *, seed: str | None = None) -> list[dict]:
    """n разных карт в случайном порядке; optional seed is for reproducible tests.

    Порядок важен: карты ложатся на позиции расклада (Прошлое/Настоящее/Будущее),
    поэтому берём sample, а не set — у множества порядок обхода определяется
    слотом хеша, и первая карта оказывалась привязана к её месту в колоде.
    """
    if not isinstance(n, int) or isinstance(n, bool) or not 1 <= n <= len(DECK):
        raise ValueError(f"tarot draw size must be between 1 and {len(DECK)}")
    cards = []
    rng = random.Random(seed) if seed is not None else _RNG
    for card in rng.sample(DECK, n):
        card = dict(card)
        # честная тасовка: каждая карта ложится прямо или перевёрнуто ~50/50
        card["reversed"] = bool(rng.getrandbits(1))
        cards.append(card)
    return cards


def _combination_rule(left: dict, right: dict) -> str:
    """Return a bounded traditional cue tied to the adjacent cards, never an unsupported claim."""
    names = {str(left.get("name", "")), str(right.get("name", ""))}
    if {"Смерть", "Башня"} <= names:
        return "transformational_pressure"
    if {"Влюблённые", "Двойка Кубков"} <= names:
        return "relationship_choice"
    if {"Звезда", "Солнце"} <= names:
        return "hope_and_clarity"
    if {"Дьявол", "Луна"} <= names:
        return "attachment_and_ambiguity"
    if left.get("suit") and left.get("suit") == right.get("suit"):
        return "same_suit_cluster"
    if bool(left.get("reversed")) != bool(right.get("reversed")):
        return "orientation_tension"
    return "adjacent_cards_read_together"


DECK_META = {
    "tarot": {"id": "rws-78-v1", "tradition": "Rider-Waite-Smith"},
    "lenormand": {"id": "mary-el-78-v1", "tradition": "Mary-El / Lenormand"},
}


def reading_ledger(cards: list[dict], spread_code: str = "three",
                   positions: list[str] | None = None,
                   deck: str = "tarot") -> dict:
    """Create user-safe deterministic evidence for a validated draw."""
    meta = DECK_META.get(deck or "tarot", DECK_META["tarot"])
    deck_id = meta["id"]
    canonical_cards = _canonical_cards(cards)
    item = spread(spread_code)
    canonical_spread = item["code"]
    positions = (positions or item["positions"])[:len(canonical_cards)]
    entries = []
    for index, card in enumerate(canonical_cards):
        entries.append({
            "index": index,
            "position": positions[index] if index < len(positions) else f"Карта {index + 1}",
            "card_id": card.get("img") or card.get("name"),
            "name": card.get("name"),
            "arcana": card.get("arcana"),
            "suit": card.get("suit"),
            "reversed": bool(card.get("reversed")),
            "orientation": "reversed" if card.get("reversed") else "upright",
        })
    combinations = []
    for left, right in zip(canonical_cards, canonical_cards[1:]):
        combinations.append({
            "left": left.get("name"), "right": right.get("name"),
            "rule": _combination_rule(left, right),
            "type": "adjacent_pair",
        })
    canonical = json.dumps({"deck_id": deck_id, "spread": canonical_spread,
                            "entries": entries}, ensure_ascii=False,
                           sort_keys=True, separators=(",", ":"))
    return {
        "version": "tarot-ledger-v1",
        "deck_id": deck_id,
        "deck": deck or "tarot",
        "tradition": meta["tradition"],
        "spread": canonical_spread,
        "entries": entries,
        "adjacent_combinations": combinations,
        "checksum": hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16],
        "interpretation_boundary": "Cards and positions are calculated evidence; meanings are read through the spread's traditional language and position.",
        "replay": {**TAROT_REPLAY_CONTRACT, "checksum": hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]},
    }


def replay_ledger(cards: list[dict], spread_code: str,
                  expected_checksum: str | None = None,
                  deck: str = "tarot") -> dict:
    """Rebuild a draw ledger without drawing again and verify its checksum.

    The database stores the drawn cards before interpretation. A replay therefore
    must be a pure reconstruction from that immutable evidence, not a new call to
    the random generator. The optional checksum lets callers detect tampering or
    accidental changes to a historical payload.
    """
    ledger = reading_ledger(cards, spread_code, deck=deck)
    if expected_checksum is not None and ledger["checksum"] != expected_checksum:
        raise ValueError("tarot ledger checksum mismatch")
    return ledger


def cards_text(cards: list[dict], positions: list[str] | None = None) -> str:
    lines = []
    for i, c in enumerate(cards):
        pos = f"{positions[i]}: " if positions and i < len(positions) else ""
        rev = " (перевёрнутая)" if c["reversed"] else ""
        lines.append(f"{pos}{c['emoji']} {c['name']}{rev} — {c['meaning']}")
    return "\n".join(lines)
