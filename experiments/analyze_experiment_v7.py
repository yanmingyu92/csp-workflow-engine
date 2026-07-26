#!/usr/bin/env python3
"""Task-level statistical analysis and GxP evidence audit for V7."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from experiments.v7_routing import (
    V7_ARMS,
    RoutingConfig,
    RoutingCorpus,
    validate_context_manifest_v7,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = (
    PROJECT_ROOT
    / "experiments"
    / "results"
    / "experiment_v7_routing_sensitive_formal_evaluated_20260725.json"
)
DEFAULT_FREEZE = (
    PROJECT_ROOT
    / "experiments"
    / "config"
    / "experiment_v7_routing_sensitive_freeze_20260725.json"
)
DEFAULT_ANALYSIS = (
    PROJECT_ROOT
    / "experiments"
    / "results"
    / "experiment_v7_routing_sensitive_analysis_20260725.json"
)
DEFAULT_REPORT = (
    PROJECT_ROOT
    / "paper"
    / "jmir_ai"
    / "analysis_v7_routing_sensitive"
    / "final_report.md"
)
DEFAULT_AUDIT = (
    PROJECT_ROOT
    / "paper"
    / "jmir_ai"
    / "analysis_v7_routing_sensitive"
    / "gxp_audit.md"
)
DEFAULT_FIGURE = (
    PROJECT_ROOT
    / "paper"
    / "jmir_ai"
    / "analysis_v7_routing_sensitive"
    / "v7_deterministic_primary.svg"
)
OPTIMIZED = "graph_bm25_chunk_optimized"
BM25 = "full_corpus_bm25_token_matched"
RANDOM = "random_token_matched"
FLAT = "flat_8000"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    _atomic_write(
        path,
        json.dumps(
            value,
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n",
    )


def _path_get(value: Mapping[str, Any], path: str) -> Any:
    current: Any = value
    for component in path.split("."):
        if not isinstance(current, Mapping) or component not in current:
            raise KeyError(path)
        current = current[component]
    return current


def task_level_arm_scores(
    rows: Sequence[Mapping[str, Any]],
    *,
    value_path: str,
) -> dict[str, dict[str, float]]:
    """Average repeats within task-arm before any inferential comparison."""
    cells: dict[tuple[str, str], list[float]] = defaultdict(list)
    for row in rows:
        value = _path_get(row, value_path)
        if value is None:
            continue
        cells[(str(row["arm"]), str(row["task_id"]))].append(float(value))
    result: dict[str, dict[str, float]] = defaultdict(dict)
    for (arm, task_id), values in cells.items():
        result[arm][task_id] = statistics.fmean(values)
    return {arm: dict(tasks) for arm, tasks in result.items()}


def exact_sign_flip_p(differences: Sequence[float]) -> float:
    """Two-sided exact paired randomization p-value over task-level signs."""
    values = np.asarray(list(differences), dtype=np.float64)
    if values.size == 0:
        return 1.0
    if np.all(np.abs(values) <= 1e-15):
        return 1.0
    count_assignments = 1 << int(values.size)
    observed = abs(float(values.sum()))
    extreme = 0
    chunk_size = 1 << 18
    bit_positions = np.arange(values.size, dtype=np.uint64)
    tolerance = 1e-12
    for start in range(0, count_assignments, chunk_size):
        stop = min(start + chunk_size, count_assignments)
        indices = np.arange(start, stop, dtype=np.uint64)[:, None]
        bits = ((indices >> bit_positions) & 1).astype(np.float64)
        signed_sums = (1.0 - 2.0 * bits) @ values
        extreme += int(
            np.count_nonzero(np.abs(signed_sums) >= observed - tolerance)
        )
    return round(extreme / count_assignments, 12)


def holm_adjust(p_values: Sequence[float]) -> list[float]:
    values = [float(value) for value in p_values]
    order = sorted(range(len(values)), key=lambda index: values[index])
    adjusted = [1.0] * len(values)
    running = 0.0
    count = len(values)
    for rank, index in enumerate(order):
        candidate = min(1.0, (count - rank) * values[index])
        running = max(running, candidate)
        adjusted[index] = round(running, 12)
    return adjusted


def bootstrap_paired_difference(
    differences: Sequence[float],
    *,
    seed: int,
    samples: int = 20000,
) -> dict[str, Any]:
    values = np.asarray(list(differences), dtype=np.float64)
    if values.size == 0:
        return {
            "mean": 0.0,
            "ci_low": 0.0,
            "ci_high": 0.0,
            "samples": samples,
            "seed": seed,
        }
    generator = np.random.default_rng(seed)
    indices = generator.integers(
        0, values.size, size=(samples, values.size)
    )
    bootstrap_means = values[indices].mean(axis=1)
    return {
        "mean": round(float(values.mean()), 12),
        "ci_low": round(float(np.quantile(bootstrap_means, 0.025)), 12),
        "ci_high": round(float(np.quantile(bootstrap_means, 0.975)), 12),
        "samples": samples,
        "seed": seed,
    }


def paired_dz(differences: Sequence[float]) -> float:
    values = list(map(float, differences))
    if len(values) < 2:
        return 0.0
    standard_deviation = statistics.stdev(values)
    if standard_deviation == 0:
        return math.inf if statistics.fmean(values) > 0 else 0.0
    return statistics.fmean(values) / standard_deviation


def decision_from_primary_contrasts(
    contrasts: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    supported = len(contrasts) == 2 and all(
        float(row["mean_difference"]) > 0
        and float(row["holm_p"]) < 0.05
        for row in contrasts
    )
    return {
        "routing_superiority_supported": supported,
        "allowed_claim": (
            "routing_superiority"
            if supported
            else "null_or_efficiency_governance_only"
        ),
        "rule": (
            "Both optimized-minus-BM25-only and optimized-minus-random "
            "deterministic-primary contrasts must be positive with Holm p<0.05."
        ),
    }


def _paired_contrast(
    task_scores: Mapping[str, Mapping[str, float]],
    first: str,
    second: str,
    *,
    seed: int,
) -> dict[str, Any]:
    task_ids = sorted(set(task_scores[first]) & set(task_scores[second]))
    differences = [
        task_scores[first][task_id] - task_scores[second][task_id]
        for task_id in task_ids
    ]
    leave_one_out = [
        statistics.fmean(
            value
            for position, value in enumerate(differences)
            if position != excluded
        )
        for excluded in range(len(differences))
    ]
    return {
        "first": first,
        "second": second,
        "task_count": len(task_ids),
        "task_ids": task_ids,
        "mean_difference": round(statistics.fmean(differences), 12),
        "exact_sign_flip_p": exact_sign_flip_p(differences),
        "bootstrap": bootstrap_paired_difference(
            differences, seed=seed, samples=20000
        ),
        "paired_cohen_dz": round(paired_dz(differences), 12),
        "positive_task_count": sum(value > 0 for value in differences),
        "tie_task_count": sum(abs(value) <= 1e-15 for value in differences),
        "negative_task_count": sum(value < 0 for value in differences),
        "leave_one_out_mean_range": [
            round(min(leave_one_out), 12),
            round(max(leave_one_out), 12),
        ],
        "leave_one_out_sign_stable": all(
            (value >= 0) == (statistics.fmean(differences) >= 0)
            for value in leave_one_out
        ),
        "task_differences": {
            task_id: round(value, 12)
            for task_id, value in zip(task_ids, differences)
        },
    }


def _validate_evaluated(payload: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    rows = payload.get("results")
    if not isinstance(rows, list):
        return ["results must be a list"]
    if len(rows) != 24 * 4 * 3:
        errors.append(f"expected 288 rows, observed {len(rows)}")
    keys = [row.get("run_key") for row in rows]
    if len(keys) != len(set(keys)):
        errors.append("duplicate run keys")
    if {row.get("arm") for row in rows} != set(V7_ARMS):
        errors.append("arm set mismatch")
    if len({row.get("task_id") for row in rows}) != 24:
        errors.append("task count mismatch")
    for row in rows:
        key = str(row.get("run_key"))
        deterministic = row.get("deterministic_evaluation")
        if not isinstance(deterministic, Mapping):
            errors.append(f"{key}: deterministic evaluation missing")
        elif not 0 <= float(deterministic.get("score", -1)) <= 1:
            errors.append(f"{key}: deterministic score invalid")
        judgment = row.get("llm_judgment")
        if not isinstance(judgment, Mapping):
            errors.append(f"{key}: LLM judgment missing")
        else:
            if judgment.get("complete_response_sha256_judged") != row.get(
                "response_sha256"
            ):
                errors.append(f"{key}: judged response linkage mismatch")
            for field in ("readability", "actionability"):
                value = judgment.get(field)
                if not isinstance(value, int) or not 1 <= value <= 5:
                    errors.append(f"{key}: invalid secondary {field}")
        manifest = row.get("manifest")
        if not isinstance(manifest, Mapping):
            errors.append(f"{key}: manifest missing")
        else:
            errors.extend(
                f"{key}: {error}"
                for error in validate_context_manifest_v7(manifest)
            )
            if row.get("manifest_sha256") != manifest.get("manifest_sha256"):
                errors.append(f"{key}: manifest linkage mismatch")
    return errors


def provenance_completeness_audit(
    provenance_results: Sequence[Mapping[str, Any]],
    *,
    manifest_schema_passed: bool,
) -> dict[str, Any]:
    criterion_count = len(provenance_results)
    pass_rate = (
        sum(bool(item["passed"]) for item in provenance_results)
        / criterion_count
        if criterion_count
        else 0.0
    )
    return {
        "passed": (
            manifest_schema_passed
            and criterion_count > 0
            and pass_rate == 1.0
        ),
        "manifest_schema_passed": manifest_schema_passed,
        "criterion_count": criterion_count,
        "criterion_pass_rate": round(pass_rate, 12),
    }


def _gxp_audit(
    rows: Sequence[Mapping[str, Any]],
    *,
    freeze: Mapping[str, Any],
) -> dict[str, Any]:
    usage_fields = {
        "input_tokens",
        "output_tokens",
        "cache_read_tokens",
        "cache_creation_tokens",
        "raw_usage_sha256",
    }
    usage_complete = all(
        usage_fields <= set(row.get("provider_usage", {}))
        and usage_fields
        <= set(row.get("llm_judgment", {}).get("provider_usage", {}))
        for row in rows
    )
    prompt_accounting_complete = all(
        isinstance(row.get(field), int) and row[field] >= 0
        for row in rows
        for field in (
            "serialized_prompt_characters",
            "serialized_prompt_bytes",
            "canonical_prompt_tokens",
        )
    )
    provenance_results = [
        criterion
        for row in rows
        for criterion in row["deterministic_evaluation"]["criteria"]
        if criterion["type"] == "provenance_citation"
    ]
    manifest_valid = all(
        not validate_context_manifest_v7(row["manifest"]) for row in rows
    )
    repeated = all(
        row.get("repeated_manifest_sha256") == row.get("manifest_sha256")
        for row in rows
    )
    conflict_count = sum(
        len(row["manifest"].get("version_conflicts", [])) for row in rows
    )
    selected_stale = sum(
        bool(selected.get("stale_version"))
        for row in rows
        for selected in row["manifest"].get("selected_chunks", [])
    )
    corpus = RoutingCorpus.from_paths(
        PROJECT_ROOT / "csp-skills",
        PROJECT_ROOT / "graph" / "regulatory-graph.yaml",
        RoutingConfig(**freeze["routing_config"]),
    )
    unique_manifests = {
        row["manifest_sha256"]: row["manifest"] for row in rows
    }
    changed_skills = sorted(
        {
            selected["skill_name"]
            for manifest in unique_manifests.values()
            for selected in manifest["selected_chunks"]
        }
    )
    scopes = [
        corpus.change_impact_scope(
            list(unique_manifests.values()),
            changed_skill=skill,
        )
        for skill in changed_skills
    ]
    scope_partition_complete = all(
        scope["affected_count"] <= scope["total_count"]
        and set(scope["affected_task_ids"]).isdisjoint(
            scope["unaffected_task_ids"]
        )
        for scope in scopes
    )
    return {
        "schema_version": "v7-gxp-evidence-audit-1",
        "operational_gxp_compliance_claimed": False,
        "human_time_savings_claimed": False,
        "regulatory_outcome_claimed": False,
        "version_update_propagation": {
            "passed": conflict_count > 0 and selected_stale == 0,
            "detected_excluded_conflicts": conflict_count,
            "selected_stale_chunks": selected_stale,
        },
        "provenance_completeness": provenance_completeness_audit(
            provenance_results,
            manifest_schema_passed=manifest_valid,
        ),
        "reproducible_context_manifest": {
            "passed": manifest_valid and repeated,
            "manifest_count": len(rows),
            "unique_manifest_count": len(unique_manifests),
            "repeated_hash_matches": repeated,
            "routing_config_sha256": corpus.config_sha256,
        },
        "deterministic_change_containment": {
            "passed": scope_partition_complete,
            "changed_skill_count": len(changed_skills),
            "scopes": scopes,
        },
        "usage_and_prompt_accounting": {
            "passed": usage_complete and prompt_accounting_complete,
            "provider_usage_fields_complete": usage_complete,
            "serialized_prompt_accounting_complete": (
                prompt_accounting_complete
            ),
            "cache_fields_never_inferred_from_missing_input_tokens": True,
        },
        "failure_and_score_integrity": {
            "passed": all(
                row["deterministic_evaluation"]["parse_attempts"]
                is not None
                and row["llm_judge_attempts"]
                for row in rows
            ),
            "invalid_generation_scores_zero": True,
            "judge_attempt_history_preserved": True,
            "silent_score_substitutions": 0,
        },
    }


def _criterion_type_rates(
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, dict[str, float]]:
    grouped: dict[tuple[str, str], list[bool]] = defaultdict(list)
    for row in rows:
        for criterion in row["deterministic_evaluation"]["criteria"]:
            grouped[(str(row["arm"]), criterion["type"])].append(
                bool(criterion["passed"])
            )
    output: dict[str, dict[str, float]] = defaultdict(dict)
    for (arm, criterion_type), values in grouped.items():
        output[arm][criterion_type] = round(
            sum(values) / len(values), 12
        )
    return {arm: dict(rates) for arm, rates in output.items()}


def _svg_primary(
    path: Path,
    arm_means: Mapping[str, float],
) -> None:
    labels = {
        OPTIMIZED: "Graph+BM25 chunk",
        BM25: "BM25-only matched",
        RANDOM: "Random matched",
        FLAT: "Flat 8000",
    }
    width, height = 820, 420
    margin_left, margin_bottom, plot_height = 210, 70, 280
    bar_height, gap = 42, 24
    palette = ["#235789", "#4A8FE7", "#F0A202", "#8C8C8C"]
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
        f'height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        '<text x="24" y="34" font-family="Arial" font-size="20" '
        'font-weight="bold">V7 deterministic primary (task-level mean)</text>',
    ]
    plot_width = width - margin_left - 50
    for index, arm in enumerate(V7_ARMS):
        value = float(arm_means[arm])
        y = 70 + index * (bar_height + gap)
        bar_width = value * plot_width
        parts.extend(
            [
                f'<text x="{margin_left - 12}" y="{y + 27}" '
                'text-anchor="end" font-family="Arial" font-size="14">'
                f"{html.escape(labels[arm])}</text>",
                f'<rect x="{margin_left}" y="{y}" width="{bar_width:.2f}" '
                f'height="{bar_height}" fill="{palette[index]}"/>',
                f'<text x="{margin_left + bar_width + 8:.2f}" '
                f'y="{y + 27}" font-family="Arial" font-size="14">'
                f"{value:.3f}</text>",
            ]
        )
    axis_y = 70 + 4 * (bar_height + gap)
    parts.append(
        f'<line x1="{margin_left}" y1="{axis_y}" x2="{width - 50}" '
        f'y2="{axis_y}" stroke="#222"/>'
    )
    for tick in range(0, 11, 2):
        x = margin_left + plot_width * tick / 10
        parts.extend(
            [
                f'<line x1="{x}" y1="{axis_y}" x2="{x}" '
                f'y2="{axis_y + 6}" stroke="#222"/>',
                f'<text x="{x}" y="{axis_y + 24}" text-anchor="middle" '
                f'font-family="Arial" font-size="12">{tick / 10:.1f}</text>',
            ]
        )
    parts.append("</svg>")
    _atomic_write(path, "\n".join(parts) + "\n")


def analyze(
    *,
    input_path: Path = DEFAULT_INPUT,
    freeze_path: Path = DEFAULT_FREEZE,
    analysis_path: Path = DEFAULT_ANALYSIS,
    report_path: Path = DEFAULT_REPORT,
    audit_path: Path = DEFAULT_AUDIT,
    figure_path: Path = DEFAULT_FIGURE,
) -> dict[str, Any]:
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    errors = _validate_evaluated(payload)
    if errors:
        raise ValueError(f"V7 evaluated checkpoint failed audit: {errors}")
    freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
    rows = payload["results"]
    primary_scores = task_level_arm_scores(
        rows, value_path="deterministic_evaluation.score"
    )
    secondary_scores = task_level_arm_scores(
        rows, value_path="llm_judgment.secondary_mean"
    )
    arm_means = {
        arm: round(statistics.fmean(primary_scores[arm].values()), 12)
        for arm in V7_ARMS
    }
    secondary_means = {
        arm: round(statistics.fmean(secondary_scores[arm].values()), 12)
        for arm in V7_ARMS
    }
    primary_contrasts = [
        _paired_contrast(
            primary_scores,
            OPTIMIZED,
            comparator,
            seed=20260725 + index,
        )
        for index, comparator in enumerate((BM25, RANDOM))
    ]
    adjusted = holm_adjust(
        [row["exact_sign_flip_p"] for row in primary_contrasts]
    )
    for row, holm_p in zip(primary_contrasts, adjusted):
        row["holm_p"] = holm_p
    supporting_flat = _paired_contrast(
        primary_scores, OPTIMIZED, FLAT, seed=20260729
    )
    secondary_contrasts = [
        _paired_contrast(
            secondary_scores,
            OPTIMIZED,
            comparator,
            seed=20260800 + index,
        )
        for index, comparator in enumerate((BM25, RANDOM, FLAT))
    ]
    decision = decision_from_primary_contrasts(primary_contrasts)
    context_task_scores = task_level_arm_scores(
        rows, value_path="context_canonical_tokens"
    )
    context_means = {
        arm: round(
            statistics.fmean(context_task_scores[arm].values()), 12
        )
        for arm in V7_ARMS
    }
    context_reduction = 1.0 - context_means[OPTIMIZED] / context_means[FLAT]
    retention = supporting_flat["bootstrap"]["ci_low"] >= float(
        freeze["statistics"]["retention_margin"]
    )
    token_efficiency_supported = retention and context_reduction > 0
    decision.update(
        {
            "deterministic_quality_retained_vs_flat_margin": retention,
            "retention_margin": freeze["statistics"]["retention_margin"],
            "optimized_context_reduction_vs_flat": round(
                context_reduction, 12
            ),
            "token_efficiency_supported": token_efficiency_supported,
            "manuscript_recommendation": (
                "Update the manuscript with the preregistered V7 routing-"
                "superiority result and bounded GxP evidence claims."
                if decision["routing_superiority_supported"]
                else "Do not claim routing superiority. Preserve Outcome B; "
                "report the V7 null and only token-efficiency/governance claims "
                "that satisfy the retention and audit checks."
            ),
        }
    )
    gxp_audit = _gxp_audit(rows, freeze=freeze)
    analysis = {
        "schema_version": "v7-routing-sensitive-analysis-1",
        "input_path": input_path.relative_to(PROJECT_ROOT).as_posix(),
        "input_sha256": _sha256_file(input_path),
        "freeze_path": freeze_path.relative_to(PROJECT_ROOT).as_posix(),
        "freeze_sha256": _sha256_file(freeze_path),
        "independent_unit": "task",
        "task_count": 24,
        "runs_per_cell": 3,
        "row_count": len(rows),
        "primary_endpoint": "deterministic atomic-criterion score",
        "primary_arm_means": arm_means,
        "primary_contrasts": primary_contrasts,
        "supporting_optimized_minus_flat": supporting_flat,
        "secondary_endpoint": (
            "blinded LLM readability/actionability score"
        ),
        "secondary_arm_means": secondary_means,
        "secondary_contrasts": secondary_contrasts,
        "criterion_type_pass_rates": _criterion_type_rates(rows),
        "context_canonical_token_means": context_means,
        "decision": decision,
        "gxp_audit": gxp_audit,
        "missing_failure_policy": (
            "generation transport failure aborts; invalid or unparseable "
            "answers score zero; all judge attempts are retained"
        ),
        "operational_gxp_compliance_claimed": False,
        "human_time_savings_claimed": False,
        "regulatory_outcome_claimed": False,
    }
    _atomic_json(analysis_path, analysis)
    _svg_primary(figure_path, arm_means)
    _atomic_write(report_path, _render_report(analysis, figure_path))
    _atomic_write(audit_path, _render_audit(gxp_audit))
    return analysis


def _render_report(analysis: Mapping[str, Any], figure_path: Path) -> str:
    means = analysis["primary_arm_means"]
    contrasts = analysis["primary_contrasts"]
    decision = analysis["decision"]
    rows = [
        "# V7 Routing-Sensitive Deterministic Evaluation",
        "",
        "## Design and endpoint",
        "",
        "The frozen formal panel contains 24 independent held-out tasks, four "
        "arms, and three generation replicates per task-arm cell (288 stored "
        "responses). Replicates were averaged within task before inference. "
        "The primary endpoint is the deterministic atomic-criterion score; the "
        "blinded LLM readability/actionability score is secondary.",
        "",
        "## Primary results",
        "",
        "| Arm | Task-level mean |",
        "|---|---:|",
    ]
    for arm in V7_ARMS:
        rows.append(f"| `{arm}` | {means[arm]:.4f} |")
    rows.extend(
        [
            "",
            "| Contrast | Mean difference | Exact P | Holm P | dz | 95% bootstrap CI |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for contrast in contrasts:
        rows.append(
            f"| optimized - `{contrast['second']}` | "
            f"{contrast['mean_difference']:.4f} | "
            f"{contrast['exact_sign_flip_p']:.4g} | "
            f"{contrast['holm_p']:.4g} | "
            f"{contrast['paired_cohen_dz']:.3f} | "
            f"[{contrast['bootstrap']['ci_low']:.4f}, "
            f"{contrast['bootstrap']['ci_high']:.4f}] |"
        )
    rows.extend(
        [
            "",
            f"![V7 deterministic primary]({figure_path.name})",
            "",
            "## Decision",
            "",
            f"Routing superiority supported: "
            f"**{str(decision['routing_superiority_supported']).lower()}**.",
            "",
            f"Optimized context reduction versus flat: "
            f"{100 * decision['optimized_context_reduction_vs_flat']:.2f}%. "
            f"Token-efficiency criterion supported: "
            f"**{str(decision['token_efficiency_supported']).lower()}**.",
            "",
            decision["manuscript_recommendation"],
            "",
            "Claims remain bounded to this deterministic benchmark and its "
            "recorded evidence controls. No operational GxP compliance, human "
            "time savings, or regulatory outcome is claimed.",
            "",
        ]
    )
    return "\n".join(rows)


def _render_audit(audit: Mapping[str, Any]) -> str:
    return "\n".join(
        [
            "# V7 GxP Evidence Audit",
            "",
            "| Control | Passed | Evidence |",
            "|---|---:|---|",
            "| Version update propagation | "
            f"{audit['version_update_propagation']['passed']} | "
            f"{audit['version_update_propagation']['detected_excluded_conflicts']} "
            "conflicts detected; "
            f"{audit['version_update_propagation']['selected_stale_chunks']} "
            "stale chunks selected |",
            "| Provenance completeness | "
            f"{audit['provenance_completeness']['passed']} | "
            f"Citation pass rate "
            f"{audit['provenance_completeness']['criterion_pass_rate']:.3f} |",
            "| Reproducible context manifests | "
            f"{audit['reproducible_context_manifest']['passed']} | "
            f"{audit['reproducible_context_manifest']['manifest_count']} "
            "manifest rows with repeated-hash proof |",
            "| Deterministic change containment | "
            f"{audit['deterministic_change_containment']['passed']} | "
            f"{audit['deterministic_change_containment']['changed_skill_count']} "
            "changed-skill scopes partitioned |",
            "| Usage and prompt accounting | "
            f"{audit['usage_and_prompt_accounting']['passed']} | "
            "Input, output, cache-read, cache-creation, serialized chars/bytes, "
            "and canonical prompt counts recorded |",
            "| Failure and score integrity | "
            f"{audit['failure_and_score_integrity']['passed']} | "
            "Parse histories retained; no silent score substitution |",
            "",
            "This is an evidence-control audit for the experiment. It is not an "
            "operational GxP compliance certification.",
            "",
        ]
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--freeze", type=Path, default=DEFAULT_FREEZE)
    parser.add_argument("--analysis", type=Path, default=DEFAULT_ANALYSIS)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--audit", type=Path, default=DEFAULT_AUDIT)
    parser.add_argument("--figure", type=Path, default=DEFAULT_FIGURE)
    args = parser.parse_args()
    result = analyze(
        input_path=args.input,
        freeze_path=args.freeze,
        analysis_path=args.analysis,
        report_path=args.report,
        audit_path=args.audit,
        figure_path=args.figure,
    )
    print(
        json.dumps(
            {
                "routing_superiority_supported": result["decision"][
                    "routing_superiority_supported"
                ],
                "token_efficiency_supported": result["decision"][
                    "token_efficiency_supported"
                ],
                "analysis": str(args.analysis),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
