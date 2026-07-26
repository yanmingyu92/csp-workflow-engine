from __future__ import annotations

import copy
from pathlib import Path

import pytest

from experiments.v7_routing import (
    RoutingConfig,
    RoutingCorpus,
    TaskRoutingRequest,
    canonical_token_count,
    chunk_skill_document,
    validate_context_manifest_v7,
)


def _skill(
    name: str,
    body: str,
    *,
    version: str = "3.0",
) -> str:
    return (
        "---\n"
        f"name: {name}\n"
        f"description: Evidence for {name}\n"
        f'version: "{version}"\n'
        "---\n\n"
        f"{body}\n"
    )


def test_chunker_prioritizes_evidence_sections_and_excludes_cli_boilerplate():
    content = _skill(
        "adam-adsl-builder",
        """
## Runtime Configuration (Step 0)
Run the CLI and inspect environment variables.

## Derivation
SAFFL is Y only when qualifying exposure exists.

## Constraints
Population flags follow the prespecified SAP definitions.

## Edge Cases
Randomized but never dosed means SAFFL=N and ITTFL=Y when ITT is all randomized.

## Validation
Assert one record per USUBJID.

## Examples
adam-adsl-builder --input foo --output bar
""",
    )

    chunks = chunk_skill_document(
        "adam-adsl-builder",
        Path("csp-skills/layer-4-adam/adam-adsl-builder/SKILL.md"),
        content,
        max_chunk_tokens=80,
    )

    headings = {chunk.heading_path for chunk in chunks}
    assert any("Derivation" in heading for heading in headings)
    assert any("Constraints" in heading for heading in headings)
    assert any("Edge Cases" in heading for heading in headings)
    assert any("Validation" in heading for heading in headings)
    assert not any("Runtime Configuration" in heading for heading in headings)
    assert not any("Examples" in heading for heading in headings)
    assert all(chunk.chunk_id.startswith("adam-adsl-builder::") for chunk in chunks)
    assert len({chunk.chunk_id for chunk in chunks}) == len(chunks)


def test_dependency_expansion_uses_integration_and_graph_edges_with_two_hop_penalty(
    tmp_path: Path,
):
    skills = tmp_path / "csp-skills"
    for name, body in {
        "current": "## Integration\n**Up:** /upstream\n**Related:** /related",
        "upstream": "## Integration\n**Up:** /source",
        "source": "## Derivation\nRare lineage rule.",
        "related": "## Constraints\nRelated validation rule.",
    }.items():
        path = skills / name / "SKILL.md"
        path.parent.mkdir(parents=True)
        path.write_text(_skill(name, body), encoding="utf-8")

    graph_path = tmp_path / "graph.yaml"
    graph_path.write_text(
        """
schema_version: 1
global_skills: []
nodes:
  - id: source-node
    skills_bound: [/source]
    dependencies: []
  - id: current-node
    skills_bound: [/current]
    dependencies:
      - node: source-node
        edge_type: data-lineage
""",
        encoding="utf-8",
    )

    corpus = RoutingCorpus.from_paths(
        skill_root=skills,
        graph_path=graph_path,
        config=RoutingConfig(context_budget=180, max_chunk_tokens=80),
    )
    distances = corpus.dependency_distances("current-node", max_hops=2)

    assert distances["current"] == 0
    assert distances["upstream"] == 1
    assert distances["related"] == 1
    assert distances["source"] == 1
    assert corpus.dependency_multiplier(1) > corpus.dependency_multiplier(2)
    assert corpus.dependency_multiplier(2) > 0


