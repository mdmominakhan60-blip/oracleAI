# OracleAI — полная карта продуктовых surface

**Дата аудита:** 2026-08-27
**Исходный коммит:** `4b0f8e2`
**Статус:** baseline inventory; подтверждённые ограничения отмечены явно.

## Как читать карту

| Статус | Значение |
|---|---|
| **Enabled** | Surface реализован в коде, имеет API/UX-контракт и покрыт существующими проверками. |
| **Enabled with limitation** | Основной путь реализован, но ограничение является частью truth state и не должно скрываться. |
| **Partial** | Часть цепочки реализована, однако отсутствует один или несколько слоёв: evidence, history, export, UX или E2E. |
| **Not enabled** | В репозитории нет завершённого пользовательского продукта; наличие upstream-возможности не считается реализацией. |
| **External gate** | Локальная реализация есть, но нужны реальные credentials, Telegram device QA, платёжная сертификация, legal/licensing или production evidence. |

## Identity

| Surface | Текущее состояние | Evidence / gap |
|---|---|---|
| Registration / first identity | **Enabled with limitation** | Telegram identity и dev-user режим реализованы в `app/api/deps.py`; самостоятельной email-регистрации нет. |
| Onboarding | **Enabled** | Mini App onboarding и профильный intake в `miniapp/js/05-app.js`, `miniapp/js/12-misc.js`. Возрастной гейт удалён (GAUNTLET v2). |
| Login / logout | **Enabled with limitation** | Авторизация через Telegram `initData`; logout как отдельная серверная сессия не нужен, но нужна device QA. |
| Profile | **Enabled** | `/api/me`, `/api/profile`, профильные поля и UI. |
| Birth data | **Enabled** | Дата, время, точность времени, место и координаты используются расчётным контрактом. |
| Timezone | **Enabled** | IANA timezone проходит через профиль и chart contracts. |
| Location / coordinates | **Enabled with limitation** | Геокодирование и ручные координаты поддержаны; качество внешнего геокодера — external gate. |
| Avatar | **Partial** | Агентские спрайты есть; пользовательский avatar upload как завершённый identity-surface не подтверждён. |
| Language | **Enabled** | RU/EN client localization и server language fields. |
| Preferences | **Enabled with limitation** | Профильные настройки и отдельный owner-scoped notification preference contract реализованы; дополнительные категории требуют отдельной продуктовой спецификации. |
| Privacy controls | **Enabled with limitation** | Memory consent, pause/delete controls и privacy docs есть; legal sign-off остаётся внешним gate. |
| Account deletion | **Partial** | Admin anonymization существует; self-service deletion flow требует отдельного E2E-подтверждения. |

## User experience

| Surface | Текущее состояние | Evidence / gap |
|---|---|---|
| Public landing | **Enabled** | `web/landing.html`, `web/landing-en.html`, CSS, terms/privacy и sitemap. |
| Onboarding | **Enabled** | Age gate, intro guide, birth-data setup. |
| Home / Today | **Enabled** | `/api/today`, diary, practices, moon week, home shell. |
| Dashboard | **Enabled with limitation** | Mini App home acts as dashboard; отдельный desktop dashboard не выделен. |
| Profile | **Enabled** | Profile view, chart and settings actions. |
| History | **Partial** | Tarot, reports, chat sessions and palm histories exist; unified cross-tool history is not complete. |
| Favorites / saved results | **Partial** | Saved reports and memories exist; generalized favorites contract is not confirmed. |
| Notifications | **Enabled with limitation** | Mini App bell показывает server-owned inbox summaries с unread count и mark-all-read; реальная Telegram delivery/device QA остаётся external gate. |
| Empty states | **Enabled** | Core widgets include explicit empty and unavailable states; full matrix needs visual QA. |
| Loading states | **Enabled** | Widget-specific loading/re-entry guards and API error states exist. |
| Error / retry | **Enabled with limitation** | Friendly client errors and retry-chat exist; every feature still needs matrix-level E2E. |
| Offline | **Partial** | Offline fallback exists for LLM/domain defaults; no full offline-first cache contract. |
| Mobile | **Enabled with limitation** | Telegram WebView-oriented CSS and viewport handling exist; real-device verification is external. |
| Desktop | **Enabled with limitation** | Responsive layout exists; browser matrix and visual regression should be expanded. |

## AI, agents, memory, and evidence

