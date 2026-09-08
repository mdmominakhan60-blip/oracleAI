"""Human-first natal-chart content contract (BUS-501 §1/§17, BUS-523, v2).

Layering rule of the spec: human meaning first, astrological explanation
second. The LLM produces only the human-language block texts under the same
closed-evidence discipline as ``chart_interpretation`` (v1). Everything the
spec demands as product structure — profile scales, question hooks, block
CTAs and the render order — is computed here deterministically by code.

The v1 technical contract stays available as the collapsed "астрологическая
основа" second level; nothing astrological is deleted.
"""
from __future__ import annotations

import json
import re
from typing import Any

from . import interpretation

CONTRACT_VERSION = 2

BLOCKS = (
    "who_you_are", "strengths", "obstacles", "love", "career", "purpose", "profile",
)

LIMITS = {
    "who_you_are": 900,
    "strengths_item": 280,
    "obstacles_item": 280,
    "love_field": 400,
    "career_field": 400,
    "purpose_human": 700,
    "purpose_detail": 600,
    "profile_summary": 500,
}

_LOVE_FIELDS = (
    ("showing_feelings", "Как ты проявляешь чувства"),
    ("needs_from_partner", "Что тебе нужно от партнёра"),
    ("attracted_to", "Что тебя привлекает"),
    ("breaks_relationships", "Что может разрушать отношения"),
    ("partner_archetype", "Какой тип партнёра подходит тебе"),
)

_CAREER_FIELDS = (
    ("where_you_thrive", "Где ты раскрываешься лучше всего"),
    ("work_style", "Какой тип работы тебе подходит"),
    ("motivation", "Что тебя мотивирует"),
    ("decision_style", "Как ты принимаешь решения"),
    ("growth_potential", "Где твой потенциал для роста"),
    ("career_mistakes", "Какие ошибки мешают карьере"),
)

_SCALE_META = (
    ("identity", "Личность"),
    ("emotions", "Эмоции"),
    ("relationships", "Отношения"),
    ("ambition", "Амбиции"),
    ("intuition", "Интуиция"),
)

DISCLAIMER = "Натальная карта — язык самонаблюдения, а не диагноз и не гарантия будущего."

_HOUSE_REF = re.compile(
    r"(?<!\w)(?:[1-9]|1[0-2])\s*(?:-|‑)?(?:й|ый|ой)?\s*дом(?:е|а|ов)?\b", re.I
)
# Hard spec rule: human blocks speak without astrological vocabulary. Only the
# purpose details ("Подробнее: Раху…") may name the lunar nodes.
_HUMAN_FORBIDDEN = tuple(name for name in interpretation.KNOWN_CHART_POINTS
                         if name not in {"Раху", "Кету"}) + tuple(interpretation.KNOWN_ASPECT_WORDS)

_SIGN_ELEMENT = {
    "Овен": "огонь", "Телец": "земля", "Близнецы": "воздух", "Рак": "вода",
    "Лев": "огонь", "Дева": "земля", "Весы": "воздух", "Скорпион": "вода",
    "Стрелец": "огонь", "Козерог": "земля", "Водолей": "воздух", "Рыбы": "вода",
}

_TENSE = ("квадрат", "оппозиция")
_HARMONIOUS = ("трин", "секстиль")
_ANY = ("соединение", "оппозиция", "трин", "квадрат", "секстиль")


