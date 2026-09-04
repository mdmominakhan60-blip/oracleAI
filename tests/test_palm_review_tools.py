import importlib.util
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load_script(name: str):
    path = ROOT / "scripts" / name
    scripts_dir = str(ROOT / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _record(status="adjudicated", expected_state="observed"):
    return {
        "record_id": "gold-001",
        "image_path": "protected/gold-001.jpg",
        "image_sha256": "a" * 64,
        "source": {"kind": "synthetic_contract", "license_or_permission": "generated-test", "collected_at": "2026-08-27"},
        "consent": {"status": "synthetic_no_person", "raw_image_retention": "synthetic", "review_use": True},
        "split": "challenge",
        "capture": {"quality_state": "usable", "view_type": "open_palm", "hand_count": 1, "hand_side": "unknown", "expected_user_action": "analyze"},
        "regions": [{
            "region_id": "heart-001", "topic": "heart_line", "visibility": "clear",
            "evidence_state": expected_state, "expected_confidence_band": "high", "annotator_refs": ["human-a", "human-b"],
        }],
        "expected_claims": [{"claim_id": "claim-001", "topic": "heart_line", "allowed_state": expected_state, "must_be_grounded_in_region": "heart-001"}],
        "prohibited_claims": ["diagnosis"],
        "adjudication": {"status": status, "annotators": ["human-a", "human-b"], "domain_reviewer_required": True, "domain_reviewer": "domain-c" if status == "adjudicated" else None},
    }


def test_corpus_template_passes_schema_only():
    validator = _load_script("validate_palm_corpus.py")
    manifest = ROOT / "data/palm_golden/manifest.template.jsonl"
    assert validator.main.__module__
    record = json.loads(manifest.read_text(encoding="utf-8"))
    errors = validator._validate_record(record, 1, None, True)
    assert errors == []


def test_corpus_validator_rejects_unknown_as_observed():
    validator = _load_script("validate_palm_corpus.py")
    record = _record(expected_state="unknown")
    record["regions"][0]["visibility"] = "not_visible"
    record["regions"][0]["expected_confidence_band"] = "zero"
    record["expected_claims"][0]["allowed_state"] = "unknown"
    errors = validator._validate_record(record, 1, None, True)
    assert errors == []
    record["regions"][0]["evidence_state"] = "observed"
    errors = validator._validate_record(record, 1, None, True)
    assert any("not_visible cannot be observed/inferred" in error for error in errors)


def test_human_review_passes_only_adjudicated_exact_coverage(tmp_path):
    runner = _load_script("run_palm_human_review.py")
    manifest = {"gold-001": _record()}
    predictions = {"gold-001": {"record_id": "gold-001", "quality_state": "usable", "view_type": "open_palm", "observations": [{
        "topic": "heart_line", "visibility": "clear", "evidence_state": "observed", "confidence": 0.9,
    }]}}
    result = runner.evaluate(manifest, predictions)
    assert result["semantic_signoff"] == "PASS"
    assert result["metrics"]["false_observed_count"] == 0

    blocked_manifest = {"gold-001": _record(expected_state="unknown")}
    blocked_predictions = {"gold-001": {"record_id": "gold-001", "quality_state": "usable", "observations": [{
        "topic": "heart_line", "visibility": "clear", "evidence_state": "observed", "confidence": 0.95,
    }]}}
    blocked = runner.evaluate(blocked_manifest, blocked_predictions)
    assert blocked["semantic_signoff"] == "BLOCKED"
    assert "critical false-observed region promotion detected" in blocked["block_reasons"]


def test_independent_critic_reports_actionable_semantic_block():
    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts/palm_independent_critic.py")],
        check=True, capture_output=True, text=True,
    )
    report = json.loads(completed.stdout)
    required = {
        "two independent annotators per record",
        "domain-reviewer adjudication for test/challenge records",
        "immutable image hashes and exact prediction/manifest coverage",
        "zero critical false-observed promotions",
    }
    assert report["critic"] == "palm-independent-static-critic-v3"
    assert report["deterministic_contract"] == "PASS"
    assert report["semantic_accuracy"] == "BLOCKED"
    assert required.issubset(set(report["required_for_semantic_signoff"]))
    assert "adjudicated manifest not supplied:" in report["semantic_block_reasons"][0]
    assert "no human-review report supplied" in report["semantic_block_reasons"]


def test_human_review_cli_break_and_retest(tmp_path):
    manifest_path = tmp_path / "manifest.jsonl"
    predictions_path = tmp_path / "predictions.jsonl"
    output_path = tmp_path / "review.json"
    manifest_path.write_text(json.dumps(_record(), ensure_ascii=False) + "\n", encoding="utf-8")
    predictions_path.write_text(json.dumps({
        "record_id": "gold-001", "quality_state": "usable", "view_type": "open_palm",
        "observations": [{"topic": "heart_line", "visibility": "clear", "evidence_state": "observed", "confidence": 0.9}],
    }) + "\n", encoding="utf-8")
    command = [sys.executable, str(ROOT / "scripts/run_palm_human_review.py"), "--manifest", str(manifest_path), "--predictions", str(predictions_path), "--out", str(output_path)]
    passed = subprocess.run(command, check=False, capture_output=True, text=True)
    assert passed.returncode == 0
    assert json.loads(output_path.read_text(encoding="utf-8"))["semantic_signoff"] == "PASS"

    blocked_manifest = _record(expected_state="unknown")
    blocked_manifest["regions"][0]["visibility"] = "not_visible"
    blocked_manifest["regions"][0]["expected_confidence_band"] = "zero"
    manifest_path.write_text(json.dumps(blocked_manifest, ensure_ascii=False) + "\n", encoding="utf-8")
    blocked = subprocess.run(command, check=False, capture_output=True, text=True)
    assert blocked.returncode == 2
    assert "critical false-observed" in json.loads(output_path.read_text(encoding="utf-8"))["block_reasons"][0]


