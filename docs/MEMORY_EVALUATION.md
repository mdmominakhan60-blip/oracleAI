# Memory evaluation

**Дата:** 26 августа 2026

The local evaluator uses synthetic facts only and exercises the real SQLite memory repository plus policy helpers:

```bash
LLM_PROVIDER=off EMBED_MODEL= python3 scripts/evaluate_memory.py
```

| Case | Result |
|---|---|
| Relevant recall | Pass |
| Irrelevant fact excluded from a narrow query | Pass |
| Owner isolation | Pass |
| Memory pause prevents new writes and AI recall | Pass |
| Prompt-injection-shaped fact is wrapped as untrusted data | Pass |
| Contradictory residence facts are detected without choosing a winner | Pass |
| Account anonymization clears memories/diary and disables memory/push/age flags | Pass |

The run reports **7/7 checks passed**. Recall caching now includes the requested result limit, preventing a wider cached result from leaking irrelevant facts into a narrower prompt. Contradictions remain a review/revision signal; the system does not silently invent which fact is current. Production still needs retention policy sign-off, real user deletion verification and longitudinal stale-fact telemetry.