def _schema() -> dict[str, Any]:
    def field(max_len: int) -> dict[str, Any]:
        return {"type": "string", "maxLength": max_len}

    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["who_you_are", "strengths", "obstacles", "love", "career", "purpose", "profile_summary"],
        "properties": {
            "who_you_are": field(LIMITS["who_you_are"]),
            "strengths": {"type": "array", "minItems": 3, "maxItems": 5,
                          "items": {"type": "string", "maxLength": LIMITS["strengths_item"]}},
            "obstacles": {"type": "array", "minItems": 2, "maxItems": 4,
                          "items": {"type": "string", "maxLength": LIMITS["obstacles_item"]}},
            "love": {"type": "object", "additionalProperties": False,
                     "required": [key for key, _ in _LOVE_FIELDS],
                     "properties": {key: field(LIMITS["love_field"]) for key, _ in _LOVE_FIELDS}},
            "career": {"type": "object", "additionalProperties": False,
                       "required": [key for key, _ in _CAREER_FIELDS],
                       "properties": {key: field(LIMITS["career_field"]) for key, _ in _CAREER_FIELDS}},
            "purpose": {"type": "object", "additionalProperties": False,
                        "required": ["human", "rahu_detail", "ketu_detail"],
                        "properties": {
                            "human": field(LIMITS["purpose_human"]),
                            "rahu_detail": field(LIMITS["purpose_detail"]),
                            "ketu_detail": field(LIMITS["purpose_detail"]),
                        }},
            "profile_summary": field(LIMITS["profile_summary"]),
        },
    }


# ---------------------------------------------------------------- chart helpers

def _planet(chart: dict, name: str) -> dict:
    return next((item for item in chart.get("planets") or [] if item.get("name") == name), {})


def _has_aspect(chart: dict, p1: str, p2: str, codes: tuple[str, ...]) -> bool:
    return any(
        {a.get("p1"), a.get("p2")} == {p1, p2} and a.get("aspect") in codes
        for a in chart.get("aspects") or []
    )


def _node(chart: dict, prefix: str) -> dict:
    return next((item for item in chart.get("nodes") or []
                 if str(item.get("name", "")).startswith(prefix)), {})


def _house_of(chart: dict, planet_name: str) -> int | None:
    planet = _planet(chart, planet_name)
    house = planet.get("house")
    return int(house) if house else None


# ---------------------------------------------------------------- profile scales

def _clamp(value: float) -> int:
    return int(max(10, min(95, round(value))))


def _score_identity(chart: dict, *, time_known: bool) -> tuple[int, list[str]]:
    sun = _planet(chart, "Солнце")
    element = _SIGN_ELEMENT.get(sun.get("sign") or "", "")
    drivers: list[str] = []
    score = 45.0
    element_score = {"огонь": 14, "воздух": 10, "земля": 7, "вода": 6}.get(element, 0)
    if element_score:
        score += element_score
        drivers.append(f"ядро воли в {element}-м знаке")
    harmonious = sum(1 for other in ("Луна", "Меркурий", "Венера", "Марс", "Юпитер")
                     if _has_aspect(chart, "Солнце", other, _HARMONIOUS))
    tense = sum(1 for other in ("Луна", "Меркурий", "Венера", "Марс", "Сатурн")
                if _has_aspect(chart, "Солнце", other, _TENSE))
    if harmonious:
        score += 8 * min(2, harmonious)
        drivers.append("внутренние опоры согласованы между собой")
    if tense:
        score -= 6 * min(2, tense)
        drivers.append("есть внутреннее напряжение, которое требует выбора")
    if time_known and chart.get("ascendant"):
        score += 5
        drivers.append("образ и воля читаются надёжнее с подтверждённым временем рождения")
    return _clamp(score), drivers or ["базовый профиль по положению светил"]


def _score_emotions(chart: dict, *, time_known: bool) -> tuple[int, list[str]]:
    moon = _planet(chart, "Луна")
    element = _SIGN_ELEMENT.get(moon.get("sign") or "", "")
    drivers: list[str] = []
    score = 45.0
    element_score = {"вода": 16, "земля": 9, "огонь": 8, "воздух": 6}.get(element, 0)
    if element_score:
        score += element_score
        drivers.append(f"эмоциональный ритм в {element}-м знаке")
    if _has_aspect(chart, "Луна", "Нептун", _ANY):
        score += 10
        drivers.append("чуткость к настроениям других людей")
    if _has_aspect(chart, "Луна", "Сатурн", _TENSE):
        score += 6
        drivers.append("сдержанность в проявлении чувств")
    if _has_aspect(chart, "Луна", "Плутон", _ANY):
        score += 7
        drivers.append("эмоциональные глубины и сильные привязанности")
    return _clamp(score), drivers or ["базовый профиль по положению Луны"]