def test_graph_ranking_can_cross_workflow_band_and_current_is_a_service_floor(
    tmp_path: Path,
):
    skills = tmp_path / "csp-skills"
    documents = {
        "current": """
## Derivation
General subject-level derivation.
## Runtime Configuration
Lots of irrelevant CLI runtime boilerplate.
""",
        "predecessor": """
## Edge Cases
For a randomized but never dosed subject, SAFFL=N while ITTFL=Y.
""",
        "successor": """
## Validation
Validate output formatting.
""",
    }
    for name, body in documents.items():
        path = skills / name / "SKILL.md"
        path.parent.mkdir(parents=True)
        path.write_text(_skill(name, body), encoding="utf-8")
    graph_path = tmp_path / "graph.yaml"
    graph_path.write_text(
        """
schema_version: 1
global_skills: []
nodes:
  - id: predecessor-node
    skills_bound: [/predecessor]
    dependencies: []
  - id: current-node
    skills_bound: [/current]
    dependencies: [predecessor-node]
  - id: successor-node
    skills_bound: [/successor]
    dependencies: [current-node]
""",
        encoding="utf-8",
    )
    corpus = RoutingCorpus.from_paths(
        skill_root=skills,
        graph_path=graph_path,
        config=RoutingConfig(
            context_budget=200,
            current_service_floor_tokens=20,
            max_chunk_tokens=60,
            top_k=4,
        ),
    )
    request = TaskRoutingRequest(
        task_id="dev-adsl-never-dosed",
        node_id="current-node",
        query="What flags apply to a randomized subject who never received a dose?",
    )

    built = corpus.build_context(request, "graph_bm25_chunk_optimized", run_id=0)
    selected = built.manifest["selected_chunks"]
    selected_skills = [row["skill_name"] for row in selected]

    assert "current" in selected_skills
    assert "predecessor" in selected_skills
    predecessor = next(row for row in selected if row["skill_name"] == "predecessor")
    successor = next(row for row in selected if row["skill_name"] == "successor")
    assert predecessor["final_score"] > successor["final_score"]
    assert not any("Runtime Configuration" in row["heading_path"] for row in selected)


def test_bm25_and_random_are_exactly_matched_to_optimized_canonical_budget(
    tmp_path: Path,
):
    skills = tmp_path / "csp-skills"
    for index in range(8):
        name = f"skill-{index}"
        path = skills / name / "SKILL.md"
        path.parent.mkdir(parents=True)
        path.write_text(
            _skill(
                name,
                (
                    "## Derivation\n"
                    f"rare derivation token{index} " + "evidence " * 80
                ),
            ),
            encoding="utf-8",
        )
    graph_path = tmp_path / "graph.yaml"
    graph_path.write_text(
        """
schema_version: 1
global_skills: []
nodes:
  - id: active
    skills_bound: [/skill-0, /skill-1]
    dependencies: []
""",
        encoding="utf-8",
    )
    corpus = RoutingCorpus.from_paths(
        skill_root=skills,
        graph_path=graph_path,
        config=RoutingConfig(
            context_budget=220,
            flat_budget=350,
            max_chunk_tokens=100,
            top_k=8,
        ),
    )
    request = TaskRoutingRequest(
        task_id="match",
        node_id="active",
        query="token0 token1 rare derivation evidence",
    )

    optimized = corpus.build_context(
        request, "graph_bm25_chunk_optimized", run_id=0
    )
    bm25 = corpus.build_context(
        request,
        "full_corpus_bm25_token_matched",
        run_id=0,
        target_tokens=optimized.canonical_tokens,
    )
    random = corpus.build_context(
        request,
        "random_token_matched",
        run_id=0,
        target_tokens=optimized.canonical_tokens,
    )
    flat = corpus.build_context(request, "flat_8000", run_id=0)

    assert optimized.canonical_tokens == bm25.canonical_tokens
    assert optimized.canonical_tokens == random.canonical_tokens
    assert canonical_token_count(optimized.context_text) == optimized.canonical_tokens
    assert flat.canonical_tokens == 350
    assert flat.canonical_tokens > optimized.canonical_tokens


