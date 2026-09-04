# OracleAI — Final QA Matrix

## Scope and evidence policy

Проверка выполнена с чистого checkout ветки `master` на исходном коммите `3b8f578` (27 августа 2026). Цель матрицы — зафиксировать не только зелёные проверки, но и поверхности, для которых в sandbox не было реальных Telegram/payment credentials или Docker daemon. `NOT RUN` и `PARTIAL` не трактуются как PASS.

QA-пользователь `tg_id=10001` создавался только в disposable SQLite-базе `/tmp/oracleai_qa.db` скриптом `scripts/seed_visual_user.py`; production data не использовалась.

| Surface | Test | Expected | Actual | Result | Evidence |
| --- | --- | --- | --- | --- | --- |
| Clean checkout | Clone `master`, inspect status and HEAD | Reproducible clean tree | Clone clean, HEAD `3b8f578` | PASS | `git status --short --branch`; `git log -1` |
| Python install | Fresh venv + `pip install -r requirements-dev.txt` | Dependencies install without hidden local state | PASS after installing standard native build prerequisites (`build-essential`, `pkg-config`, SQLite/Python headers) | PASS | `/tmp/oracleai_pip_install4.log` |
| Node install | `npm ci` + `npm audit` | Lockfile-resolved install without known advisories | PASS; clean `npm audit` reports 0 vulnerabilities after Lighthouse remediation | PASS | `/tmp/oracleai_npm_ci_override.log`, `package.json`, `package-lock.json` |
| Database startup | New SQLite DB, app startup, health endpoint | Clean DB, WAL, schema, integrity | `ok=true`, integrity `ok`, journal `wal`, 49 tables | PASS | `GET /api/health`; `/tmp/oracleai_api.log` |
| Migrations | `pytest tests/test_migrations.py`, full fixture startup | Ordered, repeatable schema setup | Covered by full suite; no migration failures | PASS | `pytest` result; `tests/test_migrations.py` |
| Automated tests | `pytest -q` after frontend build | All regression tests pass | 606 passed, 1 skipped | PASS | `/tmp/oracleai_pytest_after_build.log` |
| Selfcheck | `python -m scripts.selfcheck` | Runtime smoke checks pass | PASS | PASS | `/tmp/oracleai_selfcheck_baseline.log` |
| Release gate | `python -m scripts.release_gate` | Static release contract passes | `RELEASE GATE: PASS` | PASS | `/tmp/oracleai_release_gate_baseline.log` |
| Static analysis | Ruff + `compileall` | No lint or syntax errors | Both PASS | PASS | `/tmp/oracleai_ruff_baseline.log`, `/tmp/oracleai_compile_baseline.log` |
| Frontend build | `npm run build:frontend` + `check_frontend_build.py` | Hashed bundles and valid manifest | `app.c477d084b2d4.min.js`, `app.7678b94995ed.min.css`; manifest validated | PASS | `/tmp/oracleai_frontend_build_baseline.log`, `/tmp/oracleai_check_frontend_build.log` |
| Static assets | `check_static_asset_references.py` + cache busting | No stale/missing references | PASS; cache policy `v102` and independent asset versions detected | PASS | `/tmp/oracleai_check_assets.log`, `/tmp/oracleai_cache_busting.log` |
| Repository hygiene | `check_repository_hygiene.py` | No forbidden artifacts/secrets in source tree | PASS | PASS | `/tmp/oracleai_hygiene.log` |
| Design contract | `check_design_contract.py` | Tokens, motion, focus, touch targets and inventory valid | PASS | PASS | `/tmp/oracleai_design_contract.log` |
| Skill/agent quality | Skill library, agent stability, Vedic and Mira smoke benchmarks | Deterministic contracts and bounded agent behavior | All PASS; 4 agents, 139 skills; Mira/vedic smoke PASS | PASS | `/tmp/oracleai_skill_library.log`, `/tmp/oracleai_agent_stability.log`, `/tmp/oracleai_vedic.log`, `/tmp/oracleai_mira.log` |
| Accessibility | Axe on 10 seeded SPA states | Zero violations | 0 violations for all 10 states; one `color-contrast` incomplete review item per state | PASS with review item | `artifacts/lighthouse-axe-final/summary.json` |
| Lighthouse | 10 seeded states at 1440×900 | No runtime errors; accessibility/best practices/SEO valid | Runtime errors `null`; accessibility 100, best practices 100, SEO 100 for every state; performance 31–67 in clean remediated run | PASS with performance follow-up | `artifacts/lighthouse-axe/summary.json` |
| Onboarding | New user: age → welcome → onboarding → first value | State progresses and persists | API/fixture coverage passes; visual seeded returning-user path verified | PASS (API/seeded UI) | `tests/test_bot_fsm.py`, `tests/test_api.py`, Lighthouse matrix |
| Telegram `/start` | Real Bot API start, deep link, referral and promo | Telegram identity and start params verified server-side | Not executable: no real bot token/session in sandbox | NOT RUN | External credential required |
| Mini App | Real browser load, routing, API calls, seeded content | App renders across home/hub/chat/profile states | All 10 seeded routes loaded; no runtime errors | PASS | Lighthouse/axe summaries |
| Chat | Oracle, astrology, Tarot, chiromant routes | Composer, history and agent surfaces render safely | All 4 chat routes rendered; API contract tests pass | PASS (seeded UI/API) | `tests/test_api.py`, `artifacts/lighthouse-axe/summary.json` |
| Agents | Agent routing, skills and bounded workflow | Correct agent/domain boundary | Routing, stability and context tests PASS | PASS | `tests/test_agent_routing.py`, `tests/test_agent_stability.py`, `tests/test_agent_context*.py` |
| Tools | Tool allowlist, executor boundary and errors | Forbidden tools rejected; valid tools bounded | Contract/security tests PASS | PASS (automated) | `tests/test_agent_context_integrity.py`, `tests/test_interpretation_guardrails.py` |
| Memory | Explicit opt-in, pause/off, isolation, deletion | Memory remains owner-scoped and untrusted | Regression tests PASS, including memory-off and cache invalidation | PASS (automated) | `tests/test_security_regressions.py`, `tests/test_memory_evaluation.py` |
| Tarot | Draw, finalize, history and owner scope | Append-only answer and owner isolation | Tests PASS; seeded history rendered | PASS | `tests/test_tarot_contract.py`, `tests/test_security_regressions.py` |
| Astrology | Natal, date-only, transit/compatibility contracts | Stable schema and no cross-surface contradiction | Chart contract/domain tests PASS; seeded chart rendered | PASS (automated/seeded UI) | `tests/test_chart_contract.py`, `tests/test_domain_qa.py` |
| Palm | Upload/vision contract and safe response schema | Strict schema, controlled upload pipeline | Static release gate and palm tests PASS; real image pipeline not exercised in browser | PARTIAL | `tests/test_palm_*.py`, `app/core/palm/` |
| History | Unified archive and deep links | Owner-scoped, normalized, content-redacted list | API tests PASS; direct probe returned owner-scoped history | PASS | `tests/test_api.py`, `GET /api/history?dev_user=10001` |
| Reports | Report creation/history/PDF contracts | Stored result and report paths remain consistent | Report/PDF tests PASS | PASS (automated) | `tests/test_report_history.py`, `tests/test_pdfgen.py`, `tests/test_pdf_matrix.py` |
| Shop | Product/SKU/plan display | Server-authoritative catalog | Monetization/product tests PASS | PASS (automated) | `tests/test_billing.py`, `tests/test_chart_products.py` |
| Payments | Product → provider → webhook → entitlement → result | Real provider state transitions, idempotency and refund | Unit/regression tests PASS; real provider/webhook unavailable | PARTIAL | `tests/test_billing.py`, `tests/test_payment_monitor.py`, external provider required |
| Admin | Admin dashboard, analytics, operations | Normal user cannot access privileged actions | Automated auth tests PASS; normal-user probe received safe 404 | PASS (automated/probe) | `tests/test_analytics.py`, `tests/test_p1_controls.py`, HTTP probe log |
| Profile | Preferences, timezone, gender, language | Validation and persistence | API tests PASS; profile states rendered | PASS | `tests/test_api.py`, Lighthouse matrix |
| Deletion/privacy | Export, anonymization, account deletion | Sensitive rows removed/pseudonymized; no resurrection | Anonymization and webhook redaction tests PASS; destructive live deletion not run | PASS (automated), PARTIAL (live) | `tests/test_security_regressions.py`, `tests/test_api.py` |
| Localization | RU/EN labels and truth states | No broken/contradictory localization | Localization tests PASS; browser run used `ru-RU` | PASS (automated/RU) | `tests/test_content_localization.py`, `tests/test_api.py` |
| Mobile E2E | 375/390/430px and Telegram WebView behavior | Safe area, keyboard, scrolling, back/deep links/uploads | Desktop browser matrix only; no mobile WebView device available | NOT RUN | Device/Telegram WebView required |
| Desktop E2E | 1024/1440/1920px | Bounded layouts and admin/report/chat states | Lighthouse/axe at 1440; other desktop widths not executed in this run | PARTIAL | `artifacts/lighthouse-axe/summary.json` |
| Telegram notifications | Real notification delivery | Correct user/channel and privacy boundaries | Not executable without Bot API credentials | NOT RUN | External credential required |
| Clean Docker stack | Compose build → migrate → run → test | Reproducible full service topology | Docker CLI/daemon absent in sandbox | NOT RUN | `docker: command not found`; `infra/docker-compose.yml` |

