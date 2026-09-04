# OracleAI Payments UX and Integration

## Что реализовано

Mini App получил отдельную root-вкладку **«Оплата»**. Она не прячется в профиле: пользовательница видит её рядом с «Сегодня», «Диалоги» и «Моё», а swipe-навигация также включает новый экран. Поверх существующей темной космической визуальной системы добавлены hero-блок, баланс Кристаллов, выбор способа оплаты, тарифные карточки и компактные карточки разовых пакетов.

Оплата разделена на два понятных сценария. **Telegram Stars** используется для подписок и любых товаров каталога через существующий server-created invoice. **TON и крипта** отображаются одной группой выбора актива: TON, USDT или BTC. Для этой группы используется существующий Crypto Pay adapter, но теперь invoice создаётся в выбранном asset, а не только как абстрактный USD invoice.

## Server-side safety model

Браузер не является источником цены, entitlement или платёжного статуса. Клиент отправляет только SKU и выбранный allowlisted asset. Сервер сам загружает каталог, проверяет возрастную и пользовательскую авторизацию, создаёт pending order, записывает provider metadata и возвращает ссылку на invoice. Начисление выполняется только через подписанный provider webhook и существующую идемпотентную `apply_payment` boundary.

Для Crypto Pay в order metadata фиксируется `asset`, а webhook проверяет `invoice_id`, `payload`, `status` и совпадение выбранного актива. Неподдерживаемые assets отклоняются сервером. Внешний Crypto Pay invoice настроен как одноразовый, с отключёнными anonymous comments и ограниченным сроком действия.

> TON в текущей реализации принимается через Crypto Pay с asset `TON`. Это сделано намеренно: прямой TON Connect перевод требует отдельного production-grade blockchain monitor, проверки masterchain finality, адреса назначения, суммы и комментария заказа до выдачи entitlement. Такой мониторинг нельзя подменять callback от wallet UI.

## Payment UX principles

Интерфейс показывает цену и смысл покупки до нажатия кнопки. Для Stars пользовательница видит кнопку «Открыть оплату Stars», а для TON/crypto — сначала выбирает актив, после чего каждая карточка показывает выбранную валюту. Состояния loading, temporary failure, retry и order history присутствуют на самом экране; после открытия invoice не создаётся ложное сообщение об успешной оплате.

Копирайт не использует страх, дефицит или обещания гарантированного будущего. Главная ценность формулируется через глубину персонализации, доступ к проводникам и запас Кристаллов, а не через давление «купи сейчас».

## Production checklist

| Gate | Что проверить | Статус локального checkout |
|---|---|---|
| Stars | Telegram test environment: invoice, pre-checkout, `successful_payment`, duplicate delivery and refund charge id | Код использует существующий flow; нужен реальный Telegram E2E |
| Crypto Pay / TON asset | `createInvoice` с `currency_type=crypto`, `asset=TON`, webhook `invoice_paid`, asset mismatch and retry | Unit/API tests проходят; нужен sandbox webhook |
| Other crypto | USDT/BTC invoice, conversion, expiry and provider settlement | API allowlist готов; нужен provider sandbox |
| Production security | Secret rotation, webhook URL, rate limits, backup, monitoring and support/refund process | Не выполняется автоматически в sandbox |
| Legal/product | Terms, refund rules, tax/jurisdiction, product price book and final catalog approval | Требуется решение владельца и юриста |

## References

[1]: https://core.telegram.org/bots/payments-stars — Telegram Bot Payments API for digital goods and services.
[2]: https://docs.ton.org/applications/ton-connect/overview — TON Connect overview and key custody boundary.
[3]: https://docs.ton.org/applications/ton-connect/how-to/send-transaction — TON Connect `sendTransaction` request and comment payload.
[4]: https://docs.ton.org/applications/payments/overview — TON payment processing, off-chain monitoring and masterchain finality.
[5]: https://help.send.tg/en/articles/10279948-crypto-pay-api — Crypto Pay API `createInvoice`, supported assets and invoice fields.
