"""LLM-агенты сервиса.

Агент описывается ФАЙЛОВЫМ ПАКЕТОМ под `app/agents/<code>/`
(`agent.yaml` + `SYSTEM.md` + `skills/`). Runtime собирает из него immutable
`AgentSpec` через `registry.py`.

    registry.py      — canonical реестр (по legacy_code)
    file_loader.py   — загрузка агентских файлов + skill dependency graph
    base.py          — dataclass AgentSpec + сборка системного промпта
    context.py       — bounded history для tool-use
    routing.py       — выбор агента по вопросу пользователя
    runtime.py       — исполнение: контекст, инструменты, офлайн-подстраховка
    runtime_guard.py — единый wall-clock deadline публичного ответа
"""
from .base import SAFETY, AgentSpec, build_system_prompt  # noqa: F401
from .registry import DEFAULT_AGENT, REGISTRY, codes, get, reload  # noqa: F401
from .runtime import (agent_list, offline_answer, resolve,  # noqa: F401
                      system_for)
from .runtime_guard import answer

__all__ = [
    "AgentSpec", "SAFETY", "build_system_prompt", "REGISTRY", "DEFAULT_AGENT",
    "get", "codes", "reload", "resolve", "system_for", "answer", "offline_answer",
    "agent_list",
]
