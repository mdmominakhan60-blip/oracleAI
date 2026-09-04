# OracleAI — Final Release Certification

**Дата проверки:** 27 августа 2026.
**Аудируемая ветка:** `master`.
**Исходный audited commit:** `3b8f578f033d7073e6b399039edc0effd44cbd8a`.
**Финальный verdict:** **BLOCKED**.

## Build

Аудит начат с нового clone ветки `master`; исходное рабочее дерево было чистым. Локальная проверка использовала Python `3.12.3`, Node.js `v22.13.0`, npm `10.9.2` и свежие зависимости из `requirements-dev.txt` и `package-lock.json`. Для сборки `pyswisseph` в sandbox потребовались стандартные native prerequisites: `build-essential`, `pkg-config`, `libsqlite3-dev` и `python3.12-dev`.

Frontend был собран командой `npm run build:frontend`. Проверенный manifest указывает на хешированные ассеты `app.c477d084b2d4.min.js` и `app.7678b94995ed.min.css`; `check_frontend_build.py`, `check_static_asset_references.py` и `check_cache_busting.py` завершились успешно. Для QA tooling закрыт supply-chain finding: Lighthouse зафиксирован на `12.6.1`, а `overrides.@puppeteer/browsers=3.2.1` исключает уязвимый `extract-zip`; после clean `npm ci` команда `npm audit` сообщила `0 vulnerabilities`, production-only audit также `0 vulnerabilities`. Тестовый API запускался с `APP_ENV=dev`, `DEV_MODE=1`, `CELERY_ENABLED=0` и disposable SQLite DB `/tmp/oracleai_qa.db`. Production credentials и пользовательские данные не использовались.

| Build item | Result | Evidence |
| --- | --- | --- |
| Fresh checkout | PASS | `git status --short --branch`, audited HEAD `3b8f578` |
| Python dependencies | PASS | `/tmp/oracleai_pip_install4.log` |
| Node dependencies | PASS | `/tmp/oracleai_npm_ci_override.log`; clean `npm audit`: 0 vulnerabilities |
| Frontend build | PASS | `/tmp/oracleai_frontend_build_baseline.log` |
| Runtime health | PASS | `GET /api/health`: `ok=true`, integrity `ok`, WAL, 49 tables |
| Docker/Compose clean stack | NOT RUN | Docker CLI/daemon отсутствует в sandbox |

## QA

### Automated and static validation

После frontend build полный тестовый набор дал **606 passed и 1 skipped**. `selfcheck`, `release_gate`, Ruff, `compileall`, repository hygiene, design contract, skill library, agent stability, Vedic routing и Mira/Lenormand smoke checks завершились успешно. Dependency audit сообщил `No known vulnerabilities found`.

### Browser and visual validation

На seeded synthetic user `10001` были проверены home, hub, четыре chat-состояния и четыре profile tabs. Axe-core дал **0 violations во всех 10 состояниях**. В каждом состоянии осталась одна `color-contrast` запись в `incomplete`, которую инструмент не смог автоматически подтвердить; это review item, а не violation. Lighthouse дал для всех состояний `accessibility=100`, `bestPractices=100`, `seo=100`, `runtimeError=null`; performance score составил 31–67 в clean remediated run и требует отдельного performance budget, но не является runtime failure.

### Domain and user journeys

API и seeded-browser evidence покрывают onboarding state, first value, chat, agents, tools, memory, Tarot, astrology, history, reports, shop, profile, localization и privacy contracts. Автоматизированные regression tests подтверждают owner scope, memory opt-in/off, append-only Tarot finalization, deletion/anonymization и webhook payload redaction.

Real Telegram Bot API, настоящие Telegram Mini App initData, mobile Telegram WebView, внешняя payment provider lifecycle и Docker Compose topology не могли быть выполнены в sandbox. Они отмечены в `FINAL_QA_MATRIX.md` как `NOT RUN` или `PARTIAL`.

## Security

### Authentication and authorization

