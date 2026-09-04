# OracleAI — domain documentation

## Document orientation

| Field | Definition |
|---|---|
| **Purpose** | Map domain semantics to the code contracts without mixing them with transport or deployment details. |
| **Source of truth** | The focused pages below plus their referenced implementation modules and tests. |
| **Scope** | Astrology, Tarot/card reflection, palm evidence and the shared evidence policy. |
| **Do not change** | Do not infer unsupported precision, houses, cards, diagnoses or future certainty from a missing input or from an LLM response. |
| **Key files** | `app/core/astro.py`, `app/core/chart_contract.py`, `app/core/tarot.py`, `app/core/palm/`, `app/core/palm_vision.py`. |
| **Validation** | `python3 -m scripts.domain_qa`, focused chart/Tarot/palm tests and the product-contract tests. |

## Canonical map

| Domain | Canonical page | Implementation | Boundary |
|---|---|---|---|
| Shared evidence policy and enabled methods | [`CONTRACTS.md`](CONTRACTS.md) | `app/core/`, `docs/` contracts | Deterministic code produces evidence; AI interprets only supplied evidence. |
| Western/Vedic astrology and chart products | [`ASTROLOGY.md`](ASTROLOGY.md) | `app/core/astro.py`, `chart_contract.py`, `vedic.py`, `chart_products.py` | Precision and school are explicit; date-only input does not receive houses or angles. |
| Tarot and card reflection | [`TAROT.md`](TAROT.md) | `app/core/tarot.py`, `app/api/routers/tarot.py` | Draw, position and orientation come from the persisted ledger; Lenormand is not silently enabled. |
| Palm/visual evidence | [`PALM.md`](PALM.md) | `app/core/palm/`, `palm_vision.py`, `palm_lines.py`, `palm_full_scope.py` | Quality/confidence and view requirements remain visible; no diagnosis or guaranteed prediction. |

Product-specific chart JSON contracts are documented in [`../CHART_PRODUCT_CONTRACTS.md`](../CHART_PRODUCT_CONTRACTS.md). AI routing and prompt boundaries are documented in [`../AI_SYSTEM.md`](../AI_SYSTEM.md).

## References

[1]: [CONTRACTS.md](CONTRACTS.md) — cross-domain calculation and evidence policy.
[2]: [ASTROLOGY.md](ASTROLOGY.md) — astrology source of truth.
[3]: [TAROT.md](TAROT.md) — Tarot source of truth.
[4]: [PALM.md](PALM.md) — palm source of truth.
