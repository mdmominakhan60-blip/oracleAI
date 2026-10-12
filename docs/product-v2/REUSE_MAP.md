# OracleAI v2 — Reuse Map

Что переносится из v1 в v2, откуда, с какими зависимостями и рисками. Разделение явное: **визуальная логика** (переносится как компонент/стиль) и **серверные расчёты** (остаются на backend без изменений).

Обозначения: **REUSE** — без изменений · **ADAPT** — с адаптацией · **REBUILD** — заново · **DEFER** — позже · **REMOVE** — кандидат на удаление.

---

## 1. Изображения и визуальные ресурсы — REUSE

| Ресурс | Путь | Размер | Состояние | Зависимости |
|---|---|---|---|---|
| 78 карт Таро (RWS) | `miniapp/img/tarot/*.jpg` | 7,2 MB | **Проверено: 78 файлов, slug'и `m00`…`m21` + `{wands\|cups\|swords\|pents}{01..14}` — 1:1 с `full_deck()`** | Контракт `img` в `app/core/tarot.py:188-213` |
| 78 карт Ленорманда | `miniapp/img/lenormand/*.jpg` | 9,9 MB | Проверено: 78 файлов | То же; `deck` ∈ `{tarot, lenormand}` |
| Рубашка карты | `miniapp/img/card-back.jpg` | 166 KB | В использовании | `.tcard-back` |
| Лицо карты (fallback) | `miniapp/img/card-face.jpg` | 188 KB | Заглушка | — |
| Фоны космоса | `miniapp/img/bg-cosmos.jpg`, `bg-cosmos-2.jpg`, `lilith-sil.png` | ~0,5 MB | В использовании, `preload` в `index.html:14,47` | — |
| Иконка/OG | `miniapp/img/favicon.svg`, `oracle-mark.png`, `og-card.jpg` | — | — | — |
| Шрифты Manrope (cyrillic/cyrillic-ext/latin woff2 + ttf) | `miniapp/fonts/manrope-*` | — | **Работающая кириллица, preload** | `miniapp/fonts/oracle-fonts.css` |
| Шрифты Cinzel, PJS | `miniapp/fonts/{cinzel-*,pjs-*}`, `oracle-fonts.css` | — | Fallback | — |

**Как раздаётся:** всё уже доступно абсолютно по `/static/...` через `app.mount("/static", StaticFiles(MINIAPP_DIR))` (`app/api/main.py:393`). Новый фронт ссылается как есть — **переносить файлы не нужно**, они остаются в `miniapp/`.

**РЕШЕНИЕ: не копировать картинки в `frontend-v2/`.** Дублирование раздует репозиторий и создаст второй источник правды. Vite ссылается на `/static/img/...` абсолютным путём; `scripts/check_static_asset_references.py` уже умеет `.ts`/`.tsx` и проверит, что ссылки существуют.

**Риски:**
- `onerror` на картах в v1 отсутствует — в v2 добавить fallback на `card-face.jpg`.
- Кэш: `/static/img/*` имеет `max-age=3600` (не immutable) — имена без хеша. Это работающий контракт, ломать не нужно.
- Аватары агентов `miniapp/img/agents/{coach,keeper,numero}.jpg` — **REMOVE**, в реестре агентов их нет (см. §6).

---

## 2. Анимации и механика карт — ADAPT (визуальная логика)

