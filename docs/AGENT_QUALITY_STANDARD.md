# OracleAI agent quality standard

## Purpose

OracleAI uses four file-backed specialist agents behind a shared harness. The quality bar is not only a good prompt: every profile must expose a bounded runtime budget, an explicit risk/memory/output contract, evidence rules, tool allow-list, progressive skills and repeatable evaluation cases.

The four public specialists remain backward-compatible under their existing API codes:

| File-backed profile | Public code | Scope | Skills | Deterministic tools | Eval cases |
| --- | --- | ---: | ---: | ---: | ---: |
| Lilith | `oracle` | reflective guidance, Matrix, diary and practices | 31 | 11 | 13 |
| Urania | `astro` | natal chart, placements, nodes, transits and compatibility | 39 | 22 | 15 |
| Madame Lenormand | `tarot` | RWS Tarot spreads, card evidence, choice and relationship readings | 35 | 3 | 13 |
| Mira | `chiromant` | palm-photo quality, visual evidence, visible zones and comparison | 34 | 3 | 13 |

## Runtime contract

Each `agent.yaml` is validated at load time. `skills_max_active`, `max_turns`, `max_tool_calls` and `timeout_s` must be positive. `risk_level` is one of `low`, `medium`, `high`; memory is explicitly `opt_in` or `disabled`; and `output_contract` follows the versioned `name.vN` format. These values are passed into the actual LLM workflow rather than being decorative profile metadata.

A chat response preserves the legacy `answer` field and additionally exposes a non-sensitive `agent_profile` and `proof` envelope. `proof.mode` distinguishes deterministic grounding, offline reflection and safety response. `proof.tools_used` contains only the names of tools actually invoked for that request; no hidden reasoning or personal data is included. The Mini App renders this as a compact specialist proof card in both Russian and English.

## Tool quality contract

Every registered tool has a stable name, user-safe description, closed input schema and callable runner. Model-generated arguments are bounded at the execution boundary: card counts, history limits, career horizons, memory text/query length and compatibility relation are normalized or rejected with a human-readable response. Placement errors enumerate the full public catalog, including Rahu/Ketu, Lilith and expanded natal points.

Tool output is evidence, not instruction. The agent must state what was calculated or observed before giving a symbolic interpretation, acknowledge missing precision or image quality, and never turn a tool result into a medical, legal, financial or guaranteed predictive claim.

## Skill routing contract

The selector renders a compact index of all domain skill names/descriptions plus only bounded routed hints. It uses skill name, description, body, tags, metadata and multilingual intent aliases for routing, but does not inject every skill body into the initial prompt. Exact high-signal tokens such as `synastry`, `lunar_node`, `choice`, `mount` and `palm` receive priority over broad handbook overlap. The agent uses the domain activation tool to load one selected body on demand; dependencies such as the shared anti-Barnum protocol are resolved before delivery.

## Acceptance gate

Run the following from the repository root:

```bash
PYTHONPATH=. python3 scripts/check_agent_quality.py
PYTHONPATH=. LLM_PROVIDER=off python3 -m pytest tests/test_agent_file_harness.py tests/test_agent_context.py tests/test_miniapp_actions.py tests/test_openai_compat.py tests/test_llm.py tests/test_api.py -q
ruff check app tests scripts
find miniapp/js admin -name '*.js' -print0 | xargs -0 -n1 node --check
```

The deterministic gate currently checks **33 registered tools, 139 file-backed skills and 54 evaluation cases**, verifies all four profile-to-legacy mappings, resolves skill dependencies, exercises the original 20-case Urania/Lilith routing set, the 10-case Vedic/adversarial set and the 20-case Mira/Lenormand routing set, validates tool schemas and checks that user-visible proof surfaces are wired into the Mini App.

## Safety boundary

These agents provide symbolic and reflective services. They must not present astrology, Tarot, numerology or palmistry as validated diagnosis, legal or financial advice, certain prediction, or proof of another person’s private thoughts. A missing input is a reason to ask a precise question, not to fill the gap with a confident story.
