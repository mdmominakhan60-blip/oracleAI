# ADR-0005 — Адресат внутренних платёжных алертов отделён от ADMIN_ID

**Status:** accepted
**Date:** 2026-09-11
**Task:** BUS-854 (решение CTO в BUS-851, документ plan rev 9a9584a0)
**Owner:** Backend Engineer

## Context

Прод-`ADMIN_ID` принадлежит vip-клиентке. `payment_monitor` отправлял все
внутренние алерты (`critical`/`degraded`) на `settings.admin_id`, но чат
владельца с ботом недоступен → `TelegramError` → `delivered=False` →
`last_alert_at` не обновляется → ретри каждые 10 минут. Канал платёжных
алертов фактически мёртв: реальный инцидент никуда бы не дошёл
(отчёт `Business/reports/2026-09-11-cs-payment-alert-loop-scan.md`).

## Продуктовое правило

**Клиент никогда не является адресатом внутренних операционных алертов**
(платежи, безопасность, сбои). `ADMIN_ID` — это identity владельца продукта
(seed owner в `admins`, admin-scope API, startup-проверка `config.ready`),
а не канал уведомлений; этот смысл менять нельзя.

## Decision

Новый опциональный env **`PAYMENT_ALERT_CHAT_ID`** (int, Telegram chat_id
сотрудника/группы, куда бот добавлен):

- `app/config.py` — `payment_alert_chat_id: int = _int("PAYMENT_ALERT_CHAT_ID", 0)`.
- `app/services/payment_monitor.py` — адресат алерта =
  `settings.payment_alert_chat_id or settings.admin_id`; при обоих нулях
  доставка не выполняется (legacy-поведение).
- Startup-warning (один раз за процесс, при первом тике payment_monitor):
  если адресат не сконфигурирован, алерты уйдут на владельца — напоминание
  задать `PAYMENT_ALERT_CHAT_ID` (mitigation против забытого конфига).
- Прод-конфигурация и верификация доставки — DevOps (BUS-855).

## Alternatives considered

| Вариант | Вердикт | Почему |
|---|---|---|
| A. Заменить `ADMIN_ID` на сотрудника в прод `.env` | Отклонено | `ADMIN_ID` = identity owner: seed owner-админа, admin-scope, панель поддержки. Смена = смена владельца продукта, не починка алертов; ломает админку и seed. |
| B. Только secondary webhook (`PAYMENT_ALERT_SECONDARY_URL`) | Отложено | Код уже есть, но постит кастомный JSON — нужен relay-сервис. Сложнее в эксплуатации; основной канал остался бы мёртвым. Годится как будущий эскалационный канал, не как замена. |
| C. Алерты только в Alertmanager/Grafana | Отклонено | Infra-метрики закрывают не всё (reconciliation-аномалии — бизнес-логика БД), и alertmanager указывал на тот же мёртвый chat_id. |
| D. ✅ Отдельный `PAYMENT_ALERT_CHAT_ID` + fallback | Принято | Минимальное изменение (2 строки кода + env), не трогает identity, решает оба случая (payment_monitor и infra-алерты), тестируемо. |

## Consequences

- `ADMIN_ID` нигде не меняется: seed, admin-scope, идентичность владельца.
- Пока `PAYMENT_ALERT_CHAT_ID` не задан, поведение идентично прежнему
  (fallback на владельца) — миграция не требует одновременного деплоя.
- Retri-гейт доставки (ограничение вечного ретри при недоставке) — отдельная
  задача BUS-850, здесь не входит.
- `ALERT_CHAT_ID` Alertmanager — зона DevOps (BUS-855).

## References

- Решение CTO: BUS-851 (документ plan, rev 9a9584a0).
- DevOps-исполнение: BUS-855. Ретри-гейт: BUS-850.
- CS-отчёт: `Business/reports/2026-09-11-cs-payment-alert-loop-scan.md`.
