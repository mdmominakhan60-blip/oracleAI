# API OracleAI

## Document orientation

| Field | Definition |
|---|---|
| **Purpose** | HTTP API and error contract. |
| **Source of truth** | `app/api/`, `app/services/` and `tests/`. |
| **Scope** | Routes, identity, validation, rate limits, response shapes and failure behavior. |
| **Do not change** | Do not add a route without owner scope, validation, tests and documentation. |
| **Key files** | `app/api/main.py`, `app/api/routers/`, `app/api/contracts/`. |
| **Validation** | `pytest -q tests/test_api.py tests/test_api_resilience.py`. |


## Назначение и base URL

HTTP API обслуживает Telegram Mini App, административную панель и платёжные интеграции. Пользовательские роуты находятся под `/api`; публичные лендинги и статические файлы не являются частью JSON API. В development-режиме OpenAPI доступен по `/api/openapi.json`, а Swagger UI — по `/api/docs`; в production эти страницы намеренно скрыты.[1]

| Среда | Base URL | Пример |
|---|---|---|
| Локальная разработка | `http://127.0.0.1:8080` | `GET /api/me?dev_user=10001` при `APP_ENV=dev`, `DEV_MODE=1` |
| Production | Значение `WEBAPP_URL` | `https://your-domain.example/api/me` |

Все ответы — JSON, кроме image share endpoints и публичных файлов. Контракт обновляется вместе с кодом роутеров; отдельный сгенерированный клиент не поддерживается.

## Аутентификация и ограничения

Пользовательская аутентификация основана на Telegram WebApp `initData` и вычисленном Telegram ID. `?dev_user=<id>` существует только для локальной разработки; сервер завершает startup с ошибкой, если `DEV_MODE=1` включён вне `APP_ENV=dev`.[1]

| Категория | Значение | Примеры |
|---|---|---|
| `read` | Лимит операций чтения. | Гороскоп. |
| `write` | Лимит изменения данных. | Профиль, память, дневник, практика. |
| `llm` | Лимит дорогих AI-вызовов. | Диалог, интерпретация, отчёт. |
| Admin | Проверка административной роли. | CRM, контент, флаги, broadcast. |
| Webhook | Проверка подписи провайдера. | Paddle. |

Не передавайте Telegram ID как доверенный идентификатор в теле запроса: сервер получает текущую пользовательницу через dependency. Любые поля, не описанные Pydantic-моделью endpoint, считаются неподдерживаемыми.

## Общие ответы и ошибки

| Код | Смысл | Поведение клиента |
|---|---|---|
| `200` | Успешное чтение или действие. | Обновить локальное состояние. |
| `400` | Неверные или неподдерживаемые данные. | Показать сообщение рядом с формой; не повторять автоматически. |
| `401` / `403` | Нет валидной Telegram-сессии или прав. | Перезапустить Mini App/вернуться в Telegram. |
| `404` | Ресурс не принадлежит текущей пользовательнице или не существует. | Показать нейтральное пустое состояние. |
| `409` | Конфликт состояния. | Перезагрузить нужный блок; например, память выключена. |
| `410` | Telegram identity относится к уже удалённому аккаунту. | Не восстанавливать профиль; начать новый onboarding через бота. Повторное подтверждённое удаление остаётся идемпотентным. |
| `429` | Превышен лимит. | Сообщить о паузе и не создавать retry-loop. |
| `500` | Непредвиденная ошибка. | Показать безопасный fallback; не выводить stack trace. |

## Профиль, согласия и аналитика

| Method | Path | Назначение | Тело / ключевые поля |
|---|---|---|---|
| `GET` | `/api/health` | Здоровье БД и LLM-цепочки. | — |
| `GET` | `/api/me` | Bootstrap профиля, лимитов, флагов, памяти и агентов. | — |
| `POST` | `/api/profile` | Настройки профиля. | `oracle_name`, `persona`, `morning_push`, `memory_enabled`, `lang`, `tz`, `goal` |
| `POST` | `/api/experiment-exposure` | Техническая отметка показа A/B-варианта. | `experiment`, `variant` |
| `GET` | `/api/personas` | Доступные образы проводника. | — |
| `GET` | `/api/referral` | Ссылка и реферальная статистика. | — |
| `GET` | `/api/memories` | Список сохранённых фактов без внутренних embedding-полей. | — |
| `POST` | `/api/memories` | Ручное сохранение факта. | `fact`, `kind` |
| `DELETE` | `/api/memories/{memory_id}` | Удалить один факт. | — |
| `POST` | `/api/account/delete` | Анонимизировать текущий аккаунт; повторный вызов идемпотентен. | `confirm: true` |
| `GET` | `/api/faq` | Контент FAQ. | — |
| `GET` | `/api/history` | Единый owner-scoped архив отчётов, раскладов, чтений ладони и чатов. | `limit` (1–100) |
| `GET` | `/api/notifications` | Owner-scoped inbox server-owned summaries с unread count. | `limit` (1–100); private chat/provider payloads excluded |
| `POST` | `/api/notifications/read-all` | Идемпотентно отметить уведомления текущего пользователя прочитанными. | — |
| `GET` | `/api/notifications/preferences` | Получить поддерживаемые пользовательские delivery preferences. | — |
| `PATCH` | `/api/notifications/preferences` | Включить/выключить утренний прогноз в Telegram. | `morning_forecast: boolean` |

