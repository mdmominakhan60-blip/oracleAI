# OracleAI — privacy-safe event dictionary

Этот словарь является контрактом между продуктом, кодом, аналитикой и privacy review. События отвечают на вопрос «какой этап опыта был завершён», но не должны восстанавливать содержание личного разговора.

> **Запрещено во всех product events:** сообщение или его hash, diary text, memory/fact, birth date/time/place, partner data, model answer, payment details, raw Telegram initData, IP, arbitrary URL query, free-form user text и client-supplied event name.

## Общие правила

| Поле | Правило |
|---|---|
| `name` | Только server-owned allowlist из `app/repo/analytics.py`; клиент не может создать новое имя. |
| `tg_id` | Используется только для ownership/cohort queries внутри защищённой БД; не выводится в dashboard export и logs. |
| `surface` | Одно из `bot`, `miniapp`, `admin`, `system`; назначается server-side. |
| `props_json` | Только перечисленные categorical/low-cardinality поля из таблицы ниже. |
| `day` | UTC `YYYY-MM-DD` для агрегирования; не является датой рождения или пользовательским событием. |
| Retention | Детальные `events`, `llm_usage` и `product_cost_events` — rolling 120 дней; дневные агрегаты — отдельно после проверки юридической retention policy. |
| Deletion | Удаление аккаунта удаляет или анонимизирует связанные event rows в соответствии с утверждённой deletion policy. |

## Activation and retention funnel

| Event | Момент | Allowed props | Surface | Owner | KPI |
|---|---|---|---|---|---|
| `miniapp_open` | Сервер успешно обработал `GET /api/me` для владельца. | none | `miniapp` | Product | Open rate, cohort start. |
| ~~`age_confirmed`~~ | ~~Возраст-гейт завершён.~~ Удалено (GAUNTLET v2): возрастная проверка больше не выполняется. | — | — | — | Removed |
| `first_ritual` | Первая успешная отметка дневной практики, не повторная отметка за день. | `surface_action`: `practice_done` | `bot`/`miniapp` | Product | First ritual completion, time-to-first-value. |
| `first_question` | Первый завершённый обычный или crisis-safe вопрос с ответом. | `agent`, optional `safety=crisis` | caller surface | AI/Product | First question completion, first-value rate. |
| `return_d1` | Open on or after UTC day +1 from first Mini App open; atomically recorded once. | `cohort_day`: `1` | `miniapp` | Product | D1 voluntary return. |
| `return_d7` | Open on or after UTC day +7 from first Mini App open; atomically recorded once. | `cohort_day`: `7` | `miniapp` | Product | D7 voluntary return. |

D1/D7 — это milestone пользователя, а не количество открытий. Если пользовательница вернулась на восьмой день, оба milestone могут быть записаны при этом открытии; dashboard должен считать cohort completion, а не складывать rows как sessions.

## Existing product events

