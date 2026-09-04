"""Build reviewable per-agent skill manifests from SKILL.md front matter."""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.agents.file_loader import load_profiles

ROOT = Path(__file__).resolve().parents[1] / "app" / "agents"


def main() -> None:
    profiles = load_profiles()
    for agent_id, profile in profiles.items():
        manifest = {
            "agent": agent_id,
            "legacy_code": profile.legacy_code,
            "manifest_version": "1.0.0",
            "skills_count": len(profile.skills),
            "skills": [
                {
                    "name": skill.name,
                    "version": skill.version,
                    "depends_on": list(skill.dependencies),
                    "requires_tools": list(skill.requires_tools),
                    "tags": list(skill.tags),
                    "path": str(Path(skill.path).relative_to(ROOT.parent.parent)),
                }
                for skill in profile.skills
            ],
        }
        target = ROOT / agent_id / "skills.manifest.yaml"
        target.write_text(yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True), encoding="utf-8")
        print(agent_id, "manifest skills=", len(profile.skills))


if __name__ == "__main__":
    main()
