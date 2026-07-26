"""Deterministic English reports and SVG figures for the V7 oracle audit."""

from __future__ import annotations

import html
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

from experiments.v7_oracle_regulatory_alignment import (
    ACCESSED_DATE,
    ALIGNMENT_ROWS,
    FDA_SOURCES,
)


GRAPH = "graph_bm25_chunk_optimized"
BM25 = "full_corpus_bm25_token_matched"
GRAPH_LABEL = "Graph + BM25"
BM25_LABEL = "BM25 only"
BLUE = "#0072B2"
ORANGE = "#E69F00"
GREEN = "#009E73"
VERMILION = "#D55E00"
GRAY = "#666666"


def _fmt(value: Any, digits: int = 4) -> str:
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (int, float)):
        return f"{float(value):.{digits}f}"
    return str(value)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8", newline="\n")


def _svg_document(
    *,
    title: str,
    description: str,
    body: Sequence[str],
    width: int,
    height: int,
) -> str:
    escaped_title = html.escape(title)
    escaped_description = html.escape(description)
    lines = [
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
            f'height="{height}" viewBox="0 0 {width} {height}" '
            'role="img" aria-labelledby="title desc">'
        ),
        f'<title id="title">{escaped_title}</title>',
        f'<desc id="desc">{escaped_description}</desc>',
        "<style>",
        (
            "text{font-family:Arial,sans-serif;fill:#222}"
            ".title{font-size:20px;font-weight:700}"
            ".label{font-size:12px}.tick{font-size:10px;fill:#555}"
            ".grid{stroke:#ddd;stroke-width:1}.axis{stroke:#333;stroke-width:1.2}"
        ),
        "</style>",
        *body,
        "</svg>",
    ]
    return "\n".join(lines)


def _figure_oracle_retrieval(payload: Mapping[str, Any]) -> str:
    aggregates = payload["arm_aggregates"]
    metrics = (
        ("Required-section recall", "required_section_recall"),
        ("Required-section precision", "required_section_precision"),
        ("Required-token precision", "required_token_precision"),
        ("Irrelevant-token ratio", "irrelevant_token_ratio"),
        ("Redundancy", "redundancy"),
    )
    width, height = 920, 440
    left, top, plot_width = 225, 72, 620
    row_height = 58
    body = [
        (
            '<text x="30" y="34" class="title">'
            "Held-out oracle retrieval diagnostics</text>"
        ),
    ]
    for tick in range(0, 11, 2):
        x = left + plot_width * tick / 10
        body.append(
            f'<line x1="{x:.1f}" y1="{top - 15}" x2="{x:.1f}" '
            f'y2="{top + row_height * len(metrics)}" class="grid"/>'
        )
        body.append(
            f'<text x="{x:.1f}" y="{top - 22}" text-anchor="middle" '
            f'class="tick">{tick / 10:.1f}</text>'
        )
    for index, (label, key) in enumerate(metrics):
        y = top + index * row_height
        graph_value = float(aggregates[GRAPH][key])
        bm25_value = float(aggregates[BM25][key])
        body.extend(
            [
                (
                    f'<text x="{left - 12}" y="{y + 19}" '
                    f'text-anchor="end" class="label">{html.escape(label)}</text>'
                ),
                (
                    f'<rect x="{left}" y="{y}" width="{plot_width * graph_value:.2f}" '
                    f'height="16" fill="{BLUE}"/>'
                ),
                (
                    f'<rect x="{left}" y="{y + 21}" '
                    f'width="{plot_width * bm25_value:.2f}" height="16" '
                    f'fill="{ORANGE}"/>'
                ),
                (
                    f'<text x="{left + plot_width * graph_value + 5:.2f}" '
                    f'y="{y + 12}" class="tick">{graph_value:.3f}</text>'
                ),
                (
                    f'<text x="{left + plot_width * bm25_value + 5:.2f}" '
                    f'y="{y + 33}" class="tick">{bm25_value:.3f}</text>'
                ),
            ]
        )
    legend_y = height - 32
    body.extend(
        [
            (
                f'<rect x="300" y="{legend_y - 11}" width="18" '
                f'height="12" fill="{BLUE}"/>'
            ),
            f'<text x="325" y="{legend_y}" class="label">{GRAPH_LABEL}</text>',
            (
                f'<rect x="505" y="{legend_y - 11}" width="18" '
                f'height="12" fill="{ORANGE}"/>'
            ),
            f'<text x="530" y="{legend_y}" class="label">{BM25_LABEL}</text>',
        ]
    )
    return _svg_document(
        title="Held-out oracle retrieval diagnostics",
        description=(
            "Grouped bars compare graph plus BM25 with BM25 only on required "
            "evidence recall, precision, irrelevant tokens, and redundancy."
        ),
        body=body,
        width=width,
        height=height,
    )


