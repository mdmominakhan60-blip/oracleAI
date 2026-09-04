# План доведения OracleAI до production-ready состояния и массового запуска

## Document orientation

| Field | Definition |
|---|---|
| **Purpose** | Production readiness gates and release procedure. |
| **Source of truth** | `infra/`, `scripts/`, `docs/RELEASE/`. |
| **Scope** | Launch gates, evidence, operational prerequisites, rollback and current limitations. |
| **Do not change** | Do not announce public launch while a P0, legal, payment, provider or restore gate is open. |
| **Key files** | `docs/RELEASE/TASKS.md`, `docs/RELEASE/CURRENT_STATUS.md`, `scripts/release_gate.py`. |
| **Validation** | `python3 -m scripts.release_gate`. |


## Цель

Довести OracleAI — Telegram-бот и Mini App с четырьмя самостоятельными проводниками, расширенными астрологическими калькуляторами и palm-reading pipeline Миры — до безопасного, наблюдаемого и коммерчески готового состояния. Результатом должен стать повторяемый процесс запуска: от закрытой проверки на реальных устройствах до управляемого публичного трафика с понятными SLO, поддержкой, аналитикой, резервным копированием и планом отката.

План исходит из текущего состояния проекта: FastAPI, aiogram, PostgreSQL, Docker Compose, Caddy, backup service, Sentry/JSONL logging, серверная Telegram auth, opt-in memory, четыре агента, 19 calculator entries и отдельный vision/persistence контур Миры. Возрастная проверка (16+) удалена как продуктовая граница (GAUNTLET v2). Полный тестовый набор уже проходит, но массовая готовность требует закрыть не только кодовые задачи, но и риски эксплуатации, качества LLM, данных, устройств Telegram, поддержки и платежей.

## Стартовая оценка

| Область | Уже есть | Что следует подтвердить или доработать до public launch |
|---|---|---|
| Функциональность | Четыре агента, калькуляторы, Таро, дневник, Mini App, API и bot surfaces. | Реальный device QA всех критических путей, product documentation Миры, release regression matrix. |
| Palm vision | Валидация изображений, quality gates, safety sanitization, raw image не хранится, mocked E2E зелёный. | Надёжный live provider fallback, strict structured response, latency budget, manual quality benchmark на согласованном датасете. |
| Безопасность | Server-side auth/ownership, rate limits, memory privacy guard, CSP, webhook principles, backup guidance. | Внешний security review, секреты и доступы, legal review, verified restore drill, abuse/incident rehearsal. |
| Инфраструктура | Compose с bot/api/Caddy/backup, HTTPS runbook, healthcheck, Sentry, rollback notes. | Staging, CI/CD, production secrets, off-site backups, operational dashboard, capacity/load proof. |
| Масштабирование | PostgreSQL 16 + pgvector, pooled connections, Alembic migrations и single API worker — контролируемая стартовая конфигурация. | Измерить пределы; для роста подготовить distributed rate limiting, очередь задач и object-storage policy без хранения raw palm images. |
| Монетизация и рост | Платёжная модель и Paddle webhook safeguards описаны. | Sandbox-to-production payment certification, price/entitlement review, support/refund workflow, acquisition funnel и lifecycle messaging. |

> Главный принцип: выпускать не «всё сразу», а только после выполнения измеримых launch gates. Функция, для которой нет владельца, SLO, наблюдаемости и rollback-плана, не считается production-ready.

## Стратегия запуска: решение на Gate 0

До начала реализации владелец продукта выбирает один из двух маршрутов. Оба маршрута используют один и тот же security, LLM-quality и legal baseline; отличаются уровнем инфраструктурной подготовки и скоростью выхода.

| Подход | Что происходит | Компромиссы | Стоимость и сложность |
|---|---|---|---|
| **Контролируемая закрытая beta** | Ограниченный доступ по invite-list, лимиты на LLM и palm uploads, один production instance, ежедневный мониторинг и быстрый feedback loop. | Быстрее проверяет ценность и UX, но не доказывает готовность к резким рекламным всплескам. | Ниже начальные затраты и быстрее запуск; необходимы support-дежурство и ручной контроль. |
| **Подготовка к широкому публичному запуску** | Сначала staging, нагрузочные испытания, масштабируемая БД/кэш/очередь, provider fallback, observability и self-service support; затем публичный launch. | Меньше операционного риска при маркетинговом трафике, но больше срок и инженерная работа до первой кампании. | Выше стоимость и сложность, зато меньше риск потери данных, платежей или доверия при всплеске. |

