# OracleAI — Production Gauntlet Journal

**Дата проверки:** 2026-08-27  
**Репозиторий:** [`astartv1ai-del/oracleAI`](https://github.com/astartv1ai-del/oracleAI)  
**Ветка:** `master`  
**Проверенный commit:** `68e3945`  
**Режим доказательств:** локальный sandbox; production claims запрещены.

## Правило verdict

> Локально проверенное поведение не считается staging или production evidence. Неподтверждённые внешние gates остаются `BLOCKED` или `PARTIAL`, даже если соответствующий unit/integration test зелёный.

Итог этого цикла: **BLOCKED**. Автономно устранимые локальные дефекты исправлены и покрыты regression tests. Публичный запуск заблокирован внешними проверками, для которых нужны staging, реальные Telegram signed `initData`, provider sandbox credentials, production deployment, off-site backup custody и owner/legal sign-off.

## Методика и область проверки

Проверка выполнена по принципу **AUDIT → DEFINE INVARIANTS → IMPLEMENT → TEST → BREAK → OBSERVE → FIX → RETEST**. Существующая архитектура не переписывалась: сохранялись FastAPI/aiogram, repository/service boundaries, SQLite/WAL fallback, PostgreSQL path, Celery/Redis, deterministic calculation layer, provider fallback, backup tooling и текущие API contracts.[1]

В ходе цикла были прочитаны backend/security/deployment документы, API entrypoints и shared dependencies, DB lifecycle, payment webhooks, background delivery, upload boundary, Docker/Caddy configuration и existing test evidence. Baseline до патча: `pytest -q` — PASS; compile, Ruff, JavaScript syntax, selfcheck, release gate и `pip-audit` — PASS. Docker runtime в sandbox отсутствует, поэтому Compose build/up, live Postgres/Redis/Celery, HTTPS и device WebView не запускались.

## Найденные проблемы и исправления

| ID | Подсистема | Риск | Severity | Evidence | Статус |
|---|---|---|---|---|---|
| F-001 | Admin CRM audit | Добавление и удаление CRM-тегов меняли состояние без записи в `admin_audit`; задним числом нельзя было объяснить административное действие. | Medium | `app/api/routers/admin.py`, `tests/test_api.py` | **Fixed locally** |
| F-002 | Production configuration | Runtime/release gate не проверяли PostgreSQL URL, шаблонный `POSTGRES_PASSWORD`, обязательный `RELEASE_ID` и Redis при включённом Celery; Compose имел dev-friendly defaults. | High | `app/api/main.py`, `scripts/release_gate.py`, `tests/test_release_gate.py` | **Fixed locally** |
| F-003 | Privacy / logging | Несколько operational log calls интерполировали Telegram ID, invoice payload, charge ID или сырые Telegram exception messages. | High | `app/api/deps.py`, `app/bot/shop.py`, `app/services/{billing,broadcast,chat,scheduler,telegram}.py` | **Fixed locally** |
| F-004 | Production evidence | Реальные Telegram device/signature, provider settlement/refund, encrypted off-site backup, production rollback, legal/privacy и licensing не доступны в локальном sandbox. | Critical | `docs/RELEASE/P0_PRODUCTION_EXECUTION_PLAN.md`, `docs/LEGAL_REVIEW.md` | **External gate** |
| F-005 | Live LLM SLO | Последний зафиксированный live synthetic run имеет p95 выше рабочей цели 15 секунд; live rerun без staging provider configuration не может быть достоверно выполнен. | High | dated performance baseline reports (removed from tree) | **Partial / blocker** |
| F-006 | Docker/game day | Docker Engine отсутствует в sandbox, поэтому container build, Compose healthchecks, SIGTERM, Postgres migration and production game day не получили runtime evidence. | High | command result: `docker: command not found` | **External environment gate** |

### F-001 — Admin CRM tags were not auditable

**Evidence and reproduction.** `POST /api/admin/users/{tg_id}/tags` и `DELETE /api/admin/users/{tg_id}/tags/{tag}` вызывали repository mutation, но не `admin_repo.audit`, в отличие от соседних note mutations. Повторяемый сценарий: открыть admin context в dev test, выполнить add/remove tag, затем запросить `/api/admin/audit`; соответствующих `tag.add` и `tag.delete` rows не было.

**Desired invariant.** Каждое чувствительное admin mutation должно оставлять server-owned audit record с действием, target и минимальным безопасным payload.

**Fix and verification.** Добавлены события `tag.add` и `tag.delete`; tag сохраняется в audit только после нормализации lowercase, без пользовательского текста. Regression test проверяет оба endpoint-а, нормализацию и JSON payload. Rollback — revert только двух audit calls; database state и API contract не меняются.

### F-002 — Production database/configuration must fail closed

**Evidence and reproduction.** Runtime startup validation проверяла Telegram token/admin/webapp, но не требовала production `DATABASE_URL`, сильный `POSTGRES_PASSWORD`, release identity или Redis URL при включённом Celery. Production release gate имел тот же gap. При пропущенных переменных Compose мог использовать local defaults, что недопустимо как production evidence.

**Desired invariant.** До обслуживания запросов production process должен остановиться, если окружение не идентифицирует production, не указывает PostgreSQL, использует шаблонный пароль, не имеет release identity или не настроило обязательный broker.

**Fix and verification.** `_validate_production_config()` и `scripts.release_gate.check_production_env()` синхронно проверяют новые поля. Добавлены tests для safe configuration и rejection of template password/SQLite URL. Dev/test bypass сохранён только для `APP_ENV=dev|test` или `DEV_MODE`.

**Rollback/evidence.** Revert runtime/gate patch only after a replacement platform-level secret validation is deployed; otherwise rollback reopens a high-risk startup gap. No production database was touched locally.

### F-003 — Operational logs must not become a private data store

**Evidence and reproduction.** Static inspection found log messages containing Telegram IDs, payment invoice payload, charge ID and raw exception text in admin authentication, duplicate payment, broadcast, crisis, scheduler and Telegram client paths. Formatter redaction reduced exposure for many numeric IDs, but relying on message redaction is weaker than not emitting the data.

**Desired invariant.** Logs retain event category, operation, release/request correlation and error type, but never emit raw Telegram IDs, payment payloads, charge IDs, message text, diary/memory content or provider exception payloads.

**Fix and verification.** Removed sensitive interpolations, replaced raw exception strings in these paths with exception type, and kept broadcast queue error state bounded to exception type. Added a source-level regression guard and retained formatter redaction tests. Rollback is a code-only revert; no schema change is involved.

## Phase evidence matrix

The matrix below records what was actually exercised. `Local pass` means reproducible in this sandbox; `Partial` means some local evidence exists but the acceptance criteria require staging/production; `External gate` means the missing evidence cannot be manufactured from the repository.

| Phase | Scope | Status | Evidence / limitation |
|---:|---|---|---|
| 0 | Reconnaissance | **Local pass** | Repository/docs/code inventory; baseline commands completed. |
| 1 | System invariants | **Local pass** | Ownership, consent, payment, history and recovery contracts covered by tests/docs. |
| 2 | Telegram authentication | **Partial** | Parser edge cases and dev bypass tests pass; real signed device matrix is external. |
| 3 | Authorization | **Local pass / Partial** | Admin, ownership and age tests pass; full route matrix with real auth remains staging work. |
| 4 | Privacy | **Local pass / Partial** | Source review, formatter, history/export assertions and logging patch pass; deployed telemetry/Sentry review external. |
| 5 | Age/consent | **Local pass** | Direct API age gate, memory-off, delete and re-enable contracts are tested. |
| 6 | Database | **Local pass / Partial** | SQLite migration/transaction/index tests pass; live PostgreSQL and lock behavior external. |
| 7 | Atomicity | **Local pass** | Billing, entitlement, report/history and worker transaction tests pass; process-kill staging drill remains. |
| 8 | Idempotency | **Local pass** | Duplicate payment, chat, promo, delivery and report paths covered by tests. |
| 9 | Payment/webhook reliability | **Partial** | Signature/order binding/idempotency tests pass; sandbox settlement/refund/chargeback unavailable. |
| 10 | Concurrency | **Local pass / Partial** | Full local simulator exercised 2,000 starts, 4,000-target forecast workload, 1,000 questions and 100 payments; multi-process Postgres remains external. |
| 11 | Rate limiting | **Local pass** | Read/write/LLM/admin limits and Retry-After tests pass; Redis failover in live topology external. |
| 12 | Timeout/cancellation | **Local pass / Partial** | LLM, Telegram, payment and tool timeout paths are bounded in code/tests; live provider cancellation requires staging. |
| 13 | Background workers | **Local pass / Partial** | Durable task/broadcast/scheduler tests pass; restart/lease behavior in live Celery topology external. |
| 14 | Error handling | **Local pass** | Safe HTTP errors, exception classification and no stack traces to clients tested. |
| 15 | Resilience/degradation | **Local pass / Partial** | Offline LLM and bounded fallbacks pass; provider outage in deployed stack external. |
| 16 | Observability | **Local pass / Partial** | Correlation IDs, whitelisted fields and latency/error logs pass; alert delivery/dashboard external. |
| 17 | Logging attack | **Local pass** | Redaction tests plus new logger-call regression pass; production log sink review external. |
| 18 | Sentry/monitoring | **Partial** | Sentry initialization and privacy settings inspected; real DSN alert routing not exercised. |
| 19 | Performance | **Local directional pass** | Product benchmark: Tarot p50 0.04 ms, PDF p50 6.72 ms, chart p50 2.71 ms; small-n p95 is explicitly directional. |
| 20 | Load | **Local synthetic pass** | Full harness: 2,000 `/start` zero errors, 2,749 available forecasts zero errors, 1,000 questions p95 657 ms, 100 payments zero errors and exactly 100 grants. |
| 21 | Database performance | **Local directional pass** | Existing query/index audits and benchmark pass; real production query plans/traffic external. |
| 22 | Resource exhaustion | **Local pass / Partial** | Pydantic bounds, body limits, pixel limits and pagination tests pass; host disk/memory pressure external. |
| 23 | Upload security | **Local pass / Partial** | Palm MIME/signature/size/pixel/EXIF/raw-retention tests pass; object-storage lifecycle external. |
| 24 | Web security headers | **Local pass / Partial** | FastAPI/Caddy policy inspected and header tests pass; actual HTTPS/browser behavior external. |
| 25 | Secret hygiene | **Local pass** | Tracked-source scan found no exposed key-shaped values; history hits were documentation/examples and were not printed. |
| 26 | Dependency/supply chain | **Local pass** | `pip-audit -r requirements.txt`: no known vulnerabilities; license/provenance review remains owner/legal gate. |
| 27 | Docker/container | **Partial** | Dockerfile is pinned and app image uses non-root `oracle`; Docker build/runtime could not run because Docker is absent. |
| 28 | Production configuration | **Local pass for code gate** | New fail-closed checks and release tests pass; real secrets/host values external. |
| 29 | Startup | **Local pass / Partial** | Local import/selfcheck and migrations pass; production-like Compose startup external. |
| 30 | Shutdown | **Partial** | Code uses lifespan close and task drain patterns; SIGTERM/WAL/Celery shutdown needs disposable Compose. |
| 31 | Migrations | **Local pass / Partial** | SQLite idempotency and migration tests pass; Alembic/Postgres forward/rollback drill external. |
| 32 | Backup | **Local pass / Partial** | Disposable SQLite backup/restore: integrity `ok`, owner isolation `true`; encrypted off-site PostgreSQL backup external. |
| 33 | Disaster recovery | **Partial** | Runbooks and failure modes documented; DB corruption/disk-full/provider outage game day external. |
| 34 | Rollback | **External gate** | Compatibility/runbook documented; no disposable production-like image/schema rollback available. |
| 35 | API contracts | **Local pass** | Pydantic validation, errors, pagination and owner-scoped response tests pass. |
| 36 | Admin security | **Local pass / Partial** | Role escalation, direct requests, audit and identifier-scope tests pass; real stale-session device tests external. |
| 37 | Data deletion | **Local pass / Partial** | Idempotent anonymization and memory/push/age scrubbing tests pass; legal retention sign-off external. |
| 38 | Retention | **Partial** | Retention policy is documented; actual scheduled purge and approved legal windows require operator/legal evidence. |
| 39 | Adversarial security | **Local pass / Partial** | IDOR, tampering, replay, malformed/oversized payload and upload abuse tests pass; external penetration test not run. |
| 40 | Reliability critic | **Partial** | Fresh checklist review identified production config/logging gaps and they were fixed; independent reviewer rerun remains external. |
| 41 | Security critic | **Partial** | Hostile-client trust-boundary pass performed locally; independent security sign-off remains external. |
| 42 | Operations critic | **Partial** | Restart/provider/DB-lock recovery paths documented; operator rehearsal in staging not run. |
| 43 | Performance critic | **Partial** | Measured bottleneck remains live LLM p95 and palm CPU; provider/model tuning needs staging evidence. |
| 44 | Production game day | **External gate** | Requires Docker/Compose, staging services, provider outage injection and rollback target. |
| 45 | Final checklist | **BLOCKED** | Local gates green, but P0 external evidence is incomplete. |

## Reproducible local commands

| Check | Command | Result |
|---|---|---|
| Full tests | `pytest -q` | **PASS** |
| Compile | `python3 -m compileall -q app scripts tests` | **PASS** |
| Ruff | `ruff check app scripts tests` | **PASS** |
| JavaScript | `find miniapp/js admin -type f -name '*.js' -print0 \| xargs -0 -n1 node --check` | **PASS** |
| Selfcheck | `python3 -m scripts.selfcheck` | **PASS**, expected live/config skips |
| Release gate | `python3 -m scripts.release_gate` | **PASS** |
| Dependency audit | `pip-audit -r requirements.txt` | **PASS**, no known vulnerabilities |
| Product benchmark | `python3 scripts/benchmark_product_performance.py` | **PASS**, directional |
| Backup/restore infrastructure | `python3 scripts/check_p004_infrastructure.py && bash -n infra/backup-postgres.sh infra/restore-postgres.sh` | **PASS**, static PostgreSQL contract; production restore drill remains external |
| Full load harness | `DATABASE_URL=... python3 scripts/seed_load.py --count 5000` plus `DATABASE_URL=... python3 load/simulate.py --full` | **External/disposable PostgreSQL evidence required; do not use production |
| Docker validation | `docker compose ... config/build/up` | **NOT RUN**, Docker absent |

## External blockers

| Blocker | Why it cannot be solved autonomously here | Required action | Affected subsystem | Risk |
|---|---|---|---|---|
| Real Telegram signature/device evidence | Sandbox has no real Telegram test session and cannot certify iOS/Android/Desktop WebView behavior. | Security owner runs P0-001 with staging bot, HTTPS and disposable accounts. | Auth, ownership, Mini App | Unauthorized access or device dead end. |
| Payment certification | Provider sandbox keys, settlement, refund, chargeback and reconciliation data are not available. | Payments owner runs P0-002 and preserves redacted ledger/reconciliation evidence. | Billing, entitlement, webhooks | Duplicate grant, incorrect refund or untracked money. |
| Live LLM quality/SLO | No approved staging provider configuration; repository records p95 above 15 s. | AI quality owner reruns P0-003 with exact model route, cost cap and approved rubric. | Chat, reports, palm, safety | Slow/expensive or unsafe user-visible responses. |
| Production backup/restore/rollback | Off-site storage, host key custody, PostgreSQL and approved rollback target are external. | SRE runs P0-004, records checksum/RPO/RTO and rollback timing. | Data/recovery | Irrecoverable loss or privacy regression. |
| Docker/HTTPS game day | Docker Engine and public DNS/TLS are unavailable in this sandbox. | Operator validates Compose build, healthchecks, SIGTERM, Caddy and failure injection in staging. | Infrastructure | Unverified deployment failure or unsafe exposure. |
| Legal/privacy/licensing sign-off | Operator identity, contacts, jurisdiction, retention, refund wording and commercial Swiss Ephemeris/Kerykeion rights require owner/legal decisions. | Product/legal owner fills public pages and records approvals. | Public launch, data policy, chart engine | Non-compliant public processing or licensing exposure. |

## References

[1]: [ARCHITECTURE.md](ARCHITECTURE.md) — architecture, trust boundaries and lifecycle.  
[2]: [SECURITY.md](SECURITY.md) — privacy, age, memory, payments and logging policy.  
[3]: [DEPLOYMENT.md](DEPLOYMENT.md) — production topology, deployment, backup and rollback.  
[4]: [P0_PRODUCTION_EXECUTION_PLAN.md](RELEASE/P0_PRODUCTION_EXECUTION_PLAN.md) — signed external gate procedures.
[5]: [TASKS.md](RELEASE/TASKS.md) — current backlog and P0 status.
[6]: [BACKUP_RESTORE_DRILL.md](BACKUP_RESTORE_DRILL.md) — disposable restore evidence.  
