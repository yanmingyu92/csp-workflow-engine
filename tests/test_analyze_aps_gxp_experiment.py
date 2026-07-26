"""Task-paired statistics and governance tests for APS-GxP v6."""

from __future__ import annotations

import pytest

from experiments.analyze_aps_gxp_experiment import (
    CONFIRMATORY_CONTRASTS,
    aggregate_task_means,
    analyze_experiment,
    analyze_quality,
    build_analysis_bundle_files,
    classify_formal_outcome,
    exact_sign_flip_p,
    holm_adjust,
    leave_one_task_out_range,
    summarize_governance_metrics,
    validate_complete_response_judgments,
)
from experiments.run_experiment_v6_aps_gxp import (
    build_complete_response_judge_prompt,
)
from experiments import run_experiment_v4_claude as v4
from experiments.aps_gxp_context import (
    canonical_manifest_sha256,
    sha256_text,
)


def _synthetic_rows() -> list[dict]:
    rows = []
    offsets = {
        "aps_v5_frozen": 0.0,
        "aps_gxp_optimized": 0.5,
        "flat_8000": 0.2,
        "random_token_matched": 0.1,
    }
    for task_index in range(10):
        for arm, offset in offsets.items():
            for run_id in range(3):
                rows.append(
                    {
                        "task_id": f"task-{task_index:02d}",
                        "arm": arm,
                        "run_id": run_id,
                        "quality_score": 3.0 + task_index / 20 + offset,
                        "is_error_response": False,
                    }
                )
    return rows


def test_confirmatory_family_is_locked():
    assert CONFIRMATORY_CONTRASTS == (
        ("aps_gxp_optimized", "aps_v5_frozen"),
        ("aps_gxp_optimized", "flat_8000"),
        ("aps_gxp_optimized", "random_token_matched"),
    )


def test_replicates_are_aggregated_within_task_before_inference():
    means = aggregate_task_means(_synthetic_rows(), "quality_score")

    assert len(means["aps_gxp_optimized"]) == 10
    assert means["aps_gxp_optimized"]["task-00"] == pytest.approx(3.5)


def test_quality_analysis_reports_all_prespecified_task_level_statistics():
    report = analyze_quality(_synthetic_rows(), seed=42)

    assert set(report["confirmatory"]) == {
        "aps_gxp_optimized_minus_aps_v5_frozen",
        "aps_gxp_optimized_minus_flat_8000",
        "aps_gxp_optimized_minus_random_token_matched",
    }
    for result in report["confirmatory"].values():
        assert result["n_tasks"] == 10
        assert result["ci_95"][0] <= result["mean_difference"] <= result["ci_95"][1]
        assert 0 <= result["p_exact_sign_flip"] <= 1
        assert 0 <= result["p_holm"] <= 1
        assert set(result["task_signs"]) == {"positive", "negative", "tied"}
        assert result["leave_one_task_out_range"][0] <= (
            result["mean_difference"]
        ) <= result["leave_one_task_out_range"][1]
        assert "paired_dz" in result


def test_exact_two_sided_sign_flip_and_holm_are_deterministic():
    assert exact_sign_flip_p([1.0] * 4) == pytest.approx(0.125)
    assert holm_adjust({"a": 0.01, "b": 0.04, "c": 0.03}) == pytest.approx(
        {"a": 0.03, "b": 0.06, "c": 0.06}
    )


def test_leave_one_task_out_range_uses_task_differences():
    low, high = leave_one_task_out_range([0.0, 1.0, 2.0])
    assert low == pytest.approx(0.5)
    assert high == pytest.approx(1.5)


def test_locked_outcome_classifier_distinguishes_a_b_and_c():
    quality = analyze_quality(_synthetic_rows(), seed=42)
    efficiency = {
        "optimized_vs_flat_mean_token_reduction_percent": 16.0,
        "prespecified_15_percent_reduction_met": True,
    }
    governance = {
        "provenance_completeness_percent": 100.0,
        "manifest_reproducibility_percent": 100.0,
        "change_impact": {
            "paired_optimized_minus_flat": {"mean_difference": -2.0}
        },
    }

    outcome_a = classify_formal_outcome(
        quality, efficiency, governance, integrity_pass=True
    )
    assert outcome_a["outcome"] == "A"
    assert outcome_a["gates"]["superiority_vs_nonrouted_control"]["pass"]

    for contrast in quality["confirmatory"].values():
        contrast["p_holm"] = 1.0
    outcome_b = classify_formal_outcome(
        quality, efficiency, governance, integrity_pass=True
    )
    assert outcome_b["outcome"] == "B"
    assert outcome_b["gates"]["quality_retention"]["pass"]

    quality["confirmatory"][
        "aps_gxp_optimized_minus_flat_8000"
    ]["ci_95"][0] = -0.21
    outcome_c = classify_formal_outcome(
        quality, efficiency, governance, integrity_pass=True
    )
    assert outcome_c["outcome"] == "C"