def _figure_error_decomposition(payload: Mapping[str, Any]) -> str:
    taxonomy = payload["error_taxonomy"]
    classes = list(taxonomy["classes"])
    counts = taxonomy["arm_error_counts"]
    maximum = max(
        [int(counts[arm].get(name, 0)) for arm in (GRAPH, BM25) for name in classes]
        or [1]
    )
    width = 1040
    height = 125 + 48 * len(classes)
    left, plot_width = 300, 650
    body = [
        '<text x="30" y="34" class="title">Criterion-level error decomposition</text>',
    ]
    for index, name in enumerate(classes):
        y = 72 + 48 * index
        graph_count = int(counts[GRAPH].get(name, 0))
        bm25_count = int(counts[BM25].get(name, 0))
        graph_width = plot_width * graph_count / maximum
        bm25_width = plot_width * bm25_count / maximum
        body.extend(
            [
                (
                    f'<text x="{left - 12}" y="{y + 17}" text-anchor="end" '
                    f'class="label">{html.escape(name)}</text>'
                ),
                (
                    f'<rect x="{left}" y="{y}" width="{graph_width:.2f}" '
                    f'height="15" fill="{BLUE}"/>'
                ),
                (
                    f'<rect x="{left}" y="{y + 19}" width="{bm25_width:.2f}" '
                    f'height="15" fill="{ORANGE}"/>'
                ),
                (
                    f'<text x="{left + graph_width + 5:.2f}" y="{y + 12}" '
                    f'class="tick">{graph_count}</text>'
                ),
                (
                    f'<text x="{left + bm25_width + 5:.2f}" y="{y + 31}" '
                    f'class="tick">{bm25_count}</text>'
                ),
            ]
        )
    return _svg_document(
        title="Criterion-level error decomposition",
        description=(
            "Graph plus BM25 and BM25-only failure counts under the mutually "
            "exclusive deterministic error taxonomy."
        ),
        body=body,
        width=width,
        height=height,
    )


def _scaled(value: float, minimum: float, maximum: float, span: float) -> float:
    if maximum == minimum:
        return span / 2
    return (value - minimum) / (maximum - minimum) * span


