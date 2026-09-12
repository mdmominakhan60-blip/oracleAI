# R01 — Baseline Inventory: актуальная база и полный scope редизайна

**Задача:** BUS-729 (волна A эпика BUS-721). **Статус:** сверено с кодом.
**Репозиторий:** `oracleAI`, ветка `bus709-docs-guard`, HEAD `ff56694`, diverged от `master` (`85fcc4f`) на 6 коммитов (см. §6).

## 1. Зафиксированная база (state of the world)

### 1.1. Структура миниаппа
- **Точки входа HTML:** `miniapp/index.html` (SPA, 19 JS-модулей, `?v=108` cache-busting), `/survey` (отдельный маршрут `app/api/main.py:338`).
- **Топ-вью роутера** (`05-app.js:500 app.go`): `home`, `hub` (чат), `payment`, `profile`. Внутренние сцены: tarot (09), chart (10), compat (11), widgets (08), palm (13), products (14), feedback (19). `go('chat')` — канонический алиас `hub`.
- **Telegram BackButton** синхронизируется (`05-app.js:479`); Esc/Tab trap в модалах (`13-events.js:15`).
- **Публичные поверхности** (`app/api/main.py:458-510`): `/landing`, `/landing/en`, `/privacy`, `/privacy/en`, `/terms`, `/terms/en`, `/robots.txt`, `/sitemap.xml`; `/public` маунт отдаёт только ассеты (HTML → 404, анти-SEO-дубль BUS-130/321).
- **Admin-панель:** `/admin` + `admin/` (SPA, отдельный static-маунт). Полный редизайн admin в scope НЕ входит (§1.3 эпика).

### 1.2. Реестр агентов и инструментов (03-data.js FEATURES)
Четыре агента (fallback-реестр + `/api/agents`):
| Агент | Инструменты (id → handler) |
|---|---|
| Лилит (oracle) | `today`→featureToday, `matrix`→featureMatrix, `monthly`→chatMonthly |
| Урания (astro) | `chart`, `placements`, `compat`, `synastry`, `composite`, `transits`, `returns`, `moon`, `career` |
| Мадам Ленорман (tarot) | `tar`→featureTarot |
| Мира (chiromant) | `palm_scan`→featurePalm |

Ведические (Chart/Dasha/Panchang/Guna) — prompt-инструменты внутри чата Урании (`08-widgets.js:508-521`), не REST-формы. Подтверждает §10.

### 1.3. Ключевые справочники
- **Placement-коды (17):** `moon_sign … chinese_zodiac` — все 17 в `16-placements.js:5-21`, маршрутизация через `data-placement-code` (клик-делегация, не data-act) + `POST /api/placements/calculate`.
- **Таро-колоды (2):** `tarot` (Rider–Waite), `lenormand` (Mary-El) — `09-tarot.js:111`.
- **Расклады (10):** `one, three, love, choice, path, money, career, work, celtic, year` — `app/core/tarot.py:280`.
- **Ладонь:** 2 file-input (камера/галерея, `13-palm.js:89`), accept JPEG/PNG/WebP, отправка одного файла `input.files[0]` (`13-palm.js:248`) — подтверждает противоречие «текст просит два фото, код шлёт одно» (§10).
- **Тарифы:** monthly/annual billing_period (`shop.py:39`), Stars + crypto (TON/USDT/BTC через `/api/shop/invoice`, `/api/shop/crypto-invoice`), промокод `/api/shop/promo` (submit-форма `data-act-form="promo"`, `13-events.js:67`).

### 1.4. Backend API-инventory
Всего **177 маршрутов** в `app/api/routers/` (72 admin, 16 profile, 15 chart, 12 chat, 10 shop, 8 tarot, 6 placements, 5 diary/today, 4 chart_products/notifications/practices, ≤3 прочие; из них 4 — корневые `""` в префиксных роутерах: jobs, logs, practices, shop). Миниапп вызывает **51 уникальный endpoint** (grep по `api('...')` в `miniapp/js/`). Экспорт данных: JSON `oracle-account-export.json` (`12-misc.js:494`), PDF `oracle-natal-chart.pdf` (`12-misc.js:599`). Эксперименты: `experiment_exposure` (track + POST, `profile.py:170-179`).

## 2. Mapping-таблица 105 действий (§16.1)

Контрольный снимок §10.1 сверен с кодом `miniapp/js/15-actions.js` (ветка HEAD).

**Расхождение — единственное: `explain-chart`.**
- На HEAD: **104** обработчика; `explain-chart` отсутствует.
- На ветке `feat/bus650-chart-interpret-ui` (2 коммита BUS-650 Э8b поверх HEAD, НЕ влита): `'explain-chart': (el) => call('explainChart', el)` добавлен рядом с `fc-explain`.
- Семантический преемник на HEAD: `fc-explain` → `app.explainChart` (`12-misc.js:724`) — тот же целевой метод. Сумма «104 в коде + explain-chart на невлитой ветке = 105 по плану» сходится: план снят с ветки BUS-650, эпик предполагал её влитие.