| Элемент | Источник | Что переносим |
|---|---|---|
| **3D-переворот карты** | `miniapp/css/10-tarot-carousel.css:65-79` + `miniapp/css/15-ritual-redesign.css:1263-1266` | `.tcard{perspective:1000px}` → `.tcard-inner{transform-style:preserve-3d;transition:transform var(--tarot-flip)}` → `.tcard.open .tcard-inner{transform:rotateY(180deg)}`; `.tcard-front` предповёрнут на `rotateY(180deg)`; обе грани `backface-visibility:hidden` |
| **Приподнимание перед переворотом** | `15-ritual-redesign.css:1263-1266` + `09-tarot.js:240-243` | `.tcard.is-turning .tcard-inner{transform:rotateY(11deg) scale(.975)}`, 130мс |
| **Раздача колоды** | `10-tarot-carousel.css:36-39` + `07-chat.js:581` | `@keyframes dealIn{from{translateY(-46px) rotateY(96deg) scale(.72);opacity:0}}`, стаггер `i*80ms` |
| **«Дыхание» следующей карты** | `15-ritual-redesign.css:1261-1262,1272-1277` | `.tpos.is-next .tcard{animation:tarotNextCard 1.8s ease-in-out infinite}` |
| **Прогресс раскрытия** | `15-ritual-redesign.css:1226-1251` + `09-tarot.js:253-259` | `scaleX` на `--tarot-progress` |
| **Порядок открытия** | `miniapp/js/09-tarot.js:221-251` | Логика `nextReveal`, подсказка «сначала открой первую» |
| **reduced-motion** | `15-ritual-redesign.css:1279-1290` + `11-misc.css:82-93` | Конечный `rotateY(180deg)` сохраняется, переходы off |

**Что НЕ переносить механически:**
1. **Sibling-селектор `~`** для подписей позиций (`10-tarot-carousel.css:90-98`) — в React аналога нет; заменяется на state-условие `revealed && <PositionLabel/>`.
2. **Прямое обновление DOM** (`09-tarot.js:218-219` обходит ререндер, чтобы не прыгал скролл) — в React решается ключами + `useLayoutEffect`.
3. **Хардкод таймингов** — вынести в токены `--tarot-lift:130ms`, `--tarot-flip:550ms`, `--tarot-deal-step:80ms`, `--tarot-cascade:120ms`, `--tarot-breathe:1800ms`.

**Реализация в v2:** `<TarotCard slug deck reversed revealed isNext positionLabel/>` + `<TarotDeck positions cards revealedIndex/>` — `DESIGN_SYSTEM.md` §7.3.

---

## 3. API-клиент с авторизацией — REUSE (визуальная логика, дословный порт)

Источник: `miniapp/js/01-utils.js:43-177`. Это **готовая, отлаженная реализация**, а не кандидат на переписывание.

| Функция | Строка | Что делает | Перенос |
|---|---|---|---|
| `mintSession()` | `66-88` | Один POST `/api/auth/session`, `mintInFlight` дедуп параллельных вызовов | Дословно |
| `authHeaders()` | `93-100` | Приоритет `X-Session-Token` → `X-Init-Data` | Дословно |
| `withSessionResilient(run)` | `109-125` | 401 → сверка токена → clear → реминт → один повтор. **Не ретраит по `x-init-data`** (повтор бессмыслен) | Дословно, с осторожностью |
| `friendlyError()` | `231-244` | Санитизация: 401/подпись → «Открой OracleAI из Telegram»; 5xx/таймаут → «Это временно» | Дословно + расширить |
| `api()` / `apiBlob()` | `128-197` | Базовый относительный URL; ретраи: сеть всегда, 5xx **только GET**; `AbortError` никогда | Дословно |
| `newRequestKey()` | `103-107` | `crypto.randomUUID()` для `X-Idempotency-Key` | Дословно |

**Почему ретрай 5xx только GET:** повтор мутации может задвоить эффект. Это корректное решение, не потерять при порте.

**Заголовки:** `X-Session-Token`, `X-Init-Data` (fallback), `X-Dev-Key` (dev), `X-Idempotency-Key` (чат), `X-Start-Param` (только `/api/me`), а также `X-Session-Id` (опционален, мост анонимной сессии, `app/api/routers/profile.py:254`).

---

## 4. Фон, атмосфера, навигация — ADAPT