def test_strict_analysis_bundle_contains_real_vector_figures():
    quality = analyze_quality(_synthetic_rows(), seed=42)
    report = {
        "source_sha256": "1" * 64,
        "dry_run": False,
        "quality": quality,
        "efficiency": {
            "task_level_arm_tokens": {
                arm: {
                    f"task-{index:02d}": 6000.0 + index * 10
                    for index in range(10)
                }
                for arm in quality["task_means"]
            },
            "arm_summary": {
                arm: {
                    "n_tasks": 10,
                    "mean": 6045.0,
                    "sd_across_tasks": 30.28,
                }
                for arm in quality["task_means"]
            },
            "optimized_vs_flat_mean_token_reduction_percent": 16.0,
            "prespecified_15_percent_reduction_met": True,
        },
        "governance": {
            "provenance_completeness_percent": 100.0,
            "manifest_reproducibility_percent": 100.0,
            "context_scope": {},
            "change_impact": {
                "paired_optimized_minus_flat": {"mean_difference": -2.0}
            },
        },
        "complete_response_judging": {
            "pass": True,
            "policy": "full_stored_response_no_character_truncation",
            "errors": [],
        },
        "outcome_decision": {"outcome": "A", "label": "advantage"},
    }

    files = build_analysis_bundle_files(report)

    assert {
        "analysis-report.md",
        "statistical-appendix.md",
        "figure-catalog.md",
        "figures/task-level-quality.svg",
        "figures/context-efficiency.svg",
    } <= set(files)
    assert "<svg" in files["figures/task-level-quality.svg"]
    assert "Purpose" in files["figure-catalog.md"]
    assert "SD across tasks" in files["figure-catalog.md"]


def test_governance_metrics_remain_separate_without_composite_score():
    contexts = [
        {
            "task_id": "task-a",
            "arm": "aps_gxp_optimized",
            "manifest_sha256": "1" * 64,
            "repeated_manifest_sha256": ["1" * 64] * 3,
            "provenance_complete": True,
            "scope": {
                "current": {"skills": 1, "tokens": 100},
                "relevance_qualified_adjacent": {"skills": 2, "tokens": 200},
                "global": {"skills": 0, "tokens": 0},
                "out_of_scope": {"skills": 0, "tokens": 0},
            },
        }
    ]

    summary = summarize_governance_metrics(contexts)

    assert summary["provenance_completeness_percent"] == pytest.approx(100.0)
    assert summary["manifest_reproducibility_percent"] == pytest.approx(100.0)
    assert "context_scope" in summary
    assert "composite_gxp_score" not in summary


def _complete_judged_row() -> dict:
    task_id = "task-20-tfl-ae"
    response = "A complete response with a unique tail."
    criteria = "criteria"
    prompt = build_complete_response_judge_prompt(
        task_id, response, criteria
    )
    scores = {
        "completeness": 4.0,
        "terminology": 3.0,
        "structure": 5.0,
    }
    return {
        "run_key": f"{task_id}::aps_gxp_optimized::0",
        "task_id": task_id,
        "arm": "aps_gxp_optimized",
        "run_id": 0,
        "response": response,
        "response_sha256": sha256_text(response),
        "judge_domain_criteria": criteria,
        "judge_domain_criteria_sha256": sha256_text(criteria),
        "dim_completeness": 4.0,
        "dim_terminology": 3.0,
        "dim_structure": 5.0,
        "quality_score": 4.0,
        "scalar_judgment": {
            "policy": "full_stored_response_no_character_truncation",
            "truncated": False,
            "response_characters_judged": len(response),
            "response_bytes_judged": len(response.encode("utf-8")),
            "response_sha256": sha256_text(response),
            "rendered_prompt_characters": len(prompt),
            "rendered_prompt_bytes": len(prompt.encode("utf-8")),
            "rendered_prompt_sha256": sha256_text(prompt),
            "scores": scores,
            "judge_model_requested": "judge",
            "judge_model_returned": "judge-returned",
            "judge_response_id": "response-id",
            "system_fingerprint": None,
            "system_fingerprint_capture": "provider_returned_null",
            "judge_input_tokens": 10,
            "judge_output_tokens": 5,
            "finish_reason": "stop",
            "judge_parse_error": None,
        },
    }


