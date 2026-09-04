# OracleAI — documentation map

## Document orientation

| Field | Definition |
|---|---|
| **Purpose** | Provide one navigable map of current product, engineering, operations, domain and release documentation. |
| **Source of truth** | This map points to the canonical document for each subsystem; implementation truth remains in the referenced code and tests. |
| **Scope** | Current contracts, operating procedures, feature and domain references. |
| **Do not change** | Do not create a second backlog, audit, status or architecture source of truth. Do not promote evidence or research notes into current behavior without code validation. |
| **Key files** | `README.md`, `docs/PRODUCT.md`, `docs/ARCHITECTURE.md`, `docs/AI_SYSTEM.md`, `docs/RELEASE/CURRENT_STATUS.md`. |
| **Validation** | Follow [`CONTRIBUTING.md`](CONTRIBUTING.md), run the commands in [`TESTING.md`](TESTING.md), and check links before release. |

## Start here

| Topic | Canonical document | When to read it | Related code |
|---|---|---|---|
| Product | [`PRODUCT.md`](PRODUCT.md) | Understand the audience, promise, boundaries and enabled surfaces. | `miniapp/`, `app/bot/`, `app/api/routers/` |
| Architecture | [`ARCHITECTURE.md`](ARCHITECTURE.md) | Change data flow, modules, storage, agents or client loading order. | `app/`, `miniapp/`, `infra/` |
| AI system | [`AI_SYSTEM.md`](AI_SYSTEM.md) | Change agents, skills, tools, context, memory, safety or provider behavior. | `app/core/agents/`, `app/core/tool_registry.py`, `app/core/llm.py` |
| Design | [`DESIGN_SYSTEM.md`](DESIGN_SYSTEM.md) | Change screens, tokens, components, motion, localization or accessibility. | `miniapp/css/`, `miniapp/js/`, `miniapp/index.html` |
| Admin architecture | [`ADMIN_ARCHITECTURE.md`](ADMIN_ARCHITECTURE.md) | Extend admin features, API wiring, layouts or styles without returning to monoliths. | `admin/src/`, `admin/styles/`, `admin/index.html` |
| API | [`API.md`](API.md) | Add or change an HTTP route, request, response, auth or error contract. | `app/api/`, `app/services/` |
| Security | [`SECURITY.md`](SECURITY.md) | Change identity, owner scope, consent, privacy, uploads, payments or safety. | `app/api/deps.py`, `app/api/security.py`, `app/core/safety.py` |
| Deployment | [`DEPLOYMENT.md`](DEPLOYMENT.md) | Build, configure, migrate, deploy or roll back the stack. | `Makefile`, `infra/`, `.env*.example` |
| Operations | [`OPERATIONS.md`](OPERATIONS.md) | Operate services, workers, backups, recovery or incidents. | `infra/docker-compose.yml`, `scripts/`, `app/tasks/` |
| Testing | [`TESTING.md`](TESTING.md) | Select checks for a change and interpret local versus external evidence. | `tests/`, `scripts/`, `.github/workflows/ci.yml` |
| Contributing | [`CONTRIBUTING.md`](CONTRIBUTING.md) | Prepare a branch, review a diff and complete a pull request. | `.github/`, `Makefile` |

## Domain and feature contracts

