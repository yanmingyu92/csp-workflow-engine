"""Tests for the original-experiment full-response analysis."""

from pathlib import Path
import subprocess
import sys

from experiments.analyze_original_full_response import (
    classify_primary,
    task_means,
    validate_source,
)


def test_locked_decision_requires_positive_interval_and_exact_test():
    assert (
        classify_primary(
            {
                "mean_difference": 0.4,
                "ci_95": [0.1, 0.8],
                "p_exact_sign_flip": 0.02,
            }
        )
        == "retained_secondary_evidence"
    )
    assert (
        classify_primary(
            {
                "mean_difference": 0.4,
                "ci_95": [-0.1, 0.8],
                "p_exact_sign_flip": 0.02,
            }
        )
        == "directional_but_uncertain"
    )
    assert (
        classify_primary(
            {
                "mean_difference": -0.1,
                "ci_95": [-0.4, 0.2],
                "p_exact_sign_flip": 0.5,
            }
        )
        == "not_retained"
    )


def test_task_means_keeps_full_and_prefix_scores_separate():
    rows = [
        {
            "task_id": "task-1",
            "condition": "agent_only",
            "quality_score": 5,
            "prefix_judgment": {"quality_score": 3},
        },
        {
            "task_id": "task-1",
            "condition": "agent_only",
            "quality_score": 3,
            "prefix_judgment": {"quality_score": 1},
        },
    ]

    assert task_means(rows, "quality_score", "full") == {
        "agent_only": {"task-1": 4.0}
    }
    assert task_means(rows, "quality_score", "prefix") == {
        "agent_only": {"task-1": 2.0}
    }


def test_source_validation_rejects_incomplete_prefix_checkpoint():
    errors = validate_source(
        {
            "metadata": {"rejudge_complete": False},
            "results": [],
            "pairwise_results": [],
            "pairwise_presentations": [],
        }
    )

    assert any("not marked complete" in error for error in errors)
    assert any("not a full-response" in error for error in errors)


def test_direct_cli_entrypoint_can_import_experiments_package():
    script = (
        Path(__file__).parents[1]
        / "experiments"
        / "analyze_original_full_response.py"
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
