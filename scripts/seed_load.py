"""Генератор фейк-юзеров для нагрузочных тестов (G29).

Даёт базе «10 000 установившихся»: таймзоны, тарифы, цель, канал привлечения,
лоттерея онбординга — как в живом продукте. Случайность засеяна фиксированным
сидом, прогоны воспроизводимы. Сеть не нужна: города с зашитыми координатами,
геокодинг не вызывается.

    python -m scripts.seed_load --count 10000
    python -m scripts.seed_load --count 5000 --all-active --age-confirmed --active-subscription

Цель — база из DATABASE_URL. Фиктивные юзеры пишутся в неё же; перезапуск без
риска дублей благодаря upsert по tg_id.
"""
from __future__ import annotations

import argparse
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.data.session import connect  # noqa: E402

# (город, tz, lat, lon) — координаты точные, chart-расчёт не тронет сеть.
CITIES = [
    ("Москва", "Europe/Moscow", 55.75, 37.61),
    ("Санкт-Петербург", "Europe/Moscow", 59.93, 30.36),
    ("Калининград", "Europe/Kaliningrad", 54.71, 20.51),
    ("Екатеринбург", "Asia/Yekaterinburg", 56.85, 60.61),
    ("Новосибирск", "Asia/Novosibirsk", 55.03, 82.95),
    ("Алматы", "Asia/Almaty", 43.25, 76.95),
    ("Минск", "Europe/Minsk", 53.90, 27.57),
]

NAMES = ["Анна", "Мария", "Ольга", "Елена", "Наталья", "Ирина", "Ксения",
         "Дарья", "Виктория", "Полина", "Алиса", "Екатерина", "Светлана",
         "Анастасия", "Татьяна", "Юлия", "Ангелина", "Маргарита", "Марина",
         "Валерия"]
GOALS = ["love", "career", "practice"]
SOURCES = ["organic", "tiktok", "instagram", "promo", "ref"]
SUB_WEIGHTS = [("trial", 0.5), ("vip", 0.2), ("free", 0.3)]


def _weighted(pairs: list, rnd: random.Random):
    r = rnd.random()
    acc = 0.0
    for value, w in pairs:
        acc += w
        if r <= acc:
            return value
    return pairs[-1][0]


def _birth(rnd: random.Random) -> tuple[str, str, int]:
    year = rnd.randint(1975, 2005)
    month = rnd.randint(1, 12)
    day = rnd.randint(1, 28)
    birth_date = f"{year:04d}-{month:02d}-{day:02d}"
    known = rnd.random() < 0.65
    birth_time = f"{rnd.randint(0, 23):02d}:{rnd.randint(0, 59):02d}" if known else None
    return birth_date, birth_time, int(known)


def _rows(count: int, *, all_active: bool = False,
          active_subscription: bool = False, force_onboarded: bool = False) -> list[tuple]:
    rnd = random.Random(42)
    now = datetime.now(timezone.utc)
    rows = []
    for i in range(count):
        tg_id = 100_000_000 + i
        city, tz, lat, lon = CITIES[i % len(CITIES)]
        name = rnd.choice(NAMES)
        sub_level = "vip" if active_subscription else _weighted(SUB_WEIGHTS, rnd)
        if sub_level == "free":
            sub_until = (now - timedelta(days=rnd.randint(1, 60))).isoformat()
        else:
            span = rnd.randint(5, 90)
            sub_until = (now + timedelta(days=span)).isoformat()
        birth_date, birth_time, time_known = _birth(rnd)
        onboarded = int(force_onboarded or rnd.random() < 0.65)
        morning_push = int(rnd.random() >= 0.12)
        created_days_ago = rnd.randint(1, 180)
        rows.append((
            tg_id, name, f"user_{tg_id}", "ru", tz, birth_date, birth_time,
            time_known, city, lat, lon, sub_level, sub_until,
            5, onboarded, morning_push, 0,
            rnd.choice(GOALS), rnd.choice(SOURCES),
            (now - timedelta(days=rnd.randint(0, 30))).isoformat() if onboarded else None,
            "active" if all_active or rnd.random() > 0.02 else "blocked",
            (now - timedelta(days=created_days_ago)).isoformat(),
        ))
    return rows


async def _seed(db, count: int, *, all_active: bool = False,
               active_subscription: bool = False,
               force_onboarded: bool = False) -> None:
    await db.executemany(
        "INSERT INTO users(tg_id, name, username, lang, tz, birth_date, "
        "birth_time, birth_time_known, birth_city, birth_lat, birth_lon, sub_level, "
        "sub_until, crystals, onboarded, morning_push, memory_enabled, "
        "goal, source, last_seen, status, created_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
        "ON CONFLICT(tg_id) DO UPDATE SET "
        "name=EXCLUDED.name, username=EXCLUDED.username, lang=EXCLUDED.lang, "
        "tz=EXCLUDED.tz, birth_date=EXCLUDED.birth_date, "
        "birth_time=EXCLUDED.birth_time, "
        "birth_time_known=EXCLUDED.birth_time_known, "
        "birth_city=EXCLUDED.birth_city, birth_lat=EXCLUDED.birth_lat, "
        "birth_lon=EXCLUDED.birth_lon, sub_level=EXCLUDED.sub_level, "
        "sub_until=EXCLUDED.sub_until, crystals=EXCLUDED.crystals, "
        "onboarded=EXCLUDED.onboarded, morning_push=EXCLUDED.morning_push, "
        "memory_enabled=EXCLUDED.memory_enabled, "
        "goal=EXCLUDED.goal, "
        "source=EXCLUDED.source, last_seen=EXCLUDED.last_seen, "
        "status=EXCLUDED.status, created_at=EXCLUDED.created_at)",
        _rows(count, all_active=all_active,
              active_subscription=active_subscription, force_onboarded=force_onboarded))
    await db.commit()


async def main(count: int, all_active: bool,
               active_subscription: bool, force_onboarded: bool) -> None:
    db = await connect()
    try:
        await _seed(db, count, all_active=all_active,
                    active_subscription=active_subscription, force_onboarded=force_onboarded)
    finally:
        await db.close()
    print(f"засеяно {count} юзеров в DATABASE_URL")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=10_000)
    ap.add_argument("--all-active", action="store_true",
                    help="не добавлять заблокированные профили (для HTTP-потока)")
    ap.add_argument("--active-subscription", action="store_true",
                    help="дать synthetic users future VIP entitlement для paid API probes")
    ap.add_argument("--onboarded", action="store_true",
                    help="пометить synthetic users как прошедших onboarding")
    args = ap.parse_args()
    import asyncio
    asyncio.run(main(args.count, args.all_active,
                      args.active_subscription, args.onboarded))
