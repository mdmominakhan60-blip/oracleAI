# OracleAI — автономный backlog

## Document orientation

| Field | Definition |
|---|---|
| **Purpose** | Authoritative unresolved release backlog. |
| **Source of truth** | `app/`, `tests/`, `scripts/`, `infra/` and external owners. |
| **Scope** | Only current tasks with ID, subsystem, priority, problem, acceptance, status, evidence and blocker. |
| **Do not change** | Do not keep competing TODO/backlog lists or close external gates using local-only evidence. |
| **Key files** | `docs/RELEASE/CURRENT_STATUS.md`, `docs/EVIDENCE/TRACEABILITY_MATRIX_2026-08-26.md`. |
| **Validation** | `python3 -m scripts.release_gate`. |


**Дата baseline:** 2026-08-26  
**Исходный коммит:** `e25c9d5870cd7acd4e65e9ca533e864b2a2181d5`  
**Правило:** задача считается закрытой только после implementation, tests, relevant QA, documentation and evidence.

## Completed baseline checks

| Check | Result | Evidence |
|---|---|---|
| Dependency installation | **Pass** after installing `build-essential`, `pkg-config`, `libsqlite3-dev`, `python3.12-dev` | pinned `requirements-dev.txt` installed successfully |
| Repository self-check | **Pass**, two expected skips: live LLM and incomplete local `.env` | `APP_ENV=dev DEV_MODE=1 LLM_PROVIDER=off python3 -m scripts.selfcheck` |
| Automated tests | **Pass** | `APP_ENV=dev DEV_MODE=1 LLM_PROVIDER=off pytest -q` |
| Python syntax | **Pass** | `python3 -m compileall -q app scripts tests` |
| JavaScript syntax | **Pass** | `node --check` for all `miniapp/js/*.js` and `admin/*.js` |
| Ruff | **Pass** | `ruff check app scripts tests` |
| Release gate | **Pass** | `python3 -m scripts.release_gate` |

## P0 — release blockers

| ID | Subsystem | User journey | Problem / evidence | Acceptance criteria | Status |
|---|---|---|---|---|---|
| P0-001 | Security / auth | Any authenticated request | Production auth requires real Telegram initData and secrets; local baseline cannot validate real signature or device behavior. | Run disposable staging with real signed initData, verify invalid/expired/tampered signatures, owner isolation and no PII in URLs/logs. | External gate |
| P0-002 | Payments | Purchase → webhook → entitlement | Local tests prove signature/idempotency logic, not provider settlement or refund reconciliation. | Complete sandbox provider certification for invoice, duplicate webhook, refund, chargeback/error and reconciliation; capture logs/evidence without secrets. | External gate |
| P0-003 | Safety / AI | User asks for high-stakes or deterministic fact | Live synthetic provider evaluation now exists and has zero critical violations; measured p95 latency still exceeds the product target. | Execute live evaluation set for grounding, forbidden guarantees, medical/diagnostic claims, third-party mind reading and refusal behavior; zero critical violations and p95 target. | Partial: safety/language/calibration pass; latency gate open |
| P0-004 | Operations | Deploy → migrate → recover | Backup scripts and runbook exist; a disposable Python restore drill now runs locally. | Run disposable backup/restore drill and verify schema, user isolation, report snapshots and rollback. | Partial: local integrity/isolation pass; production storage and rollback remain external |

## P1 — highest-value local work

