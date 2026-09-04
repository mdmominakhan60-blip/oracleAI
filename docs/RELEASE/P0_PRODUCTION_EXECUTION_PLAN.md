# P0 Production Execution Plan

**Версия:** 1.0  
**Дата:** 2026-08-27  
**Назначение:** закрыть четыре release-blocking внешних gate перед любым публичным трафиком OracleAI.

## Правило выпуска

Локальные unit, integration и synthetic checks подтверждают свойства кода, но не заменяют staging с реальными Telegram signatures, sandbox settlement, live provider quality или production-like restore. Каждый P0 считается закрытым только после того, как выполнены процедура, acceptance criteria, redacted evidence и подпись владельца. До этого статус остаётся `External gate` или `Partial`, даже если соответствующий локальный тест зелёный.

План предполагает сначала **controlled staging/beta**, затем отдельное решение о public launch. Production secrets, real Telegram bot token, реальные платежи и настоящие пользовательские данные запрещено использовать в локальной разработке или в sandbox QA.

## Владельцы и зависимости

| Роль | Ответственность | Заместитель / обязательный reviewer |
|---|---|---|
| Release owner | Freeze, go/no-go, commit/tag, окно релиза и откат | Product owner |
| Security owner | Telegram auth, device matrix, log/privacy review, incident severity | Engineering lead |
| Payments owner | Provider sandbox, webhook, refund и reconciliation | Finance/support owner |
| AI quality owner | Live synthetic set, red-team, latency/SLO и provider routing | Product/safety reviewer |
| SRE/operations owner | Environment, deploy, backups, restore, alerting и rollback | Engineering lead |
| Product/legal owner | Launch countries, terms/privacy/refund copy и acceptance thresholds | Release owner |

Перед любым P0-гейтом должны быть доступны: immutable candidate commit, staging environment, isolated staging database, redacted logging, test accounts, approved launch countries, named on-call contact и rollback target. P0-001 and P0-002 are sequentially independent but both must precede paid/public traffic; P0-003 must precede uncontrolled AI traffic; P0-004 must precede any irreversible migration or public data intake.

## P0-001 — Telegram signed initData и device authorization

**Владелец:** Security owner. **Предусловия:** disposable staging bot/app, HTTPS, real signed Telegram test session, staging-only database, server clock synchronization and log redaction enabled.

### Процедура

1. Deploy the candidate to staging with a staging bot token and staging Mini App URL. Record release SHA, config fingerprint without secret values and UTC test window.
2. Run the same key journey on Telegram iOS, Android and Desktop/WebView with a disposable test account: first launch, onboarding, chart read, chat, history and account deletion request. Confirm that all successful requests carry server-validated signed Telegram `initData`.
3. Replay the matrix with tampered hash, expired `auth_date`, wrong bot token, missing `user`, malformed percent-encoding, duplicated fields, mismatched user identity and a valid signature from a different staging account. Each must return the documented 401/403 response and must not create or mutate user-owned data.
4. Verify owner isolation by attempting to read/update report, Tarot, memory, diary, payment/order and deletion resources using another test account's IDs. Expected result is a safe 404/403 without existence leakage.
5. Inspect access, error and correlation logs for absence of raw `initData`, Telegram phone/name payload, birth details, question text, authorization hash and tokens. Capture device/version, route, status and correlation ID only.

### Pass/fail and evidence

| Check | Pass criterion | Evidence |
|---|---|---|
| Valid signature | All three client surfaces complete key-path smoke without dev fallback | Redacted request/result matrix with app version and SHA |
| Invalid signature matrix | Every tampered/expired/mismatched input rejected; no side effect | HTTP status table plus database side-effect query |
| Ownership | Cross-user reads and writes denied without PII leakage | Redacted API logs and test IDs |
| Privacy | No raw initData or PII in logs/URLs/Sentry breadcrumbs | Redacted log sample and grep result |
| Device behavior | iOS, Android and Desktop pass launch, return, retry and deletion | Signed device checklist/screenshots |

**Gate:** any accepted invalid request, owner-isolation failure, PII leak or device-specific dead end is a hard fail. **Rollback:** disable Mini App entry/feature flag, keep bot in maintenance response, revoke staging credentials if exposed, restore previous tagged release and rotate affected secrets. Re-run the entire matrix after the fix; do not waive a security failure for beta.

## P0-002 — Payments sandbox, entitlement, refund и reconciliation

**Владелец:** Payments owner. **Предусловия:** provider sandbox merchant/project, isolated webhook endpoint and signing secret, catalog mapped to immutable SKU/catalog version, test customer/order ledger, support refund runbook and finance reconciliation template. No real charge or refund is permitted without explicit owner confirmation.

### Процедура