`POST /api/profile` принимает только RU и EN для `lang`. При отключённой памяти `GET /api/memories` возвращает пустой список, а создание факта возвращает `409`; это часть серверного privacy-контракта, не только UX.[2] `POST /api/account/delete` требует JSON `{ "confirm": true }`, стирает пользовательскую историю и PII, отключает memory/push/age flags, оставляет только settlement-safe user row и возвращает `already_deleted: true` при повторе.

`GET /api/notifications` материализует только уже сохранённый дневной forecast в deduplicated inbox item; endpoint не запускает LLM и не принимает user-supplied notification body. `POST /api/notifications/read-all` ограничен текущим owner scope и безопасен при повторе. Provider notification settings и secondary channels остаются admin-only.

Удалённая учётная запись сохраняется только как обезличенный settlement-safe anchor и не считается действующей пользовательской identity: обычные authenticated routes возвращают `410`, поэтому удалённый пользователь не может повторно включить возраст, память, push или изменить профиль. Исключение — `POST /api/account/delete` с `confirm: true`, который использует только валидированную Telegram identity для безопасного повторения операции и возвращает `already_deleted: true`.

`GET /api/history` возвращает только метаданные и безопасные action/deep-link поля: тела сообщений, ответы раскладов, тексты отчётов, изображения и embedding-векторы выдаются только отдельными owner-scoped маршрутами. Удаление или архивирование определяется полем `deletion`; общий архив не создаёт новый источник записи и не дублирует domain tables.

Пример настройки согласий:

```json
POST /api/profile
{
  "memory_enabled": true,
  "lang": "ru"
}
```

## Сегодня, чат и дневник

| Method | Path | Назначение |
|---|---|---|
| `GET` | `/api/today` | Карта дня и персональный daily context. |
| `GET` | `/api/moon/week` | Неделя лунных данных. |
| `GET` | `/api/sky` | Небесные данные для UI. |
| `GET` | `/api/horoscope` | Гороскоп для выбранного знака. |
| `GET` | `/api/horoscope/all` | Гороскопы всех знаков. |
| `GET` | `/api/agents` | Доступные проводники. |
| `GET` | `/api/chat` | Обзор чатов. |
| `GET` | `/api/chat/{agent}` | История диалога проводника. |
| `POST` | `/api/chat/{agent}` | Новое сообщение проводнику. |
| `POST` | `/api/ask` | Универсальный быстрый вопрос. |
| `DELETE` | `/api/chat/{agent}` | Очистить историю проводника. |
| `GET` | `/api/chat/{agent}/sessions` | Список сессий. |
| `POST` | `/api/chat/{agent}/sessions` | Создать сессию. |
| `GET` | `/api/chat/{agent}/sessions/{thread_id}` | Сообщения одной сессии. |
| `POST` | `/api/chat/{agent}/sessions/{thread_id}` | Сообщение в сессии. |
| `DELETE` | `/api/chat/{agent}/sessions/{thread_id}` | Архивировать/удалить сессию по контракту роутера. |
| `GET` | `/api/diary` | Записи дневника. |
| `GET` | `/api/diary/{entry_id}` | Одна owner-scoped запись дневника для архива. |
| `POST` | `/api/diary` | Создать запись. |
| `GET` | `/api/diary/prompt` | Вопрос-подсказка для дневника. |
| `GET` | `/api/diary/summary` | Краткое резюме дневника. |

Для LLM-вызовов (`/today`, chat, interpretation/report endpoints) клиент обязан выдерживать состояние `sending`, не отправлять дубликаты и обрабатывать rate limit. Дневник не попадает в AI-контекст при отключённой памяти.[3]

## Таро, карта и совместимость

