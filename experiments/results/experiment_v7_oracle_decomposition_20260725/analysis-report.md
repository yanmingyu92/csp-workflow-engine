# V7 Offline Oracle Retrieval and Error Decomposition

## Executive finding

The audit reconstructed 288 held-out cells (24 tasks x 4 arms x 3 repetitions) and 1236 deterministic criterion records from stored manifests, full responses, and criterion histories. No model generation or judging was run.

The independent freeze audit verified 8 frozen source files, 59 corpus files, and 288 exact generation-to-evaluation record linkages with zero mismatches.

The dominant quality-null explanation is a combination of a held-out BM25 evidence-recall ceiling and downstream output-realization failures. The current graph is also semantically under-identified: its router treats workflow adjacency as symmetric evidence dependency, ignores typed edge semantics in distance, and selected no graph-only chunk marked as required by the frozen registry.

This analysis does not establish graph superiority. It is not an operational GxP compliance assessment or finding. The evaluated architecture may be described only as GxP-oriented, audit-supporting, and human-overseen. There is no cross-version mean comparison.

## Frozen primary result

The frozen deterministic means were graph + BM25 `0.5926` and BM25 only `0.5839`. Their task-level mean difference was `0.0087`, with frozen 95% bootstrap CI `[-0.0281, 0.0460]`, Holm-adjusted `P=0.6719`, and a leave-one-task-out range of `[-0.001242236025, 0.018771566598]`.

## Oracle retrieval metrics

| Metric | Graph + BM25 | BM25 only |
|---|---:|---:|
| Deterministic score | 0.5926 | 0.5839 |
| Required-section recall | 0.9583 | 0.9583 |
| Required-section precision | 0.2177 | 0.2196 |
| Required-token precision | 0.2532 | 0.2570 |
| Dependency coverage | 0.9583 | 0.9583 |
| Topology alignment | 1.0000 | 1.0000 |
| Irrelevant-token ratio | 0.7468 | 0.7430 |
| Redundancy | 0.1191 | 0.1131 |
| Version selection correctness | 1.0000 | 1.0000 |
| Version/conflict output correctness | 0.9167 | 0.9005 |
| Provenance completeness | 1.0000 | 1.0000 |
| Correct citation rate | 0.9444 | 0.9167 |

Across 72 paired task/repetition comparisons, graph selection added 57 chunks not present in the matched BM25 context. Required graph additions: 0; unique required-evidence gains: 0. Thus, the graph did not supplement a BM25-missing registry-required section in this panel.

BM25 was at perfect required-section recall for 23/24 tasks; below-ceiling task(s): v7h13-p21-artifact-role. This is a ceiling for the frozen registry evidence map, not proof that every semantically necessary fact was represented by that map.

Graph context was descriptively slightly more dilute: required-token precision was lower and irrelevant-token ratio and redundancy were higher than BM25 only. The paired uncertainty interval includes zero, so this is a diagnostic signal, not a superiority or harm claim.

## Evidence-to-output conditional analysis

Required-section recall was unchanged in every graph/BM25 pair. Conditional outcome counts were `{'evidence_unchanged__output_improved': 12, 'evidence_unchanged__output_unchanged': 52, 'evidence_unchanged__output_worsened': 8}`. No cell occupied the evidence-improved stratum, so V7 cannot estimate whether output improves when graph retrieval uniquely repairs a BM25 miss.

| Task-level graph minus BM25 estimand | Mean | Bootstrap 95% CI | LOO range | LOO sign changes |
|---|---:|---:|---:|---:|
| Required-section recall | 0.0000 | [0.0000, 0.0000] | [0.0000, 0.0000] | 0 |
| Required-section precision | -0.0019 | [-0.0155, 0.0088] | [-0.0041, 0.0035] | 2 |
| Required-token precision | -0.0038 | [-0.0143, 0.0022] | [-0.0048, 0.0010] | 1 |
| Deterministic output score | 0.0087 | [-0.0280, 0.0451] | [-0.0012, 0.0188] | 1 |
| Output score excluding provenance criterion | 0.0005 | [-0.0493, 0.0491] | [-0.0140, 0.0150] | 5 |

## Strict error decomposition

Each failed atomic criterion receives one primary class. Retrieval absence is evaluated before generator omission or derivation; when required evidence is present, generator/derivation/schema/citation failures are not attributed to the router.

| Primary error class | Graph + BM25 | BM25 only |
|---|---:|---:|
| `retrieval_miss` | 8 | 8 |
| `wrong_or_stale_evidence` | 0 | 0 |
| `evidence_present_generator_omission` | 33 | 33 |
| `derivation_error` | 58 | 61 |
| `schema_or_serialization_error` | 12 | 12 |
| `forbidden_hallucination` | 5 | 7 |
| `citation_mismatch` | 1 | 3 |
| `judge_only_disagreement` | 1 | 3 |
| `unresolved_insufficient_artifact_evidence` | 0 | 0 |

