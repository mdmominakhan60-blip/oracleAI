# BUS-1564 — live re-verify (10.10.2026, 15:00–15:12 лок. / 12:00–12:12Z)

Верификация «вживую» состояния стека и конфигурации. Все значения секретов — только длина и sha256-префикс, без вывода.

## 1. Стек

| Проверка | Результат |
|---|---|
| Контейнеры проекта `infra` | 14/14 `running` |
| `GET https://localhost:8443/api/health` (через caddy) | `200 {"ok":true}` |
| `infra-api-1` | Up, healthy |
| `infra-bot-1` | **crash-loop: 20 → 111 рестартов за ~7 минут** (два замера: 106 @12:29:35, 111 @12:30:00), `exitCode=0` |
| `infra-worker-1` | ready, `oracle.maintenance` succeeded (12:02:24) |
| `infra-beat-1` | Scheduler running, рассылает `oracle-maintenance-hourly` |

Вывод: утверждение «stack is NOT down» из предыдущего рана **подтверждено**. BUS-1546 («stack down 3 weeks») — устарело.

## 2. Root cause #1 — placeholder BOT_TOKEN (подтверждён)

```
docker exec infra-bot-1 printenv BOT_TOKEN -> len=13  sha256[:12]=c8c8ce6708b3
.env.example           BOT_TOKEN=            -> len=14  sha256[:12]=ed16f04f1d0
```

Расхождение в длине — это разные плейсхолдеры (в контейнере 13 символов, в шаблоне 14 — лишний перевод строки/точка). Второй опорный слепок:

```
Business/projects/oracleai-mvp-release/.env  BOT_TOKEN -> len=13  sha256[:12]=c8c8ce6708b3
```

То есть токен в контейнере **побайтово равен** токену в другого репо-проекта и тоже является плейсхолдером (`123456:ABC...`). Настоящего прод-токена нет ни в одном источнике, доступной агенту.

Логи (`app/bot/main.py:181`):

```
app/bot/main.py:181 -> await bot.delete_webhook(drop_pending_updates=True)
aiogram.exceptions.TelegramUnauthorizedError: Telegram server says - Unauthorized
```

Плюс `bot/main.py:151` — `getMe` / `set_my_commands` → Unauthorized. В логах **ноль строк поллинга** — бот ни разу не был жив.

## 3. Root cause #2 — LLM-цепочка (новая находка, не в past-run)

| Параметр (infra-api-1) | Значение |
|---|---|
| `LLM_PROVIDER` | `auto` (len=4) |
| `CUSTOM_LLM_BASE_URL` | len=25, = `http://127.0.0.1:20128/v1` |
| `CUSTOM_LLM_MODEL` / `CUSTOM_LLM_MODEL_LITE` | len=18, равны между собой |
| `CUSTOM_LLM_API_KEY` | len=15 |
| `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` | **пусты** |
| `APP_ENV` | `dev` (не `production`) |

Две отдельные проблемы:

**(а) `127.0.0.1` недостижим из контейнера.** `infra-compose.oci.yml:45-59` добавляет `host.docker.internal:host-gateway` именно потому, что loopback VPS не виден. Текущее значение указывает на `127.0.0.1` — оба прежних рабочих канала отломаны.

```
docker exec infra-api-1 curl http://127.0.0.1:20128/v1/models     -> HTTP 000 (connection refused)
docker exec infra-api-1 curl http://host.docker.internal:20128/... -> HTTP 200 (канал рабочий)
```

**(б) Запрошенная модель не обслуживается.** Прямая проба прокси:

```
requested oc/claude-sonnet-5 -> served opencode-zen/step-5-preview-free (2 повтора, оба 200)
```

Модель подменяется прокси. Это означает, что P0-003 (Live AI) сертифицирован на модели, которая **не является той, что считаем продуктовой**.

Латентность: первый вызов 34.5с, через `host.docker.internal` — 2.6с. => p95-риск реальный, но он хостовый, не контейнерный.

## 4. Root cause #3 — `.env` отсутствует, деплой сломан

