# OracleAI — testing contract

## Document orientation

| Field | Definition |
|---|---|
| **Purpose** | Verification strategy and interpretation of evidence. |
| **Source of truth** | `tests/`, `scripts/`, `.github/workflows/ci.yml`. |
| **Scope** | Unit, integration, security, domain, visual, release and external checks. |
| **Do not change** | Do not call synthetic/local evidence staging or production certification. |
| **Key files** | `tests/`, `scripts/`, `.github/workflows/ci.yml`. |
| **Validation** | `pytest -q && ruff check app scripts tests`. |


## Required verification layers

| Layer | Scope | Command / evidence |
|---|---|---|
| Unit | Domain calculations, parsers, safety rules, repositories and services. | `pytest -q` and focused test modules. |
| Integration | PostgreSQL schema/migrations, billing idempotency, API contracts and provider fallbacks. | `tests/`, `scripts/selfcheck.py`, `scripts/reset_test_database.py`. |
| Static | Python syntax, Ruff, JavaScript syntax, repository hygiene and design contracts. | CI commands and `scripts/check_*.py`. |
| Domain QA | Golden cases for exact/date-only charts, timezone/DST, products, Tarot/Matrix/Vedic boundaries and palm confidence. | Versioned fixtures and comparison evidence. |
| Security QA | Telegram signature, owner isolation, IDOR, rate limits, secret redaction, upload validation and webhook signatures. | `tests/test_security_regressions.py`, auth/webhook tests. |
| Visual QA | Landing, Mini App states, mobile/desktop layout and rendered PDF pages. | Screenshots/rendered artifacts kept outside source tree unless intentionally approved. |
| E2E | New user, returning user, natal, date-only, synastry and Tarot journeys. | Disposable DB and staging/browser evidence. |
| Production gate | Real Telegram, live providers, payments, deployment, backup/restore and licensing/legal sign-off. | External owner evidence; never represented by local mocks. |

## Baseline commands

```bash
APP_ENV=dev DEV_MODE=1 LLM_PROVIDER=off \
DATABASE_URL=postgresql+asyncpg://oracle:oracle@127.0.0.1:5432/oracle_test \
pytest -q
python3 -m scripts.selfcheck
python3 -m scripts.release_gate
python3 -m compileall -q app scripts tests
ruff check app scripts tests
find miniapp/js admin -type f -name '*.js' -print0 | xargs -0 -r -n1 node --check
python3 scripts/check_documentation_links.py
pip-audit -r requirements.txt
```

## Test-quality rules

Tests must assert observable behavior and meaningful invariants. Do not swallow exceptions, weaken expected values to make a test green, replace integration failures with broad mocks, or add snapshots without semantic assertions. Every new feature must include negative input, missing input, unauthorized access, rate-limit/retry and empty/partial-state coverage appropriate to its contract.

## Current evidence

At the 2026-08-26 baseline, the full existing suite, self-check, release gate, Python/JavaScript syntax, Ruff, repository hygiene and dependency audit passed in offline local mode. Live LLM, Telegram device, payment settlement, production deployment, visual browser, independent calculator and restore-drill evidence remain explicit external or follow-up gates.

## References

[1]: ../tests/ "OracleAI automated tests"  
[2]: ../scripts/selfcheck.py "Repository self-check"  
[3]: ../scripts/release_gate.py "Production-readiness static gate"  
[4]: ../.github/workflows/ci.yml "Continuous integration workflow"
[5]: ../scripts/check_documentation_links.py "Repository-relative Markdown link checker"
