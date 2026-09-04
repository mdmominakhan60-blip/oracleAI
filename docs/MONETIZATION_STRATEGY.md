# OracleAI — стратегия монетизации

**Дата исследования:** 27 августа 2026 года, GMT+3.
**Статус:** аналитическая рекомендация и техническое задание следующего этапа; цены, лимиты и платёжные механики ниже **не внедрены** и требуют одобрения владельца, финансово-юридической проверки и controlled experiment.
**Автор:** Manus AI.

> Главная рекомендация: запускать не «безлимитного AI-астролога», а честную гибридную модель **подписка + фиксированные кредиты за глубокие результаты**. Бесплатный слой должен завершать первый полезный ритуал, подписка — давать регулярную привычку, а кредиты — оплачивать редкие дорогие действия: полные отчёты, синастрию, длинные прогнозы, расширенное Таро и подарочные результаты.

## 1. Executive Summary

OracleAI уже имеет рабочую коммерческую основу: планы, Telegram Stars, Paddle web-flow, разовые продукты, кристаллы, entitlements, идемпотентные заказы и журнал LLM usage. В seed-каталоге есть уровни `guide` за $9.99, `vip` за $24.99, годовой `vip_year` за $179 и `concierge` за $99; однако это **seed defaults**, а не доказанная рыночная или net-revenue цена. Администратор может менять каталог, а актуальным перед публикацией считается live database/admin export, не файл seed [11].

Наиболее подходящая следующая модель — **Hybrid B**:

| Слой | Рекомендация | Роль в экономике |
|---|---:|---|
| Free | 3 коротких вопроса в неделю после первого законченного ритуала; одна базовая карта и дневной инсайт | Доказать ценность и сформировать привычку, не оставляя пользователя без результата |
| Plus | **$19.99/месяц** или **$199.90/год** | Предсказуемый MRR, регулярный чат, 50 включённых deep credits, 2 PDF в месяц |
| Power | **$29.99/месяц** или **$299.90/год** | Более высокий retention и регулярная работа с несколькими агентами, 180 включённых deep credits, 5 PDF |
| Credit pack S | 50 credits за **$9.99** | Низкий барьер для первого углубления |
| Credit pack M | 150 credits за **$24.99** | Основной импульсный, но прозрачный повторный пакет |
| Credit pack L | 400 credits за **$59.99** | High-intent пакет для power users и подарочных отчётов |

При таком дизайне вовлечённый пользователь может добровольно потратить $50–100 в месяц через конкретное использование, а не через скрытое ограничение. Примеры: `$19.99 + $24.99 + $24.99 = $69.97`; `$29.99 + $59.99 = $89.98`; или `$9.99 + $59.99 = $69.98` без обязательной подписки.

Публичные аналоги подтверждают, что рынок уже использует разные механики: Co-Star совмещает подписку Pro-Star с отдельными вопросами, отчётами и расширенными картами; The Pattern продаёт необязательный Go Deeper+ от $14.99/месяц; CHANI — $11.99/месяц или $107.99/год; Sanctuary совмещает подписку, introductory reading и оплату консультаций по времени; Nebula сочетает premium tiers с chat balance; Steer занимает противоположную free/unlimited позицию; Labyrinthos оставляет базовые чтения бесплатными и монетизирует AI readings/decks [1] [2] [3] [4] [5] [6] [7]. Эти цены являются публичными storefront/first-party anchors, а не наблюдаемым ARPU.

Экономика LLM сама по себе не является главным ограничением: при текущей внутренней модели `gpt-5-mini` рутинное сообщение с 3 000 input и 500 output tokens оценивается в $0.001750, а глубокий вызов `gpt-5` с 10 000 input и 1 800 output — в $0.030500 [12]. Основной риск — не токены, а net settlement, налоги, refunds, поддержка, acquisition и качество повторных покупок. В проекте LLM costs логируются, но PDF-rendering, settlement deductions, tax, support и CAC ещё не образуют полного reviewed contribution ledger [9] [10].

**Решение для владельца:** одобрить или отклонить Hybrid B, подтвердить $19.99/$29.99 и credit packs, выбрать основной платёжный канал и разрешить только reversible soft launch. До этого не менять действующие подписки, цены существующих entitlements или платёжную логику.