| ID | Subsystem | User journey | Problem / evidence | Acceptance criteria | Status |
|---|---|---|---|---|---|
| P1-001 | Product / history | Returning user → previous research → new tool | Unified archive now covers reports, Tarot, sessions and diary; palm remains explicitly excluded because it is not persisted as a first-class artifact. | Define unified history read model with owner scope, kind, created-at, snapshot/evidence ID, deep link and deletion behavior; add API/UI tests. | Done locally with palm boundary |
| P1-002 | Memory | Enable memory → chat → recall → edit/delete | Dedicated synthetic evaluator now covers retrieval, pause, deletion, isolation, contradiction and injection-shaped data. | Add memory evaluation fixtures for relevance, opt-in, pause, deletion, profile isolation, stale/contradictory facts and injection resistance; document thresholds. | Done locally for synthetic evaluator; longitudinal stale-fact telemetry open |
| P1-003 | PDF | Calculate → interpret → save → regenerate | A deterministic six-case RU/EN matrix now covers exact/date-only, long-name, DST-shaped and high-latitude inputs. | Generate RU/EN exact-time and date-only, long-name/city, edge-coordinate, minimal/maximal and dense-aspect reports; render and inspect pages; fix clipping, glyph, density and truth-state issues. | Done locally for synthetic matrix; production pixel/font review open |
| P1-004 | Domain QA | Natal / date-only / products | Canonical contracts and a reproducible cross-implementation harness now cover the required critical cases; a second independent ephemeris authority is not yet captured. | Record two independent calculator comparisons with identical settings for normal, DST, historical timezone, unknown time, edge longitude, high latitude and midnight cases; explain every difference. | Partial: 8/8 local cross-implementation cases pass; external authority comparison open ([QA](../DOMAIN/ACCURACY_MATRIX.md)) |
| P1-005 | Vedic boundary | Vedic tool → interpretation | Lahiri/sidereal/date-only/no-Western-leakage boundary is now documented and tested in the existing Vedic contract. | Specify Lahiri sidereal rules, ayanamsa, nakshatra/dasha/panchang boundaries, no western semantic leakage, golden cases and error behavior. | Done locally for boundary; independent calculator comparison open |
| P1-006 | Tarot / Lenormand | Question → draw → replay → history | Tarot contract tests now cover 78-card invariants, persistence/replay, reversal ledger and unsupported Lenormand fallback. | Document and test 78-card Tarot invariants, random draw persistence, replay semantics, reversal, and separately define or remove unsupported Lenormand promises. | Done locally for enabled Tarot; canonical Lenormand intentionally disabled |
| P1-007 | Data integrity | Profile update → historical report | Legacy unique key plus `INSERT OR REPLACE` destroyed prior report versions. | Append-only schema/migration, immutable `report_id`, owner-scoped retrieval, deterministic source metadata and regression tests prove old rows survive regeneration. | **Done locally** |
| P1-008 | E2E | New and returning users | Seeded Playwright journey now captures onboarding, natal/chart, history, memory, chat and Tarot states; real Telegram remains external. | Add automated browser or equivalent integration flows for onboarding, natal, date-only, memory, chat, synastry and tarot with screenshots/logs. | Done locally for seeded journey; Telegram WebView and full synastry route remain external |
| P1-009 | API resilience | Any tool | Deterministic matrix now covers missing identity, validation, paused memory, owner-scoped 404, rate limit and safe backend failure. Route inventory gate (`scripts/check_route_inventory.py` + `tests/test_route_inventory.py`, matrix in `docs/EVIDENCE/ROUTE_INVENTORY_P1009.txt`) proves all 155 /api routes carry an auth dependency or a written public reason; CI-enforced. | Build a route-by-route matrix and cover all key surfaces with deterministic negative tests plus frontend state assertions. | **Done locally**; timeout/cancellation and expired-session staging remain open |
| P1-010 | Observability | Production incident | Local structured logs expose correlation, redaction, latency and error fields; dashboards and production journey sampling are not available in the repository run. | Confirm correlation IDs, redaction, latency/error fields and event dictionary for key journeys without sensitive payloads. | Partial: local assertions pass; deployed dashboards and journey sampling remain external |
| P1-011 | Monetization analytics | Paid action → result delivered → margin | Product-level event ledger now complements legacy `llm_usage` with server-owned dimensions, retries, latency, artifact bytes, delivery/refund/support categories and explicit unknown contribution inputs. | Add privacy-safe SKU/catalog/channel/purpose dimensions; record retries, render time/bytes, delivery, refund and support categories; expose cost and contribution by product without user text or secrets. | **Done locally; production settlement/tax/refund inputs and dashboard remain external** |

## P2 — product quality and trust