План ниже построен так, чтобы первые четыре фазы были обязательны для обоих подходов. Решение о миграции на масштабируемую data plane принимается по результатам baseline load test и прогнозу трафика, а не по предположению.

## Фаза 0. Product, scope и governance

Сначала необходимо зафиксировать единственный source of truth для продукта. Следует обновить `docs/PRODUCT.md`, добавить Миру в таблицу проводников, описать palm-reading boundaries, объяснить различие между наблюдаемым признаком, символической интерпретацией и советом к саморазмышлению. Для всех 19 calculator entries нужно создать краткие карточки: необходимый ввод, точность результата, ограничения, sample response и owner.

Далее следует утвердить launch brief: целевая аудитория и страны, языки первой волны, допустимые acquisition channels, предполагаемый DAU/MAU, допустимый бюджет на LLM на активного пользователя, план монетизации, часы поддержки и владелец каждого критического направления. Отдельно нужно утвердить policy для Palm: допустимые фото, retention метаданных, запрет на диагностику и медицинские выводы, процедура удаления analysis data и формат обращений в поддержку.

| Артефакт | Критерий готовности | Владелец |
|---|---|---|
| Product requirements и backlog | Приоритизированы P0/P1/P2, каждое P0 имеет acceptance criteria и метрику. | Product owner |
| Обновлённая документация проводников | Мира, её инструменты, ограничения и UI находятся в продуктовой и пользовательской документации. | Product + content |
| Data map и retention schedule | Для Telegram ID, birth data, memory, diary, palm analysis, logs и платежей описаны цель, срок, доступ и удаление. | Product + security + legal |
| Launch decision | Выбран controlled beta либо public-scale route; зафиксированы целевой трафик и release owner. | Product owner |

## Фаза 1. Качество LLM и безопасность ответов

Vision pipeline Миры должен перейти от prompt-only JSON discipline к строгому provider contract: JSON Schema с `strict: true`, server-side schema validation, одна контролируемая повторная попытка на schema/quality failure и fallback на второй vision-capable provider. Выбор моделей следует делать по live catalog непосредственно перед deployment: для недорогих потоковых задач — быстрый model tier, для vision — multimodal provider с подтверждённой структурированной выдачей; параметры token budget должны соответствовать семейству модели. Отдельно следует сохранить уже добавленную GPT-5 compatibility проверку и распространить её на выбранные production providers.

Нужно создать versioned LLM evaluation suite. Он должен содержать согласованные и безопасно лицензированные примеры palm photo: хороший кадр, blur, низкое разрешение, частичная ладонь, два человека, не-ладонь, текст/prompt injection на изображении, разные ориентации и сложный свет. Для каждого примера фиксируются ожидаемые outcome class, quality threshold, hand detection, допустимые visibility labels, safety flags и expected next action. Никакие реальные пользовательские фото не включаются в dataset без явного отдельного согласия.

Для всех агентов нужно ввести red-team suite: кризис, здоровье, деньги, право, сексуализированный/возрастной контекст, coercion, «сними проклятие за оплату», jailbreak/prompt injection и cross-agent tool leakage. Ворота выпуска — отсутствие критических safety failures, 100% block/redirect на запрещённых сценариях и человеческий review пограничных ответов.

| Проверка | Gate | Действие при провале |
|---|---|---|
| JSON и enum contract Palm | Не менее 99% валидных структурированных ответов на approved eval set. | Fallback/retry, затем `needs_photo` без сохранения reading. |
| Vision latency | Утверждён p95 budget и timeout; пользователь получает progress и понятный fallback. | Автоматический provider switch или graceful retry state. |
| Safety red team | Ноль неотфильтрованных критических claims. | Блокировать релиз, править guardrails и добавлять regression case. |
| Tool isolation | Мира не может получить Tarot/Astro/Matrix tool ни в одном provider mode. | Блокировать релиз и расширять allow-list tests. |
| Human quality review | Независимая ручная оценка качества выборки ответов по rubric. | Изменить prompt, schema или provider routing. |

## Фаза 2. UX, Mobile QA и accessibility

Нужно провести реальное тестирование не только в sandbox browser, но и в Telegram на iOS, Android и Desktop. Матрица должна покрыть first launch, onboarding, смену RU/EN, memory on/off, все четыре агента, астрологические calculators, upload/preview/permission flow Миры, чат, ошибки сети, slow LLM, offline fallback, support/deletion, checkout и возврат из внешней оплаты.

