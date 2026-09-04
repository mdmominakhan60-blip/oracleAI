# OracleAI file-backed agents

Each directory under this folder is a human-readable agent profile. The profile is composed of `agent.yaml`, `SYSTEM.md`, `skills/`, `knowledge/`, `tools/` and `evals/`. The shared runtime remains in `app/core/agents`; these folders contain profile data and domain capability packs.

## Add or edit a skill

Create `app/agents/<agent>/skills/<skill-name>/SKILL.md`. Use lowercase kebab-case for `<skill-name>`. The file must start with YAML front matter containing `name` and `description`; keep the name equal to the directory name. Add `references/` for large domain material rather than putting an entire handbook into the main skill file. Skills are loaded on demand and the runtime selects at most three per user turn.

A skill may describe a workflow and knowledge, but it cannot grant itself new tools or permissions. Tool access is controlled by the profile and the server-side policy layer.

## Change an agent

Edit `agent.yaml` for display metadata, model tier, limits, memory mode and the allow-list of legacy tool aliases. Edit `SYSTEM.md` for the short identity, voice and domain boundaries. Do not copy the shared runner, database code, provider logic or safety middleware into an agent directory.

## Add a domain tool

Implement the deterministic operation in the existing domain/core layer or in a small agent adapter. Register its typed contract in the tool registry before exposing it in `agent.yaml`. The contract must validate arguments and results, define timeout and risk, declare allowed agents and state whether approval is required. Keep legacy tool aliases until the migration is complete.

## Verify a change

Run the following commands from the repository root:

```bash
PYTHONPATH=. LLM_PROVIDER=off python3 -m pytest -q
ruff check app scripts tests
PYTHONPATH=. LLM_PROVIDER=off python3 scripts/check_agent_stability.py
PYTHONPATH=. LLM_PROVIDER=off python3 -m scripts.selfcheck
python3 scripts/check_design_contract.py
PYTHONPATH=. LLM_PROVIDER=off python3 scripts/release_gate.py
```

The live LLM check is intentionally separate. It requires configured provider credentials and a staging environment; a successful offline selfcheck proves fallback and domain code, not live provider quality.

## Current profiles

| Directory | Legacy code | Domain |
|---|---|---|
| `lilith` | `oracle` | self-reflection, Matrix, diary, memory and practices |
| `urania` | `astro` | calculated natal astrology, transits and compatibility |
| `lenormand` | `tarot` | Rider-Waite-Smith tarot symbolism |
| `mira` | `chiromant` | visible palm evidence and traditional palmistry |
