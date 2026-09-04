"""Дневник: записи, стрик, вечерний вопрос от Оракула.

Практики живут в отдельном роутере (`practices.py`) — это самостоятельный
раздел продукта с программой по дням, а не придаток дневника.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from ...core import astro, memory
from ...services.repo_gateway import dialog, users
from ...services import analytics
from ..deps import confirmed_age_user, get_db, rate_limit

router = APIRouter(prefix="/api", tags=["diary"])


class DiaryIn(BaseModel):
    text: str = Field(min_length=1, max_length=1000)
    mood: str | None = Field(default=None, max_length=20)


@router.get("/diary")
async def diary_list(user=Depends(confirmed_age_user), db=Depends(get_db)):
    entries = await dialog.get_diary(db, user["tg_id"], limit=60)
    return {"entries": entries,
            "streak": await dialog.diary_streak(db, user["tg_id"])}


_MOOD_ENTRY_CUES = {
    "спокойно": "Можно заметить, что уже даёт тебе устойчивость, и не торопить следующий шаг.",
    "радостно": "Разреши этому свету побыть рядом: назови, что именно сегодня тебя поддержало.",
    "напряжённо": "Не обязательно решать всё сразу. Сначала выбери одну маленькую вещь, которую можно отпустить на сегодня.",
    "устало": "Сделай ставку на минимум: вода, пауза, сон или просьба о поддержке — уже достаточно.",
    "неясно": "Попробуй не искать готовый ответ, а оставить вопрос открытым ещё на один спокойный вдох.",
}


def _entry_reflection(moon: dict, mood: str | None) -> str:
    """Короткий ориентир после записи: факт фазы + бережный, не-предсказательный шаг."""
    cue = _MOOD_ENTRY_CUES.get(mood or "")
    if cue:
        return (f"Сегодня {moon['name'].lower()} · примерно {moon['day']}-й лунный день. "
                f"{cue}")
    return (f"Сегодня {moon['name'].lower()} · примерно {moon['day']}-й лунный день. "
            f"Твой ориентир фазы: {moon['advice'].capitalize()}.")


@router.post("/diary", dependencies=[Depends(rate_limit("write"))])
async def diary_add(item: DiaryIn, user=Depends(confirmed_age_user), db=Depends(get_db)):
    """Сохраняет личную заметку и возвращает краткий ориентир текущей лунной фазы."""
    text = item.text.strip()[:1000]
    await dialog.add_diary(db, user["tg_id"], text, mood=item.mood)
    # Дневник остаётся личной записью всегда; в память проводников он попадает
    # только по явному разрешению пользовательницы в настройках приватности.
    if user["memory_enabled"]:
        await memory.remember(db, user["tg_id"], f"Из дневника: {text[:150]}",
                              kind="event")
    moon = astro.moon_phase(date.fromisoformat(users.user_today(user)))
    await analytics.track(db, "diary_write", user["tg_id"], surface="miniapp")
    return {
        "ok": True,
        "streak": await dialog.diary_streak(db, user["tg_id"]),
        "moon": {key: moon[key] for key in ("name", "emoji", "day")},
        "reflection": _entry_reflection(moon, item.mood),
    }


@router.get("/diary/prompt")
async def diary_prompt(user=Depends(confirmed_age_user), db=Depends(get_db)):
    """Вечерний вопрос от Оракула — чтобы дневник не был пустым полем.

    Вопрос зависит от того, писала ли она сегодня и есть ли у неё стрик:
    пустое поле «расскажи, как день» люди не заполняют, а конкретный вопрос —
    заполняют.
    """
    entries = await dialog.get_diary(db, user["tg_id"], limit=1)
    streak = await dialog.diary_streak(db, user["tg_id"])
    today = users.user_today(user)
    written_today = False
    if entries and entries[0]["created_at"]:
        # created_at в UTC, а «сегодня» — по зоне клиентки: вечером UTC
        # ещё вчера, и сравнение по подстроке даёт ложный False
        local = datetime.fromisoformat(entries[0]["created_at"]).astimezone(
            users.user_tz(user))
        written_today = local.strftime("%Y-%m-%d") == today
    return {
        "written_today": written_today,
        "streak": streak,
        "prompt": _prompt_for(streak, written_today),
    }


_PROMPTS_FIRST = [
    "С чего начнём? Расскажи, что сегодня было самым важным.",
    "Что сегодня отняло больше всего сил — и что вернуло?",
    "Если бы у сегодняшнего дня было одно слово, какое?",
]
_PROMPTS_REGULAR = [
    "Что сегодня получилось лучше, чем ты ожидала?",
    "О чём ты думала сегодня чаще всего?",
    "Что тебя сегодня задело — и почему именно это?",
    "Кому сегодня хотелось написать, но ты не стала?",
    "За что сегодня можешь сказать себе спасибо?",
]
_PROMPTS_STREAK = [
    "Ты пишешь уже который день. Что изменилось с первой записи?",
    "Что повторяется в твоих днях последнюю неделю?",
    "Если посмотреть на неделю целиком — куда она тебя ведёт?",
]


def _prompt_for(streak: int, written_today: bool) -> str:
    """Детерминированный выбор: вопрос не должен меняться при каждом обновлении."""
    from ...core.stable import stable_seed
    if written_today:
        return "Сегодня уже записано ✨ Хочешь добавить ещё что-то?"
    pool = (_PROMPTS_STREAK if streak >= 5 else
            _PROMPTS_REGULAR if streak >= 1 else _PROMPTS_FIRST)
    return pool[stable_seed(str(streak), "diary") % len(pool)]


# ─────────────────────── месячная сводка «что показала Вселенная» ─────────────
# Счётчики и темы считает код, а не LLM: текст итога пишет агент, но факты —
# реальные. Так сводка не выдумывает, сколько записей было и о чём они.

_THEMES = {
    "отношения": ["любов", "партнёр", "партнер", "муж", "отношени", "расставан",
                  "вместе", "свидан", "бывший", "одино", "с ним"],
    "деньги и работа": ["деньг", "работ", "зарплат", "долг", "плат", "заказ",
                        "клиент", "проект", "начальн", "коллег", "отпуск", "увольн"],
    "самочувствие": ["сон", "спать", "устал", "болит", "болею", "врач", "голова",
                     "тревог", "паник"],
    "энергия и практика": ["практик", "мантр", "медитац", "энерг", "восстанов",
                           "зарядил", "утром", "настроил"],
    "дом и близкие": ["мам", "пап", "семь", "дома", "домой", "ребен", "ребён",
                      "подруг", "родител", "сестр", "брат"],
}
_CHANGE_WORDS = ("изменил", "перестал", "наконец", "по-другому", "решила",
                 "поняла", "отпустил", "начала", "смел", "смогла")
_STOPWORDS = {
    "что", "как", "это", "меня", "мне", "было", "будет", "себя", "для", "она",
    "его", "ее", "её", "так", "уже", "все", "когда", "если", "очень", "еще",
    "ещё", "только", "быть", "стала", "был", "были", "потом", "сейчас", "сегодня",
}


def _month_bounds(month: str) -> tuple[str, str]:
    """Начало и конец месяца в UTC — окно записей для сводки."""
    start = datetime.strptime(month, "%Y-%m").replace(tzinfo=timezone.utc)
    nxt = (start.replace(year=start.year + 1, month=1)
           if start.month == 12 else start.replace(month=start.month + 1))
    return start.isoformat(), nxt.isoformat()


def _themes_of(entries: list[dict]) -> list[dict]:
    counts = {t: 0 for t in _THEMES}
    for e in entries:
        text = (e.get("text") or "").lower()
        for theme, kws in _THEMES.items():
            if any(k in text for k in kws):
                counts[theme] += 1
    return [{"theme": t, "count": c} for t, c in counts.items() if c]


def _top_words(entries: list[dict], limit: int = 8) -> list[list]:
    freq: dict[str, int] = {}
    for e in entries:
        for w in re.findall(r"[а-яё]{3,}", (e.get("text") or "").lower()):
            if w not in _STOPWORDS:
                freq[w] = freq.get(w, 0) + 1
    return [list(pair) for pair in
            sorted(freq.items(), key=lambda kv: kv[1], reverse=True)[:limit]]


def _max_streak(days: set[str]) -> int:
    """Лучшая серия дней подряд в месяце."""
    ordered = sorted(days)
    best = run = 0
    prev = None
    for d in ordered:
        run = run + 1 if (prev and (date.fromisoformat(d)
                                    - date.fromisoformat(prev)).days == 1) else 1
        best = max(best, run)
        prev = d
    return best


@router.get("/diary/summary")
async def diary_summary(month: str | None = Query(default=None),
                        user=Depends(confirmed_age_user), db=Depends(get_db)):
    """Месячная сводка: сколько записей, о чём, что менялось.

    Отдаёт факты и структуру для LLM (поле `data_for_prompt`), а не готовый
    текст: «Книгу судьбы» формулирует Оракул, но не выдумывает цифры.
    """
    month = month or datetime.now(timezone.utc).strftime("%Y-%m")
    try:
        start_iso, end_iso = _month_bounds(month)
    except ValueError:
        return {"month": month, "empty": True, "error": "bad month"}

    entries = await dialog.diary_entries_between(db, user["tg_id"], start_iso, end_iso)
    if not entries:
        return {"month": month, "empty": True, "count": 0, "days_written": 0,
                "themes": [], "moods": {}, "data_for_prompt": ""}

    days = {e["created_at"][:10] for e in entries if e["created_at"]}
    moods: dict[str, int] = {}
    for e in entries:
        if e.get("mood"):
            moods[e["mood"]] = moods.get(e["mood"], 0) + 1

    def _day_num(entry) -> int:
        try:
            return int(datetime.fromisoformat(entry["created_at"]).day)
        except ValueError:
            return 16

    first_half = sum(1 for e in entries if _day_num(e) <= 15)
    second_half = len(entries) - first_half
    direction = ("up" if second_half > first_half else
                 "down" if second_half < first_half else "stable")
    changes = sum(1 for e in entries
                  if any(w in (e.get("text") or "").lower() for w in _CHANGE_WORDS))

    themes = _themes_of(entries)
    repeated = [t["theme"] for t in themes if t["count"] >= 2]
    first, last = entries[0], entries[-1]
    def snippet(entry):
        return (entry.get("text") or "")[:120]

    themes_line = (", ".join(f"{t['theme']} — {t['count']}" for t in themes)
                   or "нет явных")
    data_for_prompt = (
        f"Записей за месяц: {len(entries)} (на {len(days)} дней, "
        f"лучшая серия — {_max_streak(days)} подряд). "
        f"Темы: {themes_line}. "
        f"Настроения: {', '.join(f'{k} — {v}' for k, v in moods.items()) or 'не отмечались'}. "
        f"Динамика: первая половина {first_half}, вторая {second_half} записей. "
        f"Слов про перемены — {changes}. "
        f"Первая запись: «{snippet(first)}». Последняя: «{snippet(last)}»."
    )

    return {
        "month": month,
        "empty": False,
        "count": len(entries),
        "days_written": len(days),
        "streak_max": _max_streak(days),
        "moods": moods,
        "themes": themes,
        "repeated_themes": repeated,
        "top_words": _top_words(entries),
        "trend": {"first_half": first_half, "second_half": second_half,
                  "direction": direction},
        "changes": changes,
        "first": {"date": first["created_at"], "text": snippet(first)},
        "last": {"date": last["created_at"], "text": snippet(last)},
        "data_for_prompt": data_for_prompt,
    }


@router.get("/diary/{entry_id}")
async def diary_item(entry_id: int, user=Depends(confirmed_age_user), db=Depends(get_db)):
    """Open one diary entry from the unified archive without crossing owners."""
    cur = await db.execute(
        "SELECT id, text, mood, created_at FROM diary WHERE id=:id AND tg_id=:tg_id",
        {"id": entry_id, "tg_id": user["tg_id"]},
    )
    row = await cur.fetchone()
    if not row:
        from fastapi import HTTPException
        raise HTTPException(404, "запись дневника не найдена")
    return dict(row)