| Area | Canonical document | Related code |
|---|---|---|
| [PRODUCT.md](PRODUCT.md) | Product, support, маркетинг | Чтобы понять аудиторию, границы обещания и пользовательские сценарии. |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Разработка, техлид, QA | Чтобы менять код, API, модели данных или интеграции. |
| [DESIGN_SYSTEM.md](DESIGN_SYSTEM.md) | Дизайн, frontend, QA | Чтобы добавлять экраны, компоненты и motion без визуального дрейфа. |
| [API.md](API.md) | Frontend, backend, интеграции | Чтобы вызывать или изменять HTTP-контракты. |
| [DEPLOYMENT.md](DEPLOYMENT.md) | DevOps, владелец продукта | Чтобы подготовить окружение, выпустить релиз и откатить его. |
| [SECURITY.md](SECURITY.md) | Разработка, support, legal | Чтобы работать с согласиями, личными данными и инцидентами. |
| [ANALYTICS_EVENT_DICTIONARY.md](ANALYTICS_EVENT_DICTIONARY.md) | Product, analytics, privacy | Чтобы добавлять KPI-события без PII и трактовать funnel одинаково. |
| [LLM_EVALUATION.md](LLM_EVALUATION.md) | LLM, QA, product | Чтобы проверять grounding, safety, language, next step и latency до релиза. |
| [PALM_ENGINE_RESEARCH.md](PALM_ENGINE_RESEARCH.md) | AI, CV, legal, product | Исследование palm-line engines, лицензий, model contracts и безопасного integration boundary. |
| [LAUNCH_GOVERNANCE.md](RELEASE/LAUNCH_GOVERNANCE.md) | Product, operations, legal, support | Чтобы вести P0/P1 launch gates, владельцев, SLO и go/no-go decisions. |
| [PRODUCTION_READINESS.md](RELEASE/PRODUCTION_READINESS.md) | Все владельцы релиза | Чтобы пройти путь от beta до public launch и определить масштабирование. |
| [P0_PRODUCTION_EXECUTION_PLAN.md](RELEASE/P0_PRODUCTION_EXECUTION_PLAN.md) | Release, security, payments, AI quality, operations | Чтобы закрыть P0-001—P0-004 по процедурам, evidence, go/no-go и rollback. |
| [COMPOSITE_AND_RETURNS_PRODUCT_SPEC.md](COMPOSITE_AND_RETURNS_PRODUCT_SPEC.md) | Product, astrology, backend, QA | Чтобы реализовать будущие composite и planetary returns без неявных precision-правил. |
| [DESIGN_COMPONENT_INVENTORY.md](DESIGN_COMPONENT_INVENTORY.md) | Design, frontend, QA | Чтобы сохранять состояния компонентов, accessibility и visual regression matrix. |
| [SCALE_AND_MIGRATION.md](SCALE_AND_MIGRATION.md) | Operations, database, performance | Чтобы измерять PostgreSQL/pgvector нагрузку и репетировать migration без production риска. |
| [CHART_PRODUCT_CONTRACTS.md](CHART_PRODUCT_CONTRACTS.md) | Frontend, backend, agent, QA | Чтобы вызывать текущие natal, synastry и transit contracts одинаково. |
| [CHART_TYPE_CAPABILITIES.md](CHART_TYPE_CAPABILITIES.md) | Product, astrology, release owner | Чтобы отличать enabled product paths от upstream capabilities. |
| [BILLING.md](FEATURES/BILLING.md) | Product, billing, finance | Чтобы сверить текущие планы, SKU, платёжные пути и открытые gaps без PII. |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Все участники разработки | Чтобы подготовить ветку, изменения и pull request. |
| [CONTRACTS.md](DOMAIN/CONTRACTS.md), [AGENT_ARCHITECTURE.md](AGENT_ARCHITECTURE.md), [MEMORY.md](FEATURES/MEMORY.md) | Domain, AI, product | Расчётные школы, evidence-first агенты и memory policy. |
| [PDF_SYSTEM.md](PDF_SYSTEM.md), [PDF_TEMPLATE_CATALOG.md](PDF_TEMPLATE_CATALOG.md), [TESTING.md](TESTING.md) | QA, backend, product | Отчёты, product-specific template gates, visual regression и проверочные слои. |
| [FULL_PRODUCT_SURFACE.md](FULL_PRODUCT_SURFACE.md), [TASKS.md](RELEASE/TASKS.md) | Все владельцы | Surface matrix и текущий backlog. |
| [HISTORY.md](FEATURES/HISTORY.md) | Frontend, backend, privacy, QA | Cross-tool archive read model, deep links, deletion ownership and palm boundary. |
| [ANALYTICS_EVENT_DICTIONARY.md](ANALYTICS_EVENT_DICTIONARY.md), `product_cost_events` | Product, finance, privacy, operations | Privacy-safe product cost, delivery, refund and support dimensions without user content. |
| [MEMORY_EVALUATION.md](MEMORY_EVALUATION.md) | AI, privacy, QA | Synthetic relevance, pause, isolation, contradiction and prompt-injection evaluation. |
| [LOCALIZATION_GLOSSARY.md](LOCALIZATION_GLOSSARY.md) | Product, frontend, content, QA | RU/EN technical labels, truth states, Tarot terms and pluralization rules. |
| [API_RESILIENCE_MATRIX.md](API_RESILIENCE_MATRIX.md) | Backend, frontend, QA | Negative-path, rate-limit, backend-error and owner-scope checks. |
| [BACKUP_RESTORE_DRILL.md](BACKUP_RESTORE_DRILL.md) | Operations, database, security | Disposable integrity, restore, snapshot and isolation drill. |
| [PRODUCTION_GAUNTLET.md](PRODUCTION_GAUNTLET.md) | Release, security, reliability, operations | Full audit matrix, findings, local evidence and external gates. |
| [PRODUCTION_FINAL_REVIEW.md](PRODUCTION_FINAL_REVIEW.md) | Release owner, product, operations | Evidence-based final review and exact BLOCKED/SHIP IT verdict. |
| [`models/THIRD_PARTY_NOTICES.md`](../models/THIRD_PARTY_NOTICES.md) | Legal, release, ML | Provenance, MIT notice, checksums and limitations for the vendored palm-line models. |
| [COMPETITOR_MATRIX.md](COMPETITOR_MATRIX.md) | Product, strategy | First-party competitor benchmark и product gaps. |
| [CHANGELOG.md](RELEASE/CHANGELOG.md) | Все стейкхолдеры | Чтобы сверить состав версии и пользовательские изменения. |
| Domain index | [`DOMAIN/README.md`](DOMAIN/README.md) | `app/core/` |
| Shared calculation/evidence policy | [`DOMAIN/CONTRACTS.md`](DOMAIN/CONTRACTS.md) | `app/core/astro.py`, `chart_contract.py`, `tarot.py`, `palm/` |
| Astrology and chart products | [`DOMAIN/ASTROLOGY.md`](DOMAIN/ASTROLOGY.md) and [`CHART_PRODUCT_CONTRACTS.md`](CHART_PRODUCT_CONTRACTS.md) | `app/core/astro.py`, `vedic.py`, `chart_products.py` |
| Tarot and card reflection | [`DOMAIN/TAROT.md`](DOMAIN/TAROT.md) | `app/core/tarot.py`, `app/api/routers/tarot.py` |
| Palm and visual evidence | [`DOMAIN/PALM.md`](DOMAIN/PALM.md) | `app/core/palm*.py`, `app/api/routers/placements.py` |
| Memory | [`FEATURES/MEMORY.md`](FEATURES/MEMORY.md) | `app/core/memory.py`, profile routes, repositories |
| Unified history | [`FEATURES/HISTORY.md`](FEATURES/HISTORY.md) | `app/api/routers/history.py`, `app/repo/readings.py` |
| Billing and monetization | [`FEATURES/BILLING.md`](FEATURES/BILLING.md) | `app/services/billing.py`, shop/webhook routes |

