# Мониторинг платежей и админ-панель

## Что проверяется автоматически

Активный bot process запускает lease-защищённый scheduler tick каждые десять минут. Внутри этого тика payment monitor выполняет bounded read-only проверки и сохраняет в `settings` только агрегированный snapshot. Второй bot process остаётся standby благодаря существующему SQLite lease, поэтому один и тот же alert не должен отправляться двумя владельцами одновременно.

Мониторинг проверяет зависшие `pending`-заказы старше двух часов, неуспешные заказы за последние 24 часа, обработанные webhook events по provider, безопасный failure journal webhook за 24 часа, orphan payments, paid orders без succeeded payment, дубликаты succeeded payments по заказу и расхождение последнего `crystal_ledger.balance` с быстрым балансом пользователя. Raw webhook payload, invoice IDs, Telegram IDs и произвольный текст в snapshot не попадают.

При наличии `CRYPTOBOT_API_TOKEN` monitor выполняет read-only `getBalance`. В snapshot сохраняются только asset и ограниченные строки available/onhold, без token и пользовательских данных. Stars помечены как `bot_polling`, потому что успешная оплата приходит через Telegram `successful_payment`, а Crypto Pay и Paddle — через HTTP webhook. Повторное DEGRADED/CRITICAL уведомление не отправляется чаще одного раза в шесть часов; новое уведомление приходит при переходе состояния или после cooldown. Восстановление до OK отправляет отдельное сообщение владельцу.

Состояния интерпретируются так:

| Состояние | Условие | Реакция |
|---|---|---|
| `OK` | Нет stale pending, ошибок заказов, failure journal и reconciliation anomalies; provider checks не degraded | Ничего не отправляется |
| `DEGRADED` | Есть stale pending/failed orders или provider balance check недоступен | Owner alert с cooldown |
| `CRITICAL` | Есть reconciliation anomaly: orphan payment, paid order без payment, duplicate succeeded payment или ledger mismatch | Owner alert с cooldown; ручная сверка обязательна |

## Как войти в админ-панель через Telegram

Владелец задаётся переменной `ADMIN_ID`. В Telegram нужно открыть чат с ботом и отправить `/admin`. Бот проверяет роль и присылает меню. В production при корректно заданном HTTPS `WEBAPP_URL` кнопка `📊 Панель управления` открывает `WEBAPP_URL/admin` как Telegram Mini App. Веб-панель передаёт Telegram `initData` в `X-Init-Data`; API проверяет подпись HMAC, срок `auth_date`, Telegram user id и роль. Пароль в панели не используется.

Если `WEBAPP_URL` пуст или не начинается с HTTPS, production-кнопка Mini App не показывается; остаётся только callback `📊 Статистика`. Это намеренное fail-closed поведение, а не полноценный вход в панель. Команда `/stats` даёт короткую сводку администратору.

Для локальной проверки используется только `DEV_MODE=1` и query-параметр `?dev_user=<ADMIN_ID>`. Этот режим не должен включаться в production. В браузерном smoke test необходимо открыть `/admin?dev_user=1`, убедиться в успешном gate, загрузке dashboard и `Платёжный контур`, затем выключить DEV_MODE перед деплоем.

## Демо-режим

Кнопка `ДЕМО: выкл.` отображается только owner после успешного `/api/admin/me`. После нажатия она меняет только состояние текущей страницы и запрашивает owner-only `/api/admin/dashboard/demo`. Synthetic response содержит ровно 451 уникального пользователя, 130 повторных плательщиков, 17 дней работы и 17 056 Stars, которые UI показывает ориентировочно как `$328` по своей reference rate `1/52`.

> Демо-режим — это презентационный срез, а не фиктивная запись в product database.

На экране всегда видны маркировка `ДЕМО-РЕЖИМ · тестовые данные` и пояснение, что данные не являются реальными пользователями, заказами, платежами или балансом. Операционный payment-health card остаётся реальным даже при включённом demo, поэтому состояние provider и сверки нельзя случайно принять за demo KPI. Демо endpoint не создаёт users, orders, payments, events, entitlements, balances или webhook rows. Выключение кнопки возвращает обычный `/api/admin/dashboard`.

## Production activation checklist

Перед публикацией необходимо задать `BOT_TOKEN`, `ADMIN_ID`, HTTPS `WEBAPP_URL`, а для web/crypto flows — соответствующие `PADDLE_WEBHOOK_SECRET`, `PADDLE_API_KEY`/price mapping и `CRYPTOBOT_API_TOKEN`. Crypto Pay webhook URL должен быть зарегистрирован в Crypto Pay App; секретный URL path и signature header остаются provider boundary. Paddle webhook destination должен быть настроен на `/api/webhooks/paddle` и доставлять `transaction.completed` с проверяемой подписью.

Для Telegram Stars необходимо пройти реальный pre-checkout → `successful_payment` flow. Для Crypto Pay нужно подтвердить реальный `invoice_paid` flow, баланс и повторную доставку webhook. Для Paddle нужно проверить signed completed transaction и retry behaviour. Эти проверки требуют тестовых или production credentials и не выполняются локальными unit tests. Прямой TON Connect здесь не заявляется как реализованный payment rail: для него отдельно нужны transaction monitor, masterchain finality и reconciliation.

Источники provider facts: [Telegram Bot API][1], [Crypto Pay API][2] и [Paddle Webhooks][3].

[1]: https://core.telegram.org/bots/api "Telegram Bot API"
[2]: https://help.send.tg/en/articles/10279948-crypto-pay-api "Crypto Pay API"
[3]: https://developer.paddle.com/webhooks/overview "Paddle Webhooks"

## Расширенный owner workflow