| Surface | Текущее состояние | Evidence / gap |
|---|---|---|
| Agent catalog | **Enabled** | `/api/agents`, agent runtime and frontend agent cards. |
| Agent identity / role / tone | **Enabled** | Agent profiles and prompts in `app/agents/` and `app/core/`. |
| Allowed tools / routing | **Enabled** | Router and tool manifests; tests cover routing and file harness. |
| Prohibited behavior / safety | **Enabled** | Safety and interpretation guardrails; ongoing adversarial review required. |
| Evidence contract | **Enabled** | Evidence-first interpretation separates deterministic facts from LLM prose. |
| Deterministic tool calls | **Enabled** | Astrology, chart products, tarot draw, matrix and domain tools do not delegate facts to LLM. |
| Streaming | **Partial** | Chat path exists; full streaming behavior and cancellation need production-provider verification. |
| Provider fallback | **Enabled** | custom → Anthropic → OpenAI → offline chain is documented and tested locally. |
| Hallucination protection | **Enabled with limitation** | Grounding checks and refusal rules exist; live-provider evaluation remains an external gate. |
| Conversation history | **Enabled** | Chat sessions and thread endpoints. |
| Personalization | **Enabled with limitation** | Profile and bounded memory are assembled; quality depends on provider and retrieval evaluation. |
| Multilingual behavior | **Enabled with limitation** | RU/EN strings exist; live LLM language evaluation needs provider credentials. |
| Memory opt-in / consent | **Enabled** | Server-side memory switch and consent-aware storage. |
| Memory categories | **Partial** | Profile, preferences, facts, goals, interests, history, reflections, important/temporary context are concepts in the memory contract; taxonomy coverage requires evaluation dataset. |
| Memory retrieval / relevance | **Partial** | Bounded retrieval exists; semantic embeddings are optional and quality is not fully benchmarked. |
| Memory edit / delete / visibility | **Enabled** | `/api/memories`, delete endpoint and memory UI. |
| Stale / contradiction handling | **Partial** | No complete user-visible contradiction workflow is confirmed. |
| Memory poisoning / prompt injection | **Enabled with limitation** | Trust boundaries and guardrails exist; adversarial dataset should be expanded. |
| Profile isolation | **Enabled** | Owner-scoped repository/API contracts and security tests. |

## Western astrology and chart products

| Surface | Текущее состояние | Evidence / gap |
|---|---|---|
| Natal exact | **Enabled** | `natal_schema_version=2`; planets, houses, angles, nodes, Lilith, additional points, aspects and retrograde flags. |
| Natal date-only | **Enabled with limitation** | `time_known=false`; houses, ASC, MC and wheel remain hidden. |
| Tropical zodiac | **Enabled** | Canonical calculation source in `app/core/astro.py`. |
| Swiss Ephemeris / Kerykeion | **Enabled** | Pinned dependencies and chart engine decision docs. |
| House system / orbs / aspects | **Enabled with limitation** | Contracted settings exist; external calculator comparison remains a release gate. |
| DST / historical timezone / high latitude / midnight edges | **Partial** | Golden/regression tests exist in part; full independent comparison matrix requires evidence. |
| Chart image | **Enabled with limitation** | Server-side transient rendering; raw SVG is not persisted or exposed. |
| Synastry | **Enabled JSON-first** | `synastry_schema_version=1`; exact saved partner, cross-chart aspects and owner scope. |
| Composite | **Enabled JSON-first** | `composite_schema_version=1`; circular midpoints and internal major aspects; no houses/angles. |
| Transits | **Enabled JSON-first** | `transit_schema_version=1`; explicit date/time precision and no transit houses. |
| Solar return | **Enabled JSON-first** | `returns_schema_version=1`; bounded Sun return search, target year and location requirements. |
| Lunar return / progressions / Davison / relocation | **Not enabled** | No completed product contract is present; must not be implied by UI. |
| Compatibility | **Partial** | Basic `/api/compat` and full interpretation path exist; product depth and evidence need final review. |
| Vedic astrology | **Partial / bounded** | UI and agent tools expose Lahiri/Kundli, Vimshottari, Panchang and Guna Milan concepts; boundary golden cases and full product contracts remain required. |

## Tarot, Lenormand, numerology, Matrix, and palmistry

| Surface | Текущее состояние | Evidence / gap |
|---|---|---|
| Tarot deck / cards | **Enabled** | Card catalog, unique identifiers, spread endpoints and assets. |
| Tarot Major / Minor / suits / numbering | **Enabled with limitation** | Existing data/tests cover the deck; licensing of all art/assets remains a gate. |
| Tarot random draw | **Enabled** | Draw is server-side and persisted separately from interpretation. |
| Seed / replay / reversals / spread positions | **Partial** | Reversal and position are present; deterministic replay contract needs explicit product-level verification. |
| Tarot history / outcome | **Enabled** | History, stats and outcome endpoints. |
| Tarot interpretation | **Enabled with limitation** | AI interpretation is separate from draw and guarded; live quality is provider-dependent. |
| Lenormand 36-card system | **Partial** | The agent/UI names Lenormand; canonical 36-card pair/chain/Grand Tableau product is not evidenced as complete. |
| Numerology | **Partial** | Life path and related tools are routed; school, transliteration and all golden cases need explicit documentation. |
| Destiny Matrix | **Enabled with limitation** | Independent matrix calculation and visual; methodology and evidence need final domain review. |
| Palm image input | **Enabled with limitation** | Upload/vision path exists with fixture and quality handling. |
| Palm evidence / confidence | **Enabled with limitation** | Observations and confidence are present; no medical, diagnostic or longevity claims are allowed. |

