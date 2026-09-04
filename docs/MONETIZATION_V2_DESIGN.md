# OracleAI Monetization v2 Design

**Status:** implementation baseline and reversible soft-launch hypothesis. Prices and conversion inputs are planning assumptions, not observed production facts.

## Decision

OracleAI will use a **three-layer hybrid model**. The permanent Free tier provides deterministic product value and previews. Paid subscriptions provide recurring AI access, bounded memory, richer context, premium tools, and a monthly grant of deep-analysis Crystals. Crystals are a separate server-side balance used for compute-heavy reports and one-off premium outputs.

The model deliberately removes the automatic new-user VIP month. Existing active subscriptions, trials, annual purchases, Crystal balances, reports, and entitlements remain valid until their existing expiry or consumption rules complete. New purchases use a versioned catalog and price book; historical orders remain immutable legacy records.

## Canonical tiers

| Public tier | Code | Monthly USD hypothesis | Annual USD hypothesis | AI message budget | Compute budget | Monthly Crystal grant | Role |
|---|---|---:|---:|---:|---:|---:|---|
| Искра | `free` | 0.00 | — | 0 | 0 | 0 | Deterministic preview, basic chart facts, Today, basic ritual/history |
| VIP | `vip_core` | 19.99 | 199.90 | 120 | 0.12 USD | 60 | Full AI chat, bounded memory, core guides, limited deep tools |
| VIP Plus | `vip_plus` | 34.99 | 349.90 | 300 | 0.35 USD | 180 | Recommended tier: larger context, advanced tools, monthly report, deeper history |
| Pro | `pro` | 69.99 | 699.90 | 700 | 0.90 USD | 450 | Power users, advanced reports, priority processing, larger memory |
| Concierge | `concierge_v2` | 99.99 | 999.90 | 1200 | 1.50 USD | 800 | Highest allowance and routing quality with fair-use boundaries; never “unlimited” |

Annual prices are exactly ten paid months, or approximately 16.7% below twelve monthly payments. The UI must show total annual charge and monthly equivalent together.

Legacy plan codes `trial`, `guide`, `vip`, and `vip_year` remain queryable and grant-compatible. They are not removed or rewritten. New users and new catalog purchases use the v2 codes.

## Crystal economy

Purchased Crystals do not expire. Subscription bonus Crystals are issued as a separate monthly grant with a 90-day controlled carry-over and are consumed before purchased Crystals when they expire sooner. Legacy balances are preserved as `legacy` balance and are never silently reduced. A failed premium operation must restore a reservation or leave the balance unchanged.

| Pack | Code | USD hypothesis | Crystals | Effective USD / Crystal | Use |
|---|---|---:|---:|---:|---|
| Small | `crystals_50_v2` | 9.99 | 50 | 0.200 | First top-up / one short deep result |
| Medium | `crystals_150_v2` | 24.99 | 150 | 0.167 | Main repeat purchase |
| Large | `crystals_400_v2` | 59.99 | 400 | 0.150 | Power user / multiple reports |

Crystal prices are intentionally separate from subscription access. A customer may buy a one-off result without subscribing, but deep operations still require the relevant capability or Crystal cost.

## Deep-operation price book

`expected_cost_usd` is a configurable budget, not a provider invoice. It includes the expected LLM/tool/PDF/vision/delivery envelope. The engine rejects a SKU with no cost budget or non-positive Crystal price.

| Operation | SKU | Crystal price | Cost budget USD | Included in | Standalone |
|---|---|---:|---:|---|---|
| Small AI enhancement | `deep_followup` | 15 | 0.02 | VIP Core+ | Yes |
| One-card Tarot interpretation | `tarot_one_deep` | 20 | 0.03 | VIP Core+ | Yes |
| Three-card Tarot interpretation | `tarot_three_deep` | 40 | 0.05 | VIP Plus+ | Yes |
| Full natal report | `report_natal_deep` | 120 | 0.14 | VIP Plus+ | Yes |
| Deep synastry report | `report_synastry_deep` | 150 | 0.18 | Pro+ | Yes |
| Large annual report | `report_annual_deep` | 240 | 0.28 | Pro+ | Yes |
| Expensive vision workflow | `vision_deep_dynamic` | 120–300 | 0.15–0.50 | VIP Plus+ | Yes, dynamic |

Subscription inclusion means the capability is unlocked and the operation still consumes the plan’s compute budget. Crystal pricing is used when the user is outside the included allowance or chooses one-off consumption. No frontend value is authoritative.

## Canonical capabilities

The entitlement engine exposes typed, declarative capabilities:

`astro.basic`, `astro.advanced`, `today.basic`, `tarot.basic`, `tarot.advanced`, `palm.basic`, `palm.advanced`, `ai.chat`, `ai.memory`, `ai.deep_context`, `report.natal.basic`, `report.natal.deep`, `report.synastry.deep`, `voice`, `priority_queue`, `monthly_report`, and `crystals.purchase`.

Every decision returns effective tier, capability, quota, remaining compute budget, Crystal balance, expiry, cancellation/grace state, and an explanation suitable for a contextual paywall. Bot and Mini App call the same backend service and catalog.

## Feature matrix