## Release and evidence

| Type | Canonical document | Purpose |
|---|---|---|
| Current status | [`RELEASE/CURRENT_STATUS.md`](RELEASE/CURRENT_STATUS.md) | The only current go/no-go statement, separated by LOCAL, STAGING, PRODUCTION and EXTERNAL. |
| Current backlog | [`RELEASE/TASKS.md`](RELEASE/TASKS.md) | The only authoritative list of unresolved work, acceptance criteria, evidence and blockers. |
| Production readiness | [`RELEASE/PRODUCTION_READINESS.md`](RELEASE/PRODUCTION_READINESS.md) | Release process and readiness gates. |
| Launch governance | [`RELEASE/LAUNCH_GOVERNANCE.md`](RELEASE/LAUNCH_GOVERNANCE.md) | Owners, gates, SLO placeholders and go/no-go rules. |
| P0 execution | [`RELEASE/P0_PRODUCTION_EXECUTION_PLAN.md`](RELEASE/P0_PRODUCTION_EXECUTION_PLAN.md) | Owner-led procedures for the four public-launch blockers. |
| Changelog | [`RELEASE/CHANGELOG.md`](RELEASE/CHANGELOG.md) | User- and engineering-visible release history. |
| Final QA matrix | [`RELEASE/FINAL_QA_MATRIX.md`](RELEASE/FINAL_QA_MATRIX.md) | Functional, browser and red-team checks with reproducible evidence. |
| Final release certification | [`RELEASE/FINAL_RELEASE_CERTIFICATION.md`](RELEASE/FINAL_RELEASE_CERTIFICATION.md) | Final build, QA, security scorecard, blockers and verdict. |

