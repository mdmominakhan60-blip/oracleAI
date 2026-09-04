# OracleAI — agent architecture

## Runtime pipeline

```text
User request
  → intent and agent routing
  → allowed deterministic domain tool(s)
  → immutable evidence object
  → bounded profile and consented memory context
  → LLM interpretation or offline fallback
  → grounding/safety validation
  → response, persistence, analytics
```

The browser and Telegram bot do not call providers directly. `app/core/agent.py`, `app/core/agents/`, `app/core/tool_registry.py` and `app/core/interpretation.py` form the runtime boundary. Deterministic facts are calculated before interpretation; the model cannot rewrite the evidence object.

## Agent contract

| Contract field | Required behavior |
|---|---|
| Identity | Stable code, name and visual identity. |
| Role and tone | Agent-specific role and bounded style, not merely a different avatar. |
| Capabilities | Explicit skills and product surfaces available to the agent. |
| Prohibited behavior | No invented cards/placements, guaranteed events, diagnosis, financial/legal advice or third-party mind reading. |
| Allowed tools | Tool allow-list enforced by runtime routing. |
| Evidence | Deterministic tools must return source facts and limitations before prose. |
| Memory policy | Only consented, bounded context is retrieved; memory-off is server-side. |
| Escalation | Ask for missing birth data, clarification or safer human support when needed. |
| Evaluation | Route, grounding, language, safety and next-step cases are kept in `data/llm_eval/` and `tests/`. |

## Evidence contract

The current `Evidence` object contains a domain kind, fact lines, allowed points, precision flags and limitations. Its prompt serialization is closed to the model and is intentionally separate from generated prose. Every new deterministic tool must add, at minimum, the following evidence fields either directly or in its structured result:

| Field | Meaning |
|---|---|
| `source` | Canonical code/engine or persisted draw source. |
| `calculation_method` | Named school, algorithm and product version. |
| `timestamp` | Calculation/snapshot time where relevant. |
| `inputs` | Validated inputs, excluding unnecessary PII from analytics. |
| `configuration` | Zodiac, ayanamsa, house, orb or spread configuration. |
| `result` | Deterministic result that the model may explain but not modify. |
| `confidence` | Quality/confidence for image or uncertain observations. |
| `limitations` | Missing time, incomplete data, ambiguity and forbidden interpretations. |

## Tool execution rules

1. Validate input at the API boundary and again in the domain tool where the invariant matters.
2. Return a deterministic result or a typed error; never silently fall back to a made-up value.
3. Persist random draws and calculation snapshots before interpretation.
4. Include the same truth state in API, UI, AI and PDF. In particular, `time_known=false` hides houses, ASC, MC and house-based claims everywhere.
5. Apply grounding checks to generated text and use an offline response based on actual evidence when a provider is unavailable.
6. Keep user ownership and rate limits in server-side dependencies and repositories.

## Memory policy

Memory is optional, consented and bounded. Profile facts, preferences, goals, interests, history, reflections, important context and temporary context are different categories; not every chat line is eligible for long-term storage. Memory retrieval must be relevant to the current task, isolated by Telegram ID, visible in the user UI, editable/deletable, and excluded when memory is paused. Memory contents are untrusted data and must not override system safety rules or tool evidence.

## Agent differentiation

The agents should differ through their allowed skills, prompt policies, evidence requirements and next-step behavior. A regression test must prove that a route request goes to the intended agent, unsupported tools are refused, and all agents inherit the shared high-stakes safety boundary.

## References

[1]: ../app/core/agent.py "OracleAI orchestration and report generation"  
[2]: ../app/core/interpretation.py "Evidence and grounding contracts"  
[3]: ../app/core/tool_registry.py "Deterministic tool registry and execution"  
[4]: ../app/core/agents/ "Agent definitions and runtime"