В payment-health карточке теперь отображается bounded timeline последних webhook events: provider, event kind, received/failed status и время. Payload, invoice ID, Telegram ID и произвольные provider fields не выводятся. Кнопка `Открыть сверку` ведёт в owner-only экран `Сверка платежей`.

Экран reconciliation показывает только безопасные order identifiers и тип аномалии. Owner может запросить повторную server-side сверку конкретного заказа, пометить его `manual_review` и скачать aggregate JSON export. Review action изменяет только bounded metadata заказа и пишет audit event; он не меняет `paid`, `failed`, `refunded`, payment rows или entitlement.

В настройках уведомлений доступны отдельные cooldown для `DEGRADED` и `CRITICAL`, тихие часы и опциональный второй webhook-канал. `PAYMENT_ALERT_SECONDARY_URL` задаётся только через environment; URL не сохраняется в БД и не отображается в admin response. Второй канал получает только text/status summary.

## User payment history и privacy center

Mini App теперь запрашивает `/api/shop/payment-history`, который строит этапы исключительно из server-side order/payment/entitlement records: `created` → `paid` → `entitlement`. Callback `Telegram.WebApp.openInvoice` не считается доказательством успешного платежа; он только инициирует обновление UI.

В профиле добавлен account/privacy center с объяснением anonymization policy, категориями данных и `/api/account/export`. Экспорт ограничен профилем и безопасной историей платежей; raw chats, memory, diary, provider payloads и Telegram identifiers туда не включаются. Удаление аккаунта остаётся явным и необратимым anonymization flow.

## TON finality boundary

Прямой TON Connect по-прежнему не включён. До появления отдельного transaction monitor с проверкой masterchain finality, replay protection, recipient/amount validation и reconciliation нельзя показывать неподтверждённую wallet transaction как успешную. Рабочий путь для TON — Crypto Pay invoice и его server-side webhook.

Официальная документация TON уточняет границу: TON Connect — это протокол подключения dApp к wallet; сам protocol не предоставляет blockchain integration, поэтому приложению всё равно нужен собственный on-chain lookup/verification.[4] `sendTransaction` возвращает broadcast BoC, а не доказательство успешного бизнес-платежа; документация отдельно рекомендует lookup transaction on-chain.[5] Для payment processing нужно проверять включение shardchain transaction в masterchain block перед финальным зачислением.[6]

[4]: https://docs.ton.org/applications/ton-connect/overview "TON Connect overview"
[5]: https://docs.ton.org/applications/ton-connect/how-to/send-transaction "How to send a transaction with TON Connect"
[6]: https://docs.ton.org/applications/payments/overview "TON payment processing overview"

Для ссылок на кабинеты provider можно задать `TELEGRAM_STARS_DASHBOARD_URL`, `CRYPTOBOT_DASHBOARD_URL` и `PADDLE_DASHBOARD_URL`. Сервер принимает только HTTP(S) URL без username/password, обрезает длину и отдаёт их как обычные external links с `noopener noreferrer`; если переменная не задана, кнопка не отображается.

## Security audit privacy/reconciliation and provider status — 2026-08-27

Проведён отдельный аудит новых endpoint-ов `/api/account/privacy`, `/api/account/export`, `/api/account/delete`, `/api/admin/reconciliation*` и `/api/admin/payment-notifications`. Privacy routes используют signed Telegram identity через `current_user`; deletion требует отдельное `confirm=true` и write rate limit. Export/privacy responses теперь имеют `Cache-Control: no-store`, `Pragma: no-cache` и `X-Content-Type-Options: nosniff`; export дополнительно ограничен read rate limit. Reconciliation routes защищены router-wide admin rate limit и server-side owner check; `order_id` ограничен положительным 32-bit integer. Export сверки содержит только aggregate status/provider states/counters, без order IDs, payloads, Telegram IDs и secrets.

В ходе аудита обнаружено и исправлено хранение raw provider bodies: прежний idempotency journal записывал первые 8 KB Paddle/Crypto Pay payload в `webhook_events.payload`. Теперь event ID/kind/provider сохраняются для idempotency/timeline, а payload всегда `NULL`. Named migration `2026_08_webhook_payload_redaction` очищает legacy rows; account anonymization также очищает любые оставшиеся legacy webhook bodies, даже если provider payload не содержит `tg_id`.

Для Crypto Pay исправлены две интеграционные ошибки. Webhook HMAC теперь использует SHA256(app token) как ключ и подписывает непроцессированное тело запроса; outbound API использует официальный `Crypto-Pay-API-Token` header. Invoice IDs, Paddle event IDs и event kinds ограничены и валидируются, malformed JSON shapes получают bounded 400, а Crypto Pay analytics больше не сохраняет invoice ID. Логи webhook больше не выводят Telegram ID/provider invoice ID. Health monitor остаётся read-only: `getBalance` не меняет orders, payments, entitlements или ledger.

Persisted notification settings и order `meta_json` теперь нормализуются безопасно: повреждённые часы/cooldown откатываются к defaults, строка `"false"` не превращается в truthy boolean, а malformed/list metadata не вызывает `AttributeError` при recheck. Общий response cache middleware больше не перезаписывает endpoint-specific `no-store`.

По состоянию репозитория отсутствуют tracked production log files или live provider delivery records. Проверены только код, тестовые fixtures, миграции и документация. Реальные Crypto Pay/Paddle credentials, dashboard delivery history, webhook retries, balance calls и provider logs в этой среде недоступны и не имитировались.

Official provider contracts used during audit: Crypto Pay API documents `Crypto-Pay-API-Token`, SHA256-derived webhook HMAC and webhook retry/disable behavior; Paddle documents notification-destination-specific secrets, raw-body HMAC and `transaction.completed` fulfillment. Production sandbox evidence remains an external release gate.
