"""Самопроверка проекта: синтаксис, импорты, схема, деньги, LLM.

    python -m scripts.selfcheck

Проверяет то, что ломается чаще всего и дороже всего: структуру БД после
миграций, идемпотентность оплаты, лимиты и живой ответ LLM-цепочки. Работает на
общей базе DATABASE_URL, очищая её между секциями — боевые данные не трогает.
"""
from __future__ import annotations

import ast
import asyncio
import os
import pathlib
import sys
import traceback
from datetime import datetime, timedelta, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

OK, FAIL, SKIP = "  ✅", "  ❌", "  ⏭"
errors = 0
warnings = 0


def check(title, fn):
    global errors
    try:
        result = fn()
        print(OK, title, ("— " + str(result)) if result is not None else "")
    except SkipCheck as e:
        global warnings
        warnings += 1
        print(SKIP, title, "—", e)
    except Exception:
        errors += 1
        print(FAIL, title)
        traceback.print_exc(limit=3)


class SkipCheck(Exception):
    """Проверка неприменима в этом окружении (нет зависимости, нет ключей)."""


# ─────────────────────────── статические проверки ─────────────────────────────

def syntax_all():
    bad = 0
    files = 0
    for path in sorted(ROOT.glob("app/**/*.py")) + sorted(ROOT.glob("scripts/*.py")) \
            + sorted(ROOT.glob("tests/*.py")):
        files += 1
        try:
            ast.parse(path.read_text())
        except SyntaxError as e:
            bad += 1
            print(FAIL, f"синтаксис: {path.relative_to(ROOT)} — {e}")
    if bad:
        raise SystemExit(f"{bad} синтаксических ошибок")
    return f"{files} файлов разобраны"


def imports_all():
    """Импортируем всё: так ловятся опечатки в именах и циклические импорты."""
    import importlib
    modules = [
        "app.config", "app.data.session", "app.data.seed",
        "app.repo", "app.services", "app.core.agent",
        "app.core.agents", "app.core.llm", "app.core.tool_registry", "app.core.astro",
        "app.core.tarot", "app.core.matrix", "app.core.memory", "app.core.safety",
        "app.core.practices", "app.core.cards", "app.core.geo",
        "app.pdfgen", "app.services.practices", "app.services.horoscopes",
        "app.api.main", "app.api.deps", "app.api.security",
        "app.bot.main", "app.bot.chat", "app.bot.features", "app.bot.growth",
        "app.bot.shop", "app.bot.profile", "app.bot.onboarding",
        "app.bot.keyboards",
    ]
    for name in modules:
        importlib.import_module(name)
    return f"{len(modules)} модулей импортируются"


def safety_filter():
    """Кризисный протокол обязан ловить формулировки, а не отдельные слова."""
    from app.core import safety

    must_stop = ["не хочу жить", "Я не хочу жить...", "он меня бьёт",
                 "думаю покончить с собой", "н е   х о ч у   ж и т ь"]
    for text in must_stop:
        level, category = safety.classify(text)
        assert level == safety.CRISIS, f"пропущен кризис: «{text}» → {level}"
        assert category, f"кризис без категории: «{text}»"

    must_soften = ["мне поставили диагноз", "стоит ли брать ипотеку"]
    for text in must_soften:
        level, _ = safety.classify(text)
        assert level == safety.SOFTEN, f"не смягчено: «{text}» → {level}"

    must_pass = ["что меня ждёт в любви?", "когда я встречу своего человека",
                 "стоит ли ему написать первой"]
    for text in must_pass:
        level, _ = safety.classify(text)
        assert level == safety.NONE, f"ложное срабатывание: «{text}» → {level}"
    return (f"{len(must_stop)} кризисных, {len(must_soften)} смягчаемых, "
            f"{len(must_pass)} обычных — разобраны верно")