## 2. Аудит текущего состояния монетизации

### 2.1. Что уже работает

Текущий проект поддерживает три коммерческих контура.

| Контур | Как работает сейчас | Что важно для стратегии |
|---|---|---|
| Telegram Stars | Order создаётся до оплаты; после `successful_payment` выполняется idempotent grant; charge ID сохраняется | Для digital goods в Telegram нельзя исходить из произвольной валютной схемы; необходимо сверять фактический settlement и региональные условия |
| Paddle web | Сервер создаёт transaction из trusted `price_id` и custom data, затем webhook выдаёт план | Подходит для web-подписок, но credit-first web selling ещё не является готовым продуктовым контрактом |
| Internal crystals | Баланс и `crystal_ledger` изменяются атомарно; есть entitlements и expiry | Технически близко к кредитной модели, но смысл кристалла, price book и cost budget пока не унифицированы |

Платёжные заказы, entitlements, payments, crystal ledger и LTV уже представлены в схеме. Существующие safeguards — order-before-payment, idempotent webhook, server-owned grant resolution, atomic balance spend и refund status — нельзя ослаблять в следующей реализации [8] [9].

### 2.2. Что продаётся в seed-каталоге

| Объект | Seed price | Лимит/грант | Комментарий |
|---|---:|---|---|
| `guide` | $9.99 / 550 Stars | 1 вопрос в день, +20 crystals, карта, Matrix, дневник | Низкий recurring anchor |
| `vip` | $24.99 / 1,300 Stars | 3 вопроса в день, +50 crystals, все расклады, синастрия | Средний anchor |
| `vip_year` | $179 / 8,900 Stars | 365 дней, +300 crystals | Несогласован с типичной 20–30% annual discount логикой; требует пересмотра |
| `concierge` | $99 / 5,200 Stars | до 30 вопросов в день, +200 crystals, priority/audio | High-ticket anchor; «безлимит» фактически ограничен 30 вопросами |
| `spread_one` | 75 Stars / 10 crystals | 1 карта, 30 дней | Разовая покупка |
| `spread_celtic` | 450 Stars / 60 crystals | 10 карт, 30 дней | Более дорогой и потенциально более дорогой по LLM результат |
| `report_natal` | 690 Stars / 90 crystals | Полный natal report | Cost allocation и value framing требуют измерения |
| `question_5` | 250 Stars / 35 crystals | +5 вопросов, 30 дней | Уже существующий credit-like product |
| `crystals_100/250/600` | 550/1,150/2,250 Stars | 100/250/600 crystals | Внутренняя валюта без единого публичного price book |

Сведения выше взяты из seed-каталога и не означают, что именно эти значения сейчас видны покупателю. Seed использует `INSERT OR IGNORE`, поэтому live catalog должен быть выгружен перед любым pricing decision [11].

### 2.3. Какие данные для unit economics уже есть

| Данные | Наличие | Ограничение |
|---|---|---|
| LLM provider/model | Есть в `llm_usage` | Сейчас `cost_usd` — estimate по rate card, не provider invoice |
| Input/output tokens | Есть в `llm_usage` | Нужно связать purpose и SKU/result type для product-level cost |
| Latency и success | Есть | P95/p99 и retry attribution требуют operational dashboard |
| Orders/payments/refunds | Есть | Net settlement, tax, chargeback и reconciliation отсутствуют как reviewed inputs |
| Stars revenue | Есть в native Stars | Gross booking нельзя выдавать за profit |
| Usage frequency | Вычисляется из events/messages/readings/diary | Нужны когорты платящих, repeat purchase и rolling-30-day ARPPU |
| PDF cost | **Нет отдельного ledger** | Нужны render duration, artifact bytes, storage/egress и failure/retry tags |
| Voice/tool/support cost | Частично/нет | Нужны provider statements и allowlisted cost events |
| CAC | Нет | До soft launch нельзя использовать paid acquisition как доказанный input |

**Срочная задача для следующего технического этапа:** начать логировать product-level unit costs. Минимальный event/ledger contract должен связывать `sku`, `price_variant`, `channel`, `purpose`, `model`, input/output tokens, retries, latency, PDF render milliseconds, artifact bytes, result delivery, refund и support category — без хранения текста, birth data, memory facts или payment secrets.