## Reports and sharing

| Surface | Текущее состояние | Evidence / gap |
|---|---|---|
| PDF generation | **Enabled** | `app/pdfgen/`, `/api/reports/{kind}` and smoke tests. |
| PDF human layer | **Partial** | Narrative, headings and chart assets exist; luxury editorial visual regression is not yet proven. |
| PDF verification layer | **Partial** | Methodology metadata exists in contracts; exact evidence-ID appendix needs consistency review. |
| Report history | **Enabled with limitation** | Append-only versioned rows, owner-scoped `report_id`, latest-version cache and migration are implemented; unified cross-tool archive remains open. |
| Report regeneration | **Enabled with limitation** | `POST /api/reports/{kind}?refresh=true` appends a new immutable version; full visual/product E2E remains open. |
| Share cards | **Enabled with limitation** | Today/chart/compat/reading image endpoints; visual QA and privacy review required. |
| Downloadable assets | **Enabled with limitation** | Binary API and generated images exist; production storage/retention policy is external. |
| Localization | **Enabled with limitation** | RU/EN report labels exist; long-name/long-city and glyph regression set needs expansion. |
| Template system | **Partial** | PDF generation is reusable but not yet a fully documented multi-product template catalog. |

## Monetization and platform operations

| Surface | Текущее состояние | Evidence / gap |
|---|---|---|
| Catalog / prices / plans | **Enabled** | Seeded plans/products and shop/admin endpoints. |
| Credits / entitlements / trial | **Enabled with limitation** | Billing services and tests cover core balance/idempotency; production price ownership is external. |
| Paywall | **Partial** | Limit and entitlement checks exist; complete UX matrix needs browser validation. |
| Web checkout | **Enabled with limitation** | Paddle/LemonSqueezy-style configuration path; requires real provider certification. |
| Telegram Stars / crypto invoice | **Partial** | Endpoints and payment history exist; external credentials, provider certification and live settlement reconciliation are not locally provable. |
| Refund / webhook / reconciliation | **Enabled with limitation** | Signature and idempotency tests exist; live settlement drill is external. |
| Telegram bot | **Enabled with limitation** | aiogram entrypoint and handlers exist; real bot token/device flow is external. |
| Mini App | **Enabled with limitation** | FastAPI static delivery and Telegram WebApp client. |
| Web landing | **Enabled** | RU/EN public pages and legal pages. |
| Public API | **Enabled with limitation** | Authenticated internal product API; not a documented third-party API. |
| Admin | **Enabled with limitation** | Admin HTML and admin router with users, content, flags, plans, orders, broadcasts and audit. |
| CRM / support | **Partial** | Admin notes/tags/message surfaces exist; no separate CRM integration contract. |
| Analytics | **Enabled with limitation** | Event dictionary and analytics repository exist; privacy and production sink verification remain gates. |
| Referrals | **Enabled with limitation** | Referral data and APIs are present; full growth E2E needs verification. |
| Scheduler / jobs | **Enabled with limitation** | Scheduler and broadcast paths exist; production job monitoring is external. |
| Backups / restore | **Enabled with external gate** | Scripts and runbook exist; actual restore drill must be performed against a disposable deployment. |

## Cross-cutting acceptance obligations

Каждый enabled surface обязан сохранять одну и ту же цепочку: **input → validation → deterministic calculation → evidence → interpretation → UI → persistence → history → export → analytics → errors → tests**. Если слой отсутствует, статус понижается до **Partial** или **External gate**, а не маскируется как готовность.

Ключевые внешние gates, которые нельзя честно закрыть только локальным sandbox: Telegram device/initData QA, live LLM quality, платёжная сертификация и settlement reconciliation, production deployment/image validation, backup/restore drill, legal/privacy review и лицензирование визуальных ассетов/движков.

## References

[1]: ../docs/ARCHITECTURE.md "OracleAI architecture contract"  
[2]: ../docs/API.md "OracleAI API contracts"  
[3]: ../docs/CHART_TYPE_CAPABILITIES.md "Chart-type capability matrix"  
[4]: ../app/api/routers/ "Registered API routers"  
[5]: ../miniapp/js/03-data.js "Frontend tool catalog"  
[6]: ../tests/ "Automated regression suite"