def _figure_evidence_output_delta(payload: Mapping[str, Any]) -> str:
    task_rows = payload["graph_vs_bm25_oracle_delta"]["task_level"]
    x_values = [float(row["required_section_recall_delta"]) for row in task_rows]
    y_values = [float(row["deterministic_score_delta"]) for row in task_rows]
    x_bound = max([abs(value) for value in x_values] or [0.0]) + 0.02
    y_bound = max([abs(value) for value in y_values] or [0.0]) + 0.02
    x_min, x_max = -x_bound, x_bound
    y_min, y_max = -y_bound, y_bound
    width, height = 820, 620
    left, top, span_x, span_y = 105, 70, 620, 450
    zero_x = left + _scaled(0.0, x_min, x_max, span_x)
    zero_y = top + span_y - _scaled(0.0, y_min, y_max, span_y)
    body = [
        '<text x="30" y="34" class="title">Evidence delta versus output delta</text>',
        (
            f'<line x1="{left}" y1="{zero_y:.2f}" x2="{left + span_x}" '
            f'y2="{zero_y:.2f}" class="axis"/>'
        ),
        (
            f'<line x1="{zero_x:.2f}" y1="{top}" x2="{zero_x:.2f}" '
            f'y2="{top + span_y}" class="axis"/>'
        ),
    ]
    overlapping = Counter(
        (
            round(float(row["required_section_recall_delta"]), 12),
            round(float(row["deterministic_score_delta"]), 12),
        )
        for row in task_rows
    )
    offsets: Counter[tuple[float, float]] = Counter()
    for row in task_rows:
        raw_x = float(row["required_section_recall_delta"])
        raw_y = float(row["deterministic_score_delta"])
        key = (round(raw_x, 12), round(raw_y, 12))
        occurrence = offsets[key]
        offsets[key] += 1
        jitter = (occurrence - (overlapping[key] - 1) / 2) * 4
        x = left + _scaled(raw_x, x_min, x_max, span_x) + jitter
        y = top + span_y - _scaled(raw_y, y_min, y_max, span_y)
        body.append(
            f'<circle cx="{x:.2f}" cy="{y:.2f}" r="5" fill="{GREEN}" '
            'fill-opacity="0.78"/>'
        )
    body.extend(
        [
            (
                f'<text x="{left + span_x / 2}" y="{height - 45}" '
                'text-anchor="middle" class="label">Graph minus BM25 '
                "required-section recall</text>"
            ),
            (
                f'<text x="24" y="{top + span_y / 2}" text-anchor="middle" '
                f'class="label" transform="rotate(-90 24 {top + span_y / 2})">'
                "Graph minus BM25 deterministic score</text>"
            ),
            (
                f'<text x="{left}" y="{height - 18}" class="tick">'
                "Each point is one held-out task mean across three repetitions. "
                "Horizontal jitter reveals exact overlaps.</text>"
            ),
        ]
    )
    return _svg_document(
        title="Evidence delta versus output delta",
        description=(
            "Task-level graph-minus-BM25 required-evidence recall differences "
            "against deterministic output-score differences."
        ),
        body=body,
        width=width,
        height=height,
    )


def _arm_table(payload: Mapping[str, Any]) -> list[str]:
    aggregates = payload["arm_aggregates"]
    lines = [
        "| Metric | Graph + BM25 | BM25 only |",
        "|---|---:|---:|",
    ]
    for label, key in (
        ("Deterministic score", "deterministic_score_mean"),
        ("Required-section recall", "required_section_recall"),
        ("Required-section precision", "required_section_precision"),
        ("Required-token precision", "required_token_precision"),
        ("Dependency coverage", "dependency_coverage"),
        ("Topology alignment", "topology_alignment"),
        ("Irrelevant-token ratio", "irrelevant_token_ratio"),
        ("Redundancy", "redundancy"),
        ("Version selection correctness", "version_selection_correctness"),
        (
            "Version/conflict output correctness",
            "version_conflict_output_correctness",
        ),
        ("Provenance completeness", "provenance_completeness"),
        ("Correct citation rate", "correct_citation_rate"),
    ):
        if key not in aggregates[GRAPH] or key not in aggregates[BM25]:
            continue
        lines.append(
            f"| {label} | {_fmt(aggregates[GRAPH][key])} | "
            f"{_fmt(aggregates[BM25][key])} |"
        )
    return lines


def _uncertainty_table(payload: Mapping[str, Any]) -> list[str]:
    uncertainty = payload["graph_vs_bm25_oracle_delta"]["uncertainty"]
    lines = [
        "| Task-level graph minus BM25 estimand | Mean | Bootstrap 95% CI | "
        "LOO range | LOO sign changes |",
        "|---|---:|---:|---:|---:|",
    ]
    labels = {
        "required_section_recall_delta": "Required-section recall",
        "required_section_precision_delta": "Required-section precision",
        "required_token_precision_delta": "Required-token precision",
        "deterministic_score_delta": "Deterministic output score",
        "substantive_score_excluding_provenance_delta": (
            "Output score excluding provenance criterion"
        ),
    }
    for key, label in labels.items():
        if key not in uncertainty:
            continue
        row = uncertainty[key]
        ci = row["bootstrap_95_ci"]
        loo = row["loo"]
        lines.append(
            f"| {label} | {_fmt(row['mean'])} | "
            f"[{_fmt(ci[0])}, {_fmt(ci[1])}] | "
            f"[{_fmt(loo['minimum'])}, {_fmt(loo['maximum'])}] | "
            f"{int(loo['sign_changes'])} |"
        )
    return lines