## 3. Конкурентный анализ

Цены ниже — US App Store/official web snapshots, проверенные 26 августа 2026 года UTC, если не указано иное. Они могут меняться по стране, платформе, налогам, introductory offers и локализации. ARPU в открытых источниках не найден в надёжной сопоставимой форме, поэтому не выдумывается.

| Продукт | Модель | Цена/тарифы | Что ограничено в free | Триггеры апсейла | Оценка ARPU |
|---|---|---|---|---|---|
| **Co-Star** | Гибрид: free + subscription + pay-per-feature | Pro-Star monthly $8.99; 5 Questions $2.99; 10 Questions $4.99; 25 Questions $6.99; Year Ahead $11.99; Advanced Chart Self/Relationships $8.99; Eros $6.99 | Listing не раскрывает полный free cap; базовый продукт отмечен Free | Ограниченные вопросы, advanced charts, relationship/self reports, year-ahead | Н/Д; storefront prices are not ARPU [1] |
| **Nebula** | Subscription + chat balance + paid relationship/reading features | Visible products include Premium $7.99/$29.99/$39.99/$49.99 variants, $9.99 Chat Balance, $4.99 Relationship Check-In | Точный free cap не раскрыт в listing | Daily secrets, relationship check-in, chat balance, psychic/palm/Tarot breadth | Н/Д; periods for some variants need device verification [2] |
| **Sanctuary** | Subscription + pay-per-reading + time-based human consultation | Sanctuary+ $14.99 monthly / $49.99 annual; intro readings $4.99; Tarot 10 min $29.99; Psychic 10 min $49.99; paid reading $19.99 | Free app with paid reading entry; exact free message cap not disclosed | 5-minute intro, choose reader/duration, live human reading, Tarot/astrology/psychic | Н/Д; consultation GMV is not ARPU [3] |
| **The Pattern** | Free app + optional recurring Go Deeper+ | Go Deeper+ from $14.99/month | Listing describes many free surfaces but not the exact paywall split | Depth of personality, transits, relationships, collections, audio, Connect | Н/Д [4] |
| **CHANI** | Premium subscription with trial, monthly/annual | $11.99/month; $107.99/year, explicitly 25% off monthly equivalent; 14-day monthly or 30-day annual trial | Trial/new-user boundary and free/premium content are documented; full feature split varies by app surface | Transits paywall, detailed chart, workshops, meditations, affirmations | Н/Д [5] |
| **Steer** | Free/unlimited positioning; no paywall | Official site claims unlimited free Vedic questions in ChatGPT, no per-question fee, no ads, no paywall; separate app/API surfaces | No paid restriction claimed on core ChatGPT surface | Trust, Vedic depth, app/API expansion rather than paywall | Not applicable as paid ARPU benchmark [6] |
| **Labyrinthos** | Free/ad-free Tarot + optional AI readings/decks/physical products | App Store marks Free with IAP; search listing lead shows Unlimited Personalized Readings $9.99, but full purchase list not visible in page | Basic readings, learning, journals and free decks are emphasized as available | AI reading, premium decks, 70+ spreads, courses, physical decks | Н/Д; $9.99 is a lead, not a fully verified current price [7] |
| **AstroMatrix** | Low-price subscription + lifetime license + ads/full-version positioning | Visible variants: monthly $2.49, quarterly $19.99, 6-month $9.99, annual $14.99/$27.99/$39.99, lifetime $24.99/$34.95/$49.99, weekly $9.99 | Listing does not provide a canonical free cap; multiple variants suggest localized/legacy price records | Remove ads, unlock full chart/database, lifetime license | Н/Д; prices are a range benchmark, not one current tariff [8] |
| **AstroTalk / human marketplace analogue** | Marketplace + per-minute or per-session expert consultations | Public site positions first call/free trial and paid experts; exact provider rates vary | Introductory free call/credit mechanics may apply | Human expert choice, urgency, personal attention, repeat consultation | Н/Д; marketplace GMV is not comparable without take rate |

### 3.1. What appears to work

