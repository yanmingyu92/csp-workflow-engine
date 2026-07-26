"""Tests for the independent V7 oracle verifier."""

from __future__ import annotations

from pathlib import Path

from experiments.v7_oracle_decomposition import write_analysis
from experiments.verify_v7_oracle_decomposition import (
    verify_analysis_directory,
    verify_payload,
)


ROOT = Path(__file__).resolve().parents[1]


def _valid_payload() -> dict[str, object]:
    cells = []
    for task_index in range(24):
        for arm in (
            "graph_bm25_chunk_optimized",
            "full_corpus_bm25_token_matched",
            "random_token_matched",
            "flat_8000",
        ):
            for run_id in range(3):
                cells.append(
                    {
                        "task_id": f"task-{task_index:02d}",
                        "arm": arm,
                        "run_id": run_id,
                        "metrics": {
                            "required_section_recall": 1.0,
                            "required_section_precision": 0.5,
                            "required_token_precision": 0.5,
                            "dependency_coverage": 1.0,
                            "topology_alignment": 1.0,
                            "irrelevant_token_ratio": 0.5,
                            "redundancy": 0.1,
                            "version_selection_correctness": 1.0,
                            "version_conflict_output_correctness": 1.0,
                            "provenance_completeness": 1.0,
                            "correct_citation_rate": 1.0,
                        },
                    }
                )
    return {
        "schema_version": "v7-oracle-decomposition-1",
        "claim_boundaries": {
            "graph_superiority_established": False,
            "cross_version_means_compared": False,
            "operational_gxp_compliance_claimed": False,
            "paid_generation_started": False,
        },
        "input_hashes": {
            "v6_judged_baseline": {
                "path": (
                    "experiments/results/"
                    "experiment_v6_aps_gxp_formal_20260724_judged.json"
                ),
                "sha256": (
                    "fb9f787a6e95e2bd0813c7f7b90fd986e64adeba09305645572a"
                    "3875df927aa0"
                ),
            }
        },
        "freeze_contract_audit": {
            "mismatch_count": 0,
            "frozen_source_count": 8,
            "verified_source_count": 8,
            "frozen_corpus_file_count": 59,
            "verified_corpus_file_count": 59,
        },
        "generation_evaluation_linkage_audit": {
            "generation_record_count": 288,
            "evaluation_record_count": 288,
            "linked_record_count": 288,
            "mismatch_count": 0,
        },
        "future_experiment_go_no_go": {
            "decision": "no_go_for_immediate_paid_generation",
            "conditional_protocol": {
                "automatic_start_authorized": False,
            },
        },
        "cells": cells,
        "error_taxonomy": {
            "classes": [
                "retrieval_miss",
                "wrong_or_stale_evidence",
                "evidence_present_generator_omission",
                "derivation_error",
                "schema_or_serialization_error",
                "forbidden_hallucination",
                "citation_mismatch",
                "judge_only_disagreement",
                "unresolved_insufficient_artifact_evidence",
            ]
        },
    }


def test_verifier_accepts_complete_panel_contract() -> None:
    errors = verify_payload(
        _valid_payload(),
        root=Path("C:/nonexistent-read-only-fixture-root"),
        verify_files=False,
    )

    assert errors == []


def test_verifier_rejects_missing_cell_invalid_metric_and_claim_upgrade() -> None:
    payload = _valid_payload()
    payload["cells"] = list(payload["cells"])[:-1]
    payload["cells"][0]["metrics"]["required_section_recall"] = 1.5
    payload["claim_boundaries"]["graph_superiority_established"] = True

    errors = verify_payload(
        payload,
        root=Path("C:/nonexistent-read-only-fixture-root"),
        verify_files=False,
    )

    assert any("expected 288 cells" in error for error in errors)
    assert any("outside [0, 1]" in error for error in errors)
    assert any("graph superiority" in error for error in errors)


def test_verifier_rejects_v6_hash_mismatch() -> None:
    payload = _valid_payload()
    payload["input_hashes"]["v6_judged_baseline"]["sha256"] = "0" * 64

    errors = verify_payload(
        payload,
        root=Path("C:/nonexistent-read-only-fixture-root"),
        verify_files=False,
    )

    assert any("V6 judged baseline hash" in error for error in errors)