| Event | Server-owned props | KPI/use |
|---|---|---|
| `start` | `source` from allowlist | Telegram acquisition and onboarding start. |
| `onboard_done` | `source` from allowlist | Completed bot onboarding. |
| `question` | `agent`, `charge` from server enums | Questions, cost/limit mix. |
| `tarot_draw` | `spread`, `charge` from catalog/server | Tarot completion. |
| `forecast_view` | `channel`: `bot`, `push`, `miniapp` | Daily content reach. |
| `practice_start` | `code` from catalog | Practice intent. |
| `practice_done` | `code`, `streak`, `finished` | Practice completion; not a shame/streak pressure metric. |
| `practice_stop` | `code` from catalog | Voluntary stop and quality review. |
| `limit_reached` | `reason`, `agent` or `spread` from server enums | Friction and paywall diagnostics. |
| `experiment_exposure` | validated `experiment`, `variant` only | Experiment cohort assignment. |
| `profile_update` | list of changed field names, never values | Settings adoption; not profile content. |
| `web_payment` / `payment_success` | plan/sku and provider event category only | Payment completion and recovery. |
| `safety_crisis` | category from safety enum | Safety volume and review; never expose excerpt in analytics. |
| `llm_usage` | provider/model/purpose/tokens/cost/latency/ok | Quality, latency and unit economics; stored separately from product events. |
| `product_cost_events` | Server-owned `event_kind`, `sku`, `catalog_version`, `channel`, `purpose`, `provider`, `model`, `result_category`, `status`, retries, tokens, latency/duration, artifact bytes, bounded cost, order/reference IDs and categorical reason | Product-level variable cost, delivery, refund and support coverage; never user text, question, chart/memory/image payload, payment secret or client-supplied SKU. |
| `paywall_view` | `surface`, optional `result_category`, `price_variant` | Value-first paywall reach; server-owned only. |
| `paywall_choice` | `surface`, `sku`, `price_variant`, `credit_band` | Chosen offer variant; never raw price text or free-form choice. |
| `credit_pack_checkout_started` | `sku`, `channel`, `credit_band` | Crystal pack checkout intent before invoice; server catalog only. |
| `credit_pack_paid` | `sku`, `channel`, `credit_band` | Confirmed crystal pack payment after idempotent grant. |
| `credit_spent` | `sku`, `channel`, `credit_band`, `result_category` | Successful server-side spend followed by entitlement/grant. |
| `credit_balance_low` | `channel`, `reason` | Categorical low-balance threshold; raw balance is excluded. |
| `report_delivered` | `sku`, `result_category` | Successful premium result delivery, not merely entitlement purchase. |
| `refund_requested` | `sku`, `reason` | Server-owned support/refund category; no payment payload or free text. |
| `refund_completed` | `sku`, `reason` | Completed internal state transition after provider/refund workflow. |

## Product-cost ledger

`product_cost_events` is an append-only, server-owned telemetry table. `event_kind` is one of `llm`, `pdf`, `voice`, `tool`, `delivery`, `refund` or `support`; `channel` is one of `bot`, `miniapp`, `web` or `system`; and `status` is one of `succeeded`, `failed`, `delivered`, `refunded` or `pending`. Text-like dimensions are accepted only as bounded low-cardinality tokens containing letters, digits, `_`, `-`, `.`, `:` or `/`; invalid values are dropped or rejected by the repository boundary. The recorder is best-effort so analytics failures cannot fail a paid answer or refund.

The product KPI endpoint groups by `sku` and `channel`, reports variable provider cost, tokens, retries, delivery count, failure count, cost coverage and gross booking Stars from paid server orders. Gross booking is joined by the pair `sku + order.surface` (with missing surface mapped to `system`), preventing the same SKU-level gross value from being repeated across bot and Mini App channel rows. Gross booking is explicitly not net revenue or profit. `net_revenue_estimate` and `contribution_margin_estimate` remain `null` until settlement realization, taxes/withholding, channel refunds/fees, support/tool/voice cost, fixed OPEX and paid marketing inputs are supplied and reviewed.

## Monetization event rules

Monetization events are emitted only from authenticated server-owned transitions. `sku`, `price_variant`, `result_category` and `reason` are validated categorical values; `channel` is an allowlisted surface/channel category. The client cannot submit an event name, grant amount, payment amount, receipt, order payload or arbitrary props. `credit_pack_paid` is not emitted on duplicate webhook delivery, and `credit_spent` is emitted only after the atomic debit/grant transaction succeeds.

## Dashboard definitions

| KPI | Definition | Exclusions |
|---|---|---|
| ~~Age-gate completion~~ | ~~Этап воронки удалён~~ (GAUNTLET v2). Воронка активации начинается с `first_ritual`. | — |
| First ritual rate | Unique users with `first_ritual` divided by cohort users. | Do not count `practice_start` alone. |
| First question rate | Unique users with `first_question` divided by cohort users. | Failed/denied question is not completion. |
| D1 / D7 return | Cohort users with milestone event divided by cohort users with first open. | No push/open pressure interpretation. |
| Fallback rate | `llm_fallback` operational records divided by successful provider completions, segmented by purpose/provider/language outside event table. | Never attach prompt, answer or memory. |

## Review and ownership

The product owner reviews activation and voluntary return weekly. The AI owner reviews `first_question`, fallback and safety segments after prompt/provider changes. The technical owner reviews event retention, deletion, dashboards and alert noise monthly. Any new event requires an entry here, a privacy check, a test, and a documented owner before code merge.
