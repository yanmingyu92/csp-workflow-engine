#!/usr/bin/env python3
"""Generate publication-ready tables and figures for corrected experiment v5."""

from __future__ import annotations

import argparse
import copy
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from experiments.analyze_corrected_experiment import (  # noqa: E402
    CONDITION_LABELS,
    holm_adjust,
    sha256_file,
)


CONDITION_ORDER = (
    "agent_only",
    "agent_domain_prompt_only",
    "agent_skills_random",
    "agent_skills_flat",
    "agent_framework",
    "agent_framework_distill",
)

COLORS = {
    "agent_only": "#777777",
    "agent_domain_prompt_only": "#56B4E9",
    "agent_skills_random": "#E69F00",
    "agent_skills_flat": "#CC79A7",
    "agent_framework": "#0072B2",
    "agent_framework_distill": "#009E73",
}

MARKERS = ("o", "s", "^", "D", "P", "X")


def validate_full_rejudged_source(data: Mapping[str, Any]) -> list[str]:
    """Refuse to publish a bundle from prefix-only or incomplete judgments."""
    errors = []
    metadata = data.get("metadata", {})
    if not metadata.get("rejudge_complete"):
        errors.append("full-response re-judgment is not marked complete")
    if metadata.get("response_judging_policy") != (
        "full_stored_response_no_character_truncation"
    ):
        errors.append("source is not a full-response judgment checkpoint")
    if len(data.get("results", [])) != 180:
        errors.append("source does not contain 180 scalar results")
    if len(data.get("pairwise_results", [])) != 90:
        errors.append("source does not contain 90 logical pair results")
    if len(data.get("pairwise_presentations", [])) != 180:
        errors.append("source does not contain 180 AB/BA presentations")
    if any(
        row.get("judge_parse_error")
        for row in data.get("pairwise_presentations", [])
    ):
        errors.append("at least one pairwise presentation is unparseable")
    if any(row.get("judge_parse_error") for row in data.get("results", [])):
        errors.append("at least one full-response scalar judgment is unparseable")
    return errors


def _contrast_label(condition_a: str, condition_b: str) -> str:
    return f"{condition_a}_minus_{condition_b}"


def _fmt_number(value: Any, digits: int = 2) -> str:
    if value is None:
        return "NA"
    value = float(value)
    if math.isnan(value):
        return "NA"
    return f"{value:.{digits}f}"


def _fmt_p(value: Any) -> str:
    if value is None:
        return "NA"
    value = float(value)
    if value < 0.001:
        return "<.001"
    return f"{value:.3f}".lstrip("0")


def _label(condition: str) -> str:
    return CONDITION_LABELS.get(condition, condition)