- `docker compose config -q` из `infra/` **падает**: `required variable APP_ENV is missing`, `DATABASE_URL`, `POSTGRES_PASSWORD`, `GRAFANA_ADMIN_PASSWORD`.
- Причина: `infra/docker-compose.yml:20-21` требует `env_file: ../.env`, а файла `/home/softis/apps/oraclAI/oracleAI/.env` **нет на диске**.
- Контейнеры живы потому, что были созданы 2026-10-09T01:31:31Z — до удаления `.env`. Любой `up -d` / recreate **сломает стек**.
- `WEBAPP_URL` в api-контейнере пуст; `DOMAIN` в caddy = `localhost`.

Это означает: **сейчас нельзя ни перезапустить, ни пересоздать контейнеры через compose.** Правка `.env` — предварительное условие любого фикса.

## 5. Состояние данных (подтверждает «цепочка ценности мертва»)

| Таблица | Строк |
|---|---|
| `events` | 0 |
| `deliveries` | 0 |
| `users` | 0 |
| `llm_usage` | 0 |
| `messages` | 0 |
| `horoscopes` | 0 |
| `daily_stats` | 2 (10.09, 10.10 — от `oracle.maintenance`, не от людей) |
| `task_jobs` | 19, все `kind=maintenance`, `status=succeeded`, `tg_id` пуст |

`POST /api/chat/ask` и `/api/chat/sonnet` → `401 {"detail":"подпись Telegram не подтверждена"}` — fail-closed работает корректно, просто до него дело не доходит.

Уточнение к past-run: `task_jobs` ≠ 0 — celery-инфраструктура жива, но делает только maintenance. Ни одного пользовательского события нет.

## 6. Артефакты past-run не существуют

- Заявленный коммит `d2e4bbd` — **не найден** (`git rev-parse d2e4bbd` → fatal, ни в одной ветке).
- `reports/2026-10-09-bot-token-placeholder-root-cause.md` — **файла нет**, каталога `reports/` нет; в истории git он никогда не появлялся.
- Work product `356633c4` — `GET /api/work-products/356633c4` → `404 API route not found`; `GET /api/issues/{id}/work-products` → пустой массив.

Итог: предыдущий отчёт остался только текстом в комментарии issue, без файла и без work product. Данный документ закрывает этот пробел.

## 7. Git-состояние

- `dev` = `a2c1d03`, `master` = `d7785f7`. `master` **не является предком** `dev`: в dev есть 1 коммит (`a2c1d03` BUS-1541), в master — 3 (`d7785f7` merge BUS-1511/1527/1533 + `10124cb`, `85c650d` BUS-1166/1232). merge-base = `8c134bf`.
- Расхождение требует merge-cycle по DR 2026-09-12 (dev → master с QA-гейтом).

## 8. Классификация степени блокировки

| Блокер | Кто может снять | Тип |
|---|---|---|
| Реальный `BOT_TOKEN` в `.env` | board/owner (секрет) | board-only |
| `CUSTOM_LLM_BASE_URL` → `host.docker.internal:20128/v1` | DevOps | конфиг |
| Модель продукта: подтвердить/заменить подмену прокси | CTO + DevOps | архитектура |
| Восстановить `.env` (сейчас compose не резолвится) | DevOps/owner | конфиг |
| Merge `dev` → `master` | CTO/QA | процесс |

## 9. Рекомендации

1. **Немедленно:** восстановить `.env` из `.env.production.example` + секреты владельца; без него стек не переживёт рестарт.
2. `CUSTOM_LLM_BASE_URL=http://host.docker.internal:20128/v1` — зафиксировать в `.env`, соответствуя `infra/docker-compose.oci.yml:46-47`.
3. Отдельная задача на подтверждение модели: `oc/claude-sonnet-5` не обслуживается прокси → P0-003 пересертифицировать на фактически отдаваемой модели, либо сменить канал.
4. После правки `.env` — плановая замена `BOT_TOKEN` владельцем + рестарт `bot/worker/beat` + проверка `events>0` и `llm_usage.ok=1`.
5. Не считать BUS-1564 закрытым до предоставления токена: это board-гейт.
