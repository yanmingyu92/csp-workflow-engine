"""Offline V7 oracle retrieval and error decomposition.

The analysis consumes frozen registry, manifest, response, and deterministic
criterion histories. It never calls a model or alters the V7 router.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import yaml  # type: ignore[import-untyped]

from experiments.v7_oracle_metrics import (
    ERROR_CLASSES,
    build_chunk_corpus,
    build_error_decomposition,
    build_graph_index,
    canonical_json_bytes,
    compare_graph_to_bm25,
    compute_cell_metrics,
    confusion_counts,
    dependency_routes,
    extract_task_requirements,
    lexical_overlap,
    mean,
    parse_response_json,
    quantile,
    reconstruct_fragment,
    requirement_matches_chunk,
    response_evidence_ids,
    sha256_file,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = (
    ROOT / "experiments" / "results" / "experiment_v7_oracle_decomposition_20260725"
)
EXPECTED_V6_SHA256 = "fb9f787a6e95e2bd0813c7f7b90fd986e64adeba09305645572a3875df927aa0"
ARMS = (
    "graph_bm25_chunk_optimized",
    "full_corpus_bm25_token_matched",
    "random_token_matched",
    "flat_8000",
)
ARM_ORDER = {arm: index for index, arm in enumerate(ARMS)}
METRIC_KEYS = (
    "required_section_recall",
    "required_section_precision",
    "required_token_precision",
    "dependency_coverage",
    "topology_alignment",
    "irrelevant_token_ratio",
    "redundancy",
    "version_selection_correctness",
    "version_conflict_output_correctness",
    "provenance_completeness",
    "correct_citation_rate",
)
FROZEN_INPUTS = {
    "task_registry": (
        "experiments/config/" "experiment_v7_routing_sensitive_tasks_20260725.yaml"
    ),
    "final_freeze": (
        "experiments/config/"
        "experiment_v7_routing_sensitive_freeze_final_audit_20260725.json"
    ),
    "graph": "graph/regulatory-graph.yaml",
    "stage0_diagnostics": (
        "experiments/results/" "experiment_v7_routing_sensitive_stage0_20260725.json"
    ),
    "formal_generation": (
        "experiments/results/"
        "experiment_v7_routing_sensitive_formal_generation_20260725.json"
    ),
    "formal_evaluated": (
        "experiments/results/"
        "experiment_v7_routing_sensitive_formal_evaluated_20260725.json"
    ),
    "frozen_analysis": (
        "experiments/results/" "experiment_v7_routing_sensitive_analysis_20260725.json"
    ),
    "frozen_failure_log": (
        "experiments/results/"
        "experiment_v7_routing_sensitive_failure_log_20260725.json"
    ),
    "v7_router_source": "experiments/v7_routing.py",
    "v7_validator_source": "experiments/v7_deterministic_eval.py",
    "v7_stage0_source": "experiments/v7_stage0.py",
    "v7_runner_source": "experiments/run_experiment_v7_routing_sensitive.py",
    "v7_analysis_source": "experiments/analyze_experiment_v7.py",
    "v7_verifier_source": "experiments/verify_experiment_v7.py",
    "v7_plan": "plan/jmir_aps_gxp_v7_routing_sensitive_experiment_20260725.md",
    "v6_judged_baseline": (
        "experiments/results/" "experiment_v6_aps_gxp_formal_20260724_judged.json"
    ),
}
FROZEN_SOURCE_PATHS = {
    "runner": "experiments/run_experiment_v7_routing_sensitive.py",
    "routing": "experiments/v7_routing.py",
    "deterministic_eval": "experiments/v7_deterministic_eval.py",
    "stage0": "experiments/v7_stage0.py",
    "task_registry": (
        "experiments/config/" "experiment_v7_routing_sensitive_tasks_20260725.yaml"
    ),
    "graph": "graph/regulatory-graph.yaml",
    "analyzer": "experiments/analyze_experiment_v7.py",
    "verifier": "experiments/verify_experiment_v7.py",
}


def _canonical_hash(value: Any) -> str:
    compact = json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(compact.encode("utf-8")).hexdigest()


def _domain_from_node_id(node_id: str) -> str:
    """Return the benchmark category encoded by the graph node, not task text."""
    normalized = node_id.lower()
    if normalized.startswith("adam-adsl"):
        return "adsl"
    if normalized.startswith("adam-adae"):
        return "adae"
    if normalized.startswith("sdtm-dm"):
        return "dm"
    if normalized.startswith("sdtm-ae"):
        return "ae"
    if normalized.startswith("p21-"):
        return "p21"
    if normalized.startswith("define-"):
        return "define"
    if normalized.startswith("tfl-"):
        return "tfl"
    return "other"


def _mean_dict(
    rows: Sequence[Mapping[str, Any]], keys: Iterable[str]
) -> dict[str, float]:
    return {key: mean([float(row.get(key, 0.0)) for row in rows]) for key in keys}


def _bootstrap_mean_ci(
    values: Sequence[float],
    *,
    seed: int,
    iterations: int = 10_000,
) -> list[float]:
    if not values:
        return [0.0, 0.0]
    rng = random.Random(seed)
    estimates = []
    for _ in range(iterations):
        estimates.append(mean([values[rng.randrange(len(values))] for _ in values]))
    return [quantile(estimates, 0.025), quantile(estimates, 0.975)]


def _loo_summary(values: Sequence[float]) -> dict[str, Any]:
    if len(values) <= 1:
        return {"minimum": mean(values), "maximum": mean(values), "sign_changes": 0}
    full = mean(values)
    estimates = [
        mean([value for index, value in enumerate(values) if index != held_out])
        for held_out in range(len(values))
    ]
    sign_changes = sum(
        1
        for estimate in estimates
        if full != 0.0 and estimate != 0.0 and (estimate > 0) != (full > 0)
    )
    return {
        "minimum": min(estimates),
        "maximum": max(estimates),
        "sign_changes": sign_changes,
    }


def _requirement_text(
    requirements: Sequence[Mapping[str, Any]],
    corpus: Mapping[str, Mapping[str, Any]],
) -> str:
    chunks = [
        str(chunk["content"])
        for chunk in corpus.values()
        if any(requirement_matches_chunk(req, chunk) for req in requirements)
    ]
    return "\n\n".join(chunks)


def _validate_manifest_rows(
    *,
    rows: Sequence[Mapping[str, Any]],
    corpus: Mapping[str, Mapping[str, Any]],
) -> tuple[dict[str, str], list[dict[str, Any]]]:
    fragments: dict[str, str] = {}
    failures: list[dict[str, Any]] = []
    for result in rows:
        run_key = str(result.get("run_key"))
        response_hash = hashlib.sha256(
            str(result.get("response", "")).encode("utf-8")
        ).hexdigest()
        if response_hash != result.get("response_sha256"):
            failures.append(
                {
                    "code": "response_hash_mismatch",
                    "run_key": run_key,
                    "severity": "error",
                }
            )
        manifest = result.get("manifest", {})
        expected_manifest_hash = str(manifest.get("manifest_sha256", ""))
        unhashed = dict(manifest)
        unhashed.pop("manifest_sha256", None)
        if _canonical_hash(unhashed) != expected_manifest_hash:
            failures.append(
                {
                    "code": "manifest_hash_mismatch",
                    "run_key": run_key,
                    "severity": "error",
                }
            )
        if result.get("manifest_sha256") != expected_manifest_hash:
            failures.append(
                {
                    "code": "outer_manifest_hash_mismatch",
                    "run_key": run_key,
                    "severity": "error",
                }
            )
        if result.get("repeated_manifest_sha256") != expected_manifest_hash:
            failures.append(
                {
                    "code": "repeated_manifest_hash_mismatch",
                    "run_key": run_key,
                    "severity": "error",
                }
            )
        for chunk_row in manifest.get("selected_chunks", []):
            chunk_id = str(chunk_row.get("chunk_id"))
            reconstructed = corpus.get(chunk_id)
            if not reconstructed:
                failures.append(
                    {
                        "code": "chunk_not_reconstructed",
                        "run_key": run_key,
                        "chunk_id": chunk_id,
                        "severity": "error",
                    }
                )
                continue
            for field in ("source_sha256", "content_sha256"):
                if reconstructed.get(field) != chunk_row.get(field):
                    failures.append(
                        {
                            "code": f"{field}_mismatch",
                            "run_key": run_key,
                            "chunk_id": chunk_id,
                            "severity": "error",
                        }
                    )
            fragment = reconstruct_fragment(chunk_row, corpus)
            if fragment is None:
                failures.append(
                    {
                        "code": "injected_fragment_not_reconstructed",
                        "run_key": run_key,
                        "chunk_id": chunk_id,
                        "severity": "error",
                    }
                )
            else:
                fragments[chunk_id] = fragment
    return fragments, sorted(
        failures,
        key=lambda row: (
            str(row.get("code")),
            str(row.get("run_key")),
            str(row.get("chunk_id", "")),
        ),
    )


def _audit_final_freeze(
    *,
    root: Path,
    final_freeze: Mapping[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Verify the complete V7 freeze contract without importing frozen code."""
    failures: list[dict[str, Any]] = []

    def record_failure(code: str, **details: Any) -> None:
        failures.append({"code": code, "severity": "error", **details})

    freeze_without_content_hash = dict(final_freeze)
    expected_content_hash = str(
        freeze_without_content_hash.pop("freeze_content_sha256", "")
    )
    if _canonical_hash(freeze_without_content_hash) != expected_content_hash:
        record_failure("freeze_content_hash_mismatch")

    direct_checks = {
        "v6_immutable_sha256": FROZEN_INPUTS["v6_judged_baseline"],
        "stage0_sha256": FROZEN_INPUTS["stage0_diagnostics"],
        "plan_sha256": FROZEN_INPUTS["v7_plan"],
        "task_registry_sha256": FROZEN_INPUTS["task_registry"],
    }
    for field, relative in direct_checks.items():
        observed = sha256_file(root / relative)
        if observed != final_freeze.get(field):
            record_failure(
                "freeze_direct_hash_mismatch",
                field=field,
                path=relative,
            )

    source_hashes = final_freeze.get("source_hashes", {})
    verified_source_count = 0
    for role, expected in sorted(source_hashes.items()):
        source_relative = FROZEN_SOURCE_PATHS.get(str(role))
        if source_relative is None:
            record_failure("unknown_frozen_source_role", role=str(role))
            continue
        path = root / source_relative
        if not path.is_file():
            record_failure(
                "frozen_source_missing",
                role=str(role),
                path=source_relative,
            )
            continue
        if sha256_file(path) != expected:
            record_failure(
                "frozen_source_hash_mismatch",
                role=str(role),
                path=source_relative,
            )
            continue
        verified_source_count += 1

    corpus_files = list(final_freeze.get("corpus_files", []))
    if _canonical_hash(corpus_files) != final_freeze.get("corpus_tree_sha256"):
        record_failure("corpus_tree_hash_mismatch")
    verified_corpus_count = 0
    root_resolved = root.resolve()
    for row in corpus_files:
        relative = str(row.get("path", ""))
        path = (root / relative).resolve()
        if root_resolved != path and root_resolved not in path.parents:
            record_failure("unsafe_frozen_corpus_path", path=relative)
            continue
        if not path.is_file():
            record_failure("frozen_corpus_file_missing", path=relative)
            continue
        if sha256_file(path) != row.get("sha256"):
            record_failure("frozen_corpus_hash_mismatch", path=relative)
            continue
        verified_corpus_count += 1

    preflight = final_freeze.get("heldout_structural_preflight", {})
    preflight_contract = {
        "quality_scores_computed": False,
        "generation_or_judge_scores_used": False,
        "cell_count": 96,
    }
    for field, expected in preflight_contract.items():
        if preflight.get(field) != expected:
            record_failure(
                "heldout_preflight_contract_mismatch",
                field=field,
            )
    boundary_contract = {
        "manuscript_modified": False,
        "operational_gxp_compliance_claimed": False,
    }
    for field, expected in boundary_contract.items():
        if final_freeze.get(field) != expected:
            record_failure("freeze_claim_boundary_mismatch", field=field)

    ordered_failures = sorted(
        failures,
        key=lambda row: (
            str(row.get("code")),
            str(row.get("field", "")),
            str(row.get("role", "")),
            str(row.get("path", "")),
        ),
    )
    return (
        {
            "freeze_content_hash_verified": (
                _canonical_hash(freeze_without_content_hash) == expected_content_hash
            ),
            "frozen_source_count": len(source_hashes),
            "verified_source_count": verified_source_count,
            "frozen_corpus_file_count": len(corpus_files),
            "verified_corpus_file_count": verified_corpus_count,
            "corpus_tree_hash_verified": (
                _canonical_hash(corpus_files) == final_freeze.get("corpus_tree_sha256")
            ),
            "mismatch_count": len(ordered_failures),
        },
        ordered_failures,
    )


