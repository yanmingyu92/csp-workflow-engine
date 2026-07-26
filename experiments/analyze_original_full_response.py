#!/usr/bin/env python3
"""Analyze the original experiment after locked full-response re-judgment.

The corrective six-arm v5 experiment remains the primary evidence. This
analysis determines whether the original framework-versus-bare-agent contrast
can be retained as secondary evidence after removing the 4,000-character judge
input limit and adding bidirectional pairwise presentations.
"""

from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path
import sys
from typing import Any, Dict, Iterable, Mapping, Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from experiments.analyze_corrected_experiment import (  # noqa: E402
    exact_sign_flip_p,
    holm_adjust,
    paired_bootstrap_ci,
    paired_dz,
    sha256_file,
)
from experiments.generate_v5_analysis_bundle import (  # noqa: E402
    summarize_pairwise_results,
)


ANALYSIS_VERSION = "original-full-response-task-paired-1"
CONDITIONS = (
    "agent_only",
    "agent_framework",
    "agent_framework_distill",
)
CONTRASTS = (
    ("agent_framework", "agent_only"),
    ("agent_framework_distill", "agent_only"),
    ("agent_framework_distill", "agent_framework"),
)
METRICS = (
    "quality_score",
    "dim_completeness",
    "dim_terminology",
    "dim_structure",
)
LABELS = {
    "agent_only": "Bare agent",
    "agent_framework": "Original framework",
    "agent_framework_distill": "Original framework + principles",
}
PRIMARY_LABEL = "agent_framework_minus_agent_only"


def _contrast_label(condition_a: str, condition_b: str) -> str:
    return f"{condition_a}_minus_{condition_b}"


def validate_source(data: Mapping[str, Any]) -> list[str]:
    """Refuse incomplete, prefix-only, or structurally inconsistent inputs."""
    errors: list[str] = []
    metadata = data.get("metadata", {})
    rows = list(data.get("results", []))
    logical_pairs = list(data.get("pairwise_results", []))
    presentations = list(data.get("pairwise_presentations", []))
    if not metadata.get("rejudge_complete"):
        errors.append("full-response re-judgment is not marked complete")
    if metadata.get("response_judging_policy") != (
        "full_stored_response_no_character_truncation"
    ):
        errors.append("source is not a full-response judgment checkpoint")
    if len(rows) != 90:
        errors.append(f"expected 90 scalar results, found {len(rows)}")
    if len(logical_pairs) != 60:
        errors.append(f"expected 60 logical pairs, found {len(logical_pairs)}")
    if len(presentations) != 120:
        errors.append(
            f"expected 120 pairwise presentations, found {len(presentations)}"
        )
    run_keys = [row.get("run_key") for row in rows]
    if len(run_keys) != len(set(run_keys)):
        errors.append("duplicate scalar run keys")
    if {str(row.get("condition")) for row in rows} != set(CONDITIONS):
        errors.append("unexpected condition set")
    if len({str(row.get("task_id")) for row in rows}) != 10:
        errors.append("expected 10 tasks")
    if any(
        row.get("full_response_judgment", {}).get("judge_parse_error")
        for row in rows
    ):
        errors.append("at least one scalar judgment is unparseable")
    if any(row.get("quality_score") is None for row in rows):
        errors.append("at least one full-response overall score is missing")
    if any(
        row.get("judge_parse_error") for row in presentations
    ):
        errors.append("at least one pairwise presentation is unparseable")
    return errors


