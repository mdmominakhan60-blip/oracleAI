# OracleAI — P0 production test cases

**Назначение:** единый test-case catalog для закрытия технических P0 перед production.
**Юридические проверки:** намеренно исключены по запросу владельца.
**Статусы:** `AUTO` — должен выполняться в CI; `STAGE` — нужен controlled staging и внешняя интеграция; `MANUAL` — нужен операторский/ручной review.

> Локальные green tests не закрывают staging cases. Production gate считается пройденным только после выполнения всех `BLOCKER` cases без незакрытого critical failure.

## 1. Общие правила выполнения

Все тесты выполняются на synthetic accounts и тестовых ресурсах. В evidence сохраняются commit SHA, environment label, test-case ID, timestamp, status, duration, request ID в redacted виде и агрегированные counters. Не сохраняются raw Telegram `initData`, auth hash, bot/provider secrets, payment tokens, birth payloads, chart JSON, palm images, prompts, ответы, diary или memory text.

Перед каждым staging run фиксируются версия приложения, версия схемы, модель/провайдер, feature flags, queue configuration, DB/storage namespace и rollback artifact. Повторные запуски должны быть идемпотентными: повторный test run не должен создавать второе списание, второе entitlement, второе assistant message или второй delivery event.

## 2. P0-A — age/eligibility и queued jobs

| ID | Статус | Предусловие | Действия | Ожидаемый результат |
|---|---|---|---|---|
| A-01 | ~~AUTO/BLOCKER~~ | ~~Age-gate тест удалён~~ (GAUNTLET v2): возрастная проверка больше не выполняется. | — | — |
| A-02 | AUTO/BLOCKER | Active user. | Enqueue valid chat. | `202`; job `queued`; только owner видит status; prompt не возвращается status API. |
| A-03 | ~~AUTO/BLOCKER~~ | ~~Age-reset-mid-job тест удалён~~ (GAUNTLET v2); удаление аккаунта mid-job покрывает A-04. | — | — |
| A-04 | AUTO/BLOCKER | User status changes to `deleted` or `blocked` after enqueue. | Запустить worker. | Job rejected/terminal; no LLM, charge or content write. Другой owner не видит job. |
| A-05 | AUTO/BLOCKER | Valid queued job. | Deliver same Celery task twice. | Один charge максимум, одна user message, один assistant result, второй delivery harmless. |
| A-06 | ~~AUTO/BLOCKER~~ | ~~Age-gate тест удалён~~ (GAUNTLET v2); account_not_active still raised for deleted/blocked. | — | — |
| A-07 | AUTO | Unknown/deleted user ID. | Call worker with task ID and owner ID. | No uncaught retry loop for policy denial; status is terminal and error is bounded/non-sensitive. |
| A-08 | AUTO | Crisis-like text, confirmed active user. | Send through normal and queued paths. | Code-generated crisis response, no LLM charge; safety event follows existing contract. |
| A-09 | STAGE/BLOCKER | Signed Telegram identity for another user. | Alter user ID while preserving invalid signature/body. | `401`/safe rejection; no rate-limit identity confusion, job creation or data access. |
| A-10 | STAGE/BLOCKER | Expired, duplicate-field and tampered signed init data. | Submit each variant. | Rejected before user lookup/mutation. |

**Exit condition:** A-01…A-08 pass in CI; A-09/A-10 pass in production-like Telegram staging; no endpoint or worker path can reach `chat_service.ask` without the shared guard.

## 3. P0-B — Telegram authentication и WebView critical path

