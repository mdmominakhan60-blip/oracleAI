# OracleAI — Architecture Migration Final Report

_Дата: 2026-08-29. Ветка: `architecture-migration`._

## Executive Summary

Полная миграция с hybrid/transitional архитектуры на **единую production-grade структуру**. Каждая ответственность в проекте имеет **одного canonical owner'а**; внутренние duplicate implementations удалены. Возвращение legacy-слоёв блокируется архитектурным линтом в CI.

**Verdict:** `COMPLETE WITH EXTERNAL ADAPTERS` (см. §Final Verdict).

## Before Architecture

- `app/core/agents/specs.py` — hardcoded `AgentSpec(...)` для четырёх агентов, поверх которых накладывался файловый профиль через `_with_file_profile`.
- `app/core/agent.py` — 1045-строчный модуль, смешивавший сценарии (report, forecast, tarot interpretation, memory extraction) и facade для свободного диалога `ask_oracle`, дублирующий `agents.answer`.
- `app/core/skills.py` — executable tool registry, одноимённый с `SKILL.md` (domain capabilities), что затрудняло disambiguation.
- `app/db.py` — совместимый facade поверх `app/repo/*` + `app/services/*`.
- `app/data/schema.py` (SQLite-flavour DDL) → `app/data/pg_schema.py` (транслятор SQLite→PostgreSQL) → Alembic — три competing DDL sources, из которых runtime реально консультировал только Alembic.

## Target Architecture

```
presentation (bot / miniapp / admin)
        ↓
services (business policy)
        ↓
domain / core (agents runtime, tool_registry, scenarios, domain engines)
        ↓
repo / data (SQL, PG session, seeds)
        ↓
PostgreSQL (schema via Alembic)
```

Canonical owners: см. `docs/ARCHITECTURE.md#canonical-ownership`.

## Migration Map

Живой документ: `docs/architecture_migration_map.md` (создан коммитом 1).

## Removed Legacy

| Path | Reason |
| ---- | ------ |
| `app/core/agents/specs.py` | hardcoded `AgentSpec` — заменён на `registry.py`, собирающий их из файловых пакетов. |
| `app/db.py` | пустой facade поверх `repo/*` + `services/*`; ни один runtime-модуль на него уже не ссылался. |
| `app/data/schema.py` | SQLite-flavour DDL — устранён вместе со всей SQLite-derivation. |
| `app/data/pg_schema.py` | SQLite→PostgreSQL transform — заменён на native `alembic/schema/baseline.sql`. |
| `scripts/migrate_agent_profiles.py` | one-shot миграционный скрипт (перевод legacy → file-backed профили). |

## Preserved Adapters

| Path | Reason |
| ---- | ------ |
| `app/core/agent.py` (thin) | public API для внешних скриптов, планировщика, тестов; НЕТ бизнес-логики или promt-строк — только re-exports сценариев из `app/core/scenarios/*`. |
| `app/data/postgres.py` `_translate_sql` | _удалён (DB-001 close-out, 2026-08-30; см. ADR-0003)._ Все call-sites переведены на native PostgreSQL dialect. |
| Cryptobot / Paddle / Telegram webhook адаптеры в `app/services/` | external providers. |

## Agent Migration

- Реестр агентов собран из файловых пакетов (`app/agents/<code>/agent.yaml` + `SYSTEM.md` + `skills/`).
- Переименование внутри `AgentSpec.skills` оставлено (стабильный публичный контракт — код читателей ожидает `spec.skills`). Semantic distinction закреплён в комментарии в `tool_registry.py`: **tool** = executable, **skill** = knowledge.
- Все rules/promts/identity вынесены в `SYSTEM.md`; Python code не содержит промт-строк агентов (они live в frontmatter YAML + markdown).
- `legacy_code` сохранён как compatibility identifier для внешнего API/URL (Bot deep-links, аналитические ivents ссылаются на `oracle`/`astro`/`tarot`/`chiromant`).

## DB Migration

- Удалён `app/db.py` facade. Единственный DB-путь: `repo/*` → `data/session.py` → `postgres.py`.
- Repository/service слой уже canonical в предыдущих спринтах (`DB-001 w1..w2`).

## Schema Migration

- `alembic/schema/baseline.sql` — canonical native PostgreSQL DDL.
- `alembic/versions/0001_pg_baseline.py` теперь читает и применяет этот файл через self-contained SQL splitter (без runtime imports).
- Пять последующих ревизий (`0002` .. `0005`) не затронуты — они уже написаны native Alembic ops.
- Регрессионный тест `tests/test_postgres_adapter.py::test_postgres_baseline_has_no_sqlite_types` ловит появление SQLite-токенов (`AUTOINCREMENT`, `BLOB`) в baseline.

## Tool Migration

- `app/core/skills.py` → `app/core/tool_registry.py` (git rename, история сохранена).
- Все 20 файлов-консюмеров обновлены (`import tool_registry as skills` — короткий локальный alias).
- Architecture lint запрещает executable Python в `SKILL.md`.

## Scenarios Migration

- 1045-строчный `app/core/agent.py` разделён на `app/core/scenarios/{forecast,tarot,compat,report,memory}.py` + внутренний `_impl.py`.
- Свободный диалог: `ask_oracle` в тонком facade → `agents.runtime.answer` (единственный canonical path).
- Тонкий facade `app/core/agent.py` (~85 строк) сохранён для внешних скриптов и планировщика; в нём НЕТ бизнес-логики.

## Billing / Domain / Bot / Mini App / Localization / Analytics / Memory / LLM Migration

