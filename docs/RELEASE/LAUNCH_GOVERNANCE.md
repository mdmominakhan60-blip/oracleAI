# OracleAI Launch Governance

## Назначение

Этот документ является рабочим контрактом для production-релиза OracleAI. Он не заменяет юридическое заключение и не разрешает публичный запуск автоматически. Каждый launch gate должен иметь evidence, владельца и дату проверки.

## Решение Gate 0

До получения доказательств масштабируемости выбран безопасный default: **контролируемая закрытая beta**. Доступ расширяется волнами по invite-list или ограниченному acquisition channel; palm scan, платные функции и lifecycle notifications включаются feature flags. Переход к широкому public launch возможен только после двух последовательных beta waves без критических инцидентов и с прохождением P0/P1 gates.

Решение о немедленной миграции от SQLite к PostgreSQL, Redis и очереди принимается по baseline load test. Для beta single-writer SQLite допустим только при измеренном capacity ceiling, ежедневном encrypted off-site backup и подтверждённом restore drill. Резкий рекламный трафик до этой проверки запрещён.

## Launch brief v1

| Поле | Утверждённое значение / действие |
|---|---|
| Аудитория | Telegram users (без возрастной границы), первая волна: RU/EN; country scope проходит отдельный legal review. |
| Позиционирование | Бережная self-reflection через четыре проводника; не медицинская, юридическая, финансовая или психологическая помощь. |
| First value | Первый завершённый ритуал, первый безопасный ответ или quality result Миры. |
| Palm promise | Только видимые признаки на снимке, с quality/limitations; исходное фото не хранится. |
| Release route | Invite-only controlled beta → две beta waves → go/no-go public launch. |
| LLM budget | Утвердить до beta после baseline: cost per successful answer и monthly/user cap. |
| Support | Назначить owner и SLA до первой invite wave; обязательны privacy, deletion, safety и payment escalation paths. |
| Payments | Только Paddle sandbox до отдельного sign-off; реальные charges/refunds не выполнять без подтверждения владельца. |
| Analytics | Только privacy-safe event taxonomy; тексты чатов, дневников, memory и palm analysis не отправлять в events. |
| Release owner | Назначить одного accountable owner перед staging rehearsal. |

## P0 gates — до любого внешнего трафика

| Gate | Evidence | Owner | Status |
|---|---|---|---|
| Production config | `APP_ENV=production`, `DEV_MODE=0`, HTTPS `WEBAPP_URL`, real Telegram token and admin access outside Git. | Operations | OPEN |
| Staging isolation | Separate bot token, DB, LLM/payment credentials and domain; no production user data. | Operations | OPEN |
| LLM safety | Versioned eval set, red-team suite, strict schema, provider fallback/circuit breaker, zero critical safety failures. | AI/Safety | OPEN |
| Palm quality | Approved image benchmark, valid enum/schema rate ≥99%, p95 vision latency budget and `needs_photo` fallback. | AI/Product | OPEN |
| Device UX | iOS, Android, Desktop Telegram matrix including first launch, permissions, RU/EN, offline and slow provider. | Product/QA | OPEN |
| Privacy/legal | Privacy Policy, Terms, deletion, retention and cross-border review for first-wave countries. | Product/Legal | EXTERNAL |
| Backup/restore | Encrypted off-site copy, checksum, isolated restore drill and post-restore selfcheck. Disposable plaintext/encrypted restore now passes locally; off-site and scheduled production drill remain open. | Operations | OPEN |
| Incident response | Severity matrix, contact tree, on-call owner, provider/payment/data incident tabletop. | Operations | OPEN |
| Monitoring | Health, HTTP, LLM/provider, scheduler and business funnel dashboards plus test alerts. Local scheduler lease/status and alert parsing are now verified; production routing remains open. | Operations | OPEN |

## P1 gates — до public launch