Подпись Telegram initData проверяется через HMAC, auth date имеет возрастной и future-bound, duplicate fields отклоняются, oversized payload ограничен. В dev-only режиме bypass возможен только при явной dev-конфигурации; production config gate требует `APP_ENV=production`, выключенный `DEV_MODE`, HTTPS `WEBAPP_URL`, `BOT_TOKEN` и `ADMIN_ID`.

Owner-scoped routes и admin boundaries проверены regression tests и HTTP probes. Запрос без identity вернул `401`, неизвестный identity — `404`, запрос обычного пользователя к admin surface не раскрыл privileged data, а неверные Tarot/diary IDs вернули `404`.

### Privacy, memory and AI boundary

Memory отключена по умолчанию для новых пользователей, tool calls при `memory_enabled=0` не сохраняют и не возвращают факты, cache invalidation после удаления проверена. Списки памяти не возвращают embedding payload. Anonymization удаляет чувствительные rows, сбрасывает identity и псевдонимизирует финансовый trace; legacy raw webhook payload очищается.

Agent context и tool routing имеют отдельные regression tests. В доступном automated контуре не найдено доказательств, что пользовательские memory/context fields могут повысить привилегии или заменить system authority. Live provider-level prompt-injection E2E не запускался.

### Input, upload and error boundaries

Telegram markup escaping, malformed profile input, path traversal (`/..%2F.env`) и invalid resource IDs проверены. Palm response schema strict и закрывает `additionalProperties`. Полный adversarial upload corpus, decompression-bomb test и production reverse-proxy rate-limit test не запускались.

## Attack register

| Attack | Result | Severity | Fix / regression test |
| --- | --- | --- | --- |
| Missing authentication | `401` on `/api/me` | No finding | Covered by `tests/test_api.py` |
| Unknown identity | Safe `404` | No finding | Covered by API lifecycle tests |
| Duplicate Telegram initData fields | Rejected | No finding | `test_init_data_rejects_duplicate_fields` |
| Stale/future Telegram auth date | Rejected | No finding | `test_init_data_requires_fresh_auth_date` |
| Normal user → admin | No privileged response; safe `404` probe | No finding in tested surface | Admin authorization tests |
| Path traversal to `.env` | `404`, no file content | No finding | `test_path_traversal_is_blocked` |
| Invalid profile/XSS-like input | Controlled `400` | No finding | API validation and Telegram escaping tests |
| Tarot/diary resource ID substitution | Foreign/nonexistent access rejected | No finding | Owner-scope tests |
| Memory disabled bypass | Save/recall blocked and no data returned | No finding | `test_memory_tools_cannot_bypass_memory_off` |
| Memory deletion cache resurrection | Deleted memory not recalled | No finding | `test_recall_cache_is_invalidated_after_memory_delete` |
| Append-only Tarot overwrite | Foreign finalize and second finalize rejected | No finding | `test_tarot_finalization_is_owner_scoped_and_append_only` |
| Restricted safety/admin permissions | Support role cannot read or grant restricted data | No finding | `test_support_cannot_grant_or_read_restricted_safety` |
| Raw webhook privacy leak after anonymization | Payload cleared | No finding | `test_anonymize_clears_legacy_webhook_payload` |
| Payment provider/webhook forgery | Automated signature/idempotency contracts pass; live provider not available | Unverified externally | Requires real provider sandbox run |
| QA tooling supply chain (`extract-zip`) | Initial clean npm install reported 4 high vulnerabilities; remediation removed vulnerable transitive package | Fixed in candidate | Lighthouse `12.6.1` + `@puppeteer/browsers=3.2.1`; clean `npm audit=0` |
| Mobile/WebView-specific attacks | Not executed | Unverified externally | Requires representative Telegram WebView/device |
| Docker deployment boundary | Not executed because Docker unavailable | Release blocker | Run clean Compose build in CI/release environment |

## Scorecard

Оценки ниже отражают evidence, а не уверенность разработчика. Недоступные внешние поверхности не получают искусственный PASS.