def test_bm25_budget_fill_extends_beyond_small_top_k_core(tmp_path: Path):
    skills = tmp_path / "csp-skills"
    documents = {
        "current-large": (
            "## Audited Derivation\n"
            "current dependency evidence " + "largecontext " * 100
        ),
        "lexical-small": (
            "## Audited Derivation\nrarequery exact lexical evidence"
        ),
        "filler": (
            "## Validation\nadditional evidence " + "filltoken " * 100
        ),
    }
    for name, body in documents.items():
        path = skills / name / "SKILL.md"
        path.parent.mkdir(parents=True)
        path.write_text(_skill(name, body), encoding="utf-8")
    graph_path = tmp_path / "graph.yaml"
    graph_path.write_text(
        """
schema_version: 1
global_skills: []
nodes:
  - id: active
    skills_bound: [/current-large]
    dependencies: []
""",
        encoding="utf-8",
    )
    corpus = RoutingCorpus.from_paths(
        skill_root=skills,
        graph_path=graph_path,
        config=RoutingConfig(
            context_budget=100,
            flat_budget=200,
            max_chunk_tokens=120,
            top_k=1,
            current_service_floor_tokens=80,
            score_gap_ratio=0.2,
            graph_current_boost=20.0,
        ),
    )
    request = TaskRoutingRequest(
        task_id="budget-fill",
        node_id="active",
        query="rarequery exact lexical evidence",
    )
    optimized = corpus.build_context(
        request, "graph_bm25_chunk_optimized", run_id=0
    )

    bm25 = corpus.build_context(
        request,
        "full_corpus_bm25_token_matched",
        run_id=0,
        target_tokens=optimized.canonical_tokens,
    )

    assert bm25.canonical_tokens == optimized.canonical_tokens
    assert len(bm25.manifest["selected_chunks"]) > 1
    assert any(
        row["selection_reason"] == "full_corpus_bm25_budget_fill"
        for row in bm25.manifest["selected_chunks"]
    )


def test_mmr_reduces_duplicate_sections_and_version_conflicts_are_explicit(
    tmp_path: Path,
):
    skills = tmp_path / "csp-skills"
    documents = {
        "fresh": "## Constraints\nUse SDTM IG v3.4. " + "same duplicate " * 30,
        "duplicate": "## Constraints\nUse SDTM IG v3.4. " + "same duplicate " * 30,
        "stale": "## Constraints\nUse SDTM IG v3.3 for this mapping.",
        "diverse": "## Edge Cases\nPreserve partial ISO 8601 dates without imputation.",
    }
    for name, body in documents.items():
        path = skills / name / "SKILL.md"
        path.parent.mkdir(parents=True)
        path.write_text(_skill(name, body), encoding="utf-8")
    graph_path = tmp_path / "graph.yaml"
    graph_path.write_text(
        """
schema_version: 1
global_skills: []
nodes:
  - id: active
    skills_bound: [/fresh, /duplicate, /stale, /diverse]
    dependencies: []
""",
        encoding="utf-8",
    )
    corpus = RoutingCorpus.from_paths(
        skill_root=skills,
        graph_path=graph_path,
        config=RoutingConfig(
            context_budget=180,
            max_chunk_tokens=80,
            top_k=3,
            pinned_versions={"SDTM IG": "3.4"},
        ),
    )
    request = TaskRoutingRequest(
        task_id="conflict",
        node_id="active",
        query="SDTM IG mapping partial date constraint",
    )

    built = corpus.build_context(request, "graph_bm25_chunk_optimized", run_id=0)
    selected = built.manifest["selected_chunks"]

    assert any(row["skill_name"] == "diverse" for row in selected)
    assert not any(row["skill_name"] == "stale" for row in selected)
    assert built.manifest["version_conflicts"]
    assert built.manifest["version_conflicts"][0]["pinned_version"] == "3.4"


def test_manifest_is_deterministic_complete_and_fail_closed(tmp_path: Path):
    skills = tmp_path / "csp-skills"
    path = skills / "only" / "SKILL.md"
    path.parent.mkdir(parents=True)
    path.write_text(
        _skill("only", "## Validation\nDeterministic manifest provenance."),
        encoding="utf-8",
    )
    graph_path = tmp_path / "graph.yaml"
    graph_path.write_text(
        """
schema_version: 1
global_skills: []
nodes:
  - id: active
    skills_bound: [/only]
    dependencies: []
""",
        encoding="utf-8",
    )
    corpus = RoutingCorpus.from_paths(
        skill_root=skills,
        graph_path=graph_path,
        config=RoutingConfig(context_budget=80, max_chunk_tokens=60),
    )
    request = TaskRoutingRequest(
        task_id="manifest",
        node_id="active",
        query="deterministic manifest provenance",
    )

    first = corpus.build_context(request, "graph_bm25_chunk_optimized", 0)
    second = corpus.build_context(request, "graph_bm25_chunk_optimized", 0)

    assert first.manifest == second.manifest
    assert validate_context_manifest_v7(first.manifest) == []
    assert first.manifest["context_sha256"] == second.manifest["context_sha256"]
    assert first.manifest["manifest_sha256"] == second.manifest["manifest_sha256"]

    tampered = copy.deepcopy(first.manifest)
    tampered["selected_chunks"][0]["source_sha256"] = "0" * 64
    assert "manifest hash mismatch" in validate_context_manifest_v7(tampered)

    unsafe = copy.deepcopy(first.manifest)
    unsafe["api_key"] = "not-a-real-key"
    assert any(
        "secret-like field" in error
        for error in validate_context_manifest_v7(unsafe)
    )


