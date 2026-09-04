# OracleAI composable skill library

OracleAI now treats each specialist as a package, not a monolithic prompt. Shared runtime code remains in `app/core`; domain behavior lives in `app/agents/<agent>/`. A skill is a versioned, on-demand capability with a narrow purpose, evidence contract, workflow and failure modes.

## Package layout

```text
app/agents/<agent>/
├── agent.yaml                 # identity, tool allow-list, limits
├── SYSTEM.md                  # short role and hard boundaries
├── skills.manifest.yaml       # generated index for review
├── knowledge/
│   └── DOMAIN_PLAYBOOK.md     # domain methodology loaded with the context
├── skills/
│   └── <skill-name>/SKILL.md  # one composable capability
└── evals/cases.yaml           # normal and adversarial cases
```

The loader validates every package, reads `version`, `depends_on`, `requires_tools` and `tags`, detects missing/cyclic dependencies and checks skills against the agent's allow-listed tools. The runtime renders a compact `[SKILL_INDEX]` with short cards for the complete domain registry, bounded routed hints and a playbook synopsis. Full skill bodies are not inserted eagerly: the agent calls the domain-specific activation tool only when the current question requires that workflow; dependencies such as `anti-barnum-protocol` are then resolved in deterministic order before the activated body is returned. Activated skill text remains below the immutable safety boundary.

## Fast knowledge improvement

To improve knowledge without changing runtime code, edit or add one `SKILL.md` and, if the material is broad, update `knowledge/DOMAIN_PLAYBOOK.md`. Keep a skill narrow and composable. For example, add `retrogrades` rather than a single giant `astrology-everything` file. Use `depends_on` to reuse the shared anti-Barnum layer.

To teach a new function, first implement and type the function in the shared tool layer, add its name to the intended agent's `tools` list, create a skill with `requires_tools`, add a normal and adversarial eval case, rebuild the manifest and run the gates. A skill cannot grant a tool permission by itself.

```bash
python3 scripts/new_agent_skill.py urania electional-research \
  "Compare candidate dates using supplied constraints and calculated data" \
  --tools get_transits --tags timing choice
python3 scripts/build_skill_manifests.py
PYTHONPATH=. python3 scripts/validate_skill_library.py
PYTHONPATH=. python3 scripts/check_domain_evals.py
```

## Quality standard

A professional skill must identify its evidence class, use a deterministic tool when data is required, state uncertainty, include at least one alternative explanation, specify failure modes and return a practical next step. Domain playbooks define terminology and method; they do not override safety or permissions.

The repository deliberately measures methodological quality rather than claiming that symbolic practices are scientifically validated. For astrology, tarot and palmistry, the response must distinguish calculation or visible observation from traditional interpretation. Health, death, fertility, lifespan, diagnosis, financial certainty and third-party mind reading remain blocked.