Следует устранить product friction: сократить путь до первого полезного результата, объяснить, что Мира читает лишь видимые признаки, добавить доступный пример корректного фото, показать status upload/vision, сделать retry и delete очевидными. Для calculator explorer важны ясные термины и distinction между date-only и exact calculation. Необходимо завершить accessibility audit: контраст, крупные touch targets, keyboard navigation, screen-reader labels, reduced motion, Telegram safe areas и локализация без обрезания текста.

| Поверхность | P0 критерий | Метод проверки |
|---|---|---|
| Первое открытие | Пользователь понимает ценность и следующий шаг без обязательной даты рождения. | Moderated usability sessions + device QA. |
| Чат и проводники | Роль каждого агента ясна, UI не создаёт впечатления, что Мира — ветка Таро. | Task-based test и UI regression screenshots. |
| Palm scan | Фото можно выбрать/заменить, видны privacy note, progress, quality result и следующий шаг. | iOS/Android camera/gallery QA. |
| Ошибка LLM/сети | Нет пустого экрана, бесконечного spinner или потери draft. | Network throttling и forced provider failure. |
| Доступность | Основные flows доступны при touch/keyboard/screen reader и reduce motion. | Manual accessibility checklist + automated scan. |

## Фаза 3. Data, privacy, legal и trust

До внешнего трафика нужно завершить независимую юридическую проверку Privacy Policy, Terms, consent language, cookies/analytics, data deletion, cross-border data transfer, платёжных условий и refund process для стран первой волны. Этот пункт требует внешнего квалифицированного юриста; инженерная документация не заменяет правовое заключение.

На инженерном уровне следует реализовать и протестировать self-service data controls: экспорт сведений по запросу, deletion request flow с SLA, полное удаление связанных palm analysis и memory data согласно policy, support audit trail без раскрытия личных текстов. Необходимо зафиксировать retention для технических журналов, LLM usage, платежных событий, backup и deleted records. Следует провести privacy threat model: кто имеет доступ к базе, backup, Sentry, provider logs и admin panel; как этот доступ выдается, отзывается и проверяется.

| Gate | Доказательство готовности |
|---|---|
| Legal/compliance | Письменный review применимых документов и country-by-country launch scope. |
| Secrets | Production secrets созданы вне Git, rotation owner назначен, доступ по least privilege. |
| Privacy controls | Memory-off, export, deletion и ownership проверены в automated и manual flows. |
| Backups | Encrypted off-site backup, checksum и restore drill в изолированном контуре. |
| Incident response | Назначены роли, контакт-лист, severity matrix и проведено tabletop exercise. |

## Фаза 4. Инфраструктура, reliability и масштабирование

Нужно создать отдельные staging и production environments, которые никогда не используют production Telegram token, payments или реальную пользовательскую БД для тестирования. Каждый release должен собираться одним способом, получать immutable version/tag, проходить CI и деплоиться в staging до production. CI включает unit tests, API contract tests, static checks, migration test на чистой и заполненной базе, frontend asset validation, dependency/security scan и report artifact.

В текущем варианте PostgreSQL, pooled connections и один API worker разумны для ограниченной beta, но не являются доказанной конфигурацией для рекламного всплеска. Следует выполнить нагрузочные тесты с правдоподобными read/write/LLM-mix сценариями. Если при целевом p95 latency, queue length или pool-wait rate не достигаются SLO, следующая фаза — Redis-based distributed rate limit и очередь долгих vision/LLM jobs. Palm uploads обрабатываются асинхронно: API быстро создаёт job/status, worker выполняет provider call, клиент безопасно poll/получает обновление; raw image удаляется сразу после обработки согласно policy.

Для production нужна наблюдаемость по четырём уровням: infrastructure health, HTTP/API, business funnel и LLM/provider. В dashboard должны быть p50/p95/p99 latency, 4xx/5xx, DB lock/retry, queue depth, provider success/timeout/fallback rate, cost per successful outcome, palm quality distribution, payment conversion и support/deletion volume. Alerting должен иметь owner, threshold, runbook и test alert.

| Масштабный контур | Controlled beta baseline | Public-scale baseline |
|---|---|---|
| Database | PostgreSQL 16 + pgvector, Alembic, connection pooling, encrypted off-site backup и измеренный load ceiling. | PITR/replication evidence, capacity baseline и проверенный restore/forward-recovery plan. |
| Rate limiting | Текущие server-side limits с measured safe capacity. | Redis/distributed limits, per-user quota и abuse detection. |
| Long LLM/vision | Короткие timeout, fallback, quota и мониторинг; ограниченный доступ. | Queue worker, status/retry UX, idempotency key, provider routing and circuit breakers. |
| Observability | Sentry, JSONL, ops alerts, uptime checks, manual on-call. | Central dashboard, alert routing, SLO/error budget, runbooks и weekly ops review. |
| Deployment | Versioned Compose release with manual approval and verified backup. | Staging, CI/CD, canary or gradual rollout, feature flags and automated rollback. |