## Supporting references

These documents provide focused implementation, research or operational context without competing with the canonical contracts above.

| Area | Reference |
|---|---|
| Observability | [`OBSERVABILITY.md`](OBSERVABILITY.md) |
| AI evaluation and agent quality | [`LLM_EVALUATION.md`](LLM_EVALUATION.md), [`AGENT_ARCHITECTURE.md`](AGENT_ARCHITECTURE.md), [`AGENT_QUALITY_STANDARD.md`](AGENT_QUALITY_STANDARD.md), [`INTERPRETATION_QUALITY_STANDARD.md`](INTERPRETATION_QUALITY_STANDARD.md) |
| AI onboarding and skills | [`AGENTS.md`](AGENTS.md), [`AGENT_SKILL_LIBRARY.md`](AGENT_SKILL_LIBRARY.md) |
| Chart and product boundaries | [`CHART_ENGINE_DECISION.md`](CHART_ENGINE_DECISION.md), [`CHART_ENGINE_LICENSING.md`](CHART_ENGINE_LICENSING.md), [`CHART_TYPE_CAPABILITIES.md`](CHART_TYPE_CAPABILITIES.md), [`COMPOSITE_AND_RETURNS_PRODUCT_SPEC.md`](COMPOSITE_AND_RETURNS_PRODUCT_SPEC.md) |
| Astronomy and visual domain research | [`DOMAIN/ACCURACY_MATRIX.md`](DOMAIN/ACCURACY_MATRIX.md), [`PALM_ENGINE_RESEARCH.md`](PALM_ENGINE_RESEARCH.md) |
| API, memory and localization | [`API_RESILIENCE_MATRIX.md`](API_RESILIENCE_MATRIX.md), [`MEMORY_EVALUATION.md`](MEMORY_EVALUATION.md), [`LOCALIZATION_GLOSSARY.md`](LOCALIZATION_GLOSSARY.md) |
| Analytics and payments | [`ANALYTICS_EVENT_DICTIONARY.md`](ANALYTICS_EVENT_DICTIONARY.md), [`PAYMENTS_UX_AND_INTEGRATION.md`](PAYMENTS_UX_AND_INTEGRATION.md), [`PAYMENT_MONITORING.md`](PAYMENT_MONITORING.md) |
| PDF, backup and visual QA | [`PDF_SYSTEM.md`](PDF_SYSTEM.md), [`PDF_TEMPLATE_CATALOG.md`](PDF_TEMPLATE_CATALOG.md), [`BACKUP_RESTORE_DRILL.md`](BACKUP_RESTORE_DRILL.md), [`VISUAL_QA.md`](VISUAL_QA.md) |
| Scale and competition | [`SCALE_AND_MIGRATION.md`](SCALE_AND_MIGRATION.md), [`COMPETITOR_MATRIX.md`](COMPETITOR_MATRIX.md) |
| Legal and model provenance | [`LEGAL_REVIEW.md`](LEGAL_REVIEW.md), [`models/THIRD_PARTY_NOTICES.md`](../models/THIRD_PARTY_NOTICES.md) |

