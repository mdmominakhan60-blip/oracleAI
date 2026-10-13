# OracleAI — Ориентация для не-программиста

> Этот файл — твоя карта. Здесь описан весь проект простым языком: что есть, где лежит, как работает, зачем нужно.

---

## 1. Что такое OracleAI

**Telegram-бот + Mini App** (приложение внутри Telegram) для осмысленной саморефлексии.

- Астрология (натальная карта, транзиты, совместимость, ведика)
- Таро и Ленорман (расклады, интерпретация)
- Хиромантия (анализ ладони по фото)
- Дневник, практики, стрики
- Память (Oracle помнит людей, события, прошлые разговоры)
- AI-чат (единый проводник, который сам решает какой инструмент применить)

**Возраст:** 16+. Продукт **не** заменяет психолога, врача или юриста.

---

## 2. Полный инвентарь каталогов

```
oracleAI/
│
├── app/                    ← «Мозг» проекта (Python)
│   ├── api/               ← 22 роутера (эндпоинты HTTP API)
│   │   ├── routers/       ← каждый файл = одна область (chat, tarot, profile, admin, ...)
│   │   ├── contracts/     ← форматы ответов (JSON-схемы)
│   │   ├── deps.py        ← авторизация, лимиты, scope
│   │   ├── security.py    ← проверка Telegram initData (HMAC)
│   │   └── main.py        ← точка входа FastAPI
│   │
│   ├── agents/            ← 4 персоны-агента (YAML + Markdown + skills)
│   │   ├── lilith/        ← Лилит (общий Oracle, дневник, рефлексия)
│   │   ├── urania/        ← Урания (астрология, натальная карта, ведика)
│   │   ├── lenormand/     ← Мадам Ленорман (Таро, Ленорман)
│   │   └── mira/          ← Мира (хиромантия, фото ладони)
│   │
│   ├── bot/              ← Telegram-бот (aiogram)
│   │   ├── main.py        ← запуск бота
│   │   ├── chat.py        ← обработка сообщений
│   │   ├── onboarding.py ← первый вход (дата рождения, имя)
│   │   ├── features.py   ← команды (карта, таро, практики)
│   │   ├── keyboards.py  ← меню (кнопки)
│   │   ├── growth.py     ← CRM, рассылки, воронки
│   │   ├── palm.py       ← загрузка фото ладони
│   │   └── shop.py       ← подписка, оплата
│   │
│   ├── core/             ← Ядро: расчёты + IИ + безопасность
│   │   ├── astro.py      ← натальная карта (Kerykeion + Swiss Ephemeris)
│   │   ├── vedic.py      ← ведическая астрология
│   │   ├── tarot.py      ← колода Таро + Ленорман (78+78 карт)
│   │   ├── matrix.py     ← Матрица Судьбы (нумерология)
│   │   ├── chart_*.py    ← контракты карт (natal, synastry, transit, composite, returns)
│   │   ├── palm/         ← хиромантия (MediaPipe + ONNX + OpenCV)
│   │   ├── llm.py        ← вызов IИ (Anthropic, OpenAI, Ollama — цепочка)
│   │   ├── safety.py     ← кризисный протокол (самоубийство, суицид → код, не промпт)
│   │   ├── memory.py     ← память (что Oracle помнит)
│   │   ├── shared_context.py ← общий контекст (транзиты, рекомендации)
│   │   ├── tool_registry.py  ← 33 инструмента (какие функции может вызвать агент)
│   │   ├── agents/       ← роутер, runtime, registry, context, routing
│   │   ├── scenarios/    ← сценарии (прогноз, таро, совместимость, отчёт)
│   │   ├── personas.py   ← 3 стиля общения (friend / witch / mentor)
│   │   ├── interpretation.py  ← проверка ответов IИ (нет выдумок)
│   │   └── product_cost.py    ← учёт стоимости IИ (до $2.5/мес на пользователя)
│   │
│   ├── repo/             ← Склад (18 модулей, доступ к БД)
│   │   ├── users.py      ← профили
│   │   ├── dialog.py     ← сообщения чатов
│   │   ├── billing.py    ← подписки, кредиты
│   │   ├── crm.py       ← сегменты, воронки
│   │   ├── analytics.py  ← события
│   │   ├── content.py    ← настраиваемый контент (админка)
│   │   └── ...           ← feedback, growth, notifications, palm, readings
│   │
│   ├── services/         ← Повара (24 модуля, бизнес-логика)
│   │   ├── chat.py       ← оркестрация чата (роутинг → контекст → IИ → проверка)
│   │   ├── billing.py    ← подписки, кредиты, refund
│   │   ├── payment_monitor.py ← мониторинг платежей
│   │   ├── broadcast.py  ← рассылки
│   │   ├── scheduler.py  ← тики (ежедневные задачи)
│   │   ├── limits.py     ← лимиты вопросов
│   │   ├── eligibility.py← кто может что
│   │   └── ...           ← referrals, horoscopes, practices, telegram
│   │
│   ├── pdfgen/           ← PDF-отчёты (натальная карта, таро)
│   ├── tasks/            ← Celery (фоновые задачи)
│   ├── queue.py          ← конфигурация Celery
│   └── config.py         ← все настройки (env vars)
│
├── miniapp/             ← ТЕКУЩИЙ фронтенд (vanilla JS)
│   ├── index.html        ← точка входа (загружает 25 JS + 1 CSS)
│   ├── js/              ← 25 модулей (00-runtime → 21-r06-s14)
│   ├── css/             ← 34 CSS-модуля (00-tokens → 27-observatory)
│   ├── styles.css       ← агрегатор (импортирует все CSS)
│   ├── img/             ← 175 картинок (Таро, Ленорман, аватарки, фоны)
│   ├── fonts/           ← 10 шрифтов (Manrope, Cinzel, PJS)
│   └── dist/            ← собранный бандл (gitignored, build)
│
├── frontend-v2/         ← НОВЫЙ фронтенд (React + Vite + TypeScript)
│   ├── src/             ← 39 файлов (routes, components, hooks, api, i18n)
│   ├── index.html       ← Vite entry
│   ├── vite.config.ts   ← сборка
│   └── tsconfig.json    ← TS конфигурация
│
├── admin/               ← Админ-панель (отдельный HTML/JS)
│   ├── index.html       ← точка входа
│   ├── src/app.js       ← регистрирует 14 фичей
│   ├── src/features/    ← analytics, audience, cohorts, commerce, content,
│   │                      dashboard, engagement, feedback, logs, observability,
│   │                      settings, users, attention-queue, churn-cards
│   ├── src/core/        ← runtime, api
│   └── styles/          ← 5 CSS-файлов
│
├── alembic/             ← Миграции БД (15 файлов)
│   ├── versions/        ← 0001_pg_baseline → 0015_precision_approx_canon
│   └── schema/baseline.sql
│
├── infra/               ← Инфраструктура (Docker, мониторинг, деплой)
│   ├── Dockerfile       ← как собирается образ
│   ├── docker-compose.yml  ← Postgres + Redis + Caddy + API + Bot + Worker + Beat
│   ├── Caddyfile        ← TLS + reverse proxy
│   ├── observability/   ← Prometheus, Grafana, Loki, Alertmanager
│   ├── staging/         ← staging-стенд (отдельный deploy, бэкапы)
│   ├── systemd/         ← сервисы VPS
│   └── backup-postgres.sh ← ежедневные зашифрованные бэкапы
│
├── data/                ← Тестовые данные (fixtures)
│   ├── llm_eval/        ← golden cases для оценки IИ
│   └── palm_golden/     ← реестр рецензентов + схемы для хиромантии
│
├── models/              ← CV-модели (хиромантия)
│   ├── hand_landmarker.task  ← MediaPipe (определение линий руки)
│   ├── palm_line_student_fp16.onnx  ← ONNX (детекция линий)
│   ├── palm_line_student_int8.onnx
│   └── THIRD_PARTY_NOTICES.md
│
├── scripts/             ← 66 Python + 5 JS (QA, build, проверки)
│   ├── selfcheck.py     ← "всё ли живое?" (запускает smoke-тесты)
│   ├── release_gate.py  ← production-проверки
│   ├── build_frontend.mjs ← сборка miniapp (esbuild)
│   ├── run_axe_core.mjs   ← accessibility-аудит
│   └── ...              ← benchmarks, visual QA, domain QA
│
├── tests/               ← 116 тестовых файлов (pytest)
│   ├── test_api.py      ← API-контракты
│   ├── test_core.py     ← расчёты (астрология, таро, матрица)
│   ├── test_safety.py   ← кризисный протокол
│   ├── test_billing.py  ← платежи
│   ├── test_miniapp_actions.py ← UI-контракты
│   └── ...
│
├── docs/product-v2/     ← 10 спецификаций v2 (единственная документация)
│   ├── PRODUCT_BRIEF.md     ← что делаем и почему
│   ├── UX_FLOWS.md          ← сценарии пользователя
│   ├── SCREEN_SPEC.md       ← 15 экранов
│   ├── DESIGN_SYSTEM.md     ← токены, компоненты
│   ├── ARCHITECTURE.md      ← IИ-путь, память, риски
│   ├── API_CONTRACTS.md     ← 13 новых endpoint'ов
│   ├── REUSE_MAP.md         ← что берём со старого
│   ├── MIGRATION_PLAN.md    ← 6 этапов
│   ├── ACCEPTANCE_CRITERIA.md ← проверяемые условия
│   └── TEST_PLAN.md         ← что тестировать
│
├── Makefile             ← команды (make up, make test, make selfcheck)
├── requirements.txt     ← Python-зависимости (FastAPI, aiogram, kerykeion, ...)
├── package.json         ← Node-зависимости (esbuild, axe, lighthouse)
├── pytest.ini           ← конфиг тестов
├── ruff.toml           ← линтер Python
├── .github/            ← GitHub Actions (CI)
├── .gitlab-ci.yml       ← GitLab CI (mirror)
└── README.md            ← короткая заглушка
```