def _score_relationships(chart: dict, *, time_known: bool) -> tuple[int, list[str]]:
    venus = _planet(chart, "Венера")
    element = _SIGN_ELEMENT.get(venus.get("sign") or "", "")
    drivers: list[str] = []
    score = 45.0
    element_score = {"воздух": 12, "вода": 12, "огонь": 8, "земля": 8}.get(element, 0)
    if element_score:
        score += element_score
        drivers.append(f"язык привязанности в {element}-м знаке")
    venus_aspects = sum(1 for other in ("Луна", "Марс", "Сатурн", "Плутон")
                        if _has_aspect(chart, "Венера", other, _ANY))
    if venus_aspects:
        score += 6 * min(3, venus_aspects)
        drivers.append("тема близости занимает заметное место в карте")
    if _has_aspect(chart, "Венера", "Марс", _ANY):
        drivers.append("притяжение и страсть идут в паре")
    if time_known and chart.get("ascendant"):
        score += 5
        drivers.append("зона партнёрства определена по дому отношений")
    return _clamp(score), drivers or ["базовый профиль по положению Венеры"]


def _score_ambition(chart: dict, *, time_known: bool) -> tuple[int, list[str]]:
    mars = _planet(chart, "Марс")
    element = _SIGN_ELEMENT.get(mars.get("sign") or "", "")
    drivers: list[str] = []
    score = 45.0
    element_score = {"огонь": 16, "земля": 12, "воздух": 7, "вода": 7}.get(element, 0)
    if element_score:
        score += element_score
        drivers.append(f"способ действовать в {element}-м знаке")
    if _has_aspect(chart, "Марс", "Сатурн", _ANY):
        score += 7
        drivers.append("напор соединён с дисциплиной")
    if _has_aspect(chart, "Марс", "Юпитер", _ANY):
        score += 6
        drivers.append("склонность браться за масштабное")
    if time_known and chart.get("mc"):
        score += 4
        drivers.append("профессиональный вектор определён по MC")
    return _clamp(score), drivers or ["базовый профиль по положению Марса"]


def _score_intuition(chart: dict, *, time_known: bool) -> tuple[int, list[str]]:
    drivers: list[str] = []
    score = 45.0
    water = sum(1 for name in ("Солнце", "Луна", "Меркурий", "Венера")
                if _SIGN_ELEMENT.get(_planet(chart, name).get("sign") or "") == "вода")
    if water:
        score += 5 * water
        drivers.append(f"{water} из ключевых точек — в водной стихии")
    if _has_aspect(chart, "Луна", "Нептун", _ANY):
        score += 12
        drivers.append("считывание невербальных сигналов")
    mercury_element = _SIGN_ELEMENT.get(_planet(chart, "Меркурий").get("sign") or "", "")
    if mercury_element == "вода":
        score += 6
        drivers.append("мышление начинается с ощущения, а не с логики")
    if time_known:
        occupied = sum(1 for name in ("Луна", "Венера", "Меркурий")
                       if _house_of(chart, name) in {8, 12})
        if occupied:
            score += 6 * occupied
            drivers.append("важная часть жизни живёт во внутренних, скрытых зонах")
    return _clamp(score), drivers or ["базовый профиль по стихиям карты"]


_SCORERS = {
    "identity": _score_identity,
    "emotions": _score_emotions,
    "relationships": _score_relationships,
    "ambition": _score_ambition,
    "intuition": _score_intuition,
}