| Method | Path | Назначение |
|---|---|---|
| `GET` | `/api/tarot/spreads` | Краткий каталог раскладов. |
| `GET` | `/api/tarot/spreads/full` | Полный каталог раскладов. |
| `POST` | `/api/tarot/draw` | Вытянуть карты. |
| `POST` | `/api/tarot/interpret/{reading_id}` | Получить AI-интерпретацию расклада. |
| `GET` | `/api/tarot/history` | История раскладов. |
| `GET` | `/api/tarot/history/{reading_id}` | Один owner-scoped завершённый расклад. |
| `GET` | `/api/tarot/stats` | Статистика раскладов. |
| `POST` | `/api/tarot/outcome/{reading_id}` | Отметить наблюдаемый результат. |
| `GET` | `/api/chart` | Текущая натальная карта. |
| `POST` | `/api/chart` | Создать/обновить данные и расчёт карты. |
| `POST` | `/api/chart/interpret` | Интерпретировать карту. |
| `GET` | `/api/matrix` | Матрица по данным профиля. |
| `POST` | `/api/compat` | Краткая совместимость. |
| `POST` | `/api/compat/full` | Полная AI-интерпретация совместимости. |
| `GET` | `/api/partners` | Сохранённые партнёры. |
| `POST` | `/api/partners` | Сохранить партнёра. |
| `DELETE` | `/api/partners/{partner_id}` | Удалить партнёра. |
| `GET` | `/api/reports` | Список персональных отчётов. |
| `GET` | `/api/history` | Нормализованная owner-scoped история отчётов, Tarot, чатов и дневника; raw bodies не включаются. |
| `GET` | `/api/reports/{kind}` | Получить отчёт заданного типа. |
| `POST` | `/api/reports/{kind}` | Создать AI-отчёт; `?refresh=true` принудительно создаёт новую immutable history version. |

`POST /api/tarot/draw` возвращает `ledger.replay` с контрактом `tarot-replay-v1`. Replay всегда восстанавливается из server-side `cards_json`, позиций и ориентаций уже вытянутых карт; повторная вытяжка не выполняется. Поле `ledger.checksum` позволяет обнаружить изменение исторического payload, а `tarot.replay_ledger(cards, spread, expected_checksum)` отклоняет несовпадение checksum.

### Натальный контракт v2

`GET /api/chart` и `POST /api/chart` сохраняют legacy-поля `nodes`, `planets`, `houses` и `aspects`, но дополнительно возвращают `natal_schema_version: 2`, вычислительные conventions (`engine`, `zodiac_type`, `house_system`, `house_system_name`, `perspective_type`), canonical `lunar_nodes` и `additional_points`. В `lunar_nodes` северный узел называется **Rahu / Раху**, южный — **Ketu / Кету**; текущая продуктовая настройка `mode: "true"` означает True Node. `nodes` остаётся для совместимости и также содержит Лилит.

| Поле | Смысл | Пример |
|---|---|---|
| `engine` | Источник эфемерид. | `Swiss Ephemeris via Kerykeion` |
| `zodiac_type` | Зодиакальная система. | `Tropical` |
| `house_system` / `house_system_name` | Идентификатор и имя домов. | `P` / `Placidus` |
| `perspective_type` | Геометрическая перспектива. | `Apparent Geocentric` |
| `lunar_nodes.rahu` / `.ketu` | Канонические положения Rahu/Ketu. | точка, знак, градус, дом, exact-поля |
| `additional_points` | Расширенные точки. | Хирон, Джуно, Церера, Веста, Паллада |

Если время рождения неизвестно, `precision` сообщает `date_only`, а дома, ASC и MC скрываются; положения планет, True Node Rahu/Ketu и дополнительные точки остаются эфемеридными фактами без притворной точности домов.

### Полный PDF natal report

Для ручной или batch-сборки используется `python -m scripts.gen_pdf`. Один заказ можно собрать так:

```bash
python -m scripts.gen_pdf --name Анна --date 21.06.1990 --time 14:30 \\
  --city Казань --lang ru --out data/pdf
```

Для English-версии используется тот же pipeline с `--lang en`. В batch CSV допускается поле `lang` или `language`; без него выбирается `ru`.

```bash
python -m scripts.gen_pdf --name Anna --date 21.06.1990 --time 14:30 \\
  --city Kazan --lang en --out data/pdf
```

В приложении язык берётся из пользовательской настройки профиля `lang` (`ru` или `en`) и передаётся в `Order.lang`. Редактируемые project settings для обложки и footer: `brand.name`, `brand.name_en`, `brand.tagline`, `brand.tagline_en`, `brand.project_url`, `disclaimer` и `disclaimer_en`. Если URL не задан в БД, используется `PUBLIC_URL`/`WEBAPP_URL`, а затем ссылка репозитория OracleAI как безопасный fallback.

Команда создаёт PDF через WeasyPrint, а при его отсутствии сохраняет HTML, который можно открыть на телефоне или ПК и распечатать в PDF браузером. `--html` принудительно сохраняет responsive HTML preview; `--csv` запускает batch-режим. Полный отчёт включает summary, wheel с Rahu/Ketu, conventions, планеты, лунные узлы, Lilith, expanded points, дома, аспекты, интерпретационные разделы, Матрицу и safety disclaimer. PDF использует читаемую A4-верстку; HTML preview применяет screen CSS для узких и широких viewport.