| Элемент | Источник | Решение |
|---|---|---|
| 4 состояния фона (welcome/chat/tarot/work) | `miniapp/css/22-background-states.css` (весь) + `01-sky-shell.css` + `04-atmosphere.css` | Переносим как компонент `<StarField state/>` |
| Starfield, метеоры, nebula, galaxy, constellations | `miniapp/index.html:22-48` (SVG-созвездия) + CSS | Переносим SVG дословно — он уже чистый и независимый |
| Автопауза фона при `visibilitychange` + тумблер | `22-background-states.css:68-85` + `05-app.js:39-52` | Переносим логику |
| reduced-motion авторитетный блок | `00-tokens.css:220-227` | Переносим (покрывает все 9 движений) |
| Safe-area + viewport чата | `miniapp/css/20-chat-viewport.css` + `05-app.js:265-299` | Переносим; вынести `env(safe-area-inset-*)` в токены |
| Свайп-навигация с блок-листом зон | `miniapp/js/14-gestures.js:7-105` | **ADAPT**: пороги `|dx|>=66 && |dx|>|dy|*1.35 && elapsed<900`, мышь и ПКМ игнорируются; `button`/`[data-act]` в блок-листе |
| Иерархия «назад» | `05-app.js:550-581` (`BackButton.onClick`) | **REBUILD**: в v2 — React Router + явный стек, не императивный стек обработчиков |
| Bottom sheet с focus-trap и Esc | `13-events.js:19+`, `13-toolbar-sheet.css` | REBUILD на доступном примитиве |
| Toast 2400мс | `07-chat.js:156-161` + `15-ritual-redesign.css:352` | REBUILD |

---

## 5. Натальная карта как визуализация — ADAPT

Источник: `miniapp/js/10-chart.js` (inline SVG-колесо), `miniapp/css/09-chart-panels.css`, `15-ritual-redesign.css` (`chartOrbit`, `chartReveal`, `chartRise`).

- Колесо рисуется **inline SVG**, без растровых картинок — переносимо без потерь.
- Питается от `GET /api/chart` (контракт в `API_CONTRACTS.md` §6).
- **Обязательное правило:** при `precision != "exact"` не рисовать дома и ASC/MC. Источник истины — `precision` в ответе.
- Растровая альтернатива уже есть: `GET /api/chart/image?variant=compact|full|share|print&format=png|webp` с `ETag`/304 — использовать как fallback для share, не как основную отрисовку.

---

## 6. Серверные расчёты — REUSE без изменений

**Не переписывать. Не дублировать на клиенте.**

| Модуль | Путь | Что считает | Контракт |
|---|---|---|---|
| Колода Таро | `app/core/tarot.py` | 78 карт, 10 раскладов, `reading_ledger`, `cards_text` | `img`-слаг, `immutable_cards` + `checksum` |
| Раздача | `app/core/tarot.py:406-425` | `secrets.SystemRandom()`, `rng.sample(DECK, n)`, `card["reversed"]=rng.getrandbits(1)` | **Только сервер.** Порядок значим |
| Натальная карта | `app/core/astro.py`, `astrology_engine.py`, `chart_contract.py` | Планеты, дома, аспекты, узлы, секции, precision | `natal_schema_version: 2` |
| Эфемериды | `kerykeion 5.12.9` + `pyswisseph 2.10.3.2` | Астрономия | **AGPL — см. §Риски** |
| Матрица Судьбы | `app/core/matrix.py:205` | 7 позиций из даты рождения | `compute_matrix` |
| Совместимость | `app/core/tool_registry.py:306-382`, `app/services/compatibility.py` | Балл, breakdown, 5 сфер, вердикт | Одна формула на весь продукт |
| Chart products | `app/core/chart_products.py` | Синastрия, композит, транзиты, returns | 422 `{code,message,missing}` |
| Placement-калькуляторы | `app/core/placements.py` | 24 калькулятора (21 западный + life_path, chinese_zodiac, natal_chart) | `POST /api/placements/calculate` |
| Ведические | `app/core/vedic.py` | 10 инструментов (чарт, накшатра, даша, панчанг, раху-каал, варги, гуна-милан, транзиты, сила планет, мухурта) | `calculation_mode:"deterministic"` |
| Лунные данные | `app/core/astro.py:746-822` (`moon_day`) | Фаза, знак, лунный день, транзит | `engine:"moon-engine-v1"` |
| Планирование картинок | `app/core/cards.py` | `reading_card`, `forecast_card`, `compat_card` (Pillow) | `/api/share/*.png` |
| PDF | `app/pdfgen/*` + WeasyPrint | Натальный разбор | `/api/chart/pdf` |
| Хиромантия | `app/core/palm/*` + `models/*.onnx`, `models/hand_landmarker.task` | CV-геометрия + vision | `palm-evidence-v1` |

