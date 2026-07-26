# V7 Routing-Sensitive and Deterministic-Evaluation Experiment Plan

## Goal

Independently test whether dependency-aware graph routing improves deterministic task correctness over token-matched full-corpus BM25-only and random retrieval while preserving an auditable, reproducible, and GxP-relevant evidence trail. LLM judging is secondary.

## Immutable and Scope Boundaries

- The V6 baseline is read-only: `experiments/results/experiment_v6_aps_gxp_formal_20260724_judged.json`.
- Expected V6 SHA-256 prefix/suffix: `fb9f787a...27aa0`.
- Do not overwrite any V5/V6 source, configuration, checkpoint, response, analysis, or result.
- Use V7-specific names for every source, configuration, checkpoint, response, analysis, and audit artifact.
- Preserve all pre-existing tracked, untracked, and ignored files.
- Do not push, publish, or modify the manuscript/submission package in this task.
- Before final V7 audit, the only paper-area file that may be edited is `paper/jmir_ai/REVISION_TRACKER.md`.
- Router parameters may be tuned only from development-task retrieval diagnostics, never from generation or judge arm scores.
- Smoke results may be inspected only for transport, parsing, checkpoint/resume, and full-response judging integrity. Arm quality scores are sealed until the formal run is complete.

## Pre-Registered Experimental Design

### Arms

1. `graph_bm25_chunk_optimized`: dependency-aware graph expansion plus section/chunk BM25 retrieval.
2. `full_corpus_bm25_token_matched`: full-corpus BM25-only retrieval with an exact/canonical token budget matched to arm 1.
3. `random_token_matched`: deterministic seeded random retrieval with the same exact/canonical token budget.
4. `flat_8000`: flat context with an 8,000-token cap.

No fifth domain-prompt-only arm is included because V5 already evaluated corpus benefit. V6 remains historical context only.

### Units and Calls

- 20-24 independent, genuinely held-out, routing-sensitive tasks.
- Four arms and three generation repetitions per task.
- Planned formal generation calls: 240-288.
- The task, not the repetition, is the independent inferential unit.

### Primary Endpoint

For each task and arm:

1. Score machine-verifiable atomic criteria on every repetition.
2. Apply the frozen missing/failure policy: missing, unparseable, schema-invalid, or validator-crashing outputs score zero for affected criteria; infrastructure failures are retried only through checkpoint-safe transport retry and remain explicitly logged.
3. Aggregate criterion scores within a repetition as earned atomic weight divided by available atomic weight.
4. Aggregate the three repetitions per task-arm by arithmetic mean.
5. Use the resulting task-level deterministic score as the primary endpoint.

Validator families must cover exact variables, controlled terminology/codelist versions, forbidden hallucinations, derivation formulas, XML/JSON/YAML schema, executable code/schema where feasible, traceability/provenance citations, upstream change propagation, stale-version/conflict detection, deterministic manifest reproducibility, and change containment.

### Secondary Endpoint

- Blinded LLM judge readability/actionability score over complete stored responses.
- The judge must not receive arm identity or retrieval metadata.
- Re-judging must retain every parse attempt and may not silently substitute a score.
- A second judge or documented human spot-check may be added as sensitivity evidence but cannot replace the deterministic primary endpoint.

### Statistical Analysis

- Planned primary contrasts: optimized vs BM25-only and optimized vs random.
- Supporting contrast: optimized vs flat 8000.
- Exact paired randomization tests at the task level.
- Task-level paired bootstrap confidence intervals.
- Paired standardized effect size (`d_z`) plus mean/median paired differences.
- Holm correction across the two primary optimized-arm contrasts; the
  optimized-versus-flat contrast is supporting.
- Leave-one-task-out stability and validator-family/domain sensitivity analyses.
- Report all task counts, repetitions, missing/failure records, descriptive statistics, confidence intervals, exact p-values, adjusted p-values, and effect sizes.
- Repetitions quantify response variability but do not increase the inferential sample size.

### Decision Rule

Routing superiority may be claimed only if the optimized arm is superior on the deterministic primary endpoint to both BM25-only and random after Holm correction. Otherwise report a null routing result and, where supported, only efficiency and/or governance findings. If deterministic quality is retained while context is significantly smaller, the allowed claim is token efficiency, not routing superiority.

The frozen engineering retention margin is -0.05 on the 0-1 deterministic
score. Token efficiency requires the optimized-minus-flat paired bootstrap
interval lower bound to be at least -0.05 and a positive canonical context-token
reduction. This is a benchmark engineering retention rule, not a regulatory
equivalence claim.

No operational GxP compliance, human time savings, or regulatory outcome claim is permitted.

## Checkpoints

### Checkpoint 0: Stage 0 Offline Audit

- [x] Confirm repository instructions, Git state, existing plans, V5/V6 runners, APS router, tests, results, and revision tracker.
- [x] Verify the V6 immutable artifact hash, shape, and historical summary without rewriting it.
- [x] Build a development task-to-required-evidence/skill-section map.
- [x] Audit ADSL, P21, TFL, Define, and SDTM corpus sections for accuracy, versioning, conflicts, and executable guidance.
- [x] Correct inaccurate or ambiguous core skill corpus content with explicit provenance/version labels.
- [x] Quantify recall@k, precision@k, dependency coverage, irrelevant-token ratio, redundancy, provenance completeness, and change-impact scope on development tasks.
- [x] Record Stage 0 evidence and select the development-only retrieval configuration. The final offline diagnostics achieved recall@k 1.0, dependency coverage 1.0, provenance completeness 1.0, precision@k 0.3483, irrelevant-token ratio 0.6194, and mean redundancy 0.1364 across 10 development tasks. No generation or judge score was available to tuning.