def test_verifier_rejects_corrupted_shape_and_audit_contracts() -> None:
    payload = _valid_payload()
    payload["schema_version"] = "wrong"
    payload["cells"][0]["task_id"] = "unexpected-task"
    payload["cells"][0]["arm"] = "unexpected-arm"
    payload["cells"][0]["run_id"] = 9
    payload["cells"][0]["metrics"]["redundancy"] = None
    payload["cells"][1] = dict(payload["cells"][0])
    payload["error_taxonomy"]["classes"] = []
    payload["failure_summary"] = {"error_count": 1}
    payload["freeze_contract_audit"] = {
        "mismatch_count": 1,
        "frozen_source_count": 8,
        "verified_source_count": 7,
        "frozen_corpus_file_count": 59,
        "verified_corpus_file_count": 58,
    }
    payload["generation_evaluation_linkage_audit"] = {
        "generation_record_count": 287,
        "evaluation_record_count": 287,
        "linked_record_count": 286,
        "mismatch_count": 1,
    }
    payload["future_experiment_go_no_go"] = {
        "decision": "go",
        "conditional_protocol": {"automatic_start_authorized": True},
    }

    errors = verify_payload(
        payload,
        root=Path("C:/nonexistent-read-only-fixture-root"),
        verify_files=False,
    )

    assert any("schema version" in error for error in errors)
    assert any("duplicate" in error for error in errors)
    assert any("unexpected arm" in error for error in errors)
    assert any("unexpected run" in error for error in errors)
    assert any("missing numeric metric" in error for error in errors)
    assert any("taxonomy" in error for error in errors)
    assert any("freeze contract" in error for error in errors)
    assert any("generation/evaluation linkage" in error for error in errors)
    assert any("go/no-go" in error for error in errors)


def test_verifier_checks_missing_and_changed_input_hashes(
    tmp_path: Path,
) -> None:
    payload = _valid_payload()

    missing_errors = verify_payload(
        payload,
        root=tmp_path,
        verify_files=True,
    )
    assert any("missing hashed input" in error for error in missing_errors)

    relative = Path(payload["input_hashes"]["v6_judged_baseline"]["path"])
    path = tmp_path / relative
    path.parent.mkdir(parents=True)
    path.write_bytes(b"not the frozen baseline")
    changed_errors = verify_payload(
        payload,
        root=tmp_path,
        verify_files=True,
    )
    assert any("input hash mismatch" in error for error in changed_errors)


def test_directory_verifier_rejects_invalid_json_and_missing_phrases(
    tmp_path: Path,
) -> None:
    for filename in (
        "stats-appendix.md",
        "figure-catalog.md",
        "failure_log.json",
        "input_hashes.json",
    ):
        (tmp_path / filename).write_text("placeholder\n", encoding="utf-8")
    (tmp_path / "oracle_decomposition.json").write_text(
        "{invalid",
        encoding="utf-8",
    )
    (tmp_path / "analysis-report.md").write_text(
        "No boundaries.",
        encoding="utf-8",
    )
    (tmp_path / "regulatory-alignment-matrix.md").write_text(
        "No classifications.",
        encoding="utf-8",
    )

    result = verify_analysis_directory(root=ROOT, analysis_dir=tmp_path)

    assert result["passed"] is False
    assert any("JSON is invalid" in error for error in result["errors"])
    assert any("boundary phrase" in error for error in result["errors"])
    assert any("matrix lacks distinction" in error for error in result["errors"])


def test_full_frozen_panel_writes_and_independently_verifies(
    tmp_path: Path,
) -> None:
    payload = write_analysis(root=ROOT, output_dir=tmp_path)
    result = verify_analysis_directory(root=ROOT, analysis_dir=tmp_path)

    assert payload["panel"] == {
        "task_count": 24,
        "arm_count": 4,
        "repetitions_per_task_arm": 3,
        "cell_count": 288,
        "criterion_record_count": 1236,
    }
    assert payload["failure_summary"]["error_count"] == 0
    assert payload["freeze_contract_audit"]["mismatch_count"] == 0
    assert (
        payload["freeze_contract_audit"]["verified_corpus_file_count"]
        == payload["freeze_contract_audit"]["frozen_corpus_file_count"]
    )
    assert payload["generation_evaluation_linkage_audit"] == {
        "generation_record_count": 288,
        "evaluation_record_count": 288,
        "linked_record_count": 288,
        "mismatch_count": 0,
    }
    assert result["passed"] is True
    assert result["errors"] == []