**Инвариант, который переносится как есть:** модель никогда не выдумывает карты, планеты, арканы — она получает готовый расчёт и объясняет его (`app/core/tool_registry.py:15-17`).

---

## 7. AI-оркестрация — REUSE + ADAPT

| Компонент | Путь | Решение |
|---|---|---|
| Детерминированный роутер доменов | `app/core/agents/routing.py` | **REUSE** — уже то, что нужно. Explainable, без LLM |
| Реестр агентов (файловые пакеты) | `app/core/agents/registry.py` | **REUSE** — механизм; `DEFAULT_AGENT="oracle"` |
| Runtime исполнения | `app/core/agents/runtime.py` | **REUSE** — allow-list, бюджеты, safety-gate, офлайн-фолбэк |
| 33 инструмента | `app/core/tool_registry.py` | **REUSE** |
| Бюджет workflow | `app/core/llm.py:74-120` (`_WorkflowBudget`) | **REUSE** — timeout + tool-calls + cost ceiling |
| Цепочка провайдеров + fallback | `app/core/llm.py`, `provider_chain` в `config.py` | **REUSE** |
| Guides (правила трактовки) | `app/core/tool_registry.py:41-171` | **REUSE** — редактируются в админке, без деплоя |
| Skills (SKILL.md) | `app/agents/*/skills/` | **REUSE** — 139 файлов знаний |
| **Allow-list инструментов** | `runtime.py:129` `frozenset(spec.skills)` | **ADAPT**: источник — домен вопроса, а не выбранная персона |
| Per-agent лимиты | `agent.yaml` (`limits`) | **ADAPT**: стать per-domain; `risk_level:high` для хиромантии |
| Поле `agent` в shared-context | `app/core/shared_context.py:125` | **ADAPT**: переосмыслить как домен/аспект |
| 4 × `SYSTEM.md` | `app/agents/*/SYSTEM.md` | **DEFER**: слияние в один с доменными секциями — после рабочей механизмки |

**Главное:** агенты — это данные (`agent.yaml` + `SYSTEM.md` + `skills/`), не код. Поэтому консолидация не требует переписывания runtime.

---

## 8. Память и история — REUSE (слои) + ADAPT (связи)

| Слой | Путь | Состояние | Решение |
|---|---|---|---|
| Краткая история треда | `app/core/agents/context.py:60-81` | Последние `history_limit` реплик дословно, ранние сжаты в 4 пункта × 220 символов; сообщение ≤1200 | REUSE |
| Долговременная память | `app/core/memory.py` | Дедуп (точное → косинус ≥0.90), поиск (floor 0.35, pool 300, TTL 5м, anchor 40%), недельная сводка «кто она» | REUSE |
| Shared context | `app/core/shared_context.py` | 8 рекомендаций за 30 дней, ≤900 символов; анти-контрадикция между доменами | REUSE — при едином Oracle важен больше |
| Consent | `tool_registry.py:937,950,960`, `profile.py:444,457`, `runtime.py:70-72` | Три точки проверки; тесты `test_memory_tools_cannot_bypass_memory_off`, `test_diary_tool_is_blocked_when_memory_off` | REUSE — **абсолют** |
| Anonymize | `app/repo/users.py:202-250` | Жёсткий allowlist 19 таблиц + обезличивание финансового следа | REUSE + расширить на граф |
| **Граф связей** | — | **Не существует**: `memories` — плоский список строк; `partners` не связан ни с памятью, ни с раскладами, ни с дневником | **ADAPT/REBUILD** — аддитивная миграция, `MIGRATION_PLAN.md` Этап 6 |
| История (метаданные) | `app/api/routers/history.py:51-92` | `kind, entry_id, source_id, evidence_id, deep_link, preview≤160`; чаты/дневник с пустым preview | REUSE |