| ID | Статус | Предусловие | Действия | Ожидаемый результат |
|---|---|---|---|---|
| B-01 | STAGE/BLOCKER | Clean staging bot and empty synthetic namespace. | User opens bot, presses `/start`, opens Mini App. | User is created once; signed init data authenticates same owner; no `dev_user` path is available. |
| B-02 | STAGE/BLOCKER | Existing staging user. | Close and reopen Mini App from Telegram. | Returning user loads own profile and state; no onboarding duplication or cross-owner data. |
| B-03 | STAGE/BLOCKER | Valid signed init data. | Change user ID, username or hash independently. | Request rejected; no user update or data read. |
| B-04 | STAGE/BLOCKER | `DEV_MODE=0`. | Try `?dev_user=...` with missing/invalid signed header. | `401`; query parameter never authenticates. |
| B-05 | STAGE/BLOCKER | New user, age not confirmed. | Decline age, refresh, directly call sensitive routes. | Sensitive surfaces remain blocked server-side; no chart/chat/palm/Tarot generation. |
| B-06 | STAGE/BLOCKER | New user, age confirmed. | Complete profile with exact time, unknown time, invalid/future date, invalid city/timezone. | Valid input persists; invalid input has bounded error; unsupported precision is truthfully labelled. |
| B-07 | STAGE | Clean profile. | Navigate Today → first value → Dialogues → agent → composer → send. | No dead end; progress and error states visible; result/history are owner-scoped. |
| B-08 | STAGE | 360/390/430 px Telegram viewport. | Open keyboard, type long question, dismiss keyboard, rotate/reopen. | Composer, safe area, bottom navigation and CTA remain usable; no horizontal overflow. |
| B-09 | STAGE | Poor/slow network. | Delay API, drop one request, restore connection. | Loading state is bounded; retry is safe; draft remains; no duplicate send/charge. |
| B-10 | STAGE | Memory enabled and disabled users. | Add, recall, delete memory; repeat with memory disabled. | Consent is enforced server-side; disabled memory is neither read nor written. |
| B-11 | STAGE | Two staging owners. | Use IDs from one owner against history, diary, Tarot, palm, job and profile routes of the other. | `404`/safe rejection; zero cross-owner data. |
| B-12 | STAGE/MANUAL | Synthetic account with history/memory. | Confirm deletion twice; reopen/re-authenticate. | First deletion anonymizes/deletes allowed personal content; repeat is idempotent; no sensitive content returns. |

**Exit condition:** identity, age, critical path and owner-isolation evidence exists for selected Telegram iOS/Android/Desktop WebView devices. Local browser evidence alone is insufficient.

## 4. P0-C — live LLM quality, latency и recovery

| ID | Статус | Предусловие | Действия | Ожидаемый результат |
|---|---|---|---|---|
| C-01 | STAGE/BLOCKER | Locked model/provider configuration. | Run 30–50 synthetic cases over all four agents and safety classes. | Report includes p50/p95/p99, queue/provider/tool/final timings, tokens, cost, retries, fallback and errors. |
| C-02 | STAGE/BLOCKER | Normal traffic envelope. | Run bounded concurrency at agreed beta load. | Total p95 ≤15 s or an explicitly approved alternative SLO with UX/cost guard; no uncontrolled queue growth. |
| C-03 | STAGE | Provider returns 429/5xx/timeout. | Execute each failure deterministically. | Retry only retryable errors with bounded backoff; terminal error/fallback is clear; no duplicate charge/message. |
| C-04 | STAGE | Primary provider unavailable. | Disable primary, invoke fallback; disable all providers. | Fallback metadata is observable; all-provider failure is honest offline/error state, not fabricated live answer. |
| C-05 | STAGE | Valid chat draft. | Start request, cancel/timeout/retry. | Draft remains; partial response is not stored as final; retry uses idempotency semantics. |
| C-06 | AUTO/STAGE | Date-only chart, memory, diary and user-supplied untrusted text. | Include opposing instructions and prompt-injection-like text. | Deterministic chart evidence remains authoritative; untrusted text cannot change system/tool policy; no unsupported house/time claim. |
| C-07 | AUTO/STAGE | Crisis and soft-risk fixtures. | Run crisis, medical/legal/financial overclaim and self-harm safety fixtures. | Crisis uses code path/no charge; unsafe overclaim is softened/refused according to contract; safety event is recorded without raw excerpt in aggregate telemetry. |
| C-08 | AUTO | Tarot ledger fixture. | Ask model to invent/add/change cards and positions. | Output remains bound to stored ledger; checksum/proof does not claim more than it proves. |
| C-09 | STAGE | Palm poor-quality/valid image fixtures. | Run glare, crop, low resolution, no-lines and valid capture. | User receives actionable reshoot or bounded evidence; raw image/mask is not retained; CV time budget is visible. |
| C-10 | STAGE | Observability enabled. | Review logs and metrics after full run. | No raw prompt, answer, memory, diary, birth payload or secret; model/provider/latency/cost dimensions are sufficient for incident diagnosis. |

**Exit condition:** quality dimensions pass; p95 and cost targets are met or explicitly revised; timeout, fallback, safety, prompt integrity and PII logging checks pass.

## 5. P0-D — payment, webhook, entitlement и reconciliation

Юридические условия, published terms и tax review в данный catalog не входят. Здесь проверяется только техническая integrity платежного контура на sandbox fixtures.

