"""Offline corpus, retrieval, and immutable-baseline diagnostics for V7."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

from experiments.v7_deterministic_eval import validate_holdout_isolation
from experiments.v7_routing import (
    RoutingConfig,
    RoutingCorpus,
    TaskRoutingRequest,
    validate_context_manifest_v7,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TASKS = (
    PROJECT_ROOT
    / "experiments"
    / "config"
    / "experiment_v7_routing_sensitive_tasks_20260725.yaml"
)
DEFAULT_V6 = (
    PROJECT_ROOT
    / "experiments"
    / "results"
    / "experiment_v6_aps_gxp_formal_20260724_judged.json"
)
DEFAULT_OUTPUT = (
    PROJECT_ROOT
    / "experiments"
    / "results"
    / "experiment_v7_routing_sensitive_stage0_20260725.json"
)
EXPECTED_V6_SHA256 = (
    "fb9f787a6e95e2bd0813c7f7b90fd986e64adeba09305645572a3875df927aa0"
)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _atomic_json_write(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(
            payload,
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def load_task_registry(path: Path) -> dict[str, Any]:
    """Load and validate the isolated development/smoke/held-out registry."""
    registry = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(registry, Mapping):
        raise ValueError("V7 task registry must be an object")
    result = dict(registry)
    for panel in ("development_tasks", "smoke_tasks", "heldout_tasks"):
        tasks = result.get(panel)
        if not isinstance(tasks, list) or not tasks:
            raise ValueError(f"{panel} must be a non-empty list")
        identifiers = [task.get("task_id") for task in tasks]
        if not all(isinstance(item, str) and item for item in identifiers):
            raise ValueError(f"{panel} contains an invalid task_id")
        if len(identifiers) != len(set(identifiers)):
            raise ValueError(f"{panel} contains duplicate task IDs")
    if not 20 <= len(result["heldout_tasks"]) <= 24:
        raise ValueError("V7 requires 20-24 independent held-out tasks")
    result["holdout_isolation"] = validate_holdout_isolation(
        result["development_tasks"],
        result["heldout_tasks"],
    )
    return result


def audit_v6_baseline(path: Path) -> dict[str, Any]:
    """Verify the immutable V6 reference without modifying it."""
    path = Path(path)
    sha256 = _sha256_file(path)
    if sha256 != EXPECTED_V6_SHA256:
        raise ValueError(f"V6 immutable SHA-256 mismatch: {sha256}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("results", [])
    if not isinstance(rows, list):
        raise ValueError("V6 results are not a list")
    task_ids = sorted({str(row.get("task_id")) for row in rows})
    arms = sorted({str(row.get("arm")) for row in rows})
    run_ids = sorted({int(row.get("run_id")) for row in rows})
    arm_means = {}
    for arm in arms:
        values = [
            float(row["quality_score"])
            for row in rows
            if row.get("arm") == arm
        ]
        arm_means[arm] = round(statistics.fmean(values), 10)
    required_v7_accounting = {
        "cache_read_tokens",
        "cache_creation_tokens",
        "serialized_prompt_characters",
        "serialized_prompt_bytes",
        "canonical_prompt_tokens",
    }
    observed_fields = set().union(
        *(set(row) for row in rows)
    ) if rows else set()
    return {
        "path": path.relative_to(PROJECT_ROOT).as_posix(),
        "sha256": sha256,
        "row_count": len(rows),
        "task_count": len(task_ids),
        "arm_count": len(arms),
        "runs_per_cell": len(run_ids),
        "arms": arms,
        "arm_means": arm_means,
        "generation_failure_count": len(
            payload.get("failed_generation_attempts", [])
        ),
        "v7_accounting_fields_missing": sorted(
            required_v7_accounting - observed_fields
        ),
        "immutable_verified": (
            len(rows) == 120
            and len(task_ids) == 10
            and len(arms) == 4
            and run_ids == [0, 1, 2]
        ),
    }


def _matches_requirement(
    row: Mapping[str, Any], requirement: Mapping[str, Any]
) -> bool:
    return (
        row.get("skill_name") == requirement.get("skill_name")
        and str(requirement.get("heading_contains", "")).lower()
        in str(row.get("heading_path", "")).lower()
    )


def _mean(values: Sequence[float]) -> float:
    return statistics.fmean(values) if values else 0.0


def retrieval_diagnostics(
    corpus: RoutingCorpus,
    development_tasks: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Measure retrieval only; no generated response or judge score is accepted."""
    per_task: list[dict[str, Any]] = []
    manifests: list[dict[str, Any]] = []
    for task in development_tasks:
        request = TaskRoutingRequest(
            task_id=str(task["task_id"]),
            node_id=str(task["node_id"]),
            query=str(task["prompt"]),
            version_pins=dict(task.get("version_pins", {})),
        )
        built = corpus.build_context(
            request,
            "graph_bm25_chunk_optimized",
            run_id=0,
        )
        manifest = built.manifest
        manifests.append(manifest)
        selected = manifest["selected_chunks"]
        requirements = list(task.get("required_evidence", []))
        requirement_hits = [
            any(_matches_requirement(row, requirement) for row in selected)
            for requirement in requirements
        ]
        relevant_rows = [
            row
            for row in selected
            if any(
                _matches_requirement(row, requirement)
                for requirement in requirements
            )
        ]
        selected_tokens = sum(
            int(row["injected_canonical_tokens_with_header"])
            for row in selected
        )
        relevant_tokens = sum(
            int(row["injected_canonical_tokens_with_header"])
            for row in relevant_rows
        )
        distances = corpus.dependency_distances(request.node_id, max_hops=2)
        dependency_hits = [
            requirement.get("skill_name") in distances
            for requirement in requirements
        ]
        chunk_pairs: list[float] = []
        selected_chunks = [
            corpus.chunk_by_id[row["chunk_id"]]
            for row in selected
            if row["chunk_id"] in corpus.chunk_by_id
        ]
        for left_index, left in enumerate(selected_chunks):
            for right in selected_chunks[left_index + 1 :]:
                chunk_pairs.append(corpus._jaccard(left, right))
        manifest_errors = validate_context_manifest_v7(manifest)
        provenance_complete = not manifest_errors and all(
            row.get("chunk_id")
            and row.get("source_sha256")
            and row.get("content_sha256")
            and row.get("injected_fragment_sha256")
            for row in selected
        )
        per_task.append(
            {
                "task_id": task["task_id"],
                "required_evidence_count": len(requirements),
                "retrieved_required_evidence_count": sum(requirement_hits),
                "recall_at_k": (
                    sum(requirement_hits) / len(requirements)
                    if requirements
                    else 1.0
                ),
                "precision_at_k": (
                    len(relevant_rows) / len(selected) if selected else 0.0
                ),
                "dependency_coverage": (
                    sum(dependency_hits) / len(dependency_hits)
                    if dependency_hits
                    else 1.0
                ),
                "irrelevant_token_ratio": (
                    1.0 - relevant_tokens / selected_tokens
                    if selected_tokens
                    else 1.0
                ),
                "redundancy": _mean(chunk_pairs),
                "provenance_completeness": float(provenance_complete),
                "context_tokens": built.canonical_tokens,
                "selected_chunk_count": len(selected),
                "manifest_sha256": manifest["manifest_sha256"],
                "manifest_errors": manifest_errors,
            }
        )

    required_skills = sorted(
        {
            str(requirement["skill_name"])
            for task in development_tasks
            for requirement in task.get("required_evidence", [])
        }
    )
    impact_rows = []
    all_task_ids = {
        str(task["task_id"]) for task in development_tasks
    }
    for skill in required_skills:
        observed = corpus.change_impact_scope(
            manifests,
            changed_skill=skill,
        )
        required = sorted(
            str(task["task_id"])
            for task in development_tasks
            if any(
                requirement.get("skill_name") == skill
                for requirement in task.get("required_evidence", [])
            )
        )
        observed_affected = set(observed["affected_task_ids"])
        observed_unaffected = set(observed["unaffected_task_ids"])
        required_set = set(required)
        impact_rows.append(
            {
                "changed_skill": skill,
                "required_evidence_task_ids": required,
                "observed_affected_task_ids": observed["affected_task_ids"],
                "observed_unaffected_task_ids": observed[
                    "unaffected_task_ids"
                ],
                "required_recall": (
                    len(required_set & observed_affected) / len(required_set)
                    if required_set
                    else 1.0
                ),
                "scope_precision": (
                    len(required_set & observed_affected)
                    / len(observed_affected)
                    if observed_affected
                    else 1.0
                ),
                "partition_complete": (
                    observed_affected.isdisjoint(observed_unaffected)
                    and observed_affected | observed_unaffected == all_task_ids
                ),
            }
        )
    aggregate = {
        field: round(_mean([float(row[field]) for row in per_task]), 12)
        for field in (
            "recall_at_k",
            "precision_at_k",
            "dependency_coverage",
            "irrelevant_token_ratio",
            "redundancy",
            "provenance_completeness",
            "context_tokens",
        )
    }
    aggregate["mean_context_tokens"] = aggregate.pop("context_tokens")
    return {
        "aggregate": aggregate,
        "per_task": per_task,
        "change_impact": {
            "passed": all(
                row["required_recall"] == 1.0 and row["partition_complete"]
                for row in impact_rows
            ),
            "mean_scope_precision": round(
                _mean([row["scope_precision"] for row in impact_rows]), 12
            ),
            "per_skill": impact_rows,
        },
        "generation_or_judge_scores_used": False,
    }


