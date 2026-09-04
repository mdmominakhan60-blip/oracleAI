# OracleAI — feature contracts

## Document orientation

| Field | Definition |
|---|---|
| **Purpose** | Map user-facing feature contracts to their implementation and tests. |
| **Source of truth** | The focused feature pages and the referenced API/core/repository modules. |
| **Scope** | Memory, unified history and billing/monetization foundations. |
| **Do not change** | Do not describe a planned capability as enabled, and do not move consent, owner scope, payment or deletion rules into client-only code. |
| **Key files** | `app/api/routers/`, `app/core/`, `app/services/`, `app/repo/`, `miniapp/`. |
| **Validation** | The focused feature tests plus the complete repository quality gates. |

| Feature | Canonical page | Implementation anchors |
|---|---|---|
| Memory | [`MEMORY.md`](MEMORY.md) | `app/core/memory.py`, `app/repo/`, `app/api/routers/profile.py`, `tests/test_memory_evaluation.py` |
| Unified history | [`HISTORY.md`](HISTORY.md) | `app/api/routers/history.py`, `app/repo/readings.py`, `miniapp/js/12-misc.js`, `tests/test_report_history.py` |
| Billing and monetization | [`BILLING.md`](BILLING.md) | `app/services/billing.py`, `app/services/invoices.py`, `app/api/routers/shop.py`, `app/api/routers/webhooks.py` |

The current product and release boundaries remain in [`../PRODUCT.md`](../PRODUCT.md) and [`../RELEASE/CURRENT_STATUS.md`](../RELEASE/CURRENT_STATUS.md). Research packs and dated audits are evidence or reference material, not competing feature contracts.
