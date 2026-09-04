"""Каталог агентов — canonical source of truth.

Ответственности:
- Загружать файловые пакеты `app/agents/<code>/{agent.yaml,SYSTEM.md,skills/}`
  через `file_loader.load_profiles()`;
- Собирать из них immutable `AgentSpec` (см. `base.AgentSpec`);
- Экспонировать реестр по `legacy_code` (для внешних API/URL и bot handlers),
  который стабилен между версиями продукта.

`AgentSpec` — это data class; никакой бизнес-логики или promt-строк здесь нет.
Идентичность агента, правила и знания лежат в `SYSTEM.md` и `skills/*/SKILL.md`.

Правило миграции: hardcoded `AgentSpec(code="oracle", ..., rules="...")` строго
запрещены вне этого модуля. Архитектурный lint (`scripts/check_architecture.py`)
ловит их автоматически.
"""
from __future__ import annotations

from pathlib import Path

from .base import AgentSpec
from .file_loader import FileProfile, load_profiles


def _spec_from_profile(profile: FileProfile) -> AgentSpec:
    """Превращает файловый профиль в runtime `AgentSpec`.

    Атрибуты spec берутся исключительно из `agent.yaml` и `SYSTEM.md`. Единственная
    точка, где `legacy_code` попадает в код — это `AgentSpec.code`: он остаётся
    стабильным идентификатором для публичного API (ссылки, аналитика, deep-links).
    """
    data = profile.data
    limits = data.get("limits") if isinstance(data.get("limits"), dict) else {}
    return AgentSpec(
        code=profile.legacy_code,
        name=str(data.get("name", profile.agent_id)),
        emoji=str(data.get("emoji", "")),
        title=str(data.get("title", profile.agent_id)),
        tagline=str(data.get("tagline", "")),
        style="",   # persona подставляется динамически в runtime
        rules=profile.system,
        skills=tuple(data.get("tools", ())),
        greeting=str(data.get("greeting", "")),
        accent=str(data.get("accent", "#e8c56b")),
        tier=str(data.get("tier", "main")),
        max_tokens=int(data.get("max_tokens", 1500)),
        uses_persona=bool(data.get("uses_persona", False)),
        history_limit=int(data.get("history_limit", 14)),
        suggestions=tuple(data.get("suggestions", ())),
        skills_max_active=max(1, int(data.get("skills_max_active", 3))),
        max_turns=max(1, int(limits.get("max_turns", 6))),
        max_tool_calls=max(1, int(limits.get("max_tool_calls", 8))),
        timeout_s=max(1.0, float(limits.get("timeout_s", 35.0))),
        memory_mode=str(data.get("memory", "opt_in")),
        risk_level=str(data.get("risk_level", "medium")),
        output_contract=str(data.get("output_contract", "agent_response.v1")),
    )


def _build_registry() -> dict[str, AgentSpec]:
    profiles = load_profiles()
    if not profiles:
        raise RuntimeError(
            "No agent profiles found under app/agents/. Every canonical agent "
            "must be a directory with agent.yaml + SYSTEM.md + skills/.")
    registry: dict[str, AgentSpec] = {}
    for profile in profiles.values():
        spec = _spec_from_profile(profile)
        if spec.code in registry:
            raise RuntimeError(f"duplicate legacy_code in agent registry: {spec.code}")
        registry[spec.code] = spec
    return registry


REGISTRY: dict[str, AgentSpec] = _build_registry()
DEFAULT_AGENT = "oracle"  # legacy_code of the Lilith profile


def get(code: str | None) -> AgentSpec:
    """Агент по коду. Неизвестный код — Оракул: чат не должен ломаться."""
    return REGISTRY.get(code or "", REGISTRY[DEFAULT_AGENT])


def codes() -> tuple[str, ...]:
    return tuple(REGISTRY)


def reload(root: Path | None = None) -> dict[str, AgentSpec]:
    """Пересобрать реестр из файлов (для админ-хот-релоад-сценариев)."""
    global REGISTRY  # noqa: PLW0603
    from . import file_loader
    if root is not None:
        file_loader._PROFILE_CACHE.clear()  # noqa: SLF001
    REGISTRY = _build_registry()
    return REGISTRY