| Gate | Required evidence |
|---|---|
| Capacity | Load test passes approved traffic profile or migration to PostgreSQL/Redis/queue is completed. |
| Payments | Paddle sandbox covers transaction creation, signed webhook, idempotent retry, entitlement, cancel, fail and refund reconciliation. |
| Support | FAQ/help route, response templates, deletion/privacy/payment/safety escalation and SLA report. |
| Analytics | Funnel from landing to first value and D1/D7 cohorts works without personal-content leakage. |
| Accessibility | Touch, keyboard, screen reader, contrast, reduced motion and Telegram safe-area review completed. |
| Beta evidence | Two invite waves meet SLO, trust, support and cost thresholds without critical incidents. |
| Rollout | Versioned release, backup confirmation, canary, feature flags, rollback command and 72-hour monitoring rota. |

## Operational SLO placeholders

Exact numbers must be set after production-like baseline testing. Until then the following are required as metrics, not as unverified promises:

| Dimension | Metric | Launch action |
|---|---|---|
| Availability | `/api/health`, API 5xx, bot webhook failures | Freeze rollout on sustained breach; follow incident runbook. |
| Responsiveness | p50/p95/p99 API and vision latency | Enable queue/status UX or reduce traffic when budget is exceeded. |
| LLM reliability | Provider success, timeout, invalid JSON, fallback and circuit-open rates | Switch provider/disable palm feature if threshold is breached. |
| Data integrity | SQLite lock/retry, failed migrations, backup age and restore result | Stop writes or rollback before corruption spreads. |
| Safety | Critical red-team failures, sanitized claims, crisis routing errors | Immediate feature flag off and safety hotfix. |
| Trust | Deletion SLA, privacy contacts, support backlog | Pause acquisition if support cannot meet SLA. |
| Economics | Cost per successful outcome, monthly/user spend, payment/refund rate | Tighten quota or change routing before scaling. |

## Required artifacts before sign-off

The release owner must attach the following evidence to the release record: CI result, migration test, device QA matrix, LLM evaluation report, safety red-team report, backup checksum, restore log, load-test result, payment sandbox log, security/privacy sign-off, dashboard links, rollback result and support rota. A green unit test suite alone is insufficient.

## Go / no-go rule

The release is **NO-GO** if any P0 item is OPEN, if legal/privacy review is not complete for the intended country scope, if real provider vision success and latency are unproven, if restore has not been rehearsed, or if the team cannot respond to safety, data, payment and provider incidents. A beta wave is **GO** only when its traffic cap, feature flags, owner and stop conditions are recorded before opening access.

## References

[1]: [Product source of truth](../PRODUCT.md)
[2]: [Security checklist](../SECURITY.md)
[3]: [Deployment runbook](../DEPLOYMENT.md)
[4]: [Production readiness plan](PRODUCTION_READINESS.md)


## Evidence update — 2026-08-25

The current cycle added the following local evidence without closing the external launch gates: a sanitized production-like `release_gate.py --production` run passed with synthetic staging values; an isolated API health smoke returned `{"ok":true}` against a disposable database; plaintext and AES-256 encrypted SQLite backup/restore fixtures passed with checksum and integrity checks; and the synthetic operational alert dry-run detected HTTP 5xx, webhook failure, stale backup and scheduler error signals without user content. `docs/INCIDENT_RESPONSE_RUNBOOK.md` now defines severity, containment and tabletop procedures, but named owners, real alert routing and external acknowledgement remain open.

The live LLM probe was attempted through the configured sandbox provider and failed because the provider returned empty responses after retries. This is evidence that P0 live-provider readiness is **not closed**; no successful live-quality claim is made. The declared project requirements audit (`pip-audit -r requirements-dev.txt`) reports no known vulnerabilities, while the ambient sandbox environment has unrelated installed-package findings; production image verification still requires a clean Docker/staging run.

## Chart-engine migration gate — 2026-08-25

The natal visual migration is technically implemented in Mode P: Kerykeion 5.12.9 → transient in-memory SVG → resvg_py 0.5.0 → PNG/WebP, with authenticated owner-scoped binary delivery and no raw SVG in client/share/PDF boundaries. Exact natal output, unknown-time recovery, API ETag behavior, PDF print image, visual artifacts and local regression gates pass. This does **not** close public-launch governance: Kerykeion AGPL-3.0/Swiss Ephemeris licensing requires legal owner sign-off, and Docker/target-image verification remains open. The public release remains **NO-GO** while any P0 gate is open.
