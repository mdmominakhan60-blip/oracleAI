# Unified cross-tool history

## Document orientation

| Field | Definition |
|---|---|
| **Purpose** | Unified history and immutable report contract. |
| **Source of truth** | `app/api/routers/history.py`, `app/repo/readings.py`. |
| **Scope** | History projection, owner scope, deep links, deletion and immutable report versions. |
| **Do not change** | Do not expose private content in the shared index or overwrite historical evidence during regeneration. |
| **Key files** | `app/api/routers/history.py`, `app/repo/readings.py`, `tests/test_report_history.py`. |
| **Validation** | `pytest -q tests/test_report_history.py`. |


**Status:** implemented locally for reports, Tarot, chat sessions and diary entries. Palm history remains deferred because the current product does not persist a palm-reading artifact as a first-class record.

## Contract

`GET /api/history?limit=30` returns a normalized, owner-scoped archive. Every item contains `kind`, the source-local integer `entry_id`, a globally readable `source_id` in the form `{kind}:{id}`, `title`, `created_at`, a preview capped at 160 characters, `deep_link` and a deletion note. The response also declares `owner_scoped: true` and `raw_content_included: false`.

The endpoint never returns report bodies, full diary text, birth data, memory facts or raw chat history. Previews are limited to the authenticated owner and are used only to render a compact profile card. Source-specific endpoints remain responsible for opening full content and performing destructive actions.

| Kind | Source | Exact route | Destructive owner |
|---|---|---|---|
| `report` | Immutable report history | `/api/reports/{kind}?report_id={id}` | Report lifecycle / regeneration contract |
| `tarot` | Completed Tarot reading | `/api/tarot/history/{reading_id}` | Tarot outcome/source surface |
| `chat` | Active chat session | `/api/chat/{agent}/sessions/{thread_id}` | Chat session archive endpoint |
| `diary` | Personal diary entry | `/api/diary/{entry_id}` | Diary/account lifecycle |

## UI

The profile History tab renders the first eight normalized entries as full-width keyboard-focusable cards. The cards share the established glass-and-champagne design language, have a minimum touch target, expose an accessible label and preserve ellipsis behavior for long titles or previews. Report and Tarot cards reuse their existing modal flows; chat cards reopen the correct agent session; diary cards open an owner-scoped modal.

## Security tests

The API regression creates one item in each source, checks that the normalized response contains all four kinds, proves report bodies are absent, verifies exact Tarot/chat/diary links and creates a second user to prove foreign report IDs do not leak into the first user’s archive. The source routes themselves retain their owner predicates.

## Deferred boundary

Palm image analysis currently produces an interpretation flow but does not persist a first-class historical palm artifact. It must not be represented as present in this archive until retention, consent, deletion and visual evidence contracts are implemented.