def test_complete_response_validation_reconstructs_prompt_and_lengths():
    row = _complete_judged_row()
    assert validate_complete_response_judgments([row]) == []

    row["scalar_judgment"]["rendered_prompt_sha256"] = "0" * 64
    row["scalar_judgment"]["rendered_prompt_characters"] -= 1
    row["scalar_judgment"]["response_bytes_judged"] -= 1

    errors = validate_complete_response_judgments([row])

    assert any("rendered prompt hash" in error for error in errors)
    assert any("rendered prompt length" in error for error in errors)
    assert any("judged response byte" in error for error in errors)


def test_complete_response_validation_rejects_redundant_score_conflicts():
    row = _complete_judged_row()
    row["quality_score"] = 1.0

    errors = validate_complete_response_judgments([row])

    assert any("quality_score" in error for error in errors)


def test_analysis_suppresses_inference_when_judgment_panel_is_incomplete():
    row = _complete_judged_row()
    data = {
        "metadata": {
            "seed": 42,
            "tasks": list(v4.QUICK_10_TASKS),
            "arms": [
                "aps_v5_frozen",
                "aps_gxp_optimized",
                "flat_8000",
                "random_token_matched",
            ],
            "runs": 3,
        },
        "results": [row],
    }

    report = analyze_experiment(data, source_sha256="1" * 64)

    assert report["complete_response_judging"]["pass"] is False
    assert report["quality"] is None
    assert report["dimension_sensitivity"] is None


def test_analysis_fails_closed_when_valid_panel_keys_are_cross_linked():
    task_id = "task-20-tfl-ae"
    arms = [
        "aps_v5_frozen",
        "aps_gxp_optimized",
        "flat_8000",
        "random_token_matched",
    ]
    rows = []
    for arm in arms:
        row = _complete_judged_row()
        manifest = {
            "schema_version": "aps-gxp-v6-context-manifest-1",
            "task_id": task_id,
            "arm": arm,
            "run_id": 0,
            "seed": 42,
            "budget": 8000,
            "budget_used": 0,
            "scheduler_sha256": "1" * 64,
            "graph_sha256": "2" * 64,
            "task_sha256": sha256_text(v4.TASK_PROMPTS[task_id]),
            "prompt_context_sha256": "3" * 64,
            "candidates": [],
        }
        if arm == "aps_gxp_optimized":
            manifest.update(
                {
                    "context_budget_policy": (
                        "optimized_84_percent_soft_cap_with_full_current_override"
                    ),
                    "optimized_soft_cap_tokens": 6720,
                    "effective_context_cap_tokens": 6720,
                }
            )
        manifest["manifest_sha256"] = canonical_manifest_sha256(manifest)
        row.update(
            {
                "run_key": f"{task_id}::{arm}::0",
                "arm": arm,
                "graph_node": v4.TASK_NODES[task_id][0],
                "skills_tokens": 0,
                "budget_used": 0,
                "manifest": manifest,
                "manifest_sha256": manifest["manifest_sha256"],
                "repeated_manifest_sha256": [
                    manifest["manifest_sha256"]
                ]
                * 3,
                "agent_model_requested": "glm-5",
                "agent_model_returned": "glm-5-returned",
                "is_error_response": False,
            }
        )
        rows.append(row)
    data = {
        "metadata": {
            "seed": 42,
            "budget": 8000,
            "tasks": [task_id],
            "arms": arms,
            "runs": 1,
            "agent_model_requested": "glm-5",
            "judge_model_requested": "judge",
        },
        "results": rows,
    }
    assert analyze_experiment(data, "1" * 64)[
        "complete_response_judging"
    ]["pass"]

    tampered = {
        **data,
        "results": [dict(row) for row in rows],
    }
    tampered["results"][0]["arm"], tampered["results"][1]["arm"] = (
        tampered["results"][1]["arm"],
        tampered["results"][0]["arm"],
    )

    report = analyze_experiment(tampered, "1" * 64)

    assert report["complete_response_judging"]["pass"] is False
    assert report["quality"] is None
    assert any(
        "row identity" in error
        for error in report["complete_response_judging"]["errors"]
    )