def add_exploratory_holm(
    mechanism: Mapping[str, Mapping[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    """Copy mechanism results and add a Holm-4 exploratory sensitivity column."""
    output = copy.deepcopy(dict(mechanism))
    raw_p = {
        label: float(result["p_exact_sign_flip"])
        for label, result in output.items()
        if result.get("p_exact_sign_flip") is not None
    }
    for label, adjusted in holm_adjust(raw_p).items():
        output[label]["p_holm_exploratory"] = adjusted
    return output


def summarize_pairwise_results(
    rows: Iterable[Mapping[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    """Summarize replicate-matched pairwise judgments by contrast."""
    grouped: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        condition_a = str(row["condition_a"])
        condition_b = str(row["condition_b"])
        label = _contrast_label(condition_a, condition_b)
        result = grouped.setdefault(
            label,
            {
                "condition_a": condition_a,
                "condition_b": condition_b,
                "n_total": 0,
                "n_valid": 0,
                "a_wins": 0,
                "b_wins": 0,
                "ties": 0,
                "discordant": 0,
                "errors": 0,
            },
        )
        result["n_total"] += 1
        winner = row.get("winner")
        if row.get("judge_parse_error") or winner not in {
            condition_a,
            condition_b,
            "tie",
            "discordant",
        }:
            result["errors"] += 1
            continue
        result["n_valid"] += 1
        if winner == condition_a:
            result["a_wins"] += 1
        elif winner == condition_b:
            result["b_wins"] += 1
        elif winner == "discordant":
            result["discordant"] += 1
        else:
            result["ties"] += 1

    for result in grouped.values():
        decisive = result["a_wins"] + result["b_wins"]
        result["a_win_rate_excluding_ties"] = (
            result["a_wins"] / decisive if decisive else None
        )
    return grouped


def summarize_resources(rows: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
    """Return descriptive resource-use summaries for each experimental arm."""
    fields = (
        "skills_count",
        "skills_tokens",
        "principles_count",
        "tokens_in",
        "tokens_out",
        "cost_usd",
    )
    grouped: Dict[str, Dict[str, list[float]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for row in rows:
        condition = str(row["condition"])
        for field in fields:
            if row.get(field) is not None:
                grouped[condition][field].append(float(row[field]))
    return {
        condition: {
            f"mean_{field}": float(np.mean(values))
            for field, values in metrics.items()
            if values
        }
        for condition, metrics in grouped.items()
    }


def integrity_summary(data: Mapping[str, Any]) -> Dict[str, Any]:
    """Compute compact integrity diagnostics from the immutable checkpoint."""
    rows = list(data.get("results", []))
    pairwise = list(data.get("pairwise_results", []))
    presentations = list(data.get("pairwise_presentations", []))
    run_keys = [row.get("run_key") for row in rows]
    pairwise_keys = [row.get("pairwise_key") for row in pairwise]
    return {
        "agent_results": len(rows),
        "pairwise_results": len(pairwise),
        "pairwise_presentations": len(presentations),
        "tasks": len({row.get("task_id") for row in rows}),
        "conditions": sorted({str(row.get("condition")) for row in rows}),
        "runs_per_cell": sorted({int(row.get("run_id", -1)) for row in rows}),
        "agent_errors": sum(bool(row.get("is_error_response")) for row in rows),
        "agent_judge_parse_errors": sum(
            row.get("judge_parse_error") is not None for row in rows
        ),
        "pairwise_judge_parse_errors": sum(
            row.get("judge_parse_error") is not None
            for row in (presentations or pairwise)
        ),
        "nonisolated_runs": sum(
            not bool(row.get("isolated_working_directory")) for row in rows
        ),
        "duplicate_run_keys": len(run_keys) - len(set(run_keys)),
        "duplicate_pairwise_keys": len(pairwise_keys) - len(set(pairwise_keys)),
        "agent_models_returned": sorted(
            {str(row.get("agent_model_returned")) for row in rows}
        ),
        "judge_models_returned": sorted(
            {
                str(row.get("judge_model_returned"))
                for row in rows + (presentations or pairwise)
                if row.get("judge_model_returned")
            }
        ),
        "total_cost_usd": float(
            data.get("metadata", {}).get("cumulative_cost_usd")
            or data.get("metadata", {}).get("total_cost")
            or sum(float(row.get("cost_usd", 0)) for row in rows)
        ),
    }


def _bootstrap_mean_ci(
    values: Sequence[float], seed: int, n_boot: int = 10_000
) -> tuple[float, float]:
    array = np.asarray(values, dtype=float)
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, len(array), size=(n_boot, len(array)))
    means = array[draws].mean(axis=1)
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def _style_axes(axis: plt.Axes) -> None:
    axis.spines["top"].set_visible(False)
    axis.spines["right"].set_visible(False)
    axis.grid(axis="y", color="#D9D9D9", linewidth=0.7, alpha=0.8)
    axis.set_axisbelow(True)


def plot_condition_comparison(
    primary: Mapping[str, Any], output_dir: Path, seed: int
) -> None:
    """Plot task-level arm values with descriptive task-bootstrap intervals."""
    task_means = primary["task_means"]
    figure, axis = plt.subplots(figsize=(8.4, 5.0))
    rng = np.random.default_rng(seed)
    for index, condition in enumerate(CONDITION_ORDER):
        values = np.asarray(list(task_means[condition].values()), dtype=float)
        jitter = rng.uniform(-0.10, 0.10, size=len(values))
        axis.scatter(
            np.full(len(values), index) + jitter,
            values,
            marker=MARKERS[index],
            s=34,
            facecolor="white",
            edgecolor=COLORS[condition],
            linewidth=1.2,
            alpha=0.9,
            zorder=3,
        )
        mean = float(values.mean())
        low, high = _bootstrap_mean_ci(values, seed + index)
        axis.errorbar(
            index,
            mean,
            yerr=[[mean - low], [high - mean]],
            fmt="D",
            markersize=6,
            color=COLORS[condition],
            markeredgecolor="black",
            markeredgewidth=0.5,
            capsize=4,
            linewidth=1.8,
            zorder=4,
        )
    axis.set_xticks(range(len(CONDITION_ORDER)))
    axis.set_xticklabels([_label(item) for item in CONDITION_ORDER], rotation=24, ha="right")
    axis.set_ylabel("Task-level mean quality score (1–5)")
    axis.set_ylim(2.45, 4.85)
    axis.set_title("Corrected six-arm experiment: task-level performance")
    _style_axes(axis)
    figure.text(
        0.01,
        0.01,
        "Open symbols: individual tasks; diamonds and bars: mean and descriptive 95% task-bootstrap CI.",
        fontsize=8,
        color="#444444",
    )
    figure.tight_layout(rect=(0, 0.05, 1, 1))
    _save_figure(figure, output_dir / "figure-01-condition-comparison")


def plot_task_contrast_heatmap(
    primary: Mapping[str, Any], output_dir: Path
) -> None:
    """Plot per-task differences for routing and distillation contrasts."""
    contrasts = (
        ("agent_framework", "agent_domain_prompt_only"),
        ("agent_framework", "agent_skills_flat"),
        ("agent_framework", "agent_skills_random"),
        ("agent_framework_distill", "agent_framework"),
    )
    task_means = primary["task_means"]
    tasks = sorted(task_means["agent_framework"])
    values = np.asarray(
        [
            [task_means[a][task] - task_means[b][task] for a, b in contrasts]
            for task in tasks
        ],
        dtype=float,
    )
    maximum = max(0.5, float(np.max(np.abs(values))))
    color_map = LinearSegmentedColormap.from_list(
        "difference", ("#0072B2", "#F7F7F7", "#D55E00")
    )
    figure, axis = plt.subplots(figsize=(8.2, 5.4))
    image = axis.imshow(
        values,
        aspect="auto",
        cmap=color_map,
        norm=TwoSlopeNorm(vmin=-maximum, vcenter=0, vmax=maximum),
    )
    axis.set_xticks(range(len(contrasts)))
    axis.set_xticklabels(
        [
            "APS − prompt",
            "APS − flat",
            "APS − random",
            "APS+principles − APS",
        ],
        rotation=20,
        ha="right",
    )
    axis.set_yticks(range(len(tasks)))
    axis.set_yticklabels(tasks, fontsize=8)
    for row_index in range(values.shape[0]):
        for column_index in range(values.shape[1]):
            value = values[row_index, column_index]
            axis.text(
                column_index,
                row_index,
                f"{value:+.2f}",
                ha="center",
                va="center",
                fontsize=7.5,
                color="white" if abs(value) > maximum * 0.58 else "#222222",
            )
    color_bar = figure.colorbar(image, ax=axis, shrink=0.82, pad=0.03)
    color_bar.set_label("Task-level mean difference")
    axis.set_title("Heterogeneity of task-level mechanism contrasts")
    figure.tight_layout()
    _save_figure(figure, output_dir / "figure-02-task-contrast-heatmap")


def _save_figure(figure: plt.Figure, path_without_suffix: Path) -> None:
    metadata = {
        "Title": path_without_suffix.name,
        "Author": "Corrected Experiment v5 analysis pipeline",
        "Subject": "Task-paired ablation analysis",
    }
    figure.savefig(
        path_without_suffix.with_suffix(".pdf"),
        bbox_inches="tight",
        metadata=metadata,
    )
    figure.savefig(
        path_without_suffix.with_suffix(".png"),
        dpi=600,
        bbox_inches="tight",
    )
    plt.close(figure)


def _contrast_rows(results: Mapping[str, Mapping[str, Any]], adjusted: bool) -> list[str]:
    lines = []
    for result in results.values():
        low, high = result["ci_95"]
        columns = [
            f"{_label(result['condition_a'])} − {_label(result['condition_b'])}",
            str(result["n_tasks"]),
            _fmt_number(result["mean_difference"]),
            f"[{_fmt_number(low)}, {_fmt_number(high)}]",
            _fmt_p(result["p_exact_sign_flip"]),
        ]
        if adjusted:
            columns.append(_fmt_p(result.get("p_holm")))
        else:
            columns.append(_fmt_p(result.get("p_holm_exploratory")))
        columns.append(_fmt_number(result["paired_dz"]))
        lines.append("| " + " | ".join(columns) + " |")
    return lines


def render_analysis_report(
    report: Mapping[str, Any],
    integrity: Mapping[str, Any],
    pairwise: Mapping[str, Mapping[str, Any]],
    mechanism: Mapping[str, Mapping[str, Any]],
) -> str:
    primary = report["analyses"]["intention_to_run"]["quality_score"]
    condition = primary["condition_summary"]
    aps_flat = primary["confirmatory"][
        _contrast_label("agent_framework", "agent_skills_flat")
    ]
    aps_random = primary["confirmatory"][
        _contrast_label("agent_framework", "agent_skills_random")
    ]
    distill = mechanism[
        _contrast_label("agent_framework_distill", "agent_framework")
    ]
    routing_supported = (
        aps_flat["mean_difference"] > 0
        and aps_random["mean_difference"] > 0
        and aps_flat["p_holm"] < 0.05
        and aps_random["p_holm"] < 0.05
    )
    routing_decision = (
        "The prespecified routing-superiority hypothesis is **supported** against "
        "both corpus controls in this re-judged experiment."
        if routing_supported
        else "The prespecified routing-superiority hypothesis is **not supported**. "
        "The manuscript must not attribute outcome-quality gains to routing."
    )
    distill_supported = (
        distill["mean_difference"] > 0
        and distill.get("p_holm_exploratory", 1) < 0.05
    )
    distill_decision = (
        "Adding distilled principles produced a positive exploratory mechanism "
        "signal after Holm-4 sensitivity adjustment."
        if distill_supported
        else "Adding distilled principles did not produce a multiplicity-adjusted "
        "exploratory signal in this re-judged analysis."
    )
    lines = [
        "# Corrected Experiment v5: Analysis Report",
        "",
        f"Immutable source SHA-256: `{report['source_sha256']}`  ",
        f"Analysis version: `{report['analysis_version']}`  ",
        "Experimental unit: task (10 tasks; 3 replicates averaged within each task-condition cell)",
        "",
        "## Decision",
        "",
        routing_decision,
        "",
        distill_decision
        + " Mechanism contrasts were exploratory and require independent confirmation.",
        "",
        "## Observation",
        "",
        f"Corrected APS averaged {_fmt_number(condition['agent_framework']['mean'])}; flat corpus loading averaged {_fmt_number(condition['agent_skills_flat']['mean'])}; random corpus loading averaged {_fmt_number(condition['agent_skills_random']['mean'])}; and APS plus distilled principles averaged {_fmt_number(condition['agent_framework_distill']['mean'])}.",
        "",
        "Figure 1 shows the task-level distributions. Figure 2 shows the signs and magnitudes of each task-level mechanism contrast.",
        "",
        "## Confirmatory support",
        "",
        "P values are exact two-sided sign-flip tests over paired task differences. Holm adjustment covers the three prespecified overall-score contrasts.",
        "",
        "| Contrast (A − B) | Tasks | Mean difference | 95% paired-bootstrap CI | Exact P | Holm P | paired dz |",
        "|---|---:|---:|---:|---:|---:|---:|",
        *_contrast_rows(primary["confirmatory"], adjusted=True),
        "",
        f"The APS−flat estimate was {_fmt_number(aps_flat['mean_difference'])} points (Holm P={_fmt_p(aps_flat['p_holm'])}); the APS−random estimate was {_fmt_number(aps_random['mean_difference'])} points (Holm P={_fmt_p(aps_random['p_holm'])}).",
        "",
        "## Exploratory mechanism support",
        "",
        "The Holm-4 column is a sensitivity adjustment across all four mechanism contrasts; these tests were not part of the confirmatory family.",
        "",
        "| Contrast (A − B) | Tasks | Mean difference | 95% paired-bootstrap CI | Exact P | Holm-4 P | paired dz |",
        "|---|---:|---:|---:|---:|---:|---:|",
        *_contrast_rows(mechanism, adjusted=False),
        "",
        f"The APS+principles contrast was {_fmt_number(distill['mean_difference'])} points (exploratory Holm-4 P={_fmt_p(distill['p_holm_exploratory'])}).",
        "",
        "## Pairwise-judge sensitivity",
        "",
        "Each replicate-matched pair was presented in both AB and BA order. Only one conservative logical result is counted per pair; order-discordant judgments are reported separately. This sensitivity analysis does not replace task-level confirmatory inference.",
        "",
        "| Contrast | Valid | A wins | B wins | Ties | Order-discordant | Errors | A win rate excluding ties and discordance |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for result in pairwise.values():
        win_rate = result["a_win_rate_excluding_ties"]
        lines.append(
            f"| {_label(result['condition_a'])} vs {_label(result['condition_b'])} | "
            f"{result['n_valid']} | {result['a_wins']} | {result['b_wins']} | "
            f"{result['ties']} | {result['discordant']} | {result['errors']} | "
            f"{_fmt_number(win_rate, 3) if win_rate is not None else 'NA'} |"
        )
    lines.extend(
        [
            "",
            "## Boundary conditions",
            "",
            "- The inferential sample is 10 tasks, not 30 replicate runs. Exact tests are consequently discrete and power is limited.",
            "- Percentile bootstrap CIs and exact sign-flip P values answer related but nonidentical questions; an interval excluding zero can coexist with a nonsignificant discrete exact test. Decisions here follow the prespecified exact test and Holm family.",
            "- Scores came from one automated judge version (`deepseek-v4-flash`) applied consistently across all arms. No human-expert outcome assessment was performed.",
            "- The experiment supports statements about this benchmark, backbone, prompts, and skill corpus only. It does not establish clinical validity or regulatory readiness.",
            "- Corrected APS and flat loading used essentially the same deterministic skill-context budget in this run. Do not claim context-token savings versus flat; routing may still be discussed as an auditability or selection mechanism.",
            "",
            "## Integrity snapshot",
            "",
            f"The checkpoint contains {integrity['agent_results']} agent results, {integrity['pairwise_results']} logical pair results, and {integrity['pairwise_presentations']} pairwise presentations. Agent errors: {integrity['agent_errors']}; multidimensional-judge parse errors: {integrity['agent_judge_parse_errors']}; pairwise-judge parse errors: {integrity['pairwise_judge_parse_errors']}; duplicate run keys: {integrity['duplicate_run_keys']}; nonisolated working directories: {integrity['nonisolated_runs']}. Returned models were {', '.join(integrity['agent_models_returned'])} and {', '.join(integrity['judge_models_returned'])}. Cumulative recorded cost was ${integrity['total_cost_usd']:.6f}.",
            "",
            "## Manuscript action",
            "",
            "1. Align every routing claim with the confirmatory gate reported above; do not generalize beyond the tested benchmark and model.",
            "2. Report corpus and principle-distillation contrasts with their estimates and multiplicity status, without implying unsupported component benefits.",
            "3. Remove the context-token-savings claim versus flat loading; retain only accurately measured auditability and selection-behavior claims.",
            "4. Add the corrected v5 checkpoint, analysis script, source hash, exact-test specification, and judge-version disclosure to the reproducibility materials before resubmission.",
            "",
        ]
    )
    return "\n".join(lines)


def render_stats_appendix(
    report: Mapping[str, Any],
    pairwise: Mapping[str, Mapping[str, Any]],
    resources: Mapping[str, Mapping[str, float]],
    mechanism: Mapping[str, Mapping[str, Any]],
) -> str:
    analyses = report["analyses"]["intention_to_run"]
    primary = analyses["quality_score"]
    lines = [
        "# Corrected Experiment v5: Statistical Appendix",
        "",
        "## Prespecified analysis",
        "",
        "Replicates were averaged within each task-condition cell. The task was the inferential unit. Overall quality used paired task differences, 10,000-resample percentile bootstrap intervals, exact two-sided sign-flip P values, and paired standardized mean differences (dz). Holm adjustment controlled the family-wise error rate across three confirmatory routing contrasts. Failed agent calls would receive score 1 under intention-to-run analysis; no such failures occurred.",
        "",
        "## Task-level condition summaries",
        "",
        "| Condition | Tasks | Mean | SD across tasks |",
        "|---|---:|---:|---:|",
    ]
    for condition in CONDITION_ORDER:
        result = primary["condition_summary"][condition]
        lines.append(
            f"| {_label(condition)} | {result['n_tasks']} | {_fmt_number(result['mean'])} | {_fmt_number(result['sd_across_tasks'])} |"
        )
    lines.extend(
        [
            "",
            "## Confirmatory overall-score contrasts",
            "",
            "| Contrast (A − B) | Tasks | Mean difference | 95% paired-bootstrap CI | Exact P | Holm P | paired dz |",
            "|---|---:|---:|---:|---:|---:|---:|",
            *_contrast_rows(primary["confirmatory"], adjusted=True),
            "",
            "## Exploratory mechanism contrasts",
            "",
            "| Contrast (A − B) | Tasks | Mean difference | 95% paired-bootstrap CI | Exact P | Holm-4 sensitivity P | paired dz |",
            "|---|---:|---:|---:|---:|---:|---:|",
            *_contrast_rows(mechanism, adjusted=False),
            "",
            "## Dimension-level sensitivity results",
            "",
        ]
    )
    for metric in ("dim_completeness", "dim_terminology", "dim_structure"):
        lines.extend(
            [
                f"### {metric.replace('dim_', '').title()}",
                "",
                "| Contrast (A − B) | Tasks | Mean difference | 95% paired-bootstrap CI | Exact P | paired dz |",
                "|---|---:|---:|---:|---:|---:|",
            ]
        )
        for result in analyses[metric]["confirmatory"].values():
            low, high = result["ci_95"]
            lines.append(
                f"| {_label(result['condition_a'])} − {_label(result['condition_b'])} | "
                f"{result['n_tasks']} | {_fmt_number(result['mean_difference'])} | "
                f"[{_fmt_number(low)}, {_fmt_number(high)}] | "
                f"{_fmt_p(result['p_exact_sign_flip'])} | {_fmt_number(result['paired_dz'])} |"
            )
        lines.append("")
    lines.extend(
        [
            "## Pairwise-judge descriptive sensitivity",
            "",
            "| Contrast | Total | Valid | A wins | B wins | Ties | Order-discordant | Errors |",
            "|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for result in pairwise.values():
        lines.append(
            f"| {_label(result['condition_a'])} vs {_label(result['condition_b'])} | "
            f"{result['n_total']} | {result['n_valid']} | {result['a_wins']} | "
            f"{result['b_wins']} | {result['ties']} | {result['discordant']} | "
            f"{result['errors']} |"
        )
    lines.extend(
        [
            "",
            "## Descriptive resource use",
            "",
            "| Condition | Skills | Skill-context tokens | Principles | Agent input tokens | Agent output tokens | Cost/run (USD) |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for condition in CONDITION_ORDER:
        result = resources[condition]
        lines.append(
            f"| {_label(condition)} | {_fmt_number(result.get('mean_skills_count'), 1)} | "
            f"{_fmt_number(result.get('mean_skills_tokens'), 1)} | "
            f"{_fmt_number(result.get('mean_principles_count'), 1)} | "
            f"{_fmt_number(result.get('mean_tokens_in'), 1)} | "
            f"{_fmt_number(result.get('mean_tokens_out'), 1)} | "
            f"{_fmt_number(result.get('mean_cost_usd'), 4)} |"
        )
    lines.extend(
        [
            "",
            "## Sensitivity and interpretation notes",
            "",
            "The complete-case analysis is numerically identical to intention-to-run because no agent or judge parse failures occurred. Dimension-level P values are unadjusted descriptive sensitivity results. No normality assumption is required for the exact sign-flip test, but exchangeability of signs under the null and representativeness of the 10 benchmark tasks remain substantive assumptions.",
            "",
        ]
    )
    return "\n".join(lines)


def render_figure_catalog(source_hash: str) -> str:
    return "\n".join(
        [
            "# Corrected Experiment v5: Figure Catalog",
            "",
            f"Source checkpoint SHA-256: `{source_hash}`",
            "",
            "## Figure 1 — Task-level condition comparison",
            "",
            "- Files: `figures/figure-01-condition-comparison.pdf` and `.png` (600 dpi).",
            "- Purpose: show the six-arm score distributions without treating replicate runs as independent observations.",
            "- Data: replicate-averaged task means for overall quality (10 tasks per arm).",
            "- Encoding: open symbols are tasks; filled diamonds and bars are arm means and descriptive 95% task-bootstrap intervals.",
            "- Key observation: the plot exposes arm-level overlap and task dispersion; formal routing conclusions come from paired contrasts, not visual rank alone.",
            "- Caveat: between-arm inference must use paired contrasts in the statistical appendix, not overlap of descriptive arm intervals.",
            "",
            "Suggested caption: **Figure 1. Task-level quality scores in the corrected six-arm ablation experiment.** Three replicate scores were averaged within each task-condition cell. Open symbols show the 10 task means per condition; diamonds and error bars show the condition mean and descriptive 95% task-bootstrap interval. Confirmatory inference used paired task differences and exact sign-flip tests with Holm adjustment (Table X).",
            "",
            "## Figure 2 — Task-level contrast heatmap",
            "",
            "- Files: `figures/figure-02-task-contrast-heatmap.pdf` and `.png` (600 dpi).",
            "- Purpose: expose heterogeneity hidden by aggregate means and identify whether effects are consistently signed across tasks.",
            "- Data: paired task differences for APS−prompt, APS−flat, APS−random, and APS+principles−APS.",
            "- Encoding: blue is negative, orange is positive, and each cell is annotated with its score difference.",
            "- Key observation: the plot reveals task-level heterogeneity and whether contrast signs are consistent; formal evidence is reported in the exact-test table.",
            "- Caveat: task-specific cells are descriptive and are not separate hypothesis tests.",
            "",
            "Suggested caption: **Figure 2. Heterogeneity of task-level mechanism contrasts.** Cells show replicate-averaged paired score differences for each benchmark task. Positive values favor the first-named condition. The heatmap is descriptive; formal inference was conducted over the vector of 10 paired task differences.",
            "",
            "## Visual quality checklist",
            "",
            "- Colorblind-safe blue/orange/green palette and redundant marker shapes are used.",
            "- Axes, units, experimental unit, and uncertainty encoding are explicit.",
            "- Vector PDF is the submission master; 600-dpi PNG is provided for systems requiring raster upload.",
            "- No causal or significance annotation is embedded in the figures.",
            "",
        ]
    )


def build_summary(
    data: Mapping[str, Any], report: Mapping[str, Any]
) -> Dict[str, Any]:
    primary = report["analyses"]["intention_to_run"]["quality_score"]
    return {
        "analysis_version": "v5-publication-bundle-1",
        "source_sha256": report["source_sha256"],
        "integrity": integrity_summary(data),
        "confirmatory": primary["confirmatory"],
        "mechanism_with_holm4": add_exploratory_holm(primary["mechanism"]),
        "pairwise": summarize_pairwise_results(data.get("pairwise_results", [])),
        "resources": summarize_resources(data.get("results", [])),
    }


def generate_bundle(
    data: Mapping[str, Any], report: Mapping[str, Any], output_dir: Path
) -> Dict[str, Any]:
    source_errors = validate_full_rejudged_source(data)
    if source_errors:
        raise ValueError("; ".join(source_errors))
    output_dir.mkdir(parents=True, exist_ok=True)
    figure_dir = output_dir / "figures"
    figure_dir.mkdir(parents=True, exist_ok=True)
    summary = build_summary(data, report)
    primary = report["analyses"]["intention_to_run"]["quality_score"]
    plot_condition_comparison(primary, figure_dir, int(report["seed"]))
    plot_task_contrast_heatmap(primary, figure_dir)
    (output_dir / "analysis-report.md").write_text(
        render_analysis_report(
            report,
            summary["integrity"],
            summary["pairwise"],
            summary["mechanism_with_holm4"],
        ),
        encoding="utf-8",
    )
    (output_dir / "stats-appendix.md").write_text(
        render_stats_appendix(
            report,
            summary["pairwise"],
            summary["resources"],
            summary["mechanism_with_holm4"],
        ),
        encoding="utf-8",
    )
    (output_dir / "figure-catalog.md").write_text(
        render_figure_catalog(str(report["source_sha256"])), encoding="utf-8"
    )
    (output_dir / "analysis-summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()

    data = json.loads(args.input.read_text(encoding="utf-8"))
    report = json.loads(args.report.read_text(encoding="utf-8"))
    source_errors = validate_full_rejudged_source(data)
    if source_errors:
        raise SystemExit(
            "Refusing publication bundle:\n- " + "\n- ".join(source_errors)
        )
    actual_hash = sha256_file(args.input)
    if actual_hash != report.get("source_sha256"):
        raise SystemExit("Source checkpoint hash does not match the analysis report")
    expected = build_summary(data, report)
    if args.verify:
        stored_path = args.output_dir / "analysis-summary.json"
        stored = json.loads(stored_path.read_text(encoding="utf-8"))
        if stored != expected:
            raise SystemExit("Verification failed: bundle summary does not recompute exactly")
        required = (
            "analysis-report.md",
            "stats-appendix.md",
            "figure-catalog.md",
            "figures/figure-01-condition-comparison.pdf",
            "figures/figure-01-condition-comparison.png",
            "figures/figure-02-task-contrast-heatmap.pdf",
            "figures/figure-02-task-contrast-heatmap.png",
        )
        missing = [name for name in required if not (args.output_dir / name).is_file()]
        if missing:
            raise SystemExit(f"Verification failed: missing outputs: {missing}")
        print(f"Verified analysis bundle: {args.output_dir}")
        return
    generate_bundle(data, report, args.output_dir)
    print(f"Wrote analysis bundle: {args.output_dir}")


if __name__ == "__main__":
    main()
