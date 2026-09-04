# Vedic / Jyotish boundary contract

Vedic calculations are a separate domain system from Western tropical astrology. They are implemented in `app/core/vedic.py` with Swiss Ephemeris through `pyswisseph 2.10.3.2`, sidereal zodiac and **Lahiri ayanamsa**. The system must never present a sidereal result as if it were a Western tropical placement or silently mix the two traditions in one sentence.

## Calculated surfaces

The module exposes deterministic evidence for sidereal planetary positions, true Rahu/Ketu, nakshatra and pada, Vimshottari dasha, Panchanga, Rahu Kaal, D1/D9/D10 varga charts, bounded Guna Milan, sidereal transits, sign-dignity-lite and criteria-led muhurta comparison. Every envelope carries tool name, deterministic mode, tradition, ayanamsa, ephemeris engine, inputs, result, limitations and calculation timestamp.

Exact Vedic chart mode requires a birth time confirmed by the caller and valid coordinates. It uses sidereal `houses_ex` only to obtain a lagna source and then emits whole-sign houses. Date-only or unconfirmed time emits planetary/nakshatra evidence but omits lagna and houses. Missing timezone is represented as a UTC date snapshot and is stated in limitations; it is not a hidden local-time claim.

Panchanga is evaluated at local noon in the current product contract. Its tithi/yoga/karana and sunrise/sunset results are not an interval-exact boundary service. Vimshottari requires a birth time because the starting balance depends on the Moon position at that local instant. Varga D9/D10 uses the documented Parashara sign-division rule, while school variants may differ. Guna Milan is an explicit balanced implementation with a maximum of 36 and is a reflection aid, not a relationship verdict.

## Interpretation boundary

Vedic outputs may explain the selected tradition’s calculated evidence and limitations. They must not be merged with tropical Western positions, used as medical/legal/financial advice, or turned into deterministic event guarantees. Differences between Jyotish schools, ayanamsa choices and varga rules must remain visible. Independent school/reference comparison is an open evidence gate.
