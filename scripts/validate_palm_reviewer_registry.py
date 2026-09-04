"""Validate the non-identifying reviewer registry used by Palm adjudication."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

ID = re.compile(r"^[a-z0-9][a-z0-9._-]{2,63}$")
ROLES = {"annotator", "domain_reviewer", "safety_reviewer"}
INDEPENDENCE = {"independent", "conflict_disclosed", "not_eligible"}
POLICY_VERSION = "palm-human-review-v1"


def validate(registry: Any, require_domain: bool = False) -> list[str]:
    errors: list[str] = []
    if not isinstance(registry, dict):
        return ["registry must be an object"]
    if registry.get("registry_version") != "palm-reviewers-v1":
        errors.append("registry_version must be palm-reviewers-v1")
    reviewers = registry.get("reviewers")
    if not isinstance(reviewers, list) or not reviewers:
        return errors + ["reviewers must be a non-empty array"]
    ids: set[str] = set()
    active_annotators = 0
    active_domains = 0
    for index, reviewer in enumerate(reviewers):
        path = f"reviewers[{index}]"
        if not isinstance(reviewer, dict):
            errors.append(f"{path}: object required")
            continue
        reviewer_id = reviewer.get("reviewer_id")
        if not isinstance(reviewer_id, str) or not ID.fullmatch(reviewer_id):
            errors.append(f"{path}.reviewer_id: invalid stable id")
        elif reviewer_id in ids:
            errors.append(f"{path}.reviewer_id: duplicate id")
        else:
            ids.add(reviewer_id)
        roles = reviewer.get("roles")
        valid_roles = isinstance(roles, list) and bool(roles) and set(roles).issubset(ROLES) and len(set(roles)) == len(roles)
        if not valid_roles:
            errors.append(f"{path}.roles: invalid role list")
        if valid_roles and "annotator" in roles and "domain_reviewer" in roles:
            errors.append(f"{path}.roles: domain reviewer must be distinct from annotator")
        expertise = reviewer.get("expertise_domains")
        if not isinstance(expertise, list) or not expertise or not all(isinstance(item, str) and len(item.strip()) >= 3 for item in expertise):
            errors.append(f"{path}.expertise_domains: non-empty expertise list required")
        if not isinstance(reviewer.get("qualification_reference"), str) or len(reviewer["qualification_reference"].strip()) < 3:
            errors.append(f"{path}.qualification_reference: protected qualification record required")
        active = reviewer.get("active")
        independence = reviewer.get("independence")
        if not isinstance(active, bool):
            errors.append(f"{path}.active: boolean required")
        if independence not in INDEPENDENCE:
            errors.append(f"{path}.independence: invalid")
        conflict = reviewer.get("conflict_of_interest")
        if conflict not in {"none", "disclosed", "not_eligible"}:
            errors.append(f"{path}.conflict_of_interest: declaration required")
        if independence == "independent" and conflict != "none":
            errors.append(f"{path}: independent reviewer must declare conflict_of_interest=none")
        if independence == "conflict_disclosed" and conflict != "disclosed":
            errors.append(f"{path}: conflict_disclosed reviewer must declare conflict_of_interest=disclosed")
        if active is True and (independence == "not_eligible" or conflict == "not_eligible"):
            errors.append(f"{path}: active reviewer cannot be not_eligible")
        attestation = reviewer.get("attestation")
        if not isinstance(attestation, dict):
            errors.append(f"{path}.attestation: object required")
        else:
            if attestation.get("policy_version") != POLICY_VERSION:
                errors.append(f"{path}.attestation.policy_version: invalid")
            if not isinstance(attestation.get("accepted_at"), str) or len(attestation["accepted_at"]) < 10:
                errors.append(f"{path}.attestation.accepted_at: date required")
            if attestation.get("signed") is not True:
                errors.append(f"{path}.attestation.signed: explicit true required")
            if attestation.get("blinded_review") is not True:
                errors.append(f"{path}.attestation.blinded_review: explicit true required")
            if not isinstance(attestation.get("training_reference"), str) or len(attestation["training_reference"].strip()) < 3:
                errors.append(f"{path}.attestation.training_reference: protected training record required")
        if active is True and isinstance(roles, list) and valid_roles and independence == "independent" and conflict == "none" and isinstance(attestation, dict) and attestation.get("signed") is True and attestation.get("blinded_review") is True:
            if "annotator" in roles:
                active_annotators += 1
            if "domain_reviewer" in roles:
                active_domains += 1
    if require_domain:
        if active_annotators < 2:
            errors.append("at least two active attested annotators are required")
        if active_domains < 1:
            errors.append("at least one active attested domain reviewer is required")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--require-domain", action="store_true")
    args = parser.parse_args()
    errors: list[str] = []
    try:
        registry = json.loads(args.registry.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"registry unreadable: {exc}")
        registry = None
    errors.extend(validate(registry, args.require_domain))
    result = {"registry": str(args.registry), "errors": errors, "status": "PASS" if not errors else "FAIL"}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