## Docker-first launch

For the full stack, use Docker Engine with Compose v2 from the repository root:

```bash
cp .env.example .env
# Fill BOT_TOKEN/ADMIN_ID and an LLM provider key when required.
make up
make ps
make selfcheck
```

Compose starts PostgreSQL + pgvector, Redis, migrations, API, Telegram bot, Celery worker/Beat and Caddy. The application image also contains the Mini App, admin, landing, astrology engine, palm assets and LLM runtime. Development ports are `8080` (HTTP) and `8443` (HTTPS). The observability contour includes Grafana, Loki, Prometheus, Alloy, cAdvisor and node-exporter; Grafana is bound to `127.0.0.1:3000` by default. See [`OBSERVABILITY.md`](OBSERVABILITY.md) and [`DEPLOYMENT.md`](DEPLOYMENT.md).

For the optional local OpenAI-compatible LLM, set `CUSTOM_LLM_BASE_URL=http://ollama:11434/v1`, `CUSTOM_LLM_MODEL` and `CUSTOM_LLM_MODEL_LITE`, then run `make up-local-llm`.

## Local development

For a manual run without Docker, use Python 3.11+ and keep real Telegram authorization checks limited to a controlled environment. Install dependencies and create `.env` once:

```bash
cd /path/to/oracleAI
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

A local development mode is available for interface inspection. It accepts `dev_user` and must never be exposed on a public address. A manual run needs a reachable PostgreSQL and a `DATABASE_URL`; the SQLite dev/test fallback no longer exists — `make test` runs the suite against the Compose PostgreSQL stack.

```bash
APP_ENV=dev DEV_MODE=1 uvicorn app.api.main:app --host 127.0.0.1 --port 8080
# http://127.0.0.1:8080/?dev_user=10001
```

Production uses `DEV_MODE=0`, a real HTTPS `WEBAPP_URL` and server validation of Telegram `initData`. The complete process is in [`DEPLOYMENT.md`](DEPLOYMENT.md).

## Working cycle

| Stage | Minimum action | Verification artifact |
|---|---|---|
| Product change | Reconcile the scenario with PRODUCT and DESIGN_SYSTEM. | Updated copy, states and analytics event when needed. |
| Data change | Update `schema.py` and migrations for existing databases. | New migration run and regression test. |
| API change | Update the router and client call. | API.md review and negative-path tests. |
| UI change | Use tokens, CSS cascade and delegated events. | Mobile viewport and `prefers-reduced-motion` check. |
| Before release | Run syntax, tests, selfcheck and diff review. | Changelog entry and green CI/local QA. |

## Operating rules

Current behavior must be established from code, tests and configuration first. A document change that alters a contract must update the corresponding canonical page in the same pull request. A local or synthetic check must name its environment and limitation; it cannot close a staging, production, legal, payment or provider gate.

Before opening a pull request, validate relative links, stale path references, documented commands and generated artifacts. Keep raw screenshots, logs, local databases, generated reports and secrets outside the tracked source tree unless a reproducible fixture or legal notice requires them.

## References

[1]: [Repository README](../README.md) — repository-level quick start and boundary.
[2]: [Current status](RELEASE/CURRENT_STATUS.md) — current release verdict.
[3]: [Current tasks](RELEASE/TASKS.md) — current backlog.
[4]: [Documentation link checker](../scripts/check_documentation_links.py) — repository-relative Markdown checker.