## Фаза 5. Платежи, поддержка и коммерческая готовность

До включения paid access необходимо пройти полный Paddle sandbox certification: создание transaction только на сервере, подпись raw webhook body, idempotent repeated delivery, binding to pending order, entitlement grant/revoke, cancellation, failed payment, refund и support reconciliation. Нельзя проводить реальные charge/refund операции до отдельного подтверждения владельца продукта.

Следует сформировать тарифную архитектуру, которая не завязана на страх или давление: бесплатная ценность должна быть законченной, premium limits прозрачны, а upgrade copy не обещает «спасение», снятие опасности или гарантированный исход. Для каждого paid capability необходимо определить unit economics: модель, average input/output tokens, success rate, provider cost, customer price, refund exposure и monthly budget guardrails.

Support readiness включает public help center/FAQ, in-app contact route, типовые ответы для privacy/deletion/payment/safety запросов, escalation path, response-time expectation и weekly review top issues. Контент-команда должна иметь редакционный календарь для ежедневных ритуалов, push-notifications, seasonal content и multilingual quality review.

## Фаза 6. Analytics, growth и controlled experiments

Нужно утвердить event taxonomy, запрещающую записывать в аналитику текст вопросов, дневников и анализов ладони. События должны измерять только технически необходимые шаги: acquisition source, bot start, age confirmation, onboarding step completion, selected guide, feature open, upload started/completed/failed, provider fallback, payment step, subscription status, retention and support contact. Каждое событие получает owner, purpose, retention и privacy review.

Воронка запуска должна быть инструментирована до первой рекламной кампании: landing → bot start → first value event → D1/D7 return → retained active user → optional conversion. Нужны cohort dashboards и qualitative feedback mechanism, а A/B experiments запускаются ограниченно, с pre-registered hypothesis, guardrail metric и automatic stop condition. Запрещается экспериментировать с safety wording, consent или crisis routing ради конверсии.

Growth plan строится из четырёх потоков: Telegram referral/share mechanics с privacy-safe assets, creator/community partnerships, ASO/landing SEO для discovery и retention communications, которые пользовательница явно включила. Перед масштабной платной рекламой необходимо показать, что retention, support load, LLM cost и failure rate укладываются в утверждённые пороги на beta cohort.

## Фаза 7. Release execution и launch gates

### Pre-production rehearsal

В staging нужно провести release rehearsal: deploy с нуля, migration, Telegram Mini App setup, healthcheck, четырёхагентный smoke test, LLM provider failure, payment sandbox webhook, backup, restore drill и rollback. Владелец релиза подписывает checklist только после сохранения evidence: dashboard screenshots, test logs, backup checksum, restore result, device QA matrix и signed security/legal approvals.

### Controlled beta

Если на Gate 0 выбран beta route, запуск выполняется invite waves с заранее определённым лимитом. Каждая волна открывается только при зелёных SLO предыдущей: error rate, p95 latency, provider success, zero security incidents, support queue and deletion requests within SLA, cost per active user within budget. Feature flags позволяют отдельно включать palm scan, payments и lifecycle notifications; выключение должно занимать минуты и не требовать новой сборки.

### Public launch

Публичный launch разрешается, только если две последовательные beta волны прошли без критических инцидентов, технические и доверительные метрики достигают порогов, а support/incident owners доступны. Публикация выполняется по runbook: release tag, backup confirmation, deploy, canary health, key-path smoke test, monitoring window, communication to partners and users. Первые 72 часа предусматривают повышенное наблюдение и ежедневный incident/cost review.

| Launch gate | Минимальное доказательство |
|---|---|
| Code quality | Полный CI, migrations, API contracts и device matrix зелёные. |
| LLM reliability | Утверждённая quality suite, fallback/circuit breaker, real provider success/latency within SLO. |
| Safety/trust | Red-team suite, crisis routing, privacy/consent/data deletion and legal review signed off. |
| Operations | Staging rehearsal, off-site encrypted backup and restore, alerting, runbooks and rollback tested. |
| Scale | Load test meets approved traffic profile; migration decision documented. |
| Commerce | Sandbox payment certification, support/refund process and cost guardrails approved. |
| Growth | Analytics funnel working without personal content leakage; beta retention/support/cost metrics pass. |