Все 104 обработчика HEAD + `explain-chart` (ветка BUS-650) образуют полный список из §10.1 без неподтверждённых исключений. **Действие для команды:** влить или явно закрыть `feat/bus650-chart-interpret-ui` до R12 (миграция чата/карты), чтобы базовая линия зафиксировалась на одном дереве — иначе счёт 105/104 зависит от выбора ветки.

## 3. Внешние события вне словаря data-act (инвентаризированы)

| Событие | Где | Обработчик |
|---|---|---|
| click-делегация `[data-act]` | `13-events.js:7` | `app.dispatchAction` → `15-actions.js` |
| Enter в `#chat-input` (без Shift) | `13-events.js:16` | `app.doSend()` |
| Escape/Tab (modal trap, toolbox) | `13-events.js:22` | `closeModal` / `trapTabKey` / `setToolbox(false)` |
| input `#tarot-q` | `13-events.js:46` | `app.pendingQ` |
| input `#chat-input` (draft + auto-grow) | `13-events.js:49` | `app.chat.draft`, BUS-636 Э5 |
| input `#ch-city` / `#sp-city` (city suggest) | `13-events.js:54` | `app.citySuggest` |
| input survey `#fb-dream-text` / `#fb-other-text` | `13-events.js:59` | `app.surveySyncInput` (BUS-240) |
| submit `[data-act-form="promo"]` | `13-events.js:67` | `app.submitPromo` (BUS-398) |
| click `[data-placement-code]` | `16-placements.js:103` | `app.calculatePlacement` |
| change file input (палонь, 2 инпута) | `13-palm.js:246` | чтение `input.files[0]`, отправка |
| pointerdown/move/up/cancel (свайпы) | `14-gestures.js:23-40` | toolbox open/close, жесты |
| Telegram BackButton | `05-app.js:479` | `app._backHandler` + haptic |
| download/share ссылки | `12-misc.js` | PNG `oracle-tarot.png`, PDF natal-chart, JSON export |

## 4. Реестр экранов S01–S30 (соответствие кода плану)

Реестр §11 плана принимается как целевой (новая IA). Соответствие текущего кода (для R12-миграции):

| S-экран | Текущий код-носитель | Комментарий |
|---|---|---|
| S01–S03 вход/ошибка/welcome | `01-utils` (initData), `05-app` renderAuthRequired | splash/restore существуют |
| S04 знакомство | bot `Onb` + `miniapp` формы рождения (`06-home`, `10-chart` birth form) | продолжение bot↔app — проверка R09 |
| S05–S07 чат | `07-chat` (renderChat, toolbox, sessions) | основной объём миграции R11 |
| S08–S09 агенты | `05-app` AGENT_BRAND, renderHub | 4 агента подтверждены |
| S10 каталог инструментов | toolbox `07-chat.js:755` (setToolbox/toggleToolbox) | сейчас встроен в чат, не отдельный каталог |
| S12 выполнение/результат | widgets-рендеры `08-widgets`, reports `12-misc` | |
| S13 таро | `09-tarot` (decks, draw, flip, interpret) | |
| S14 карта | `10-chart` + `16-placements`; разбор human v2 — BUS-523 (master) | |
| S15 сегодня | `06-home` + `/api/today`, day-flip, forecast-expand (BUS-517) | |
| S16 отношения | `11-compat` + `14-products` (synastry/composite) | раздельные сценарии подтверждены |
| S17 периоды | `14-products` (transits, returns) + vedic prompts | |
| S18 луна/карьера/матрица/практика | `08-widgets` (moon week/day, career, matrix, practices) | career на лунных данных — подтверждено §10 |
| S19 дневник | `08-widgets` diary (`/api/diary`) | |
| S20 библиотека | `12-misc` history/readings, sessions `07-chat` | |
| S21 профиль | `12-misc` + `/api/profile`, gender/language | имя пользователя ≠ имя оракула — поля раздельны |
| S22 память | `12-misc` memories modal (`/api/memories`) | |
| S23 уведомления | `12-misc` bell + `/api/notifications` | |
| S24–S26 оплата | `17-payments` + `/api/shop/*` | S25 pending-логика — проверить R16 |
| S27 приглашения/опрос | `12-misc` refCopy; `19-feedback` survey | |
| S28 помощь | публичные маршруты `/privacy`, `/terms` | ссылка поддержки — R18 |
| S29 данные аккаунта | `12-misc` export/privacy/delete | fail-closed owner-scope сохранять |
| S30 публичные поверхности | `/landing`, `/landing/en`, robots, sitemap | полный редизайн вне scope, только согласованность |