Дата, время и место рождения — чувствительные профильные данные. Клиент должен запрашивать их только при ясной задаче, объяснять назначение и не включать в share URL или analytics properties.

## Практики, sharing и магазин

| Method | Path | Назначение |
|---|---|---|
| `GET` | `/api/practices` | Каталог практик. |
| `GET` | `/api/practices/{code}` | Одна практика и прогресс. |
| `POST` | `/api/practices/{code}/start` | Начать практику. |
| `POST` | `/api/practices/{code}/done` | Отметить шаг выполненным. |
| `POST` | `/api/practices/{code}/stop` | Остановить практику. |
| `GET` | `/api/share/reading/{reading_id}.png` | PNG-карточка расклада. |
| `GET` | `/api/share/today.png` | PNG-карточка дня. |
| `GET` | `/api/share/compat.png` | PNG-карточка совместимости. |
| `GET` | `/api/share/enabled` | Доступность share-функции. |
| `GET` | `/api/shop` | Витрина тарифов и товаров. |
| `POST` | `/api/shop/invoice` | Создать счёт Telegram Stars. |
| `POST` | `/api/shop/web-checkout` | Получить web checkout. |
| `POST` | `/api/shop/crystals` | Получить/купить кристаллы по контракту магазина. |
| `POST` | `/api/shop/promo` | Активировать промокод. |
| `GET` | `/api/shop/orders` | История заказов. |
| `GET` | `/api/shop/crystals/history` | История движения кристаллов. |

## Webhook и админский API

`POST /api/webhooks/paddle` принимается только от доверенного платёжного провайдера и требует проверяемую подпись. Он не предназначен для Mini App и не должен вызываться браузером.[4]

Административный API имеет prefix `/api/admin` и отдельную авторизацию. Он содержит группы `/me`, `/health`, `/dashboard`, `/events`, `/costs`, `/safety`, `/horoscopes`, `/users`, `/content`, `/settings`, `/flags`, `/plans`, `/products`, `/orders`, `/promo`, `/broadcasts`, `/admins`, `/audit` и `/logs`. `GET /api/admin/logs` возвращает последние redacted operational entries из ограниченного process-local ring buffer; `GET /api/admin/logs/stream` отдаёт тот же поток через authenticated SSE и поддерживает фильтры `level`, `logger` и `query`. Поток не заменяет stdout/file retention и не должен использоваться для пользовательских сообщений или PII. Полные request/response модели проверяются по OpenAPI в development и исходнику [`admin.py`](../app/api/routers/admin.py); добавление админского endpoint без audit trail недопустимо.

### История и регенерация отчётов

Отчёты хранятся как **append-only history entries**. Обычный `POST /api/reports/{kind}` возвращает последнюю сохранённую версию с `cached: true`; `POST /api/reports/{kind}?refresh=true` после проверки entitlement рассчитывает и добавляет новую версию, не удаляя предыдущую. Ответ содержит `report_id`, а `GET /api/reports/{kind}` всегда читает последнюю версию. Каждая новая версия сохраняет deterministic source и evidence limitations в закрытом `meta_json`, чтобы изменение профиля не меняло уже созданный historical report.

### Unified history

`GET /api/history?limit=30` возвращает компактную cross-tool read model с `kind`, source-local `entry_id`, глобально читаемым `source_id`, `created_at`, ограниченным preview и точным `deep_link`. Endpoint не возвращает full report body, полный текст дневника, память, birth data или raw chat history. Все source-specific routes сохраняют собственную owner-фильтрацию и правила удаления; palm analysis намеренно не включён, поскольку в текущем продукте он не хранится как first-class history artifact.

## Правила изменения контракта

1. Добавьте Pydantic-модель для нового тела и ограничения длины/формата.
2. Укажите dependency для current user, admin, rate limit или webhook signature.
3. Верните предсказуемый JSON и не раскрывайте внутренние ошибки или SQL.
4. Обновите эту таблицу, клиентский вызов и тесты в одном pull request.
5. Для несовместимого изменения добавьте новый endpoint или переходный период; Mini App может быть закэширован.

## References

[1]: [app/api/main.py](../app/api/main.py) — конфигурация OpenAPI, docs URL и защита dev-режима.
[2]: [app/api/routers/profile.py](../app/api/routers/profile.py) — контракт `ProfileIn`, память и exposure-события.
[3]: [app/api/routers/diary.py](../app/api/routers/diary.py), [app/services/chat.py](../app/services/chat.py), [app/core/agents/runtime.py](../app/core/agents/runtime.py) — privacy guard дневника и памяти.
[4]: [app/api/routers/webhooks.py](../app/api/routers/webhooks.py) — webhook Paddle.