def test_change_containment_only_marks_contexts_selecting_changed_chunks(
    tmp_path: Path,
):
    skills = tmp_path / "csp-skills"
    for name, token in (("alpha", "rarealpha"), ("beta", "rarebeta")):
        path = skills / name / "SKILL.md"
        path.parent.mkdir(parents=True)
        path.write_text(
            _skill(name, f"## Derivation\n{token} derivation."),
            encoding="utf-8",
        )
    graph_path = tmp_path / "graph.yaml"
    graph_path.write_text(
        """
schema_version: 1
global_skills: []
nodes:
  - id: alpha-node
    skills_bound: [/alpha]
    dependencies: []
  - id: beta-node
    skills_bound: [/beta]
    dependencies: []
""",
        encoding="utf-8",
    )
    corpus = RoutingCorpus.from_paths(
        skill_root=skills,
        graph_path=graph_path,
        config=RoutingConfig(context_budget=70, top_k=1),
    )
    alpha = corpus.build_context(
        TaskRoutingRequest("alpha-task", "alpha-node", "rarealpha"),
        "graph_bm25_chunk_optimized",
        0,
    )
    beta = corpus.build_context(
        TaskRoutingRequest("beta-task", "beta-node", "rarebeta"),
        "graph_bm25_chunk_optimized",
        0,
    )

    impact = corpus.change_impact_scope(
        [alpha.manifest, beta.manifest], changed_skill="alpha"
    )

    assert impact["affected_task_ids"] == ["alpha-task"]
    assert impact["unaffected_task_ids"] == ["beta-task"]


def test_change_containment_aggregates_multiple_manifests_per_task():
    affected_manifest = {
        "task_id": "shared-task",
        "selected_chunks": [{"skill_name": "alpha"}],
    }
    same_task_unaffected_arm = {
        "task_id": "shared-task",
        "selected_chunks": [{"skill_name": "beta"}],
    }
    unaffected_manifest = {
        "task_id": "other-task",
        "selected_chunks": [{"skill_name": "beta"}],
    }

    impact = RoutingCorpus.change_impact_scope(
        [
            affected_manifest,
            same_task_unaffected_arm,
            unaffected_manifest,
        ],
        changed_skill="alpha",
    )

    assert impact["affected_task_ids"] == ["shared-task"]
    assert impact["unaffected_task_ids"] == ["other-task"]
    assert impact["affected_count"] == 1
    assert impact["total_count"] == 2


def test_matched_context_rejects_missing_target_and_unknown_arm(tmp_path: Path):
    skills = tmp_path / "csp-skills"
    path = skills / "one" / "SKILL.md"
    path.parent.mkdir(parents=True)
    path.write_text(_skill("one", "## Derivation\nOne."), encoding="utf-8")
    graph_path = tmp_path / "graph.yaml"
    graph_path.write_text(
        "nodes:\n  - id: active\n    skills_bound: [/one]\n    dependencies: []\n",
        encoding="utf-8",
    )
    corpus = RoutingCorpus.from_paths(skills, graph_path, RoutingConfig())
    request = TaskRoutingRequest("x", "active", "one")

    with pytest.raises(ValueError, match="target_tokens"):
        corpus.build_context(request, "random_token_matched", 0)
    with pytest.raises(ValueError, match="Unknown V7 arm"):
        corpus.build_context(request, "other", 0)