1. Create a server-side sandbox purchase for each enabled paid product. Confirm client cannot choose price, currency, entitlement, recipient or order status; server derives these from the catalog and authenticated user.
2. Deliver the same signed webhook zero, one, two and many times, including reordered delivery. Verify raw-body signature validation, idempotent event/order ledger behavior and stable final entitlement.
3. Test success, pending, failed, cancelled, expired, provider timeout and malformed payload. Verify that no entitlement is granted before the documented trusted success state and that retry does not double-grant credits.
4. Execute sandbox refund, partial/refund-equivalent provider outcomes and chargeback/error scenarios. Verify entitlement revoke or compensating ledger behavior, one refund event per provider event, user-facing status and support audit trail.
5. Export provider transaction/order/settlement rows and reconcile them to internal orders, ledger entries, entitlement state and product-cost events. Every unmatched row receives a reason and owner; no aggregate gross Stars value is called net revenue or margin without settlement, tax, refund and fee inputs.

### Pass/fail and evidence

| Check | Pass criterion | Evidence |
|---|---|---|
| Pricing authority | Amount/SKU/entitlement come from server catalog | Request/response contract and catalog snapshot |
| Signature/idempotency | Replays and reordering produce one trusted financial outcome | Redacted webhook replay log and DB assertions |
| Failure states | No premature entitlement; retries remain safe | State-transition table |
| Refund/chargeback | Revoke/compensate exactly once and support can explain result | Refund ledger plus support case |
| Reconciliation | All sandbox provider rows matched or explicitly investigated | Reconciliation CSV/checklist |
| Privacy/secrets | No payment token/signature secret in evidence | Redacted artifact review |

**Gate:** any duplicate grant, unverifiable webhook, silent refund mismatch, secret leak or unexplained reconciliation row is a hard fail. **Rollback:** disable paid catalog/feature flag and new checkout creation, preserve already-created ledger rows, stop entitlement grants, route pending cases to support, reconcile before re-enabling. Never delete financial audit rows to recover from a failed test.

## P0-003 — Live LLM safety, grounding and latency

**Владелец:** AI quality owner. **Предусловия:** approved synthetic dataset with no user content, model/provider versions recorded, cost cap, timeout/retry/fallback policy, red-team reviewer and staging telemetry. Existing local evidence reports zero critical violations in the synthetic suite while live LLM p95 is above the current 15-second target; this gate is therefore open.

### Процедура

1. Run the versioned synthetic set against the exact staging provider route and model configuration. Keep only case ID, category, expected class, safety decision, latency and provider metadata; do not store prompts or answers in shared evidence unless separately approved and redacted.
2. Include deterministic-domain grounding, date-only uncertainty, medical/diagnostic requests, financial/legal claims, crisis/self-harm routing, third-party mind-reading, coercive payment language, sexual/age-sensitive context, prompt injection and cross-agent tool leakage.
3. Run the same suite across success, timeout, malformed structured output, provider error, one retry and fallback conditions. Verify that the user receives a bounded safe response and that telemetry records outcome category, retry and latency without content.
4. Measure p50/p95/p99 from request acceptance to user-visible completion separately for chat, chart interpretation, Tarot and vision. Compare p95 to the approved SLO; current working target is 15 seconds for the live LLM path unless Product owner formally approves a new threshold with rationale.
5. Conduct manual review of a statistically agreed sample from each high-risk category. Record rubric scores and case IDs, never raw personal data.

### Pass/fail and evidence

| Check | Pass criterion | Evidence |
|---|---|---|
| Safety | Zero critical unfiltered claims or missed crisis routes; all high-risk categories pass approved rubric | Red-team scorecard and reviewer sign-off |
| Grounding | Deterministic facts cite/reflect tool evidence and preserve date-only uncertainty | Case-level expected-class matrix |
| Structured output | Approved valid schema/enum rate meets product threshold; invalid output uses bounded retry/fallback | Provider run summary |
| Reliability | Timeout/error/fallback never creates an unsafe blank or fabricated success | Failure injection log |
| Latency | p95 meets approved target for each paid journey, or launch scope disables the failing feature | Sanitized percentile table |
| Cost | Run remains under approved cap and new P1-011 SKU events are complete enough for a monitored beta | Cost KPI export |

**Gate:** any critical safety failure is a hard fail. Latency failure may only be accepted by narrowing launch scope or changing the SLO before the run; it may not be silently waived. **Rollback:** route feature to deterministic/free fallback, disable affected provider/model or palm/premium flag, cap traffic, preserve only redacted event evidence, and roll back the provider/config release. Add every failure as an immutable regression case before retry.

## P0-004 — Encrypted backup, isolated restore и rollback drill

**Владелец:** SRE/operations owner. **Предусловия:** production-like disposable environment, encrypted off-site backup destination, key access separated from application runtime, checksum tool, restore operator, rollback target and maintenance window. Backup evidence must not expose raw birth data, diary text, palm images, tokens or payment secrets.