def profile_scales(chart: dict, *, time_known: bool) -> dict:
    """Deterministic profile scales. Value = how prominent the theme is in the
    chart (0-100), not a quality grade. Every scale carries its drivers so the
    UI can explain «почему такая полоска» without inventing anything."""
    scales = []
    for key, label in _SCALE_META:
        value, drivers = _SCORERS[key](chart, time_known=time_known)
        scales.append({"key": key, "label": label, "value": value, "drivers": drivers})
    return {
        "scale_range": [0, 100],
        "semantics": "выраженность темы в карте, не оценка «хорошо/плохо»",
        "scales": scales,
        "time_known": bool(time_known),
    }


# ---------------------------------------------------------------- question hooks

def question_hooks(chart: dict, *, time_known: bool, limit: int = 5) -> list[dict]:
    """Auto-generate curiosity hooks from actual chart factors. Each hook carries
    the evidence that selected it, so hooks are always personalized, never a
    static list (BUS-501 §1.11)."""
    hooks: list[dict] = []

    def add(hook_id: str, question: str, block: str, evidence: str) -> None:
        hooks.append({"id": hook_id, "question": question, "block": block, "evidence": evidence})

    if (_has_aspect(chart, "Венера", "Сатурн", ("соединение", *_TENSE))
            or _has_aspect(chart, "Луна", "Сатурн", _TENSE)
            or _has_aspect(chart, "Луна", "Плутон", ("соединение", *_TENSE))):
        add("trust", "Почему тебе сложно доверять людям?", "love",
            "напряжение между близостью и осторожностью в карте")
    if (_has_aspect(chart, "Венера", "Марс", _TENSE)
            or _has_aspect(chart, "Венера", "Юпитер", _TENSE)
            or (time_known and _house_of(chart, "Сатурн") == 2)):
        add("money_leaks", "Где ты теряешь деньги?", "career",
            "напряжённая связка темы ресурсов и желаний")
    if _node(chart, "Раху"):
        add("rahu", "Что показывает твой Раху — и почему ты часто начинаешь всё с нуля?", "purpose",
            "ось Раху/Кету: привычный сценарий против направления роста")
    if (_has_aspect(chart, "Луна", "Плутон", _ANY)
            or _has_aspect(chart, "Венера", "Плутон", _ANY)
            or _planet(chart, "Венера").get("sign") == "Скорпион"
            or _planet(chart, "Луна").get("sign") == "Скорпион"):
        add("attraction", "Почему тебя тянет к определённым людям — и что это говорит о твоих потребностях?", "love",
            "интенсивная связка привязанности и глубины")
    if (_has_aspect(chart, "Марс", "Сатурн", _TENSE)
            or _has_aspect(chart, "Марс", "Юпитер", _TENSE)
            or (time_known and _house_of(chart, "Марс") == 12)):
        add("burnout", "Почему ты выгораешь на старте новых дел?", "obstacles",
            "напряжение между импульсом и сдерживающей силой")
    if (_has_aspect(chart, "Солнце", "Юпитер", ("соединение", *_HARMONIOUS))
            or _SIGN_ELEMENT.get(_planet(chart, "Юпитер").get("sign") or "") == "огонь"):
        add("potential", "Как раскрыть твой потенциал?", "strengths",
            "сильная связка воли и роста")
    mercury_element = _SIGN_ELEMENT.get(_planet(chart, "Меркурий").get("sign") or "", "")
    if mercury_element == "вода" or _has_aspect(chart, "Меркурий", "Сатурн", _ANY):
        add("decisions", "Почему в решениях ты сначала чувствуешь, а потом объясняешь?", "career",
            "чувствительный стиль мышления в карте")

    # Personalized fallbacks: hooks stay chart-tied even without tense aspects.
    if len(hooks) < 3:
        add("portrait", "Почему я веду себя именно так?", "who_you_are",
            "Солнце и Луна задают два разных ритма поведения")
    if len(hooks) < 3:
        add("partner", "Какой человек тебе действительно подходит?", "love",
            "потребности привязанности видны из Венеры и Луны")
    if len(hooks) < 3:
        add("career_fit", "Какой тип работы тебе действительно подходит?", "career",
            "стиль действия виден из Марса и MC")

    return hooks[:limit]


