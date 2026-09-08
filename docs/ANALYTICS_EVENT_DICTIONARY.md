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
| `miniapp_open` | Сервер успешно обработал `GET /api/me` для владельца. | optional `utm`: ascii-токен из Telegram `startapp` deep-link (pass-through из `X-Start-Param`, server-side валидация, ≤48 символов — `_WEB_SOURCE_LIMIT`, без PII); отсутствие = organic | `miniapp` | Product | Open rate, cohort start, deep-link attribution. |
| ~~`age_confirmed`~~ | ~~Возраст-гейт завершён.~~ Удалено (GAUNTLET v2): возрастная проверка больше не выполняется. | — | — | — | Removed |
| `first_ritual` | Первая успешная отметка дневной практики, не повторная отметка за день. | `surface_action`: `practice_done` | `bot`/`miniapp` | Product | First ritual completion, time-to-first-value. |
| `first_question` | Первый завершённый обычный или crisis-safe вопрос с ответом. | `agent`, optional `safety=crisis` | caller surface | AI/Product | First question completion, first-value rate. |
| `return_d1` | Open on or after UTC day +1 from first Mini App open; atomically recorded once. | `cohort_day`: `1` | `miniapp` | Product | D1 voluntary return. |
| `return_d7` | Open on or after UTC day +7 from first Mini App open; atomically recorded once. | `cohort_day`: `7` | `miniapp` | Product | D7 voluntary return. |
| `session_linked` | Серверная связка анонимной сессии с пользователем: первый аутентифицированный вызов (`GET /api/me`) с заголовком `X-Session-Id`. Записывается один раз на `(session_id, tg_id)`; оба идентификатора — в индексированные колонки `events.session_id`/`events.tg_id`, не в props. | none | `miniapp` | Product | Visit→paid conversion, source attribution of payers (bridge for the top-of-funnel join). |
| `return_d30` | Open on or after UTC day +30 from first Mini App open; atomically recorded once. | `cohort_day`: `30` | `miniapp` | Product | D30 voluntary return. |

D1/D7/D30 — это milestone пользователя, а не количество открытий. Если пользовательница вернулась на 31-й день, сразу три milestone (`return_d1`, `return_d7`, `return_d30`) могут быть записаны при этом открытии; dashboard должен считать cohort completion (COUNT DISTINCT tg_id), а не складывать rows как sessions.

## Web funnel events (visit → signup → activation — EXP-004 / BUS-144, сверка BUS-271)

Нижний ярус воронки до ботового `start`: анонимная сессия на публичной поверхности и регистрация. Связка — по `session_id` (клиентский анонимный sid, колонка `events.session_id`, миграция 0008; частичный уникальный индекс `uq_events_session_name` = идемпотентность per-session). Приём — только через серверный эндпоинт `POST /api/funnel/events` (батч 1–20, rate-limit, pydantic extra=forbid, allowlist имён и props); клиент не создаёт новые имена. Все props — категориальные allowlist-значения, нормализуемые сервером; вне формата — отбрасываются (fail-closed). Детальная схема props: `Business/metrics/funnel-events-schema.md`.

| Event | Момент | Allowed props | tg_id | Surface | Owner | KPI |
|---|---|---|---|---|---|---|
| `visit` | Сервер принял первое событие анонимной сессии на публичной поверхности (лендинг/мини-лендинг); дедуп `(session_id, name)` на уровне БД. | required `source` (`organic`\|`direct`\|`referral`\|`tg`\|`instagram`\|`reddit`\|`email`\|`paid`\|`unknown`), `medium` (`organic`\|`cpc`\|`social`\|`email`\|`referral`\|`none`\|`unknown`); optional `campaign` (ascii-токен ≤64), `path` (путь без query ≤128) | NULL | `web`/`bot`/`miniapp` | Growth/Product | Top of funnel; visit→signup conversion; channel attribution (utm). |
| `signup` | Сервер зафиксировал регистрацию (создание аккаунта); до связки с профилем tg_id — псевдонимный. | same props as `visit` + optional `signup_method` (`telegram`, `miniapp`, ascii-токен ≤32) | optional | `web`/`bot`/`miniapp` | Growth/Product | Registration rate (signup/visit); канал регистраций. |
| `activation` | Сервер зафиксировал ключевое действие активации. | same props as `visit` + required `action`: `first_question` \| `first_ritual` \| `profile_complete` \| `daily_forecast` (несписочное — отказ записи) | optional | `web`/`bot`/`miniapp` | Growth/Product | Activation rate = activation/signup (KPI проекта ≥25% регистраций, organic-growth-engine). |

