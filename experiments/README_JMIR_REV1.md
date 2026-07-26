# JMIR AI Revision 1 Reproducibility Release

This directory contains the experiment code and finalized checkpoints supporting manuscript 100769, revision 1. The benchmark inputs and stored responses are synthetic; no human-participant, patient-record, or identifiable personal data are included.

## Authoritative artifacts

The complete-response corrective analysis is based on:

- `results/experiment_v5_corrected_20260717.json`: 180 GLM-5 generations under 6 conditions.
- `results/experiment_v5_rejudged_full_outputs.json`: 180 complete-response scalar judgments and 90 logical pairs evaluated in both AB and BA presentation order (180 presentations) with `deepseek-v4-flash`.
- `run_experiment_v5_corrected.py`: post-run validation-hardened copy of the generation runner and checkpoint validator.
- `rejudge_v5_full_outputs.py`: fail-closed complete-response re-judgment and validator.
- `analyze_corrected_experiment.py`: task-paired exact sign-flip analysis.
- `generate_v5_analysis_bundle.py`: publication-table and figure bundle generator.
- `evaluation_panels/persona_panel_scores.csv`: the 20 persona-panel scoring rows supporting Table 2.
- `evaluation_panels/analyze_persona_panels.py`: a standard-library reproduction of the pooled means and interpanel agreement.

The secondary original-experiment full-response analysis is based on:

- `results/experiment_v4_claude/experiment_20260410_095153.json`: the immutable 90-run source checkpoint containing all original stored responses.
- `results/experiment_original_rejudged_full_outputs.json`: 90 complete-response scalar judgments and 60 logical pairs evaluated in both AB and BA presentation order (120 presentations) with `deepseek-v4-flash`.
- `rejudge_original_full_outputs.py`: the locked complete-response re-judgment protocol and fail-closed validator.
- `analyze_original_full_response.py`: the task-paired exact sign-flip, bootstrap, effect-size, protocol-sensitivity, leave-one-task-out, and bidirectional pairwise analysis.
- `tests/test_rejudge_original_full_outputs.py` and `tests/test_analyze_original_full_response.py`: focused validation tests for the original-experiment repair.

The prespecified APS-GxP optimization follow-up is based on:

- `../plan/jmir_aps_gxp_optimization_experiment_20260724.md`: the design, decision boundaries, engineering gates, and interpretation rules frozen before the formal run.
- `aps_gxp_context.py`: deterministic relevance, provenance-manifest, token-matching, and simulated change-impact implementation.
- `run_experiment_v6_aps_gxp.py`: four-arm Stage-0, generation, complete-response judging, checkpoint-resume, and fail-closed validation harness.
- `analyze_aps_gxp_experiment.py`: task-paired exact sign-flip/Holm analysis and deterministic efficiency/governance analysis.
- `results/experiment_v6_aps_gxp_stage0.json`: the passing 40-cell, no-network structural gate report.
- `results/experiment_v6_aps_gxp_formal_20260724.json`: the immutable 120-generation formal checkpoint.
- `results/experiment_v6_aps_gxp_formal_20260724_judged.json`: the final 120/120 complete-response judged checkpoint. It retains every parse-error attempt and records zero final invalid judgments; no valid judgment was replaced.
- `../paper/jmir_ai/analysis_v6_aps_gxp/`: the exact verified analysis JSON, Markdown report, statistical appendix, figure catalog, and SVG figures.
- `../tests/test_aps_gxp_context.py`, `../tests/test_experiment_v6_aps_gxp_design.py`, and `../tests/test_analyze_aps_gxp_experiment.py`: 55 focused tests for context construction, experiment integrity, and analysis.

The earlier 4-arm ablation sensitivity workflow is retained in:

- `run_experiment_v4_claude.py`
- `rejudge_ablation.py`
- `analyze_ablation.py`
- `results/experiment_v4_claude/experiment_20260716_134707_rejudged.json`

## Verification

From the repository root:

```bash
python experiments/run_experiment_v5_corrected.py \
  --validate experiments/results/experiment_v5_corrected_20260717.json

python experiments/rejudge_v5_full_outputs.py \
  --input experiments/results/experiment_v5_corrected_20260717.json \
  --output experiments/results/experiment_v5_rejudged_full_outputs.json \
  --validate

python experiments/analyze_corrected_experiment.py \
  --input experiments/results/experiment_v5_rejudged_full_outputs.json \
  --output-prefix paper/jmir_ai/corrected_experiment_v5_full_report \
  --verify

python experiments/generate_v5_analysis_bundle.py \
  --input experiments/results/experiment_v5_rejudged_full_outputs.json \
  --report paper/jmir_ai/corrected_experiment_v5_full_report.json \
  --output-dir paper/jmir_ai/analysis_v5_full \
  --verify

python experiments/evaluation_panels/analyze_persona_panels.py --verify

python experiments/rejudge_original_full_outputs.py \
  --input experiments/results/experiment_v4_claude/experiment_20260410_095153.json \
  --output experiments/results/experiment_original_rejudged_full_outputs.json \
  --validate

python experiments/analyze_original_full_response.py \
  --input experiments/results/experiment_original_rejudged_full_outputs.json \
  --output-dir paper/jmir_ai/analysis_original_full

python experiments/analyze_original_full_response.py \
  --input experiments/results/experiment_original_rejudged_full_outputs.json \
  --output-dir paper/jmir_ai/analysis_original_full \
  --verify

pytest -q \
  tests/test_rejudge_original_full_outputs.py \
  tests/test_analyze_original_full_response.py

python experiments/run_experiment_v6_aps_gxp.py --stage0 \
  --output experiments/results/experiment_v6_aps_gxp_stage0.json

python experiments/analyze_aps_gxp_experiment.py \
  --input experiments/results/experiment_v6_aps_gxp_formal_20260724_judged.json \
  --output-prefix paper/jmir_ai/analysis_v6_aps_gxp/formal_analysis_20260724 \
  --bundle-dir paper/jmir_ai/analysis_v6_aps_gxp/formal_bundle_20260724 \
  --verify

pytest -q \
  tests/test_aps_gxp_context.py \
  tests/test_experiment_v6_aps_gxp_design.py \
  tests/test_analyze_aps_gxp_experiment.py
```

