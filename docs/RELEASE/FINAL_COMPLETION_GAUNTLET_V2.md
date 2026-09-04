# GAUNTLET v2 — Final Completion Report

Date: 2026-08-31 · Branch: `master` · Scope: local verification only

## Verdict

**LOCAL: COMPLETE.** All locally closeable gaps are closed, verified by tests and
static gates. Remaining blockers are exclusively external gates (staging /
real-device / provider / licensing), unchanged in scope from the previous pass.

## §1–2 Age policy (critical rule) — DONE (superseded)

**FINAL state (commit `148149d`): the age check was removed entirely, not just
the UX.** Earlier passes removed the user-facing confirmation step but retained a
server-side guard (`confirmed_age_user`), `eligibility.require_age`, and the
`age_confirmed` / `age_proof_hash` columns. Follow-up removed all of it:

- `confirmed_age_user` is now a pure alias of `current_user` (no 403 by age);
  `eligibility.require_age` deleted from the service.
- Bot onboarding saves any birth date without an under-16 refusal; birth date is
  only an astronomy input, never an attestation.
- The `age_gate` funnel stage and `E_AGE_CONFIRMED` event are deleted.
- Alembic `0006_drop_age_columns` drops `users.age_confirmed` /
  `age_proof_hash`; repo allowlist, anonymization reset, `/api/me` and seed
  loader no longer reference them. Baseline schema updated.
- Docs (PRODUCT / SECURITY / API / analytics / legal / P0 cases / launch) reflect
  "no age boundary"; historical CHANGELOG lines struck through.
- Removed earlier: legacy `age:confirm`/`age:decline` handlers, `age_gate_kb`,
  Mini App age-gate overlay (`showAgeGate` + i18n keys + dead CSS),
  `POST /api/profile {age_confirmed,birth_year}` client path.

## §Verification evidence

| Check | Result |
|---|---|
| Full pytest suite (docker, Postgres) | **805 passed, 1 skipped** |
| Route inventory gate (P1-009) | 155/155 routes auth'd or documented reason |
| `scripts/release_gate.py` | PASS |
| All `scripts/check_*.py` gates | PASS (in docker network where DB needed) |
| Frontend build + cache-busting | PASS (dist rebuilt after age-gate removal) |
| Independent critic (age change) | ACCEPT-WITH-RESERVATIONS; both minor findings fixed |

## §Local gaps closed this pass

| Item | Action |
|---|---|
| CRITICAL bot bug (commit 6ee1f4b review) | callback handlers wrote birth data to bot's user row → explicit `tg_id` in helpers |
| P1-009 route inventory | `scripts/check_route_inventory.py` + CI test, matrix in EVIDENCE |
| P2-005 avatar retention | closed: avatars are static assets, no user uploads |
| §1–2 age gate removal | see above |
| Agent-stability gate order sensitivity | compare as set |
| Dead age-gate CSS + orphaned funnel stage | deleted / re-pointed to bot event |

## §Not locally closeable (unchanged)

P0-001..004 (real Telegram identity, payments sandbox, live LLM SLO, backup
rehearsal in production-like infra), P1-004 independent astrology comparison,
P2-002 manual device accessibility review. These need staging/external owners.

## Update rule

This report covers LOCAL state only. No local pass may be promoted to a
staging/production claim (see CURRENT_STATUS.md update rule).