# ---------------------------------------------------------------- validation

def _forbidden_in(text: str) -> list[str]:
    lowered = text.lower()
    found = []
    for name in _HUMAN_FORBIDDEN:
        pattern = rf"(?<!\w){re.escape(name.lower())}(?!\w)"
        if re.search(pattern, lowered):
            found.append(name)
    return found


def validate_payload(payload: dict[str, Any], chart: dict, *, time_known: bool) -> list[str]:
    """Shape, lengths and human-first discipline. Mirrors v1 conservatism."""
    issues: list[str] = []
    schema = _schema()
    missing = set(schema["required"]) - set(payload)
    if missing:
        issues.append("missing keys: " + ", ".join(sorted(missing)))
    extra = set(payload) - set(schema["required"])
    if extra:
        issues.append("unexpected keys: " + ", ".join(sorted(extra)))

    def check_text(label: str, text: Any, max_len: int, *, human: bool) -> None:
        if not isinstance(text, str) or not text.strip():
            issues.append(f"{label} must be a non-empty string")
            return
        if len(text.strip()) > max_len:
            issues.append(f"{label} is too long")
        if human:
            for name in _forbidden_in(text):
                issues.append(f"{label} mentions astrological term outside the technical layer: {name}")
            if _HOUSE_REF.search(text):
                issues.append(f"{label} references a house; houses belong to the technical layer")

    check_text("who_you_are", payload.get("who_you_are"), LIMITS["who_you_are"], human=True)
    strengths = payload.get("strengths")
    if not isinstance(strengths, list) or not (3 <= len(strengths) <= 5) \
            or not all(isinstance(item, str) and item.strip() for item in strengths):
        issues.append("strengths must be a string list of 3-5 items")
    else:
        for index, item in enumerate(strengths):
            check_text(f"strengths[{index}]", item, LIMITS["strengths_item"], human=True)
    obstacles = payload.get("obstacles")
    if not isinstance(obstacles, list) or not (2 <= len(obstacles) <= 4) \
            or not all(isinstance(item, str) and item.strip() for item in obstacles):
        issues.append("obstacles must be a string list of 2-4 items")
    else:
        for index, item in enumerate(obstacles):
            check_text(f"obstacles[{index}]", item, LIMITS["obstacles_item"], human=True)
    for key, label in _LOVE_FIELDS:
        check_text(f"love.{key}", (payload.get("love") or {}).get(key), LIMITS["love_field"], human=True)
    for key, label in _CAREER_FIELDS:
        check_text(f"career.{key}", (payload.get("career") or {}).get(key), LIMITS["career_field"], human=True)
    check_text("profile_summary", payload.get("profile_summary"), LIMITS["profile_summary"], human=True)

    purpose = payload.get("purpose") or {}
    check_text("purpose.human", purpose.get("human"), LIMITS["purpose_human"], human=True)
    has_nodes = bool(_node(chart, "Раху") and _node(chart, "Кету"))
    for key in ("rahu_detail", "ketu_detail"):
        value = purpose.get(key)
        if not has_nodes:
            if isinstance(value, str) and value.strip():
                issues.append(f"purpose.{key} filled without lunar-node evidence")
            continue
        check_text(f"purpose.{key}", value, LIMITS["purpose_detail"], human=False)
        if isinstance(value, str) and _HOUSE_REF.search(value) and not time_known:
            issues.append(f"purpose.{key} claims a house in date-only mode")

    if not time_known:
        blob = json.dumps(payload, ensure_ascii=False)
        if _HOUSE_REF.search(blob):
            issues.append("house claim in date-only interpretation")
    for field_name in ("who_you_are", "profile_summary"):
        value = payload.get(field_name)
        if isinstance(value, str):
            nonfatal = interpretation.validate_nonfatal_text(value)
            issues.extend(nonfatal.issues)
    blob_all = json.dumps(payload, ensure_ascii=False)
    issues.extend("nonfatal: " + issue for issue in
                  interpretation.validate_nonfatal_text(blob_all).issues)
    return issues


