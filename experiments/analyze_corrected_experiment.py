#!/usr/bin/env python3
"""Task-paired analysis for the corrected six-arm JMIR AI experiment."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple

import numpy as np


CONFIRMATORY: Tuple[Tuple[str, str], ...] = (
    ("agent_framework", "agent_domain_prompt_only"),
    ("agent_framework", "agent_skills_flat"),
    ("agent_framework", "agent_skills_random"),
)

MECHANISM: Tuple[Tuple[str, str], ...] = (
    ("agent_domain_prompt_only", "agent_only"),
    ("agent_skills_flat", "agent_domain_prompt_only"),
    ("agent_skills_random", "agent_domain_prompt_only"),
    ("agent_framework_distill", "agent_framework"),
)

METRICS = (
    "quality_score",
    "dim_completeness",
    "dim_terminology",
    "dim_structure",
)

CONDITION_LABELS = {
    "agent_only": "Bare agent",
    "agent_domain_prompt_only": "Domain prompt only",
    "agent_framework": "Corrected APS",
    "agent_framework_distill": "Corrected APS + principles",
    "agent_skills_flat": "Flat corpus",
    "agent_skills_random": "Random corpus (k=5)",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def aggregate_task_means(
    rows: Iterable[Mapping[str, Any]],
    metric: str,
    intention_to_run: bool = True,
) -> Dict[str, Dict[str, float]]:
    """Average replicates within each task-condition cell.

    Agent failures receive the prespecified conservative score of 1 in the
    intention-to-run analysis. Judge parse failures without an agent failure
    remain missing because no neutral score is imputed.
    """
    cells: Dict[str, Dict[str, List[float]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for row in rows:
        value = row.get(metric)
        if value is None and intention_to_run and row.get("is_error_response"):
            value = 1.0
        if value is None:
            continue
        cells[str(row["condition"])][str(row["task_id"])].append(float(value))

    return {
        condition: {
            task_id: float(np.mean(values))
            for task_id, values in task_cells.items()
            if values
        }
        for condition, task_cells in cells.items()
    }


def paired_bootstrap_ci(
    differences: Sequence[float],
    n_boot: int = 10_000,
    seed: int = 42,
) -> Tuple[float, float, float]:
    """Return mean and percentile CI by resampling paired task differences."""
    diffs = np.asarray(differences, dtype=float)
    if diffs.size == 0:
        raise ValueError("At least one paired difference is required")
    rng = np.random.default_rng(seed)
    indices = rng.integers(0, diffs.size, size=(n_boot, diffs.size))
    boot_means = diffs[indices].mean(axis=1)
    return (
        float(diffs.mean()),
        float(np.percentile(boot_means, 2.5)),
        float(np.percentile(boot_means, 97.5)),
    )


def exact_sign_flip_p(differences: Sequence[float]) -> float:
    """Exact two-sided randomization P value for paired task differences."""
    diffs = np.asarray(differences, dtype=float)
    if diffs.size == 0:
        raise ValueError("At least one paired difference is required")
    observed = abs(float(diffs.mean()))
    extreme = 0
    total = 0
    for signs in itertools.product((-1.0, 1.0), repeat=diffs.size):
        statistic = abs(float((diffs * np.asarray(signs)).mean()))
        extreme += statistic >= observed - 1e-12
        total += 1
    return extreme / total


def paired_dz(differences: Sequence[float]) -> float:
    """Paired standardized mean difference using the sample SD of differences."""
    diffs = np.asarray(differences, dtype=float)
    if diffs.size < 2:
        return math.nan
    standard_deviation = float(diffs.std(ddof=1))
    if standard_deviation == 0:
        mean = float(diffs.mean())
        return math.copysign(math.inf, mean) if mean else 0.0
    return float(diffs.mean()) / standard_deviation


def holm_adjust(p_values: Mapping[str, float]) -> Dict[str, float]:
    """Holm family-wise error adjustment keyed by contrast label."""
    ordered = sorted(p_values.items(), key=lambda item: (item[1], item[0]))
    count = len(ordered)
    adjusted: Dict[str, float] = {}
    running_max = 0.0
    for rank, (label, p_value) in enumerate(ordered):
        candidate = min(1.0, (count - rank) * float(p_value))
        running_max = max(running_max, candidate)
        adjusted[label] = running_max
    return {label: adjusted[label] for label in p_values}


def _contrast_label(condition_a: str, condition_b: str) -> str:
    return f"{condition_a}_minus_{condition_b}"


def _paired_differences(
    task_means: Mapping[str, Mapping[str, float]],
    condition_a: str,
    condition_b: str,
) -> Tuple[List[str], List[float]]:
    tasks = sorted(
        set(task_means.get(condition_a, {}))
        & set(task_means.get(condition_b, {}))
    )
    differences = [
        task_means[condition_a][task] - task_means[condition_b][task]
        for task in tasks
    ]
    return tasks, differences


def _analyze_contrasts(
    task_means: Mapping[str, Mapping[str, float]],
    contrasts: Sequence[Tuple[str, str]],
    seed: int,
) -> Dict[str, Dict[str, Any]]:
    output: Dict[str, Dict[str, Any]] = {}
    for offset, (condition_a, condition_b) in enumerate(contrasts):
        label = _contrast_label(condition_a, condition_b)
        tasks, differences = _paired_differences(
            task_means, condition_a, condition_b
        )
        if not differences:
            output[label] = {
                "condition_a": condition_a,
                "condition_b": condition_b,
                "n_tasks": 0,
                "error": "No paired task cells",
            }
            continue
        estimate, ci_low, ci_high = paired_bootstrap_ci(
            differences, seed=seed + offset
        )
        output[label] = {
            "condition_a": condition_a,
            "condition_b": condition_b,
            "tasks": tasks,
            "n_tasks": len(tasks),
            "task_differences": differences,
            "mean_difference": estimate,
            "ci_95": [ci_low, ci_high],
            "p_exact_sign_flip": exact_sign_flip_p(differences),
            "paired_dz": paired_dz(differences),
        }
    return output


def _condition_summary(
    task_means: Mapping[str, Mapping[str, float]]
) -> Dict[str, Dict[str, float]]:
    summary = {}
    for condition, task_values in task_means.items():
        values = list(task_values.values())
        summary[condition] = {
            "n_tasks": len(values),
            "mean": float(np.mean(values)) if values else math.nan,
            "sd_across_tasks": (
                float(np.std(values, ddof=1)) if len(values) > 1 else math.nan
            ),
        }
    return summary


def analyze_experiment(data: Mapping[str, Any], source_sha256: str) -> Dict[str, Any]:
    rows = data.get("results", [])
    seed = int(data.get("metadata", {}).get("seed", 42))
    analyses: Dict[str, Any] = {}

    for sensitivity_name, intention_to_run in (
        ("intention_to_run", True),
        ("complete_case", False),
    ):
        metric_results = {}
        for metric in METRICS:
            task_means = aggregate_task_means(
                rows, metric, intention_to_run=intention_to_run
            )
            confirmatory = _analyze_contrasts(
                task_means, CONFIRMATORY, seed=seed
            )
            if metric == "quality_score":
                valid_p = {
                    label: result["p_exact_sign_flip"]
                    for label, result in confirmatory.items()
                    if "p_exact_sign_flip" in result
                }
                adjusted = holm_adjust(valid_p)
                for label, adjusted_p in adjusted.items():
                    confirmatory[label]["p_holm"] = adjusted_p
            metric_results[metric] = {
                "condition_summary": _condition_summary(task_means),
                "task_means": task_means,
                "confirmatory": confirmatory,
                "mechanism": _analyze_contrasts(
                    task_means, MECHANISM, seed=seed + 100
                ),
            }
        analyses[sensitivity_name] = metric_results

    return {
        "analysis_version": "v5-task-paired-1",
        "source_sha256": source_sha256,
        "dry_run": bool(data.get("metadata", {}).get("dry_run")),
        "seed": seed,
        "confirmatory_family": [
            _contrast_label(condition_a, condition_b)
            for condition_a, condition_b in CONFIRMATORY
        ],
        "analyses": analyses,
    }


def _fmt_number(value: Any, digits: int = 2) -> str:
    if value is None:
        return "NA"
    value = float(value)
    if math.isnan(value):
        return "NA"
    if math.isinf(value):
        return "+Inf" if value > 0 else "-Inf"
    return f"{value:.{digits}f}"


def _fmt_p(value: Any) -> str:
    if value is None:
        return "NA"
    value = float(value)
    if value < 0.001:
        return "<.001"
    return f"{value:.3f}".lstrip("0")


def render_markdown(report: Mapping[str, Any]) -> str:
    primary = report["analyses"]["intention_to_run"]["quality_score"]
    lines = [
        "# Corrected Experiment v5 Report",
        "",
        f"Source SHA-256: `{report['source_sha256']}`",
        f"Dry run: `{str(report['dry_run']).lower()}`",
        "",
        "## Task-Level Condition Means",
        "",
        "| Condition | Tasks | Mean | SD across tasks |",
        "|---|---:|---:|---:|",
    ]
    for condition, values in primary["condition_summary"].items():
        lines.append(
            f"| {CONDITION_LABELS.get(condition, condition)} | "
            f"{values['n_tasks']} | {_fmt_number(values['mean'])} | "
            f"{_fmt_number(values['sd_across_tasks'])} |"
        )

    lines.extend(
        [
            "",
            "## Confirmatory Overall-Score Contrasts",
            "",
            "Replicates are averaged within task before paired inference. P values "
            "are exact two-sided sign-flip tests; Holm adjustment covers the three "
            "prespecified contrasts.",
            "",
            "| Contrast (A − B) | Tasks | Difference | 95% paired-bootstrap CI | Exact P | Holm P | dz |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for result in primary["confirmatory"].values():
        if "error" in result:
            lines.append(
                f"| {result['condition_a']} − {result['condition_b']} | 0 | NA | NA | NA | NA | NA |"
            )
            continue
        low, high = result["ci_95"]
        lines.append(
            f"| {CONDITION_LABELS.get(result['condition_a'], result['condition_a'])} − "
            f"{CONDITION_LABELS.get(result['condition_b'], result['condition_b'])} | "
            f"{result['n_tasks']} | {_fmt_number(result['mean_difference'])} | "
            f"[{_fmt_number(low)}, {_fmt_number(high)}] | "
            f"{_fmt_p(result['p_exact_sign_flip'])} | "
            f"{_fmt_p(result.get('p_holm'))} | {_fmt_number(result['paired_dz'])} |"
        )

    lines.extend(
        [
            "",
            "## Mechanism Contrasts",
            "",
            "| Contrast (A − B) | Tasks | Difference | 95% paired-bootstrap CI | Exact P | dz |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for result in primary["mechanism"].values():
        if "error" in result:
            continue
        low, high = result["ci_95"]
        lines.append(
            f"| {CONDITION_LABELS.get(result['condition_a'], result['condition_a'])} − "
            f"{CONDITION_LABELS.get(result['condition_b'], result['condition_b'])} | "
            f"{result['n_tasks']} | {_fmt_number(result['mean_difference'])} | "
            f"[{_fmt_number(low)}, {_fmt_number(high)}] | "
            f"{_fmt_p(result['p_exact_sign_flip'])} | {_fmt_number(result['paired_dz'])} |"
        )

    lines.extend(["", "## Interpretation Gate", ""])
    if report["dry_run"]:
        lines.append(
            "This is dry-run data. No scientific or significance conclusion is permitted."
        )
    else:
        routed = primary["confirmatory"]
        flat = routed.get(
            _contrast_label("agent_framework", "agent_skills_flat"), {}
        )
        random = routed.get(
            _contrast_label("agent_framework", "agent_skills_random"), {}
        )
        supported = (
            flat.get("mean_difference", 0) > 0
            and random.get("mean_difference", 0) > 0
            and flat.get("p_holm", 1) < 0.05
            and random.get("p_holm", 1) < 0.05
        )
        if supported:
            lines.append(
                "The prespecified routing superiority gate is met against both flat "
                "and random corpus controls."
            )
        else:
            lines.append(
                "The prespecified routing superiority gate is not met. Do not claim "
                "outcome superiority for APS routing; attribute gains only to supported "
                "components and describe routing as an efficiency/auditability mechanism."
            )

    lines.extend(
        [
            "",
            "Complete-case and dimension-level sensitivity results are retained in "
            "the companion JSON report.",
            "",
        ]
    )
    return "\n".join(lines)


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output-prefix", required=True, type=Path)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()

    source_hash = sha256_file(args.input)
    data = json.loads(args.input.read_text(encoding="utf-8"))
    report = analyze_experiment(data, source_hash)

    json_path = args.output_prefix.with_suffix(".json")
    markdown_path = args.output_prefix.with_suffix(".md")
    if args.verify:
        existing = json.loads(json_path.read_text(encoding="utf-8"))
        if existing != _json_safe(report):
            raise SystemExit("Verification failed: report does not recompute exactly")
        print(f"Verified: {json_path}")
        return

    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(_json_safe(report), indent=2), encoding="utf-8"
    )
    markdown_path.write_text(render_markdown(report), encoding="utf-8")
    print(f"Wrote: {markdown_path}")
    print(f"Wrote: {json_path}")


if __name__ == "__main__":
    main()