| Feature | Free | VIP | VIP Plus | Pro | Concierge | Crystal path |
|---|---:|---:|---:|---:|---:|---:|
| Today and lunar facts | Yes | Yes | Yes | Yes | Yes | — |
| Basic natal preview | Yes | Yes | Yes | Yes | Yes | — |
| Ordinary AI chat | No | Yes | Yes | Yes | Yes | — |
| AI memory | No | Bounded | Deeper | Large | Largest | — |
| Advanced Tarot | No | Limited | Yes | Yes | Yes | Optional deep operations |
| Palm AI | No | Limited | Yes | Yes | Priority | Optional deep operations |
| Natal deep report | Preview | Limited | Included budget | Included budget | Included budget | 120 ✦ |
| Synastry deep report | Preview | Preview | Limited | Included budget | Included budget | 150 ✦ |
| Monthly report | No | No | Yes | Yes | Yes | — |
| Priority processing | No | No | Yes | Yes | Highest | — |
| One-off Crystal packs | Purchase | Purchase | Purchase | Purchase | Purchase | 50/150/400 ✦ |

## Unit-economics assumptions

The model uses a configurable 70% net cash factor and repository planning COGS cases: light $0.351, medium $1.083, power $1.315, and stress $2.750 per payer-month. These are assumptions until settlement, tax, refund, support, delivery, and provider exports are available. Gross bookings are never presented as profit.

The reproducible model in [`scripts/model_monetization_v2.py`](../scripts/model_monetization_v2.py) evaluates three price hypotheses:

| Variant | Monthly ladder | Planning contribution / activated user | Planning contribution / payer |
|---|---|---:|---:|
| A | $14.99 / $29.99 / $59.99 / $99.99 | $1.86 | $21.86 |
| B | $19.99 / $34.99 / $69.99 / $99.99 | **$2.03** | **$27.01** |
| C | $14.99 / $39.99 / $69.99 / $99.99 | $1.90 | $23.81 |

Variant B is the starting hypothesis because it has the highest modeled contribution under the stated assumptions while keeping the entry tier within the requested $15–20 range and placing the recommended tier in the requested $30–40 range. The actual winner must be re-evaluated from observed contribution, refund rate, retention, and provider settlement data.

For 1,000 activated users, the same model produces these illustrative outcomes:

| Variant | Scenario | Paid conversion | Gross revenue | Variable cost | Contribution |
|---|---|---:|---:|---:|---:|
| B | Conservative | 5.0% | $1,489.44 | $33.23 | $1,009.38 |
| B | Base | 7.5% | $2,995.33 | $70.86 | **$2,025.87** |
| B | Upside | 10.0% | $5,858.68 | $134.72 | $3,966.36 |

These conversion rates are planning assumptions only. The generated CSV contains all variants and scenarios.

## Migration and lifecycle policy

The v2 catalog is additive. New tables store `catalog_version`, `price_book_version`, immutable product snapshots, channel prices, grant rules, and cost budgets. Existing `plans`, `products`, `orders`, `payments`, `entitlements`, and `crystal_ledger` rows are not deleted or rewritten.

An active legacy VIP remains active through its recorded `sub_until`. A legacy trial is not extended automatically. A legacy annual purchase remains active through its recorded expiry. After expiry, the effective tier is Free unless a v2 subscription is active. Purchased reports and balances remain available. Refunds revoke only the rights attributable to the refunded order and never erase unrelated historic rights.

Cancellation stops renewal but leaves access until `sub_until`; renewal failure enters a bounded grace period; expiry transitions to Free. Provider events remain signature-verified, order-bound, and idempotent. Server-side payment metadata, not browser fields, determines every grant.

## Analytics and dashboard contract

The server emits allowlisted, privacy-safe, channel-neutral events for pricing, paywall, checkout, subscription lifecycle, AI unlock, first paid action, Crystal grant/spend/low balance, deep report lifecycle, refunds, upgrades, downgrades, and expiration. No question text, chart data, memory facts, birth data, provider payloads, or secrets are stored in monetization telemetry.

The admin dashboard reports gross booking, estimated net revenue only when reviewed assumptions exist, refunds, revenue by SKU, free-to-paid and paywall funnels, active/new/churn/renewal/retention, Crystal grants/purchases/spend/outstanding/repeat purchases, LLM/vision/PDF/tool COGS, and contribution by tier/SKU. Unknown inputs remain explicitly marked as unknown.

## Commercial gauntlet answers

**Why pay $19.99?** The user receives a recurring personal AI guide, bounded memory, richer context, premium agents, and a monthly Crystal grant, while basic deterministic value remains free.

**Why upgrade to $34.99?** VIP Plus is the recommended depth tier: larger AI and memory budgets, advanced Tarot and compatibility, a monthly report, and a materially larger Crystal grant. It improves capability and quality, not only message count.

**Why buy Crystals?** Crystals map an optional payment to a named, recoverable output such as a deep natal report or synastry report. The user sees the exact cost before confirmation and can continue using free surfaces.

**Why pay $69–100?** Pro and Concierge serve users who need high allowance, advanced reports, priority routing, and the highest fair-use boundaries. They are not advertised as unlimited, and cost budgets cap runaway usage.

**Why renew month two?** The subscription creates accumulated value through memory, recurring guidance, monthly reports, included Crystals, and continuity. Cancellation is visible and access remains until expiry.

## References

[1]: ./MONETIZATION_STRATEGY.md "Existing OracleAI monetization strategy and cost assumptions"
[2]: ./MONETIZATION_RESEARCH_PACK.md "Existing OracleAI monetization research pack"
[3]: ../app/repo/billing.py "Legacy billing persistence and invariants"
[4]: ../app/services/billing.py "Legacy billing orchestration"
[5]: ../app/services/limits.py "Legacy usage gates"
[6]: ../app/repo/analytics.py "Existing analytics and cost attribution"