**Anti-фрод и дедупликация:** `visit` дедуплицируется по `(session_id, name)` — повторные beacon/retry не создают дублей; `activation` по одному sid — одно событие на action. Проп `path` не содержит query-строку (utm и произвольные параметры отбрасываются — «arbitrary URL query» запрещён глобальным privacy-правилом). Имена в allowlist `app/repo/analytics.py` (`E_VISIT`/`E_SIGNUP`/`E_ACTIVATION`).

## Promo redemption (BUS-271 сверка)

| Event | Момент | Allowed props | Surface | Owner | KPI |
|---|---|---|---|---|---|
| `promo_redeemed` | Серверная точка успешного активирования промокода: после идемпотентного `_apply_grant` (`source='promo'`) в `redeem_promo` (billing). Повторное использование того же кода той же клиенткой не создаёт новое событие (dedup таблицей `promo_redemptions`). | `batch` (server-owned значение из `promo_codes.batch`; для беты — `BETA1`, разрез волны беты); `kind`: `plan_days` \| `crystals` \| `product`; **`code` — НЕ в события**: точный код — user-redeemable secret с неограниченной кардинальностью (per-user значение), для разбора живёт в `promo_redemptions` (защищённая БД, admin-only) | `bot` | Product | Redemption rate батча, конверсия промо→активация, разрез волны беты по `batch=BETA1`. |

**Правило `code`-пропа (уточнение против текущей эмиссии):** проп `code` в текущем вызове `billing.py` (`props={"code", "batch", "kind"}`) нарушает низкокардиальное правило словаря — точный промокод есть per-user значение, а `promo_redemptions` уже хранит связку `(code, tg_id)` полностью. Backend-дельта (BUS-172/реализация беты): убрать `code` из props события, оставить `batch`+`kind`. Атрибуция источника пользователя через `users.source = promo:{batch}` (server-side, уже реализовано) не меняется.

## Existing product events

| Event | Server-owned props | KPI/use |
|---|---|---|
| `start` | `source` from allowlist | Telegram acquisition and onboarding start. |
| `onboard_done` | `source` from allowlist | Completed bot onboarding. |
| `question` | `agent`, `charge` from server enums | Questions, cost/limit mix. |
| `tarot_draw` | `spread`, `charge` from catalog/server | Tarot completion. |
| `forecast_view` | `channel`: `bot`, `push`, `miniapp`; optional `tier`: `free` (только при `channel=push`); optional `source`: `push` \| `broadcast` (server-side, G-1) | Daily content reach; push→open атрибуция. |
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

## Feedback survey events

События задаются словарём до реализации кода (инженерный эпик BUS-180): имена войдут в server-owned allowlist `app/repo/analytics.py`, триггер и тест добавляются при реализации. Это три шага одной воронки day-7 опроса: `feedback_survey_sent` (касалась) → `feedback_survey_completed` (ответила) → `survey_grant_issued` (получила бонус). Параметры бонуса — спека BUS-170 §7 rev3 (решение BUS-177, принято CEO: 40✦, `source='review_bonus'`, 90 дней).

