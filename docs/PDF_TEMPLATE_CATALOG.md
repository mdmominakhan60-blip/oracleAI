# PDF template catalog

**Дата:** 26 августа 2026

The PDF system keeps calculation truth, human interpretation and visual layout as separate layers. Every enabled template must receive localized copy, a snapshot input contract, deterministic fallback behavior, a golden-case matrix and a visual review before public commercialization.

| Product | Current state | Snapshot/input contract | Local evidence | Release gate |
|---|---|---|---|---|
| Natal | **Enabled** | Exact or date-only chart, explicit conventions, Matrix, safety disclaimer, localized `Order.lang` | `app/pdfgen/builder.py`, `tests/test_pdfgen.py`, `scripts/check_pdf_golden_cases.py` | Six synthetic RU/EN exact/date-only/edge cases pass; production pixel and font review remain. |
| Synastry | API/product contract exists; PDF export is not enabled as a separate template | Two owner-scoped exact chart snapshots, partner consent and deterministic aspect evidence | `docs/CHART_PRODUCT_CONTRACTS.md`, `app/core/chart_products.py` | Add template, localized copy, PDF golden cases and independent calculator comparison. |
| Tarot | Reading/history contract exists; PDF export is not enabled as a separate template | Persisted draw, positions, orientation, ledger and interpretation grounding | `app/core/tarot.py`, `tests/test_tarot_contract.py` | Add licensed card-art policy, template, snapshot schema and visual/legal review. |
| Future products | **Deferred** | Product-specific evidence and precision contract required | `docs/DOMAIN/CONTRACTS.md`, `docs/RELEASE/TASKS.md` | No UI or export promise until a separate contract and gate exist. |

A template is not production-ready merely because HTML renders. Public release additionally requires licensed assets, legal/privacy review, print and mobile visual review, reproducible source snapshots and a rollback-safe deployment. The current repository intentionally exposes only the natal PDF path.