Within graph + BM25 and BM25-only cells, evidence-present output failures totaled 225, versus 16 retrieval/stale failures. This supports a downstream bottleneck under the frozen evidence map, while keeping schema/serialization, derivation, omission, hallucination, citation, and judge-only errors separate in the machine-readable decomposition.

## Graph-design audit

Graph edge-type inventory: `{'enables': 15, 'requires': 80, 'validates': 3}`. The router uses edge type in dependency distance: `no`; it traverses predecessors and successors symmetrically: `yes`.

| Graph route label | Added chunks | Registry-required | Required fraction | Associated output delta |
|---|---:|---:|---:|---:|
| current_node | 21 | 0 | 0.0000 | 0.0918 |
| enables | 3 | 0 | 0.0000 | 0.0000 |
| requires | 33 | 0 | 0.0000 | 0.0388 |

These edge-route output deltas are associations repeated over added chunks, not independent causal effects. Every route had zero registry-required graph additions, so output associations cannot be interpreted as evidence-mediated graph benefit.

Current-node-only requirement tasks: 21/24; multi-hop requirement tasks: 3/24. This benchmark composition strongly favors sparse retrieval of a single named section and provides little identifying variation for topology.

Development-stage graph precision-at-k was `0.3483` with irrelevant-token ratio `0.6194`. On held-out tasks, required-section precision was `0.2177` and irrelevant-token ratio was `0.7468`. This development-to-held-out shift is diagnostic evidence of benchmark/selection mismatch, not a post hoc tuning target.

The CURRENT floor is not independently auditable from the stored selection reason because it is conflated with graph MMR. Frozen settings were floor `320` tokens, 2-hop penalty `0.5`, score-gap ratio `0.35`, and MMR lambda `0.68`. No stale chunk was selected in graph contexts (`0`).

Bottleneck judgment: benchmark ceiling and downstream output use are the primary explanations visible here; graph construction and selection are secondary unresolved weaknesses because workflow edges are not typed evidence/data lineage and graph-added chunks were not oracle-required. The absence of a graph-only arm prevents isolating the graph's retrieval contribution.

Exploratory strata (associations, not causal or superiority tests):

| Stratum family | Level | Tasks | Recall delta | Output delta |
|---|---|---:|---:|---:|
| lexical_overlap | low | 8 | 0.0000 | 0.0589 |
| lexical_overlap | middle | 8 | 0.0000 | 0.0119 |
| lexical_overlap | high | 8 | 0.0000 | -0.0446 |
| multi_hop | false | 21 | 0.0000 | 0.0190 |
| multi_hop | true | 3 | 0.0000 | -0.0635 |
| task_category | adsl | 3 | 0.0000 | -0.0185 |
| task_category | ae | 3 | 0.0000 | 0.0370 |
| task_category | define | 4 | 0.0000 | 0.0595 |
| task_category | dm | 3 | 0.0000 | -0.0556 |
| task_category | p21 | 5 | 0.0000 | 0.0133 |
| task_category | tfl | 6 | 0.0000 | 0.0026 |

## Strategy and claim boundary

The graph has independent governance value as an optional layer: it can expose named dependencies, version state, provenance, change impact, and auditable selection paths even when mean output quality does not improve. That value is an architecture property and benchmark proxy, not a validated operational control.

Recommendation: retain graph support as optional and human-reviewed; do not make it the default quality-improvement claim. Prioritize generator evidence-use, derivation, schema, and citation controls, then evaluate typed evidence/data-lineage construction and selectors on tasks that truly require cross-node evidence.

Post-diagnostic algorithm ideas--typed-edge RWR/PPR, submodular or knapsack selection, Steiner-style evidence subgraphs, and hybrid sparse+dense retrieval--are proposals only and were not evaluated.

Go/no-go: **no-go for immediate paid generation**. The offline oracle is sufficient to diagnose the current null. If isolating graph causality becomes publication-critical, preregister a new external held-out 2x2 (graph on/off x BM25 retrieval on/off), keep corpus, token budget, generator, validators, and analysis unit fixed, and make oracle evidence gain the primary endpoint. Do not start that protocol automatically.

### Claims supportable in a formal manuscript

- V7 found no evidence of graph superiority over BM25 only.
- BM25 already retrieved nearly all registry-declared required sections.
- The current graph-added context did not add registry-required evidence.
- The architecture is GxP-oriented, audit-supporting, and human-overseen.
- Stored manifests and hashes support reproducible benchmark auditing.

### Claims not supportable

- Graph routing improves output quality, regulatory outcomes, or human time.
- The system follows or meets FDA guidance.
- The system is operationally GxP compliant.
- Benchmark provenance is a validated end-to-end submission control.
- V5, V6, and V7 means are directly comparable.
