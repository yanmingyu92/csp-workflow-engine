"""Tests for the offline V7 oracle decomposition.

These tests intentionally precede the implementation.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from experiments.v7_oracle_decomposition import (
    ERROR_CLASSES,
    _domain_from_node_id,
    build_error_decomposition,
    canonical_json_bytes,
    compare_graph_to_bm25,
    compute_cell_metrics,
    extract_task_requirements,
    requirement_matches_chunk,
)


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = (
    ROOT
    / "experiments"
    / "config"
    / "experiment_v7_routing_sensitive_tasks_20260725.yaml"
)
EVALUATED = (
    ROOT
    / "experiments"
    / "results"
    / "experiment_v7_routing_sensitive_formal_evaluated_20260725.json"
)
V6_JUDGED = (
    ROOT
    / "experiments"
    / "results"
    / "experiment_v6_aps_gxp_formal_20260724_judged.json"
)


def _chunk(
    chunk_id: str,
    skill: str,
    heading: str,
    tokens: int,
    *,
    hops: int | None = None,
    reason: str = "full_corpus_bm25_mmr",
) -> dict[str, object]:
    return {
        "rank": 1,
        "chunk_id": chunk_id,
        "skill_name": skill,
        "source_path": f"csp-skills/{skill}/SKILL.md",
        "source_sha256": "1" * 64,
        "declared_version": "1.0",
        "heading_path": heading,
        "section_kind": "derivation",
        "content_sha256": "2" * 64,
        "injected_fragment_sha256": "3" * 64,
        "injected_canonical_tokens_with_header": tokens,
        "lexical_relevance_score": 1.0,
        "section_priority_score": 2.4,
        "dependency_hops": hops,
        "graph_dependency_score": 0.0 if hops is None else 1.0,
        "final_score": 3.4,
        "selection_reason": reason,
        "truncated": False,
    }


def test_extract_task_requirements_maps_all_atomic_criteria() -> None:
    task = {
        "task_id": "task-1",
        "criteria": [
            {
                "id": "value",
                "type": "json_exact",
                "path": "answer.value",
                "expected": "x",
            },
            {
                "id": "provenance",
                "type": "provenance_citation",
                "required": [
                    {
                        "skill_name": "skill-a",
                        "heading_contains": "Audited Derivation",
                    }
                ],
            },
        ],
    }

    mapped = extract_task_requirements(task)

    assert mapped["task_requirements"] == [
        {
            "skill_name": "skill-a",
            "heading_contains": "Audited Derivation",
        }
    ]
    assert mapped["criteria"]["value"] == mapped["task_requirements"]
    assert mapped["criteria"]["provenance"] == mapped["task_requirements"]
    assert mapped["mapping_basis"] == "registry_provenance_requirement_union"


def test_requirement_matching_is_case_insensitive_and_section_specific() -> None:
    requirement = {
        "skill_name": "skill-a",
        "heading_contains": "Audited Derivation",
    }

    assert requirement_matches_chunk(
        requirement,
        _chunk("a", "skill-a", "Rules > audited derivation", 100),
    )
    assert not requirement_matches_chunk(
        requirement,
        _chunk("b", "skill-a", "Overview", 100),
    )
    assert not requirement_matches_chunk(
        requirement,
        _chunk("c", "skill-b", "Audited Derivation", 100),
    )


def test_compute_cell_metrics_separates_recall_precision_and_token_dilution() -> None:
    requirements = [
        {"skill_name": "skill-a", "heading_contains": "Audited Derivation"},
        {"skill_name": "skill-b", "heading_contains": "Audited Validation"},
    ]
    selected = [
        _chunk("required-a", "skill-a", "Audited Derivation", 100, hops=0),
        _chunk("irrelevant-1", "skill-c", "Overview", 150, hops=1),
        _chunk("irrelevant-2", "skill-d", "Edge Cases", 100, hops=2),
    ]
    manifest = {
        "selected_chunks": selected,
        "version_conflicts": [],
        "budget_padding_canonical_tokens": 0,
    }
    content = {
        "required-a": "alpha beta gamma",
        "irrelevant-1": "alpha beta delta",
        "irrelevant-2": "unrelated content",
    }

    metrics = compute_cell_metrics(
        requirements=requirements,
        manifest=manifest,
        chunk_content=content,
        dependency_reachable_skills={"skill-a": 0, "skill-c": 1, "skill-d": 2},
        response_evidence_ids=["required-a"],
    )

    assert metrics["required_section_recall"] == pytest.approx(0.5)
    assert metrics["required_section_precision"] == pytest.approx(1 / 3)
    assert metrics["required_token_precision"] == pytest.approx(100 / 350)
    assert metrics["irrelevant_token_ratio"] == pytest.approx(250 / 350)
    assert metrics["dependency_coverage"] == pytest.approx(0.5)
    assert metrics["topology_alignment"] == pytest.approx(0.5)
    assert metrics["provenance_completeness"] == 1.0
    assert metrics["correct_citation_rate"] == pytest.approx(0.5)
    assert 0.0 <= metrics["redundancy"] <= 1.0


def test_graph_delta_counts_only_unique_required_graph_chunks() -> None:
    requirements = [
        {"skill_name": "skill-a", "heading_contains": "Audited Derivation"},
        {"skill_name": "skill-b", "heading_contains": "Audited Validation"},
    ]
    graph = [
        _chunk("shared", "skill-a", "Audited Derivation", 100),
        _chunk("graph-required", "skill-b", "Audited Validation", 100),
        _chunk("graph-noise", "skill-c", "Overview", 100),
    ]
    bm25 = [_chunk("shared", "skill-a", "Audited Derivation", 100)]

    delta = compare_graph_to_bm25(
        requirements=requirements,
        graph_chunks=graph,
        bm25_chunks=bm25,
    )

    assert delta["graph_added_chunk_count"] == 2
    assert delta["graph_added_required_chunk_count"] == 1
    assert delta["graph_added_required_fraction"] == pytest.approx(0.5)
    assert delta["graph_unique_requirement_gain"] == pytest.approx(0.5)
    assert delta["graph_added_necessary"] is True


def test_graph_delta_does_not_call_irrelevant_addition_necessary() -> None:
    requirements = [
        {"skill_name": "skill-a", "heading_contains": "Audited Derivation"},
    ]
    shared = _chunk("shared", "skill-a", "Audited Derivation", 100)
    graph = [
        shared,
        _chunk("graph-noise", "skill-c", "Overview", 100),
    ]
    bm25 = [shared]

    delta = compare_graph_to_bm25(
        requirements=requirements,
        graph_chunks=graph,
        bm25_chunks=bm25,
    )

    assert delta["graph_unique_requirement_count"] == 0
    assert delta["graph_added_required_chunk_count"] == 0
    assert delta["graph_added_necessary"] is False


@pytest.mark.parametrize(
    ("criterion", "context", "expected_class"),
    [
        (
            {"id": "x", "type": "json_exact", "passed": False},
            {"required_evidence_present": False},
            "retrieval_miss",
        ),
        (
            {"id": "x", "type": "json_exact", "passed": False},
            {
                "required_evidence_present": True,
                "stale_or_conflicting_chunk_selected": True,
            },
            "wrong_or_stale_evidence",
        ),
        (
            {
                "id": "forbidden",
                "type": "forbidden_terms",
                "passed": False,
            },
            {"required_evidence_present": True},
            "forbidden_hallucination",
        ),
        (
            {
                "id": "provenance",
                "type": "provenance_citation",
                "passed": False,
            },
            {"required_evidence_present": True},
            "citation_mismatch",
        ),
        (
            {"id": "formula", "type": "regex", "passed": False},
            {"required_evidence_present": True},
            "derivation_error",
        ),
        (
            {"id": "schema", "type": "object_schema", "passed": False},
            {"required_evidence_present": True},
            "schema_or_serialization_error",
        ),
        (
            {
                "id": "value",
                "type": "json_exact",
                "passed": False,
                "detail": "observed=None; expected='x'",
            },
            {"required_evidence_present": True},
            "evidence_present_generator_omission",
        ),
    ],
)
def test_error_taxonomy_does_not_blame_router_for_output_failures(
    criterion: dict[str, object],
    context: dict[str, object],
    expected_class: str,
) -> None:
    deterministic = {
        "parse_status": "success",
        "criteria": [criterion],
    }

    rows = build_error_decomposition(
        deterministic_evaluation=deterministic,
        criterion_requirements={str(criterion["id"]): [{"skill_name": "skill-a"}]},
        context_by_criterion={str(criterion["id"]): context},
        judge=None,
    )

    assert rows[0]["error_class"] == expected_class
    assert rows[0]["error_class"] in ERROR_CLASSES


def test_parse_failure_precedes_retrieval_attribution() -> None:
    rows = build_error_decomposition(
        deterministic_evaluation={
            "parse_status": "failure",
            "criteria": [{"id": "value", "type": "json_exact", "passed": False}],
        },
        criterion_requirements={"value": [{"skill_name": "skill-a"}]},
        context_by_criterion={"value": {"required_evidence_present": False}},
        judge=None,
    )

    assert rows[0]["error_class"] == "schema_or_serialization_error"


def test_canonical_json_is_order_stable_and_has_final_newline() -> None:
    first = canonical_json_bytes({"b": 2, "a": [3, 1]})
    second = canonical_json_bytes({"a": [3, 1], "b": 2})

    assert first == second
    assert first.endswith(b"\n")
    assert json.loads(first) == {"a": [3, 1], "b": 2}


def test_frozen_panel_shape_and_v6_hash() -> None:
    panel = json.loads(EVALUATED.read_text(encoding="utf-8"))
    rows = panel["results"]

    assert len(rows) == 288
    assert len({row["task_id"] for row in rows}) == 24
    assert len({row["arm"] for row in rows}) == 4
    assert len({row["run_id"] for row in rows}) == 3
    assert REGISTRY.exists()
    assert hashlib.sha256(V6_JUDGED.read_bytes()).hexdigest() == (
        "fb9f787a6e95e2bd0813c7f7b90fd986e64adeba09305645572a3875df927aa0"
    )


@pytest.mark.parametrize(
    ("node_id", "expected"),
    [
        ("adam-adsl", "adsl"),
        ("adam-adae", "adae"),
        ("sdtm-dm-mapping", "dm"),
        ("sdtm-ae-mapping", "ae"),
        ("p21-sdtm-validation", "p21"),
        ("define-xml-sdtm", "define"),
        ("tfl-table-generation", "tfl"),
    ],
)
def test_task_category_comes_from_graph_node(
    node_id: str,
    expected: str,
) -> None:
    assert _domain_from_node_id(node_id) == expected
