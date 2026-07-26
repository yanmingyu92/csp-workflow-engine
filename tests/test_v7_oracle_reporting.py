"""Tests for deterministic V7 oracle reporting."""

from __future__ import annotations

from pathlib import Path

from experiments.v7_oracle_reporting import write_reports


def _payload() -> dict[str, object]:
    graph = "graph_bm25_chunk_optimized"
    bm25 = "full_corpus_bm25_token_matched"
    error_classes = [
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
    return {
        "analysis_date": "2026-07-25",
        "panel": {
            "task_count": 24,
            "arm_count": 4,
            "repetitions_per_task_arm": 3,
            "cell_count": 288,
            "criterion_record_count": 1236,
        },
        "arm_aggregates": {
            graph: {
                "deterministic_score_mean": 0.59,
                "required_section_recall": 0.95,
                "required_section_precision": 0.22,
                "required_token_precision": 0.25,
                "irrelevant_token_ratio": 0.75,
                "redundancy": 0.12,
                "correct_citation_rate": 0.94,
            },
            bm25: {
                "deterministic_score_mean": 0.58,
                "required_section_recall": 0.95,
                "required_section_precision": 0.23,
                "required_token_precision": 0.26,
                "irrelevant_token_ratio": 0.74,
                "redundancy": 0.11,
                "correct_citation_rate": 0.92,
            },
        },
        "task_arm_means": [
            {
                "task_id": "task-1",
                "arm": graph,
                "required_section_recall": 1.0,
                "required_token_precision": 0.25,
                "deterministic_score": 0.6,
            },
            {
                "task_id": "task-1",
                "arm": bm25,
                "required_section_recall": 1.0,
                "required_token_precision": 0.26,
                "deterministic_score": 0.5,
            },
        ],
        "graph_vs_bm25_oracle_delta": {
            "uncertainty": {
                "required_section_recall_delta": {
                    "mean": 0.0,
                    "bootstrap_95_ci": [0.0, 0.0],
                    "loo": {
                        "minimum": 0.0,
                        "maximum": 0.0,
                        "sign_changes": 0,
                    },
                },
                "required_token_precision_delta": {
                    "mean": -0.01,
                    "bootstrap_95_ci": [-0.02, 0.0],
                    "loo": {
                        "minimum": -0.01,
                        "maximum": -0.01,
                        "sign_changes": 0,
                    },
                },
                "deterministic_score_delta": {
                    "mean": 0.01,
                    "bootstrap_95_ci": [-0.03, 0.05],
                    "loo": {
                        "minimum": -0.001,
                        "maximum": 0.02,
                        "sign_changes": 1,
                    },
                },
            },
            "task_level": [
                {
                    "task_id": "task-1",
                    "required_section_recall_delta": 0.0,
                    "required_token_precision_delta": -0.01,
                    "deterministic_score_delta": 0.1,
                }
            ],
            "conditional_evidence_output_table": {
                "evidence_unchanged__output_improved": 1
            },
            "edge_route_associations": {},
        },
        "error_taxonomy": {
            "classes": error_classes,
            "arm_error_counts": {
                graph: {name: 1 for name in error_classes},
                bm25: {name: 2 for name in error_classes},
            },
        },
        "graph_design_audit": {
            "diagnosis": {
                "bm25_retrieval_ceiling_supported": True,
                "graph_semantic_mismatch_supported": True,
                "graph_context_dilution_supported": True,
                "downstream_generation_or_validation_bottleneck_supported": True,
            },
            "future_proposals_not_evaluated": ["typed-edge RWR/PPR"],
        },
        "strata": {},
        "requirement_mapping": {
            "limitation": "Task-level evidence union maps to each criterion."
        },
    }


def test_reports_include_boundaries_matrix_and_deterministic_svgs(
    tmp_path: Path,
) -> None:
    payload = _payload()
    write_reports(payload=payload, output_dir=tmp_path)
    first = {
        path.relative_to(tmp_path).as_posix(): path.read_bytes()
        for path in sorted(tmp_path.rglob("*"))
        if path.is_file()
    }
    write_reports(payload=payload, output_dir=tmp_path)
    second = {
        path.relative_to(tmp_path).as_posix(): path.read_bytes()
        for path in sorted(tmp_path.rglob("*"))
        if path.is_file()
    }

    assert first == second
    assert {
        "analysis-report.md",
        "stats-appendix.md",
        "figure-catalog.md",
        "regulatory-alignment-matrix.md",
        "figures/figure-01-oracle-retrieval.svg",
        "figures/figure-02-error-decomposition.svg",
        "figures/figure-03-evidence-output-delta.svg",
    } <= set(first)
    report = first["analysis-report.md"].decode("utf-8").lower()
    assert "does not establish graph superiority" in report
    assert "not an operational gxp compliance" in report
    assert "human-overseen" in report
    assert "no cross-version mean comparison" in report
    matrix = first["regulatory-alignment-matrix.md"].decode("utf-8").lower()
    for phrase in (
        "architecture property",
        "benchmark proxy",
        "validated operational control",
        "formal compliance",
        "remaining human responsibility",
    ):
        assert phrase in matrix
