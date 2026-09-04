# ADR-0002 — Architecture Migration to a Single Canonical Runtime

**Status:** Accepted
**Date:** 2026-08-29

## Context

Проект OracleAI переходил из legacy hybrid architecture к чистой production-grade
структуре. К моменту старта этой миграции существовали конкурирующие реализации
одной и той же ответственности:

- **Agents** — hardcoded `AgentSpec` в `app/core/agents/specs.py` **и** файловые
  профили `app/agents/<code>/{agent.yaml,SYSTEM.md,skills/}`. Первый работал как
  hardcoded fallback, поверх которого через `_with_file_profile` накладывался
  файловый профиль.
- **Tools / Skills** — модуль `app/core/skills.py` содержит executable
  tool registry, но имя перекрывалось с `SKILL.md` (domain capabilities).
- **Scenarios / free-form chat** — `app/core/agent.py` (60 KB) смешивал сценарии
  (report, forecast, tarot interpretation, memory extraction) и facade для
  свободного диалога, который дублирует `agents.answer`.
- **DB access** — `app/db.py` жил как совместимый facade поверх `repo/*` +
  `services/*`.
- **DB schema** — DDL описан одновременно в `app/data/schema.py` (SQLite-flavour)
  и в `app/data/pg_schema.py` (SQLite → PostgreSQL transform), при том что
  Alembic (`alembic/versions/*`) уже был обязательным runtime источником.

## Decision

Полностью устранить внутренние duplicate implementations. Оставить один canonical
owner на каждую ответственность:

1. **Agent identity/behaviour** — файловые пакеты `app/agents/<code>/` +
   canonical registry `app/core/agents/registry.py`. `specs.py` удалён,
   hardcoded `AgentSpec` вынесены в `AgentSpec.from_profile()` внутри registry.
2. **Executable tools** — `app/core/skills.py` → `app/core/tool_registry.py`,
   плюс архитектурный lint, запрещающий хранение executable кода в `SKILL.md`.
3. **Scenarios** — `app/core/agent.py` разделён на `app/core/scenarios/*.py`
   (`forecast.py`, `tarot.py`, `reports.py`, `memory.py`, `compat.py`). Свободный
   диалог всегда идёт через `app/core/agents/runtime.answer`; тонкий facade
   `app/core/agent.py` остаётся только как public re-export для внешних скриптов
   и планировщика.
4. **DB access** — `app/db.py` удалён. `scripts/selfcheck.py` и все остальные
   консюмеры импортируют напрямую `app.repo.*` / `app.services.*`.
5. **DB schema** — `app/data/schema.py` и `app/data/pg_schema.py` удалены.
   Alembic получает native PostgreSQL DDL в `0001_pg_native_baseline.py`.
6. **Architecture lint** — `scripts/find_legacy.py` и
   `scripts/check_architecture.py` включены в CI. Они отказывают, если снова
   появляется:
   - hardcoded `AgentSpec` вне `app/core/agents/registry.py`;
   - `from app.db import ...`;
   - executable Python в `SKILL.md`;
   - runtime schema creation через `schema.py` / `pg_schema.py`.

## Consequences

**Positive**

- Один путь свободного диалога, один tool registry, один DB source.
- Новый разработчик читает `docs/ARCHITECTURE.md` и не спрашивает «использовать
  ли `app.db`?».
- CI гарантирует, что дублирование не вернётся.

**Negative / migration cost**

- Требуется массовая правка импортов (`specs` → `registry`, `skills` →
  `tool_registry`).
- Alembic baseline пересобирается native PostgreSQL DDL — старые dev-базы, которые
  прогонялись по старой baseline через SQLite-derivation, должны быть
  переприменены с `alembic upgrade head`. Данные не теряются (используется
  `CREATE TABLE IF NOT EXISTS` + идентичная структура), но `alembic_version`
  переезжает на новую head-ревизию.

## Rollback Plan

Все коммиты миграции атомарны (см. `docs/RELEASE/ARCHITECTURE_MIGRATION_FINAL.md`).
Откат = `git revert` каждого коммита в обратном порядке (11 → 1). Однако Alembic
baseline пересобран — при rollback нужен ручной шаг: восстановить старую
baseline из git-истории.
