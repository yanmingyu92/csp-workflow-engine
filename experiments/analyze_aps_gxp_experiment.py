#!/usr/bin/env python3
"""Task-paired quality and governance analysis for APS-GxP v6.

The task is the inferential unit. Replicate scores are averaged within each
task-arm cell before any contrast is calculated. The locked confirmatory family
contains optimized APS minus frozen v5 APS, flat loading, and token-matched
random loading. Each contrast uses a 10,000-resample paired-task bootstrap and
an exact two-sided sign-flip test; Holm adjustment is applied only across those
three quality contrasts.

GxP-oriented provenance, reproducibility, context-scope, and simulated
change-impact measurements are deliberately reported as separate deterministic
metrics. They are architectural proxies and are not a composite compliance
score or evidence of operational GxP compliance.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import itertools
import json
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from experiments import run_experiment_v4_claude as v4  # noqa: E402
from experiments.run_experiment_v6_aps_gxp import (  # noqa: E402
    FOUR_ARM_CONDITIONS,
    SMOKE_TASK_ID,
    build_complete_response_judge_prompt,
    validate_v6_checkpoint,
)


CONFIRMATORY_CONTRASTS = (
    ("aps_gxp_optimized", "aps_v5_frozen"),
    ("aps_gxp_optimized", "flat_8000"),
    ("aps_gxp_optimized", "random_token_matched"),
)

ARM_ORDER = (
    "aps_v5_frozen",
    "aps_gxp_optimized",
    "flat_8000",
    "random_token_matched",
)

QUALITY_METRICS = (
    "quality_score",
    "dim_completeness",
    "dim_terminology",
    "dim_structure",
)

ADMITTED_STATUSES = frozenset({"loaded", "truncated"})
FULL_RESPONSE_POLICY = "full_stored_response_no_character_truncation"
BOOTSTRAP_RESAMPLES = 10_000
SIGN_TOLERANCE = 1e-12

PROVENANCE_FIELDS = (
    "skill_name",
    "source_path",
    "source_sha256",
    "declared_version",
    "active_node_id",
    "skill_bound_node_ids",
    "graph_relation",
    "priority_band",
    "lexical_relevance_score",
    "hub_degree",
    "final_priority_score",
    "original_estimated_tokens",
    "injected_estimated_tokens",
    "status",
    "selection_reason",
    "injected_fragment_sha256",
)

SCOPE_CATEGORIES = (
    "current",
    "relevance_qualified_adjacent",
    "global",
    "out_of_scope",
)


def sha256_file(path: Path) -> str:
    """Return a streaming SHA-256 digest for an input checkpoint."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(text: str) -> str:
    """Return the SHA-256 digest of UTF-8 text."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _finite_score(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    numeric = float(value)
    return numeric if math.isfinite(numeric) else None


def _row_metric(row: Mapping[str, Any], metric: str) -> float | None:
    """Read a metric from a row, including the stored scalar-judgment scores."""
    score_name = {
        "dim_completeness": "completeness",
        "dim_terminology": "terminology",
        "dim_structure": "structure",
    }.get(metric)
    scores = (row.get("scalar_judgment") or {}).get("scores") or {}
    if score_name:
        judgment_value = _finite_score(scores.get(score_name))
        if judgment_value is not None:
            return judgment_value
    if metric == "quality_score":
        dimensions = [
            _finite_score(scores.get(name))
            for name in ("completeness", "terminology", "structure")
        ]
        if all(value is not None for value in dimensions):
            finite_dimensions = [
                value for value in dimensions if value is not None
            ]
            return float(sum(finite_dimensions)) / len(finite_dimensions)
    return _finite_score(row.get(metric))


def aggregate_task_means(
    rows: Iterable[Mapping[str, Any]],
    metric: str,
    intention_to_run: bool = True,
) -> dict[str, dict[str, float]]:
    """Average replicates within task-arm cells before inference.

    Agent failures receive the conservative score 1 only in the
    intention-to-run analysis. Missing judge scores without an agent failure
    remain missing rather than being silently imputed.
    """
    cells: dict[str, dict[str, list[float]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for row in rows:
        value = _row_metric(row, metric)
        if value is None and intention_to_run and row.get("is_error_response"):
            value = 1.0
        if value is None:
            continue
        arm = row.get("arm", row.get("condition"))
        task_id = row.get("task_id")
        if arm is None or task_id is None:
            continue
        cells[str(arm)][str(task_id)].append(value)

    return {
        arm: {
            task_id: float(statistics.fmean(values))
            for task_id, values in task_cells.items()
            if values
        }
        for arm, task_cells in cells.items()
    }


def paired_bootstrap_ci(
    differences: Sequence[float],
    n_boot: int = BOOTSTRAP_RESAMPLES,
    seed: int = 42,
) -> tuple[float, float, float]:
    """Return the mean and percentile CI from paired-task resampling."""
    if n_boot <= 0:
        raise ValueError("At least one bootstrap resample is required")
    diffs = np.asarray(differences, dtype=float)
    if diffs.size == 0 or not np.isfinite(diffs).all():
        raise ValueError("Finite paired task differences are required")
    generator = np.random.default_rng(seed)
    indices = generator.integers(0, diffs.size, size=(n_boot, diffs.size))
    bootstrap_means = diffs[indices].mean(axis=1)
    return (
        float(diffs.mean()),
        float(np.percentile(bootstrap_means, 2.5)),
        float(np.percentile(bootstrap_means, 97.5)),
    )


def exact_sign_flip_p(differences: Sequence[float]) -> float:
    """Return the exact two-sided paired sign-flip P value."""
    diffs = np.asarray(differences, dtype=float)
    if diffs.size == 0 or not np.isfinite(diffs).all():
        raise ValueError("Finite paired task differences are required")
    observed = abs(float(diffs.mean()))
    extreme = 0
    total = 0
    for signs in itertools.product((-1.0, 1.0), repeat=diffs.size):
        statistic = abs(float((diffs * np.asarray(signs)).mean()))
        extreme += statistic >= observed - SIGN_TOLERANCE
        total += 1
    return extreme / total


def holm_adjust(p_values: Mapping[str, float]) -> dict[str, float]:
    """Apply step-down Holm adjustment while preserving caller key order."""
    for label, value in p_values.items():
        if not math.isfinite(float(value)) or not 0 <= float(value) <= 1:
            raise ValueError(f"Invalid P value for {label}: {value}")
    ordered = sorted(p_values.items(), key=lambda item: (item[1], item[0]))
    family_size = len(ordered)
    adjusted: dict[str, float] = {}
    running_max = 0.0
    for rank, (label, raw_p) in enumerate(ordered):
        candidate = min(1.0, (family_size - rank) * float(raw_p))
        running_max = max(running_max, candidate)
        adjusted[label] = running_max
    return {label: adjusted[label] for label in p_values}


def paired_dz(differences: Sequence[float]) -> float:
    """Return paired Cohen ``d_z`` using the sample SD of task differences."""
    values = [float(value) for value in differences]
    if len(values) < 2:
        return math.nan
    standard_deviation = statistics.stdev(values)
    mean = statistics.fmean(values)
    if standard_deviation == 0:
        return math.copysign(math.inf, mean) if mean else 0.0
    return mean / standard_deviation


def leave_one_task_out_range(
    differences: Sequence[float],
) -> tuple[float, float]:
    """Return the range of paired means after omitting each task once."""
    values = [float(value) for value in differences]
    if len(values) < 2:
        return (math.nan, math.nan)
    means = [
        statistics.fmean(values[:index] + values[index + 1 :])
        for index in range(len(values))
    ]
    return min(means), max(means)


def _contrast_label(arm_a: str, arm_b: str) -> str:
    return f"{arm_a}_minus_{arm_b}"


def _arm_summary(
    task_means: Mapping[str, Mapping[str, float]],
) -> dict[str, dict[str, float | int]]:
    summary: dict[str, dict[str, float | int]] = {}
    arms = [*ARM_ORDER, *sorted(set(task_means) - set(ARM_ORDER))]
    for arm in arms:
        if arm not in task_means:
            continue
        values = list(task_means[arm].values())
        summary[arm] = {
            "n_tasks": len(values),
            "mean": statistics.fmean(values) if values else math.nan,
            "sd_across_tasks": (
                statistics.stdev(values) if len(values) > 1 else math.nan
            ),
        }
    return summary


def _task_signs(differences: Sequence[float]) -> dict[str, int]:
    return {
        "positive": sum(value > SIGN_TOLERANCE for value in differences),
        "negative": sum(value < -SIGN_TOLERANCE for value in differences),
        "tied": sum(abs(value) <= SIGN_TOLERANCE for value in differences),
    }


def _analyze_contrast(
    task_means: Mapping[str, Mapping[str, float]],
    arm_a: str,
    arm_b: str,
    seed: int,
) -> dict[str, Any]:
    tasks = sorted(
        set(task_means.get(arm_a, {})) & set(task_means.get(arm_b, {}))
    )
    if not tasks:
        return {
            "arm_a": arm_a,
            "arm_b": arm_b,
            "n_tasks": 0,
            "error": "No paired task cells",
        }
    differences = [
        task_means[arm_a][task_id] - task_means[arm_b][task_id]
        for task_id in tasks
    ]
    estimate, low, high = paired_bootstrap_ci(differences, seed=seed)
    leave_low, leave_high = leave_one_task_out_range(differences)
    return {
        "arm_a": arm_a,
        "arm_b": arm_b,
        "tasks": tasks,
        "n_tasks": len(tasks),
        "task_differences": differences,
        "mean_difference": estimate,
        "ci_95": [low, high],
        "p_exact_sign_flip": exact_sign_flip_p(differences),
        "paired_dz": paired_dz(differences),
        "task_signs": _task_signs(differences),
        "leave_one_task_out_range": [leave_low, leave_high],
    }


def analyze_quality(
    rows: Iterable[Mapping[str, Any]],
    seed: int = 42,
    metric: str = "quality_score",
    intention_to_run: bool = True,
    adjust_holm: bool = True,
) -> dict[str, Any]:
    """Analyze the locked quality family using task-aggregated replicates."""
    row_list = list(rows)
    task_means = aggregate_task_means(
        row_list, metric, intention_to_run=intention_to_run
    )
    confirmatory: dict[str, dict[str, Any]] = {}
    for offset, (arm_a, arm_b) in enumerate(CONFIRMATORY_CONTRASTS):
        label = _contrast_label(arm_a, arm_b)
        confirmatory[label] = _analyze_contrast(
            task_means, arm_a, arm_b, seed=seed + offset
        )

    raw_p_values = {
        label: result["p_exact_sign_flip"]
        for label, result in confirmatory.items()
        if "p_exact_sign_flip" in result
    }
    if adjust_holm:
        adjusted = holm_adjust(raw_p_values)
        for label, adjusted_p in adjusted.items():
            confirmatory[label]["p_holm"] = adjusted_p

    arm_summary = _arm_summary(task_means)
    return {
        "metric": metric,
        "intention_to_run": intention_to_run,
        "bootstrap_resamples": BOOTSTRAP_RESAMPLES,
        "holm_family": (
            [_contrast_label(*contrast) for contrast in CONFIRMATORY_CONTRASTS]
            if adjust_holm
            else None
        ),
        "arm_summary": arm_summary,
        "condition_summary": arm_summary,
        "task_means": task_means,
        "confirmatory": confirmatory,
    }


def validate_complete_response_judgments(
    rows: Iterable[Mapping[str, Any]],
) -> list[str]:
    """Validate the no-prefix scalar-judging evidence in result rows."""
    errors: list[str] = []
    seen_keys: set[str] = set()
    for index, row in enumerate(rows):
        key = str(row.get("run_key") or f"row[{index}]")
        if key in seen_keys:
            errors.append(f"{key}: duplicate run key")
        seen_keys.add(key)
        response = row.get("response")
        judgment = row.get("scalar_judgment")
        if not isinstance(response, str):
            errors.append(f"{key}: response is missing")
            continue
        response_hash = sha256_text(response)
        if row.get("response_sha256") != response_hash:
            errors.append(f"{key}: stored response hash mismatch")
        if not isinstance(judgment, Mapping):
            errors.append(f"{key}: scalar judgment is missing")
            continue
        if judgment.get("policy") != FULL_RESPONSE_POLICY:
            errors.append(f"{key}: complete-response policy is missing")
        if judgment.get("truncated") is not False:
            errors.append(f"{key}: scalar judgment used a truncated response")
        if judgment.get("response_characters_judged") != len(response):
            errors.append(f"{key}: judged character count does not match response")
        if judgment.get("response_bytes_judged") != len(
            response.encode("utf-8")
        ):
            errors.append(f"{key}: judged response byte count does not match")
        if judgment.get("response_sha256") != response_hash:
            errors.append(f"{key}: judged response hash mismatch")
        if judgment.get("judge_parse_error"):
            errors.append(f"{key}: judge parse error")
        for field in (
            "judge_model_requested",
            "judge_model_returned",
            "judge_response_id",
            "system_fingerprint",
            "system_fingerprint_capture",
            "judge_input_tokens",
            "judge_output_tokens",
            "finish_reason",
            "rendered_prompt_sha256",
            "judge_parse_error",
        ):
            if field not in judgment:
                errors.append(f"{key}: missing judge provenance field {field}")
        for field in (
            "judge_model_requested",
            "judge_model_returned",
            "judge_response_id",
            "finish_reason",
            "rendered_prompt_sha256",
        ):
            if not judgment.get(field):
                errors.append(f"{key}: empty judge provenance field {field}")
        expected_fingerprint_capture = (
            "available"
            if judgment.get("system_fingerprint")
            else "provider_returned_null"
        )
        if (
            judgment.get("system_fingerprint_capture")
            != expected_fingerprint_capture
        ):
            errors.append(f"{key}: invalid system fingerprint capture status")
        task_id = row.get("task_id")
        criteria = row.get("judge_domain_criteria")
        if task_id not in v4.TASK_PROMPTS or not isinstance(criteria, str):
            errors.append(f"{key}: task or judge domain criteria is invalid")
        else:
            rendered_prompt = build_complete_response_judge_prompt(
                str(task_id), response, criteria
            )
            if judgment.get("rendered_prompt_sha256") != sha256_text(
                rendered_prompt
            ):
                errors.append(f"{key}: rendered prompt hash mismatch")
            if (
                judgment.get("rendered_prompt_characters")
                != len(rendered_prompt)
                or judgment.get("rendered_prompt_bytes")
                != len(rendered_prompt.encode("utf-8"))
            ):
                errors.append(f"{key}: rendered prompt length mismatch")
        scores = judgment.get("scores")
        if not isinstance(scores, Mapping):
            errors.append(f"{key}: scalar scores are missing")
            continue
        for dimension in ("completeness", "terminology", "structure"):
            score = _finite_score(scores.get(dimension))
            if score is None or not 1 <= score <= 5:
                errors.append(f"{key}: invalid {dimension} score")
        finite_scores = {
            dimension: _finite_score(scores.get(dimension))
            for dimension in ("completeness", "terminology", "structure")
        }
        if all(value is not None for value in finite_scores.values()):
            for field, dimension in (
                ("dim_completeness", "completeness"),
                ("dim_terminology", "terminology"),
                ("dim_structure", "structure"),
            ):
                if row.get(field) != finite_scores[dimension]:
                    errors.append(
                        f"{key}: {field} conflicts with scalar judgment"
                    )
            expected_quality = round(
                sum(
                    value
                    for value in finite_scores.values()
                    if value is not None
                )
                / 3.0,
                2,
            )
            if row.get("quality_score") != expected_quality:
                errors.append(
                    f"{key}: quality_score conflicts with scalar judgment"
                )
    return errors


def validate_result_panel(data: Mapping[str, Any]) -> list[str]:
    """Accept only the fixed four-call smoke or locked 120-call formal panel."""
    errors: list[str] = []
    metadata = data.get("metadata", {})
    tasks = metadata.get("tasks")
    arms = metadata.get("arms")
    runs = metadata.get("runs")
    smoke_panel = (
        tasks == [SMOKE_TASK_ID]
        and arms == list(FOUR_ARM_CONDITIONS)
        and runs == 1
    )
    formal_panel = (
        tasks == list(v4.QUICK_10_TASKS)
        and arms == list(FOUR_ARM_CONDITIONS)
        and runs == 3
    )
    if not smoke_panel and not formal_panel:
        errors.append("result panel is neither the locked smoke nor formal panel")
        return errors
    rows = data.get("results", [])
    keys = [row.get("run_key") for row in rows]
    expected_keys = {
        f"{task_id}::{arm}::{run_id}"
        for task_id in tasks
        for arm in arms
        for run_id in range(runs)
    }
    if len(keys) != len(expected_keys) or set(keys) != expected_keys:
        errors.append(
            f"result cardinality/run keys {len(keys)} != {len(expected_keys)}"
        )
    return errors


def _empty_scope() -> dict[str, dict[str, int]]:
    return {
        category: {"skills": 0, "tokens": 0}
        for category in SCOPE_CATEGORIES
    }


def _scope_from_manifest(
    manifest: Mapping[str, Any],
) -> dict[str, dict[str, int]]:
    scope = _empty_scope()
    for candidate in manifest.get("candidates", []):
        if candidate.get("status") not in ADMITTED_STATUSES:
            continue
        relation = candidate.get("graph_relation")
        if relation == "CURRENT":
            category = "current"
        elif relation in {"SUCCESSOR", "PREDECESSOR"}:
            category = "relevance_qualified_adjacent"
        elif relation == "GLOBAL":
            category = "global"
        else:
            category = "out_of_scope"
        scope[category]["skills"] += 1
        scope[category]["tokens"] += int(
            candidate.get("injected_estimated_tokens", 0)
        )
    return scope


def _merge_scope(
    target: dict[str, dict[str, int]],
    source: Mapping[str, Mapping[str, Any]],
) -> None:
    for category in SCOPE_CATEGORIES:
        values = source.get(category, {})
        target[category]["skills"] += int(values.get("skills", 0))
        target[category]["tokens"] += int(values.get("tokens", 0))


def _candidate_provenance_complete(candidate: Mapping[str, Any]) -> bool:
    if any(field not in candidate for field in PROVENANCE_FIELDS):
        return False
    for field in PROVENANCE_FIELDS:
        if field == "declared_version":
            continue
        value = candidate.get(field)
        if value is None or value == "":
            return False
    return True


def summarize_change_impact(
    contexts: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Summarize offline one-skill manifest impact by arm and task.

    A task context is affected when the skill appears in its ordered candidate
    manifest, matching the runner's in-memory source-hash/version perturbation.
    Multiple formal replicates are collapsed to the task-arm level.
    """
    rows = list(contexts)
    skills = sorted(
        {
            str(candidate["skill_name"])
            for row in rows
            for candidate in (row.get("manifest") or {}).get("candidates", [])
            if candidate.get("skill_name")
        }
    )
    tasks_by_arm: dict[str, set[str]] = defaultdict(set)
    affected: dict[str, dict[str, set[str]]] = defaultdict(
        lambda: defaultdict(set)
    )
    for row in rows:
        arm = str(row.get("arm", row.get("condition", "")))
        task_id = str(row.get("task_id", ""))
        if not arm or not task_id:
            continue
        tasks_by_arm[arm].add(task_id)
        for candidate in (row.get("manifest") or {}).get("candidates", []):
            skill_name = candidate.get("skill_name")
            if skill_name:
                affected[arm][str(skill_name)].add(task_id)

    per_arm: dict[str, Any] = {}
    for arm in [*ARM_ORDER, *sorted(set(tasks_by_arm) - set(ARM_ORDER))]:
        if arm not in tasks_by_arm:
            continue
        task_count = len(tasks_by_arm[arm])
        counts = {
            skill: len(affected[arm].get(skill, set())) for skill in skills
        }
        proportions = {
            skill: (count / task_count if task_count else math.nan)
            for skill, count in counts.items()
        }
        values = list(counts.values())
        per_arm[arm] = {
            "n_tasks": task_count,
            "per_skill_affected_tasks": counts,
            "per_skill_affected_proportion": proportions,
            "mean_affected_tasks": (
                statistics.fmean(values) if values else 0.0
            ),
            "median_affected_tasks": (
                statistics.median(values) if values else 0.0
            ),
            "range_affected_tasks": (
                [min(values), max(values)] if values else [0, 0]
            ),
        }

    optimized = per_arm.get("aps_gxp_optimized", {}).get(
        "per_skill_affected_tasks", {}
    )
    flat = per_arm.get("flat_8000", {}).get(
        "per_skill_affected_tasks", {}
    )
    paired = {
        skill: optimized.get(skill, 0) - flat.get(skill, 0)
        for skill in skills
    }
    paired_values = list(paired.values())
    return {
        "simulated_skills": skills,
        "per_arm": per_arm,
        "paired_optimized_minus_flat": {
            "per_skill_affected_task_difference": paired,
            "mean_difference": (
                statistics.fmean(paired_values) if paired_values else 0.0
            ),
            "median_difference": (
                statistics.median(paired_values) if paired_values else 0.0
            ),
            "range_difference": (
                [min(paired_values), max(paired_values)]
                if paired_values
                else [0, 0]
            ),
        },
    }