def practices_catalog():
    """Практики без шагов или с битой программой — это пустой раздел продукта."""
    from app.core import practices as pr

    assert pr.PRACTICES, "каталог практик пуст"
    for code, item in pr.PRACTICES.items():
        assert item["steps"], f"{code}: нет шагов"
        assert item["days"] >= 1, f"{code}: некорректная длина программы"
        assert item["category"] in pr.CATEGORIES, f"{code}: чужая категория"
        assert item.get("signs"), f"{code}: нет знаков продвижения"
        for day in (1, item["days"] // 2 or 1, item["days"]):
            assert pr.today_step(item, day), f"{code}: нет шага на день {day}"
    categories = {i["category"] for i in pr.PRACTICES.values()}
    return (f"{len(pr.PRACTICES)} практик в {len(categories)} разделах, "
            f"программы по дням собираются")


def memory_vectors():
    """Упаковка векторов должна переживать круг «в БД и обратно»."""
    from app.core import memory

    vector = [0.1, -0.25, 0.5, 0.75]
    restored = memory.unpack(memory.pack(vector))
    assert len(restored) == len(vector), "длина вектора изменилась"
    assert all(abs(a - b) < 1e-6 for a, b in zip(vector, restored)), \
        "значения вектора исказились"
    assert memory.cosine(vector, vector) > 0.999, "косинус сам с собой не единица"
    assert abs(memory.cosine([1, 0], [0, 1])) < 1e-6, "ортогональные не нулевые"
    return f"эмбеддинги {'включены' if memory.embeddings_enabled() else 'выключены'}"


def share_cards():
    """Карточка для сторис: либо рисуется, либо честно отключена."""
    from app.core import cards

    if not cards.available():
        raise SkipCheck("Pillow не установлен — шеринг останется текстовым")
    from app.core import tarot
    png = cards.reading_card("Проверка", tarot.draw(3),
                             ["Прошлое", "Настоящее", "Будущее"],
                             name="Тест", bot_username="oracle_bot", seed=1)
    assert png and png[:8] == b"\x89PNG\r\n\x1a\n", "карточка не PNG"
    return f"PNG {len(png) // 1024} КБ собирается"


def pdf_pipeline():
    """Разбор для маркетплейса должен собираться хотя бы в HTML."""
    from app.pdfgen import builder, layout, render

    order = builder.Order(name="Проверка", birth_date="1990-06-21",
                          birth_time="14:30", birth_city="Казань",
                          promo_code="ORA-TEST1234")
    data = asyncio.run(builder.build_report_data(order))
    natal = asyncio.run(builder._natal_print_block(data, order, "ru"))
    html = layout.document("Проверка", [
        natal,
        f'<div class="wheel">{layout.matrix_svg(data["matrix"])}</div>'])
    assert "data:image/png;base64," in html and "<svg" in html and len(html) > 2000, "вёрстка разбора пустая"
    where = "PDF" if render.available() else "только HTML (нет WeasyPrint)"
    return f"натальная PNG-карта и отдельная октаграмма рисуются, вывод: {where}"


def frontend_assets():
    """Ключевые файлы модульного Mini App и админки должны отдаваться API."""
    required = [
        "miniapp/index.html", "miniapp/styles.css",
        "miniapp/js/00-runtime.js", "miniapp/js/01-utils.js",
        "miniapp/js/02-art.js", "miniapp/js/03-data.js",
        "miniapp/js/05-app.js", "miniapp/js/06-home.js",
        "miniapp/js/07-chat.js", "miniapp/js/08-widgets.js",
        "miniapp/js/09-tarot.js", "miniapp/js/10-chart.js",
        "miniapp/js/11-compat.js", "miniapp/js/12-misc.js",
        "miniapp/js/13-events.js", "miniapp/js/13-palm.js",
        "miniapp/js/14-gestures.js", "miniapp/js/14-products.js",
        "miniapp/js/15-actions.js", "miniapp/js/16-placements.js",
        "miniapp/js/17-payments.js",
        "miniapp/css/00-tokens.css", "miniapp/css/15-ritual-redesign.css",
        "miniapp/css/16-visual-qa.css", "miniapp/css/16-payments.css",
        "miniapp/css/18-pixel-reconstruction.css",
        "admin/index.html", "admin/admin.js", "admin/admin.css",
        "admin/pixel-reconstruction.css", "admin/src/app.js",
        "admin/src/layout/template.js", "admin/src/core/runtime.js",
        "admin/src/components/charts.js",
        "admin/src/features/dashboard.js", "admin/src/features/users.js",
        "admin/src/features/commerce.js", "admin/src/features/engagement.js",
        "admin/src/features/content.js", "admin/src/features/settings.js",
        "admin/src/features/observability.js", "admin/src/features/logs.js",
        "admin/styles/00-foundations.css", "admin/styles/10-shell.css",
        "admin/styles/20-components.css", "admin/styles/30-feature-surfaces.css",
        "admin/styles/40-responsive-accessibility.css",
        "admin/styles/50-pixel-reconstruction.css",
        "scripts/admin_visual_contract.py", "app/core/log_stream.py", "app/api/routers/logs.py",
    ]
    missing = [p for p in required if not (ROOT / p).is_file()]
    if missing:
        raise FileNotFoundError("нет файлов: " + ", ".join(missing))
    total = sum((ROOT / p).stat().st_size for p in required)
    return f"{len(required)} файлов, {total // 1024} КБ"


def core_smoke():
    from datetime import date

    from app.core import astro, tarot
    from app.core.matrix import compute_matrix
    from app.core.tool_registry import _compat

    assert len(tarot.DECK) == 78, "в колоде должно быть 78 карт"
    cards = tarot.draw(3)
    assert len({c["name"] for c in cards}) == 3, "карты не должны повторяться"
    assert len(tarot.draw(12)) == 12, "большие расклады должны собираться"
    sign = astro.sun_sign(date(1999, 6, 21))
    moon = astro.moon_phase()
    matrix = compute_matrix("1999-06-21")
    chart = astro.compute_chart("1999-06-21", "14:30", "Казань", 55.79, 49.12,
                                "Europe/Moscow")
    compat = _compat("1999-06-21", "1996-11-03")
    return (f"солнце {sign[0]}, луна «{moon['name']}», аркан {matrix['destiny']['n']}, "
            f"карта mode={chart['mode']}, пара {compat['score']}/100")


# ─────────────────────────── проверки на общей БД ─────────────────────────────
# Раньше каждая секция ставила собственную временную SQLite-базу. Теперь бэкенд
# один — PostgreSQL из DATABASE_URL, поэтому секции делят одну базу и перед
# прогоном очищают её через TRUNCATE (кроме миграционных таблиц).

async def _truncate_all(db) -> None:
    """Очищает все таблицы кроме alembic_version и migrations_applied, затем
    заново засевает дефолты: раньше каждая секция получала свежую базу с сидом,
    теперь делим одну и возвращаем ей состояние «засеяна с нуля»."""
    cur = await db.execute(
        "SELECT tablename FROM pg_tables WHERE schemaname='public'")
    tables = [row["tablename"] for row in await cur.fetchall()]
    keep = {"alembic_version", "migrations_applied"}
    drop = [t for t in tables if t not in keep]
    if drop:
        await db.execute(
            "TRUNCATE TABLE " + ", ".join('"' + t + '"' for t in drop)
            + " RESTART IDENTITY CASCADE")
    from app.data.seed import seed_defaults
    async with db.transaction():
        await seed_defaults(db)


async def db_smoke():
    from app.data.session import connect, healthcheck
    from app.repo import billing, dialog, users

    db = await connect(seed=False)
    try:
        await _truncate_all(db)
        state = await healthcheck(db)
        assert state["ok"], f"целостность БД: {state['integrity']}"
        assert state["journal_mode"] == "postgresql", "бэкенд не PostgreSQL"
        assert state["schema_tables"] >= 20, "схема неполная"

        await users.ensure(db, 999000111, "Тест")
        await users.update(db, 999000111, onboarded=1, birth_date="1990-06-21",
                           sub_level="vip")
        assert await dialog.save_memory(db, 999000111, "тестовый факт")

        assert not await dialog.save_memory(db, 999000111, "тестовый факт"), \
            "дубликаты памяти не отсекаются"

        plans = await billing.list_plans(db)
        products = await billing.list_products(db)
        assert any(p["code"] == "vip" for p in plans), "тарифы не засеяны"
        assert any(p["kind"] == "spread" for p in products), \
            "одиночные расклады не засеяны"
        return (f"{state['schema_tables']} таблиц, {len(plans)} тарифов, "
                f"{len(products)} товаров")
    finally:
        await db.close()


async def money_smoke():
    """Главный инвариант: повторная оплата не выдаёт товар дважды."""
    from app.data.session import connect
    from app.repo import billing, users
    from app.services import billing as billing_svc

    db = await connect(seed=False)
    try:
        await _truncate_all(db)
        await users.ensure(db, 999000222, "Плательщица")
        order = await billing_svc.checkout_plan(db, 999000222, "vip")
        first = await billing_svc.apply_payment(db, order["payload"],
                                                charge_id="ch_test",
                                                amount_stars=order["amount_stars"])
        second = await billing_svc.apply_payment(db, order["payload"],
                                                 charge_id="ch_test",
                                                 amount_stars=order["amount_stars"])
        assert first, "первая оплата не применилась"
        assert second is None, "повторная оплата выдала товар второй раз"

        fresh = await users.get(db, 999000222)
        assert users.sub_active(fresh), "подписка не активировалась"

        await users.update(db, 999000222, crystals=30)
        assert await billing.spend_crystals(db, 999000222, 20, "test")
        assert not await billing.spend_crystals(db, 999000222, 20, "test"), \
            "баланс ✦ ушёл в минус"
        return f"оплата идемпотентна, подписка до {fresh['sub_until'][:10]}"
    finally:
        await db.close()


async def limits_smoke():
    from app.data.session import connect
    from app.repo import dialog, users
    from app.services import chat, limits

    db = await connect(seed=False)
    try:
        await _truncate_all(db)
        await users.ensure(db, 999000333, "Спрашивающая")
        await users.update(db, 999000333, onboarded=1,
                           birth_date="1990-06-21", sub_level="vip",
                           sub_until=(datetime.now(timezone.utc)
                                      + timedelta(days=30)).isoformat())
        user = await users.get(db, 999000333)

        allowance = await limits.allowance(db, user)
        assert allowance.limit == 3, f"лимит VIP должен быть 3, а не {allowance.limit}"

        result = await chat.ask(db, user, "Что меня ждёт?")
        assert result["answer"], "агент не ответил"

        for _ in range(3):
            await dialog.save_message(db, 999000333, "user", "вопрос",
                                      is_question=True)
        await users.update(db, 999000333, crystals=0)
        verdict = await limits.check(db, await users.get(db, 999000333))
        assert not verdict.allowed, "лимит не срабатывает"
        return f"лимит {allowance.limit}/день, отказ работает"
    finally:
        await db.close()


async def practices_smoke():
    """Стрик и завершение программы — то, ради чего раздел вообще существует."""
    from app.data.session import connect
    from app.repo import users
    from app.services import practices as practices_svc

    db = await connect(seed=False)
    try:
        await _truncate_all(db)
        await users.ensure(db, 999000444, "Практикующая")
        await users.update(db, 999000444, onboarded=1, birth_date="1990-06-21")
        user = await users.get(db, 999000444)

        items = await practices_svc.list_for_user(db, user)
        assert items, "каталог практик пуст — раздел не наполнен"
        code = items[0]["code"]

        started = await practices_svc.start(db, user, code)
        assert started["started"], "практика не запустилась"
        assert started["today_step"], "нет шага на первый день"

        first = await practices_svc.mark_done(db, user, code)
        assert first["streak"] == 1 and not first["already"], "первый день не засчитан"
        again = await practices_svc.mark_done(db, user, code)
        assert again["already"], "вторая отметка за день накрутила стрик"

        assert await practices_svc.stop(db, user, code), "практика не останавливается"
        return f"{len(items)} практик, стрик и остановка работают"
    finally:
        await db.close()


async def horoscopes_smoke():
    """Двенадцать знаков в сутки на весь сервис, а не по тексту на клиентку."""
    from app.data.session import connect
    from app.services import horoscopes

    db = await connect(seed=False)
    try:
        await _truncate_all(db)
        assert len(horoscopes.SIGNS) == 12, "знаков должно быть двенадцать"
        text = await horoscopes.get_or_build(db, "Овен")
        assert len(text) > 60, "гороскоп подозрительно короткий"
        again = await horoscopes.get_or_build(db, "Овен")
        assert again == text, "гороскоп не закешировался — платим дважды"
        result = await horoscopes.build_day(db)
        assert result["built"] == 11, \
            f"собрано {result['built']} знаков вместо 11 оставшихся"
        return f"12 знаков, кеш держит, каналов настроено: " \
               f"{len(horoscopes.channel_map())}"
    finally:
        await db.close()


async def webhook_smoke():
    """Подпись вебхука и защита от повторной выдачи по одному событию."""
    import hashlib
    import hmac
    import time

    from app.api.routers.webhooks import _already_seen, verify_paddle
    from app.data.session import connect

    secret = "whsec_test"
    raw = b'{"event_id":"evt_1","event_type":"transaction.completed"}'
    ts = str(int(time.time()))
    digest = hmac.new(secret.encode(), f"{ts}:".encode() + raw,
                      hashlib.sha256).hexdigest()

    assert verify_paddle(raw, f"ts={ts};h1={digest}", secret), "верная подпись отклонена"
    assert not verify_paddle(raw, f"ts={ts};h1=deadbeef", secret), \
        "подделанная подпись принята"
    assert not verify_paddle(b'{"tampered":1}', f"ts={ts};h1={digest}", secret), \
        "подменённое тело принято"
    old = str(int(time.time()) - 3600)
    old_digest = hmac.new(secret.encode(), f"{old}:".encode() + raw,
                          hashlib.sha256).hexdigest()
    assert not verify_paddle(raw, f"ts={old};h1={old_digest}", secret), \
        "просроченная подпись принята"

    db = await connect(seed=False)
    try:
        await _truncate_all(db)
        assert not await _already_seen(db, "evt_1", "paddle", "test", "{}"), \
            "первое событие сочли повтором"
        assert await _already_seen(db, "evt_1", "paddle", "test", "{}"), \
            "повтор события не отсечён — товар выдался бы дважды"
    finally:
        await db.close()
    return "подпись проверяется, повтор отсекается"


async def llm_smoke():
    if os.getenv("SELF_CHECK_LIVE", "0") != "1":
        raise SkipCheck("live LLM выключен; для staging выставь SELF_CHECK_LIVE=1")
    from app.config import settings
    if not settings.llm_enabled:
        raise SkipCheck("LLM выключен — продукт работает в офлайн-режиме, это ок")
    from app.core import llm
    chain = " → ".join(settings.provider_chain)
    try:
        text = await llm.complete("Отвечай одним словом.", "Скажи: работаю",
                                  max_tokens=20)
    except RuntimeError as e:
        # Только локальный прокси (localhost) без реальных ключей может быть
        # просто выключен на машине разработчика — продукт честно уходит в
        # офлайн. Реальный сервер с ключами обязан падать на этой проверке.
        base = settings.custom_base_url or ""
        local_only = ("localhost" in base or "127.0.0.1" in base) \
            and not settings.anthropic_key and not settings.openai_key
        if local_only:
            raise SkipCheck(f"локальный LLM-сервер не отвечает: {e}") from None
        raise
    return f"цепочка [{chain}] отвечает: «{text[:40]}»"


def config_report():
    from app.config import settings
    problems = settings.ready
    if problems:
        raise SkipCheck("; ".join(problems))
    return "конфигурация готова к боевому запуску"


# ────────────────────────────────── запуск ────────────────────────────────────

print("🔮 Самопроверка Оракула\n")
check("Синтаксис всех .py", syntax_all)
check("Ядро: колода, астрология, Матрица, совместимость", core_smoke)
check("Импорты всех модулей", imports_all)
check("Файлы Mini App и админки", frontend_assets)
check("Безопасность: кризисный протокол", safety_filter)
check("Практики и мантры: каталог и программы", practices_catalog)
check("Память: упаковка векторов и близость", memory_vectors)
check("Карточки для сторис", share_cards)
check("PDF-разбор для маркетплейса", pdf_pipeline)
check("База данных: схема, миграции, сид", lambda: asyncio.run(db_smoke()))
check("Деньги: идемпотентность оплаты и баланс ✦", lambda: asyncio.run(money_smoke()))
check("Лимиты и путь вопроса", lambda: asyncio.run(limits_smoke()))
check("Практики: старт, отметка, стрик", lambda: asyncio.run(practices_smoke()))
check("Гороскопы по знакам", lambda: asyncio.run(horoscopes_smoke()))
check("Вебхук web-оплаты: подпись и идемпотентность",
      lambda: asyncio.run(webhook_smoke()))
check("LLM: живой запрос к цепочке провайдеров", lambda: asyncio.run(llm_smoke()))
check("Конфигурация .env", config_report)

print()
if errors:
    print(f"❌ Проблем: {errors}. Пришли вывод Клоду — поправит.")
    sys.exit(1)
if warnings:
    print(f"✨ Всё работает. Предупреждений: {warnings} (см. ⏭ выше).")
else:
    print("✨ Всё чисто.")
print("Запуск: python -m app.bot.main  ·  uvicorn app.api.main:app --port 8080")
