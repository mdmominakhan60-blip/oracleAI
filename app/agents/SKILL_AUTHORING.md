# Skill authoring guide

A skill is a small, versioned capability package. It teaches a profile **what to know and how to work**, but it never grants permissions. Tools remain controlled by `agent.yaml` and the shared runtime.

## Add a skill in five minutes

Create `app/agents/<agent>/skills/<skill-name>/SKILL.md`. Use lowercase kebab-case and keep one capability per skill. Start with this front matter:

```yaml
---
name: example-skill
version: 1.0.0
description: One sentence describing when this skill is useful.
depends_on:
  - anti-barnum-protocol
requires_tools:
  - tool_name
tags: [domain, workflow]
metadata:
  oracleai_agent: urania
  oracleai_loading: on_demand
  oracleai_output_contract: agent_response.v1
---
```

The body should contain `Purpose`, `Evidence contract`, `Workflow`, `Failure modes`, `Anti-Barnum gate` and `Output contract`. A skill must say what evidence it may use, how to handle missing data, what it must never claim and what observable next step it returns. Domain-critical skills should also include a method-specific ledger, precision/confidence rules, a counter-hypothesis step and at least one concrete example of a quality failure.

Use `tags` for high-signal concepts in both Russian and English where useful; the progressive selector reads names, descriptions, tags and metadata but still keeps the final active set bounded. Use `requires_tools` to declare the smallest deterministic evidence source. A required tool must exist in the agent's allow-list and have a closed input schema. The UI/API may expose proof of tools actually used, but a skill must never request hidden reasoning or expose private raw provider output.

## Dependency rules

Dependencies are other skill names in the same agent package. The loader detects missing dependencies and cycles. Put reusable safety or evidence skills first. The resolver topologically orders dependencies before the selected skill. A dependency does not bypass tool permissions.

## Tool onboarding

When adding a new function, first add a typed tool to the agent's `tools` allow-list, then add a skill with `requires_tools`, then add an eval case that proves the tool is selected and its output is bounded. Never put an API key, database write or unrestricted shell instruction inside a skill.

## Knowledge modules

Large theory belongs in `knowledge/`, not in every skill. `DOMAIN_PLAYBOOK.md` contains the operating methodology; a future `references/` file can hold source notes. Skills should link conceptually to the relevant chapter and add the task-specific procedure.

## Quality gate

A skill is ready only when its name and directory match, version is valid semver, its description explains activation, dependencies resolve, tools are allow-listed, and the relevant normal and adversarial eval coverage exists. The four flagship specialist skills (`matrix-reading`, `lunar-nodes`, `reversed-cards`, `palm-photo-quality`) are reference implementations for domain depth. Run:

```bash
PYTHONPATH=. python3 scripts/validate_skill_library.py
PYTHONPATH=. python3 scripts/check_domain_evals.py
PYTHONPATH=. python3 scripts/check_agent_quality.py
```