Exit criterion: development retrieval diagnostics and corpus audit pass; no generation or LLM judging has occurred.

### Checkpoint 1: TDD Implementation

- [x] Write failing unit and integration tests first.
- [x] Implement section/chunk indexing and prioritized injection.
- [x] Implement dependency-aware expansion with controlled two-hop penalty.
- [x] Replace unconditional CURRENT-file injection with a service floor.
- [x] Allow relevance to cross predecessor/successor bands.
- [x] Implement frozen top-k/score-gap threshold.
- [x] Implement MMR/diversity and version/conflict detection.
- [x] Implement provenance IDs, deterministic context manifests, and change containment.
- [x] Implement exact/canonical token-budget matching and complete usage/cache accounting.
- [x] Implement held-out leakage guard and deterministic validators.
- [x] Implement fail-closed checkpoint/resume and parse-attempt history.

Exit criterion: focused tests, full relevant suite, and an independent verifier pass before any paid call.

Verification record: all 35 focused V7 tests pass and all V7 Python sources
compile. The repository-wide suite completed with 263 passed, 1 skipped, and one
expected historical V5/V6 context-parity failure because the task-required core
corpus corrections intentionally change current skill token signatures. The V6
judged result remains byte-identical at its frozen SHA-256. No V6 runner or test
was changed to conceal this compatibility deviation. Ruff was unavailable from
the active interpreter, and the isolated `uv` fallback was blocked by restricted
dependency download; syntax compilation, tests, and secret scanning were used
instead.

### Checkpoint 2: Freeze

- [x] Freeze held-out task definitions, atomic criteria, validators, arm configuration, prompts, router configuration, seeds, models, and statistical analysis code.
- [x] Record SHA-256 hashes for all frozen sources and configurations.
- [x] Prove held-out tasks were not used for router tuning.
- [x] Store the deterministic formal-run structural manifest. The first
  preflight freeze (`7c0cb7ad...ef31b6`) passed the independent verifier and is
  superseded only to capture this checkpoint update in the final plan hash.

Exit criterion: all hashes and run metadata are immutable and the formal task IDs are sealed.

### Checkpoint 3: Minimal Smoke

- [ ] Run the smallest possible paid smoke covering transport, full-response storage, parser, judging, and checkpoint/resume.
- [ ] Keep arm quality scores sealed and exclude smoke outputs from formal inference.
- [ ] Fix only transport, parser, checkpoint, or configuration defects.
- [ ] If any allowed fix is required, rerun tests and create a new freeze record with new hashes.

Exit criterion: transport and integrity pass; no score-driven router or validator change has occurred.

### Checkpoint 4: Formal Generation and Re-Judging

- [ ] Execute all 240-288 generation calls with checkpoint/resume and fail-closed behavior.
- [ ] Record `input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_creation_tokens`, serialized prompt bytes/chars, and canonical tokenizer count where available.
- [ ] Run deterministic primary validators over full stored responses.
- [ ] Run blinded LLM judging over full stored responses.
- [ ] Retain all attempts, failures, raw responses, parse histories, and audit events.

Exit criterion: every planned cell is completed or explicitly failed under the frozen missing/failure policy.

### Checkpoint 5: Analysis and Final Audit

- [ ] Validate result completeness and manifest/source hashes.
- [ ] Produce deterministic and LLM analysis, exact tests, bootstrap intervals, effects, Holm correction, LOO, and sensitivity analyses.
- [ ] Produce real scientific figures and exact numeric tables.
- [ ] Audit version propagation, provenance completeness/correctness, stale/conflict detection, reproducibility, change containment, usage accounting, and response/judge integrity.
- [ ] Record an honest decision under the pre-registered rule.
- [ ] Recommend whether later manuscript changes are warranted without editing the manuscript in this task.
- [ ] Update only `paper/jmir_ai/REVISION_TRACKER.md` in the paper area.

## Planned V7 Artifact Namespace

- Source: `experiments/v7_*.py`,
  `experiments/run_experiment_v7_routing_sensitive.py`, and
  `experiments/analyze_experiment_v7.py`.
- Tests: `tests/test_*v7*.py`.
- Configuration/tasks: `experiments/config/experiment_v7_*`.
- Checkpoints/results: `experiments/results/experiment_v7_*`.
- Analysis bundle: `paper/jmir_ai/analysis_v7_routing_sensitive/`.
- Failure log and GxP audit: inside the V7 result/analysis namespace.

## Errors and Deviations

- Root `AGENTS.md` was not present on disk at task start; the complete AGENTS instructions supplied with the delegated task are treated as authoritative.
- Git ownership differs from the sandbox user. Read-only/local Git commands use a command-scoped `safe.directory` override; global Git configuration is not modified.
- No Obsidian binding was present at task start. `OBSIDIAN_VAULT_PATH` is
  unavailable, so the unbound-repository bootstrap skill cannot safely create
  or update a vault. This is a nonblocking documentation deviation; no
  project-memory registry is fabricated.

## Current Status

**Checkpoint 3 minimal smoke is next** — Stage 0, TDD implementation,
verification, and the initial freeze are complete. The final superseding freeze
will record this plan state before the first paid call. This supersedes the
legacy status line below, retained verbatim because it contains a historical
encoding artifact.

**Stage 0 in progress** — constraints and skills read; initial repository inventory and offline evidence audit underway.