def _strata_table(payload: Mapping[str, Any]) -> list[str]:
    strata = payload.get("strata", {})
    lines = [
        "| Stratum family | Level | Tasks | Recall delta | Output delta |",
        "|---|---|---:|---:|---:|",
    ]
    for family, levels in strata.items():
        for level, row in levels.items():
            lines.append(
                f"| {family} | {level} | {int(row['task_count'])} | "
                f"{_fmt(row['graph_minus_bm25_recall'])} | "
                f"{_fmt(row['graph_minus_bm25_output'])} |"
            )
    return lines


def _error_table(payload: Mapping[str, Any]) -> list[str]:
    taxonomy = payload["error_taxonomy"]
    counts = taxonomy["arm_error_counts"]
    lines = [
        "| Primary error class | Graph + BM25 | BM25 only |",
        "|---|---:|---:|",
    ]
    for name in taxonomy["classes"]:
        lines.append(
            f"| `{name}` | {int(counts[GRAPH].get(name, 0))} | "
            f"{int(counts[BM25].get(name, 0))} |"
        )
    return lines


def _edge_route_table(payload: Mapping[str, Any]) -> list[str]:
    associations = payload["graph_vs_bm25_oracle_delta"]["edge_route_associations"]
    lines = [
        "| Graph route label | Added chunks | Registry-required | "
        "Required fraction | Associated output delta |",
        "|---|---:|---:|---:|---:|",
    ]
    for label, row in associations.items():
        lines.append(
            f"| {label} | {int(row['graph_added_chunk_count'])} | "
            f"{int(row['required_chunk_count'])} | "
            f"{_fmt(row['required_fraction'])} | "
            f"{_fmt(row['mean_associated_output_delta'])} |"
        )
    return lines


