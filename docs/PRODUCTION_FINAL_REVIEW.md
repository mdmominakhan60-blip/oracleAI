# OracleAI — Production Final Review

**Дата:** 2026-08-27  
**Commit:** `68e3945`  
**Ветка:** `master`  
**Автор:** **Manus AI**  
**Уровень доказательств:** **verified locally**; staging и production claims не заявляются.

## Итоговый verdict

# BLOCKED

Локальная реализация прошла полный доступный набор unit, integration, security, resilience, migration, performance, backup/restore и synthetic load checks. В этом цикле исправлены три автономно устранимых класса дефектов: незапротоколированные CRM tag mutations, недостаточно строгий production configuration gate и PII/payment identifiers в operational logs.

Публичный production launch не может быть объявлен пройденным. Не хватает реальных signed Telegram device checks, provider payment certification, live LLM SLO evidence, production encrypted backup/restore/rollback, Docker/HTTPS game day, legal/privacy approvals и commercial chart-engine licensing. Эти блокеры требуют внешнего доступа, владельцев и подтверждаемого evidence; подменять их локальной симуляцией нельзя.[1]

## Architecture

Проверенный runtime сохраняет существующую архитектуру: FastAPI API и static delivery, aiogram bot, shared services/repositories, deterministic chart/card calculation, agent runtime, SQLite/WAL fallback, PostgreSQL/Alembic production path, Redis/Celery background execution, Caddy TLS и encrypted backup profile. Транспортные роутеры получают identity через server-side dependency; product writes идут через services/repositories; чувствительные пути используют owner, age, consent, entitlement и rate-limit guards.[2]

Startup lifecycle выполняет fail-closed production validation до обслуживания запросов, открывает DB после schema/bootstrap/migration sequence и закрывает DB в lifespan shutdown. Новая проверка требует production `APP_ENV`, Telegram/administrator configuration, PostgreSQL `DATABASE_URL`, непустой и не шаблонный `POSTGRES_PASSWORD`, `RELEASE_ID`, а также `REDIS_URL` при активном Celery.[3]

## Security

Authentication parser проверяет подписанный Telegram `initData`, duplicate keys, payload/field bounds, HMAC comparison, auth freshness и future timestamps. Existing tests cover missing/malformed/tampered/expired inputs and development bypass boundaries. Real signed initData from Telegram iOS, Android and Desktop/WebView is not available locally and remains P0-001 external evidence.[4]

Authorization and privacy tests cover owner-scoped resources, age confirmation, memory opt-in/off, account deletion, admin role ladder, role escalation, payment authority, webhook signature/idempotency, safe errors, upload limits and history projections without raw private content. Admin CRM tag add/remove now creates `tag.add`/`tag.delete` audit records with normalized tag payload, and regression coverage verifies both actions.

Logging hardening removes direct interpolation of Telegram IDs, invoice payloads, charge IDs and raw provider/Telegram exception messages from the inspected paths. The JSONL formatter still redacts obvious secrets, email addresses and numeric IDs as defense in depth; the stronger primary invariant is that sensitive values are not emitted in the first place.[5]

Dependency scan result: `pip-audit -r requirements.txt` reported **No known vulnerabilities found**. Secret scan of tracked source found no exposed key-shaped values; history matches were documentation/example references, not printed credentials. This does not replace a hosted secret scanner or legal/license review.

## Reliability

Atomic transaction wrappers, idempotency claims, owner locks, durable job status, broadcast target claiming, provider retries, bounded tool output, workflow timeout/cost/tool budgets, offline fallbacks and safe HTTP error mapping were exercised through existing tests and the new regression suite.[6]

The full local load harness completed without errors for 2,000 `/start` operations, 2,749 available forecast candidates, 1,000 question calls and 100 concurrent payment operations. Payment simulation produced exactly 100 new entitlements for 100 payment operations. These are synthetic/offline-provider results and do not prove multi-process PostgreSQL or real provider behavior.

A production game day was not executed because Docker Engine, public DNS/TLS, external providers and an approved rollback target are unavailable in the sandbox. SIGTERM, Celery restart, stale lease, DB contention, provider outage and partial deployment therefore remain staging evidence requirements.

## Data

PostgreSQL schema/migrations, report append-only history, owner-scoped reads, deletion/anonymization and transaction behavior are covered locally. The disposable `oracle_test` rebuild reached Alembic head, and the PostgreSQL backup/restore contract passed the static P0-004 gate; production restore timing, storage and owner-isolation evidence remain external.

The local drill is not a production backup pass. Encrypted PostgreSQL dump creation, off-site retention, host-key custody, restore timing, RPO/RTO and code/schema rollback require P0-004 in a production-like environment.[7]

## Performance

The local directional benchmark recorded the following values:

| Operation | Runs | p50 | p95 | Evidence interpretation |
|---|---:|---:|---:|---|
| Chart compute | 5 | 2.71 ms | 1,289.11 ms | Directional only; sample below 20. |
| Tarot draw | 20 | 0.04 ms | 0.08 ms | Local deterministic path. |
| Memory recall | 5 | 0.00 ms | 82.14 ms | Directional only; sample below 20. |
| PDF/HTML generation | 20 | 6.72 ms | 174.35 ms | Local offline generation. |
| Palm-line segmentation | 3 | 12,949.08 ms | 13,803.42 ms | CPU directional baseline; not a mobile SLO pass. |
| Synthetic question load | 1,000 | 351.5 ms | 657.0 ms | Fast stub under local semaphore, not live LLM. |

