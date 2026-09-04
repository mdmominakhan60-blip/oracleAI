# OracleAI — monetization baseline

## Document orientation

| Field | Definition |
|---|---|
| **Purpose** | Billing and entitlement contract. |
| **Source of truth** | `app/services/billing.py`, shop and webhook routes. |
| **Scope** | Products, orders, entitlements, provider webhooks, refunds and local limitations. |
| **Do not change** | Do not claim public payment readiness without provider sandbox, settlement, refund and reconciliation evidence. |
| **Key files** | `app/services/billing.py`, `app/api/routers/shop.py`, `app/api/routers/webhooks.py`. |
| **Validation** | `pytest -q tests/test_billing.py tests/test_payment_monitor.py`. |


**Reference commit:** `3c51ec9`  
**Baseline date:** 2026-08-13  
**Scope:** source/configuration audit only; no customer balances, prices, plans, payments or feature flags were changed.

## Current commercial surfaces

The product currently supports three money/entitlement paths:

| Path | Current implementation | What is issued | Current risk for unit economics |
|---|---|---|---|
| Telegram Stars | `app/services/billing.py` → order → Telegram invoice → `successful_payment` → idempotent grant | Plans, products, reports, spreads, questions and crystal packs | Stars settlement/withdrawal and effective platform deductions are not represented as a verified net-revenue input yet. |
| Paddle web | Server-created pending order bound to Paddle transaction; webhook validates transaction/order and grants plan | Public plans with `price_usd` when `web_payments` is enabled/configured | Web flow is currently plan-oriented; credit-first web selling is not enabled and requires separate platform/legal review. |
| Internal crystals | Atomic ledger-backed balance spend in one transaction with product grant | Emergency question or catalog product purchased for `price_crystals` | Crystal cost-to-revenue mapping and paid credit-spend analytics are incomplete for contribution reporting. |

The existing database is already capable of preserving historic orders: `orders` stores SKU, title, Stars/crystal amounts, status, provider metadata, timestamps and payment linkage; `entitlements` stores issued rights; `crystal_ledger` stores balance deltas and reasons. Historic receipts must not be rewritten when a new price book is introduced.

## Seed catalog snapshot

The following values are seeded defaults only. Because seed uses `INSERT OR IGNORE`, an administrator may have changed live catalog rows; the database/admin export is authoritative before any production price change.

| Code/SKU | Type | Stars | Crystals | Grant | Period/validity | Notes |
|---|---|---:|---:|---|---|---|
| `guide` | Plan | 550 | — | 30 days, 1 daily question, +20 crystals | 30 days | $9.99 reference price in seed. |
| `vip` | Plan | 1,300 | — | 30 days, 3 daily questions, +50 crystals | 30 days | $24.99 reference price; “choice of majority” badge. |
| `vip_year` | Plan | 8,900 | — | 365 days, VIP features, +300 crystals | 365 days | $179 reference price; annual anchor. |
| `concierge` | Plan | 5,200 | — | 30 days, up to 30 daily questions, +200 crystals | 30 days | $99 reference price; high-cost/unlimited-like risk. |
| `crystals_100` | Crystals | 550 | — | +100 crystals | — | Seed pack. |
| `crystals_250` | Crystals | 1,150 | — | +250 crystals | — | Seed pack. |
| `crystals_600` | Crystals | 2,250 | — | +600 crystals | — | Seed pack. |
| `spread_one` | Spread | 75 | 10 | One-card spread | 30 days | Small transaction. |
| `spread_three` | Spread | 150 | 20 | Three-card spread | 30 days | Small transaction. |
| `spread_love` | Spread | 220 | 30 | Relationship spread | 30 days | Third-party/mind-reading safety boundary applies. |
| `spread_celtic` | Spread | 450 | 60 | Ten-card spread | 30 days | Higher tool/model cost needs measurement. |
| `report_natal` | Report | 690 | 90 | Natal report | No expiry | Requires real LLM/tool cost allocation. |
| `report_synastry` | Report | 690 | 90 | Compatibility report | No expiry | Requires explicit partner consent and deletion path. |
| `report_solar` | Report | 990 | 130 | Annual card forecast | No expiry | High-value hypothesis, not a guaranteed forecast. |
| `question_5` | Question | 250 | 35 | +5 questions | 30 days | Current credit-like product, separate from crystal balance. |

The existing seed catalog is **not** a recommendation to publish those prices. It mixes Stars, USD reference values and crystals without a unified net-revenue/cost model. Phase A will measure first; Phase B may add a versioned credit catalog without deleting or silently changing these rows.

## Existing cost instrumentation

`llm_usage` already records provider, model, purpose, prompt/completion tokens, estimated USD cost, latency, success flag, day and creation time. This is the correct source for model COGS, but it is not yet joined to paid SKU/purpose in an operator-facing contribution report. Voice/tool costs, payment settlement deductions, support/refund cost, taxes, referral rewards and fixed OPEX are not yet represented as a complete unit-economics ledger.

## Existing product/payment protections

The current payment code already has several important safety properties: orders are created before payment; payment webhooks are idempotent; grants are resolved from server-side order metadata; crystal spend and grants are transactional; refund changes order/payment status and reduces the stored Stars LTV counter. These protections must remain unchanged while analytics and price-book fields are added.

## Phase A gaps

1. No canonical versioned price book exists that separates catalog price, channel, currency, credit quantity, estimated variable cost budget and effective settlement assumptions.
2. Existing `invoice_created` and `payment_success` events are useful for conversion but do not yet expose credit pack checkout/paid/spend, delivery, refund and low-balance milestones through the approved allowlist.
3. Admin analytics show Stars/payment and LLM operational summaries, but not an estimated net revenue, variable COGS, contribution margin, paid ARPPU, repeat purchase or SKU-level economics block.
4. The live effective Stars realization, payment fees, taxes, refunds, support cost, payroll, cloud and paid-acquisition CAC are open inputs. They must come from settlement exports, contracts or explicit owner assumptions rather than invented constants.
5. No price or subscription change is being made in Phase A. Existing subscribers and purchased entitlements remain untouched.

## Privacy and non-goals

This baseline contains catalog metadata and aggregate architecture only. It does not include user names, Telegram IDs, message/diary/memory text, birth data, partner data, payment identifiers or raw order payloads. Phase A analytics must keep the same boundary. It also does not start advertising, submit payment configuration, publish new prices, hide subscriptions or alter balances.

## Baseline owner and next action

The product owner supplies the missing jurisdiction/channel/cost assumptions. The technical owner implements the versioned assumptions template and server-owned event/KPI contract. The finance/legal reviewer confirms effective settlements, tax/refund treatment and permitted sales channels before any price experiment.