def _analysis_report(payload: Mapping[str, Any]) -> str:
    panel = payload["panel"]
    delta = payload["graph_vs_bm25_oracle_delta"]
    audit = payload["graph_design_audit"]
    diagnosis = audit["diagnosis"]
    pairs = delta.get("pairs", [])
    added_count = sum(int(row["graph_added_chunk_count"]) for row in pairs)
    required_added_count = sum(
        int(row["graph_added_required_chunk_count"]) for row in pairs
    )
    unique_requirement_count = sum(
        int(row["graph_unique_requirement_count"]) for row in pairs
    )
    below_ceiling = sorted(
        {
            str(row["task_id"])
            for row in payload["task_arm_means"]
            if row["arm"] == BM25 and float(row["required_section_recall"]) < 1.0
        }
    )
    frozen = payload.get("frozen_primary_result", {})
    frozen_contrast = frozen.get("graph_minus_bm25", {})
    bootstrap = frozen_contrast.get("bootstrap", {})
    conditional = delta["conditional_evidence_output_table"]
    evidence_present_count = diagnosis.get(
        "evidence_present_output_failure_count_graph_plus_bm25", 0
    )
    retrieval_count = diagnosis.get(
        "retrieval_or_stale_failure_count_graph_plus_bm25", 0
    )
    edge_types = audit.get("graph_edge_type_counts", {})
    uses_edge_type = _fmt(audit.get("router_uses_edge_type_in_dependency_distance"))
    symmetric_traversal = _fmt(
        audit.get("router_traverses_predecessors_and_successors_symmetrically")
    )
    freeze_audit = payload.get("freeze_contract_audit", {})
    linkage_audit = payload.get("generation_evaluation_linkage_audit", {})
    stage0 = audit.get("stage0_development_diagnostics", {})
    heldout = audit.get("heldout_graph_diagnostics", {})
    lines = [
        "# V7 Offline Oracle Retrieval and Error Decomposition",
        "",
        "## Executive finding",
        "",
        (
            f"The audit reconstructed {panel['cell_count']} held-out cells "
            f"({panel['task_count']} tasks x {panel['arm_count']} arms x "
            f"{panel['repetitions_per_task_arm']} repetitions) and "
            f"{panel['criterion_record_count']} deterministic criterion records "
            "from stored manifests, full responses, and criterion histories. "
            "No model generation or judging was run."
        ),
        "",
        (
            f"The independent freeze audit verified "
            f"{freeze_audit.get('verified_source_count', 0)} frozen source files, "
            f"{freeze_audit.get('verified_corpus_file_count', 0)} corpus files, "
            f"and {linkage_audit.get('linked_record_count', 0)} exact generation-"
            "to-evaluation record linkages with zero mismatches."
        ),
        "",
        (
            "The dominant quality-null explanation is a combination of a held-out "
            "BM25 evidence-recall ceiling and downstream output-realization "
            "failures. The current graph is also semantically under-identified: "
            "its router treats workflow adjacency as symmetric evidence "
            "dependency, ignores typed edge semantics in distance, and selected "
            "no graph-only chunk marked as required by the frozen registry."
        ),
        "",
        (
            "This analysis does not establish graph superiority. It is not an "
            "operational GxP compliance assessment or finding. The evaluated "
            "architecture may be described only as GxP-oriented, audit-supporting, "
            "and human-overseen. There is no cross-version mean comparison."
        ),
        "",
        "## Frozen primary result",
        "",
        (
            f"The frozen deterministic means were graph + BM25 "
            f"`{_fmt(frozen.get('arm_means', {}).get(GRAPH, 0.0))}` and BM25 only "
            f"`{_fmt(frozen.get('arm_means', {}).get(BM25, 0.0))}`. Their "
            f"task-level mean difference was "
            f"`{_fmt(frozen_contrast.get('mean_difference', 0.0))}`, with frozen "
            f"95% bootstrap CI "
            f"`[{_fmt(bootstrap.get('ci_low', 0.0))}, "
            f"{_fmt(bootstrap.get('ci_high', 0.0))}]`, Holm-adjusted "
            f"`P={_fmt(frozen_contrast.get('holm_p', 0.0))}`, and a "
            f"leave-one-task-out range of "
            f"`{frozen_contrast.get('leave_one_out_mean_range', [])}`."
        ),
        "",
        "## Oracle retrieval metrics",
        "",
        *_arm_table(payload),
        "",
        (
            f"Across {len(pairs)} paired task/repetition comparisons, graph "
            f"selection added {added_count} chunks not present in the matched "
            f"BM25 context. Required graph additions: {required_added_count}; "
            f"unique required-evidence gains: {unique_requirement_count}. "
            "Thus, the graph did not supplement a BM25-missing registry-required "
            "section in this panel."
        ),
        "",
        (
            f"BM25 was at perfect required-section recall for "
            f"{24 - len(below_ceiling)}/24 tasks; below-ceiling task(s): "
            f"{', '.join(below_ceiling) if below_ceiling else 'none'}. "
            "This is a ceiling for the frozen registry evidence map, not proof "
            "that every semantically necessary fact was represented by that map."
        ),
        "",
        (
            "Graph context was descriptively slightly more dilute: required-token "
            "precision was lower and irrelevant-token ratio and redundancy were "
            "higher than BM25 only. The paired uncertainty interval includes zero, "
            "so this is a diagnostic signal, not a superiority or harm claim."
        ),
        "",
        "## Evidence-to-output conditional analysis",
        "",
        (
            "Required-section recall was unchanged in every graph/BM25 pair. "
            f"Conditional outcome counts were `{conditional}`. No cell occupied "
            "the evidence-improved stratum, so V7 cannot estimate whether output "
            "improves when graph retrieval uniquely repairs a BM25 miss."
        ),
        "",
        *_uncertainty_table(payload),
        "",
        "## Strict error decomposition",
        "",
        (
            "Each failed atomic criterion receives one primary class. Retrieval "
            "absence is evaluated before generator omission or derivation; when "
            "required evidence is present, generator/derivation/schema/citation "
            "failures are not attributed to the router."
        ),
        "",
        *_error_table(payload),
        "",
        (
            "Within graph + BM25 and BM25-only cells, evidence-present output "
            f"failures totaled {evidence_present_count}, versus "
            f"{retrieval_count} "
            "retrieval/stale failures. This supports a downstream bottleneck under "
            "the frozen evidence map, while keeping schema/serialization, "
            "derivation, omission, hallucination, citation, and judge-only errors "
            "separate in the machine-readable decomposition."
        ),
        "",
        "## Graph-design audit",
        "",
        (
            f"Graph edge-type inventory: `{edge_types}`. The router uses edge type "
            f"in dependency distance: `{uses_edge_type}`; "
            "it traverses predecessors and successors symmetrically: "
            f"`{symmetric_traversal}`."
        ),
        "",
        *_edge_route_table(payload),
        "",
        (
            "These edge-route output deltas are associations repeated over added "
            "chunks, not independent causal effects. Every route had zero "
            "registry-required graph additions, so output associations cannot be "
            "interpreted as evidence-mediated graph benefit."
        ),
        "",
        (
            f"Current-node-only requirement tasks: "
            f"{audit.get('benchmark_current_node_requirement_task_count', 0)}/24; "
            f"multi-hop requirement tasks: "
            f"{audit.get('benchmark_multihop_requirement_task_count', 0)}/24. "
            "This benchmark composition strongly favors sparse retrieval of a "
            "single named section and provides little identifying variation for "
            "topology."
        ),
        "",
        (
            f"Development-stage graph precision-at-k was "
            f"`{_fmt(stage0.get('precision_at_k', 0.0))}` with irrelevant-token "
            f"ratio `{_fmt(stage0.get('irrelevant_token_ratio', 0.0))}`. On "
            f"held-out tasks, required-section precision was "
            f"`{_fmt(heldout.get('required_section_precision', 0.0))}` and "
            f"irrelevant-token ratio was "
            f"`{_fmt(heldout.get('irrelevant_token_ratio', 0.0))}`. This "
            "development-to-held-out shift is diagnostic evidence of benchmark/"
            "selection mismatch, not a post hoc tuning target."
        ),
        "",
        (
            "The CURRENT floor is not independently auditable from the stored "
            "selection reason because it is conflated with graph MMR. Frozen "
            f"settings were floor `{audit.get('current_floor_tokens')}` tokens, "
            f"2-hop penalty `{audit.get('two_hop_penalty')}`, score-gap ratio "
            f"`{audit.get('score_gap_ratio')}`, and MMR lambda "
            f"`{audit.get('mmr_lambda')}`. No stale chunk was selected in graph "
            f"contexts (`{audit.get('stale_chunks_selected_graph_arm', 0)}`)."
        ),
        "",
        (
            "Bottleneck judgment: benchmark ceiling and downstream output use are "
            "the primary explanations visible here; graph construction and "
            "selection are secondary unresolved weaknesses because workflow edges "
            "are not typed evidence/data lineage and graph-added chunks were not "
            "oracle-required. The absence of a graph-only arm prevents isolating "
            "the graph's retrieval contribution."
        ),
        "",
        "Exploratory strata (associations, not causal or superiority tests):",
        "",
        *_strata_table(payload),
        "",
        "## Strategy and claim boundary",
        "",
        (
            "The graph has independent governance value as an optional layer: it "
            "can expose named dependencies, version state, provenance, change "
            "impact, and auditable selection paths even when mean output quality "
            "does not improve. That value is an architecture property and "
            "benchmark proxy, not a validated operational control."
        ),
        "",
        (
            "Recommendation: retain graph support as optional and human-reviewed; "
            "do not make it the default quality-improvement claim. Prioritize "
            "generator evidence-use, derivation, schema, and citation controls, "
            "then evaluate typed evidence/data-lineage construction and selectors "
            "on tasks that truly require cross-node evidence."
        ),
        "",
        (
            "Post-diagnostic algorithm ideas--typed-edge RWR/PPR, submodular or "
            "knapsack selection, Steiner-style evidence subgraphs, and hybrid "
            "sparse+dense retrieval--are proposals only and were not evaluated."
        ),
        "",
        (
            "Go/no-go: **no-go for immediate paid generation**. The offline oracle "
            "is sufficient to diagnose the current null. If isolating graph "
            "causality becomes publication-critical, preregister a new external "
            "held-out 2x2 (graph on/off x BM25 retrieval on/off), keep corpus, "
            "token budget, generator, validators, and analysis unit fixed, and "
            "make oracle evidence gain the primary endpoint. Do not start that "
            "protocol automatically."
        ),
        "",
        "### Claims supportable in a formal manuscript",
        "",
        "- V7 found no evidence of graph superiority over BM25 only.",
        "- BM25 already retrieved nearly all registry-declared required sections.",
        "- The current graph-added context did not add registry-required evidence.",
        "- The architecture is GxP-oriented, audit-supporting, and human-overseen.",
        "- Stored manifests and hashes support reproducible benchmark auditing.",
        "",
        "### Claims not supportable",
        "",
        "- Graph routing improves output quality, regulatory outcomes, or human time.",
        "- The system follows or meets FDA guidance.",
        "- The system is operationally GxP compliant.",
        "- Benchmark provenance is a validated end-to-end submission control.",
        "- V5, V6, and V7 means are directly comparable.",
    ]
    return "\n".join(lines)


