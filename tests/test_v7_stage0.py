from __future__ import annotations

from pathlib import Path

from experiments.v7_stage0 import (
    audit_v6_baseline,
    load_task_registry,
    rank_development_configs,
    retrieval_diagnostics,
)
from experiments.v7_routing import RoutingConfig, RoutingCorpus


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TASKS_PATH = (
    PROJECT_ROOT
    / "experiments"
    / "config"
    / "experiment_v7_routing_sensitive_tasks_20260725.yaml"
)


def test_task_registry_has_independent_24_task_holdout():
    registry = load_task_registry(TASKS_PATH)

    assert len(registry["development_tasks"]) == 10
    assert len(registry["smoke_tasks"]) == 1
    assert len(registry["heldout_tasks"]) == 24
    assert registry["holdout_isolation"]["passed"] is True


def test_retrieval_diagnostics_measure_primary_offline_properties(tmp_path: Path):
    skill_root = tmp_path / "csp-skills"
    skill_path = skill_root / "needed" / "SKILL.md"
    skill_path.parent.mkdir(parents=True)
    skill_path.write_text(
        "---\nname: needed\nversion: '1.0'\n---\n"
        "## Audited Derivation\nRare required edge evidence.\n",
        encoding="utf-8",
    )
    graph = tmp_path / "graph.yaml"
    graph.write_text(
        "schema_version: 1\nglobal_skills: []\nnodes:\n"
        "  - id: active\n    skills_bound: [/needed]\n"
        "    dependencies: []\n",
        encoding="utf-8",
    )
    config = RoutingConfig(
        context_budget=80,
        flat_budget=100,
        max_chunk_tokens=40,
        top_k=2,
    )
    corpus = RoutingCorpus.from_paths(skill_root, graph, config)
    tasks = [
        {
            "task_id": "dev-one",
            "node_id": "active",
            "prompt": "rare required edge evidence",
            "required_evidence": [
                {
                    "skill_name": "needed",
                    "heading_contains": "Audited Derivation",
                }
            ],
        }
    ]

    diagnostics = retrieval_diagnostics(corpus, tasks)

    assert diagnostics["aggregate"]["recall_at_k"] == 1.0
    assert diagnostics["aggregate"]["dependency_coverage"] == 1.0
    assert diagnostics["aggregate"]["provenance_completeness"] == 1.0
    assert diagnostics["aggregate"]["irrelevant_token_ratio"] == 0.0
    assert diagnostics["change_impact"]["passed"] is True


def test_development_config_ranking_is_score_free_and_deterministic():
    candidates = [
        {
            "config": {"top_k": 8},
            "aggregate": {
                "recall_at_k": 1.0,
                "dependency_coverage": 1.0,
                "provenance_completeness": 1.0,
                "precision_at_k": 0.4,
                "irrelevant_token_ratio": 0.6,
                "redundancy": 0.1,
                "mean_context_tokens": 1000,
            },
        },
        {
            "config": {"top_k": 16},
            "aggregate": {
                "recall_at_k": 0.9,
                "dependency_coverage": 1.0,
                "provenance_completeness": 1.0,
                "precision_at_k": 0.9,
                "irrelevant_token_ratio": 0.1,
                "redundancy": 0.0,
                "mean_context_tokens": 900,
            },
        },
    ]

    ranked = rank_development_configs(candidates)

    assert ranked[0]["config"]["top_k"] == 8
    assert "generation_score" not in ranked[0]
    assert "judge_score" not in ranked[0]


def test_v6_baseline_audit_locks_hash_shape_and_arms():
    audit = audit_v6_baseline(
        PROJECT_ROOT
        / "experiments"
        / "results"
        / "experiment_v6_aps_gxp_formal_20260724_judged.json"
    )

    assert audit["sha256"] == (
        "fb9f787a6e95e2bd0813c7f7b90fd986e64adeba09305645572a3875df927aa0"
    )
    assert audit["row_count"] == 120
    assert audit["task_count"] == 10
    assert audit["runs_per_cell"] == 3
    assert set(audit["arm_means"]) == {
        "aps_gxp_optimized",
        "aps_v5_frozen",
        "flat_8000",
        "random_token_matched",
    }
