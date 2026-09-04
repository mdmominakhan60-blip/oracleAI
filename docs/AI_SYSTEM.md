# OracleAI — AI system

## Document orientation

| Field | Definition |
|---|---|
| **Purpose** | Explain the implemented agent, skill, tool, context, memory and safety pipeline. |
| **Source of truth** | `app/core/agents/`, `app/core/tool_registry.py`, `app/core/agent.py`, `app/core/llm.py` and the agent files under `app/agents/`. |
| **Scope** | Runtime routing and evidence handling for Lilith, Urania, Madame Lenormand and Mira. |
| **Do not change** | Do not move deterministic calculations into prompts, treat retrieved user data as instructions, bypass server-side safety/eligibility, or expose raw personal data to analytics. |
| **Key files** | `app/core/agents/registry.py`, `app/core/agents/routing.py`, `app/core/agents/context.py`, `app/core/agents/runtime.py`, `app/core/memory.py`, `app/core/shared_context.py`, `app/core/safety.py`. |
| **Validation** | `python3 -m scripts.check_agent_context_contracts`, `python3 -m scripts.check_agent_quality`, `python3 -m scripts.check_domain_evals`, `pytest -q tests/test_agent_context.py tests/test_agent_context_integrity.py tests/test_agent_routing.py tests/test_safety.py`. |

## System boundary

OracleAI uses code to calculate domain evidence and an LLM to explain that evidence in a bounded, localized and safety-checked response. The client does not call a provider directly. The server assembles identity, profile, language, consented memory, bounded history and deterministic evidence before invoking the selected agent.

The four implemented agents are:

| Agent | Role | Evidence boundary |
|---|---|---|
| Lilith | Self-reflection, diary and practices | May use explicitly consented memory and diary context; does not diagnose or promise outcomes. |
| Urania | Western and Vedic astrology | May interpret server-generated chart/product evidence; must preserve precision and school boundaries. |
| Madame Lenormand | Tarot and card-oriented reflection | May interpret persisted cards, positions and orientation; must not invent a draw or certainty. |
| Mira | Palm/visual reflection | May interpret normalized visual observations and confidence; must not turn palm evidence into diagnosis or deterministic prediction. |

Agent identity, persona, domain, default skills and tool allow-lists are defined server-side. The requested agent name is validated before routing; user input cannot add a tool or skill to the allow-list.

## Request and context assembly

The runtime follows this order:

1. The API or bot establishes the authenticated user and checks eligibility, age confirmation, rate limits and relevant product permissions.
2. `app/core/agents/routing.py` selects an `AgentSpec` and the bounded skill index for the requested agent.
3. `app/core/agents/context.py` builds compact recent history and adds the current question once. It does not send an unbounded transcript.
4. `app/core/shared_context.py` may add recent recommendations and the current deterministic transit snapshot. These records are explicitly marked as untrusted data.
5. The selected deterministic tool or visual preflight produces bounded evidence. The model never becomes the calculation source for charts, cards, placements or upload validation.
6. The LLM receives the system policy, localized prompt, bounded context and evidence. The result is normalized, checked for unsafe or ungrounded claims, and only then persisted or returned.

The prompt boundary is semantic as well as technical: profile fields, diary, memory, history and shared recommendations are data; they are not instructions. Injection-shaped text retrieved from a user record must remain data and cannot alter policy, routing or tool permissions.

## Skills and tools

`app/core/tool_registry.py` is the registry for tool schemas, agent allow-lists and executors. A skill file under `app/agents/<agent>/skills/` is on-demand domain guidance, not executable authority. The runtime loads the selected skill body only after the server has selected the agent and verified its domain.

Tools are divided into deterministic evidence tools, bounded retrieval tools and product helpers. Unknown tools, malformed arguments and executor failures return safe fallbacks rather than granting implicit access. Tool calls are bounded by `LLM_MAX_TOOL_CALLS`, workflow timeout, concurrency and cost settings from `app/config.py`.

## Memory and shared context

Persistent memory is opt-in. The memory service stores bounded facts only after consent, applies owner scoping and deletion rules, and can be paused. When memory is disabled, the server must not place personal memory, diary content or dynamic recommendations into the prompt. Recalled memory remains untrusted context and cannot create a chart fact, Tarot card, diagnosis or guarantee.

Shared context is a separate, bounded stream for recent agent recommendations and a deterministic daily transit snapshot. It is owner-scoped, time-bounded and deleted with the account. It exists to avoid agents independently recomputing or contradicting the same current snapshot; it does not become a policy or instruction channel.

## Deterministic evidence contracts

| Surface | Canonical evidence | AI limitation |
|---|---|---|
| Natal chart | `app/core/astro.py` and `app/core/chart_contract.py` | Unknown birth time suppresses houses, ASC, MC and wheel; no invented placements. |
| Chart products | `app/core/chart_products.py` and `app/api/contracts/chart_products.py` | Synastry, transit, composite and solar-return semantics remain JSON-first and versioned. |
| Tarot | `app/core/tarot.py` and persisted reading ledger | Interpret only saved cards, positions and orientation. |
| Palm | `app/core/palm/`, `palm_vision.py`, `palm_lines.py` and `palm_full_scope.py` | Use normalized observations and quality/confidence; never claim medical or guaranteed predictive meaning. |
| Diary/memory | `app/core/memory.py`, `app/repo/` and profile contracts | Consent, owner isolation, pause and deletion are mandatory. |

The domain contract is documented separately in [`DOMAIN/README.md`](DOMAIN/README.md), while the architecture and transport boundaries are documented in [`ARCHITECTURE.md`](ARCHITECTURE.md) and [`API.md`](API.md).

## Fallback, safety and cost controls

If no live provider is configured, the application uses the explicitly bounded offline fallback. Provider failures, empty responses, malformed structured output and timeouts are mapped to safe user-facing errors or fallback text; they must not leak a provider response, stack trace or hidden prompt.

Safety checks run before and after the model call. Crisis/high-risk paths are handled by code before paid LLM work where applicable. The response guard rejects unsupported deterministic claims, medical/diagnostic claims, third-party mind reading, guarantees and unsafe escalation. A paid action must not be charged when the request fails before a valid response is delivered.

Concurrency, per-minute limits, tool-call count, workflow timeout and maximum estimated spend are operational controls, not documentation promises. Their defaults and environment variables are defined in `app/config.py` and the environment templates.

## Validation contract

The local AI gates prove code contracts and synthetic evaluations only. They do not certify a live provider, Telegram WebView, production monitoring, human safety review or public launch. Record external evidence in `docs/EVIDENCE/` and keep the current go/no-go state in [`RELEASE/CURRENT_STATUS.md`](RELEASE/CURRENT_STATUS.md).

## References

[1]: [app/core/agents/registry.py](../app/core/agents/registry.py) — agent specifications and server-owned metadata.
[2]: [app/core/tool_registry.py](../app/core/tool_registry.py) — skill/tool registry and allow-lists.
[3]: [app/core/agents/context.py](../app/core/agents/context.py) — bounded conversation context.
[4]: [app/core/memory.py](../app/core/memory.py) and [app/core/shared_context.py](../app/core/shared_context.py) — consented memory and shared context.
[5]: [app/core/safety.py](../app/core/safety.py) and [app/services/chat.py](../app/services/chat.py) — safety and chat orchestration.