def summarize_governance_metrics(
    contexts: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Return separate deterministic GxP-oriented governance summaries."""
    rows = list(contexts)
    admitted_total = 0
    admitted_complete = 0
    fallback_context_total = 0
    fallback_context_complete = 0
    reproducibility_total = 0
    reproducibility_complete = 0
    scope_by_arm: dict[str, dict[str, dict[str, int]]] = {}

    for row in rows:
        arm = str(row.get("arm", row.get("condition", "unknown")))
        scope_by_arm.setdefault(arm, _empty_scope())
        manifest = row.get("manifest")
        if isinstance(manifest, Mapping):
            candidates = [
                candidate
                for candidate in manifest.get("candidates", [])
                if candidate.get("status") in ADMITTED_STATUSES
            ]
            admitted_total += len(candidates)
            admitted_complete += sum(
                _candidate_provenance_complete(candidate)
                for candidate in candidates
            )
            _merge_scope(scope_by_arm[arm], _scope_from_manifest(manifest))
        else:
            fallback_context_total += 1
            fallback_context_complete += bool(row.get("provenance_complete"))
            _merge_scope(scope_by_arm[arm], row.get("scope", {}))

        repeated_hashes = row.get("repeated_manifest_sha256")
        if isinstance(repeated_hashes, Sequence) and not isinstance(
            repeated_hashes, (str, bytes)
        ):
            reproducibility_total += 1
            reproducibility_complete += bool(repeated_hashes) and (
                len(set(repeated_hashes)) == 1
                and (
                    not row.get("manifest_sha256")
                    or repeated_hashes[0] == row.get("manifest_sha256")
                )
            )

    provenance_denominator = admitted_total or fallback_context_total
    provenance_numerator = (
        admitted_complete if admitted_total else fallback_context_complete
    )
    provenance_percent = (
        100.0 * provenance_numerator / provenance_denominator
        if provenance_denominator
        else math.nan
    )
    reproducibility_percent = (
        100.0 * reproducibility_complete / reproducibility_total
        if reproducibility_total
        else math.nan
    )
    return {
        "provenance_completeness_percent": provenance_percent,
        "provenance_complete_fragments": provenance_numerator,
        "provenance_admitted_fragments": provenance_denominator,
        "manifest_reproducibility_percent": reproducibility_percent,
        "manifest_reproducible_contexts": reproducibility_complete,
        "manifest_contexts_with_repeats": reproducibility_total,
        "context_scope": scope_by_arm,
        "change_impact": summarize_change_impact(rows),
        "interpretation_boundary": (
            "Deterministic governance proxies only; no operational GxP "
            "compliance claim."
        ),
    }


def summarize_efficiency(
    rows: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Summarize task-level context-token use without mixing it with quality."""
    cells: dict[str, dict[str, list[float]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for row in rows:
        arm = row.get("arm", row.get("condition"))
        task_id = row.get("task_id")
        tokens = _finite_score(row.get("skills_tokens"))
        if arm is None or task_id is None or tokens is None:
            continue
        cells[str(arm)][str(task_id)].append(tokens)
    task_means = {
        arm: {
            task_id: statistics.fmean(values)
            for task_id, values in task_cells.items()
        }
        for arm, task_cells in cells.items()
    }
    summary = _arm_summary(task_means)
    optimized_mean = summary.get("aps_gxp_optimized", {}).get("mean")
    flat_mean = summary.get("flat_8000", {}).get("mean")
    reduction = math.nan
    if (
        isinstance(optimized_mean, (int, float))
        and isinstance(flat_mean, (int, float))
        and flat_mean
    ):
        reduction = 100.0 * (float(flat_mean) - float(optimized_mean)) / float(
            flat_mean
        )
    return {
        "task_level_arm_tokens": task_means,
        "arm_summary": summary,
        "optimized_vs_flat_mean_token_reduction_percent": reduction,
        "prespecified_15_percent_reduction_met": (
            reduction >= 15.0 if math.isfinite(reduction) else None
        ),
    }


def classify_formal_outcome(
    quality: Mapping[str, Any] | None,
    efficiency: Mapping[str, Any],
    governance: Mapping[str, Any],
    integrity_pass: bool,
) -> dict[str, Any]:
    """Apply the frozen v6 A/B/C decision boundaries without tuning."""
    confirmatory = quality.get("confirmatory", {}) if quality else {}
    flat_label = "aps_gxp_optimized_minus_flat_8000"
    nonrouted_labels = (
        flat_label,
        "aps_gxp_optimized_minus_random_token_matched",
    )
    flat_result = confirmatory.get(flat_label, {})
    ci_95 = flat_result.get("ci_95", [math.nan, math.nan])
    ci_lower = (
        _finite_score(ci_95[0])
        if isinstance(ci_95, Sequence) and len(ci_95) == 2
        else None
    )
    quality_retention = (
        ci_lower is not None and ci_lower >= -0.20
    )
    superiority_contrasts = [
        label
        for label in nonrouted_labels
        if (
            _finite_score(
                confirmatory.get(label, {}).get("mean_difference")
            )
            is not None
            and float(
                confirmatory[label]["mean_difference"]
            )
            > 0
            and _finite_score(confirmatory[label].get("p_holm"))
            is not None
            and float(confirmatory[label]["p_holm"]) < 0.05
        )
    ]
    token_reduction = (
        efficiency.get("prespecified_15_percent_reduction_met") is True
    )
    provenance = (
        _finite_score(
            governance.get("provenance_completeness_percent")
        )
        == 100.0
    )
    reproducibility = (
        _finite_score(
            governance.get("manifest_reproducibility_percent")
        )
        == 100.0
    )
    change_mean = _finite_score(
        governance.get("change_impact", {})
        .get("paired_optimized_minus_flat", {})
        .get("mean_difference")
    )
    change_containment = (
        change_mean is not None and change_mean <= 0.0
    )
    gates: dict[str, dict[str, Any]] = {
        "complete_response_and_checkpoint_integrity": {
            "pass": bool(integrity_pass),
        },
        "superiority_vs_nonrouted_control": {
            "pass": bool(superiority_contrasts),
            "supported_contrasts": superiority_contrasts,
        },
        "quality_retention": {
            "pass": quality_retention,
            "optimized_minus_flat_ci_lower": ci_lower,
            "engineering_margin": -0.20,
        },
        "mean_token_reduction": {
            "pass": token_reduction,
            "actual_percent": efficiency.get(
                "optimized_vs_flat_mean_token_reduction_percent"
            ),
            "threshold_percent": 15.0,
            "policy_enforced_efficiency_disclosure": True,
        },
        "provenance_completeness": {
            "pass": provenance,
            "actual_percent": governance.get(
                "provenance_completeness_percent"
            ),
            "target_percent": 100.0,
        },
        "manifest_reproducibility": {
            "pass": reproducibility,
            "actual_percent": governance.get(
                "manifest_reproducibility_percent"
            ),
            "target_percent": 100.0,
        },
        "change_impact_containment": {
            "pass": change_containment,
            "optimized_minus_flat_mean_affected_tasks": change_mean,
            "criterion": "<= 0 (optimized is no broader than flat)",
        },
    }
    common_gates_pass = all(
        gates[name]["pass"]
        for name in (
            "complete_response_and_checkpoint_integrity",
            "quality_retention",
            "mean_token_reduction",
            "provenance_completeness",
            "manifest_reproducibility",
            "change_impact_containment",
        )
    )
    if common_gates_pass and superiority_contrasts:
        outcome = "A"
        label = "quality and governance advantage"
    elif common_gates_pass:
        outcome = "B"
        label = "similar quality with efficiency/governance advantage"
    else:
        outcome = "C"
        label = "no incremental measured value under frozen gates"
    return {
        "outcome": outcome,
        "label": label,
        "gates": gates,
        "boundary": (
            "Applies only to this benchmark, model, judge, and synthetic "
            "setting; governance metrics are architectural proxies."
        ),
    }


def analyze_experiment(
    data: Mapping[str, Any],
    source_sha256: str,
) -> dict[str, Any]:
    """Build the complete machine-readable v6 analysis report."""
    rows = list(data.get("results", []))
    contexts = list(
        data.get("contexts", data.get("cells", rows))
    )
    metadata = data.get("metadata", {})
    seed = int(metadata.get("seed", data.get("seed", 42)))
    judgment_errors = [
        *validate_result_panel(data),
        *validate_v6_checkpoint(data, require_judgments=True),
        *(
            validate_complete_response_judgments(rows)
            if rows
            else ["result rows are missing"]
        ),
    ]
    quality = analyze_quality(rows, seed=seed) if not judgment_errors else None
    dimension_results = (
        {
            metric: analyze_quality(
                rows,
                seed=seed,
                metric=metric,
                adjust_holm=False,
            )
            for metric in QUALITY_METRICS[1:]
        }
        if not judgment_errors
        else None
    )
    governance = summarize_governance_metrics(contexts)
    supplied_change_impact = (
        data.get("actuals", {}).get("change_impact")
        if isinstance(data.get("actuals"), Mapping)
        else None
    )
    if supplied_change_impact is not None:
        governance["change_impact"] = supplied_change_impact
    efficiency = summarize_efficiency(rows or contexts)
    integrity = bool(rows) and not judgment_errors
    formal_panel = (
        metadata.get("tasks") == list(v4.QUICK_10_TASKS)
        and metadata.get("arms") == list(FOUR_ARM_CONDITIONS)
        and metadata.get("runs") == 3
    )
    outcome_decision = (
        classify_formal_outcome(
            quality,
            efficiency,
            governance,
            integrity_pass=integrity,
        )
        if formal_panel
        else {
            "outcome": "NOT_APPLICABLE",
            "label": "A/B/C classification is reserved for the formal panel",
            "gates": {},
        }
    )
    return {
        "analysis_version": "aps-gxp-v6-task-paired-1",
        "source_sha256": source_sha256,
        "seed": seed,
        "dry_run": bool(metadata.get("dry_run", data.get("network_calls") == 0)),
        "confirmatory_family": [
            _contrast_label(arm_a, arm_b)
            for arm_a, arm_b in CONFIRMATORY_CONTRASTS
        ],
        "quality": quality,
        "dimension_sensitivity": dimension_results,
        "efficiency": efficiency,
        "governance": governance,
        "outcome_decision": outcome_decision,
        "complete_response_judging": {
            "policy": FULL_RESPONSE_POLICY,
            "validated_rows": len(rows) if rows and not judgment_errors else 0,
            "errors": judgment_errors,
            "pass": integrity,
        },
    }


def _fmt_number(value: Any, digits: int = 2) -> str:
    if value is None:
        return "NA"
    numeric = float(value)
    if math.isnan(numeric):
        return "NA"
    if math.isinf(numeric):
        return "+Inf" if numeric > 0 else "-Inf"
    return f"{numeric:.{digits}f}"


def _fmt_p(value: Any) -> str:
    if value is None:
        return "NA"
    numeric = float(value)
    if numeric < 0.001:
        return "<.001"
    return f"{numeric:.3f}".lstrip("0")


def render_markdown(report: Mapping[str, Any]) -> str:
    """Render the primary analysis and separate governance summaries."""
    quality = report["quality"]
    lines = [
        "# APS-GxP v6 Analysis",
        "",
        f"Source SHA-256: `{report['source_sha256']}`",
        f"Dry run: `{str(report['dry_run']).lower()}`",
        "",
        "## Task-Level Arm Means",
        "",
        "| Arm | Tasks | Mean quality | SD across tasks |",
        "|---|---:|---:|---:|",
    ]
    if quality is None:
        lines.append("| Not validated | 0 | NA | NA |")
    else:
        for arm, values in quality["arm_summary"].items():
            lines.append(
                f"| {arm} | {values['n_tasks']} | "
                f"{_fmt_number(values['mean'])} | "
                f"{_fmt_number(values['sd_across_tasks'])} |"
            )

    lines.extend(
        [
            "",
            "## Confirmatory Quality Contrasts",
            "",
            "Replicates are averaged within task. CIs use 10,000 paired-task "
            "bootstrap resamples; P values are exact two-sided sign-flip tests "
            "with Holm adjustment across the three locked contrasts.",
            "",
            "| Contrast | Tasks | Difference | 95% CI | Exact P | Holm P | dz | Signs (+/-/=) | LOTO range |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for result in (quality or {"confirmatory": {}})["confirmatory"].values():
        label = f"{result['arm_a']} - {result['arm_b']}"
        if "error" in result:
            lines.append(f"| {label} | 0 | NA | NA | NA | NA | NA | NA | NA |")
            continue
        signs = result["task_signs"]
        low, high = result["ci_95"]
        leave_low, leave_high = result["leave_one_task_out_range"]
        lines.append(
            f"| {label} | {result['n_tasks']} | "
            f"{_fmt_number(result['mean_difference'])} | "
            f"[{_fmt_number(low)}, {_fmt_number(high)}] | "
            f"{_fmt_p(result['p_exact_sign_flip'])} | "
            f"{_fmt_p(result.get('p_holm'))} | "
            f"{_fmt_number(result['paired_dz'])} | "
            f"{signs['positive']}/{signs['negative']}/{signs['tied']} | "
            f"[{_fmt_number(leave_low)}, {_fmt_number(leave_high)}] |"
        )

    governance = report["governance"]
    lines.extend(
        [
            "",
            "## GxP-Oriented Governance Metrics",
            "",
            "These are separate deterministic architectural proxies; they do not "
            "establish operational GxP compliance.",
            "",
            f"- Provenance completeness: "
            f"{_fmt_number(governance['provenance_completeness_percent'])}%",
            f"- Manifest reproducibility: "
            f"{_fmt_number(governance['manifest_reproducibility_percent'])}%",
            "",
            "### Context Scope",
            "",
            "| Arm | Category | Skills | Tokens |",
            "|---|---|---:|---:|",
        ]
    )
    for arm, categories in governance["context_scope"].items():
        for category, values in categories.items():
            lines.append(
                f"| {arm} | {category} | {values['skills']} | "
                f"{values['tokens']} |"
            )

    judging = report["complete_response_judging"]
    efficiency = report["efficiency"]
    decision = report["outcome_decision"]
    lines.extend(
        [
            "",
            "## Efficiency and Frozen Decision",
            "",
            "- Optimized-versus-flat mean skill-token reduction: "
            f"{_fmt_number(efficiency['optimized_vs_flat_mean_token_reduction_percent'])}%",
            "- Prespecified 15% reduction gate: "
            f"{'PASS' if efficiency['prespecified_15_percent_reduction_met'] else 'FAIL'}",
            "- Token reduction is partly policy-enforced by the frozen 84% "
            "soft-cap design; quality retention remains empirical.",
            f"- Outcome: **{decision['outcome']} — {decision['label']}**",
            "",
            "",
            "## Complete-Response Judging Integrity",
            "",
            f"Status: **{'PASS' if judging['pass'] else 'NOT VALIDATED'}**",
            f"Policy: `{judging['policy']}`",
            f"Validation errors: {len(judging['errors'])}",
            "",
        ]
    )
    return "\n".join(lines)


def _svg_bar_chart(
    task_means: Mapping[str, Mapping[str, float]],
    arm_summary: Mapping[str, Mapping[str, Any]],
    y_label: str,
    y_min: float,
    y_max: float,
) -> str:
    """Render a deterministic, dependency-free vector bar-and-point chart."""
    width, height = 900, 520
    left, right, top, bottom = 90, 30, 35, 105
    plot_width = width - left - right
    plot_height = height - top - bottom
    arms = [arm for arm in ARM_ORDER if arm in arm_summary]
    labels = {
        "aps_v5_frozen": "Frozen v5",
        "aps_gxp_optimized": "Optimized",
        "flat_8000": "Flat 8000",
        "random_token_matched": "Random matched",
    }
    colors = {
        "aps_v5_frozen": "#0072B2",
        "aps_gxp_optimized": "#E69F00",
        "flat_8000": "#009E73",
        "random_token_matched": "#CC79A7",
    }

    def y_coordinate(value: float) -> float:
        clipped = min(y_max, max(y_min, value))
        return top + (y_max - clipped) / (y_max - y_min) * plot_height

    elements = [
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'width="{width}" height="{height}" viewBox="0 0 {width} {height}">'
        ),
        f"<title>{html.escape(y_label)} by arm</title>",
        (
            "<desc>Bars show task-level means, whiskers show SD across tasks, "
            "and points show individual task means.</desc>"
        ),
        '<rect width="100%" height="100%" fill="white"/>',
    ]
    for tick_index in range(6):
        value = y_min + (y_max - y_min) * tick_index / 5
        y = y_coordinate(value)
        elements.extend(
            [
                (
                    f'<line x1="{left}" y1="{y:.2f}" x2="{width-right}" '
                    f'y2="{y:.2f}" stroke="#D9D9D9" stroke-width="1"/>'
                ),
                (
                    f'<text x="{left-12}" y="{y+4:.2f}" text-anchor="end" '
                    'font-family="Arial" font-size="12" fill="#222">'
                    f"{value:.1f}</text>"
                ),
            ]
        )
    elements.extend(
        [
            (
                f'<line x1="{left}" y1="{top}" x2="{left}" '
                f'y2="{height-bottom}" stroke="#222" stroke-width="1.5"/>'
            ),
            (
                f'<line x1="{left}" y1="{height-bottom}" '
                f'x2="{width-right}" y2="{height-bottom}" '
                'stroke="#222" stroke-width="1.5"/>'
            ),
            (
                f'<text x="22" y="{top + plot_height/2:.2f}" '
                f'transform="rotate(-90 22 {top + plot_height/2:.2f})" '
                'text-anchor="middle" font-family="Arial" font-size="14" '
                f'fill="#222">{html.escape(y_label)}</text>'
            ),
        ]
    )
    band = plot_width / max(1, len(arms))
    for arm_index, arm in enumerate(arms):
        center = left + band * (arm_index + 0.5)
        bar_width = band * 0.48
        values = arm_summary[arm]
        mean = float(values["mean"])
        sd_value = _finite_score(values.get("sd_across_tasks"))
        sd = sd_value if sd_value is not None else 0.0
        mean_y = y_coordinate(mean)
        baseline_y = y_coordinate(y_min)
        elements.append(
            (
                f'<rect x="{center-bar_width/2:.2f}" y="{mean_y:.2f}" '
                f'width="{bar_width:.2f}" height="{baseline_y-mean_y:.2f}" '
                f'fill="{colors[arm]}" fill-opacity="0.72" '
                'stroke="#222" stroke-width="1"/>'
            )
        )
        low_y = y_coordinate(mean - sd)
        high_y = y_coordinate(mean + sd)
        elements.extend(
            [
                (
                    f'<line x1="{center:.2f}" y1="{high_y:.2f}" '
                    f'x2="{center:.2f}" y2="{low_y:.2f}" '
                    'stroke="#222" stroke-width="2"/>'
                ),
                (
                    f'<line x1="{center-8:.2f}" y1="{high_y:.2f}" '
                    f'x2="{center+8:.2f}" y2="{high_y:.2f}" '
                    'stroke="#222" stroke-width="2"/>'
                ),
                (
                    f'<line x1="{center-8:.2f}" y1="{low_y:.2f}" '
                    f'x2="{center+8:.2f}" y2="{low_y:.2f}" '
                    'stroke="#222" stroke-width="2"/>'
                ),
            ]
        )
        task_values = list(task_means.get(arm, {}).values())
        for point_index, task_value in enumerate(task_values):
            offset = (
                (point_index - (len(task_values) - 1) / 2)
                * min(5.0, bar_width / max(1, len(task_values)))
            )
            elements.append(
                (
                    f'<circle cx="{center+offset:.2f}" '
                    f'cy="{y_coordinate(float(task_value)):.2f}" r="3" '
                    'fill="#222" fill-opacity="0.72"/>'
                )
            )
        elements.append(
            (
                f'<text x="{center:.2f}" y="{height-bottom+28}" '
                'text-anchor="middle" font-family="Arial" font-size="12" '
                f'fill="#222">{html.escape(labels[arm])}</text>'
            )
        )
    elements.append("</svg>")
    return "\n".join(elements)


def _render_statistical_appendix(report: Mapping[str, Any]) -> str:
    quality = report.get("quality")
    lines = [
        "# Statistical Appendix",
        "",
        "Unit of analysis: task. Three generations are averaged within each "
        "task-arm cell before inference.",
        "",
        "Uncertainty: 10,000-resample paired-task percentile bootstrap 95% CI. "
        "Inference: exact two-sided sign-flip test, Holm-adjusted across the "
        "three frozen quality contrasts. Effect size: paired Cohen d_z.",
        "",
        "| Contrast | n tasks | Mean difference | 95% CI | Exact P | Holm P | d_z |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for result in (quality or {"confirmatory": {}})["confirmatory"].values():
        low, high = result.get("ci_95", [math.nan, math.nan])
        lines.append(
            f"| {result['arm_a']} - {result['arm_b']} | "
            f"{result.get('n_tasks', 0)} | "
            f"{_fmt_number(result.get('mean_difference'))} | "
            f"[{_fmt_number(low)}, {_fmt_number(high)}] | "
            f"{_fmt_p(result.get('p_exact_sign_flip'))} | "
            f"{_fmt_p(result.get('p_holm'))} | "
            f"{_fmt_number(result.get('paired_dz'))} |"
        )
    lines.extend(
        [
            "",
            "The -0.20 optimized-minus-flat CI lower-bound threshold is an "
            "engineering quality-retention rule, not a validated clinical "
            "noninferiority margin. Dimension-level analyses are descriptive.",
            "",
        ]
    )
    return "\n".join(lines)


def _render_figure_catalog(report: Mapping[str, Any]) -> str:
    quality = report.get("quality") or {}
    efficiency = report.get("efficiency") or {}
    quality_summary = quality.get("arm_summary", {})
    optimized_quality = quality_summary.get(
        "aps_gxp_optimized", {}
    ).get("mean")
    flat_quality = quality_summary.get("flat_8000", {}).get("mean")
    reduction = efficiency.get(
        "optimized_vs_flat_mean_token_reduction_percent"
    )
    return "\n".join(
        [
            "# Figure Catalog and Interpretation",
            "",
            "## Figure 1 — Task-level quality by arm",
            "",
            "- **Purpose:** Compare complete-response scalar quality across the "
            "four frozen arms at the task level.",
            "- **Observation:** Optimized and flat task-level means are "
            f"{_fmt_number(optimized_quality)} and {_fmt_number(flat_quality)}.",
            "- **Interpretation:** Arm differences are interpreted only through "
            "the frozen paired-task contrasts; the plot itself is descriptive.",
            "- **Implication:** Use the Holm-adjusted contrasts and retention CI "
            "to select outcome A, B, or C.",
            "- **Caption:** Bars show task-level mean quality on the bounded 1–5 "
            "scale; whiskers are SD across tasks and points are individual task "
            "means (formal n=10 tasks per arm). No smoothing or normalization.",
            "",
            "## Figure 2 — Context efficiency by arm",
            "",
            "- **Purpose:** Show task-level injected skill-context tokens across "
            "the four arms.",
            "- **Observation:** The optimized-versus-flat mean reduction is "
            f"{_fmt_number(reduction)}%.",
            "- **Interpretation:** The reduction is partly policy-enforced by "
            "the frozen 84% soft cap and must not be presented as an independently "
            "discovered efficiency effect.",
            "- **Implication:** Efficiency supports A/B only when the empirical "
            "quality-retention and integrity/governance gates also pass.",
            "- **Caption:** Bars show mean estimated skill-context tokens from "
            "zero; whiskers are SD across tasks and points are individual task "
            "means (formal n=10 tasks per arm). No smoothing or normalization.",
            "",
        ]
    )


def build_analysis_bundle_files(
    report: Mapping[str, Any],
) -> dict[str, str]:
    """Return the deterministic strict analysis bundle as relative text files."""
    quality = report.get("quality") or {}
    efficiency = report.get("efficiency") or {}
    quality_svg = _svg_bar_chart(
        quality.get("task_means", {}),
        quality.get("arm_summary", {}),
        "Complete-response quality (1–5)",
        1.0,
        5.0,
    )
    efficiency_svg = _svg_bar_chart(
        efficiency.get("task_level_arm_tokens", {}),
        efficiency.get("arm_summary", {}),
        "Estimated injected skill-context tokens",
        0.0,
        8000.0,
    )
    return {
        "analysis-report.md": render_markdown(report),
        "analysis.json": json.dumps(
            _json_safe(report), indent=2, ensure_ascii=False
        ),
        "statistical-appendix.md": _render_statistical_appendix(report),
        "figure-catalog.md": _render_figure_catalog(report),
        "figures/task-level-quality.svg": quality_svg,
        "figures/context-efficiency.svg": efficiency_svg,
    }


def _json_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output-prefix", required=True, type=Path)
    parser.add_argument("--bundle-dir", type=Path)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()

    source_hash = sha256_file(args.input)
    data = json.loads(args.input.read_text(encoding="utf-8"))
    report = _json_safe(analyze_experiment(data, source_hash))
    json_path = args.output_prefix.with_suffix(".json")
    markdown_path = args.output_prefix.with_suffix(".md")
    bundle_files = (
        build_analysis_bundle_files(report)
        if args.bundle_dir is not None
        else {}
    )

    if args.verify:
        existing = json.loads(json_path.read_text(encoding="utf-8"))
        if existing != report:
            raise SystemExit("Verification failed: report does not recompute exactly")
        for relative_path, expected_text in bundle_files.items():
            bundle_path = args.bundle_dir / relative_path
            if bundle_path.read_text(encoding="utf-8") != expected_text:
                raise SystemExit(
                    f"Verification failed: {bundle_path} does not recompute exactly"
                )
        print(f"Verified: {json_path}")
        if args.bundle_dir is not None:
            print(f"Verified bundle: {args.bundle_dir}")
        return

    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    markdown_path.write_text(render_markdown(report), encoding="utf-8")
    for relative_path, content in bundle_files.items():
        bundle_path = args.bundle_dir / relative_path
        bundle_path.parent.mkdir(parents=True, exist_ok=True)
        bundle_path.write_text(content, encoding="utf-8")
    print(f"Wrote: {markdown_path}")
    print(f"Wrote: {json_path}")
    if args.bundle_dir is not None:
        print(f"Wrote bundle: {args.bundle_dir}")


if __name__ == "__main__":
    main()