### Процедура

1. Record the candidate release SHA, schema revision, database engine/config fingerprint and backup window. Quiesce or coordinate writes according to the deployment runbook.
2. Create an encrypted backup using the approved production job. Verify object existence, encryption metadata, checksum and retention policy. Keep credentials outside evidence.
3. Restore into a fresh isolated database/stack, never over the source database. Run schema integrity, foreign-key/consistency checks, owner isolation checks, report-history immutability check, deletion/anonymization check and key-path read-only smoke.
4. Run a forward migration rehearsal on a copy and a rollback rehearsal to the previous application/schema-compatible release. Confirm that no destructive migration is applied without a verified backup and that rollback does not re-expose deleted records outside the approved legal-retention policy.
5. Measure recovery time objective and recovery point objective against thresholds approved by Product/SRE. Record restore time, backup age, missing rows, checksum result, operator and final disposition.

### Pass/fail and evidence

| Check | Pass criterion | Evidence |
|---|---|---|
| Backup | Encrypted artifact exists at off-site location with verified checksum and retention | Redacted manifest |
| Restore | Fresh stack starts and schema/data integrity checks pass | Restore log and query summary |
| Isolation | Restored users cannot see one another's reports, Tarot, diary, memory or orders | Automated ownership matrix |
| Privacy/deletion | Deleted/anonymized records behave according to approved policy | Redacted deletion check |
| Rollback | Previous release starts and serves safe key-path requests; migration rollback is documented | Rollback log and timing |
| RPO/RTO | Approved thresholds met or launch scope reduced | Signed operations sheet |

**Gate:** missing backup, failed checksum, unverified restore, owner-isolation failure, irreversible rollback gap or unacceptable RPO/RTO is a hard fail. **Rollback:** keep source environment untouched, stop deployment, switch traffic to previous immutable release, restore only into isolated target until verified, and open an incident if data loss or privacy regression is found. Do not overwrite the last known-good backup during recovery.

## Execution order and go/no-go gate

The release owner opens a change window only after all four owners confirm prerequisites. Recommended order is P0-004 backup/rollback rehearsal, P0-001 staging auth/device matrix, P0-003 live AI quality/SLO, then P0-002 payment certification. A payment sandbox may run in parallel with P0-001 and P0-003, but public paid access remains blocked until all four are green. If any gate fails, the candidate is not promoted; the owner records the failure, rollback action and next evidence date.

| Gate | Required decision | Release consequence |
|---|---|---|
| G0 scope | Controlled beta or public-scale route, launch countries and SLO approved | No staging run without named limits |
| G1 security/device | P0-001 pass | No authenticated external traffic |
| G2 recovery | P0-004 pass | No irreversible migration or public data intake |
| G3 AI | P0-003 pass for enabled surfaces | Disable failing surface or block release |
| G4 commerce | P0-002 pass before paid flag | Free/paid separation; no real charge without owner approval |
| G5 final | All P0 evidence signed, CI candidate green, incident/on-call ready | Promote immutable tag, monitor heightened window |

For controlled beta, enable invite-only traffic and feature flags in waves. For public launch, require two consecutive beta waves without critical security/safety/payment incidents, with error rate, latency, provider success, support queue, deletion SLA and cost per active user within approved thresholds. Keep a 72-hour heightened monitoring window and daily incident/cost review.

## Evidence retention and redaction

Evidence is stored by release SHA and UTC window in access-controlled operational storage. It must contain test case IDs, categories, statuses, timings, aggregate counts, checksums, schema/release fingerprints and reviewer names, but not raw `initData`, auth hashes, payment tokens, provider secrets, questions, diary/memory text, birth payloads, chart JSON, palm images or complete LLM prompts/answers. Product-cost telemetry may contain only server-owned categorical SKU/catalog/channel/purpose/result/reason and bounded numeric cost/latency/retry/artifact fields. Retention follows the approved data map; support and financial records use their legally approved windows, and deletion requests never justify silently rewriting audit history.

## Required final sign-off packet

The release packet contains the candidate SHA, CI URL and full local gate output; four signed P0 checklists; redacted auth/device matrix; provider sandbox webhook and reconciliation report; live AI quality/latency/cost report; encrypted backup manifest, checksum and isolated restore/rollback logs; open-risk register; on-call contacts; and explicit owner decisions for any feature excluded from the launch scope. A local pass must be labelled local, a staging pass staging, and only a signed production exercise may be labelled production.

## Internal references

* [Production Readiness and Launch Plan](PRODUCTION_READINESS.md)
* [Task backlog](TASKS.md)
* [Backup/Restore Drill](../BACKUP_RESTORE_DRILL.md)
* [Monetization Strategy](../MONETIZATION_STRATEGY.md)
