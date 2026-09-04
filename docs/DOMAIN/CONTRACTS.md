# OracleAI — domain methods and evidence policy

## Document orientation

| Field | Definition |
|---|---|
| **Purpose** | Cross-domain calculation and evidence policy. |
| **Source of truth** | `app/core/` domain calculators and contract modules. |
| **Scope** | Western/Vedic astrology, lunar, Tarot, palm and evidence limitations. |
| **Do not change** | Do not replace deterministic calculation with an LLM or conceal precision limits. |
| **Key files** | `app/core/astro.py`, `app/core/tarot.py`, `app/core/palm/`. |
| **Validation** | `python3 -m scripts.domain_qa`. |


**Дата проверки источников:** 2026-08-26  
**Принцип:** deterministic calculations are produced by code and preserved as evidence; AI only interprets supplied evidence.

## Western astrology

| Field | OracleAI contract |
|---|---|
| Tradition | Western tropical astrology. |
| Canonical engine | Swiss Ephemeris through the pinned `pyswisseph` dependency, with Kerykeion used for structured chart/rendering integration. |
| Zodiac | Tropical. |
| Perspective | Apparent geocentric, as encoded by the natal contract. |
| Houses | Placidus for exact-time charts only. |
| Nodes | True Node product setting; Rahu/Ketu labels are explicit. |
| Points | Planets, angles, lunar nodes, Lilith, Chiron, Juno, Ceres, Vesta and Pallas where the contract returns them. |
| Aspects | Major aspects with the configured orb policy from `app/core/astro.py` and `chart_contract.py`. |
| Unknown time | `time_known=false`; no ASC, MC, houses, house overlays or wheel are inferred. |
| Limitations | A chart is a symbolic self-reflection tool, not a scientific diagnosis, certainty claim, or prediction guarantee. |

The canonical implementation is `app/core/astro.py`; public truth-state shaping is in `app/core/chart_contract.py`; product builders are in `app/core/chart_products.py`. The calculation source is never re-created in the browser or by an LLM.

## Vedic / Jyotish

| Field | OracleAI contract |
|---|---|
| Tradition | Sidereal Vedic path with Lahiri/Chitrapaksha configuration as exposed by `app/core/vedic.py`. |
| Calculation | Sidereal conversion and bounded deterministic calculations; exact-time-only features must reject missing birth time. |
| Products | Kundli/chart facts, Vimshottari dasha, panchang-like moon snapshot and bounded Guna Milan compatibility. |
| Boundary | Vedic calculations are not silently mixed with Western tropical meanings. A bridge must be named in the UI/agent output. |
| Limitations | No claim of canonical agreement across every Jyotish school; ayanamsa, local timezone and precision must remain visible. |

The Vedic path requires additional school-specific golden cases before any expansion to divisional charts, yogas, muhurta or broader prediction products.

## Lunar / today

The current moon path uses a deterministic snapshot with explicit local timezone and date handling. The selected method must be kept stable across API, UI, AI and PDF; cache freshness and the distinction between a day snapshot and an exact lunar instant are part of the contract.

## Synastry, composite, and returns

| Product | Deterministic rule | Explicit non-claims |
|---|---|---|
| Synastry | Two owner-scoped exact natal charts, cross-chart major aspects and bounded relationship evidence. | Does not establish feelings, infidelity, future decisions or guaranteed outcomes. |
| Composite | Circular midpoints of the contracted traditional planets plus internal major aspects; no houses/angles in the current JSON-first contract. | Not a substitute for either natal chart and not a prediction of relationship duration. |
| Solar return | Bounded search for the Sun’s return to the natal longitude using target year, owner coordinates, timezone and exact natal data. | No automatic fate/prediction claim; other planetary returns are not implied. |
| Transit | Explicit date/time snapshot with `day` or `instant` precision; no transit houses/angles in the current contract. | A day snapshot is not represented as an exact instant. |

## Tarot

The product uses a 78-card Tarot deck: 22 Major Arcana and 56 Minor Arcana distributed across four suits. The server stores the drawn card identifiers, positions and orientation before any interpretation is requested. **Random draw and AI interpretation are separate events.** The AI cannot change the persisted draw, introduce cards, guarantee events, or claim another person’s internal state.

Card art and any deck assets require an explicit license review before public commercialization. Replay/seed behavior must be documented separately from ordinary random draws.

## Lenormand

Lenormand is a separate 36-card tradition and must not inherit Tarot semantics. The current repository exposes Lenormand-related naming in UI/agent surfaces, but a complete canonical 36-card pair, chain and Grand Tableau contract is not treated as enabled until identifiers, ordering, combinations, directionality, tests and evidence are present.

## Numerology and Destiny Matrix

Numerology and Matrix paths must name the chosen school, alphabet/transliteration, reduction rule, treatment of master numbers, date parsing and special cases. The Destiny Matrix remains a separate deterministic system and is not a substitute for the natal chart. Outputs are reflection prompts rather than medical, legal, financial or guaranteed-life claims.

## Palmistry

Palmistry accepts an image only after type/size/quality checks. The vision path may return observations, visible regions, confidence and limitations. Low-quality or ambiguous images must remain low-confidence and may request another photo. It must never make medical, diagnostic, longevity or high-stakes claims.

## Source hierarchy

| Priority | Source class | Use |
|---|---|---|
| 1 | Official engine documentation and license | Calculation behavior, API semantics and distribution obligations. |
| 2 | Version-pinned source code and tests | OracleAI’s actual implementation and regression truth. |
| 3 | Primary school references / books | Terminology and traditional boundaries. |
| 4 | Competitor product pages | UX/product benchmark only, never calculation authority. |
| 5 | General articles | Discovery only; not canonical evidence. |

## Golden-case matrix

The release set must include normal exact time, DST transition, historical timezone, unknown time/date-only, edge longitude, high latitude and midnight-boundary cases. Product-specific cases must include two exact synastry profiles, composite midpoint wrap-around, transit day versus instant precision, solar-return boundary years, all Tarot deck invariants, Matrix manual cases and low-quality palm images. Every unexplained calculation difference against an independent authoritative calculator remains a P1 until explained.

## References

[1]: https://www.astro.com/swisseph/swephinfo_e.htm "Official Swiss Ephemeris documentation and licensing"  
[2]: https://kerykeion.net/ "Official Kerykeion documentation and product description"  
[3]: https://github.com/g-battaglia/kerykeion "Kerykeion source repository and license"  
[4]: https://github.com/astrorigin/pyswisseph "pyswisseph source repository and license"  
[5]: ../app/core/astro.py "OracleAI canonical Western calculation source"  
[6]: ../app/core/vedic.py "OracleAI bounded Vedic calculation source"  
[7]: ../app/core/chart_products.py "OracleAI chart-product contracts"
