# Runbook: подключение Paddle sandbox-ключей на staging (BUS-134)

Статус: **ожидание ключей от board/user** (внешний шаг, см. §1). Инфраструктура
подготовлена: env-шаблон, изоляция, passthrough. После вставки ключей остаётся
рестарт стека и повторный прогон сертификации.

## Роли

| Шаг | Роль |
|---|---|
| §1 получение ключей в Paddle Dashboard | board/user (доступ к Paddle sandbox-аккаунту) |
| §2 вставка в env + рестарт + прогон | DevOps |
| §3 повторная sandbox-сертификация | DevOps |
| F1 refund/chargeback-политика | CFO + Engineering Lead (решение), DevOps — исполнение |

## 1. Что получить в Paddle Dashboard (board/user)

Всё в **sandbox-аккаунте** (sandbox-login.paddle.com, НЕ продовом):

1. **API key** — Developer tools → Authentication → API keys → New API key.
   Формат: 69 символов, `pdl_…apikey_…sdbx_…`. Маркер `sdbx_` = sandbox;
   ключ с `live_` вставлять запрещено (ловится `check_staging_isolation.sh`).
   Показывается один раз — сохранить сразу.
2. **Webhook secret** — Developer tools → Notifications → New destination →
   Webhook. URL: `https://<STAGING_DOMAIN>/api/webhooks/paddle`
   (на локальной репетиции — домен staging по .env.staging). Секрет вида
   `pdl_ntfset_…` выдаётся при создании. Подписать и включить события:
   `transaction.completed` (+ на будущее `adjustment.updated`/`adjustment.paid`
   для F1).
3. **Checkout domain** — Checkout → Website approval. В sandbox дефолтный
   домен одобрен по умолчанию: это и есть `PADDLE_CHECKOUT_URL`
   (`https://<default-sandbox-checkout-domain>`).
4. **Prices** — Catalog → Products: создать продукты и prices для тарифов
   (например `basic`, `vip`), скопировать `pri_…` id. Формат env:
   `vip:pri_XXX,basic:pri_YYY`.

Передача ключей DevOps — через защищённый канал (не чат/не git): board/user
вставляет значения прямо в `infra/staging/.env.staging` (файл в .gitignore),
либо согласованное хранилище секретов.

## 2. Вставка ключей и рестарт (DevOps)

```bash
cd /home/softis/apps/oraclAI/oracleAI/infra/staging
# 2.1 Заполнить новые строки в .env.staging (файл уже содержит блок PADDLE_*,
#     см. .env.staging.example):
#     PADDLE_API_URL=https://sandbox-api.paddle.com
#     PADDLE_API_KEY=pdl_..._sdbx_...
#     PADDLE_WEBHOOK_SECRET=pdl_ntfset_...
#     PADDLE_CHECKOUT_URL=https://<sandbox-checkout-domain>
#     PADDLE_PRICE_IDS=vip:pri_...,basic:pri_...
# 2.2 Изоляция: sandbox-маркер и отличие от прода
bash check_staging_isolation.sh     # ожидаем PASS по PADDLE_* + ISOLATION: OK
# 2.3 Рестарт app-сервисов (env_file читается при старте контейнера)
export IMAGE_TAG="$(cat CURRENT_RELEASE)"
docker compose --env-file .env.staging -f docker-compose.staging.yml \
  up -d --no-deps staging-api staging-worker staging-bot --profile telegram
# (staging-bot можно не трогать, если ещё без токена — он в профиле telegram)
# 2.4 Проверка здоровья
docker compose -f docker-compose.staging.yml ps      # все healthy
curl -sk https://localhost:3443/health               # {"status":"ok"}
```

Примечания:
- Ключи НЕ коммитятся: `.env.staging` в `.gitignore` (строка 72), фиксируется
  только `.env.staging.example` с пустыми значениями.
- В compose все app-сервисы наследуют `env_file: ./.env.staging` — отдельный
  passthrough не требуется.
- Сетевой вызов `services.paddle.create_transaction` идёт на
  `settings.paddle_api_url` (app/config.py:92) — для sandbox это
  `https://sandbox-api.paddle.com`. Ключи live/sandbox невзаимозаменяемы.

## 3. Повторная sandbox-сертификация (DevOps)