---

## 9. Безопасность — REUSE без изменений

| Механизм | Путь | Почему переносится как есть |
|---|---|---|
| initData HMAC | `app/api/security.py:32-84` | Каноническая схема Telegram; `compare_digest`; отказ при дублях ключей; `auth_date` в окне [now−24ч, now+10мин] |
| Сессии + replay | `app/api/routers/auth_router.py:91-151` | Redis `SET NX EX` на хеш initData; stateless токен; 10/мин |
| Кризисный протокол | `app/core/safety.py` | **Код, не промпт**; работает при лежащих LLM; лимит не списывается; `_squash` ловит «н е х о ч у ж и т ь» |
| Owner-scope | `app/repo/*` | `WHERE id=:id AND tg_id=:tg_id` в SQL. Параметра `tg_id` в контракте нет вообще |
| Anti-галлюцинации | `app/core/interpretation.py:246-257` | `validate_nonfatal_text` на каждый ответ; пDestroyит «точно случится», взаимоисключающие директивы |
| Tool-injection барьер | `app/core/memory.py:146-158` (`untrusted_text_block`) | BEGIN/END UNTRUSTED DATA для дневника и памяти |
| Лог-редакция | `app/core/observability.py` | Whitelist полей + regex; Sentry `send_default_pii=False` |
| CSP / заголовки | `app/api/main.py:219-244` | `frame-ancestors` открывает Telegram-вебвью (SEC-002) |

**Что переносится НЕ полностью (открытые вопросы):** read-роуты принимают `x-init-data` напрямую (nonce только на минте); replay-store fail-open по умолчанию. Оба требуют решения владельца — `SCREEN_SPEC`/`ARCHITECTURE.md` §Риски.

---

## 10. Тесты и QA — REUSE как регрессионная сеть

| Ресурс | Путь | Что проверяет |
|---|---|---|
| 114 тестовых файлов, 1257 тестовых функций | `tests/` | Реальная PostgreSQL + `pg_advisory_lock` + `TRUNCATE CASCADE`; без моков БД |
| `test_agent_routing.py` | `tests/` | Домены, пороги, ambiguous — **ключевой гейт для единого Oracle** |
| `test_security_regressions.py` | `tests/` | initData, replay, DEV_KEY, memory-off, anonymize |
| `test_bus200_replay.py` | `tests/` | Replay fail-open/closed — требует живого Redis |
| `test_tarot_contract.py`, `test_bus1232_precision_canon.py` | `tests/` | Ledger, checksum, воспроизводимость |
| `test_chart_contract.py`, `test_placements_palm.py` | `tests/` | Precision-gates, owner-isolation |
| `test_route_inventory.py` + `scripts/check_route_inventory.py` | — | Каждый `/api` имеет auth-deep или письменное основание |
| Frontend QA (15 скриптов) | `scripts/qa_*.mjs`, `run_axe_core.mjs`, `run_lighthouse_axe.mjs`, `visual_qa_capture.py` | axe + Lighthouse по 4 категориям, визуальная регрессия |
| `check_design_contract.py` | — | Наличие 39 токенов + порядок 34 CSS-@import |