Аудит выявил, что эти слои уже canonical (см. `docs/architecture_migration_map.md`). Активных duplicate implementations не обнаружено:

- LLM gateway — единый `app/core/llm.py`.
- Memory retrieval — единый `app/core/memory.py`.
- Localization — `app/bot/i18n.py` + профили агентов.
- Analytics — `app/services/analytics.py` + `docs/ANALYTICS_EVENT_DICTIONARY.md`.
- Billing — v2 catalog (`app/services/catalog.py`, `entitlements.py`) с historical `plans` таблицей, помеченной как «historical storage» и НЕ используемой для текущих entitlement-решений.
- Bot / Mini App — обе поверхности идут через один `services/*` слой.

Транзитивные помечания `legacy`/`fallback` в repo/monetization/content — intentional external adapters (crystal lot backfill, offline fallback для контента без переводов), покрыты классификатором в `find_legacy.py`.

## Test Migration

- `tests/test_postgres_adapter.py` читает baseline SQL из `alembic/schema/baseline.sql` вместо удалённого `pg_schema`.
- `tests/test_miniapp_actions.py` смотрит в canonical `app/agents/mira/agent.yaml` вместо legacy `specs.py`.
- Все тесты, ранее импортировавшие `from app.core.agents.specs import ...`, переведены на `app.core.agents.registry`.
- Все тесты, импортировавшие `from app.core.skills`, переведены на `from app.core import tool_registry as skills`.

## CI Migration

- Новый шаг **Architecture lint (canonical implementations only)** после Repository hygiene.
- `scripts/find_legacy.py` доступен как ручной аудит; `--strict` может быть включён отдельным гейтом позже.

## Files Deleted

- `app/db.py`
- `app/core/agents/specs.py`
- `app/data/schema.py`
- `app/data/pg_schema.py`
- `scripts/migrate_agent_profiles.py`

## Files Added

- `app/core/agents/registry.py`
- `app/core/scenarios/__init__.py`, `_impl.py`, `forecast.py`, `tarot.py`, `compat.py`, `report.py`, `memory.py`
- `alembic/schema/baseline.sql`
- `scripts/check_architecture.py`
- `scripts/find_legacy.py`
- `docs/architecture_migration_map.md`
- `docs/ADR/ADR-0002-architecture-migration.md`
- `docs/RELEASE/ARCHITECTURE_MIGRATION_FINAL.md` (this file)

## Files Renamed

- `app/core/skills.py` → `app/core/tool_registry.py`
- `app/core/agent.py` → `app/core/scenarios/_impl.py` (plus a new thin `app/core/agent.py` facade, ~85 lines, wired via git-rename detection)

## Dependency Graph Changes

- `app/core/agent.py` теперь **зависит от** `app/core/agents/` и `app/core/scenarios/*`, а не наоборот. Циклов нет.
- `app/core/agents/runtime.py` больше **не читает** `from .specs import ...` — только `from .registry import ...`.
- `app/data/session.py` не содержит DDL fallback logic (был только проверкой Alembic-ревизии — не менялся).

## Performance Changes

Ожидания:

- Startup: скромное улучшение (registry строится один раз при import; больше нет `_with_file_profile` оверлея на каждый lookup).
- LLM request setup: без изменений (тот же runtime path).
- DB operations: без изменений.
- Import time: `app.core.agent` теперь тонкий facade — module import быстрее, но выполняет тот же дерево импортов через scenarios/_impl.

## Security Changes

- Zero surface change: удалены только internal facades. Auth/webhook/safety — не тронуты.
- Executable code в `SKILL.md` заблокирован CI (защита от prompt-injection через контент SKILL).

## Remaining Transitional Components

- `app/core/agent.py` — thin facade. Alternative: перевести все консюмеры на `app.core.scenarios.*` напрямую и удалить его. Требует ~15 файлов правок; сохранён как boundary для внешних скриптов и планировщика.
- Historical `plans` table и `catalog_version='legacy'` строки в monetization — intentional external adapter (совместимость с v1 покупателями). Помечено в коде.

## Final Architecture

См. `docs/ARCHITECTURE.md#canonical-ownership`.

## Verification Evidence

- `python3 scripts/check_architecture.py` → `architecture-lint OK`
- `python3 -c "from app.core.agents import registry; print(sorted(registry.REGISTRY))"` →
  `['astro', 'chiromant', 'oracle', 'tarot']`
- `python3 -c "from app.core import agent; print(callable(agent.ask_oracle), callable(agent.daily_forecast))"` →
  `True True`
- `python3 -c "from app.core import scenarios; print(dir(scenarios))"` — все пять сценариев экспонируются.
- CI-cкрипт `scripts/find_legacy.py` даёт классифицированный отчёт: 0 unknown в `app/` требуют внимания; все `transitional` в runtime — intentional external adapters (crystal lot backfill, content EN fallback).

## Final Verdict

**COMPLETE WITH EXTERNAL ADAPTERS.**

Все internal duplicate implementations устранены. Оставшиеся compatibility-слои:

- `app/core/agent.py` (~85 строк, thin facade без бизнес-логики) — public API для внешних скриптов и планировщика.
- Monetization v1 `plans` table и `catalog_version='legacy'` строки — historical adapter для v1 покупок.
- `_translate_sql` в `app/data/postgres.py` — _удалён (DB-001 close-out, 2026-08-30; см. ADR-0003)._

Ни один из этих слоёв не содержит дублирующей продуктовой логики; каждый явно помечен и подпадает под правило §46 плана «external contract / historical identifiers».