def _stats_appendix(payload: Mapping[str, Any]) -> str:
    delta = payload["graph_vs_bm25_oracle_delta"]
    lines = [
        "# V7 Oracle Statistical Appendix",
        "",
        "## Estimands and units",
        "",
        (
            "The task is the independent unit. Three repetitions are averaged "
            "within task and arm before task-level graph-minus-BM25 inference. "
            "The oracle retrieval estimands are derived from frozen registry "
            "requirements and manifest membership; no arm score enters retrieval "
            "classification or router tuning."
        ),
        "",
        *_uncertainty_table(payload),
        "",
        "Bootstrap intervals use 10,000 deterministic task-level resamples with "
        "fixed metric-specific seeds. LOO values omit one task at a time.",
        "",
        "## Sensitivity analyses",
        "",
        (
            "The substantive-score sensitivity removes provenance-citation "
            "criterion weight before rescoring each cell. It tests whether any "
            "graph/BM25 difference is driven only by the explicit evidence-ID "
            "criterion; it does not repair generator or retrieval errors."
        ),
        "",
        (
            "Lexical-overlap, multi-hop, and task-category strata are exploratory. "
            "They were not preregistered for superiority, have small unequal task "
            "counts, and are not multiplicity-adjusted."
        ),
        "",
        *_strata_table(payload),
        "",
        "## Evidence/output table",
        "",
        "```json",
        str(delta["conditional_evidence_output_table"]).replace("'", '"'),
        "```",
        "",
        "## Limitations",
        "",
        (f"- {payload['requirement_mapping']['limitation']}"),
        (
            "- Registry section matching is exact by skill and heading substring. "
            "It does not infer unregistered semantic evidence."
        ),
        (
            "- No graph-only arm exists. Evidence-delta/output-delta conditioning "
            "has no evidence-improved observations."
        ),
        (
            "- Repetitions share task prompts and frozen retrieval logic; they are "
            "not treated as independent sample-size inflation."
        ),
        (
            "- Error attribution is conservative and deterministic. Unresolvable "
            "semantics remain in the explicit unresolved class."
        ),
        (
            "- No cross-version mean comparison is performed, and no unregistered "
            "post hoc superiority claim is made."
        ),
    ]
    return "\n".join(lines)