---

## 3. Как устроен запрос (от пользователя до ответа)

```
Пользователь пишет: "Что скажут карты про мой Сатурн?"
    │
    ▼
┌─────────────────────────────────────────────────┐
│  miniapp/js/07-chat.js  или  app/bot/chat.py   │  ← транспорт
└─────────────────────────────────────────────────┘
    │  POST /api/chat/oracle
    ▼
┌─────────────────────────────────────────────────┐
│  app/api/routers/chat.py                       │  ← роутер
│  - проверяет авторизацию (initData / dev_user)  │
│  - проверяет лимиты                              │
└─────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────┐
│  app/services/chat.py                          │  ← оркестратор
│  - роутинг: "карты + Сатурн" → tarot + astro   │
│  - сборка контекста: натальная карта, память    │
│  - выбор инструментов: get_chart + draw_tarot   │
│  - вызов IИ через app/core/llm.py              │
└─────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────┐
│  app/core/agents/runtime.py                    │  ← runtime агента
│  - system prompt (персона + правила)            │
│  - bounded history (последние 20 сообщений)     │
│  - натальный JSON (планеты, знаки, аспекты)     │
│  - shared context (текущие транзиты)            │
│  - память (если включена)                       │
│  - tool-use цикл (IИ вызывает инструменты)      │
└─────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────┐
│  app/core/llm.py                               │  ← IИ
│  - цепочка: Anthropic → OpenAI → Ollama        │
│  - timeout 35с, 2 ретрая, rate limit           │
│  - учёт стоимости (llm_usage)                   │
└─────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────┐
│  app/core/interpretation.py                    │  ← проверка
│  - нет ли "у тебя рак" / "ты разведёшься"      │
│  - нет ли выдуманных карт / положений           │
│  - нет ли гарантий                              │
└─────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────┐
│  Ответ возвращается в miniapp или бот          │
│  - показывает расклад (картинки)                │
│  - показывает интерпретацию                     │
│  - сохраняет в messages                         │
└─────────────────────────────────────────────────┘
```