| ID | Статус | Предусловие | Действия | Ожидаемый результат |
|---|---|---|---|---|
| D-01 | STAGE/BLOCKER | Trusted server catalog. | Create order from each supported channel. | Price/product/owner/channel come from server-side catalog; browser cannot substitute amount or recipient. |
| D-02 | STAGE/BLOCKER | Pending valid order. | Deliver valid signed provider completion event. | Order settles once; entitlement/grant and ledger entry are exactly one. |
| D-03 | STAGE/BLOCKER | Same event ID/transaction/order. | Deliver webhook 2–5 times concurrently and sequentially. | No duplicate grant, balance increase, delivery or analytics event; responses are safe and observable. |
| D-04 | STAGE/BLOCKER | Valid signature with wrong order/owner/price. | Mutate one binding at a time. | Event rejected before mutation; order and entitlement unchanged. |
| D-05 | STAGE | Bad signature, stale timestamp, malformed JSON, unknown event. | Submit each event. | Rejected with bounded response; no DB mutation; alert/metric records category without secret/payload leakage. |
| D-06 | STAGE/BLOCKER | Provider timeout after local order creation. | Interrupt callback/replay later. | Pending order remains recoverable; no phantom entitlement; replay settles once. |
| D-07 | STAGE/BLOCKER | Settled entitlement. | Execute refund/reversal/cancellation/expiry. | Status, access and accounting/reconciliation follow one explicit state transition; no silent negative/duplicate balance. |
| D-08 | STAGE | Payment journal/database failure simulation. | Fail journal at duplicate-event boundary. | System fails closed or produces a detectable reconciliation exception; no silent double grant. |
| D-09 | STAGE | Orders from bot, Mini App, web and crypto/crystals path. | Complete one test in each channel. | `surface/channel` attribution is correct and consistent; product-cost event matches settlement path. |
| D-10 | MANUAL | Sandbox receipts and reconciliation export. | Reconcile provider events with internal orders/payments/entitlements. | Zero unexplained amount, status or entitlement delta; evidence is retained in protected ops storage. |

**Exit condition:** D-01…D-09 pass automatically or in provider sandbox; D-10 is reviewed by technical/payment owner; no duplicate grant or unexplained balance delta.

## 6. P0-E — encrypted backup, restore и rollback

| ID | Статус | Предусловие | Действия | Ожидаемый результат |
|---|---|---|---|---|
| E-01 | STAGE/BLOCKER | Production-like storage and key provider. | Run scheduled backup. | Snapshot is encrypted, checksummed, tagged with release/schema metadata; logs contain no data. |
| E-02 | STAGE/BLOCKER | Missing/invalid key or storage permission. | Run backup/restore. | Operation fails closed; no plaintext artifact; alert emitted. |
| E-03 | STAGE/BLOCKER | Valid encrypted snapshot. | Restore into isolated target. | Decrypt/verify/checksum succeeds; schema, indexes, counts and app health pass. |
| E-04 | STAGE/BLOCKER | Two synthetic owners with reports/history/memory/entitlements. | Compare source and restored data. | Owner isolation and permitted data integrity match; no cross-owner row appears. |
| E-05 | STAGE | Corrupted/truncated snapshot. | Attempt restore. | Checksum/integrity rejects artifact before service promotion; incident signal is emitted. |
| E-06 | STAGE/BLOCKER | Active queue and one in-flight job. | Restore/rollback around queued job. | No duplicate LLM generation, payment grant or assistant message; job status is reconciled. |
| E-07 | STAGE/BLOCKER | Previous release artifact. | Execute rollback to previous release and restore path. | Health/read/write smoke passes; rollback duration and RTO measured; forward deployment remains possible. |
| E-08 | STAGE | Artificially stale/missing backup. | Trigger freshness monitor. | Alert fires with bounded metadata; on-call can identify last successful snapshot. |
| E-09 | MANUAL | Restore runbook and operator role. | Independent operator follows runbook. | Procedure is executable without undocumented tribal knowledge; evidence includes RPO/RTO and decision points. |

**Exit condition:** encrypted production-like restore and rollback pass, RPO/RTO measured, alerting verified, and queue/payment idempotency preserved.

## 7. P0-F — независимая correctness и PDF

