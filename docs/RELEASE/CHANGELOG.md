# OracleAI — changelog

Все заметные изменения пользовательского продукта, API и эксплуатационных контрактов фиксируются здесь. Временные аудиты и машинные snapshots в changelog не перечисляются как ссылки на файлы.

## Unreleased

### Added

- Аудит-волна Wave 0/Wave 1: интро-онбординг и чат-состояния восстановления локализованы RU/EN (FE-008/FE-009/CONT-008); у неотправленного ответа появилась кнопка «Повторить отправку» без потери черновика (FE-012); экран «открой бота» ведёт deep-link'ом в бота через новый неавторизованный `GET /api/public/config` (UX-009); `/help` в боте и серверные отказы 402/429/500 отвечают на языке клиентки (BOT-006, CONT-001/002); добавлены полные EN system/user промпты хиромантии с выбором по языку пользователя (AI-010); композер чата ограничен 1000 символами в соответствии с серверным контрактом (FE-014).
- Добавлены regression tests `tests/test_wave0_wave1_fixes.py` для DEV_MODE fail-closed, DEV_KEY gate, public config, билингвальных отказов и выбора palm-промптов.
- Вторая аудит-волна (Wave 1 остаток + Wave 2/3): роутинг агентов матчит однословные латинские термы только по чисто-латинским токенам и с префиксной морфологией — «planет» и «explanation» больше не дают ложных срабатываний, добавлены confusion-тесты (AI-002/TEST-002); proof-конверт ответа несёт provider/model последнего LLM-вызова (AI-001); порог релевантности памяти поднят 0.25 → 0.35 (AI-014); `/api/chat/{agent}/sessions` отдаётся страницами по 100 с `offset` (API-014); исход расклада Таро — закрытый enum `came_true|partly|no` (API-012); вопрос длиннее 1000 знаков — явная ошибка `QuestionTooLong` с понятным ответом бота вместо тихой обрезки (API-003); CRM-поиск экранирует `%`/`_` и переносимо сортирует по имени через `LOWER()` (DB-015/DB-003); миграция `0005_composite_indexes` закрывает full-scan в планировщике пушей и `MIN(day)` в чате (DB-018/API-013); `/metrics` при заданном `METRICS_TOKEN` требует Bearer на уровне приложения (SEC-015); Prometheus-гистограмма и счётчик получили лейбл нормализованного маршрута (API-006/OBS-005).
- Бот на двух языках: EN-скоуп `setMyCommands` (BOT-008), промокод-флоу (BOT-010/011/018), `/delete_me` принимает DELETE и говорит по-английски (BOT-007), голосовые и аварийная покупка вопроса локализованы (BOT-014/012); глобальный обработчик ошибок бота шлёт исключения в Sentry (BOT-020); удалены мёртвые `Onb.age`, `WELCOME_FALLBACK*`, `DATE_RE/TIME_RE/UNKNOWN_TIME` (BOT-004/005).
- Mini App: деструктивные подтверждения («удалить все чаты», «новый чат») переведены с системного `window.confirm` на фирменный модал `confirmAction` (FE-005/FE-007); добавлены дизайн-токены `--hover-bg`/`--hover-border`/`--focus-outline` и единый hover-отклик контролов на pointer-устройствах (FE-018); palm-чтение при `needs_photo` показывает конкретную инструкцию, какой ракурс дослать (DOM-002).
- ~~Возрастная проверка 16+ полностью удалена (GAUNTLET v2): server-side гейт `confirmed_age_user`, отказ младше 16 в боте и этап воронки `age_gate` убраны; колонки `users.age_confirmed` / `age_proof_hash` удалены миграцией `0006_drop_age_columns` (см. Removed ниже).~~
- Добавлены `UI_PIXEL_AUDIT.md` и geometry snapshots в visual baseline harness для измерения frame, header, cards, CTA и bottom navigation.
- Добавлены `18-pixel-reconstruction.css` для Mini App и `admin/pixel-reconstruction.css` для bounded desktop/mobile dashboard layout.
- Добавлены `PRODUCTION_GAUNTLET.md` и `PRODUCTION_FINAL_REVIEW.md` с полной phase matrix, локальными evidence и явными внешними release blockers.
- Добавлены `AI_ONBOARDING_GAUNTLET.md` и `AI_SYSTEM_FINAL_REVIEW.md` как evidence contracts для AI, onboarding, Telegram и admin release review.
- Добавлены regression tests для invalid-time, unknown-city и chart-failure recovery в Telegram onboarding.
- Добавлен runtime regression test на отказ от model-generated tool call вне allow-list текущего агента.
- Добавлены versioned JSON-контракты для natal, synastry, transit, composite и solar returns product paths.
- Добавлены owner-scoped маршруты `POST /api/synastry`, `POST /api/transits`, `POST /api/composite` и `POST /api/returns` с явными precision-gates.
- Mini App получил отдельные journeys «Полная синастрия», «Транзиты», «Композит пары» и «Солнечный возврат»; Astrologer agent получает deterministic evidence для всех путей.
- Реализованы circular midpoints для composite и bounded UTC ephemeris search с локальным timestamp для solar return; extended planets, houses, wheels and prediction semantics остаются отдельными gates.
- Репозиторий очищен от исторических audit snapshots, AI handoff-файлов, generated inventories и одноразовых research artifacts.
- Добавлены `FULL_PRODUCT_SURFACE.md`, `RELEASE/TASKS.md`, `EVIDENCE/BASELINE_2026-08-26.md`, `DOMAIN/CONTRACTS.md`, `AGENT_ARCHITECTURE.md`, `FEATURES/MEMORY.md`, `PDF_SYSTEM.md`, `TESTING.md`, `COMPETITOR_MATRIX.md` и `EVIDENCE/TRACEABILITY_MATRIX_2026-08-26.md` как рабочие контракты завершения.
- Добавлен owner-scoped `GET /api/history`: единый мета-архив отчётов, Tarot, palm readings и chat sessions с actionable deep links без выдачи содержимого личных записей.
- Список памяти теперь отдаёт только inspectable поля; embedding BLOB и имя embedding-модели остаются внутренними. Recall-cache сбрасывается после ручного/AI сохранения, усиления и удаления факта.
- Tarot finalization повторно проверяет владельца и не позволяет перезаписать уже сохранённую интерпретацию; malformed upload size headers для palm получают явный 400.
- Добавлен формальный `tarot-replay-v1`: ledger восстанавливается из сохранённых карт, позиций и ориентаций, а checksum защищает исторический payload от незаметного изменения.
- Добавлен `scripts.pdf_matrix` для локального PDF preflight: 6 детерминированных RU/EN exact/date-only, long-field и edge-latitude кейсов с внешними HTML/PDF артефактами и `summary.json`.
- Добавлен privacy-safe `product_cost_events` ledger: server-owned SKU/catalog/channel/purpose dimensions, LLM retry/latency/token cost, delivery/refund/support categories, retention и product KPI aggregation; gross Stars не объявляются net revenue или contribution.
- Product-cost gross booking теперь присоединяется по `sku + order.surface/channel`, поэтому одинаковый SKU не дублируется между bot и Mini App rows; добавлен regression test.
- Добавлен воспроизводимый `scripts/domain_qa.py` и `DOMAIN/ACCURACY_MATRIX.md`: 8/8 критических cross-implementation кейсов проходят, включая date-only и fail-closed ambiguous DST; external ephemeris authority comparison остаётся открытым.
- Добавлен `RELEASE/P0_PRODUCTION_EXECUTION_PLAN.md` с owner-led процедурами, acceptance evidence, go/no-go gate, redaction policy и rollback для Telegram auth, payments, live LLM и backup/restore.
- P0-004 получил отдельный backup image, S3-compatible off-site uploader для encrypted dump и checksum, backup status marker, explicit host storage path, isolated restore target guard, ops freshness alerts, Makefile targets и CI static/drill gate.
- Lighthouse обновлён до `13.4.1`, Node CI/frontend-builder — до `22.19.0`; `npm audit` теперь проходит без advisory, а оба frontend CI job выполняют audit gate.