---

## 4. Четыре агента (персоны)

| Агент | Роль | Что умеет | Файл |
|---|---|---|---|
| **Лилит** | Общий Oracle | Чат, дневник, рефлексия, память, практики | `app/agents/lilith/` |
| **Урания** | Астролог | Натальная карта, транзиты, совместимость, ведика | `app/agents/urania/` |
| **Ленорман** | Таролог | Расклады Таро (78 карт), Ленорман (78 карт) | `app/agents/lenormand/` |
| **Мира** | Хиромант | Анализ ладони (фото → линии → интерпретация) | `app/agents/mira/` |

**В v2:** пользователь больше не выбирает персона. Пишет вопрос → система сама решает, кто отвечает.

---

## 5. База данных (PostgreSQL + pgvector)

| Таблица | Что хранит |
|---|---|
| `users` | Профиль (TG ID, имя, дата рождения, подписка, лимиты) |
| `messages` | История чатов (треды, агент, текст) |
| `memories` | Память (факты, люди, события + embedding для поиска) |
| `partners` | Люди из жизни пользователя |
| `readings` | Сохранённые расклады Таро |
| `orders` | Платежи |
| `subscriptions` | Подписки |
| `analytics_events` | События (для аналитики) |
| `llm_usage` | Токены, стоимость, латентность IИ |
| `content_items` | Настраиваемый контент (админка) |
| `task_jobs` | Фоновые задачи (Celery) |
| `shared_context_events` | Рекомендации агентов (общий контекст) |
| `shared_context_snapshots` | Дневной snapshot транзитов |