def rank_development_configs(
    candidates: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Rank retrieval candidates lexicographically with recall as the guardrail."""

    forbidden = {"generation_score", "judge_score", "quality_score"}
    for candidate in candidates:
        if forbidden & set(candidate):
            raise ValueError("Generation/judge scores cannot tune V7 retrieval")

    def key(candidate: Mapping[str, Any]) -> tuple[Any, ...]:
        aggregate = candidate["aggregate"]
        return (
            -float(aggregate["recall_at_k"]),
            -float(aggregate["dependency_coverage"]),
            -float(aggregate["provenance_completeness"]),
            -float(aggregate["precision_at_k"]),
            float(aggregate["irrelevant_token_ratio"]),
            float(aggregate["redundancy"]),
            float(aggregate["mean_context_tokens"]),
            json.dumps(candidate["config"], sort_keys=True),
        )

    return [dict(candidate) for candidate in sorted(candidates, key=key)]


def _corpus_audit(skill_root: Path) -> dict[str, Any]:
    audited = {
        "adam-adsl-builder": [
            "standard treatment variables and inclusive duration",
            "SAP-driven population flags",
            "partial-date fail-closed behavior",
        ],
        "p21-validator": [
            "versioned finding identity",
            "no fabricated stable rule IDs",
            "internal QC evidence rather than compliance certification",
        ],
        "define-xml-builder": [
            "ODM/Define namespaces and version pins",
            "MethodDef plus ItemRef MethodOID",
            "Description/TranslatedText labels and ValueListRef",
        ],
        "define-xml-validator": [
            "MethodDef cross-reference validation",
            "forbidden invented method vocabulary",
        ],
        "sdtm-dm-mapper": [
            "sponsor-defined USUBJID length",
            "no-day-zero study day",
            "partial birth date behavior",
        ],
        "sdtm-ae-mapper": [
            "partial AE dates",
            "pinned MedDRA package",
            "treatment-emergence deferred to ADAE",
        ],
        "tfl-table-generator": [
            "distinct-subject incidence",
            "population denominator",
            "event-count separation and change impact",
        ],
        "tfl-demographics": [
            "SAP/shell population denominator",
            "validated ADSL AGE reuse",
            "change propagation",
        ],
        "tfl-qc-validator": [
            "structured/data QC primary",
            "rendering diff secondary",
            "provenance-complete change containment",
        ],
    }
    rows = []
    for skill_name, corrections in audited.items():
        matches = sorted(skill_root.rglob(f"{skill_name}/SKILL.md"))
        if len(matches) != 1:
            raise ValueError(
                f"Expected exactly one audited source for {skill_name}: {matches}"
            )
        path = matches[0]
        rows.append(
            {
                "skill_name": skill_name,
                "path": path.relative_to(PROJECT_ROOT).as_posix(),
                "sha256": _sha256_file(path),
                "corrections": corrections,
            }
        )
    return {
        "audited_skill_count": len(rows),
        "skills": rows,
        "operational_compliance_claimed": False,
    }


def run_stage0(
    *,
    tasks_path: Path = DEFAULT_TASKS,
    output_path: Path = DEFAULT_OUTPUT,
) -> dict[str, Any]:
    registry = load_task_registry(tasks_path)
    base = RoutingConfig()
    base_corpus = RoutingCorpus.from_paths(
        PROJECT_ROOT / "csp-skills",
        PROJECT_ROOT / "graph" / "regulatory-graph.yaml",
        base,
    )
    candidates: list[dict[str, Any]] = []
    for top_k in (8, 12, 16):
        for score_gap_ratio in (0.35, 0.65, 1.0):
            for mmr_lambda in (0.68, 0.78, 0.88):
                config = replace(
                    base,
                    top_k=top_k,
                    score_gap_ratio=score_gap_ratio,
                    mmr_lambda=mmr_lambda,
                )
                corpus = RoutingCorpus(
                    chunks=base_corpus.chunks,
                    graph_data=base_corpus.graph_data,
                    graph_sha256=base_corpus.graph_sha256,
                    config=config,
                )
                diagnostics = retrieval_diagnostics(
                    corpus,
                    registry["development_tasks"],
                )
                candidates.append(
                    {
                        "config": asdict(config),
                        "aggregate": diagnostics["aggregate"],
                        "change_impact_passed": diagnostics["change_impact"][
                            "passed"
                        ],
                    }
                )
    ranked = rank_development_configs(candidates)
    selected_config = RoutingConfig(**ranked[0]["config"])
    selected_corpus = RoutingCorpus(
        chunks=base_corpus.chunks,
        graph_data=base_corpus.graph_data,
        graph_sha256=base_corpus.graph_sha256,
        config=selected_config,
    )
    selected_diagnostics = retrieval_diagnostics(
        selected_corpus,
        registry["development_tasks"],
    )
    report = {
        "schema_version": "v7-stage0-offline-diagnostics-1",
        "completed_at": "2026-07-25",
        "network_calls": 0,
        "paid_calls": 0,
        "v6_immutable_audit": audit_v6_baseline(DEFAULT_V6),
        "task_registry": {
            "path": tasks_path.relative_to(PROJECT_ROOT).as_posix(),
            "sha256": _sha256_file(tasks_path),
            "development_count": len(registry["development_tasks"]),
            "smoke_count": len(registry["smoke_tasks"]),
            "heldout_count": len(registry["heldout_tasks"]),
            "holdout_isolation": registry["holdout_isolation"],
        },
        "corpus_audit": _corpus_audit(PROJECT_ROOT / "csp-skills"),
        "tuning_policy": {
            "development_retrieval_diagnostics_only": True,
            "generation_or_judge_scores_used": False,
            "candidate_count": len(ranked),
            "ranking_order": [
                "recall_at_k",
                "dependency_coverage",
                "provenance_completeness",
                "precision_at_k",
                "irrelevant_token_ratio",
                "redundancy",
                "mean_context_tokens",
            ],
        },
        "selected_config": asdict(selected_config),
        "selected_config_sha256": selected_corpus.config_sha256,
        "selected_diagnostics": selected_diagnostics,
        "candidate_diagnostics": ranked,
    }
    _atomic_json_write(output_path, report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tasks", type=Path, default=DEFAULT_TASKS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    report = run_stage0(tasks_path=args.tasks, output_path=args.output)
    print(
        json.dumps(
            {
                "output": str(args.output),
                "selected_config_sha256": report["selected_config_sha256"],
                "aggregate": report["selected_diagnostics"]["aggregate"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
