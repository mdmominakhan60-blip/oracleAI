# OracleAI — competitor benchmark

**Дата доступа к источникам:** 2026-08-26  
**Метод:** сравниваются публичные product mechanics и positioning, а не защищённые тексты, брендинг или proprietary assets. Competitor pages are not calculation authorities.

## First-party benchmark

| Конкурент | Наблюдаемые strengths | What OracleAI should borrow | OracleAI opportunity |
|---|---|---|---|
| Astro.com / Astrodienst | Глубокие бесплатные гороскопы, chart drawings/calculations, extended data, personal profiles, saved birth data, reports and privacy/deletion messaging.[1] | Progressive onboarding from birth data to chart; separate beginner and advanced depth; privacy made visible. | Combine professional evidence with a calmer personal-AI experience, explicit limitations, memory consent and connected reflection history. |
| Astro-Seek | Широкий набор бесплатных chart/calculator surfaces: natal, compatibility, moon, transits, returns, progressions, sidereal, relocation, numerology and a private database.[2] | Clear tool taxonomy and beginner/advanced separation. | Avoid calculator sprawl by making every tool connect to profile, evidence, history and a useful next step. |
| Kerykeion / Astrologer ecosystem | Open calculation library, structured JSON, SVG charts, natal/synastry/transit/composite/return chart types, guides, professional workspace and transparent engine positioning.[3] | Typed data, transparent calculation/rendering separation, reusable chart product contracts. | Keep OracleAI’s single canonical calculation source and add memory/AI personalization without letting AI modify facts. |
| AstroMatrix | App positioning around personalized natal, synastry, transits, progressed charts, daily tracking, tarot and moon content.[4] | Connect chart, transits, tarot, rituals and recurring engagement. | Make connections evidence-backed and user-controlled rather than a generic feed of predictions. |
| Labyrinthos | Beginner-friendly Tarot learning, readings, spreads, card meanings, Lenormand resources, journals/workbooks and physical/digital ecosystem.[5] | Teach the system, not only output a reading; provide learning and reflective replay. | Distinguish random draw from interpretation, preserve history, and connect card reflection to consented personal memory. |
| Co–Star | Mobile-first personalized astrology positioning centered on relationships and a strong editorial voice.[6] | Fast first value, strong voice, relationship-oriented return habit. | Preserve warmth while increasing transparency: show source facts, precision and limitations instead of relying on opaque confidence. |
| CHANI | Contemporary astrology/wellness positioning with guided content and recurring ritual behavior. | Editorial cadence and practical prompts. | Tie rituals to actual user context, diary and chart evidence, avoiding generic horoscope filler. |
| The Pattern | Personalized behavioral framing and relationship-oriented self-reflection. | Clear personalized themes and return loops. | Expose what evidence supports a theme and let users edit/delete the personal context used. |
| Sanctuary | Combines astrology/tarot-style readings with content and access to human practitioners. | Layered support and clear service boundaries. | Keep low-stakes reflection AI-first while providing transparent escalation and no high-stakes claims. |
| Steer Astro | Vedic astrology, birth charts, planetary transits, dasha periods and Panchang-oriented AI positioning.[7] | Explicit Vedic feature grouping and tradition-aware routing. | Keep Lahiri/Western boundaries explicit, versioned and testable; do not collapse traditions into one semantic layer. |
| Sona / AstroMatrix Tarot-style products | Quick question-to-reading flow and immediate card value are common category mechanics. | Reduce time from question to first reflective output. | Retain speed while making the draw persistent, replayable and non-deterministic about the future. |

## Feature gap review

| Feature | Category baseline | OracleAI current | Gap | Action / verification |
|---|---|---|---|---|
| First value | Astro-Seek and Astro.com provide direct entry to birth data and chart tools.[1] [2] | Onboarding and Mini App bootstrap exist. | Real Telegram first-use device flow is unverified. | Run a signed-initData onboarding E2E and measure time-to-first chart. |
| Technical depth | Astro.com, Astro-Seek and Kerykeion expose extensive calculation depth.[1] [2] [3] | Natal v2, JSON-first synastry/transits/composite/returns. | Independent calculator comparison and broader chart visual/product coverage remain gates. | Record golden-case comparisons and keep unsupported types hidden. |
| Personalization | Co–Star, The Pattern and AstroMatrix emphasize personalized experience.[4] [6] | Profile, agents, memory and evidence-first interpretation. | Memory relevance/contradiction evaluation is incomplete. | Add memory evaluation dataset, retrieval thresholds and a unified history surface. |
| Tarot | Labyrinthos combines readings with study, spreads, card meanings and journaling.[5] | Tarot deck, spreads, random draw, interpretation, history and outcome. | Explicit replay/seed contract and canonical Lenormand product are incomplete. | Separate Tarot/Lenormand contracts and test persistence/replay semantics. |
| Relationship | Astro.com/Astro-Seek/Kerykeion cover compatibility/synastry/composite.[1] [2] [3] | Synastry and composite JSON-first with owner-scoped partner. | Visual/PDF report surfaces and external comparison are incomplete. | Add dedicated relationship report template after privacy and snapshot gates. |
| Current sky / rituals | AstroMatrix and competitor editorial products use moon/transit recurrence.[4] | Today, moon week, sky, diary and practices. | No measured retention or full notification-center proof. | Track privacy-safe journey events and verify scheduler/device behavior. |
| Trust | Astro.com visibly discusses confidentiality and user deletion.[1] | Privacy docs, consent, server-side memory pause and redaction. | Legal/production sign-off and self-service deletion E2E remain. | Complete deletion/anonymization contract and owner review. |
| Reports | Astro.com sells/serves authored reports; Kerykeion exposes SVG/report tooling.[1] [3] | PDF builder, chart image, share cards and report persistence. | Luxury visual regression and immutable version history were not previously complete. | Use append-only reports, retain deterministic snapshot metadata, and execute PDF golden matrix. |
| Monetization | Competitors mix free tools, subscriptions, premium reports, stores or services.[1] [3] [5] | Plans, products, crystals, entitlements and provider webhooks. | Live payment settlement/refund/reconciliation external. | Certify sandbox provider flows and keep paywall transparent. |

## Strategic target

OracleAI should not try to beat Astro-Seek on raw calculator count or Labyrinthos on physical Tarot retail. Its differentiated target is a **trusted personal reflection system** that combines deterministic domain engines, visible evidence, user-controlled long-term memory, distinct AI guides, connected tools and premium historical reports. The success criterion is not feature presence alone; it is whether the same fact remains consistent across calculation, interpretation, UI, history, PDF and future sessions.

## References

[1]: https://www.astro.com/index_e.htm "Astrodienst official product surface"  
[2]: https://www.astro-seek.com/ "Astro-Seek official product surface"  
[3]: https://kerykeion.net/ "Kerykeion official product and engine surface"  
[4]: https://astromatrix.org/ "AstroMatrix official product surface"  
[5]: https://labyrinthos.co/ "Labyrinthos official Tarot/Learn/App surface"  
[6]: https://play.google.com/store/apps/details?id=com.costarastrology&hl=en_US "Co–Star official app listing"  
[7]: https://steer.coach/compare/best-free-vedic-astrology-ai.html "Steer Astro comparison page"