The strongest repeatable pattern is **free first value followed by a visible depth boundary**. Co-Star and Sanctuary demonstrate two different upsell routes: discrete feature/report purchases and a human-service ladder. CHANI and The Pattern show that editorial depth, not raw AI tokens, is the subscription value proposition. Nebula demonstrates the commercial potential of broad surface area plus chat balance, while Labyrinthos demonstrates that an ad-free free layer can support optional AI/deck purchases. Steer is the useful counterexample: free/unlimited can be a positioning advantage, but it does not by itself validate paid ARPU.

The product should therefore combine personalization, continuity, evidence and calm presentation, not fear. FOMO, warnings about a partner, false rarity or claims that a larger purchase improves accuracy are prohibited. Astrology and Tarot must be framed as reflection and interpretation, not guaranteed outcomes.

## 4. Three alternative business models

### 4.1. Variant A — subscription-only

| Plan | Proposed price | Included monthly limits |
|---|---:|---|
| Free | $0 | 3 short questions/week, daily card, one basic natal overview, 1 Tarot one-card reading/week |
| Plus | $14.99/month or $149.90/year | 60 short questions, 6 deep interpretations, 1 full natal PDF, 2 relationship/Tarot spreads, all core agents |
| Premium | $29.99/month or $299.90/year | 180 short questions, 20 deep interpretations, 3 PDFs, full Tarot/synastry/transit catalog, priority queue |
| Studio/Concierge | $59.99/month or $599.90/year | 400 short questions, 45 deep interpretations, 6 PDFs, audio/priority, no true unlimited claim |

**Psychology.** The user pays for continuity and peace of mind: the product becomes a recurring personal reflective space rather than a sequence of surprise purchases. A visible monthly allowance makes the value understandable and avoids pay-per-message anxiety.

**Economics.** Subscription-only is predictable for MRR and easier to explain, but it caps high-intent users unless the top tier is expensive. The user who wants one annual report but not monthly habit may refuse to subscribe. A 30-day cap or “unlimited” wording also creates cost runaway risk.

**Risks.** The free tier can feel artificially crippled if the user cannot complete one meaningful result. The top tier needs a hard usage/cost budget even if marketing says “priority”. Annual price must be a real discount, not an inflated anchor. This model is preferable if early cohort data shows high monthly repeat usage and low refund/support burden.

### 4.2. Variant B — hybrid subscription + credits

| Layer | Proposed price | Included value |
|---|---:|---|
| Free | $0 | 3 short questions/week, daily insight, basic chart, 1 starter Tarot/week |
| Plus | $19.99/month or $199.90/year | 120 short questions, 50 deep credits, 2 PDFs/month, core agents |
| Power | $29.99/month or $299.90/year | 300 short questions, 180 deep credits, 5 PDFs/month, advanced product access |
| Credit S | $9.99 | 50 credits |
| Credit M | $24.99 | 150 credits |
| Credit L | $59.99 | 400 credits; exact bonus must be separately displayed if added |

**Suggested credit menu.** A short deep follow-up costs 8 credits; one-card Tarot costs 5; three-card Tarot 12; Celtic/large Tarot 25; natal PDF 60; synastry 75; monthly transit report 45; annual/solar report 90; audio reformat 15. Existing basic facts and safety guidance never become credit-gated.

**Psychology.** Subscription gives belonging and regularity; credits preserve user control and map payment to a concrete high-value outcome. A user can buy one important report without committing, while a power user can spend $50–100 because each incremental purchase has an understandable reason.

**Economics.** This is the best balance of MRR, high-intent peaks and cost control. Credits form a natural circuit breaker: expensive outputs can have explicit budgets, and the product does not need to pretend that unlimited generation is free. It also reuses the current crystals/entitlements architecture, though a versioned price book and clearer naming are required.

**Risks.** Internal currency can become opaque or manipulative. The interface must show exact price, paid credits, bonus credits, action cost, result format, restore path, refund/support path and what remains free before checkout. Credits must never be randomized, expire unexpectedly, or imply better accuracy.

### 4.3. Variant C — pay-per-value without mandatory subscription

| Product | Proposed price | Scope |
|---|---:|---|
| Natal starter report | $9.99 | Verified chart facts, selected interpretation, no false house claims in date-only mode |
| Full natal PDF | $24.99 | Full exact-time report with chart image and evidence/limitations |
| Couple compatibility | $29.99 | Owner-scoped partner consent, synastry/composite evidence and interpretation |
| Annual transit report | $39.99 | Bounded year-ahead themes and dates, not deterministic predictions |
| Tarot deep spread | $7.99–$14.99 | One concrete question, persisted draw and full interpretation |
| Gift bundle | $49.99 | One report plus a recipient gift flow with explicit consent and recovery |