### Changed

- Полная exact natal карта сохранена как canonical path: 10 традиционных планет, 12 домов, ASC/MC, Rahu/Ketu, Lilith, Chiron/Juno/Ceres/Vesta/Pallas, мажорные аспекты и precision-aware ограничения.
- Натальный визуал остаётся в Mode P: серверный Kerykeion → transient SVG → raster PNG/WebP; raw SVG не покидает серверный render pipeline.
- Документация сокращена до текущих product, architecture, API, design, security, deployment, agent, chart-contract и launch-governance источников правды.

### Security

- BUS-90: DEV_MODE=1 с пустым `DEV_KEY` роняет любой процесс при импорте `app.config` (fail-closed) — раньше пустой ключ отключал проверку `X-Dev-Key` целиком, и `?dev_user=<id>` входил в API без всякого заголовка. Protection-in-depth в `deps._dev_identity_allowed` закрывает вход и при подмене настроек в рантайме; QA/load-скрипты и Mini App/admin передают заголовок при dev-входе.
- SEC-001: недопустимая комбинация DEV_MODE=1 с APP_ENV вне dev|test роняет любой процесс при импорте `app.config` (fail-closed до первого запроса); при заданном `DEV_KEY` вход по `?dev_user=<id>` дополнительно требует заголовок `X-Dev-Key`.
- SEC-002: CSP `frame-ancestors` разрешает встраивание Mini App в веб-клиенты Telegram (`web/k/z/a.web.telegram.org`, `telegram.org`) — прежний `'self'`-only формально запрещал Telegram Web/Desktop embedding.
- DB-005: модульный синглтон `_db` в `app/api/deps.py` удалён; пул БД создаётся lifespan'ом и выдаётся запросам из `app.state` через request-scoped зависимость.
- CRM tag mutations в admin API теперь записываются в `admin_audit`; production startup/release gate блокируют шаблонные PostgreSQL credentials, неполную DB/Redis конфигурацию и отсутствующий release identity; operational logs больше не интерполируют Telegram IDs, invoice payloads, charge IDs или сырые provider errors в проверенных путях.
- Синастрия использует только owner-scoped `partner_id`; birth data не принимаются через GET URL и не появляются в публичных cache keys.
- Unknown-time natal charts не получают выдуманные дома, ASC, MC или колесо.
- Transit day snapshots явно маркируются как дневные и не выдаются за точный момент Луны.
- Отчёты переведены на append-only history: `?refresh=true` создаёт новую версию и сохраняет deterministic source/evidence limitations, не удаляя предыдущую.
- Repository hygiene больше не ошибочно блокирует активную `EVIDENCE/TRACEABILITY_MATRIX_2026-08-26.md`; проверка отделяет рабочие контракты от одноразовых audit dumps.
- Добавлена owner-scoped unified history для reports, Tarot, chat sessions и diary с exact routes, `source_id`, безопасным preview и palm boundary; profile History tab получил keyboard-visible cards.
- Live LLM evaluation получил catalog discovery, stratified synthetic run, cost cap, safety/language/calibration/latency gates и provider-correct GPT-5 reasoning effort через `LLM_REASONING_EFFORT`.
- English home fallback переведён в HOME_I18N; добавлены localization regression, Playwright visual/accessibility baseline и финальные per-check quality-gate artifacts.
- Добавлены `ARCHIVE/NEXT_STEPS_2026-08-26.md`, `FEATURES/HISTORY.md` и `EVIDENCE/ORACLEAI_CONTINUATION_REPORT_2026-08-26.md`; второй pass фиксирует выполненные локальные рекомендации, внешние launch blockers и незелёный LLM p95 latency gate.
- Подготовлен research-only документ `MONETIZATION_STRATEGY.md`: Hybrid B, публичные pricing anchors, unit economics, ethical upsell guardrails и owner decisions; код, UI, цены и payment logic на этом этапе не изменялись.
- Добавлены synthetic memory evaluator, API resilience matrix, PDF golden-case runner, Tarot contract tests, disposable backup/restore drill and directional chart/Tarot/memory/PDF performance benchmark.
- Account deletion получил confirm-gated idempotent API contract; anonymization clears user history and disables memory and push. Memory recall cache now respects requested result limits.
- Playwright visual baseline расширен до chart/history/memory/Tarot states, reduced-motion reference and seeded synthetic data; localized accessible names added for the previously failing inputs and tool controls.
- Agent prompt/context hardening централизовал untrusted wrappers для memory, profile summaries, diary и evidence blocks; runtime теперь дополнительно отклоняет forbidden model tool calls по server-side agent allow-list; добавлен deterministic consistency gate против взаимоисключающих start/stop directives, а pre-tool fallback теперь intent-gated для chart/transit calls.
- Telegram onboarding больше не принимает произвольную невалидную строку времени как «время неизвестно»; неизвестный город и сбой расчёта карты оставляют FSM на retryable city state с локализованным объяснением.
- Mira получил topic-aware reshoot guidance, explicit `reading_id` retrieval и optional integrity-checked ONNX line evidence helper с vendored MIT model variants; raw masks не сохраняются, hard precheck skips heavy CV, а LLM остаётся авторитетом для видимого изображения и uncertainty.
- Последний bounded live synthetic LLM run: 12/12 cases, 0 critical violations, mean 0.9167, language 1.0, next-step 1.0, calibration 0.8; p95 25.088 s против цели 15 s остаётся staging blocker. Palm-line CPU baseline: fp16 около 8.35 s p50, int8 остаётся отдельным quality tradeoff.
- Добавлен явный authenticated boot recovery state: Mini App больше не показывает полноценный home shell после неуспешного `/api/me`, а предлагает повторить вход внутри Telegram.
- Account deletion теперь доступен из Profile Summary через локализованный confirm-gated UI, вызывает существующий idempotent `/api/account/delete` и показывает terminal success state без повторного запроса данных удалённого профиля.
- Standalone agent/skill benchmark scripts получили repository-root bootstrap; direct invocation добавлен в CI как regression contract.
- Selfcheck limits path проверяет платный chat flow через account status; design contract checker учитывает visual и payments CSS layers, а VISUAL QA больше не ссылается на отсутствующие generated artifacts.
- Pixel reconstruction pass нормализует content frame, section rhythm, card families, 48px controls, safe-area/nav clearance и wide-screen bounds; Admin Dashboard получил responsive stacking, 44px controls и явные `aria-label` для dynamic form fields.

## 2.0.0 — 2026-08-12

### Added

- Ежедневный микро-ритуал, age-gate 16+, RU/EN Mini App, opt-in memory, дневник, Tarot, Matrix, palm evidence flow, аналитика и controlled-beta documentation.

### Changed

- Mini App перестроен вокруг чата с отдельными проводниками, explicit tool actions, accessibility states и responsive dark visual system.

### Security

- Server-side privacy and memory-off boundaries, safety routing and high-stakes disclaimers стали частью общего runtime-контракта.

## Release policy

Перед каждым release необходимо обновить этот файл, соответствующие canonical docs и тесты. Public launch не считается готовым только на основании локальных тестов: остаются внешние проверки production deployment, real Telegram devices, live LLM/provider quality, privacy/legal review, payments и Kerykeion/Swiss Ephemeris licensing.