| ID | Статус | Предусловие | Действия | Ожидаемый результат |
|---|---|---|---|---|
| F-01 | AUTO/STAGE/BLOCKER | Versioned independent reference fixtures. | Compare exact birth-time chart outputs. | Longitudes, UTC conversion, house/angle and retrograde values fall within approved tolerances. |
| F-02 | AUTO/STAGE/BLOCKER | Date-only fixtures. | Generate chart, prose and PDF without birth time. | No house/ASC/MC or other unsupported precision overclaim; truth state is consistent in API/UI/PDF. |
| F-03 | AUTO/STAGE | DST/non-whole-hour timezone fixtures. | Compute and render. | Timezone conversion and display are stable; no silent one-hour shift. |
| F-04 | AUTO/STAGE | High-latitude fixtures. | Compute supported/unsupported cases. | Result is correct or explicit bounded unsupported state; no malformed chart/PDF. |
| F-05 | AUTO | Extended points fixture. | Check nodes, Chiron, Juno, Ceres, Vesta, Pallas and capability flags. | Values and advertised capabilities match structured output; unsupported features are not implied. |
| F-06 | AUTO | RU/EN PDF golden fixtures. | Generate all exact/date-only/DST/high-latitude representatives. | Document exists, headings localize, long names fit, truth state and engine claims are correct. |
| F-07 | MANUAL/STAGE/BLOCKER | Rendered PDF set. | Review pages on target desktop/mobile viewer. | No clipping, blank pages, broken fonts, misleading precision, unlocalized text or inaccessible critical statement. |
| F-08 | MANUAL | Independent reviewer and reference version. | Review numeric diff and unexplained mismatch list. | Every difference is accepted, fixed or blocks release; production calculator is not its own sole oracle. |

**Exit condition:** independent numeric comparison and customer-facing PDF review have zero unexplained critical mismatch.

## 8. Release-gate summary

| Gate | Required evidence | Hard failure |
|---|---|---|
| Security invariant | A-01…A-10, B-01…B-06, B-11 | Any unauthorized, unconfirmed, deleted or cross-owner path reaches sensitive operation. |
| Critical user value | B-07…B-09, C-02…C-05 | User cannot reach first value, answer is unboundedly slow, or retry duplicates charge/result. |
| Money integrity | D-01…D-10 | Duplicate grant, wrong owner/price binding, unexplained balance delta or unrecoverable pending order. |
| Data recovery | E-01…E-09 | Plaintext backup, failed restore, unknown RPO/RTO or duplicate processing after rollback. |
| Domain truth | F-01…F-08 | Unsupported precision claim, unexplained calculator mismatch or broken customer-facing PDF. |
| Operational observability | C-10, D-05, E-02, E-08 plus CI/release gate | Incident cannot be diagnosed without raw personal data or secrets. |

## 9. Expected pre-production evidence package

The release folder should contain a redacted test summary, case-level statuses, latency/cost aggregate, provider/model configuration fingerprint, migration/schema fingerprint, signed-auth negative-case summary, payment reconciliation summary, backup checksum/restore/RTO/RPO summary, calculation diff summary, rendered PDF review notes and rollback result. It should not contain personal data or secret-bearing request bodies.

A technical GO requires every blocker row to be `PASS`, all failed/retried cases to have a documented cause and rerun, and no unresolved P0 exception. A controlled beta may use a narrower, owner-approved scope only if its disabled features are enforced server-side and the release record explicitly lists excluded cases; this is not a public-production pass.

## References

[1]: [P0 technical implementation plan](https://github.com/astartv1ai-del/oracleAI/blob/master/docs/RELEASE/P0_PRODUCTION_EXECUTION_PLAN.md) — repository execution baseline.
[2]: [app/api/routers/jobs.py](https://github.com/astartv1ai-del/oracleAI/blob/master/app/api/routers/jobs.py) — queued chat API.
[3]: [app/tasks/tasks.py](https://github.com/astartv1ai-del/oracleAI/blob/master/app/tasks/tasks.py) — queued worker execution.
[4]: [app/services/chat.py](https://github.com/astartv1ai-del/oracleAI/blob/master/app/services/chat.py) — shared chat, safety, limits and persistence.
[5]: [app/api/deps.py](https://github.com/astartv1ai-del/oracleAI/blob/master/app/api/deps.py) — identity, age confirmation and rate limiting.
[6]: [app/services/billing.py](https://github.com/astartv1ai-del/oracleAI/blob/master/app/services/billing.py) and [app/api/routers/webhooks.py](https://github.com/astartv1ai-del/oracleAI/blob/master/app/api/routers/webhooks.py) — payment integrity paths.
[7]: [infra/backup-postgres.sh](https://github.com/astartv1ai-del/oracleAI/blob/master/infra/backup-postgres.sh) и [infra/restore-postgres.sh](https://github.com/astartv1ai-del/oracleAI/blob/master/infra/restore-postgres.sh) — PostgreSQL backup/restore procedure; production drill remains an external gate.
[8]: [scripts/check_pdf_golden_cases.py](https://github.com/astartv1ai-del/oracleAI/blob/master/scripts/check_pdf_golden_cases.py) — synthetic PDF truth-state checks.
[9]: [docs/AI_SYSTEM.md](https://github.com/astartv1ai-del/oracleAI/blob/master/docs/AI_SYSTEM.md) — agent quality, safety and latency baseline.