**Psychology.** The user pays for a meaningful moment: a new relationship, birthday, career decision or one unresolved question. There is no subscription anxiety, and the price can be compared with a human reading.

**Economics.** Cash receipts can spike around seasonal moments, but MRR and retention are weak. The product needs strong repeatable occasions, referrals and product progression. A low entry report may be contribution-positive only if its scope and LLM budget are tightly bounded.

**Risks.** One-off users may never return; paid acquisition is dangerous without cohort LTV. A catalog of too many unrelated products creates choice overload. The user can interpret a high one-off price as a guarantee of correctness, so the result must clearly state its reflective nature and limitations.

### 4.4. Comparison

| Criterion | A: subscription-only | B: hybrid | C: pay-per-value |
|---|---:|---:|---:|
| Predictable MRR | High | High/medium | Low |
| High-ticket potential | Medium | High | High |
| Cost control | Medium | High | High per SKU |
| First purchase friction | Medium/high | Low/medium | Low for single result |
| Refund/entitlement complexity | Medium | High | Medium |
| Fit for current OracleAI code | Medium | High after price-book work | High for reports, lower for retention |
| Recommended now | No | **Yes** | Keep as fallback/entry lane |

## 5. Recommended Hybrid B for a $50–100/month power user

### 5.1. Price ladder and credit budget

The recommended public hypothesis is **Plus $19.99/month + credit packs**. The $19.99 price is deliberately above low-cost astrology subscriptions because OracleAI combines multi-agent chat, natal calculation, Tarot, memory, diary and reports. It remains below a recurring human consultation and can be tested against CHANI/The Pattern/Sanctuary anchors [3] [4] [5].

| SKU | Customer price | Credits | Implied price/credit | Primary role |
|---|---:|---:|---:|---|
| Plus | $19.99/month | 50 deep credits included | $0.40 of subscription value/credit before chat/PDF allocation | Entry recurring plan |
| Power | $29.99/month | 180 deep credits included | $0.17 before allocation | High-retention plan, still budgeted |
| Credit S | $9.99 | 50 | $0.20 | First top-up |
| Credit M | $24.99 | 150 | $0.17 | Core top-up |
| Credit L | $59.99 | 400 | $0.15 | Power/gift top-up |

Annual plans should offer 2 months free, not a misleading “up to” discount: Plus $199.90/year and Power $299.90/year. The final channel price must be represented in `channel`, `currency`, `display_price`, `price_stars`, `credit_qty`, `bonus_qty`, `effective_from` and `catalog_version`. Telegram Stars and Paddle should not be assumed to have one universal USD conversion or fee.

### 5.2. User paths to $50–100

| Path | Monthly basket | Total | Concrete value |
|---|---|---:|---|
| Deep natal + relationship month | Plus $19.99 + two Credit M packs $24.99 each | **$69.97** | Full natal PDF, synastry, several Tarot/deep follow-ups and a gift/report reserve |
| Power user | Power $29.99 + Credit L $59.99 | **$89.98** | 180 included deep credits plus 400 top-up credits for monthly transit, synastry, Tarot and reports |
| Non-subscriber high-intent | Credit S $9.99 + Credit L $59.99 | **$69.98** | One first deep result followed by a larger bounded package; no subscription required |
| High-intent but controlled | Plus $19.99 + Credit M $24.99 + one additional deep report $9.99 equivalent | **$54.97** | Regular chat plus one natal/synastry result and a short repeat action |

These examples are **basket hypotheses**, not a conversion forecast. A user should be able to stop after one purchase, keep the delivered result, recover the receipt and continue using free features. The product should never hide the cheaper path or use a countdown to force the larger basket.

### 5.3. Ethical engagement and upsell mechanics