def _audit_generation_evaluation_linkage(
    *,
    generation_rows: Sequence[Mapping[str, Any]],
    evaluation_rows: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, int], list[dict[str, Any]]]:
    """Verify that every evaluated response is the exact frozen generation."""
    failures: list[dict[str, Any]] = []

    def index_rows(
        rows: Sequence[Mapping[str, Any]],
        label: str,
    ) -> dict[str, Mapping[str, Any]]:
        output: dict[str, Mapping[str, Any]] = {}
        for row in rows:
            run_key = str(row.get("run_key", ""))
            if not run_key:
                failures.append(
                    {
                        "code": f"{label}_run_key_missing",
                        "severity": "error",
                    }
                )
            elif run_key in output:
                failures.append(
                    {
                        "code": f"{label}_run_key_duplicate",
                        "run_key": run_key,
                        "severity": "error",
                    }
                )
            else:
                output[run_key] = row
        return output

    generation_by_key = index_rows(generation_rows, "generation")
    evaluation_by_key = index_rows(evaluation_rows, "evaluation")
    all_keys = sorted(set(generation_by_key) | set(evaluation_by_key))
    linked_count = 0
    scalar_fields = (
        "task_id",
        "node_id",
        "arm",
        "run_id",
        "response_sha256",
        "manifest_sha256",
        "serialized_prompt_sha256",
        "context_canonical_tokens",
    )
    for run_key in all_keys:
        generation = generation_by_key.get(run_key)
        evaluation = evaluation_by_key.get(run_key)
        if generation is None:
            failures.append(
                {
                    "code": "generation_record_missing",
                    "run_key": run_key,
                    "severity": "error",
                }
            )
            continue
        if evaluation is None:
            failures.append(
                {
                    "code": "evaluation_record_missing",
                    "run_key": run_key,
                    "severity": "error",
                }
            )
            continue
        linked_count += 1
        for field in scalar_fields:
            if generation.get(field) != evaluation.get(field):
                failures.append(
                    {
                        "code": "generation_evaluation_field_mismatch",
                        "run_key": run_key,
                        "field": field,
                        "severity": "error",
                    }
                )
        for field in ("response", "manifest"):
            if _canonical_hash(generation.get(field)) != _canonical_hash(
                evaluation.get(field)
            ):
                failures.append(
                    {
                        "code": "generation_evaluation_content_mismatch",
                        "run_key": run_key,
                        "field": field,
                        "severity": "error",
                    }
                )
    ordered = sorted(
        failures,
        key=lambda row: (
            str(row.get("code")),
            str(row.get("run_key", "")),
            str(row.get("field", "")),
        ),
    )
    return (
        {
            "generation_record_count": len(generation_rows),
            "evaluation_record_count": len(evaluation_rows),
            "linked_record_count": linked_count,
            "mismatch_count": len(ordered),
        },
        ordered,
    )