## Attack coverage summary

| Attack family | Result | Evidence |
| --- | --- | --- |
| Missing/invalid authentication | Safe `401`/`404`; signed initData freshness and duplicate-field tests pass | `tests/test_security_regressions.py`, HTTP probes |
| IDOR / owner scope | History, Tarot, diary, reports and append-only ownership tests pass | `tests/test_api.py`, `tests/test_security_regressions.py` |
| Admin bypass | Normal-user admin probe did not expose privileged data; authorization tests pass | `tests/test_analytics.py`, `tests/test_p1_controls.py` |
| Memory/prompt trust boundary | Memory-off, cache invalidation and context-integrity tests pass | `tests/test_security_regressions.py`, `tests/test_agent_context_integrity.py` |
| XSS/markup | Telegram escaping tests pass; invalid profile markup rejected | `tests/test_security_regressions.py`, HTTP probe |
| Payment/webhook | Signature/idempotency and billing regression tests pass; real provider unavailable | `tests/test_billing.py`, `tests/test_payment_monitor.py` |
| Upload/palm | Strict schema and palm contract checks pass; malicious live uploads not executed | `tests/test_palm_vision.py`, `tests/test_palm_integration.py` |
| QA tooling supply chain | Initial audit found 4 high transitive advisories; Lighthouse pin plus `@puppeteer/browsers=3.2.1` override removes `extract-zip`; clean audit now 0 | `npm audit`, `package.json`, `package-lock.json` |
| Path traversal/error leakage | Traversal probe `404`; malformed input produced controlled `400` | `tests/test_api.py`, HTTP probes |

## Matrix conclusion

Функциональные и статические проверки на доступном локальном контуре пройдены. Матрица **не подтверждает release readiness**: отсутствуют Docker clean-stack evidence, real Telegram E2E, mobile Telegram WebView E2E и real payment provider lifecycle. Эти ограничения отражены как `NOT RUN`/`PARTIAL`, а не замаскированы под PASS.