| Mechanic | Honest implementation | Prohibited implementation |
|---|---|---|
| Daily habit | Free daily short insight and lunar context; expand only after the user asks | Fake “rare alignment” or alarming push notification |
| Progressive disclosure | Show basic chart facts, a real sample of deeper sections and exact credit price | Deliberately useless free result or hidden missing sections |
| Event-based return | Notify only for real, user-relevant transits/moon events; explain the event | Claim that a transit guarantees a breakup, promotion or financial result |
| Gift/referral | Gift a specific report or credits with recipient consent and idempotent recovery | Auto-enrolling recipient, multi-level rewards or hidden sender data |
| Annual plan | Show monthly equivalent, total charge and 2-month saving plainly | Countdown, preselected annual renewal, ambiguous “best value” |
| Low balance | Tell the user the exact remaining credits and offer free alternative | Artificially interrupting crisis/safety support or hiding balance |
| Deep-result preview | Show sections, evidence boundary, time/precision state and result format | “Pay to learn the truth” or pay-to-improve accuracy |

## 6. Unit economics and margin model

### 6.1. Basis and formulas

The project’s internal `PRICING` table currently estimates cost per 1M tokens as follows: `gpt-5-mini` $0.25 input / $2.00 output, `gpt-5` $1.25 / $10.00, `gpt-5.5` $5.00 / $30.00, and `text-embedding-3-small` $0.02 input [12]. Public rate cards are a benchmark; provider invoices and actual usage remain authoritative. Current official pages expose additional model families and should be rechecked at implementation time [13] [14].

`LLM cost = input_tokens × input_rate / 1,000,000 + output_tokens × output_rate / 1,000,000`

`Contribution = gross price × net cash factor − variable COGS`

`Contribution margin = Contribution / gross price`

The **net cash factor** is deliberately a sensitivity variable. It combines platform/provider deductions, taxes/withholding and refund reserve only for planning. It is not a claim that Telegram or Paddle deliver a fixed percentage. Telegram’s terms and payment documentation require channel-specific verification [15] [16].

### 6.2. Planning cost cases

| Action | Model/rate | Token budget | Estimated LLM cost |
|---|---|---:|---:|
| Routine chat | gpt-5-mini $0.25/$2.00 | 3,000 in + 500 out | **$0.001750** |
| Deep interpretation | gpt-5 $1.25/$10.00 | 10,000 in + 1,800 out | **$0.030500** |
| Premium fallback | gpt-5.5 $5/$30 | 10,000 in + 1,800 out | **$0.104000** |
| PDF render/storage | Planning assumption | 1 render + temporary artifact | **$0.020000** |

The PDF number is a planning placeholder because no dedicated PDF-cost ledger exists. It must be replaced with measured render CPU/time, storage/egress and failure retry cost. The same applies to voice, tools, support, referrals, taxes and refunds.

### 6.3. Monthly payer scenarios

| Scenario | Usage assumption | LLM + PDF | Other variable reserve | Total variable COGS |
|---|---|---:|---:|---:|
| Light | 40 routine, 1 deep, no PDF | $0.101 | $0.25 | **$0.351** |
| Medium | 100 routine, 5 deep, 1 PDF | $0.333 | $0.75 | **$1.083** |
| Power | 120 routine, 10 deep, 2 PDF | $0.515 | $0.80 | **$1.315** |
| Stress | 120 routine, 10 premium fallback deep, 2 PDF | $1.250 | $1.50 | **$2.750** |

Other variable reserve is a planning assumption for voice/tools/retries/support/referrals. It is not observed COGS. The code already logs LLM calls, tokens, latency, success and estimated cost; it does not yet log all the other rows needed to validate these reserves [9] [10].

### 6.4. Margin sensitivity

Using the power scenario’s buffered direct cost of **$0.666** before support/refund/platform assumptions, the price sensitivity is:

| Gross basket | 15% net deductions | Contribution / margin | 30% net deductions | Contribution / margin |
|---:|---:|---:|---:|---:|
| $9.99 | $8.325 net | **$7.659 / 76.7%** | $6.993 net | **$6.327 / 63.3%** |
| $19.99 | $16.992 net | **$16.326 / 81.7%** | $13.993 net | **$13.327 / 66.7%** |
| $24.99 | $21.242 net | **$20.576 / 82.3%** | $17.493 net | **$16.827 / 67.3%** |
| $59.99 | $50.992 net | **$50.326 / 83.9%** | $41.993 net | **$41.327 / 68.9%** |
| $89.98 | $76.483 net | **$75.817 / 84.3%** | $62.986 net | **$62.320 / 69.3%** |