| Area | Required | Evidence score | Assessment |
| --- | ---: | ---: | --- |
| Functional QA | 9/10 | 8/10 | Local API/browser paths pass; Telegram/payment/mobile external paths unavailable |
| Regression safety | 9/10 | 9/10 | Full suite green: 606 passed, 1 skipped |
| Security | 9.5/10 | 8.5/10 | Strong automated coverage; live upload/rate-limit/provider attacks incomplete |
| Authorization | 10/10 | 9/10 | Owner/admin tests pass; real deployment topology unverified |
| Data isolation | 10/10 | 9/10 | Owner and privacy tests pass; no multi-user production deployment run |
| Payment integrity | 10/10 | 7/10 | Contracts pass; provider/webhook/refund/reconciliation E2E not available |
| AI boundary security | 9.5/10 | 8/10 | Context/tool/memory tests pass; live LLM adversarial run unavailable |
| Reliability | 9/10 | 8/10 | Local health and tests pass; Compose workers and restart drill not run |
| E2E coverage | 9/10 | 7/10 | Seeded desktop browser matrix passes; mobile/Telegram/payment gaps remain |
| Release reproducibility | 9/10 | 7/10 | Clean Python/Node install passes; Docker clean install not possible |

## Release evidence

Создана актуальная матрица `docs/RELEASE/FINAL_QA_MATRIX.md`. Основные локальные evidence-файлы генерируются командами из этой матрицы и не содержат production PII. Доступные артефакты текущего запуска:

| Artifact | Purpose |
| --- | --- |
| `artifacts/lighthouse-axe-final/summary.json` | Axe matrix: 10 seeded states, zero violations |
| `artifacts/lighthouse-axe/summary.json` | Lighthouse + axe matrix, runtime errors and scores |
| `package.json`, `package-lock.json` | Lighthouse pin/puppeteer override; clean npm audit remediation |
| `miniapp/dist/manifest.json` | Hashed frontend asset manifest generated by build |
| `/tmp/oracleai_api.log` | Local API startup and probe evidence |

Rollback evidence в настоящем release environment не получена: Docker daemon, deployment target и production snapshot недоступны. До SHIP IT требуется выполнить clean build → install → migrate → run → test на release runner, а затем повторить critical user/admin/attack flows на candidate commit.

## Blockers

### BLOCKER 1 — Clean Docker release candidate не доказан

**Impact.** Невозможно подтвердить запуск полного service topology: PostgreSQL/pgvector, Redis, migrations, API, bot, Celery worker/Beat и Caddy.

**Evidence.** В sandbox команда `docker --version` завершилась `docker: command not found`; поэтому `infra/docker-compose.yml` и Dockerfile не прошли фактический build/run/migrate smoke.

**Why it matters.** Локальный SQLite API не эквивалентен release artifact с PostgreSQL, Redis, background workers и reverse proxy.

**Required action.** Запустить matrix на CI/release runner с Docker Compose v2, новой базой и пустыми volumes; сохранить `docker compose config`, migration logs, health output и restart/rollback evidence.

### BLOCKER 2 — Telegram, mobile WebView и payment lifecycle не сертифицированы

**Impact.** Нельзя подписать фактический путь `/start` → Mini App auth → notification/payment/provider webhook → entitlement.

**Evidence.** В окружении нет реального `BOT_TOKEN`, Telegram session, mobile WebView/device и payment provider sandbox credentials. Автоматизированные контракты проходят, но это не заменяет внешнюю E2E validation.

**Why it matters.** Критические trust boundaries зависят от внешних подписей, callback ordering, provider state и WebView behavior.

**Required action.** На изолированном staging провести real Telegram user journey, 375/390/430px WebView checks, provider purchase/webhook/refund/replay/race tests и сохранить redacted evidence.

## Final verdict

# BLOCKED

Критических уязвимостей, cross-user leak или unauthorized admin access в доступном automated/local контуре не обнаружено. Однако stop condition из задания требует доказать clean environment, clean database, migrations, full E2E, Telegram/payment boundaries и воспроизводимый release artifact. Docker clean stack, real Telegram/mobile WebView и real payment lifecycle не выполнены, поэтому текущий артефакт **не может быть сертифицирован как SHIP IT**.

После закрытия двух blockers необходимо повторить эту матрицу на release candidate, выполнить свежий QA critic и свежий security critic, а затем заменить verdict только при наличии воспроизводимых evidence.