The analysis commands generate or verify manuscript-side report and figure bundles. None of the validation, analysis, or test commands makes external API calls. The re-judgment scripts make no calls when `--validate` is supplied.

## APS provenance note

The corrective checkpoint records the SHA-256 of `scripts/context-loader.py` as `ed0125d6db267d7456df58b53d0687b9ead076d5ffae484380916c582d88154f`; the released file matches byte for byte. Legacy explanatory comments near the top of that frozen executed file predate the corrective audit and should not be treated as the behavioral specification. The executable behavior is:

- `query_match` is ignored;
- priority is `band_weight * (1 + min(0.3, 0.03 * hub_degree))`;
- CURRENT candidates are serviced first toward the smaller of CURRENT demand and 40% of available tokens;
- all unprocessed candidates then use one shared greedy remaining budget, not proportional per-band allocations;
- non-CURRENT candidates have a 25% single-skill cap; and
- truncation strips YAML frontmatter, then fenced code blocks, then applies a character cutoff.

Stored audits show CURRENT content in 30/30 corrected routed runs, SUCCESSOR content in 27/30, PREDECESSOR content in 3/30, and GLOBAL candidates present but dropped under the budget in 30/30. All four bands occurred among candidates, but no run loaded content from all four.

The checkpoint records the generation runner SHA-256 as `caf272a9978b40a63025c2dcd22ba8494b420babc9017c93916d0004082807b4`. The runner was subsequently hardened with fail-closed validation logic before the release was assembled; the released copy has SHA-256 `ee717d96f0343eac759742491a70493bd353a7606ec44f7c6f9ee60cb5622efd`. The byte-identical executed runner was not retained. The immutable checkpoint nevertheless stores the executed runner hash, rendered prompt hashes, scheduler/graph/system-prompt/task-panel hashes, condition payload audits, and all complete responses. The scheduler itself is the byte-identical executed artifact noted above.

## Interpretation boundary

Corrected APS exceeded the domain-prompt-only control, but it did not outperform budget-capped flat or random corpus loading after Holm adjustment. The experiment therefore supports a curated-context effect but does not establish routing superiority. Pairwise results are descriptive because 58/90 logical pairs were order-discordant under counterbalanced presentation.

The original experiment is retained only as secondary evidence for the bundled domain-prompt-plus-node-bound-context intervention. Its full-response framework-minus-bare-agent contrast was +0.88 points (95% CI 0.63-1.13; exact 2-sided sign-flip P=.002), but the original banded scheduler was inoperative and that design did not isolate routing. The corrective experiment remains the primary mechanism test.

The optimization follow-up yielded Outcome B: similar quality with an efficiency/governance advantage. Mean quality was 4.24 for optimized APS-GxP, 4.23 for frozen APS, 4.07 for flat loading, and 4.03 for token-matched random loading. Optimized-minus-flat was +0.18 (95% CI 0.01-0.33; exact P=.102; Holm P=.270), and optimized-minus-random was +0.21 (95% CI 0.02-0.40; exact P=.090; Holm P=.270); no quality-superiority contrast passed Holm adjustment. Optimized APS-GxP retained quality under the prespecified engineering threshold while using 28.82% fewer injected skill-context tokens than flat loading. Provenance completeness and repeated-manifest reproducibility were 100%, and simulated one-skill changes affected 7.56 fewer tasks on average than flat loading. The context reduction is partly policy-enforced by the frozen 84% soft cap, and the governance measures are deterministic architectural proxies, not evidence of operational GxP compliance.

## Routing-sensitive deterministic follow-up (V7)

The release additionally contains the prespecified routing-sensitive deterministic follow-up: 24 genuinely held-out tasks, four arms (graph-routed chunk retrieval, exactly token-matched full-corpus BM25-only retrieval, token-matched random retrieval, and flat 8000-token loading), and three replicates per cell (288 generations, 288 deterministic evaluations, and 288 blinded complete-response judgments). The frozen task registry, router/freeze configurations, immutable generation and evaluated checkpoints, failure log, statistical analysis, focused tests, and the fully offline oracle retrieval and error decomposition (288 reconstructed cells; 1,236 criterion records; byte-identical reruns; independent verifier) are all included with SHA-256 hashes in `jmir_rev1_manifest.json`.

Interpretation boundary: graph-routed retrieval did not outperform token-matched BM25-only retrieval on the deterministic primary endpoint (mean difference +0.0087; 95% bootstrap CI -0.0281 to 0.0460; exact/Holm P=.6719), while both structured retrieval arms strongly exceeded random and flat loading and used 83.34% less canonical context than flat loading under the prespecified retention rule. The oracle decomposition attributes the null primarily to a lexical-retrieval evidence ceiling (required-section recall 0.958) and downstream generation-side failures (225 evidence-present failures versus 16 retrieval-side failures); graph-added chunks contained no registry-required section on this panel. Response-level provenance-citation criteria passed in 46.9% of cells pooled across arms (94%/92% in the retrieval arms, near 0% in random/flat). No routing-superiority, operational GxP compliance, human-time, or regulatory-outcome claim is supported.

Exact file hashes are recorded in `jmir_rev1_manifest.json`.
