"""Практики и мантры: витрина, программа дня, отметка, напоминания.

Каталог собирается так же, как расклады: встроенный набор из `core/practices.py`
перекрывается записями админки (`content_items(kind='practice')`). Прогресс
клиентки живёт в таблице `practices`.

Главное продуктовое требование этого раздела — «сколько дней подряд практиковали
и что происходит в жизни». Поэтому наружу всегда отдаются три вещи: какой сегодня
день программы, что именно делать сегодня и по каким признакам понять, что
работает. Без последнего практику бросают на третий день.
"""
from __future__ import annotations

import logging
from datetime import date

from ..core import practices as catalog
from ..repo import content, readings, users

log = logging.getLogger("oracle.practices")


def _from_content(item: dict) -> dict | None:
    meta = content.content_meta(item)
    steps = meta.get("steps")
    if not isinstance(steps, list) or not steps:
        log.warning("практика %s без шагов — пропускаю", item.get("code"))
        return None
    return {
        "code": item["code"],
        "title": item.get("title") or item["code"],
        "about": item.get("body") or "",
        "category": meta.get("category", "energy"),
        "emoji": meta.get("emoji", "✨"),
        "days": int(meta.get("days") or catalog.DEFAULT_DAYS),
        "goal": meta.get("goal", ""),
        "fit": meta.get("fit", ""),
        "best_time": meta.get("best_time", ""),
        "moon": meta.get("moon", ""),
        "text": meta.get("text", ""),
        "steps": [str(s) for s in steps][:12],
        "program": [str(s) for s in (meta.get("program") or [])][:40],
        "signs": [str(s) for s in (meta.get("signs") or [])][:10],
        "warning": meta.get("warning", ""),
        "referral": meta.get("referral", ""),
    }


async def all_practices(db) -> dict[str, dict]:
    """Код → описание. Встроенные + добавленные в панели."""
    out: dict[str, dict] = {}
    for code, item in catalog.PRACTICES.items():
        out[code] = {**item, "code": code, "about": item.get("about", "")}
    try:
        for item in await content.list_content(db, "practice", active_only=True):
            parsed = _from_content(item)
            if parsed:
                out[parsed["code"]] = parsed
    except Exception as e:  # noqa: BLE001
        log.warning("практики из БД недоступны, беру встроенные: %s", e)
    return out


async def get_practice(db, code: str) -> dict | None:
    return (await all_practices(db)).get(code)


def _streak_alive(progress: dict | None, today: str | None) -> bool:
    """Стрик-огонь горит, пока последняя отметка не старше суток.

    Число `streak` в БД стареет: пропустила день — стрик «заморожен», но цифра
    осталась. Для интерфейса важно не число само по себе, а горит ли огонь
    прямо сейчас: последняя отметка сегодня или вчера.
    """
    last = (progress or {}).get("last_done")
    if not last:
        return False
    try:
        gap = (date.fromisoformat(today or date.today().isoformat())
               - date.fromisoformat(str(last)[:10])).days
    except ValueError:
        return False
    return gap <= 1


def _status(progress: dict | None) -> str:
    if not progress:
        return "not_started"
    if progress.get("finished_at"):
        return "completed"
    return "active"


def _view(item: dict, progress: dict | None, today: str | None = None) -> dict:
    """Карточка практики для интерфейса: описание + её текущий прогресс."""
    day_index = (progress or {}).get("day_index") or 0
    started = bool(progress and not progress.get("finished_at"))
    finished = bool(progress and progress.get("finished_at"))
    days = item.get("days") or catalog.DEFAULT_DAYS
    return {
        "code": item["code"],
        "title": item["title"],
        "about": item.get("about", ""),
        "category": item.get("category", "energy"),
        "category_title": catalog.CATEGORIES.get(
            item.get("category", ""), {}).get("title", "Практики"),
        "emoji": item.get("emoji", "✨"),
        "days": days,
        "goal": item.get("goal", ""),
        "fit": item.get("fit", ""),
        "best_time": item.get("best_time", ""),
        "moon": item.get("moon", ""),
        "text": item.get("text", ""),
        "steps": item.get("steps", []),
        "program": item.get("program", []),
        "signs": item.get("signs", []),
        "warning": item.get("warning", ""),
        "referral": item.get("referral", ""),
        "started": started,
        "finished": finished,
        "status": _status(progress),
        "day_index": day_index,
        "streak": (progress or {}).get("streak") or 0,
        "streak_alive": _streak_alive(progress, today),
        "last_done": (progress or {}).get("last_done"),
        "started_at": (progress or {}).get("started_at"),
        "finished_at": (progress or {}).get("finished_at"),
        "days_left": max(0, days - day_index),
        "today_step": catalog.today_step(item, max(day_index + 1, 1)),
        "percent": min(100, round(day_index * 100 / days)) if days else 0,
    }