Первичный прогон BUS-109 (42/42) шёл против **симулятора** (локальный
aiohttp-сервер вместо Paddle API + генератор подписанных вебхуков).
Для staging-прогона против реального провайдера — отдельный harness
`infra/staging/payments_staging_cert.py` (добавлен BUS-134):

- сетевой: HTTP против staging API + РЕАЛЬНЫЙ вызов `sandbox-api.paddle.com`
  через `checkout_web_plan` (без симулятора и monkeypatch);
- вебхуки подписываются реальным `PADDLE_WEBHOOK_SECRET` из .env.staging;
- без dev-режима: staging работает в `APP_ENV=production` — сценарий не
  использует `dev_user`/`X-Dev-Key` (в отличие от BUS-109);
- сценарии: S0 смоук ключа (GET /event-types), S1 invoice (реальная
  транзакция), S2 payment (реальный секрет), S3 duplicate, S4
  refund/chargeback (журналирование, находка F1), S5 error paths,
  reconciliation (`payments.charge_id` ↔ `webhook_events.event_id`).

```bash
cd /home/softis/apps/oraclAI/oracleAI
# infra/ не входит в образ → скрипт подхватывается из репо через stdin:
docker exec -i oracleai-staging-staging-api-1 \
  python3 - < infra/staging/payments_staging_cert.py
# Без ключей fail-closed: "PADDLE_* не настроены: …". С ключами:
# evidence появится в логах контейнера (/opt/oracle/logs/payments_staging_cert_*.{log,json})
# — скопировать в docs/RELEASE/evidence/ и сослаться в TASKS.md (P0-002).
```

Что проверяем на staging с реальным провайдером (покрыто harness'ом §3):
- S0 смоук: ключ живой (GET /event-types, Bearer);
- S1 invoice: `create_transaction` создаёт `txn_…` против **реального** Paddle
  sandbox (не симулятора);
- S2 payment: реальный вебхук `transaction.completed` с подписью Paddle
  проходит `verify_paddle` на staging-эндпоинте;
- S3 duplicate: повторная доставка не выдаёт второй раз;
- S4 refund/chargeback: adjustment-события журналируются (текущее поведение
  до решения F1);
- S5 error paths: битая/просроченная подпись, чужой transaction_id;
- reconciliation: `payments.charge_id` ↔ `webhook_events.event_id`.

Evidence складывается в `docs/RELEASE/evidence/` (log+json) и ссылается в
`docs/RELEASE/TASKS.md` (P0-002) — по образцу
`payments_sandbox_cert_20260905_064107.{log,json}` (симулятор, BUS-109).

## 4. F1: refund/chargeback-политика — контекст для решения

Текущее состояние кода (проверено на момент BUS-134):
- `app/api/routers/webhooks.py:76` — `GRANTING_EVENTS = {"transaction.completed"}`;
  adjustment-события (refund/chargeback) доходят до `_already_seen`
  (журналируются в webhook_events) и **игнорируются** — entitlement не
  отзывается, доступ сохраняется до конца оплаченного периода.
- `app/services/billing.py:356` `apply_payment` — выдача в одной транзакции с
  пометкой заказа; механизма отзыва нет.

Матрица вариантов для решения CFO + Engineering Lead:

| Вариант | Поведение | Плюсы | Минусы |
|---|---|---|---|
| A. Полный refund/chargeback → немедленный отзыв | отозвать подписку/кристаллы пропорционально | соответствие деньги-доступ | сложнее: отзыв частично потраченных кристаллов, риск UX-конфликтов |
| B. Отзыв только при chargeback, refund — до конца периода | компромисс | проще, less UX-harm | chargeback-конфликты с Paddle остаются |
| C. Статус-кво (журналируем, не отзываем) | доступ до конца периода | нулевые изменения кода | потери на abuse (pay→refund→keep), риск для Paddle-здоровья аккаунта |

Рекомендация DevOps: **B** как первый шаг (минимальная механика: обработать
`adjustment.updated` с action=chargeback → деактивировать подписку), либо
**A** если CFO требует строгого соответствия. Реализация — child-issue для
Backend после вердикта.

## 5. Откат

Обратимость: пустые `PADDLE_*` в `.env.staging` → рестарт app-сервисов →
платёжный контур staging возвращается в состояние «не настроен» (API отвечает,
web-чекout недоступен, isolation-скрипт WARN вместо FAIL). Отдельного отката
образов не требуется — код не менялся.