| Event | Момент | Allowed props | Surface | Owner | KPI |
|---|---|---|---|---|---|
| `feedback_survey_sent` | Scheduler успешно доставил сообщение day-7 опроса в Telegram-чат (после записи строки `deliveries` `kind='feedback_survey'`). Эмитится на каждое касание — приглашение и одно напоминание; НЕ `track_once`. | `survey_code`: `day7_v1`; `delivery_key`: `day7_v1` (приглашение) \| `day7_v1_remind` (напоминание) — server-owned значение dedup-ключа `deliveries.key` | `bot` | Product | Invitation reach; знаменатель response rate; разбивка invite vs reminder. |
| `feedback_survey_completed` | Сервер принял `POST /api/feedback` и записал ответы в `feedback_responses` (заполнен ≥1 вопрос). Записывается один раз на `(tg_id, survey_code)`: повторный POST отклоняется анти-абьюзом (BUS-170 §5). | `survey_code`: `day7_v1`; `bonus_granted`: `true` \| `false` (пройдены ли гейты бонуса BUS-170 §5.3a/3b — активность и текст ≥50 симв.); `question_count`: целое `1`–`5` (сколько вопросов заполнено) | `miniapp` | Product | Response rate (completed/sent); bonus-grant rate (`bonus_granted=true` / completed); полнота заполнения. |
| `survey_grant_issued` | Серверный триггер в момент успешного идемпотентного гранта бонуса за day-7 опрос: одна транзакция с записью ответов (`feedback_responses`) и `crystal_lot`-грантом (`source='review_bonus'`, `expires_at` = момент гранта + 90d). Не эмитируется при отклонённом POST (анти-абьюз — спека BUS-170 §5) и при повторной выдаче (один бонус на пользователя за всю жизнь). | `survey_code`: `day7_v1`; `bonus_kind`: `crystals_40`; `amount`: `40`; `expires_at`: server-derived ISO timestamp (грант + 90d, совпадает с `expires_at` лота) | `miniapp` | Product | Claim rate, claim→spend за 90d, claim→paid vs baseline (CFO-метрики, BUS-170 §8.1). |

**Сверка naming с постановкой BUS-238 (ревью CEO):**
- `survey_code` (не `survey_kind`) — единое имя с уже принятым `survey_grant_issued` и с колонкой `feedback_responses.survey_code`; значение `day7_v1` из спеки BUS-167 §2 / BUS-170 §3.
- `delivery_key` (не `delivery_id`) — в таблице `deliveries` нет колонки-id (PK `(tg_id, kind, key)`, baseline.sql:147); privacy-safe low-cardinality представление касания — сам dedup-ключ `deliveries.key` (`day7_v1` / `day7_v1_remind`), он и идёт в проп.
- NPS-оценка (`score`) и свободный текст отзыва в `feedback_survey_completed` НЕ пишутся: детальная разбивка ответов (включая NPS 0–10) живёт в `feedback_responses` и просматривается через админ-панель (BUS-168), а событие остаётся воронковым (privacy-правило §«Запрещено во всех product events»). Это уточнение к черновику BUS-167 §4, где `score` числился пропом.

`tg_id` — в авторской колонке `events` (server-owned), не в props. Все props — server-owned значения: клиент не влияет ни на имя события, ни на сумму, ни на `survey_code`. Свободный текст отзыва в события не попадает (спека BUS-170 §5.5).

## CRM lifecycle events (волна 3.6 — BUS-261, гэпы BUS-175 §3)

Контекст: CRM-цепочки (BUS-190: churn_warn → renewal / winback WB1 → WB2) требуют измерения исходов триггеров. Определения гэпов — BUS-175 §1.2 (G-1, G-2), §3 (G-5, G-6, G-9), приоритеты — BUS-183.

### Attribution: push→open (G-1)

Триггеры на стороне Telegram (бот-сообщение с кнопкой Mini App) несут `startapp`-параметр; сервер читает его в момент аутентифицированного запроса и пишет в `miniapp_open.source` / `forecast_view.source` как pass-through из server-owned dispatch-контекста. Значение ставит **сервер из собственного контекста отправки** (scheduler/broadcast знают, что и кому отправляли), не клиент: значение из startapp сверяется с журналом исходящих касаний (`deliveries`/`broadcast_targets`) — расхождение отбрасывается. Клиентский канал не может приписать себе касание. Отсутствие prop = organic-открытие.

**Ограничение:** окно атрибуции = один визит (первый open после касания); повторные open в тот же день не дублируют связь. Это гэп-закрытие первого порядка: связка «конкретная отправка → конкретный open» (per-message) не строится — для неё нужны id-колонки, которых в `deliveries` нет (PK `(tg_id, kind, key)`), а точность per-message для KPI сценариев 3.6 не требуется.

### Events