The latest repository evidence still records live LLM p95 above the working 15-second target. Because no approved staging provider configuration is available in this run, the latency gate remains **PARTIAL/BLOCKED**, not passed.[8]

## Observability

Request correlation IDs, response latency, status, release ID, provider/fallback events, safe exception categories and JSONL formatting are implemented and locally asserted. `scripts.ops_alerts` covers 5xx, webhook failure, LLM fallback, backup freshness and scheduler state according to the operational documentation.[9]

Sentry is configured with `send_default_pii=False`, but real DSN routing, alert thresholds, on-call delivery, dashboard sampling and retention controls were not tested against a deployed environment. These remain operational evidence items rather than code assumptions.

## Production

The repository contains a pinned application base image, non-root `oracle` application user, healthchecks, restart policies, Caddy security headers, PostgreSQL/Redis dependencies, one-shot migration service and backup profile. Static checks passed, but Docker is not installed in the sandbox; Compose validation, image build, container health, HTTPS certificate issuance, SIGTERM behavior and live migration ordering were not run.

The production configuration gate is now stricter in code and tests, but real secrets, real domain, staging Telegram bot, provider credentials and off-site storage must still be supplied by the responsible owners. Public Privacy/Terms pages intentionally retain operator/contact/jurisdiction/retention/payment placeholders pending legal and product decisions.[10]

## Verification record

| Check | Result |
|---|---|
| `pytest -q` | **PASS** |
| Targeted admin/security/release regressions | **PASS** |
| `python3 -m compileall -q app scripts tests` | **PASS** |
| `ruff check app scripts tests` | **PASS** |
| JavaScript `node --check` | **PASS** |
| `python3 -m scripts.selfcheck` | **PASS**, expected live/config skips |
| `python3 -m scripts.release_gate` | **PASS** |
| `pip-audit -r requirements.txt` | **PASS**, no known vulnerabilities |
| Product benchmark | **PASS**, local directional |
| SQLite backup/restore drill | **PASS**, disposable local only |
| Full synthetic load harness | **PASS**, offline/stub provider only |
| Docker Compose build/game day | **NOT RUN**, Docker unavailable |
| Real Telegram device/signature matrix | **NOT RUN**, external gate |
| Payment sandbox/settlement/refund | **NOT RUN**, external gate |
| Production encrypted backup/rollback | **NOT RUN**, external gate |

## Remaining blockers

| Exact blocker | Why it cannot be solved autonomously | Required external action | Affected subsystem | Risk |
|---|---|---|---|---|
| Real Telegram signed-initData/device evidence | No real Telegram staging session or iOS/Android/Desktop WebView is available in this sandbox. | Security owner runs P0-001 with disposable accounts, HTTPS and redacted request/side-effect matrix. | Auth, ownership, Mini App | Unauthorized access or device-specific dead end. |
| Payment provider certification | No provider sandbox credentials or settlement/refund/chargeback data are available. | Payments owner runs P0-002 and reconciles provider rows to internal ledger/entitlements. | Billing, webhooks, entitlements | Duplicate grant, refund mismatch or untracked funds. |
| Live LLM quality and p95 | Existing evidence records p95 above 15 seconds; no approved staging provider run is available here. | AI quality owner runs P0-003 with exact model route, safety rubric, cost cap and p95 evidence. | Chat, reports, palm, safety | Slow, costly or insufficiently verified AI response. |
| Production backup/restore/rollback | PostgreSQL, off-site storage, host key custody, RPO/RTO and rollback target are external. | SRE runs P0-004 with encrypted artifact, checksum, isolated restore and rollback timing. | Data and recovery | Irrecoverable loss or privacy regression. |
| Docker/HTTPS game day | Docker Engine and public DNS/TLS are unavailable locally. | Operator validates Compose build, healthchecks, Caddy, shutdown and failure injection in staging. | Infrastructure | Unverified deployment or exposure failure. |
| Legal/privacy and chart licensing | Operator identity, contacts, jurisdiction, retention/refund wording and commercial Swiss Ephemeris/Kerykeion rights require owner/legal decisions. | Product/legal owner completes public documents and licensing sign-off. | Public launch and chart engine | Regulatory, contractual and commercial exposure. |

## Final decision

**BLOCKED.** The codebase is locally verified for the checks listed above, but the release cannot be promoted to public production until all applicable P0 external evidence is signed and the live LLM latency gate is resolved or the launch scope/SLO is explicitly changed by the product owner. This review does not use “mostly ready”, “probably safe” or “production-ready” as substitutes for evidence.

## References

[1]: [P0_PRODUCTION_EXECUTION_PLAN.md](RELEASE/P0_PRODUCTION_EXECUTION_PLAN.md) — external gate procedures and evidence rules.
[2]: [ARCHITECTURE.md](ARCHITECTURE.md) — component boundaries and request/data flows.  
[3]: [DEPLOYMENT.md](DEPLOYMENT.md) — production topology and configuration.  
[4]: [SECURITY.md](SECURITY.md) — authentication, privacy, age, memory and payments.  
[5]: [PRODUCTION_GAUNTLET.md](PRODUCTION_GAUNTLET.md) — logging findings and phase matrix.  
[6]: [API_RESILIENCE_MATRIX.md](API_RESILIENCE_MATRIX.md) — negative-path and resilience contracts.  
[7]: [BACKUP_RESTORE_DRILL.md](BACKUP_RESTORE_DRILL.md) — disposable backup/restore procedure.  
[9]: [DEPLOYMENT.md](DEPLOYMENT.md) — observability and incident procedures.  
[10]: [LEGAL_REVIEW.md](LEGAL_REVIEW.md) — unresolved owner/legal launch facts.