def test_reviewer_registry_requires_attested_independent_roles():
    registry_validator = _load_script("validate_palm_reviewer_registry.py")
    registry = json.loads((ROOT / "data/palm_golden/reviewer_registry.template.json").read_text(encoding="utf-8"))
    assert registry_validator.validate(registry, require_domain=True) == []
    registry["reviewers"][0]["independence"] = "not_eligible"
    errors = registry_validator.validate(registry, require_domain=True)
    assert any("active reviewer cannot be not_eligible" in error for error in errors)


def _reviewer_registry():
    def reviewer(reviewer_id, roles):
        return {
            "reviewer_id": reviewer_id,
            "roles": roles,
            "expertise_domains": ["visual evidence review"],
            "qualification_reference": "protected-qualification-record",
            "active": True,
            "independence": "independent",
            "conflict_of_interest": "none",
            "attestation": {
                "policy_version": "palm-human-review-v1",
                "accepted_at": "2026-08-27",
                "signed": True,
                "blinded_review": True,
                "training_reference": "protected-training-record",
            },
        }
    return {"registry_version": "palm-reviewers-v1", "reviewers": [
        reviewer("human-a", ["annotator"]),
        reviewer("human-b", ["annotator"]),
        reviewer("domain-c", ["domain_reviewer", "safety_reviewer"]),
    ]}


def test_reviewer_registry_rejects_conflict_and_role_shortcuts():
    registry_validator = _load_script("validate_palm_reviewer_registry.py")
    registry = _reviewer_registry()
    registry["reviewers"][0]["attestation"].pop("blinded_review")
    registry["reviewers"][1]["conflict_of_interest"] = "disclosed"
    registry["reviewers"][2]["roles"].append("annotator")
    errors = registry_validator.validate(registry, require_domain=True)
    assert any("blinded_review" in error for error in errors)
    assert any("conflict_of_interest=none" in error for error in errors)
    assert any("distinct from annotator" in error for error in errors)


def test_corpus_registry_linkage_and_require_adjudicated():
    validator = _load_script("validate_palm_corpus.py")
    registry = _reviewer_registry()
    reviewer_map = {item["reviewer_id"]: item for item in registry["reviewers"]}
    record = _record()
    record["regions"][0]["annotator_refs"] = ["human-a", "human-b"]
    record["adjudication"]["annotators"] = ["human-a", "human-b"]
    record["adjudication"]["domain_reviewer"] = "domain-c"
    assert validator._validate_record(record, 1, None, True, reviewer_map, True) == []
    record["adjudication"]["status"] = "pending"
    errors = validator._validate_record(record, 1, None, True, reviewer_map, True)
    assert any("adjudicated record required" in error for error in errors)


def test_corpus_diff_gate_blocks_pending_and_accepts_adjudicated(tmp_path):
    record = _record()
    record["regions"][0]["annotator_refs"] = ["human-a", "human-b"]
    record["adjudication"]["annotators"] = ["human-a", "human-b"]
    record["adjudication"]["domain_reviewer"] = "domain-c"
    manifest_path = tmp_path / "manifest.jsonl"
    registry_path = tmp_path / "reviewers.json"
    registry_path.write_text(json.dumps(_reviewer_registry()), encoding="utf-8")
    command = [sys.executable, str(ROOT / "scripts/check_palm_corpus_diff.py"), "--manifest", str(manifest_path), "--reviewers", str(registry_path)]
    record["adjudication"]["status"] = "pending"
    manifest_path.write_text(json.dumps(record) + "\n", encoding="utf-8")
    blocked = subprocess.run(command, check=False, capture_output=True, text=True)
    assert blocked.returncode == 1
    assert "adjudicated record required" in blocked.stdout
    record["adjudication"]["status"] = "adjudicated"
    manifest_path.write_text(json.dumps(record) + "\n", encoding="utf-8")
    passed = subprocess.run(command, check=False, capture_output=True, text=True)
    assert passed.returncode == 0
    assert json.loads(passed.stdout)["status"] == "PASS"


def test_corpus_diff_gate_blocks_missing_base_ref(tmp_path):
    diff_gate = _load_script("check_palm_corpus_diff.py")
    current = _records_from_test_registry_record()
    assert current["record_id"] == "gold-001"
    manifest_path = tmp_path / "manifest.jsonl"
    registry_path = tmp_path / "reviewers.json"
    manifest_path.write_text(json.dumps(current) + "\n", encoding="utf-8")
    registry_path.write_text(json.dumps(_reviewer_registry()), encoding="utf-8")
    command = [sys.executable, str(ROOT / "scripts/check_palm_corpus_diff.py"), "--manifest", str(manifest_path), "--reviewers", str(registry_path), "--base-ref", "refs/heads/definitely-missing"]
    missing_ref = subprocess.run(command, check=False, capture_output=True, text=True)
    assert missing_ref.returncode == 1
    assert "base ref is unavailable" in missing_ref.stdout
    assert diff_gate._records_from_text(manifest_path.read_text(encoding="utf-8"))["gold-001"] == current


def _records_from_test_registry_record():
    record = _record()
    record["regions"][0]["annotator_refs"] = ["human-a", "human-b"]
    record["adjudication"]["annotators"] = ["human-a", "human-b"]
    record["adjudication"]["domain_reviewer"] = "domain-c"
    return record