# ---------------------------------------------------------------- prompt

def prompt(evidence_block: str, guide: str) -> str:
    love_spec = "; ".join(key for key, _ in _LOVE_FIELDS)
    career_spec = "; ".join(key for key, _ in _CAREER_FIELDS)
    return f"""{guide}

{evidence_block}

Верни только один валидный JSON-объект по схеме ниже, без Markdown и текста до/после JSON.
LLM интерпретирует только проверенные данные выше и не вычисляет градусы, дома, аспекты или периоды самостоятельно.

ПРИНЦИП human-first: сначала человеческий смысл, потом астрология. Все поля кроме purpose.rahu_detail и
purpose.ketu_detail пишутся БЕЗ астрологических терминов: никаких имён планет, аспектов, домов, градусов.
Обращение на «ты». Избегай форм с родом («ты склонен/склонна») — используй конструкции «тебе свойственно»,
«тебе важно», «тебе легко». Никаких обещаний событий и гарантий: карта — язык самонаблюдения.

- who_you_are: короткий портрет личности. Цель — реакция «наконец-то кто-то объяснил меня нормально».
- strengths: 3-5 сильных сторон; каждая — СВЯЗНЫЙ вывод из нескольких факторов evidence, а не случайный набор качеств.
- obstacles: 2-4 пункта «что может мешать тебе»: «Иногда ты…», «Твой главный риск…», как это проявляется в отношениях и в работе.
- love: {love_spec} — конкретно, без типажей-клише.
- career: {career_spec}.
- purpose.human: главный вектор роста человеческим языком («Твоя основная задача — выйти из привычного сценария и…»).
- purpose.rahu_detail и purpose.ketu_detail: технический уровень «Подробнее» — здесь можно назвать Раху/Кету и знак из evidence.
  Если Раху/Кету отсутствуют в evidence, оставь обе строки пустыми.
- profile_summary: одно-два предложения-резюме всего портрета.

JSON schema (contract v2):
{json.dumps(_schema(), ensure_ascii=False, separators=(',', ':'))}
"""


# ---------------------------------------------------------------- B4 contract

_CTA_TEMPLATES = {
    "who_you_are": ("Почему я веду себя именно так?",
                    "Почему я веду себя именно так? Разбери через мою натальную карту."),
    "strengths": ("Как применить мою сильную сторону?",
                  "Как мне применить мои сильные стороны из натальной карты на практике?"),
    "obstacles": ("Как обойти мой главный риск?",
                  "Что может мешать мне и как это обойти? Разбери через мою карту."),
    "love": ("Разобрать мою личную жизнь",
             "Разбери мою личную жизнь: что мне нужно в отношениях и какой партнёр мне подходит."),
    "career": ("Какая профессия мне подходит?",
               "Какая профессия или направление мне подходит? Разбери через мою карту."),
    "purpose": ("Что мне мешает двигаться вперёд?",
                "Что мне мешает двигаться вперёд и каков мой вектор роста?"),
    "profile": ("Собрать полный портрет в чате",
                "Собери полный портрет: как все части моей карты работают вместе?"),
}


def _cta(block: str) -> dict:
    label, prefill = _CTA_TEMPLATES[block]
    return {"label": label, "action": "agent", "agent": "astro", "prefill": prefill}