---

## 6. IИ — как работает (простым языком)

**Принцип:** IИ **не считает**. Код считает. IИ только **рассказывает** результат красивыми словами.

```
Астрологические положения → код (Kerykeion + Swiss Ephemeris)
Карты Таро → код (детерминированный алгоритм)
Линии ладони → код (MediaPipe + ONNX)
    ↓
IИ получает JSON с результатами + правила
    ↓
IИ формулирует ответ (2-3 абзаца, тёплый тон)
    ↓
Код проверяет: нет ли выдумок, диагнозов, гарантий
```

**Провайдеры (цепочка):**
1. Anthropic (Claude) — основной
2. OpenAI (GPT) — резерв
3. Ollama / vLLM (локальная) — офлайн-режим
4. Офлайн-фолбэк — шаблонный ответ без IИ (карты настоящие, текст шаблонный)

---

## 7. Безопасность (что защищает пользователя)

| Угроза | Защита | Где |
|---|---|---|
| Подделка initData | HMAC-проверка | `app/api/security.py` |
| Replay атаки | Sesson token + timestamp | `app/api/deps.py` |
| Чужие данные | Owner-scope (WHERE tg_id = ...) | все `repo/` |
| Суицид / кризис | Кризисный протокол (код, не IИ) | `app/core/safety.py` |
| Выдумки IИ | Post-check (нет диагнозов, гарантий) | `app/core/interpretation.py` |
| Утечка PII | Log redaction | `app/core/observability.py` |
| Лимиты / DDoS | Rate limit + concurrency | `app/core/llm.py` |
| Платежи | Идемпотентность, webhooks | `app/services/billing.py` |
| Удаление аккаунта | Полная анонимизация | `app/repo/users.py` |

---

## 8. Монетизация

| Механизм | Описание |
|---|---|
| **Бесплатный** | 5 вопросов/день, базовая память |
| **Подписка** (Stars) | Безлимит, полная память, PDF-отчёты |
| **Кристаллы** (crystals) | Оверлей (доп. пакеты вопросов) |
| **Vouchers** | Промокоды |
| **Referrals** | Пригласи подругу → получи кредиты |
| **Платёжный провайдер** | Paddle (внешний) |
| **Мониторинг** | `payment_monitor.py` — алерты при сбоях |

---

## 9. Инфраструктура (как работает в проде)

```
Пользователь → Telegram → Caddy (TLS) → FastAPI (uvicorn)
                                        → PostgreSQL (pgvector)
                                        → Redis (очереди)
                                        → Celery Worker (фоновые задачи)
                                        → Celery Beat (тики)
                                        → Ollama (опционально, локальный IИ)

Мониторинг:
Prometheus ← API + Worker + cAdvisor + node-exporter
Grafana     ← дашборды
Loki        ← логи
Alertmanager ← алерты (Telegram)

Бэкапы:
Ежедневно: encrypted PostgreSQL dump → локально + offsite (S3)
```

---

## 10. Два фронтенда (сравнение)

| | `miniapp/` (старый) | `frontend-v2/` (новый) |
|---|---|---|
| Технология | Vanilla JS (без бандлера) | React + Vite + TypeScript |
| Структура | 25 JS-файлов, нумерованные | 39 TSX/TS, компоненты + хуки |
| Навигация | Единая страница + табы | 4 вкладки (Home, Oracle, People, Me) |
| Агенты | Выбор из 4 персон | Единый Oracle (скрытый роутинг) |
| Состояние | `00-runtime.js` (global) | React hooks |
| API | Фетч через `02-api.js` | Типизированный `src/api/client.ts` |
| Статус | **Работает в проде** | В разработке (ветка `redesign/oracle-v2`) |

---

## 11. Команды (что можно запустить)