This reveals an important guardrail. At a 30% all-in deduction, the stated 70–80% margin target is not achieved by the $9.99 or $19.99 subscription if power-user cost is allocated to that one basket. Either the effective factor must be measured, direct variable reserve reduced by routing/caching, or expensive deep actions must remain credit-funded. The model therefore recommends **budgeting deep credits separately** and not promising unlimited premium generation.

### 6.5. Break-even

For a simple fixed-cost model, `break-even payers = monthly fixed costs / contribution per payer`. The following illustration uses $2,000 or $5,000 monthly fixed OPEX and contribution per payer of $17.49, $48.40 or $69.30. These are planning figures, not current company expenses.

| Fixed OPEX | $17.49 contribution | $48.40 contribution | $69.30 contribution |
|---:|---:|---:|---:|
| $2,000/month | 115 payers | 42 payers | 29 payers |
| $5,000/month | 286 payers | 104 payers | 73 payers |

A real break-even model must include fixed hosting, contractor/payroll, legal/accounting, support tooling, payment reserve and acquisition. No paid marketing should be approved until contribution, refunds and repeat purchase are observed for at least 50–100 successful payers.

### 6.6. Why the model can still reach $50–100 honestly

The target basket is not justified by high LLM cost. It is justified only if the user receives several concrete, bounded, recoverable outcomes: a full natal report, a consented compatibility report, a monthly transit report, several Tarot interpretations, or a gift. The product should use cheaper models for routine chat, reserve main/premium models for explicit deep actions, cap retries, cache only safe stable context and record cost by purpose. If measured COGS or refunds exceed the target, lower included limits or increase action prices before advertising—not after a hidden loss has accumulated.

## 7. Open questions and risks requiring owner approval

| Decision | Why it blocks implementation | Required answer |
|---|---|---|
| Choose model A/B/C/Hybrid | Determines catalog, entitlement semantics and paywall UX | **Recommendation: Hybrid B** |
| Approve prices | Prices are hypotheses, not observed willingness-to-pay | Approve/reject $19.99, $29.99, $9.99, $24.99, $59.99 |
| Primary payment channel | Telegram Stars and Paddle have different compliance, settlement and UX | Choose Telegram-first, Paddle-first or both with channel price book |
| Entity/jurisdiction/tax | Net revenue and digital goods treatment depend on actual entity and country | Finance/legal review required |
| Stars realization | Gross Stars are not net cash | Provide settlement export and effective factor by region/device/date |
| Refund/chargeback reserve | Contribution can be overstated without reversals | Provide observed refund/chargeback policy and data |
| Existing plans | Seed prices are not necessarily live and existing entitlements must not change | Freeze legacy rights during experiment |
| Cost budgets | Current PDF/support/tool costs are incomplete | Approve measurement schema and per-SKU max cost |
| Target geography | Store prices and conversion vary by country | Select launch markets and currency display rules |
| Legal/safety wording | Astrology/Tarot cannot promise deterministic outcomes or medical/financial advice | Legal/safety review before paywall copy |
| Acquisition | CAC is unobserved | No paid traffic until cohort contribution gate passes |
| Gift/referral | Personal data and refund ownership need explicit flow | Approve only single-level, consented, idempotent gifting |

## 8. Roadmap for implementation after approval

### Phase 0 — measure before changing prices

Add product-level cost dimensions to the existing event/LLM usage system: `sku`, `catalog_version`, `price_variant`, `channel`, `purpose`, `model`, input/output tokens, retry count, PDF render ms, artifact bytes, delivery status, refund status and support category. Run a 30-day baseline query for usage frequency, paywall views, purchase conversion, repeat purchase, refund rate, LLM cost and result delivery. Do not store user text or sensitive birth/memory/partner data in this analytics layer.

### Phase 1 — versioned price book and ledger contract

Introduce a versioned price book without deleting legacy plans or rewriting historical orders. Store exact displayed price, native channel amount, credit quantity, bonus quantity, validity, estimated cost budget, safety class and effective date. Make every grant and spend idempotent. Preserve delivered results after balance reaches zero. Add duplicate webhook, refund, reversal, negative-balance and receipt-recovery tests.

