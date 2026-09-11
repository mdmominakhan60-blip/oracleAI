"""BUS-847: маскирование секретов (test_secret_scrub) не режет честный текст."""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.test_secret_scrub import (  # noqa: E402
    SecretScrubber,
    collect_secret_values,
    install_repr_patch,
    install_logging_filter,
    make_scrubber,
)

PASSWORD = "supersecret-pw-1234"


def _env() -> dict[str, str]:
    return {
        "TEST_DATABASE_URL": f"postgresql+asyncpg://oracle_test:{PASSWORD}@postgres:5432/oracle_test",
        "DATABASE_URL": "",
        "POSTGRES_PASSWORD": PASSWORD,
        "BOT_TOKEN": "123456:ABCDEF-tg-bot-token-xyz",
        "DEV_KEY": "short" ,  # короче порога — не маскируется
    }


def test_collect_includes_url_password_and_plain_secret():
    values = collect_secret_values(env=_env(), env_file=ROOT / ".env.example")
    assert PASSWORD in values
    assert "123456:ABCDEF-tg-bot-token-xyz" in values
    # URL целиком не needle — только scheme://netloc и пароль
    assert not any(v.startswith("postgresql+asyncpg://oracle_test:super") and "@" in v and v.endswith("oracle_test")
                   for v in values if v != f"postgresql+asyncpg://oracle_test:{PASSWORD}")
    assert "short" not in values


def test_scrub_masks_longest_first_and_plural():
    scrubber = SecretScrubber([PASSWORD, "123456:ABCDEF-tg-bot-token-xyz"])
    text = (f"ConnectionParameters(password='{PASSWORD}', database='db') "
            f"token=123456:ABCDEF-tg-bot-token-xyz")
    masked = scrubber(text)
    assert PASSWORD not in masked
    assert "123456:ABCDEF-tg-bot-token-xyz" not in masked
    assert "database='db'" in masked  # честный текст не тронут


def test_repr_patch_masks_asyncpg_parameters():
    pytest.importorskip("asyncpg.connect_utils")
    import asyncpg.connect_utils as cu
    CP = cu._ConnectionParameters
    fields = dict.fromkeys(CP._fields)
    fields.update(user="oracle", password=PASSWORD, database="db")
    scrubber = SecretScrubber([PASSWORD])
    assert install_repr_patch(scrubber) is True
    params = CP(**fields)
    rendered = repr(params)
    assert PASSWORD not in rendered
    assert "password='***'" in rendered
    # Атрибут отдаёт реальное значение — коду нужна честная пара для коннекта.
    assert params.password == PASSWORD


def test_logging_filter_masks_record_text(caplog):
    scrubber = SecretScrubber([PASSWORD])
    assert install_logging_filter(scrubber) is True
    with caplog.at_level(logging.INFO, logger="bus847.test"):
        logging.getLogger("bus847.test").info(
            "connect failed with %s", f"postgresql://oracle:{PASSWORD}@h/db")
    assert PASSWORD not in caplog.text
    assert "***" in caplog.text


def test_make_scrubber_reads_real_env_or_example():
    needles, scrubber = make_scrubber()
    # Дерево без тест-DB не обязано иметь значения; scrubber должен работать.
    assert scrubber("clean text") == "clean text"
    assert isinstance(needles, list)


def test_conftest_scrubs_report(monkeypatch):
    """Скраб отчёта: longrepr и sections проходят через маскирование."""
    from tests import conftest as cf

    monkeypatch.setattr(cf, "_needs", True)
    seen: list[str] = []
    scrub = lambda text: seen.append(text) or text.replace(PASSWORD, "***")  # noqa: E731
    monkeypatch.setattr(cf, "_scrub", scrub)

    class _Outcome:
        def __init__(self, result):
            self._r = result

        def get_result(self):
            return self._r

    class _Report:
        longrepr = f"ConnectionParameters(password='{PASSWORD}')"
        sections = [("Captured stdout", f"token {PASSWORD} tail")]

    report = _Report()
    gen = cf.pytest_runtest_makereport(None, None)
    next(gen)                       # до yield
    with pytest.raises(StopIteration):
        gen.send(_Outcome(report))   # пост-фаза получает outcome
    assert len(seen) == 2
    # Хук пишет instance-атрибуты; с них pytest потом читает при выводе.
    assert report.longrepr == "ConnectionParameters(password='***')"
    assert report.sections == [("Captured stdout", "token *** tail")]


def test_release_gate_log_secrets_green_and_red(tmp_path, monkeypatch):
    """Гейт: зелёный на чистом дереве, красный при инъекции секрета в *.log."""
    import scripts.release_gate as rg

    env_file = tmp_path / ".env"
    env_file.write_text(f"POSTGRES_PASSWORD={PASSWORD}\nBOT_TOKEN=\n")
    monkeypatch.setattr(rg, "ROOT", tmp_path)

    assert rg.check_log_secrets() == []

    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    (log_dir / "make-test.log").write_text(
        "psql://oracle:supersecret-pw-1234@h/db\nsafe line\n")
    errors = rg.check_log_secrets()
    assert len(errors) == 1
    assert str(log_dir.joinpath("make-test.log").relative_to(tmp_path)) in errors[0]
    assert PASSWORD not in errors[0]  # значение не печатаем в вердикте


def test_release_gate_log_gate_url_password_extracted(tmp_path, monkeypatch):
    import scripts.release_gate as rg

    env_file = tmp_path / ".env"
    env_file.write_text(
        f"DATABASE_URL=postgresql://oracle:{PASSWORD}@postgres:5432/oracle\n")
    monkeypatch.setattr(rg, "ROOT", tmp_path)
    (tmp_path / "run.log").write_text(f"DSN postgresql://oracle:{PASSWORD}@pg\n")
    assert rg.check_log_secrets(), "пароль из DATABASE_URL должен ловиться"
