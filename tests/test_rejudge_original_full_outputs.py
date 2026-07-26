"""Regression tests for the original-experiment full-response re-judgment."""

import hashlib
from pathlib import Path
import subprocess
import sys

from experiments.rejudge_original_full_outputs import (
    ORIGINAL_CONDITIONS,
    ORIGINAL_PAIRWISE_CONTRASTS,
    build_pairwise_jobs,
    initialize_checkpoint,
    normalize_original_source,
    validate_rejudged_checkpoint,
    validate_original_source,
)


def _source():
    rows = []
    for run_id in range(3):
        for condition in ORIGINAL_CONDITIONS:
            rows.append(
                {
                    "task_id": "task-01-sap-parse",
                    "run_id": run_id,
                    "condition": condition,
                    "graph_node": "sap-parse",
                    "response": f"{condition} full response {run_id}",
                    "quality_score": 4.0,
                    "dim_completeness": 4,
                    "dim_terminology": 4,
                    "dim_structure": 4,
                    "dim_reasoning": "prefix judgment",
                    "is_error_response": False,
                }
            )
    return {
        "metadata": {
            "version": "v4-claude-3tier",
            "dry_run": False,
            "judge": "deepseek-chat",
            "seed": 42,
        },
        "results": rows,
        "pairwise_results": [],
    }


def test_normalization_adds_stable_keys_and_design_metadata():
    normalized = normalize_original_source(_source())

    assert normalized["metadata"]["tasks"] == ["task-01-sap-parse"]
    assert normalized["metadata"]["conditions"] == list(ORIGINAL_CONDITIONS)
    assert normalized["metadata"]["runs"] == 3
    assert len({row["run_key"] for row in normalized["results"]}) == 9


def test_source_validation_rejects_missing_matched_cells():
    source = _source()
    source["results"].pop()

    errors = validate_original_source(normalize_original_source(source))

    assert any("cardinality" in error or "matched" in error for error in errors)


def test_pairwise_jobs_are_replicate_matched_and_bidirectional():
    normalized = normalize_original_source(_source())

    jobs = build_pairwise_jobs(normalized["results"])

    expected_logical = 3 * len(ORIGINAL_PAIRWISE_CONTRASTS)
    assert len(jobs) == expected_logical * 2
    assert {job["orientation"] for job in jobs} == {"ab", "ba"}
    assert len({job["logical_pair_key"] for job in jobs}) == expected_logical
    assert all("full response" in job["response_a"] for job in jobs)


def test_initialize_checkpoint_preserves_prefix_judge_model():
    normalized = normalize_original_source(_source())
    source_path = Path(__file__)
    protocol = {
        "protocol_sha256": "locked",
        "source_checkpoint_sha256": "source",
    }

    checkpoint = initialize_checkpoint(normalized, source_path, protocol)

    assert all(
        row["prefix_judgment"]["judge_model_requested"] == "deepseek-chat"
        for row in checkpoint["results"]
    )


def test_partial_checkpoint_reports_incompleteness_without_false_hash_failures():
    normalized = normalize_original_source(_source())
    source_path = Path(__file__)
    protocol = {
        "protocol_sha256": "locked",
        "source_checkpoint_sha256": hashlib.sha256(
            source_path.read_bytes()
        ).hexdigest(),
        "domain_criteria_by_node": {"sap-parse": "criteria"},
    }
    checkpoint = initialize_checkpoint(normalized, source_path, protocol)

    errors = validate_rejudged_checkpoint(checkpoint, normalized, protocol)

    assert any("incomplete" in error for error in errors)
    assert not any("hash mismatch" in error for error in errors)
    assert not any("source-derived" in error for error in errors)


def test_direct_cli_entrypoint_can_import_experiments_package():
    script = (
        Path(__file__).parents[1]
        / "experiments"
        / "rejudge_original_full_outputs.py"
    )
    completed = subprocess.run(
        [sys.executable, str(script), "--help"],
        cwd=Path(__file__).parents[1],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