### Phase 2 — one honest paywall

Place the first paywall after a completed free result or explicit request for depth. It must show the result name, included/free portion, exact credit cost, exact price, what data is required, limitations, support/refund and restore path. Keep safety guidance and crisis routing outside payment. Do not add countdowns or relationship/fate guarantees.

### Phase 3 — controlled cohort experiment

Start with 50–100 friendly or organic successful payers. Test one variable at a time: price, credit quantity or framing. Pre-register cohort, duration, stop criteria and rollback. Primary metric: net contribution per payer. Guardrails: result delivery, refund rate, support rate, safety complaints, p95 latency, LLM COGS and repeat purchase.

### Phase 4 — retention and ethical growth

Add a transparent annual plan, real event-based notifications, single-level referrals and gift reports only after payment/recovery/refund paths pass. Paid acquisition requires observed CAC and a conservative LTV contribution gate. A base gate is `CAC ≤ 3× observed LTV contribution` and payback within 90 days, with a downside case still positive.

## 9. Final recommendation

Approve **Hybrid B as a reversible hypothesis**, not as a permanent price promise: Plus $19.99/month, Power $29.99/month, Credit S $9.99/50, Credit M $24.99/150, Credit L $59.99/400, annual plans at two months free. Keep a meaningful free first result and a pay-per-value path for non-subscribers. Use the current plans and entitlements as legacy compatibility surfaces until a reviewed price book is live.

The next engineering step should be **measurement and versioned price-book design**, not a cosmetic paywall. The next business step should be settlement/tax/legal confirmation. The desired $50–100 monthly basket is achievable only when the user can see and voluntarily choose several high-value outcomes; it must not be manufactured through confusion, fear, hidden expiry or artificial blocking.

## References

[1]: https://apps.apple.com/us/app/co-star-personalized-astrology/id1264782561 "Co-Star — Apple App Store US listing"
[2]: https://apps.apple.com/us/app/nebula-spiritual-guidance/id1459969523 "Nebula — Apple App Store US listing"
[3]: https://apps.apple.com/us/app/sanctuary-psychic-reading/id1417411962 "Sanctuary — Apple App Store US listing"
[4]: https://apps.apple.com/us/app/the-pattern/id1071085727 "The Pattern — Apple App Store US listing"
[5]: https://chaninicholas.zendesk.com/hc/en-us/articles/1500001732281-App-Pricing "CHANI — official pricing help center"
[6]: https://steercorp.io/ "Steer — official product page"
[7]: https://apps.apple.com/us/app/labyrinthos-tarot-reading/id1155180220 "Labyrinthos — Apple App Store US listing"
[8]: https://apps.apple.com/us/app/astromatrix-horoscopes/id1065636826 "AstroMatrix — Apple App Store US listing"
[9]: ../app/repo/analytics.py "OracleAI analytics and monetization KPI queries"
[10]: ../app/core/llm.py "OracleAI LLM usage logging and internal pricing table"
[11]: ../app/data/seed.py "OracleAI seed plans and products"
[12]: ../app/core/llm.py "OracleAI internal estimate_cost implementation"
[13]: https://developers.openai.com/api/docs/pricing "OpenAI API pricing"
[14]: https://platform.claude.com/docs/en/about-claude/pricing "Anthropic Claude Platform pricing"
[15]: https://core.telegram.org/bots/payments-stars "Telegram Bot Payments API for digital goods and services"
[16]: https://telegram.org/tos/stars "Telegram Terms of Service for Stars"

**Disclosure.** **Basis:** gross customer prices are separated from illustrative net cash factors; contribution equals net cash less variable COGS; LLM rates use the repository’s internal estimate table for reproducibility. **Time:** external competitor and LLM pricing snapshots were checked on 26 August 2026 UTC; strategy date is 27 August 2026 GMT+3. **Assumptions:** power scenario uses 120 routine calls, 10 deep calls, 2 PDFs, 15%/30% deduction sensitivity, $0.02 planning PDF cost and explicit support/tool/referral reserves; these are not observed production values. **Sources & confidence:** storefront and first-party pricing pages are source-backed; ARPU, settlement, tax, refund, support, CAC, retention and PDF cost remain unknown or estimated. **Compliance:** this is research and operating analysis only, not personalized financial advice.