def _criterion_context(
    *,
    requirements: Sequence[Mapping[str, Any]],
    selected: Sequence[Mapping[str, Any]],
    stale_selected_count: int,
) -> dict[str, Any]:
    requirement_hits = [
        any(requirement_matches_chunk(req, row) for row in selected)
        for req in requirements
    ]
    return {
        "required_evidence_present": all(requirement_hits),
        "requirement_hits": requirement_hits,
        "stale_or_conflicting_chunk_selected": stale_selected_count > 0,
    }


def _task_metadata(
    *,
    tasks: Sequence[Mapping[str, Any]],
    requirement_maps: Mapping[str, Mapping[str, Any]],
    corpus: Mapping[str, Mapping[str, Any]],
    graph_index: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    metadata: dict[str, dict[str, Any]] = {}
    overlaps = []
    for task in tasks:
        task_id = str(task["task_id"])
        requirements = requirement_maps[task_id]["task_requirements"]
        evidence_text = _requirement_text(requirements, corpus)
        overlap = lexical_overlap(str(task["prompt"]), evidence_text)
        distances, route_labels = dependency_routes(graph_index, str(task["node_id"]))
        required_routes = [
            route_labels.get(str(req["skill_name"]), "unreachable")
            for req in requirements
        ]
        required_distances = [
            distances.get(str(req["skill_name"])) for req in requirements
        ]
        metadata[task_id] = {
            "task_id": task_id,
            "node_id": str(task["node_id"]),
            "task_category": _domain_from_node_id(str(task["node_id"])),
            "lexical_overlap": overlap,
            "required_route_labels": required_routes,
            "required_dependency_distances": required_distances,
            "multi_hop": any(
                distance is not None and distance >= 1
                for distance in required_distances
            ),
            "topology_unreachable": any(
                distance is None for distance in required_distances
            ),
            "_distances": distances,
            "_route_labels": route_labels,
        }
        overlaps.append(overlap["jaccard"])
    lower = quantile(overlaps, 1 / 3)
    upper = quantile(overlaps, 2 / 3)
    for item in metadata.values():
        value = float(item["lexical_overlap"]["jaccard"])
        item["lexical_overlap_stratum"] = (
            "low" if value <= lower else "high" if value > upper else "middle"
        )
        item["low_overlap"] = value <= lower
    return metadata


def _score_without_provenance(evaluation: Mapping[str, Any]) -> float:
    criteria = [
        criterion
        for criterion in evaluation.get("criteria", [])
        if criterion.get("type") != "provenance_citation"
    ]
    available = sum(float(item.get("weight", 0.0)) for item in criteria)
    earned = sum(float(item.get("earned_weight", 0.0)) for item in criteria)
    return earned / available if available else 0.0


def _build_cells(
    *,
    results: Sequence[Mapping[str, Any]],
    tasks_by_id: Mapping[str, Mapping[str, Any]],
    requirement_maps: Mapping[str, Mapping[str, Any]],
    task_metadata: Mapping[str, Mapping[str, Any]],
    fragments: Mapping[str, str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    cells: list[dict[str, Any]] = []
    criterion_records: list[dict[str, Any]] = []
    error_rows: list[dict[str, Any]] = []
    ordered = sorted(
        results,
        key=lambda row: (
            str(row["task_id"]),
            ARM_ORDER[str(row["arm"])],
            int(row["run_id"]),
        ),
    )
    for result in ordered:
        task_id = str(result["task_id"])
        requirements = requirement_maps[task_id]["task_requirements"]
        manifest = result["manifest"]
        selected = manifest["selected_chunks"]
        parsed, parse_strategy = parse_response_json(str(result["response"]))
        cited_ids = response_evidence_ids(parsed)
        distances = task_metadata[task_id]["_distances"]
        metrics = compute_cell_metrics(
            requirements=requirements,
            manifest=manifest,
            chunk_content=fragments,
            dependency_reachable_skills=distances,
            response_evidence_ids=cited_ids,
        )
        evaluation = result["deterministic_evaluation"]
        criterion_contexts: dict[str, dict[str, Any]] = {}
        for criterion in evaluation.get("criteria", []):
            criterion_id = str(criterion["id"])
            criterion_requirements = requirement_maps[task_id]["criteria"][criterion_id]
            context = _criterion_context(
                requirements=criterion_requirements,
                selected=selected,
                stale_selected_count=int(metrics["stale_selected_count"]),
            )
            criterion_contexts[criterion_id] = context
            criterion_records.append(
                {
                    "task_id": task_id,
                    "arm": str(result["arm"]),
                    "run_id": int(result["run_id"]),
                    "criterion_id": criterion_id,
                    "criterion_type": str(criterion["type"]),
                    "criterion_passed": bool(criterion["passed"]),
                    "criterion_weight": float(criterion["weight"]),
                    "required_evidence_present": bool(
                        context["required_evidence_present"]
                    ),
                }
            )
        decomposed = build_error_decomposition(
            deterministic_evaluation=evaluation,
            criterion_requirements=requirement_maps[task_id]["criteria"],
            context_by_criterion=criterion_contexts,
            judge=result.get("llm_judgment"),
        )
        for error in decomposed:
            error_rows.append(
                {
                    "task_id": task_id,
                    "arm": str(result["arm"]),
                    "run_id": int(result["run_id"]),
                    **error,
                }
            )
        version_criteria = [
            criterion
            for criterion in evaluation.get("criteria", [])
            if any(
                term in str(criterion.get("id", "")).lower()
                for term in ("version", "selected", "status", "standard")
            )
            and criterion.get("type") != "provenance_citation"
        ]
        metrics["version_conflict_output_correctness"] = (
            mean([float(item["passed"]) for item in version_criteria])
            if version_criteria
            else 1.0
        )
        metadata = task_metadata[task_id]
        cells.append(
            {
                "task_id": task_id,
                "arm": str(result["arm"]),
                "run_id": int(result["run_id"]),
                "manifest_sha256": str(result["manifest_sha256"]),
                "response_sha256": str(result["response_sha256"]),
                "deterministic_score": float(evaluation["score"]),
                "substantive_score_excluding_provenance": (
                    _score_without_provenance(evaluation)
                ),
                "parse_status": str(evaluation["parse_status"]),
                "response_parse_strategy": parse_strategy,
                "task_category": str(metadata["task_category"]),
                "lexical_overlap": metadata["lexical_overlap"],
                "lexical_overlap_stratum": metadata["lexical_overlap_stratum"],
                "multi_hop": bool(metadata["multi_hop"]),
                "low_overlap": bool(metadata["low_overlap"]),
                "required_route_labels": metadata["required_route_labels"],
                "metrics": metrics,
            }
        )
    return cells, criterion_records, error_rows


def _aggregate_cells(cells: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    by_arm: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for cell in cells:
        by_arm[str(cell["arm"])].append(cell)
    output: dict[str, Any] = {}
    for arm in ARMS:
        rows = by_arm[arm]
        metric_rows = [row["metrics"] for row in rows]
        output[arm] = {
            "cell_count": len(rows),
            "task_count": len({str(row["task_id"]) for row in rows}),
            "repetitions_per_task": 3,
            "deterministic_score_mean": mean(
                [float(row["deterministic_score"]) for row in rows]
            ),
            "substantive_score_excluding_provenance_mean": mean(
                [float(row["substantive_score_excluding_provenance"]) for row in rows]
            ),
            **_mean_dict(metric_rows, METRIC_KEYS),
            "bm25_recall_ceiling_fraction": mean(
                [
                    float(row["metrics"]["required_section_recall"] == 1.0)
                    for row in rows
                ]
            ),
        }
    return output


def _task_arm_means(cells: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for cell in cells:
        grouped[(str(cell["task_id"]), str(cell["arm"]))].append(cell)
    rows = []
    for (task_id, arm), members in sorted(
        grouped.items(), key=lambda item: (item[0][0], ARM_ORDER[item[0][1]])
    ):
        rows.append(
            {
                "task_id": task_id,
                "arm": arm,
                "deterministic_score": mean(
                    [float(item["deterministic_score"]) for item in members]
                ),
                "substantive_score_excluding_provenance": mean(
                    [
                        float(item["substantive_score_excluding_provenance"])
                        for item in members
                    ]
                ),
                **{
                    key: mean([float(item["metrics"][key]) for item in members])
                    for key in METRIC_KEYS
                },
                "task_category": str(members[0]["task_category"]),
                "lexical_overlap_stratum": str(members[0]["lexical_overlap_stratum"]),
                "multi_hop": bool(members[0]["multi_hop"]),
                "low_overlap": bool(members[0]["low_overlap"]),
            }
        )
    return rows


def _graph_deltas(
    *,
    cells: Sequence[Mapping[str, Any]],
    results: Sequence[Mapping[str, Any]],
    requirement_maps: Mapping[str, Mapping[str, Any]],
    task_metadata: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    results_by_key = {
        (str(row["task_id"]), str(row["arm"]), int(row["run_id"])): row
        for row in results
    }
    cells_by_key = {
        (str(row["task_id"]), str(row["arm"]), int(row["run_id"])): row for row in cells
    }
    pairs: list[dict[str, Any]] = []
    edge_rows: list[dict[str, Any]] = []
    for task_id in sorted(requirement_maps):
        for run_id in range(3):
            graph_result = results_by_key[
                (task_id, "graph_bm25_chunk_optimized", run_id)
            ]
            bm25_result = results_by_key[
                (task_id, "full_corpus_bm25_token_matched", run_id)
            ]
            graph_cell = cells_by_key[(task_id, "graph_bm25_chunk_optimized", run_id)]
            bm25_cell = cells_by_key[
                (task_id, "full_corpus_bm25_token_matched", run_id)
            ]
            delta = compare_graph_to_bm25(
                requirements=requirement_maps[task_id]["task_requirements"],
                graph_chunks=graph_result["manifest"]["selected_chunks"],
                bm25_chunks=bm25_result["manifest"]["selected_chunks"],
            )
            recall_delta = float(
                graph_cell["metrics"]["required_section_recall"]
            ) - float(bm25_cell["metrics"]["required_section_recall"])
            score_delta = float(graph_cell["deterministic_score"]) - float(
                bm25_cell["deterministic_score"]
            )
            substantive_delta = float(
                graph_cell["substantive_score_excluding_provenance"]
            ) - float(bm25_cell["substantive_score_excluding_provenance"])
            precision_delta = float(
                graph_cell["metrics"]["required_section_precision"]
            ) - float(bm25_cell["metrics"]["required_section_precision"])
            token_precision_delta = float(
                graph_cell["metrics"]["required_token_precision"]
            ) - float(bm25_cell["metrics"]["required_token_precision"])
            evidence_state = (
                "improved"
                if recall_delta > 0
                else "worsened" if recall_delta < 0 else "unchanged"
            )
            output_state = (
                "improved"
                if score_delta > 0
                else "worsened" if score_delta < 0 else "unchanged"
            )
            pair = {
                "task_id": task_id,
                "run_id": run_id,
                **delta,
                "required_section_recall_delta": recall_delta,
                "required_section_precision_delta": precision_delta,
                "required_token_precision_delta": token_precision_delta,
                "deterministic_score_delta": score_delta,
                "substantive_score_excluding_provenance_delta": (substantive_delta),
                "evidence_state": evidence_state,
                "output_state": output_state,
                "task_category": graph_cell["task_category"],
                "lexical_overlap_stratum": graph_cell["lexical_overlap_stratum"],
                "multi_hop": graph_cell["multi_hop"],
            }
            pairs.append(pair)
            route_labels = task_metadata[task_id]["_route_labels"]
            graph_rows = {
                str(row["chunk_id"]): row
                for row in graph_result["manifest"]["selected_chunks"]
            }
            required_ids = set(delta["graph_added_required_chunk_ids"])
            for chunk_id in delta["graph_added_chunk_ids"]:
                row = graph_rows[chunk_id]
                edge_rows.append(
                    {
                        "task_id": task_id,
                        "run_id": run_id,
                        "chunk_id": chunk_id,
                        "route_label": route_labels.get(
                            str(row["skill_name"]), "unreachable"
                        ),
                        "required": chunk_id in required_ids,
                        "deterministic_score_delta": score_delta,
                    }
                )
    task_pairs: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for pair in pairs:
        task_pairs[str(pair["task_id"])].append(pair)
    task_level = []
    for task_id, members in sorted(task_pairs.items()):
        task_level.append(
            {
                "task_id": task_id,
                **{
                    key: mean([float(item[key]) for item in members])
                    for key in (
                        "graph_added_chunk_count",
                        "graph_added_required_chunk_count",
                        "graph_added_required_fraction",
                        "graph_unique_requirement_gain",
                        "graph_requirement_loss",
                        "required_section_recall_delta",
                        "required_section_precision_delta",
                        "required_token_precision_delta",
                        "deterministic_score_delta",
                        "substantive_score_excluding_provenance_delta",
                    )
                },
                "task_category": members[0]["task_category"],
                "lexical_overlap_stratum": members[0]["lexical_overlap_stratum"],
                "multi_hop": members[0]["multi_hop"],
            }
        )
    uncertainty = {}
    for key in (
        "required_section_recall_delta",
        "required_section_precision_delta",
        "required_token_precision_delta",
        "deterministic_score_delta",
        "substantive_score_excluding_provenance_delta",
    ):
        values = [float(row[key]) for row in task_level]
        uncertainty[key] = {
            "mean": mean(values),
            "bootstrap_95_ci": _bootstrap_mean_ci(values, seed=20260725 + len(key)),
            "loo": _loo_summary(values),
        }
    conditional = Counter(
        f"evidence_{row['evidence_state']}__output_{row['output_state']}"
        for row in pairs
    )
    edge_effects: dict[str, dict[str, Any]] = {}
    for label in sorted({str(row["route_label"]) for row in edge_rows}):
        members = [row for row in edge_rows if row["route_label"] == label]
        edge_effects[label] = {
            "graph_added_chunk_count": len(members),
            "required_chunk_count": sum(bool(row["required"]) for row in members),
            "required_fraction": mean(
                [float(bool(row["required"])) for row in members]
            ),
            "mean_associated_output_delta": mean(
                [float(row["deterministic_score_delta"]) for row in members]
            ),
            "association_not_causal": True,
        }
    return {
        "pair_count": len(pairs),
        "pairs": pairs,
        "task_level": task_level,
        "conditional_evidence_output_table": dict(sorted(conditional.items())),
        "uncertainty": uncertainty,
        "edge_route_associations": edge_effects,
    }


def _group_decomposition(
    *,
    criterion_records: Sequence[Mapping[str, Any]],
    error_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    task_confusion: dict[str, Any] = {}
    for task_id in sorted({str(row["task_id"]) for row in criterion_records}):
        task_confusion[task_id] = confusion_counts(
            [row for row in criterion_records if row["task_id"] == task_id]
        )
    criterion_confusion: dict[str, Any] = {}
    criterion_keys = sorted(
        {(str(row["task_id"]), str(row["criterion_id"])) for row in criterion_records}
    )
    for task_id, criterion_id in criterion_keys:
        key = f"{task_id}::{criterion_id}"
        criterion_confusion[key] = confusion_counts(
            [
                row
                for row in criterion_records
                if row["task_id"] == task_id and row["criterion_id"] == criterion_id
            ]
        )
    arm_error_counts: dict[str, dict[str, int]] = {}
    for arm in ARMS:
        counts = Counter(
            str(row["error_class"]) for row in error_rows if row["arm"] == arm
        )
        arm_error_counts[arm] = {
            error_class: counts.get(error_class, 0) for error_class in ERROR_CLASSES
        }
    return {
        "classes": list(ERROR_CLASSES),
        "decision_precedence": [
            "parse/schema failure",
            "forbidden hallucination",
            "required evidence absent",
            "stale/conflicting evidence selected",
            "citation mismatch",
            "schema/serialization criterion",
            "derivation criterion",
            "generator omission",
            "other derivation",
            "unresolved",
        ],
        "judge_disagreement_rule": (
            "deterministic score 1.0 with judge mean <3.0, or deterministic "
            "score 0.0 with judge mean >=4.0"
        ),
        "overall_confusion": confusion_counts(criterion_records),
        "task_level_confusion": task_confusion,
        "criterion_level_confusion": criterion_confusion,
        "arm_error_counts": arm_error_counts,
        "errors": list(error_rows),
    }


def _stratum_summary(
    task_arm_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    graph = {
        str(row["task_id"]): row
        for row in task_arm_rows
        if row["arm"] == "graph_bm25_chunk_optimized"
    }
    bm25 = {
        str(row["task_id"]): row
        for row in task_arm_rows
        if row["arm"] == "full_corpus_bm25_token_matched"
    }
    summaries: dict[str, Any] = {}
    strata: dict[str, tuple[str, Sequence[Any]]] = {
        "lexical_overlap": ("lexical_overlap_stratum", ["low", "middle", "high"]),
        "multi_hop": ("multi_hop", [False, True]),
        "task_category": (
            "task_category",
            sorted({str(row["task_category"]) for row in task_arm_rows}),
        ),
    }
    for family, (field, levels) in strata.items():
        summaries[family] = {}
        for level in levels:
            task_ids = sorted(
                task_id
                for task_id, row in graph.items()
                if row[field] == level and task_id in bm25
            )
            summaries[family][str(level).lower()] = {
                "task_count": len(task_ids),
                "graph_minus_bm25_recall": mean(
                    [
                        float(graph[task_id]["required_section_recall"])
                        - float(bm25[task_id]["required_section_recall"])
                        for task_id in task_ids
                    ]
                ),
                "graph_minus_bm25_output": mean(
                    [
                        float(graph[task_id]["deterministic_score"])
                        - float(bm25[task_id]["deterministic_score"])
                        for task_id in task_ids
                    ]
                ),
            }
    return summaries


def _graph_design_audit(
    *,
    root: Path,
    graph_data: Mapping[str, Any],
    cells: Sequence[Mapping[str, Any]],
    results: Sequence[Mapping[str, Any]],
    requirement_maps: Mapping[str, Mapping[str, Any]],
    graph_delta: Mapping[str, Any],
    aggregates: Mapping[str, Any],
    error_taxonomy: Mapping[str, Any],
) -> dict[str, Any]:
    router_source = (root / FROZEN_INPUTS["v7_router_source"]).read_text(
        encoding="utf-8"
    )
    edge_counts: Counter[str] = Counter()
    for node in graph_data.get("nodes", []):
        for dependency in node.get("dependencies", []):
            edge_counts[
                str(
                    dependency.get("edge_type", "untyped")
                    if isinstance(dependency, Mapping)
                    else "untyped"
                )
            ] += 1
    stage0 = json.loads(
        (root / FROZEN_INPUTS["stage0_diagnostics"]).read_text(encoding="utf-8")
    )
    selected_config = stage0["selected_config"]
    graph_results = [
        row for row in results if row["arm"] == "graph_bm25_chunk_optimized"
    ]
    selected_hop_counts: Counter[str] = Counter()
    required_selected_hop_counts: Counter[str] = Counter()
    selection_reason_counts: Counter[str] = Counter()
    selected_version_conflicts = 0
    selected_stale_chunks = 0
    for result in graph_results:
        requirements = requirement_maps[str(result["task_id"])]["task_requirements"]
        manifest = result["manifest"]
        selected_version_conflicts += len(manifest.get("version_conflicts", []))
        conflict_ids = {
            str(item.get("chunk_id"))
            for item in manifest.get("version_conflicts", [])
            if isinstance(item, Mapping)
        }
        selected_ids = {str(row.get("chunk_id")) for row in manifest["selected_chunks"]}
        selected_stale_chunks += len(selected_ids & conflict_ids)
        for row in manifest["selected_chunks"]:
            hop = row.get("dependency_hops")
            hop_label = "none" if hop is None else str(int(hop))
            selected_hop_counts[hop_label] += 1
            selection_reason_counts[str(row.get("selection_reason"))] += 1
            if any(
                requirement_matches_chunk(requirement, row)
                for requirement in requirements
            ):
                required_selected_hop_counts[hop_label] += 1
    required_route_counts: Counter[str] = Counter()
    for cell in cells:
        if cell["arm"] != "graph_bm25_chunk_optimized":
            continue
        for route in cell["required_route_labels"]:
            required_route_counts[str(route)] += 1
    primary_arm_error_counts: Counter[str] = Counter()
    for arm in (
        "graph_bm25_chunk_optimized",
        "full_corpus_bm25_token_matched",
    ):
        primary_arm_error_counts.update(error_taxonomy["arm_error_counts"][arm])
    bm25 = aggregates["full_corpus_bm25_token_matched"]
    unique_gain = mean(
        [
            float(row["graph_unique_requirement_gain"])
            for row in graph_delta["task_level"]
        ]
    )
    added_required_fraction = mean(
        [
            float(row["graph_added_required_fraction"])
            for row in graph_delta["task_level"]
        ]
    )
    evidence_present_output_failures = sum(
        primary_arm_error_counts[name]
        for name in (
            "evidence_present_generator_omission",
            "derivation_error",
            "schema_or_serialization_error",
            "forbidden_hallucination",
            "citation_mismatch",
        )
    )
    retrieval_failures = (
        primary_arm_error_counts["retrieval_miss"]
        + primary_arm_error_counts["wrong_or_stale_evidence"]
    )
    graph_aggregate = aggregates["graph_bm25_chunk_optimized"]
    diagnosis = {
        "bm25_retrieval_ceiling_supported": (
            float(bm25["required_section_recall"]) >= 0.95
            and float(bm25["bm25_recall_ceiling_fraction"]) >= 0.90
        ),
        "graph_semantic_mismatch_supported": (
            added_required_fraction < 0.25 or unique_gain < 0.05
        ),
        "graph_context_dilution_observed_descriptively": (
            float(graph_aggregate["required_token_precision"])
            < float(bm25["required_token_precision"])
            and float(graph_aggregate["irrelevant_token_ratio"])
            > float(bm25["irrelevant_token_ratio"])
        ),
        "downstream_generation_or_validation_bottleneck_supported": (
            evidence_present_output_failures > retrieval_failures
        ),
        "evidence_present_output_failure_count_graph_plus_bm25": (
            evidence_present_output_failures
        ),
        "retrieval_or_stale_failure_count_graph_plus_bm25": retrieval_failures,
        "bottleneck_judgment": (
            "The held-out benchmark has a BM25 retrieval ceiling and the current "
            "graph selection adds no registry-required evidence. Conditional on "
            "the declared evidence map, downstream generation/derivation/"
            "serialization/citation failures dominate retrieval failures. The "
            "current graph construction and selection policy remain semantically "
            "under-identified because edge types are not used and the benchmark "
            "mostly asks for current-node evidence."
        ),
        "thresholds_are_diagnostic_not_preregistered_superiority_tests": True,
    }
    return {
        "graph_edge_type_counts": dict(sorted(edge_counts.items())),
        "router_uses_edge_type_in_dependency_distance": (
            "edge_type"
            in router_source[
                router_source.find("def dependency_distances") : router_source.find(
                    "def dependency_multiplier"
                )
            ]
        ),
        "router_traverses_predecessors_and_successors_symmetrically": (
            "self.predecessors.get(current_node, set())" in router_source
            and "self.successors.get(current_node, set())" in router_source
        ),
        "workflow_adjacency_treated_as_evidence_dependency": True,
        "required_route_counts": dict(sorted(required_route_counts.items())),
        "selected_chunk_hop_counts": dict(sorted(selected_hop_counts.items())),
        "required_selected_chunk_hop_counts": dict(
            sorted(required_selected_hop_counts.items())
        ),
        "selection_reason_counts": dict(sorted(selection_reason_counts.items())),
        "current_floor_selection_reason_is_conflated_with_graph_mmr": True,
        "current_floor_tokens": selected_config["current_service_floor_tokens"],
        "two_hop_penalty": selected_config["two_hop_penalty"],
        "score_gap_ratio": selected_config["score_gap_ratio"],
        "mmr_lambda": selected_config["mmr_lambda"],
        "version_conflict_policy": "exclude candidates with unpinned versions",
        "version_conflict_records_graph_arm": selected_version_conflicts,
        "stale_chunks_selected_graph_arm": selected_stale_chunks,
        "stage0_development_diagnostics": stage0["selected_diagnostics"]["aggregate"],
        "heldout_graph_diagnostics": {
            key: graph_aggregate[key]
            for key in (
                "required_section_recall",
                "required_section_precision",
                "required_token_precision",
                "irrelevant_token_ratio",
                "redundancy",
            )
        },
        "benchmark_current_node_requirement_task_count": sum(
            all(route == "current_node" for route in cell["required_route_labels"])
            for cell in cells
            if cell["arm"] == "graph_bm25_chunk_optimized" and cell["run_id"] == 0
        ),
        "benchmark_multihop_requirement_task_count": sum(
            bool(cell["multi_hop"])
            for cell in cells
            if cell["arm"] == "graph_bm25_chunk_optimized" and cell["run_id"] == 0
        ),
        "graph_only_arm_present": False,
        "diagnosis": diagnosis,
        "future_proposals_not_evaluated": [
            "typed-edge RWR/PPR",
            "submodular or knapsack context selection",
            "Steiner-style evidence subgraph selection",
            "hybrid sparse+dense retrieval",
        ],
    }


def build_payload(root: Path = ROOT) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Build the complete in-memory decomposition payload."""
    input_hashes = {}
    for role, relative in FROZEN_INPUTS.items():
        path = root / relative
        input_hashes[role] = {
            "path": relative,
            "sha256": sha256_file(path),
            "bytes": path.stat().st_size,
        }
    if input_hashes["v6_judged_baseline"]["sha256"] != EXPECTED_V6_SHA256:
        raise ValueError("Frozen V6 judged baseline hash mismatch")

    final_freeze = json.loads(
        (root / FROZEN_INPUTS["final_freeze"]).read_text(encoding="utf-8")
    )
    freeze_contract_audit, freeze_failures = _audit_final_freeze(
        root=root,
        final_freeze=final_freeze,
    )
    registry = yaml.safe_load(
        (root / FROZEN_INPUTS["task_registry"]).read_text(encoding="utf-8")
    )
    tasks = list(registry["heldout_tasks"])
    tasks_by_id = {str(task["task_id"]): task for task in tasks}
    requirement_maps = {
        task_id: extract_task_requirements(task)
        for task_id, task in tasks_by_id.items()
    }
    evaluated = json.loads(
        (root / FROZEN_INPUTS["formal_evaluated"]).read_text(encoding="utf-8")
    )
    formal_generation = json.loads(
        (root / FROZEN_INPUTS["formal_generation"]).read_text(encoding="utf-8")
    )
    frozen_analysis = json.loads(
        (root / FROZEN_INPUTS["frozen_analysis"]).read_text(encoding="utf-8")
    )
    results = list(evaluated["results"])
    generation_evaluation_linkage, linkage_failures = (
        _audit_generation_evaluation_linkage(
            generation_rows=list(formal_generation["results"]),
            evaluation_rows=results,
        )
    )
    corpus = build_chunk_corpus(root)
    fragments, manifest_failures = _validate_manifest_rows(
        rows=results,
        corpus=corpus,
    )
    failures = sorted(
        [*freeze_failures, *linkage_failures, *manifest_failures],
        key=lambda row: (
            str(row.get("code")),
            str(row.get("field", "")),
            str(row.get("role", "")),
            str(row.get("path", "")),
            str(row.get("run_key", "")),
            str(row.get("chunk_id", "")),
        ),
    )
    graph_data = yaml.safe_load(
        (root / FROZEN_INPUTS["graph"]).read_text(encoding="utf-8")
    )
    graph_index = build_graph_index(graph_data, corpus)
    task_metadata = _task_metadata(
        tasks=tasks,
        requirement_maps=requirement_maps,
        corpus=corpus,
        graph_index=graph_index,
    )
    cells, criterion_records, error_rows = _build_cells(
        results=results,
        tasks_by_id=tasks_by_id,
        requirement_maps=requirement_maps,
        task_metadata=task_metadata,
        fragments=fragments,
    )
    aggregates = _aggregate_cells(cells)
    task_arm_rows = _task_arm_means(cells)
    graph_delta = _graph_deltas(
        cells=cells,
        results=results,
        requirement_maps=requirement_maps,
        task_metadata=task_metadata,
    )
    error_taxonomy = _group_decomposition(
        criterion_records=criterion_records,
        error_rows=error_rows,
    )
    stratum_summary = _stratum_summary(task_arm_rows)
    graph_design_audit = _graph_design_audit(
        root=root,
        graph_data=graph_data,
        cells=cells,
        results=results,
        requirement_maps=requirement_maps,
        graph_delta=graph_delta,
        aggregates=aggregates,
        error_taxonomy=error_taxonomy,
    )
    public_task_metadata = {
        task_id: {
            key: value for key, value in metadata.items() if not key.startswith("_")
        }
        for task_id, metadata in sorted(task_metadata.items())
    }
    payload = {
        "schema_version": "v7-oracle-decomposition-1",
        "analysis_date": "2026-07-25",
        "analysis_mode": "fully_offline_no_generation_no_judging",
        "claim_boundaries": {
            "graph_superiority_established": False,
            "cross_version_means_compared": False,
            "operational_gxp_compliance_claimed": False,
            "fda_guidance_conformance_claimed": False,
            "human_time_reduction_claimed": False,
            "regulatory_outcome_improvement_claimed": False,
            "paid_generation_started": False,
            "allowed_design_characterization": (
                "GxP-oriented, audit-supporting, human-overseen"
            ),
        },
        "panel": {
            "task_count": len(tasks),
            "arm_count": len(ARMS),
            "repetitions_per_task_arm": 3,
            "cell_count": len(cells),
            "criterion_record_count": len(criterion_records),
        },
        "frozen_primary_result": {
            "arm_means": frozen_analysis["primary_arm_means"],
            "graph_minus_bm25": frozen_analysis["primary_contrasts"][0],
            "decision": frozen_analysis["decision"],
        },
        "input_hashes": input_hashes,
        "freeze_contract_audit": freeze_contract_audit,
        "generation_evaluation_linkage_audit": (generation_evaluation_linkage),
        "requirement_mapping": {
            "basis": "registry_provenance_requirement_union",
            "limitation": (
                "The frozen registry supplies task-level provenance sections; "
                "the same declared section union is conservatively mapped to "
                "each atomic criterion because no finer criterion-to-section "
                "field exists."
            ),
            "tasks": requirement_maps,
        },
        "task_metadata": public_task_metadata,
        "cells": cells,
        "task_arm_means": task_arm_rows,
        "arm_aggregates": aggregates,
        "graph_vs_bm25_oracle_delta": graph_delta,
        "error_taxonomy": error_taxonomy,
        "strata": stratum_summary,
        "graph_design_audit": graph_design_audit,
        "future_experiment_go_no_go": {
            "decision": "no_go_for_immediate_paid_generation",
            "reason": (
                "The offline oracle is sufficient to diagnose the current null "
                "as a registry-declared BM25 retrieval ceiling plus downstream "
                "output failures, with a semantically under-identified graph."
            ),
            "unresolved_causal_question": (
                "V7 cannot isolate graph-only retrieval value because it has no "
                "graph-only arm and no graph/BM25 pair with improved required-"
                "section recall."
            ),
            "conditional_protocol": {
                "design": "2x2 graph on/off x BM25 retrieval on/off",
                "population": (
                    "new external held-out tasks enriched for preregistered "
                    "cross-node, low-overlap, and version-conflict dependencies"
                ),
                "fixed_controls": [
                    "immutable external corpus and task registry",
                    "identical generator and validator versions",
                    "identical token budgets and context serialization",
                    "task as the independent analysis unit",
                    "no formal-score router tuning",
                ],
                "primary_endpoint": (
                    "oracle unique required-evidence gain at matched token budget"
                ),
                "secondary_endpoints": [
                    "deterministic criterion realization conditional on evidence",
                    "irrelevant-token ratio and redundancy",
                    "version/conflict correctness and citation correctness",
                ],
                "automatic_start_authorized": False,
            },
        },
        "failure_summary": {
            "count": len(failures),
            "error_count": sum(1 for row in failures if row.get("severity") == "error"),
        },
    }
    return payload, failures


def write_analysis(
    *,
    root: Path = ROOT,
    output_dir: Path = DEFAULT_OUTPUT,
) -> dict[str, Any]:
    """Write canonical machine-readable artifacts and delegated reports."""
    from experiments.v7_oracle_reporting import write_reports

    payload, failures = build_payload(root)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "oracle_decomposition.json").write_bytes(
        canonical_json_bytes(payload)
    )
    (output_dir / "input_hashes.json").write_bytes(
        canonical_json_bytes(payload["input_hashes"])
    )
    (output_dir / "failure_log.json").write_bytes(
        canonical_json_bytes(
            {
                "schema_version": "v7-oracle-failure-log-1",
                "failures": failures,
            }
        )
    )
    write_reports(payload=payload, output_dir=output_dir)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    write_analysis(root=args.root.resolve(), output_dir=args.output_dir.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