def build_blocks_contract(payload: dict[str, Any], *, hooks: list[dict],
                          scales: dict, time_known: bool) -> dict[str, Any]:
    """Assemble the data contract handed to B4 (UI). Blocks in render order,
    each with its CTA; question hooks attached; technical layer is a collapsed
    pointer into chart_json, not a duplicate of it."""
    love = {key: {"label": label, "text": (payload.get("love") or {}).get(key, "")}
            for key, label in _LOVE_FIELDS}
    career = {key: {"label": label, "text": (payload.get("career") or {}).get(key, "")}
              for key, label in _CAREER_FIELDS}
    purpose = payload.get("purpose") or {}
    precision_note = ("полный разбор" if time_known
                      else "время рождения не подтверждено: дома и углы скрыты, разбор честно опирается на дату")
    return {
        "contract_version": CONTRACT_VERSION,
        "render_order": list(BLOCKS),
        "blocks": {
            "who_you_are": {"title": "Кто ты", "text": payload.get("who_you_are", ""), "cta": _cta("who_you_are")},
            "strengths": {"title": "Твои сильные стороны",
                          "items": payload.get("strengths") or [], "cta": _cta("strengths")},
            "obstacles": {"title": "Что может мешать тебе",
                          "items": payload.get("obstacles") or [], "cta": _cta("obstacles")},
            "love": {"title": "❤️ Любовь", "fields": love, "cta": _cta("love")},
            "career": {"title": "💼 Карьера", "fields": career, "cta": _cta("career")},
            "purpose": {"title": "✨ Твоя цель", "text": purpose.get("human", ""),
                        "details": {"rahu": purpose.get("rahu_detail", ""),
                                    "ketu": purpose.get("ketu_detail", "")},
                        "cta": _cta("purpose")},
            "profile": {"title": "Твой профиль", "scales": scales.get("scales", []),
                        "semantics": scales.get("semantics"), "summary": payload.get("profile_summary", ""),
                        "cta": _cta("profile")},
        },
        "question_hooks": hooks,
        "technical_layer": {"title": "Астрологическая основа", "display": "collapsed",
                            "source": "chart_json",
                            "includes": ["planets", "houses", "aspects", "nodes", "degrees"]},
        "precision": {"time_known": bool(time_known), "note": precision_note},
        "disclaimer": DISCLAIMER,
    }


# ---------------------------------------------------------------- legacy render

def _bar(value: int) -> str:
    filled = max(0, min(10, round(value / 10)))
    return "█" * filled + "░" * (10 - filled)


def render_human_text(payload: dict[str, Any], hooks: list[dict], scales: dict) -> str:
    """Render human-first Markdown for the legacy rich-text UI and Telegram."""
    love = payload.get("love") or {}
    career = payload.get("career") or {}
    purpose = payload.get("purpose") or {}
    sections = [
        "**1. Кто ты**\n" + str(payload.get("who_you_are", "")).strip(),
        "**2. Твои сильные стороны**\n"
        + "\n".join(f"• {item}" for item in payload.get("strengths") or []),
        "**3. Что может мешать тебе**\n"
        + "\n".join(f"• {item}" for item in payload.get("obstacles") or []),
        "**4. ❤️ Любовь**\n" + "\n".join(
            f"{label}: {(love.get(key) or '').strip()}" for key, label in _LOVE_FIELDS),
        "**5. 💼 Карьера**\n" + "\n".join(
            f"{label}: {(career.get(key) or '').strip()}" for key, label in _CAREER_FIELDS),
        "**6. ✨ Твоя цель**\n" + str(purpose.get("human", "")).strip()
        + ("\n\nПодробнее: " + " ".join(filter(None, (
            f"Раху: {purpose['rahu_detail']}" if purpose.get("rahu_detail") else "",
            f"Кету: {purpose['ketu_detail']}" if purpose.get("ketu_detail") else "",
        ))) if (purpose.get("rahu_detail") or purpose.get("ketu_detail")) else ""),
        "**7. Твой профиль**\n" + "\n".join(
            f"{scale['label']}: {_bar(int(scale['value']))} {scale['value']}"
            for scale in scales.get("scales", [])),
    ]
    if hooks:
        sections.append("**Тебе особенно интересно узнать:**\n"
                        + "\n".join(f"• {hook['question']}" for hook in hooks))
    sections.append(f"_{DISCLAIMER}_")
    return "\n\n".join(section for section in sections if section.strip())
