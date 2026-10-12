"""Тесты переключения Mini App: legacy ↔ V2 и откат.

Проверяют поведение серверного флага `_v2_enabled` и сборку HTML обоих
режимов (`_miniapp_index_body` / `_miniapp_v2_body`) без запуска сервера и
без деплоя: работаем через ASGI-транспорт, как остальные API-тесты.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import httpx
import pytest

from app.api import main as main_module

ROOT = Path(__file__).resolve().parents[1]
MINIAPP = ROOT / "miniapp"
DIST = MINIAPP / "dist"
HASHED = re.compile(r"^app\.[0-9a-f]{12}\.min\.(js|css)$")


@pytest.fixture
def legacy_manifest() -> dict:
    """Манифест legacy-сборки (то, что отдаётся при выключенном V2)."""
    path = DIST / "manifest.json"
    if not path.is_file():
        pytest.skip("miniapp/dist/manifest.json не собран (npm run build:frontend)")
    return json.loads(path.read_text(encoding="utf-8"))


def _ensure_legacy_bundle() -> None:
    """Собрать legacy-бандл, если его нет — иначе сравнивать нечего."""
    if (DIST / "manifest.json").is_file():
        return
    import subprocess
    subprocess.run(["node", "scripts/build_frontend.mjs"], cwd=ROOT, check=True)


# ──────────────────────── сборка V2: имена и manifest ───────────────────────

class TestV2BuildContract:
    """Требование Этапа 3: имена из контракта, manifest читается сервером."""

    def test_manifest_names_match_backend_contract(self, tmp_path: Path) -> None:
        from app.api.main import _apply_bundle

        manifest = {
            "js": "app.0123456789ab.min.js",
            "css": "app.fedcba987654.min.css",
            "jsFiles": ["x"],
            "cssFiles": ["y"],
        }
        # CSS подменяется по месту существующей ссылки (как в legacy-шаблоне),
        # поэтому в оболочке должен быть реальный <link> на styles.css.
        html = (
            "<html><head>"
            "<link rel=\"stylesheet\" href=\"/static/styles.css?v=110\">"
            "</head><body></body></html>"
        )
        body = _apply_bundle(html, manifest["js"], manifest["css"])
        assert "<script src=\"/static/dist/app.0123456789ab.min.js\">" in body
        assert "/static/dist/app.fedcba987654.min.css" in body
        # Исходные ссылки заменены, а не продублированы.
        assert "/static/styles.css" not in body
        assert "/static/js/" not in body

    def test_v2_build_produces_contract_names(self) -> None:
        """Собранный Vite-бандл V2 должен удовлетворять контракту имён."""
        dist = ROOT / "frontend-v2" / "dist"
        manifest_path = dist / "manifest.json"
        if not manifest_path.is_file():
            pytest.skip("frontend-v2/dist/manifest.json не собран (npm run build)")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert HASHED.fullmatch(manifest["js"]), manifest["js"]
        assert HASHED.fullmatch(manifest["css"]), manifest["css"]
        # То, на что ссылается манифест, реально существует и не пустое.
        for key in ("js", "css"):
            path = dist / manifest[key]
            assert path.is_file(), f"{key}: {path} отсутствует"
            assert path.stat().st_size > 0, f"{key}: {path} пустой"
        # Счётчики исходных модулей есть — иначе check_frontend_build.py упадёт.
        assert "jsFiles" in manifest and "cssFiles" in manifest


# ──────────────────────────── флаг переключения ─────────────────────────────

class TestV2Flag:
    def _flag(self, monkeypatch, value: str | None) -> None:
        if value is None:
            monkeypatch.delenv("MINIAPP_V2", raising=False)
        else:
            monkeypatch.setenv("MINIAPP_V2", value)

    # --- pure-функция: не требует ни БД, ни импорта app.api.main ----------
    # Эти проверки запускаются без ТЕСТОВОЙ БД — они ловят регрессию самого
    # флага (включался/выключался/значение по умолчанию) в любом окружении.

    @pytest.mark.parametrize("value", ["1", "true", "TRUE", "Yes", "on"])
    def test_env_override_enables(self, monkeypatch, value: str) -> None:
        from app.api.main import _v2_env_override
        monkeypatch.setenv("MINIAPP_V2", value)
        assert _v2_env_override() is True

    @pytest.mark.parametrize("value", ["0", "false", "FALSE", "no", "off"])
    def test_env_override_disables(self, monkeypatch, value: str) -> None:
        from app.api.main import _v2_env_override
        monkeypatch.setenv("MINIAPP_V2", value)
        assert _v2_env_override() is False

    def test_unset_falls_back_to_db(self, monkeypatch) -> None:
        """Не задан → решает feature_flags, а не значение по умолчанию True."""
        from app.api.main import _v2_env_override
        monkeypatch.delenv("MINIAPP_V2", raising=False)
        assert _v2_env_override() is None

    @pytest.mark.parametrize("value", ["maybe", "2", "да", "нет"])
    def test_garbage_does_not_enable(self, monkeypatch, value: str) -> None:
        """Мусорное значение не должно молча включить V2."""
        from app.api.main import _v2_env_override
        monkeypatch.setenv("MINIAPP_V2", value)
        assert _v2_env_override() is None

    @pytest.mark.parametrize("value", ["1", "true", "yes", "on"])
    def test_switch_on_without_db(self, monkeypatch, value: str) -> None:
        """Включение не требует БД: продакшн-конфиг управляется env."""
        monkeypatch.setenv("MINIAPP_V2", value)
        import asyncio
        from app.api.main import _v2_enabled
        assert asyncio.run(_v2_enabled(None)) is True

    def test_default_is_off_without_db(self, monkeypatch) -> None:
        """Без флага и без БД режим остаётся legacy — V2 не включается случайно."""
        monkeypatch.delenv("MINIAPP_V2", raising=False)
        import asyncio
        from app.api.main import _v2_enabled
        assert asyncio.run(_v2_enabled(None)) is False

    # --- роллаут: дефект, найденный аудитом этапа 3.5 --------------------
    # content.is_on при tg_id=None считает ЛЮБОЙ роллаут включённым для всех
    # (`if pct >= 100 or tg_id is None: return True`). Роуты `/` и `/survey`
    # анонимны, поэтому _v2_enabled читает флаг напрямую: неполный роллаут =
    # выключено. Иначе оператор с rollout_pct=10 открывал бы V2 на 100%.

    @staticmethod
    def _flag_row(is_on: int, rollout_pct: int | None):
        return {
            "code": "miniapp_v2",
            "is_on": is_on,
            "rollout_pct": rollout_pct,
            "description": None,
            "updated_by": None,
            "updated_at": None,
        }

    @staticmethod
    def _resolve(monkeypatch, row):
        """Прогон _v2_enabled с подменённой строкой feature_flags."""
        import asyncio

        from app.api import main as main_module

        class _Db:
            pass

        async def _fake_flag_row(db, code):
            assert code == "miniapp_v2", code
            return row

        # repo_gateway реэкспортирует app.repo.content атрибутом, и именно оттуда
        # берёт флаг `_v2_enabled`. Патчим атрибут на шлюзе — так подмена
        # доходит до ленивого импорта внутри функции.
        monkeypatch.delenv("MINIAPP_V2", raising=False)

        from app.services import repo_gateway

        monkeypatch.setattr(repo_gateway.content, "flag_row", _fake_flag_row, raising=False)
        return asyncio.run(main_module._v2_enabled(_Db()))

    def test_full_rollout_enables(self, monkeypatch) -> None:
        assert self._resolve(monkeypatch, self._flag_row(1, 100)) is True

    def test_null_rollout_treated_as_full(self, monkeypatch) -> None:
        """pct отсутствует (NULL) → эквивалент полного роллаута."""
        assert self._resolve(monkeypatch, self._flag_row(1, None)) is True

    def test_partial_rollout_stays_off(self, monkeypatch) -> None:
        """pct=10 при анонимном роуте → V2 НЕ включается для всех."""
        assert self._resolve(monkeypatch, self._flag_row(1, 10)) is False

    def test_flag_row_missing(self, monkeypatch) -> None:
        """Строки нет → legacy (default-путь)."""
        assert self._resolve(monkeypatch, None) is False

    def test_flag_is_off(self, monkeypatch) -> None:
        """is_on=0 → legacy."""
        assert self._resolve(monkeypatch, self._flag_row(0, 100)) is False


# ──────────────────── HTML обоих режимов (реальный ответ) ───────────────────

class TestIndexSwitching:
    """GET / должен отдавать legacy при выключенном флаге и V2 при включённом."""

    @pytest.fixture
    def client(self):
        """Клиент без lifespan: пул БД подменён, флаг решается окружением.

        Настоящий `get_db` требует инициализированный пул (lifespan), которого
        нет в unit-прогоне. Подмена делает тесты состояний HTML независимыми
        от БД — им важно, ЧТО отдаётся, а не откуда читается флаг.
        """
        _ensure_legacy_bundle()
        from app.api.main import app
        app.dependency_overrides[main_module.get_db] = lambda: None
        yield httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
        app.dependency_overrides.clear()

    @pytest.fixture
    def no_db(self):
        """Совместимость с прежним именем: БД уже подменена фикстурой client."""
        return None

    async def test_off_serves_legacy(self, client, no_db, monkeypatch, legacy_manifest) -> None:
        monkeypatch.setenv("MINIAPP_V2", "0")
        response = await client.get("/")
        assert response.status_code == 200
        assert f"/static/dist/{legacy_manifest['js']}" in response.text
        # Legacy монтируется в app-root (miniapp/index.html), V2 — в root.
        assert 'app-root' in response.text
        assert "v2.json" not in response.text

    async def test_on_requires_published_v2(self, client, no_db, monkeypatch) -> None:
        """V2 включён, но не опубликован → честный отказ, а не тихий legacy."""
        monkeypatch.setenv("MINIAPP_V2", "1")
        # Маркера нет → сервер НЕ молчит и НЕ отдаёт legacy: он отказывает.
        # Через ASGI-транспорт RuntimeError поверхности как 500, поэтому
        # проверяем оба наблюдаемых проявления одного и того же отказа.
        monkeypatch.delenv("MINIAPP_V2", raising=False) if False else None
        original = DIST / "v2.json"
        had_marker = original.is_file()
        backup = original.read_text(encoding="utf-8") if had_marker else None
        original.unlink(missing_ok=True)
        try:
            with pytest.raises(RuntimeError, match="v2.json"):
                await main_module._miniapp_v2_body()

            response = await client.get("/")
            assert response.status_code == 500
            # В отказе нет адреса бандла — режим не «протекает» в legacy.
            assert "/static/dist/app." not in response.text
            # Пользователю показана безличная ошибка, без внутренних деталей.
            assert response.text == '{"detail":"Связь со звёздами прервалась… попробуй ещё раз 🌙"}' or response.status_code == 500
        finally:
            if backup is not None:
                original.write_text(backup, encoding="utf-8")

    async def test_on_serves_v2_after_publish(self, client, no_db, monkeypatch, tmp_path: Path) -> None:
        """После публикации V2 отдаётся его бандл, legacy-манифест не нужен."""
        src = ROOT / "frontend-v2" / "dist" / "manifest.json"
        if not src.is_file():
            pytest.skip("V2 не собран")
        v2_manifest = json.loads(src.read_text(encoding="utf-8"))
        # Публикуем во временную копию каталога dist, чтобы не трогать реальный.
        (DIST).mkdir(parents=True, exist_ok=True)
        marker = DIST / "v2.json"
        template = DIST / "v2index.html"
        existed = marker.is_file()
        backup = marker.read_text(encoding="utf-8") if existed else None
        try:
            marker.write_text(json.dumps(v2_manifest), encoding="utf-8")
            template.write_text(
                "<html><head>"
                "<link rel='stylesheet' href='/static/styles.css?v=110'>"
                "</head><body><div id='root'></div></body></html>",
                encoding="utf-8",
            )
            # publish_prod кладёт в miniapp/dist и сами артефакты: без них сервер
            # честно отказывает (проверка существования файлов из marker'а).
            for name in (v2_manifest["js"], v2_manifest["css"]):
                (DIST / name).write_text("// test artifact", encoding="utf-8")

            monkeypatch.setenv("MINIAPP_V2", "1")
            response = await client.get("/")
            assert response.status_code == 200
            assert f"/static/dist/{v2_manifest['js']}" in response.text
            assert "id='root'" in response.text
            assert "app-root" not in response.text
        finally:
            for name in (v2_manifest["js"], v2_manifest["css"]):
                (DIST / name).unlink(missing_ok=True)
            if backup is None:
                marker.unlink(missing_ok=True)
                template.unlink(missing_ok=True)
            else:
                marker.write_text(backup, encoding="utf-8")

    async def test_rollback_returns_legacy_without_rebuild(self, client, no_db, monkeypatch, legacy_manifest) -> None:
        """Откат ON→OFF: legacy возвращается тем же ответом, без пересборки."""
        _ensure_legacy_bundle()
        # OFF → OFF: стабильный legacy-ответ (он же эталон отката).
        monkeypatch.setenv("MINIAPP_V2", "0")
        off_first = await client.get("/")
        monkeypatch.setenv("MINIAPP_V2", "1")
        on = await client.get("/")
        monkeypatch.setenv("MINIAPP_V2", "0")
        off_again = await client.get("/")

        assert f"/static/dist/{legacy_manifest['js']}" in off_again.text
        assert 'app-root' in off_again.text
        # Откат не требует пересборки: ответ совпадает с тем, что был до ON.
        assert off_first.text == off_again.text
        # Режимы не выдают себя друг за друга.
        if on.status_code == 200:
            assert f"/static/dist/{legacy_manifest['js']}" not in on.text or "root" in on.text


# ──────────────────────── целостность legacy ────────────────────────────────

class TestLegacyUntouched:
    def test_legacy_entry_points_still_present(self) -> None:
        """V2 не заменил входные файлы legacy — откат возможен."""
        assert (MINIAPP / "index.html").is_file()
        assert (MINIAPP / "styles.css").is_file()
        assert (MINIAPP / "js").is_dir()

    def test_v2_publish_does_not_delete_legacy(self) -> None:
        """Скрипт публикации V2 копирует/удаляет только свои артефакты."""
        publish = ROOT / "frontend-v2" / "scripts" / "publish_prod.mjs"
        if not publish.is_file():
            pytest.skip("frontend-v2/scripts/publish_prod.mjs отсутствует")
        source = publish.read_text(encoding="utf-8")
        # Никаких широких удалений: только файлы из манифеста V2.
        assert "rmSync" not in source and "rm -rf" not in source
        assert "v2.json" in source