**Важно:** тесты читают исходники через `/opt/oracle/` (монтирование `miniapp` ro в `Makefile`). Тесты `test_test_miniapp_actions` и `test_architecture_boundaries` зависят от файловой раскладки `miniapp/js/*` — при переезде в `frontend-v2/` их нужно пересмотреть (`TEST_PLAN.md`).

---

## 11. Что НЕ переносить

| Элемент | Путь | Почема |
|---|---|---|
| Экран выбора проводника | `06-home.js:199-235` («Выбери проводника»), `07-chat.js:45-46,713-715` (`cycleAgent`), `18-onboarding.js:117-119,224` | Противоречит главной концепции v2 |
| Per-agent темы | `05-app.js:679-682,702-705` (`AGENT_BRAND`) + `15-ritual-redesign.css:2243-2246` | Требуют агентов; в v2 единый акцент |
| Стили выбора агентов | `miniapp/css/05-agents.css` (dock-grid, orb), `27-observatory.css` (`.guide-entry`) | Нет экрана |
| Авто-переключение чата | `07-chat.js:856-859` + `routingHtml:189-198` («Передала вопрос Урании») | Ломает ощущение одного Oracle |
| Импerative-рендер | `05-app.js` (`app.view` + if/else `594-631`), innerHTML-шаблоны | Заменяется React Router + компонентами. **Не тащить как есть** |
| Глобальный `app`-хаб | `00-runtime.js:10-45` (`bindLegacyState`, `app._*`) | Заменяется стором |
| Мёртвые агенты | `02-art.js:12-14`, `03-data.js:80-90`, `personas.py:3-5` (docstring) | `coach`, `numero`, `keeper` — в реестре их нет |
| Аватары мёртвых агентов | `miniapp/img/agents/{coach,keeper,numero}.jpg` | Нет кода |
| `.rev` мёртвый класс | `07-chat.js:584` (вешает, CSS-правила нет) | В v2 — настоящий поворот арта |
| 13 мёртвых токенов | `00-tokens.css` (список в `DESIGN_SYSTEM.md` §10) | 0 использований |
| Копии картинок | `design/r06/p*/img/` (4MB), `design/sources/` (18MB) | Побайчно идентичны `miniapp/img/`; прод не ссылается |
| Дубль `.tcard__*` | `26-r06-p3.css:705-733` ~ `25-r06-p2.css:703-731` | Оставить один механизм |
| Legacy-алиасы токенов | `--ink-*`, `--champagne-*`, `--lilac-*` | Временный слой миграции v1 |

**Сохранить из `design/`:** `design/r06/HANDOFF.md` (чек-лист S01–S30), `design/r06/p*/SPEC.md` и `index.html` — ценная спека.

---

## 12. Риски переноса

| Риск | Митигация |
|---|---|
| Дублирование картинок в `frontend-v2/` | Ссылаться на `/static/img/...`, не копировать; `check_static_asset_references.py` проверит |
| **AGPL у kerykeion/pyswisseph** | Не переписывать расчёты (не решит лицензию). Решение владельца — `PRODUCT_BRIEF.md` §9 |
| `hand_landmarker.task` без provenance | Не переносить ничего; документ `THIRD_PARTY_NOTICES.md` дополняет владелец |
| i18n: 6 независимых словарей в v1 | Единый слой в v2; ключи извлечены из `01-utils.js`, `07-chat.js`, `09-tarot.js`, `13-palm.js`, `17-payments.js`, `19-feedback.js` |
| Тесты читают `miniapp/js/*` | Пересмотреть `test_miniapp_actions`, `test_architecture_boundaries` при переезде |
| `check_frontend_provenance.py` читает 4 конкретных файла | Перенести ключи провенанса; иначе CI красный |
| Нет стриминга к клиенту | v1 так же. Оценено как допустимое; `/api/jobs` есть для async, но не используется фронтом |
| `next_action.chat` содержит `agent`-код | В v2 — домен-подсказка, не персонаж; UI не показывает как выбор |