def _figure_catalog() -> str:
    return "\n".join(
        [
            "# V7 Oracle Figure Catalog",
            "",
            "## Figure 1 -- Held-out oracle retrieval diagnostics",
            "",
            (
                "Purpose: compare graph + BM25 and BM25-only retrieval coverage, "
                "precision, dilution, and redundancy. Source: cell-level frozen "
                "manifests and registry-required sections. Caveat: registry "
                "requirements are task-level section declarations."
            ),
            "",
            "File: `figures/figure-01-oracle-retrieval.svg`",
            "",
            "## Figure 2 -- Criterion-level error decomposition",
            "",
            (
                "Purpose: separate retrieval failures from evidence-present "
                "generator, derivation, schema, hallucination, citation, and judge "
                "discordance. Source: deterministic criterion histories. Caveat: "
                "classes are rule-based and mutually exclusive by precedence."
            ),
            "",
            "File: `figures/figure-02-error-decomposition.svg`",
            "",
            "## Figure 3 -- Evidence delta versus output delta",
            "",
            (
                "Purpose: show whether output changes coincide with graph-only "
                "required-evidence gain. Source: task-level paired graph/BM25 "
                "oracle metrics and deterministic scores. Caveat: all required-"
                "section recall deltas are zero, so the graph-benefit conditional "
                "question is unidentified in V7."
            ),
            "",
            "File: `figures/figure-03-evidence-output-delta.svg`",
        ]
    )


