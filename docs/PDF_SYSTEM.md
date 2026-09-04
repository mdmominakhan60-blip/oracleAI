# OracleAI — PDF system contract

## Purpose

A report is a **premium editorial artifact**, not a raw HTML dump. It combines a human-readable narrative layer with a verification layer that preserves the exact calculation context used to create it.

## Layers

| Layer | Contents |
|---|---|
| Human | Cover, personal overview, chart visualization, readable placements, selected aspects, interpretation, practical reflection and safety note. |
| Verification | Report ID, evidence ID or snapshot metadata, calculation method, engine/version, zodiac/ayanamsa, house system, node policy, aspect policy, timestamp, precision state and limitations. |

## Generation contract

`app/pdfgen/` receives validated order/profile data and deterministic chart/matrix inputs. The renderer must never calculate a second, conflicting chart. It should use the canonical domain result, render controlled SVG/raster assets, escape user-provided text and keep PII out of public share URLs. When WeasyPrint is unavailable, the system must return an explicit HTML fallback rather than a file with a misleading `.pdf` extension.

## Supported and bounded products

| Product | Current state |
|---|---|
| Natal exact | Supported with expanded points, chart image and Matrix sections. |
| Natal date-only | Must visibly omit ASC, MC, houses and house-based interpretation. |
| English / Russian | Supported; long-name and long-city cases remain regression inputs. |
| Synastry / composite / returns | JSON-first product contracts exist; dedicated luxury PDF templates are not yet enabled. |
| Tarot / yearly / Vedic extended | Require separate template and evidence decisions before being marketed as PDF products. |

## Visual regression matrix

Every release candidate should generate and render at least: RU exact-time, EN exact-time, RU date-only, EN date-only, long name, long city, edge coordinates, many aspects, minimal content and maximal content. Inspect for clipping, overflow, broken glyphs, blank pages, orphan headings, unbalanced density, chart overlap, inconsistent language and missing limitations.

The reproducible local harness is `python -m scripts.pdf_matrix --out /tmp/oracleai-pdf-matrix`. It uses deterministic fixture coordinates, writes HTML/PDF artifacts and `summary.json` outside the source tree, and fails when language, long-name rendering, exact/date-only truth-state, headings or common placeholder tokens violate the contract. The harness is a deterministic preflight, not a replacement for production font, browser viewport or manual visual sign-off.

## Privacy and immutability

Generated reports are owner-scoped. Share artifacts expose only the intended visual payload. Historical reports must retain the calculation snapshot and must not silently change when a profile is edited. Regeneration creates a new immutable report version; the previous version remains readable through history.

## References

[1]: ../app/pdfgen/ "OracleAI PDF generation package"  
[2]: ../tests/test_pdfgen.py "PDF rendering, localization and fallback tests"  
[3]: ../app/core/chart_contract.py "Canonical chart truth state"  
[4]: ../app/repo/readings.py "Immutable report-history persistence"