| Event | Момент | Allowed props | Surface | Owner | KPI |
|---|---|---|---|---|---|
| `renewal` | Серверная точка продления: событие эмитится в момент успешной активации подписки (`_apply_grant` для `plan`/`plan_days` в billing) с указанием, какой CRM-триггер предшествовал ей. Один `renewal` на (tg_id, платеж). | `reason`: `churn_warn` \| `winback1` \| `winback2` \| `organic` — категория триггера, предшествовавшего продлению (server-derived: см. matching-правило ниже); optional `sku`/`plan_code`; optional `promo_batch` (если продление через промокод winback-батча) | `bot` | Product | Payback winback-волн (гейт G2 BUS-197), renewal rate по триггерам, L5. |
| — | **G-5 (winback_sent): закрыто существующим журналом `deliveries`.** Отдельное событие НЕ вводится: отправка winback1 пишется в `deliveries` (kind=`winback`, key=`{sub_until}`) в `_winback` (scheduler.py:377); WB2 по дизайну BUS-190 §4 пишет kind=`winback2`, key=`{sub_until_iso}`. Дедуп и guardrail-частота уже обеспечены `comms.claim`. | `deliveries.kind`, `deliveries.key`, `deliveries.created_at` | `system` | Product | Winback reach и частотные лимиты — прямой SQL по deliveries. |
| — | **G-9 (история CRM-контакций): закрыто существующими таблицами.** Полная история «что клиентке отправляли»: `deliveries` (авто-касания: forecast/weekly/monthly/practice/expiry/winback/winback2/feedback_survey/broadcast), `broadcast_targets` (per-user статус и sent_at рассылок), `user_notes` + `admin_audit` (личные ответы поддержки, admin.py:352-356 — текст уже дублируется в note `[ответ поддержки]`). Отдельная таблица `crm_contacts` из черновика BUS-175 §3 НЕ создаётся — она дублирует эти три источника. | — | — | Product | Guardrail-частота касаний (не более N авто-сообщений/нед. на клиентку), анти-навязчивость. |
| — | **G-6 (эффект broadcast): закрыто связкой broadcast_targets + source=campaign.** Delivery per-user — `broadcast_targets.sent_at` (точно, без нового события); open — существующие `miniapp_open`/`forecast_view` с optional `source`=`broadcast` (G-1-механика) и optional `campaign`=`bc:{broadcast_id}` (categorical, server-side, из контекста отправки). Сравнение рассылок — по `broadcasts.id`. Отдельное delivery/open-событие НЕ вводится. | optional `campaign`: `bc:{broadcast_id}` на `miniapp_open`/`forecast_view` | `miniapp` | Product | Delivery rate (broadcast_targets), open rate (source=broadcast), сравнение рассылок по id. |

### Ограничения и решения

1. **G-9 prune 120 дней** (`comms.prune`, comms.py:53): история авто-касаний старше 120 дней стирается. Для этичной частотной политики достаточно (окна касаний — дни/недели); для «пожизненной» истории — не хватает. Решение: принимаем 120д как достаточное для guardrail; если понадобится дольше — отдельная миграция архивной таблицы (через DevOps), не через события.
2. **Matching-правило `renewal.reason`** (server-derived): в момент продления сервер смотрит на последнее недавнее касание клиентки из `deliveries`: `expiry` в последние 2 дня до платежа → `churn_warn`; `winback` → `winback1`; `winback2` (+или promo из батча `winback_*`) → `winback2`; иначе `organic`. Окно поиска — 30 дней назад от платежа; ничего не найдено → `organic`. Так `reason` — вычисляемый факт кода, не клиентский ввод, и не требует junction-таблицы.
3. **`campaign` в значение не пишем без нужды:** prop `bc:{broadcast_id}` вводится только на событиях, где сервер знает контекст отправки (G-1 pass-through); free-form campaign-строки по-прежнему запрещены.

**Privacy:** `renewal.reason` и `campaign` — categorical, server-owned; `broadcast_id` — числовой id внутренней таблицы, не пользовательский контент. `deliveries.key` содержит `sub_until` (дату) — в события не выносится, остаётся в защищённой БД.

**Реализация:** имена и props добавляются в allowlist `app/repo/analytics.py` Backend Engineer'ом при реализации (BUS-172), сверяясь с этим словарём. `E_RENEWAL = "renewal"` — новое имя; `source`/`campaign` — опциональные props существующих `E_MINIAPP_OPEN`/`E_FORECAST`.