def task_means(
    rows: Iterable[Mapping[str, Any]], metric: str, score_source: str
) -> Dict[str, Dict[str, float]]:
    """Average the three replicate scores within task-condition cells."""
    if score_source not in {"full", "prefix"}:
        raise ValueError("score_source must be 'full' or 'prefix'")
    cells: Dict[str, Dict[str, list[float]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for row in rows:
        value = (
            row.get(metric)
            if score_source == "full"
            else row.get("prefix_judgment", {}).get(metric)
        )
        if value is not None:
            cells[str(row["condition"])][str(row["task_id"])].append(
                float(value)
            )
    return {
        condition: {
            task_id: float(np.mean(values))
            for task_id, values in by_task.items()
        }
        for condition, by_task in cells.items()
    }


def _condition_summary(
    means: Mapping[str, Mapping[str, float]]
) -> Dict[str, Dict[str, float]]:
    output: Dict[str, Dict[str, float]] = {}
    for condition in CONDITIONS:
        values = list(means.get(condition, {}).values())
        output[condition] = {
            "n_tasks": len(values),
            "mean": float(np.mean(values)) if values else math.nan,
            "sd_across_tasks": (
                float(np.std(values, ddof=1)) if len(values) > 1 else math.nan
            ),
        }
    return output


def _paired_result(
    means: Mapping[str, Mapping[str, float]],
    condition_a: str,
    condition_b: str,
    seed: int,
) -> Dict[str, Any]:
    tasks = sorted(
        set(means.get(condition_a, {})) & set(means.get(condition_b, {}))
    )
    differences = [
        means[condition_a][task] - means[condition_b][task] for task in tasks
    ]
    estimate, low, high = paired_bootstrap_ci(differences, seed=seed)
    return {
        "condition_a": condition_a,
        "condition_b": condition_b,
        "tasks": tasks,
        "n_tasks": len(tasks),
        "task_differences": differences,
        "mean_difference": estimate,
        "ci_95": [low, high],
        "p_exact_sign_flip": exact_sign_flip_p(differences),
        "paired_dz": paired_dz(differences),
    }


def analyze_metric(
    rows: Sequence[Mapping[str, Any]],
    metric: str,
    score_source: str,
    seed: int,
) -> Dict[str, Any]:
    means = task_means(rows, metric, score_source)
    contrasts = {
        _contrast_label(a, b): _paired_result(means, a, b, seed + index)
        for index, (a, b) in enumerate(CONTRASTS)
    }
    return {
        "condition_summary": _condition_summary(means),
        "task_means": means,
        "contrasts": contrasts,
    }


def classify_primary(result: Mapping[str, Any]) -> str:
    """Apply the outcome-independent rule embedded in the rejudge protocol."""
    mean = float(result["mean_difference"])
    low = float(result["ci_95"][0])
    p_value = float(result["p_exact_sign_flip"])
    if mean <= 0:
        return "not_retained"
    if low > 0 and p_value < 0.05:
        return "retained_secondary_evidence"
    return "directional_but_uncertain"


def leave_one_task_out(
    result: Mapping[str, Any],
) -> list[Dict[str, Any]]:
    tasks = list(result["tasks"])
    differences = list(result["task_differences"])
    output = []
    for omitted_index, omitted_task in enumerate(tasks):
        retained = [
            difference
            for index, difference in enumerate(differences)
            if index != omitted_index
        ]
        output.append(
            {
                "omitted_task": omitted_task,
                "n_tasks": len(retained),
                "mean_difference": float(np.mean(retained)),
                "p_exact_sign_flip": exact_sign_flip_p(retained),
            }
        )
    return output


def protocol_sensitivity(
    rows: Sequence[Mapping[str, Any]],
    full_analysis: Mapping[str, Any],
    prefix_analysis: Mapping[str, Any],
) -> Dict[str, Any]:
    by_condition: Dict[str, Dict[str, Any]] = {}
    for condition in CONDITIONS:
        condition_rows = [
            row for row in rows if str(row["condition"]) == condition
        ]
        changes = [
            float(row["quality_score"])
            - float(row["prefix_judgment"]["quality_score"])
            for row in condition_rows
        ]
        by_condition[condition] = {
            "n_runs": len(condition_rows),
            "responses_over_4000_characters": sum(
                len(str(row["response"])) > 4000 for row in condition_rows
            ),
            "mean_full_minus_prefix_score": float(np.mean(changes)),
            "full_ceiling_scores": sum(
                float(row["quality_score"]) == 5 for row in condition_rows
            ),
            "prefix_ceiling_scores": sum(
                float(row["prefix_judgment"]["quality_score"]) == 5
                for row in condition_rows
            ),
        }
    primary_full = full_analysis["contrasts"][PRIMARY_LABEL]
    primary_prefix = prefix_analysis["contrasts"][PRIMARY_LABEL]
    return {
        "warning": (
            "Full-versus-prefix changes conflate response coverage with judge "
            "version/time and must not be interpreted as a causal truncation effect."
        ),
        "by_condition": by_condition,
        "primary_full": primary_full,
        "primary_prefix": primary_prefix,
        "change_in_primary_mean_difference": (
            primary_full["mean_difference"] - primary_prefix["mean_difference"]
        ),
    }


def build_analysis(data: Mapping[str, Any], source_hash: str) -> Dict[str, Any]:
    rows = list(data["results"])
    seed = int(data.get("metadata", {}).get("seed", 42))
    full = {
        metric: analyze_metric(rows, metric, "full", seed + offset * 20)
        for offset, metric in enumerate(METRICS)
    }
    prefix = analyze_metric(rows, "quality_score", "prefix", seed + 200)
    dimension_p = {
        metric: full[metric]["contrasts"][PRIMARY_LABEL][
            "p_exact_sign_flip"
        ]
        for metric in METRICS[1:]
    }
    dimension_holm = holm_adjust(dimension_p)
    for metric, adjusted in dimension_holm.items():
        full[metric]["contrasts"][PRIMARY_LABEL]["p_holm_dimensions"] = adjusted
    primary = full["quality_score"]["contrasts"][PRIMARY_LABEL]
    presentations = list(data.get("pairwise_presentations", []))
    fingerprints = sorted(
        {
            str(row.get("system_fingerprint"))
            for row in [
                *rows,
                *presentations,
            ]
            if row.get("system_fingerprint")
        }
    )
    models = sorted(
        {
            str(row.get("judge_model_returned"))
            for row in [
                *rows,
                *presentations,
            ]
            if row.get("judge_model_returned")
        }
    )
    return {
        "analysis_version": ANALYSIS_VERSION,
        "source_sha256": source_hash,
        "decision_rule": data["metadata"]["rejudge_protocol"][
            "primary_decision_rule"
        ],
        "primary_decision": classify_primary(primary),
        "full_response": full,
        "prefix_overall": prefix,
        "protocol_sensitivity": protocol_sensitivity(
            rows, full["quality_score"], prefix
        ),
        "leave_one_task_out_primary": leave_one_task_out(primary),
        "pairwise": summarize_pairwise_results(
            data.get("pairwise_results", [])
        ),
        "integrity": {
            "scalar_results": len(rows),
            "logical_pairs": len(data.get("pairwise_results", [])),
            "pairwise_presentations": len(presentations),
            "agent_errors": sum(
                bool(row.get("is_error_response")) for row in rows
            ),
            "scalar_parse_errors": sum(
                bool(
                    row.get("full_response_judgment", {}).get(
                        "judge_parse_error"
                    )
                )
                for row in rows
            ),
            "pairwise_parse_errors": sum(
                bool(row.get("judge_parse_error")) for row in presentations
            ),
            "judge_models_returned": models,
            "system_fingerprints": fingerprints,
            "rejudge_cost_usd": data["metadata"].get("rejudge_cost", {}).get(
                "total"
            ),
        },
    }


def _fmt(value: Any, digits: int = 2) -> str:
    if value is None:
        return "NA"
    return f"{float(value):.{digits}f}"


def _fmt_p(value: Any) -> str:
    if value is None:
        return "NA"
    value = float(value)
    return "<.001" if value < 0.001 else f"{value:.3f}".lstrip("0")


def _contrast_table(results: Mapping[str, Mapping[str, Any]]) -> list[str]:
    lines = []
    for result in results.values():
        low, high = result["ci_95"]
        lines.append(
            f"| {LABELS[result['condition_a']]} − "
            f"{LABELS[result['condition_b']]} | {result['n_tasks']} | "
            f"{_fmt(result['mean_difference'])} | "
            f"[{_fmt(low)}, {_fmt(high)}] | "
            f"{_fmt_p(result['p_exact_sign_flip'])} | "
            f"{_fmt(result['paired_dz'])} |"
        )
    return lines


def render_report(analysis: Mapping[str, Any]) -> str:
    overall = analysis["full_response"]["quality_score"]
    primary = overall["contrasts"][PRIMARY_LABEL]
    prefix = analysis["prefix_overall"]["contrasts"][PRIMARY_LABEL]
    sensitivity = analysis["protocol_sensitivity"]
    pairwise = analysis["pairwise"]
    decision_text = {
        "retained_secondary_evidence": (
            "The original framework contrast passes the locked retention rule, "
            "but only as secondary evidence."
        ),
        "directional_but_uncertain": (
            "The original framework contrast remains positive but does not pass "
            "the locked retention rule; report it as inconclusive sensitivity evidence."
        ),
        "not_retained": (
            "The original framework contrast does not retain a positive effect "
            "under full-response re-judgment."
        ),
    }[analysis["primary_decision"]]
    lines = [
        "# Original Experiment: Full-Response Re-judgment Analysis",
        "",
        f"Immutable checkpoint SHA-256: `{analysis['source_sha256']}`  ",
        f"Analysis version: `{analysis['analysis_version']}`",
        "",
        "## Decision",
        "",
        decision_text,
        "",
        "The corrected six-arm v5 experiment remains the primary evidence because "
        "it repaired the scheduler and separated the domain-prompt, corpus, and "
        "routing mechanisms. This reanalysis cannot restore a routing-specific "
        "claim to the original bundled experiment.",
        "",
        "## Full-response task-paired results",
        "",
        "Three replicates were averaged within each task-condition cell. Exact P "
        "values use two-sided sign flips over 10 paired task differences.",
        "",
        "| Contrast | Tasks | Mean difference | 95% paired-bootstrap CI | Exact P | paired dz |",
        "|---|---:|---:|---:|---:|---:|",
        *_contrast_table(overall["contrasts"]),
        "",
        f"The locked primary estimate is {_fmt(primary['mean_difference'])} "
        f"(95% CI [{_fmt(primary['ci_95'][0])}, "
        f"{_fmt(primary['ci_95'][1])}], exact P="
        f"{_fmt_p(primary['p_exact_sign_flip'])}).",
        "",
        "## Protocol sensitivity",
        "",
        f"The preserved first-4,000-character result was "
        f"{_fmt(prefix['mean_difference'])} (exact P="
        f"{_fmt_p(prefix['p_exact_sign_flip'])}); the full-response estimate was "
        f"{_fmt(primary['mean_difference'])}. The change was "
        f"{_fmt(sensitivity['change_in_primary_mean_difference'])} points.",
        "",
        sensitivity["warning"],
        "",
        "| Condition | Runs | Responses >4000 chars | Mean score change (full−prefix) | Full ceilings | Prefix ceilings |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for condition in CONDITIONS:
        result = sensitivity["by_condition"][condition]
        lines.append(
            f"| {LABELS[condition]} | {result['n_runs']} | "
            f"{result['responses_over_4000_characters']} | "
            f"{_fmt(result['mean_full_minus_prefix_score'])} | "
            f"{result['full_ceiling_scores']} | "
            f"{result['prefix_ceiling_scores']} |"
        )
    lines.extend(
        [
            "",
            "## Pairwise order sensitivity",
            "",
            "Each matched pair was shown in both AB and BA order. Discordant "
            "orientations are retained as discordant rather than forced into a win.",
            "",
            "| Contrast | Logical pairs | A wins | B wins | Ties | Order-discordant | Errors |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for result in pairwise.values():
        lines.append(
            f"| {LABELS[result['condition_a']]} vs "
            f"{LABELS[result['condition_b']]} | {result['n_total']} | "
            f"{result['a_wins']} | {result['b_wins']} | "
            f"{result['ties']} | {result['discordant']} | "
            f"{result['errors']} |"
        )
    loo = analysis["leave_one_task_out_primary"]
    lines.extend(
        [
            "",
            "## Robustness boundaries",
            "",
            f"- Leave-one-task-out estimates ranged from "
            f"{_fmt(min(row['mean_difference'] for row in loo))} to "
            f"{_fmt(max(row['mean_difference'] for row in loo))}.",
            "- The original intervention bundled a domain-aligned system prompt "
            "with node-bound curated rule injection while the intended four-band "
            "scheduler was inoperative; it cannot identify routing causally.",
            "- Full-versus-prefix score changes are a protocol sensitivity, not a "
            "clean truncation experiment, because the judge endpoint/version also "
            "changed over time.",
            "- Automated-judge outcomes, 10 authored benchmark tasks, and one "
            "backbone do not establish clinical validity or regulatory readiness.",
            "",
            "## Recommended manuscript action",
            "",
            "1. Lead the Abstract and Results with the corrected v5 experiment.",
            "2. Present the original experiment as a historical bundled comparison "
            "and label the full-response result according to the locked decision.",
            "3. Disclose both the inoperative scheduler and the first-4,000-character "
            "original judging limit next to the original result.",
            "4. Do not use the original experiment to claim routing superiority, "
            "even if its bundled framework contrast passes the retention rule.",
            "",
        ]
    )
    return "\n".join(lines)


def render_stats_appendix(analysis: Mapping[str, Any]) -> str:
    lines = [
        "# Original Experiment: Statistical Appendix",
        "",
        "## Full-response contrasts",
        "",
    ]
    for metric in METRICS:
        result = analysis["full_response"][metric]["contrasts"][PRIMARY_LABEL]
        low, high = result["ci_95"]
        adjusted = result.get("p_holm_dimensions")
        lines.extend(
            [
                f"### {metric.replace('dim_', '').replace('_', ' ').title()}",
                "",
                f"Framework−bare agent: {_fmt(result['mean_difference'])}; "
                f"95% CI [{_fmt(low)}, {_fmt(high)}]; exact P="
                f"{_fmt_p(result['p_exact_sign_flip'])}; paired dz="
                f"{_fmt(result['paired_dz'])}"
                + (
                    f"; Holm P across the three dimensions={_fmt_p(adjusted)}."
                    if adjusted is not None
                    else "."
                ),
                "",
            ]
        )
    lines.extend(
        [
            "## Leave-one-task-out primary sensitivity",
            "",
            "| Omitted task | Mean difference | Exact P |",
            "|---|---:|---:|",
        ]
    )
    for result in analysis["leave_one_task_out_primary"]:
        lines.append(
            f"| {result['omitted_task']} | "
            f"{_fmt(result['mean_difference'])} | "
            f"{_fmt_p(result['p_exact_sign_flip'])} |"
        )
    lines.extend(
        [
            "",
            "The exact sign-flip test assumes sign exchangeability under the null. "
            "Bootstrap intervals use 10,000 task-level resamples. The task, not "
            "the replicate run, is the inferential unit.",
            "",
        ]
    )
    return "\n".join(lines)


def plot_protocol_comparison(
    analysis: Mapping[str, Any], figure_dir: Path
) -> None:
    prefix = analysis["prefix_overall"]["condition_summary"]
    full = analysis["full_response"]["quality_score"]["condition_summary"]
    x_values = np.arange(len(CONDITIONS))
    width = 0.36
    figure, axis = plt.subplots(figsize=(7.5, 4.8))
    axis.bar(
        x_values - width / 2,
        [prefix[item]["mean"] for item in CONDITIONS],
        width,
        label="Original prefix judgment",
        color="#999999",
    )
    axis.bar(
        x_values + width / 2,
        [full[item]["mean"] for item in CONDITIONS],
        width,
        label="Full-response re-judgment",
        color="#0072B2",
    )
    axis.set_xticks(x_values)
    axis.set_xticklabels([LABELS[item] for item in CONDITIONS], rotation=18)
    axis.set_ylabel("Task-level mean quality score (1–5)")
    axis.set_ylim(1, 5)
    axis.legend(frameon=False)
    axis.spines["top"].set_visible(False)
    axis.spines["right"].set_visible(False)
    figure.tight_layout()
    _save_figure(figure, figure_dir / "figure-01-protocol-comparison")


def plot_primary_task_differences(
    analysis: Mapping[str, Any], figure_dir: Path
) -> None:
    full = analysis["full_response"]["quality_score"]["contrasts"][PRIMARY_LABEL]
    prefix = analysis["prefix_overall"]["contrasts"][PRIMARY_LABEL]
    tasks = list(full["tasks"])
    y_values = np.arange(len(tasks))
    figure, axis = plt.subplots(figsize=(8.0, 5.4))
    axis.scatter(
        prefix["task_differences"],
        y_values - 0.12,
        label="Original prefix judgment",
        color="#777777",
        marker="o",
    )
    axis.scatter(
        full["task_differences"],
        y_values + 0.12,
        label="Full-response re-judgment",
        color="#D55E00",
        marker="D",
    )
    axis.axvline(0, color="#222222", linewidth=0.8)
    axis.set_yticks(y_values)
    axis.set_yticklabels(tasks, fontsize=8)
    axis.set_xlabel("Framework − bare-agent task mean")
    axis.legend(frameon=False)
    axis.spines["top"].set_visible(False)
    axis.spines["right"].set_visible(False)
    figure.tight_layout()
    _save_figure(figure, figure_dir / "figure-02-task-differences")


def _save_figure(figure: plt.Figure, path_without_suffix: Path) -> None:
    figure.savefig(path_without_suffix.with_suffix(".pdf"), bbox_inches="tight")
    figure.savefig(
        path_without_suffix.with_suffix(".png"), dpi=600, bbox_inches="tight"
    )
    plt.close(figure)


def generate_bundle(
    data: Mapping[str, Any], analysis: Mapping[str, Any], output_dir: Path
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    figure_dir = output_dir / "figures"
    figure_dir.mkdir(parents=True, exist_ok=True)
    plot_protocol_comparison(analysis, figure_dir)
    plot_primary_task_differences(analysis, figure_dir)
    (output_dir / "analysis-summary.json").write_text(
        json.dumps(analysis, indent=2), encoding="utf-8"
    )
    (output_dir / "analysis-report.md").write_text(
        render_report(analysis), encoding="utf-8"
    )
    (output_dir / "stats-appendix.md").write_text(
        render_stats_appendix(analysis), encoding="utf-8"
    )
    (output_dir / "figure-catalog.md").write_text(
        "\n".join(
            [
                "# Original Experiment: Figure Catalog",
                "",
                f"Source SHA-256: `{analysis['source_sha256']}`",
                "",
                "## Figure 1 — Protocol comparison",
                "",
                "Task-level condition means under the preserved original "
                "first-4,000-character judgments and the locked full-response "
                "re-judgment. The comparison is descriptive because judge "
                "version/time also changed.",
                "",
                "## Figure 2 — Task-level primary contrasts",
                "",
                "Paired framework-minus-bare-agent task effects under both "
                "judging protocols. Individual tasks are descriptive; formal "
                "inference uses the complete vector of 10 paired task effects.",
                "",
            ]
        ),
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    data = json.loads(args.input.read_text(encoding="utf-8"))
    errors = validate_source(data)
    if errors:
        raise SystemExit("Source validation failed:\n- " + "\n- ".join(errors))
    analysis = build_analysis(data, sha256_file(args.input))
    if args.verify:
        expected = json.loads(
            (args.output_dir / "analysis-summary.json").read_text(
                encoding="utf-8"
            )
        )
        if analysis != expected:
            raise SystemExit("Verification failed: analysis did not recompute")
        print(f"Verified: {args.output_dir / 'analysis-summary.json'}")
        return
    generate_bundle(data, analysis, args.output_dir)
    print(f"Wrote analysis bundle: {args.output_dir}")


if __name__ == "__main__":
    main()
