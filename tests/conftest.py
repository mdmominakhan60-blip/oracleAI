"""Общие фикстуры тестов.

Каждый тест получает свою пустую базу в temp-файле: тесты денег и лимитов
меняют состояние, и общая база делала бы их зависимыми от порядка запуска.
LLM в тестах выключен — проверяем логику продукта, а не качество текстов.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Allow an isolated test database to override a developer’s default DATABASE_URL.
if os.getenv("TEST_DATABASE_URL"):
    os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]

# Выключаем провайдеров до импорта настроек: иначе тесты полезут в сеть.
os.environ["LLM_PROVIDER"] = "off"
# Tests use deterministic keyword memory; never inherit a sandbox embedding key.
os.environ["EMBED_MODEL"] = ""
os.environ.setdefault("BOT_TOKEN", "test:token")
# ADMIN_ID=1 безоговорочно: compose наливает реальный ADMIN_ID из .env через
# env_file, и setdefault его не перезапишет — админ-тесты с dev_user=1 ловили 403.
os.environ["ADMIN_ID"] = "1"
# WEBAPP_URL из .env перебивал offline-fallback ссылки проекта в отчётах.
os.environ["WEBAPP_URL"] = ""
os.environ["PUBLIC_URL"] = ""
os.environ["DEV_MODE"] = "1"
# DEV_KEY обязателен при DEV_MODE=1 (BUS-90): guard роняет импорт с пустым
# ключом. Client-фикстуры тестов добавляют заголовок X-Dev-Key к запросам.
os.environ["DEV_KEY"] = "test-dev-key"
#: Эмуляция заголовка X-Dev-Key из локального compose-стека разработчика.
TEST_DEV_KEY = "test-dev-key"
os.environ["AUTO_TRIAL"] = "1"


@pytest.fixture
async def db():
    """Пустая-но-посевочная база для одного теста, в общей PostgreSQL.

    Единственный бэкенд — PostgreSQL (env DATABASE_URL). Каждый тест получает
    все таблицы схемы, очищенные до посева, чтобы тесты денег и лимитов не
    зависели от порядка запуска.
    """
    if not os.environ.get("DATABASE_URL"):
        pytest.fail("DATABASE_URL не задан: тесты требуют общую PostgreSQL-базу")
    from app.data.session import connect
    from app.data.seed import seed_defaults

    # pgvector is an infrastructure prerequisite. The CI/local reset flow and
    # Alembic migration install it before pytest; fixtures must not require
    # superuser privileges or mutate extensions at test runtime.
    connection = await connect(seed=False)
    try:
        # Фикстура очищает ОБЩУЮ схему TRUNCATE'ом: параллельный pytest-процесс
        # (второе окно, CI-матрица) ловил взаимоблокировку TRUNCATE↔DML. Сессионный
        # advisory lock сериализует прогоны на одной базе; держим его всё время
        # теста, чтобы чужой TRUNCATE не пришёл посреди наших вставок.
        await connection.execute("SELECT pg_advisory_lock(hashtext('oracleai-test-db'))")
        cur = await connection.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname=current_schema()")
        tables = [row[0] for row in await cur.fetchall()
                  if row[0] not in ("alembic_version", "migrations_applied")]
        if tables:
            quoted = ", ".join(f'"{t}"' for t in tables)
            await connection.execute(
                f"TRUNCATE {quoted} CASCADE")
        async with connection.transaction():
            await seed_defaults(connection)
        yield connection
    finally:
        try:
            await connection.execute(
                "SELECT pg_advisory_unlock(hashtext('oracleai-test-db'))")
        finally:
            await connection.close()


@pytest.fixture
async def user(db):
    """Клиентка с триалом, прошедшая онбординг (карта построена как в онбординге)."""
    import json

    from app.core import astro
    from app.repo import users
    created = await users.ensure(db, 1001, "Тестовая", "tester")
    chart = await astro.compute_chart_async("1990-06-21", "14:30", "Казань",
                                            55.79, 49.12, "Europe/Moscow")
    await users.update(db, 1001, onboarded=1, birth_date="1990-06-21",
                       birth_time="14:30", birth_time_known=1,
                       birth_city="Казань", tz="Europe/Moscow",
                       sub_level="vip",
                       chart_json=json.dumps(chart, ensure_ascii=False),
                       memory_enabled=0)
    assert created["tg_id"] == 1001
    return await users.get(db, 1001)


@pytest.fixture
async def free_user(db):
    """Клиентка без активной подписки — уровень «Искра»."""
    from app.repo import users
    await users.ensure(db, 1002, "Без подписки")
    await users.update(db, 1002, onboarded=1, birth_date="1988-01-15",
                       sub_until="2000-01-01T00:00:00+00:00", sub_level="free",
                       memory_enabled=0)
    return await users.get(db, 1002)


@pytest.fixture(autouse=True)
async def _reset_api_rate_limits():
    """Внутрипроцессное состояние между тестами: API-лимитер накапливает корзину
    «write», кеш touch проносит last_seen между тестами, фоновые записи событий
    (G14) могут жить дольше теста и дёргать чужое соединение."""
    from app.core import memory
    from app.repo import users
    from app.services import analytics, rate_limit as rate_limit_service
    rate_limit_service.reset_limiter_for_tests()
    users._last_seen_cache.clear()
    memory._recall_cache.clear()
    await analytics.drain()