def _regulatory_matrix() -> str:
    lines = [
        "# FDA Regulatory-Alignment Matrix",
        "",
        (
            f"Official FDA sources accessed {ACCESSED_DATE}. This is a diagnostic "
            "alignment exercise, not an assertion that the research system follows "
            "or meets FDA guidance."
        ),
        "",
        (
            "Every row distinguishes an **architecture property**, a **benchmark "
            "proxy**, a **validated operational control**, and **formal compliance**. "
            "No validated operational control or formal compliance finding is "
            "established by V7."
        ),
        "",
        "## Source inventory",
        "",
    ]
    for source in FDA_SOURCES.values():
        lines.append(f"- [{source['title']}]({source['url']}) -- {source['status']}.")
    lines.extend(
        [
            "",
            "## Alignment",
            "",
            "| FDA guidance/principle | Architecture control | "
            "Machine-verifiable evidence | Classification | "
            "Validated operational control | Formal compliance | "
            "Remaining human responsibility / gap |",
            "|---|---|---|---|---|---|---|",
        ]
    )
    for row in ALIGNMENT_ROWS:
        source = FDA_SOURCES[row["source"]]
        principle = f"[{source['title']}]({source['url']}): {row['principle']}"
        values = (
            principle,
            row["architecture_control"],
            row["machine_evidence"],
            row["classification"],
            row["validated_operational_control"],
            row["formal_compliance"],
            row["remaining_human_responsibility"],
        )
        escaped = [
            str(value).replace("|", "\\|").replace("\n", " ") for value in values
        ]
        lines.append("| " + " | ".join(escaped) + " |")
    lines.extend(
        [
            "",
            "## Boundary conclusion",
            "",
            (
                "The graph and manifest controls are architecture properties that "
                "support auditability. The V7 panel supplies benchmark proxies for "
                "retrieval, traceability, and deterministic validation. It does not "
                "validate operational processes, personnel, access, signatures, "
                "retention, backup, SOPs, CAPA, or deployment change control. Those "
                "remain human and organizational responsibilities."
            ),
        ]
    )
    return "\n".join(lines)


def write_reports(*, payload: Mapping[str, Any], output_dir: Path) -> None:
    """Write byte-stable reports and accessibility-labelled SVG figures."""
    _write(output_dir / "analysis-report.md", _analysis_report(payload))
    _write(output_dir / "stats-appendix.md", _stats_appendix(payload))
    _write(output_dir / "figure-catalog.md", _figure_catalog())
    _write(
        output_dir / "regulatory-alignment-matrix.md",
        _regulatory_matrix(),
    )
    figures = output_dir / "figures"
    _write(
        figures / "figure-01-oracle-retrieval.svg",
        _figure_oracle_retrieval(payload),
    )
    _write(
        figures / "figure-02-error-decomposition.svg",
        _figure_error_decomposition(payload),
    )
    _write(
        figures / "figure-03-evidence-output-delta.svg",
        _figure_evidence_output_delta(payload),
    )