## 5. Scope редизайна (§1 эпика, фиксация)

**Меняем:** визуальная система целиком (§2), IA (§3: 3 брейкпоинта <768 / 768–1279 / ≥1280), чат как главный экран (§4), каталог инструментов (§5), подача Таро (§6), фон/девушка/motion (§7), представления агентов (§8), онбординг и вторичные экраны (§9). Это новая оболочка поверх сохранённых возможностей (§12.1).

**Сохраняем:** профили/диалоги/память/результаты/права; backend-расчёты и провайдеры; идею и механику Таро (reading_id, decks); живой космический фон; идентичности четырёх агентов (ID неизменны); RU/EN; правила доступа.

**Не входит:** переписывание расчётного ядра, смена LLM/тарифов/цен/платёжного провайдера; новые астро-функции/агенты/обязательная новая регистрация; полный редизайн admin (только нужные новому UI настройки); standalone-браузерная авторизация (отдельное решение после проверки контракта); автопубликация пользовательских данных/изображений/отзывов.

## 6. Риски и пробелы (явные, не «не найдено»)

| # | Риск/пробел | Влияние | Владелец |
|---|---|---|---|
| R-1 | Ветка BUS-650 (`explain-chart`, 105-е действие) не влита; счёт действий 104 (HEAD) vs 105 (план) зависит от дерева | Сверка §16.1 формально сходится только с учётом ветки; до влития — два «источника истины» | CTO → влитие решения до R12 |
| R-2 | 21 CSS-файл `miniapp/css/` имеет незакоммиченные правки (BUS-741: `--grad-primary`, `--shadow-primary`, legacy-gold комментарии; +149/−138 строк) | База редизайна должна фиксировать состояние CSS: либо закоммитить BUS-741, либо явно отложить; нельзя начинать R03 на dirty-дереве | CTO + Frontend |
| R-3 | Разные HEAD у окружений: рабочая ветка `bus709-docs-guard` опережает `master` на 6 коммитов (BUS-709 wipe-guard, BUS-391/647 moon-engine уже в дереве через merge) | QA-стенд и редизайн-ветка должны стартовать с одного merge-base; зафиксировать базу после мержа bus709 | DevOps |
| R-4 | Таро: 2 колоды в UI-коде; проверить серверный реестр колод/раскладов на паритет (API `/api/tarot/spreads` → 10 кодов подтверждены) | R13 должен мигрировать все серверно-активные колоды; если сервер вернёт больше 2 — пробел инвентаря | Frontend + R13 |
| R-5 | Палонь: UI-текст про два фото vs один файл в обработчике — известное противоречие §10 уже зафиксировано планом; ограничение 8 MB и форматы JPEG/PNG/WebP подтверждены в `accept`-атрибуте; серверный лимит проверить в R07 | Не блокирует baseline; R07 закрывает | R07 |
| R-6 | `experiment_exposure` — единственный эксперимент-механизм; flags-системы (feature gates) для поэтапного включения нового UI нет — переключение через §12.3 сборку/rollback | G2/G4 (вертикальный путь, выпуск) требуют flag on/off стенда (E24); план §16.2 E24 уже предполагает тестовый стенд — DevOps заложить | CTO + DevOps |
| R-7 | Admin-инвентарь (72 маршрута) в scope не входит, но новые настройки для пользовательского UI (§1.3) потребуют точечного касания admin | Держать изменения адресными; отдельной задачи R-волны нет — заводить по мере необходимости | CTO |

## 7. Числа для проверки (acceptance evidence)

- Обработчиков data-act на HEAD: **104**; на ветке BUS-650: **105** (= план §10.1).
- Backend маршрутов: **177** (`app/api/routers/`, python-подсчёт по декораторам; 173 с непустым путём + 4 корневых).
- Frontend endpoint-вызовов (уникальных, с параметризацией): **51**.
- Placement-кодов: **17/17** план↔код.
- Раскладов: **10**, колод UI: **2**.
- Публичных маршрутов: **11** (+robots/sitemap/health/metrics).
- Сцен §11: **30/30** имеют код-носитель в текущем миниаппе.

## 8. Критерии приёмки задачи (§ из BUS-729)

- [x] Mapping 105 действий полный, без неподтверждённых исключений — единственное расхождение `explain-chart` объяснено веткой BUS-650 и вынесено в риск R-1 (не «не найдено»).
- [x] Scope §1 зафиксирован (§5 этого документа).
- [x] Реестр S01–S30 опубликован с код-носителями (§4).
- [ ] Baseline согласован QA Engineer — передано на ревью (см. комментарий в задаче).
