# OracleAI — current status

## Document orientation

| Field | Definition |
|---|---|
| **Purpose** | State what is implemented, what was checked and what still blocks release. |
| **Source of truth** | Current `master` code, tests, CI configuration and [`RELEASE/TASKS.md`](TASKS.md). |
| **Scope** | Repository state observed on 2026-08-27; this document is updated as the merged master candidate changes. |
| **Do not change** | Do not convert local, synthetic or historical evidence into staging or production claims. |
| **Key files** | `app/`, `miniapp/`, `tests/`, `scripts/`, `infra/`, [`RELEASE/TASKS.md`](TASKS.md). |
| **Validation** | Use the commands in [`TESTING.md`](../TESTING.md) and the evidence record for each gate. |

## Verdict

**BLOCKED** for public launch. The repository has a substantial local implementation and automated quality baseline, but the external gates required for a public product are not certified in this checkout.

## Status by environment

| Environment | What is verified | What is not verified | Status |
|---|---|---|---|
| **LOCAL** | FastAPI/API, bot and Mini App code paths; deterministic chart, Tarot, memory, report and PDF contracts; owner-scoped persistence; safety and resilience tests; repository scripts and static checks; frontend build/provenance and release gates. The merged tree passed the full local suite and GitHub CI run [`33093428849`](https://github.com/astartv1ai-del/oracleAI/actions/runs/33093428849) (`quality` and `frontend-quality` successful). | Live provider, real Telegram identity and real payment systems are intentionally absent; visual captures and domain/palm fixtures remain local/synthetic evidence. | **IMPLEMENTED WITH LIMITATIONS** |
| **STAGING** | The code and runbooks define the required staging scenarios. | Signed Telegram `initData` and device/WebView journey, provider latency/quality, payment sandbox settlement/refund/reconciliation, production-like storage, rollback and independent domain comparison are not evidenced here. | **OPEN** |
| **PRODUCTION** | Production fail-closed configuration, Compose topology, migrations, health/security middleware and operational procedures exist in code. | No production deployment, real traffic, alert routing, encrypted off-site restore, capacity ceiling or rollback rehearsal was run from this checkout. | **NOT CERTIFIED** |
| **EXTERNAL** | Legal, licensing, provider, Telegram, payment and infrastructure owners are identified as release dependencies. | Privacy/Terms operator placeholders, Swiss Ephemeris/Kerykeion sign-off, PSP certification, country scope, live LLM and independent astronomy authority evidence remain open. | **BLOCKED** |

## Implemented surfaces

The current code includes the Telegram bot, Mini App, FastAPI API, admin surface, deterministic astrology and chart-product contracts, Tarot ledger, diary/practices, opt-in memory, bounded agents, palm upload/evidence path, billing/order/webhook foundations, PDF rendering, background-task scaffolding and migrations. The exact route and module map remains in [`ARCHITECTURE.md`](../ARCHITECTURE.md) and [`API.md`](../API.md).

The product boundary is explicit: chart and card calculations are deterministic evidence, agent responses are interpretation, memory is opt-in and untrusted, unknown birth time suppresses unsupported houses/angles, and OracleAI does not replace medical, psychological, legal or financial support.

## Open release gates

| ID | Gate | Evidence required | Current status |
|---|---|---|---|
| P0-001 | Telegram identity, onboarding and device journey | Real signed `initData`, invalid/tampered cases, real WebView/device evidence and owner isolation. Age policy since GAUNTLET v2: birth date is only an astronomy input, not an attestation; no age verification exists. | **EXTERNAL** |
| P0-002 | Payments | Provider sandbox invoice, duplicate webhook, refund, chargeback/error and reconciliation evidence. | **EXTERNAL** |
| P0-003 | Live AI | Grounding/safety/language evaluation with approved provider plus p95 latency within the owner-approved target. | **STAGING/EXTERNAL** |
| P0-004 | Operations | Encrypted backup/restore, storage permissions, migration and rollback rehearsal in disposable production-like infrastructure. | **STAGING/EXTERNAL** |
| P1-004 | Independent astrology comparison and licensing | Identical-settings comparison with an independent authority and legal confirmation of engine licensing. | **EXTERNAL** |
| P2-002 | Manual accessibility and device review | Keyboard, screen reader, contrast, touch, safe-area and reduced-motion checks on intended devices. | **STAGING** |

The authoritative task detail, acceptance criteria, evidence and blockers is [`RELEASE/TASKS.md`](TASKS.md).

## Update rule

Update this document in the same change that alters a release gate. Every status statement must name the environment and link to executable evidence or an explicit external owner. A green local check is never sufficient to mark a staging or production row as complete.

## References

[1]: [RELEASE/TASKS.md](TASKS.md) — current backlog and acceptance criteria.
[2]: [ARCHITECTURE.md](../ARCHITECTURE.md) — implementation map.
[3]: [API.md](../API.md) — HTTP contracts.