| Команда | Что делает |
|---|---|
| `make up` | Поднимает весь стек (Docker: Postgres, API, Bot, Worker, Caddy) |
| `make test` | Запускает 116 тестов (нужен PostgreSQL) |
| `make selfcheck` | Быстрая проверка "всё ли живое?" |
| `make ps` | Показывает статус контейнеров |
| `make logs` | Лог API, Bot, Worker, Postgres, Caddy |
| `make migrate` | Применяет миграции БД |
| `make backup` | Делает зашифрованный бэкап |
| `make restore BACKUP=...` | Восстанавливает из бэкапа |
| `make up-local-llm` | Поднимает Ollama (локальный IИ) |
| `python3 -m scripts.selfcheck` | Быстрый smoke-тест без Docker |
| `python3 -m scripts.release_gate` | Production-проверки |
| `python3 scripts/check_documentation_links.py` | Ссылки в docs/product-v2 |
| `python3 scripts/check_repository_hygiene.py` | Чистота репозитория |

---

## 12. Шпаргалка "Где искать"

| Нужно понять... | Иди в... |
|---|---|
| Идея продукта | `docs/product-v2/PRODUCT_BRIEF.md` |
| Как выглядит UI сейчас | `miniapp/index.html` → `miniapp/js/` |
| Будущий UI | `frontend-v2/src/routes/` |
| Астрология (расчёты) | `app/core/astro.py` |
| Ведическая астрология | `app/core/vedic.py` |
| Таро / Ленорман | `app/core/tarot.py` |
| Хиромантия | `app/core/palm/` + `models/` |
| Mатрица Судьбы | `app/core/matrix.py` |
| Память | `app/core/memory.py` + `shared_context.py` |
| Роутинг (кто отвечает) | `app/core/agents/routing.py` |
| IИ (вызов LLM) | `app/core/llm.py` |
| Безопасность / кризисы | `app/core/safety.py` |
| Платежи | `app/services/billing.py` + `paddle.py` |
| Telegram-бот | `app/bot/main.py` + `chat.py` |
| Админка | `admin/` + `app/api/routers/admin.py` |
| Деплой | `infra/` + `Makefile` |
| Миграции БД | `alembic/versions/` |
| Тесты | `tests/` |
| Мониторинг | `infra/observability/` |
| Локальный IИ (Ollama) | `make up-local-llm` |

---

## 13. Что именно сейчас строится (v2)

**Главное изменение:** вместо 4 персон → **один Oracle**.

- Пользователь не выбирает "к кому идти"
- Пишет обычный вопрос → система сама решает какой домен (таро, астрология, память, люди)
- 4 вкладки: **Home** (сводка), **Oracle** (чат), **People** (люди), **Me** (профиль)
- Таро и карта — визуальные сцены внутри чата, **не** отдельные вкладки
- Граф памяти: люди ↔ события ↔ чтения ↔ факты (13 новых endpoint'ов)
- Migration `0016`: 2 новые таблицы (memory_links, people_events)

**6 этапов (MIGRATION_PLAN.md):**
1. Фундамент Vite + React + TS (frontend-v2)
2. Сквозной чат (API-подключение)
3. Подключение сборки ( hashed bundles)
4. Маршрутизация (hash-роуты)
5. Единый Oracle (скрытый роутинг доменов)
6. Граф памяти (13 endpoint'ов + миграция)

---

## 14. Ключевые принципы (не нарушать)

1. **IИ не считает.** Код считает, IИ рассказывает.
2. **Нет гарантий, диагнозов, предсказаний.** Только рефлексия.
3. **Кризисный протокол — код, не промпт.** Если пользователь в опасности → код переключает, IИ не вызывается.
4. **Owner-scope.** Каждый запрос — только свои данные.
5. **Память opt-in.** Без согласия пользователя — данные не в промпт.
6. **Offline-fallback.** Если IИ недоступен — шаблонный ответ с реальными картами.
7. **Не ломать старый фронт.** `miniapp/` работает до замены.

---

## 15. Размер и масштаб

| Метрика | Значение |
|---|---|
| Python-модулей в `app/` | 170 |
| Тестовых файлов | 116 |
| Скриптов (Python + JS + Shell) | 71 |
| Миграций БД | 15 |
| API-роутеров | 22 |
| JS-файлов miniapp | 25 |
| CSS-файлов miniapp | 34 |
| Изображений | 175 |
| Шрифтов | 10 |
| Фичей админки | 14 |
| Компонентов frontend-v2 | 39 |
| Агентов | 4 |
| Инструментов (tool_registry) | 33 |
| Линий кода (весь проект) | ~150k+ |
