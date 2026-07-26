"""Focused deterministic relevance and provenance tests for APS-GxP v6."""

from __future__ import annotations

import pytest

from experiments.aps_gxp_context import (
    Bm25RelevanceIndex,
    canonical_manifest_sha256,
    simulate_skill_change,
    validate_context_manifest,
)


def test_bm25_relevance_is_deterministic_and_task_dependent():
    documents = {
        "ae-mapper": (
            "---\n"
            "title: Adverse Event Mapper\n"
            "description: Map adverse events to SDTM AE with MedDRA coding.\n"
            "---\n"
            "# AE Mapping\n"
            "## ISO 8601 Dates\n"
        ),
        "tfl-builder": (
            "---\n"
            "title: TFL Table Builder\n"
            "description: Build demographic and adverse-event summary tables.\n"
            "---\n"
            "# TFL Generation\n"
            "## Shell Layout\n"
        ),
    }
    index = Bm25RelevanceIndex(documents)

    ae_first = index.score(
        "Map adverse events to SDTM AE with MedDRA preferred terms.",
        "ae-mapper",
    )
    ae_again = index.score(
        "Map adverse events to SDTM AE with MedDRA preferred terms.",
        "ae-mapper",
    )
    tfl_score = index.score(
        "Create a demographic table shell with counts and percentages.",
        "ae-mapper",
    )

    assert ae_first == ae_again
    assert ae_first > tfl_score
    assert index.score(
        "Create a demographic table shell with counts and percentages.",
        "tfl-builder",
    ) > index.score(
        "Map adverse events to SDTM AE with MedDRA preferred terms.",
        "tfl-builder",
    )


def _valid_manifest() -> dict:
    manifest = {
        "schema_version": "aps-gxp-v6-context-manifest-1",
        "task_id": "task-a",
        "arm": "aps_gxp_optimized",
        "run_id": 0,
        "seed": 42,
        "budget": 8000,
        "budget_used": 120,
        "scheduler_sha256": "1" * 64,
        "graph_sha256": "2" * 64,
        "task_sha256": "3" * 64,
        "prompt_context_sha256": "4" * 64,
        "candidates": [
            {
                "skill_name": "ae-mapper",
                "source_path": "csp-skills/ae-mapper/SKILL.md",
                "source_sha256": "5" * 64,
                "declared_version": "1.2.0",
                "active_node_id": "sdtm-ae-mapping",
                "skill_bound_node_ids": ["sdtm-ae-mapping"],
                "graph_relation": "CURRENT",
                "priority_band": "CURRENT",
                "lexical_relevance_score": 7.25,
                "hub_degree": 2,
                "final_priority_score": 1.06,
                "original_estimated_tokens": 120,
                "injected_estimated_tokens": 120,
                "status": "loaded",
                "selection_reason": "current_protected",
                "injected_fragment_sha256": "6" * 64,
            }
        ],
    }
    manifest["manifest_sha256"] = canonical_manifest_sha256(manifest)
    return manifest


def test_manifest_validator_accepts_complete_repository_relative_provenance():
    assert validate_context_manifest(_valid_manifest()) == []


@pytest.mark.parametrize(
    ("mutation", "expected_fragment"),
    (
        (
            lambda manifest: manifest["candidates"][0].__setitem__(
                "source_path", r"C:\SyntheticWorkspace\secret\SKILL.md"
            ),
            "absolute path",
        ),
        (
            lambda manifest: manifest.__setitem__("api_key", "not-a-real-secret"),
            "secret-like field",
        ),
        (
            lambda manifest: manifest["candidates"][0].__setitem__(
                "source_sha256", ""
            ),
            "source_sha256",
        ),
        (
            lambda manifest: manifest["candidates"][0].__setitem__(
                "selection_reason", ""
            ),
            "selection_reason",
        ),
        (
            lambda manifest: manifest.__setitem__("budget_used", 8001),
            "budget",
        ),
        (
            lambda manifest: manifest.__setitem__("manifest_sha256", "0" * 64),
            "manifest hash",
        ),
    ),
)
def test_manifest_validator_rejects_unsafe_or_incomplete_provenance(
    mutation, expected_fragment
):
    manifest = _valid_manifest()
    mutation(manifest)

    errors = validate_context_manifest(manifest)

    assert any(expected_fragment in error for error in errors)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("active_node_id", None),
        ("skill_bound_node_ids", [None]),
        ("graph_relation", "NOT_A_RELATION"),
        ("priority_band", "NOT_A_BAND"),
        ("lexical_relevance_score", float("nan")),
        ("hub_degree", -1),
        ("final_priority_score", None),
        ("original_estimated_tokens", -1),
        ("status", None),
    ),
)
def test_manifest_validator_rejects_malformed_required_provenance(field, value):
    manifest = _valid_manifest()
    manifest["candidates"][0][field] = value
    try:
        manifest["manifest_sha256"] = canonical_manifest_sha256(manifest)
    except ValueError:
        pass

    assert any(
        field in error for error in validate_context_manifest(manifest)
    )


@pytest.mark.parametrize(
    "secret_field",
    ("openai_api_key", "aws_secret_access_key", "clientSecret"),
)
def test_manifest_validator_rejects_composite_secret_field_names(secret_field):
    manifest = _valid_manifest()
    manifest[secret_field] = "not-a-real-secret"
    manifest["manifest_sha256"] = canonical_manifest_sha256(manifest)

    assert any(
        "secret-like field" in error
        for error in validate_context_manifest(manifest)
    )


def test_simulated_skill_change_is_offline_deterministic_and_scoped():
    manifest = _valid_manifest()

    changed_first = simulate_skill_change(manifest, "ae-mapper")
    changed_again = simulate_skill_change(manifest, "ae-mapper")
    unaffected = simulate_skill_change(manifest, "unrelated-skill")

    assert changed_first == changed_again
    assert changed_first["manifest_sha256"] != manifest["manifest_sha256"]
    assert unaffected == manifest
    assert manifest["candidates"][0]["source_sha256"] == "5" * 64


def test_manifest_hash_does_not_depend_on_its_own_hash_field():
    manifest = _valid_manifest()
    original = canonical_manifest_sha256(manifest)
    manifest["manifest_sha256"] = "f" * 64

    assert canonical_manifest_sha256(manifest) == original
