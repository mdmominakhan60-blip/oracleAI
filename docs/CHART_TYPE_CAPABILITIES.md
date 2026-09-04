# Chart-type capability matrix

**Дата:** 2026-08-26
**Правило:** upstream capability не считается включённым продуктом без canonical contract, precision-gate, owner-scoped API, tests and documented UX.

| Тип | OracleAI status | Current contract and gate | Not included yet |
|---|---|---|---|
| Natal exact | **Enabled** | `natal_schema_version=2`; full canonical chart with planets, houses, ASC/MC, nodes, Lilith, additional points and major aspects | Commercial licensing sign-off and external production/device QA |
| Natal date-only | **Enabled with limitation** | Planets/aspects remain available; houses, ASC/MC and wheel are hidden | Any inferred angles or technical-noon wheel |
| Synastry | **Enabled JSON-first** | `synastry_schema_version=1`; saved owner partner; both charts exact; positions and major cross-chart aspects | New chart image, PDF/share visual, composite semantics |
| Transit | **Enabled JSON-first** | `transit_schema_version=1`; explicit ISO date; optional UTC time; `day`/`instant` precision; transit houses/angles excluded | Periods, ingresses and transit visual |
| Composite | **Enabled JSON-first** | `composite_schema_version=1`; saved owner partner; both full exact; circular midpoints of ten traditional planets and internal major aspects | Nodes, additional points, ASC/MC, houses, wheel and PDF |
| Solar returns | **Enabled JSON-first** | `returns_schema_version=1`; `planet=Sun`; target year 1900–2200; full exact natal plus owner coordinates/timezone; bounded UTC search and local timestamp | Jupiter/Saturn returns, return houses, relocation, wheel and predictions |
| Matrix | **Existing separate track** | Independent matrix calculation and visual; not a natal chart engine | Conflation with chart renderer |

## Product invariants

The visual engine never becomes a second source of truth. `app/core/astro.py` remains responsible for canonical values and precision. `app/core/chart_products.py` builds JSON-ready synastry, transit, composite and returns contracts without FastAPI, database or LLM dependencies.

Every enabled product has owner authorization, deterministic fixtures, stable error codes, PII-safe responses, explicit limitations and a JSON-first UX. New images, PDFs, share artifacts, periods, relocation semantics or automatic predictions require separate product decisions and release gates.

## References

[1]: https://kerykeion.net/content/docs "Kerykeion official documentation"  
[2]: https://pypi.org/project/kerykeion/ "Kerykeion PyPI"  
[3]: https://github.com/g-battaglia/kerykeion "Kerykeion source repository"  
[4]: ../app/core/astro.py "OracleAI canonical calculation source"  
[5]: ../app/core/chart_products.py "OracleAI chart product builders"
[6]: CHART_PRODUCT_CONTRACTS.md "OracleAI current chart product contracts"