## Dashboard definitions

| KPI | Definition | Exclusions |
|---|---|---|
| ~~Age-gate completion~~ | ~~Этап воронки удалён~~ (GAUNTLET v2). Воронка активации начинается с `first_ritual`. | — |
| First ritual rate | Unique users with `first_ritual` divided by cohort users. | Do not count `practice_start` alone. |
| First question rate | Unique users with `first_question` divided by cohort users. | Failed/denied question is not completion. |
| D1 / D7 return | Cohort users with milestone event divided by cohort users with first open. | No push/open pressure interpretation. |
| Survey response rate | Unique users with `feedback_survey_completed` divided by unique users with `feedback_survey_sent`. | Reminder touches collapse to one recipient (COUNT DISTINCT tg_id), so the denominator is reached users, not messages. |
| Survey claim rate | Unique users with `survey_grant_issued` divided by users who received the survey invitation. | Responses without bonus (anti-abuse gates, BUS-170 §5) are not claims. |
| Claim→spend (90d) | Users spending the granted lot within 90d of `survey_grant_issued`, divided by grant recipients. | Only the granted `review_bonus` lot counts, not user's own crystals. |
| Fallback rate | `llm_fallback` operational records divided by successful provider completions, segmented by purpose/provider/language outside event table. | Never attach prompt, answer or memory. |
| Beta wave DAU | COUNT DISTINCT tg_id с любым событием за UTC-день среди пользователей волны (вход в когорту волны: `promo_redeemed` с `batch='BETA1'` ИЛИ `start` с `source='promo:BETA1'`-семейство / инвайт-лист). Базовая поверхность — daily-агрегаты, не сырые events. | Синтетические tg_id 10001/10002 исключать всегда. |
| Beta activation rate | Уникальные пользователи когорты волны с `first_ritual` или `first_question` (в памяти о D1-окне) / уникальные вошедшие в когорту волны. | Активация = first-value milestone, не `miniapp_open`. |
| Beta funnel visit→signup→activation | Когортная воронка EXP-004 по `session_id` (funnel-trace) — только для web-сессий; ботовая воронка считается отдельно от `start`. | Не смешивать session-воронку (анонимную) с tg_id-воронкой. |
| Survey response rate (beta) | Определение выше («Survey response rate»); для беты — когорта волны, survey_code=`day7_v1`. | Reminder-касания схлопываются в получателя (COUNT DISTINCT tg_id). |
| Promo redemption rate (beta) | Уникальные активации кода батча `BETA1` / количество выданных кодов батча (знаменатель — из `promo_codes`/`promo_redemptions`, не из событий). | Знаменатель — учётная таблица, не события. |
| Error rate (beta-наблюдаемость) | Доля 5xx-ответов API + доля неуспешных LLM-вызовов за день. Источник — операционные логи/`llm_usage`, НЕ product events. | Продуктовые события не предназначены для ops-алертов. |
| LLM ok=0 share | Доля LLM-вызовов с `ok=false` в `llm_usage` за день, по purpose/provider. | Отдельно от error rate API. |
| p50/p95 latency | `percentile_cont` по `llm_usage.latency_ms` за день по purpose/provider. **Реализация — BUS-230 п.3 (F-3)**: owner Backend Engineer, PostgreSQL-only с деградацией на SQLite. Дашборд беты потребляет это, дублирование агрегации не создаёт. | Агрегация — не Analytics-зона; Analytics владеет определением KPI и порогами. |

**Стык BUS-230 ↔ дашборд беты (согласовано BUS-271):** BUS-230 F-3 даёт перцентили p50/p95 как SQL-агрегат в admin-агрегате; дашборд беты (Analytics) потребляет этот агрегат и добавляет DAU волны / activation rate / error rate / llm ok=0 share / redemption rate как KPI-определения из этой таблицы. Отдельного второго перцентиль-агрегата не создаём.

## Review and ownership

The product owner reviews activation and voluntary return weekly. The AI owner reviews `first_question`, fallback and safety segments after prompt/provider changes. The technical owner reviews event retention, deletion, dashboards and alert noise monthly. Any new event requires an entry here, a privacy check, a test, and a documented owner before code merge.
