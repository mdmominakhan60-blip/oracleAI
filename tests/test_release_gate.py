from __future__ import annotations

from scripts import release_gate


def test_static_release_gate_passes_repository_contract():
    assert release_gate.run(production=False) == []


def test_production_release_gate_fails_closed_without_real_env(monkeypatch):
    for name in (
        "APP_ENV", "DEV_MODE", "WEBAPP_URL", "BOT_TOKEN", "ADMIN_ID",
        "POSTGRES_PASSWORD", "GRAFANA_ADMIN_PASSWORD", "DATABASE_URL", "RELEASE_ID",
    ):
        monkeypatch.delenv(name, raising=False)
    errors = release_gate.run(production=True)
    assert "APP_ENV must equal production" in errors
    assert "DEV_MODE must be disabled" not in errors
    assert "WEBAPP_URL must be an HTTPS URL" in errors
    assert "BOT_TOKEN is missing" in errors
    assert "ADMIN_ID is missing" in errors


def test_production_release_gate_accepts_minimal_safe_env(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DEV_MODE", "0")
    monkeypatch.setenv("WEBAPP_URL", "https://oracle.example")
    monkeypatch.setenv("BOT_TOKEN", "test-token")
    monkeypatch.setenv("ADMIN_ID", "1001")
    monkeypatch.setenv("POSTGRES_PASSWORD", "a-long-random-production-secret")
    monkeypatch.setenv("GRAFANA_ADMIN_PASSWORD", "another-long-random-production-secret")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://oracle:secret@postgres:5432/oracle")
    monkeypatch.setenv("RELEASE_ID", "2026.08.27-test")
    monkeypatch.setenv("REDIS_URL", "redis://redis:6379/0")
    assert release_gate.run(production=True) == []


def test_compose_requires_non_default_credentials():
    from pathlib import Path

    compose = (Path(__file__).parents[1] / "infra" / "docker-compose.yml").read_text()
    env_example = (Path(__file__).parents[1] / ".env.example").read_text()

    assert "POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?" in compose
    assert "DATABASE_URL: ${DATABASE_URL:?" in compose
    assert "GF_SECURITY_ADMIN_PASSWORD: ${GRAFANA_ADMIN_PASSWORD:?" in compose
    assert "POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-oracle}" not in compose
    assert "GF_SECURITY_ADMIN_PASSWORD: ${GRAFANA_ADMIN_PASSWORD:-change-me}" not in compose
    assert "POSTGRES_PASSWORD=oracle" not in env_example
    assert "GRAFANA_ADMIN_PASSWORD=change-me" not in env_example


def test_production_release_gate_rejects_template_database_credentials(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DEV_MODE", "0")
    monkeypatch.setenv("WEBAPP_URL", "https://oracle.example")
    monkeypatch.setenv("BOT_TOKEN", "test-token")
    monkeypatch.setenv("ADMIN_ID", "1001")
    monkeypatch.setenv("POSTGRES_PASSWORD", "oracle")
    monkeypatch.setenv("GRAFANA_ADMIN_PASSWORD", "change-me")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///oracle.db")
    monkeypatch.setenv("RELEASE_ID", "2026.08.27-test")
    errors = release_gate.run(production=True)
    assert "POSTGRES_PASSWORD uses an unsafe template value" in errors
    assert "GRAFANA_ADMIN_PASSWORD uses an unsafe template value" in errors
    assert "DATABASE_URL must point to PostgreSQL" in errors
