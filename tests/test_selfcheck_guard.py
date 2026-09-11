"""BUS-709: fail-closed guard selfcheck._truncate_all() — prevention прод-wipe.

Слои гарда (BUS-660 → BUS-709):
1. _guard_truncate(db_name) — allowlist по фактической базе подключения:
   *_test-суффикс либо APP_ENV=dev; иначе RuntimeError ДО любых DDL.
   Работает по current_database(), а не по DATABASE_URL из env — env может
   рассинхронизироваться с реальным коннектом (вектор инцидента BUS-660).
2. _truncate_all(db) — вызывает гард по фактической базе до TRUNCATE.
3. prod_grant_check() — зелёная selfcheck-проверка, что на production
   app-роль НЕ имеет TRUNCATE (грант DevOps выполнен); вне прода — SKIP.
"""
from __future__ import annotations

import os
from unittest.mock import patch

import pytest

# Импортируем guard-функции внутри тестов: top-level модуля не должен
# запускать selfcheck как side-effect (main() вынесен за top-level).


# ── _guard_truncate unit tests ──────────────────────────────────────────────


class TestGuardTruncate:
    def _import(self):
        from scripts.selfcheck import _database_name, _guard_truncate
        return _database_name, _guard_truncate

    def test_allows_test_db_any_app_env(self):
        _, _guard_truncate = self._import()
        with patch.dict(os.environ, {"APP_ENV": "production"}):
            _guard_truncate("oracle_test")  # must not raise

    def test_allows_dev_app_env_any_db(self):
        _, _guard_truncate = self._import()
        with patch.dict(os.environ, {"APP_ENV": "dev"}):
            _guard_truncate("oracle")  # must not raise

    def test_allows_dev_app_env_with_test_suffix(self):
        _, _guard_truncate = self._import()
        with patch.dict(os.environ, {"APP_ENV": "production"}):
            _guard_truncate("oracle_dev_test")  # must not raise (suffix wins)

    def test_rejects_prod_db_prod_env(self):
        _, _guard_truncate = self._import()
        with patch.dict(os.environ, {"APP_ENV": "production"}):
            with pytest.raises(RuntimeError, match="BUS-660"):
                _guard_truncate("oracle")

    def test_rejects_prod_db_unset_env(self):
        # fail-closed: пустой APP_ENV ≠ dev — отказ
        _, _guard_truncate = self._import()
        with patch.dict(os.environ, {"APP_ENV": ""}):
            with pytest.raises(RuntimeError, match="BUS-660"):
                _guard_truncate("oracle")

    def test_rejects_prod_db_ci_env(self):
        _, _guard_truncate = self._import()
        with patch.dict(os.environ, {"APP_ENV": "ci"}):
            with pytest.raises(RuntimeError, match="BUS-660"):
                _guard_truncate("oracle")

    def test_rejects_prod_like_db_with_url_mismatch(self):
        # Вектор BUS-660: env DATABASE_URL врёт (oracle_test), коннект — к oracle.
        # Гард смотрит на фактическое имя базы, не на env.
        _, _guard_truncate = self._import()
        with patch.dict(os.environ, {
            "APP_ENV": "production",
            "DATABASE_URL": "postgresql://u@p:5432/oracle_test",
        }):
            with pytest.raises(RuntimeError, match="BUS-660"):
                _guard_truncate("oracle")

    def test_database_name_parser(self):
        _database_name, _ = self._import()
        assert _database_name("postgresql://u:p@host:5432/oracle_test") == "oracle_test"
        assert _database_name("postgresql+asyncpg://u:p@host:5432/myapp_test") == "myapp_test"
        assert _database_name("postgresql://u:p@host:5432/oracle") == "oracle"


# ── _truncate_all integration tests ────────────────────────────────────────


def _admin_dsn() -> str:
    url = os.environ.get("POSTGRES_ADMIN_DATABASE_URL", "")
    if not url:
        pytest.skip("POSTGRES_ADMIN_DATABASE_URL not set")
    return url