## План тестирования

| Уровень | Обязательные проверки |
|---|---|
| Unit и contract | Расчёты placements, palm normalization, safety filters, tool allow-list, authorization, rate limit, payment idempotency. |
| Integration | Real-image mocked vision pipeline, DB migrations, API CRUD, ownership, backup/restore, provider fallback with controlled fake clients. |
| LLM evaluation | Versioned prompt/model dataset, structured-output validation, safety red team, human scoring and regression diff. |
| E2E | Telegram Mini App on iOS/Android/Desktop; RU/EN; permissions; slow/offline/error states; checkout sandbox. |
| Security | Auth tampering, initData validation, IDOR, injection, CSP/XSS, secrets scan, admin access and webhook signature tests. |
| Performance | Read/write/LLM mix, burst rate limit, DB lock behaviour, long vision jobs, provider timeout and recovery. |
| Operational | Deploy/rollback, alert delivery, backup checksum, restore to isolated environment, incident tabletop. |
| Product | First-value usability, agent-role comprehension, Mира photo guidance, accessibility and support review. |

## Порядок приоритета

| Приоритет | Работа |
|---|---|
| **P0 — до любого внешнего трафика** | Production configuration, domain/TLS, staging, secrets, legal/privacy review, device QA, LLM safety/vision reliability, monitoring, encrypted off-site backup + restore drill, incident/rollback runbook. |
| **P1 — до публичного launch** | Load/capacity proof, payment sandbox certification, support operations, analytics funnel, product documentation including Мира, accessibility audit, beta cohort feedback loop. |
| **P2 — после доказанной beta value** | PostgreSQL/Redis/queue migration if metrics require it, advanced personalization, referral expansion, richer dashboards, growth automation and additional locales. |

## Ключевые риски и способы управления

| Риск | Почему важен | Управление |
|---|---|---|
| Vision provider timeout/invalid JSON | Palm is a differentiated feature; silent failure разрушает доверие. | Strict schema, provider fallback, circuit breaker, retry policy, queue/status UX and provider SLO. |
| PostgreSQL pool/lock pressure | Резкий рост одновременных действий может вызвать pool wait, lock contention или latency. | Load test, connection budget, lock/query metrics и documented capacity trigger. |
| LLM unsafe output | Темы здоровья, кризиса, денег и «судьбы» имеют высокий trust risk. | Red-team, safety filters, human review, crisis routing, immutable regression suite. |
| Privacy/compliance gap | Дневники, birth data и palm analysis чувствительны. | Legal review, data map, retention, deletion/export, access control and encrypted backups. |
| Telegram device variation | WebView и permissions различаются на iOS/Android/Desktop. | Real-device matrix, cache-busting control, fallback UI and staged rollout. |
| Payment inconsistency | Ошибка entitlement/refund быстро вызывает финансовые и репутационные последствия. | Webhook signature, idempotency, sandbox certification, audit and support process. |
| Acquisition spike без proof | Маркетинг может опередить capacity и support. | Invite waves, feature flags, cost/rate limits, canary launch and go/no-go gates. |

## Предпосылки и открытые решения

1. План предполагает, что первая публичная версия будет обслуживать русско- и англоязычных пользователей Telegram и сохранит позиционирование self-reflection, а не медицинского, юридического, финансового или психологического сервиса.
2. До Gate 0 нужно выбрать маршрут: controlled beta либо public-scale preparation. Оба маршрута используют PostgreSQL; различаются только уровнем доказанной capacity, distributed rate limiting и фоновой очереди.
3. До включения платежей требуется отдельное подтверждение владельца продукта и завершённая sandbox certification; данный план не предусматривает реальных платежных действий без такого подтверждения.
4. Правовые документы и трансграничная обработка данных требуют external legal review в странах запуска.
5. Точные SLO, quota и экономические пороги должны быть утверждены после baseline measurement текущего production-like environment, а не скопированы из development QA.

## Результат после выполнения плана

После прохождения всех P0/P1 gates OracleAI сможет выйти сначала в управляемую beta, а затем — в публичный launch с доказуемыми качеством LLM, устойчивостью инфраструктуры, контролем личных данных, корректной оплатой и готовой поддержкой. Масштабирование будет приниматься на основе наблюдаемых метрик, а не предположений, что позволит сохранить бережную продуктовую модель при росте аудитории.
