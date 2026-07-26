from __future__ import annotations

from experiments.analyze_experiment_v7 import (
    bootstrap_paired_difference,
    decision_from_primary_contrasts,
    exact_sign_flip_p,
    holm_adjust,
    provenance_completeness_audit,
    task_level_arm_scores,
)


def test_exact_sign_flip_p_uses_task_as_independent_unit():
    assert exact_sign_flip_p([1.0, 1.0, 1.0]) == 0.25
    assert exact_sign_flip_p([0.0, 0.0]) == 1.0


def test_holm_adjustment_is_monotone_in_original_order():
    adjusted = holm_adjust([0.01, 0.04])

    assert adjusted == [0.02, 0.04]


def test_task_level_scores_average_replicates_before_inference():
    rows = [
        {
            "task_id": "t1",
            "arm": "optimized",
            "deterministic_evaluation": {"score": 1.0},
        },
        {
            "task_id": "t1",
            "arm": "optimized",
            "deterministic_evaluation": {"score": 0.5},
        },
        {
            "task_id": "t2",
            "arm": "optimized",
            "deterministic_evaluation": {"score": 0.25},
        },
    ]

    scores = task_level_arm_scores(rows, value_path="deterministic_evaluation.score")

    assert scores["optimized"]["t1"] == 0.75
    assert scores["optimized"]["t2"] == 0.25


def test_bootstrap_is_deterministic_and_paired():
    first = bootstrap_paired_difference(
        [0.1, 0.2, -0.1, 0.3], seed=20260725, samples=2000
    )
    second = bootstrap_paired_difference(
        [0.1, 0.2, -0.1, 0.3], seed=20260725, samples=2000
    )

    assert first == second
    assert first["samples"] == 2000
    assert first["ci_low"] <= first["mean"] <= first["ci_high"]


def test_superiority_requires_both_positive_holm_significant_contrasts():
    passed = decision_from_primary_contrasts(
        [
            {"mean_difference": 0.1, "holm_p": 0.02},
            {"mean_difference": 0.2, "holm_p": 0.04},
        ]
    )
    failed = decision_from_primary_contrasts(
        [
            {"mean_difference": 0.1, "holm_p": 0.02},
            {"mean_difference": 0.2, "holm_p": 0.08},
        ]
    )

    assert passed["routing_superiority_supported"] is True
    assert failed["routing_superiority_supported"] is False
    assert failed["allowed_claim"] == "null_or_efficiency_governance_only"


def test_provenance_audit_fails_when_any_required_citation_is_incorrect():
    partial = provenance_completeness_audit(
        [{"passed": True}, {"passed": False}],
        manifest_schema_passed=True,
    )
    complete = provenance_completeness_audit(
        [{"passed": True}, {"passed": True}],
        manifest_schema_passed=True,
    )

    assert partial["criterion_pass_rate"] == 0.5
    assert partial["passed"] is False
    assert complete["passed"] is True
