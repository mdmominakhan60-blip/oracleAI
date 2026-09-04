# OracleAI — memory system contract

## Document orientation

| Field | Definition |
|---|---|
| **Purpose** | Opt-in memory contract. |
| **Source of truth** | `app/core/memory.py`, profile routes and repositories. |
| **Scope** | Consent, pause, retrieval, owner isolation, deletion and prompt boundaries. |
| **Do not change** | Do not use memory when disabled or treat retrieved user text as instructions. |
| **Key files** | `app/core/memory.py`, `app/api/routers/profile.py`, `tests/test_memory_evaluation.py`. |
| **Validation** | `pytest -q tests/test_memory_evaluation.py tests/test_agent_context_integrity.py`. |


## Product promise

Memory is a **user-controlled personal context layer**, not a hidden transcript archive. It helps the AI connect permitted facts and prior research to a current question while deterministic domain evidence remains authoritative.

## Lifecycle

| Stage | Contract |
|---|---|
| Consent | Memory is opt-in and visible in profile settings. The server enforces the setting, not only the client. |
| Capture | Store only an explicit fact, goal, preference, interest, reflection or important context that has product value. Do not persist every chat line. |
| Classification | Use stable categories: `PROFILE`, `PREFERENCES`, `FACTS`, `GOALS`, `INTERESTS`, `HISTORY`, `REFLECTIONS`, `IMPORTANT_CONTEXT`, `TEMPORARY_CONTEXT`. |
| Retrieval | Use bounded, relevance-ranked context for the current agent/task. Never retrieve memories belonging to another Telegram ID. |
| Use | Retrieved memory is untrusted context; it can personalize prose but cannot alter calculations, system rules, safety policy or evidence. |
| Visibility | The user can list and inspect stored entries in the Mini App. |
| Edit / delete | The user can remove individual entries; account deletion/anonymization must remove or neutralize all applicable memory rows. |
| Pause | When paused, new memories are not written and existing memory is excluded from AI context. |
| Staleness | Old or contradicted facts must be marked, revised or excluded rather than presented as current truth. |

## Threat model

Memory text is treated as untrusted input. A stored sentence such as “ignore all rules” is data, not an instruction. Retrieval must preserve profile isolation, avoid prompt injection, avoid cross-user joins, redact sensitive data from analytics and never use a memory to invent a chart placement, Tarot card, medical diagnosis or future certainty.

## Evaluation dataset

The minimum evaluation set should contain: relevant and irrelevant memories for the same question, memory-off requests, deletion before recall, profile-isolation attempts, stale fact replacement, contradictory facts, injection-shaped memory text, sensitive-data minimization and multilingual retrieval. Each case must assert the retrieved IDs/categories and whether the response was allowed to use them.

## Current implementation and gaps

`app/core/memory.py`, profile endpoints and the Mini App memory surface implement consented storage, listing, deletion and bounded retrieval. Existing tests cover core privacy boundaries. The remaining quality gate is a dedicated relevance/contradiction/staleness evaluation dataset and a complete self-service account-deletion E2E flow.

## References

[1]: ../app/core/memory.py "Memory policy and retrieval"
[2]: ../app/api/routers/profile.py "Memory API and server-side consent enforcement"
[3]: ../tests/test_agent_context.py "Memory/context regression tests"