async def list_for_user(db, user, *, category: str | None = None) -> list[dict]:
    """Каталог с прогрессом. Идущие практики — первыми: к ним возвращаются."""
    items = await all_practices(db)
    # Строки идут от новых к старым; берём первую по коду. Через `setdefault`,
    # а не словарным включением: у пройденной и заново начатой практики две
    # строки, и включение оставило бы старую — экран показывал бы «пройдена».
    mine: dict[str, dict] = {}
    for row in await readings.list_practices(db, user["tg_id"]):
        mine.setdefault(row["code"], row)
    out = [_view(item, mine.get(code), users.user_today(user))
           for code, item in items.items()
           if not category or item.get("category") == category]
    out.sort(key=lambda p: (not p["started"], p["finished"],
                            catalog.CATEGORIES.get(p["category"], {}).get("sort", 100),
                            p["title"]))
    return out


async def categories() -> list[dict]:
    return [{"code": code, **item}
            for code, item in sorted(catalog.CATEGORIES.items(),
                                     key=lambda kv: kv[1]["sort"])]


async def start(db, user, code: str) -> dict:
    item = await get_practice(db, code)
    if not item:
        raise LookupError("такой практики нет")
    await readings.start_practice(db, user["tg_id"], code)
    progress = await readings.active_practice(db, user["tg_id"], code)
    return _view(item, dict(progress) if progress else None,
                 users.user_today(user))


async def stop(db, user, code: str) -> bool:
    return await readings.stop_practice(db, user["tg_id"], code)


async def mark_done(db, user, code: str) -> dict:
    """Отмечает сегодняшний день. День считается по таймзоне клиентки."""
    item = await get_practice(db, code)
    if not item:
        raise LookupError("такой практики нет")
    today = users.user_today(user)
    result = await readings.mark_practice_done(
        db, user["tg_id"], code, total_days=item.get("days"), tz_today=today)
    progress = await readings.active_practice(db, user["tg_id"], code)
    if progress is None:                       # программа только что закрылась
        rows = await readings.list_practices(db, user["tg_id"])
        progress = next((r for r in rows if r["code"] == code), None)
    view = _view(item, dict(progress) if progress else None, today)
    merged = {**view, **result, "title": item["title"]}
    return {**merged, "message": congrats(item, result)}


def congrats(item: dict, result: dict) -> str:
    """Что сказать после отметки. Молчаливая галочка не удерживает."""
    if result.get("already"):
        return "Сегодня уже отмечено 🌙 Возвращайся завтра."
    if result.get("finished"):
        signs = item.get("signs") or []
        tail = ("\n\nПосмотри, что изменилось:\n"
                + "\n".join(f"• {s}" for s in signs[:4])) if signs else ""
        return (f"🎉 Ты прошла всю программу «{item['title']}» — "
                f"{item.get('days', 0)} дней.{tail}\n\n"
                f"Запиши в дневник, что стало другим. Это твоё доказательство.")
    day = result.get("day_index", 1)
    streak = result.get("streak", 1)
    total = item.get("days") or catalog.DEFAULT_DAYS
    if streak >= 7:
        note = f"🔥 {streak} дней подряд — это уже характер."
    elif streak >= 3:
        note = f"🔥 {streak} дня подряд. Не разрывай цепочку."
    else:
        note = "Главное — не пропускать."
    return f"Отмечено ✨ День {day} из {total}. {note}"
