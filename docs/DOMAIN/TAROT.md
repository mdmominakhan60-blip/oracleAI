# Tarot domain contract

## Canonical deck

OracleAI uses a self-hosted Rider–Waite–Smith-inspired 78-card corpus in `app/core/tarot.py`. The deck contains 22 Major Arcana and 56 Minor Arcana. The Minor Arcana has four suits—Cups, Pentacles, Swords and Wands—with 14 ranks per suit. Every card has a stable image/card ID, name, arcana class and suit metadata; Major cards additionally carry short meaning/advice fields and Minor cards use the bounded `RWS_MINOR` meanings where defined.

The hard invariants are tested: total count 78, unique IDs, 22/56 split, four suits and 14 cards per suit. Unknown cards, duplicate cards, ID/name mismatch and invalid orientation are rejected when building a reading ledger. This validation protects historical replay from silently accepting corrupted evidence.

## Draw contract

`tarot.draw(n)` uses `secrets.SystemRandom` by default and returns a sample without replacement. `n` must be an integer from 1 to 78; impossible sizes are rejected rather than silently clamped. Orientation is generated independently as a boolean and stored with each card. A string seed is supported only for deterministic tests and golden fixtures; product draws do not claim cryptographic guarantees beyond the default system RNG and do not expose the seed.

Spread definitions are explicit. Each spread has a stable code, title, ordered positions, access tier and guide. The number of cards is derived from the selected spread positions. The canonical spread code is used in the ledger checksum, so an unknown spread cannot create an ambiguous historical contract.

## Persistence and replay

The shared Tarot service draws and persists the cards before requesting interpretation. The database stores the question, spread, cards, surface and payment/access metadata. Interpretation is a separate owner-scoped operation; finalization is append-only and cannot overwrite an existing answer. History reconstructs the ledger from persisted cards and never calls the random generator again.

`tarot-ledger-v1` contains ordered entries with card ID, card name, position, arcana, suit, boolean reversal and normalized orientation. It also contains adjacent-combination cues and a truncated SHA-256 checksum over the canonical deck/spread/entries payload. Replay recomputes this ledger and rejects a checksum mismatch. The ledger is evidence, not the interpretation itself.

## Interpretation boundary

The model receives the exact question, exact ordered cards, exact positions and exact orientations. It must not add or reverse cards, infer an unrecorded spread, claim third-party intent as fact, or promise timing/future certainty. User question, partner name, diary and memory text are untrusted data and cannot override system or evidence instructions.

A Tarot reading is a reflective symbolic exercise. The product must not convert it into medical diagnosis, guaranteed financial outcome, guaranteed relationship outcome, mortality prediction, legal decision or deterministic future claim. Fear-based pressure and generic certainty are quality failures, even if the prose is stylistically impressive.

## Versioning and known limits

The current deck ID is `rws-78-v1`; the replay contract is `tarot-replay-v1`. Changing card IDs, meanings, spread positions, orientation semantics or checksum fields requires a migration/compatibility decision and a new golden corpus. The current tests cover deck invariants, seeded replay, orientation, duplicate rejection, unknown-card rejection and persistence ownership. A fresh live-model critic and manual review of all RWS symbolism remain external quality gates.