async def _connect_direct(database_url: str):
    """Подключается к БД как PostgresDatabase (та же обёртка, что selfcheck).
    Нормализует DSN к postgresql+asyncpg (admin-URL обычно без драйвера)."""
    import re
    from app.data.postgres import PostgresDatabase
    url = re.sub(r"^postgresql://", "postgresql+asyncpg://", database_url)
    return PostgresDatabase(url)


class TestTruncateAllGuard:
    """_truncate_all должен отказаться очищать не-test базу вне dev —
    по фактическому имени подключённой базы, до любого TRUNCATE."""

    async def test_refuses_on_prod_db_via_actual_connection(self):
        from scripts.selfcheck import _truncate_all
        # Подключаемся к НЕ-test базе (oracle) как оракульная роль,
        # APP_ENV=production → гард обязан отказать до TRUNCATE.
        admin = _admin_dsn()
        db = await _connect_direct(admin.replace("/postgres", "/oracle"))
        try:
            with patch.dict(os.environ, {"APP_ENV": "production"}):
                with pytest.raises(RuntimeError, match="BUS-660"):
                    await _truncate_all(db)
        finally:
            await db.close()

    async def test_refuses_when_env_url_lies(self):
        # Вектор BUS-660: DATABASE_URL указывает на oracle_test, но коннект
        # реально открыт на oracle. Гард обязан смотреть на current_database().
        from scripts.selfcheck import _truncate_all
        admin = _admin_dsn()
        db = await _connect_direct(admin.replace("/postgres", "/oracle"))
        try:
            with patch.dict(os.environ, {
                "APP_ENV": "production",
                "DATABASE_URL": "postgresql+asyncpg://oracle:x@postgres:5432/oracle_test",
            }):
                with pytest.raises(RuntimeError, match="BUS-660"):
                    await _truncate_all(db)
        finally:
            await db.close()

    async def test_truncates_test_db(self):
        # Happy path: *_test-база — очистка разрешена при любом APP_ENV.
        from scripts.selfcheck import _truncate_all
        test_url = os.environ.get("TEST_DATABASE_URL", "")
        if not test_url or "_test" not in test_url.rsplit("/", 1)[-1]:
            pytest.skip("TEST_DATABASE_URL не указывает на *_test базу")
        db = await _connect_direct(test_url)
        try:
            with patch.dict(os.environ, {"APP_ENV": "test"}):
                await _truncate_all(db)  # must not raise
        finally:
            await db.close()


# ── prod_grant_check ────────────────────────────────────────────────────────


class TestProdGrantCheck:
    async def test_skips_outside_production(self):
        from scripts.selfcheck import SkipCheck, prod_grant_check
        with patch.dict(os.environ, {"APP_ENV": "test"}):
            with pytest.raises(SkipCheck):
                await prod_grant_check()

    async def test_flags_truncate_privilege_on_production(self):
        # Грант ещё не выполнен (роль oracle — владелец) → проверка обязана
        # упасть с RuntimeError, а не пропустить. Это регресс-сцена́рий для
        # DevOps-хенда: после гранта без TRUNCATE этот тест меняют на зелёный.
        from scripts.selfcheck import prod_grant_check
        admin = _admin_dsn()
        with patch.dict(os.environ, {"APP_ENV": "production"}):
            # prod_grant_check читает settings.database_url → подменяем на
            # прямое подключение к oracle как владелец (TRUNCATE есть).
            from unittest.mock import AsyncMock
            db = await _connect_direct(admin.replace("/postgres", "/oracle"))
            try:
                with patch("app.data.session.connect",
                          AsyncMock(return_value=db)) as _:
                    with pytest.raises(RuntimeError, match="TRUNCATE|грант"):
                        await prod_grant_check()
            finally:
                await db.close()
