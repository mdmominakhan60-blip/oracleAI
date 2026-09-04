"""Нагрузочные сценарии приложения под SLO из docs/RELEASE/PRODUCTION_READINESS.md §2 (G29).

HTTP-слой Mini App гоняется Locust'ом — `load/locustfile.py`. Этот скрипт
нагружает бот-потоки, которые Locust'ом не достать: /start, утренний пик
прогнозов, вопросы под семофором LLM, оплаты. Базу растит
`scripts/seed_load.py`; LLM подменяется быстрым стабом — здесь проверяется
механика очередей и целостность, а не сеть провайдера.

    python scripts/seed_load.py --count 5000
    python load/simulate.py                                # быстрые прогоны
    python load/simulate.py --full                         # целевые цифры G29

--full использует числа из ТЗ: 2000 /start, 4000 прогнозов, 1000 вопросов,
100 оплат. Без флага — уменьшенные прогоны для быстрой проверки механик.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import settings  # noqa: E402
from app.core import agent as agent_core  # noqa: E402
from app.core import llm  # noqa: E402
from app.data.session import connect  # noqa: E402
from app.repo import users as urepo  # noqa: E402
from app.services import billing  # noqa: E402

SLO = {"question_p95_s": 10.0, "max_errors_pct": 0.1, "pay_errors": 0}

# Покупка, за которую оплата идёт Кристаллами прямо в сценарии simulate.
PAYMENT_PRODUCT = ("load_spread", "spread", "Нагрузочный расклад", 2,
                   "spread", "one_answer", 1, 1)


async def _flood(items, make_coro):
    """Запускает задачи пачкой по элементам `items`; (latencies, errors).

    Каждому элементу — своя корутина; item отдаётся в `make_coro(item)`.
    """
    lat = []
    errors = 0

    async def one(item):
        nonlocal errors
        t0 = time.monotonic()
        try:
            await make_coro(item)
        except Exception:
            errors += 1
            lat.append(float("inf"))
            return
        lat.append(time.monotonic() - t0)

    await asyncio.gather(*(one(i) for i in items))
    finite = sorted(x for x in lat if x != float("inf"))
    return finite, errors


def _pct(data: list[float], q: float) -> float:
    if not data:
        return float("nan")
    idx = min(len(data) - 1, int(q / 100 * len(data)))
    return data[idx]


def _report(name: str, n: int, lat: list[float], errors: int, target: str = "-") -> bool:
    ok = errors == 0 or errors / max(n, 1) * 100 <= SLO["max_errors_pct"]
    base = f"{name:<18} n={n:<5} p50={_pct(lat,50)*1e3:6.1f}ms " \
           f"p95={_pct(lat,95)*1e3:7.1f}ms p99={_pct(lat,99)*1e3:7.1f}ms " \
           f"err={errors}/{n}"
    if target == "0":
        ok = errors == 0
    elif target and target != "-":
        ok = _pct(lat, 95) < float(target)
    print(f"{'✅' if ok else '❌'} {base}  slo={target}")
    return ok


async def _run(db, full: bool) -> bool:
    results: list[bool] = []

    # ── 2000 конкурентных /start: все проходят ensure без дублей/падений ──────
    n_start = 2000 if full else 200

    async def start_one(rnd_id):
        await urepo.ensure(db, 90_000_000 + rnd_id % n_start, "Нагрузка")

    lat, err = await _flood(range(n_start), start_one)
    results.append(_report("start_flood", n_start, lat, err))

    # ── утренний пик: 3000–4000 персональных прогнозов в офлайн-режиме ────────
    # Сеть провайдера в нагрузочном прогоне не трогаем: форсим офлайн, чтобы
    # мерилась механика (замки прогноза, очередь БД), а не время сети.
    _off = (settings.llm_provider, settings.custom_base_url, settings.custom_model_main,
            settings.anthropic_key, settings.openai_key)
    settings.llm_provider = "off"
    settings.custom_base_url = settings.custom_model_main = ""
    settings.anthropic_key = settings.openai_key = ""

    pct = 4000 if full else 150
    async def forecast_one(d_user):
        await agent_core.daily_forecast_cached(db, d_user)

    cur = await db.execute(
        "SELECT * FROM users WHERE onboarded=1 AND status='active' "
        "AND morning_push=1 ORDER BY tg_id LIMIT ?", (pct,))
    users = [dict(r) for r in await cur.fetchall()]
    if len(users) < pct:
        print(f"⚠ в базе только {len(users)} кандидатов на прогноз, досей: "
              "python scripts/seed_load.py --count 5000")
    lat, err = await _flood(users, forecast_one)
    results.append(_report("forecast_p35-4k", len(users), lat, err))

    # ── 1000 одновременных вопросов: семафор LLM размазывает пик ──────────────
    n_q = 1000 if full else 60
    settings.llm_provider = "anthropic"
    settings.anthropic_key = "k"
    settings.openai_key = ""
    llm._RATE = llm._RateLimit(10_000)
    llm._CONCURRENCY = asyncio.Semaphore(max(1, settings.llm_max_concurrency))
    _orig = llm._complete_with

    async def fake_complete(provider, system, user_text, tier, max_tokens, meter):
        await asyncio.sleep(0.005)
        return "стаб-ответ под семафором"

    async def question_one(_i):
        await llm.complete("s", "u", tier="lite", purpose="answer")

    llm._complete_with = fake_complete
    try:
        lat, err = await _flood(range(n_q), question_one)
    finally:
        llm._complete_with = _orig
    results.append(_report("question_1k", n_q, lat, err, str(SLO["question_p95_s"])))

    # ── 100 конкурентных оплат: продажа выдачи ровно один раз на заказ ─────────
    n_pay = 100 if full else 20
    await db.execute(
        "INSERT INTO products(sku, kind, title, price_crystals, "
        "grant_kind, grant_code, grant_qty, sort, is_active) VALUES(?,?,?,?,?,?,?,?,1) "
        "ON CONFLICT(sku) DO UPDATE SET "
        "kind=EXCLUDED.kind, title=EXCLUDED.title, "
        "price_crystals=EXCLUDED.price_crystals, "
        "grant_kind=EXCLUDED.grant_kind, grant_code=EXCLUDED.grant_code, "
        "grant_qty=EXCLUDED.grant_qty, sort=EXCLUDED.sort, "
        "is_active=EXCLUDED.is_active",
        PAYMENT_PRODUCT)
    await db.commit()
    cur = await db.execute(
        "SELECT tg_id FROM users WHERE crystals>=? AND status='active' "
        "ORDER BY tg_id LIMIT ?", (PAYMENT_PRODUCT[3], n_pay))
    payers = [r["tg_id"] for r in await cur.fetchall()]

    async def pay_one(tg_id):
        await billing.pay_with_crystals(db, tg_id, PAYMENT_PRODUCT[0])

    cur = await db.execute(
        "SELECT COUNT(*) n FROM entitlements WHERE code='one_answer' "
        "AND source='purchase'")
    before = (await cur.fetchone())["n"]
    lat, err = await _flood(payers, pay_one)
    results.append(_report("payment_100", len(payers), lat, err, "0"))

    cur = await db.execute(
        "SELECT COUNT(*) n FROM entitlements WHERE code='one_answer' "
        "AND source='purchase'")
    delta = (await cur.fetchone())["n"] - before
    grants_ok = delta == len(payers)
    print(f"{'✅' if grants_ok else '❌'} выдача товара: +{delta} прав на "
          f"{len(payers)} оплат (каждой оплате — ровно один раз)")
    results.append(grants_ok)

    return all(results)


async def main(full: bool) -> int:
    db = await connect(seed=False)
    try:
        return 0 if await _run(db, full) else 1
    finally:
        await db.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true",
                    help="целевые цифры G29 (по умолчанию — уменьшенный прогон)")
    a = ap.parse_args()
    raise SystemExit(asyncio.run(main(a.full)))