| ID | Subsystem | Problem | Acceptance criteria | Status |
|---|---|---|---|---|
| P2-001 | UX / design | Seeded visual QA now covers home, chat, profile, chart, history, memory and Tarot at three mobile widths plus reduced-motion reference; pixel reconstruction adds measured geometry and admin responsive states. The age-gate screen was removed from the product (birth date is the attestation) and its visual-QA state retired. | Capture visual regression matrix for landing, home, chat, profile, chart, tarot, memory, loading, empty, error and reduced-motion states; fix inconsistencies. | Done locally for covered states; desktop/loading/error/manual visual review open |
| P2-002 | Accessibility | Static code checks do not prove keyboard, screen reader, focus, contrast and touch-target behavior. | Run automated accessibility checks plus manual keyboard/mobile review; document exceptions and fixes. | Done locally for Mini App and admin automated checks; manual Telegram/device review open |
| P2-003 | Localization | RU/EN strings exist; one mixed-language fallback was found and corrected with regression coverage. | Create glossary and test all supported locales, long labels, technical calculation labels, pluralization and report glyphs. | Improved locally; broader glossary/typography open |
| P2-004 | Account lifecycle | Confirm-gated idempotent account deletion now anonymizes PII/history and disables memory, push and age flags. | Add deletion/anonymization contract, confirmation, idempotency, audit behavior and privacy tests. | Done locally for API contract; legal retention sign-off open |
| P2-005 | Avatar / uploads | Palm upload integration validates MIME, malformed/undersized/oversized files, JPEG/PNG/WebP normalization, low-quality fallback and raw-image non-retention; individual deletion now scrubs analysis and image fingerprints. Avatars are static product assets only (`/static/img/agents/`) — no user avatar uploads exist, so no avatar retention lifecycle is needed. | Define upload validation, size/type limits, retention/deletion, privacy and low-quality UI states; test malicious/oversized files. | **Done locally**; object-storage lifecycle applies only if user uploads are introduced |
| P2-006 | Unified report templates | `PDF_TEMPLATE_CATALOG.md` now documents enabled natal output and explicit synastry/Tarot/future gates. | Document human/verification layers, page components, localization and snapshot inputs for natal, synastry, tarot and future products. | Done locally as catalog; future exports/licensing gates open |
| P2-007 | Performance | Directional benchmark now reports chart, Tarot, memory and offline PDF p50/p95; live LLM p95 remains 22.14s versus 15s target. | Run local benchmark with representative profiles and conversations; define budgets and optimize only measured regressions. | Done locally for directional baseline; staging SLO and LLM optimization open |
| P2-008 | Growth / monetization UX | Billing and negative entitlement logic are locally tested; the paywall now has RU/EN copy parity, provider-confirmed access messaging, retry/history states and accessible payment actions. | Verify transparent pricing, entitlement errors, trial, cancellation and refund copy with no dark patterns. | Improved locally; provider sandbox, trial/cancellation/refund and visual UX review open |

## P3 — later improvements

| ID | Subsystem | Candidate | Acceptance criteria | Status |
|---|---|---|---|---|
| P3-001 | Chart products | Additional returns, lunar returns, progressions, Davison and relocation | Add only with separate domain contract, evidence, UI, export and golden cases. | Deferred |
| P3-002 | Semantic memory | Optional embeddings and relevance ranking | Add benchmark proving improvement over lexical retrieval and preserve opt-in/privacy boundaries. | Deferred |
| P3-003 | Sharing | Richer report/share cards | Add only after privacy, localization and visual regression gates pass. | Deferred |
| P3-004 | CRM | External support/CRM connector | Add only after connector/security review and minimum product need is established. | Deferred |

## Production execution reference

The detailed owner/procedure/evidence/rollback plan for P0-001 through P0-004 is in [RELEASE/P0_PRODUCTION_EXECUTION_PLAN.md](P0_PRODUCTION_EXECUTION_PLAN.md). Local checks must not be promoted to production claims.

## Working rules

Before closing any task, record the changed files, tests, visual/domain/security QA, rollback approach and evidence link in `docs/EVIDENCE/TRACEABILITY_MATRIX_2026-08-26.md`. Do not claim a local check proves an external production gate. Keep deterministic facts immutable and make every limitation visible in API, UI, AI and PDF.
