# JMIR APS-GxP Optimization Experiment (v6)

Date: 2026-07-24  
Status: structurally amended before smoke; full execution explicitly authorized in the controlling task  
Authoritative progress source: `paper/jmir_ai/REVISION_TRACKER.md`

## 1. Purpose

The corrected v5 experiment established that APS context improved complete-response
quality relative to a domain prompt alone, but it did not establish quality
superiority over nonrouted flat or random corpus loading. This compact follow-up
optimizes the framework and evaluates two distinct value propositions:

1. **Outcome quality and efficiency:** whether a task-relevance-aware APS improves
   quality or preserves quality with less injected context.
2. **GxP-oriented governance properties:** whether the framework produces
   deterministic, version-linked selection provenance, narrower context exposure,
   reproducible manifests, and more contained rule-change impact.

The second objective concerns architectural proxies relevant to traceability and
change control. The experiment must not describe the framework as operationally
GxP compliant and must not treat these proxies as human validation.

This is an ML/AI optimization experiment, not a formal preregistration exercise.
Nevertheless, the implementation, configuration, smoke-adjustment log, source
hashes, and analysis rules must be frozen before the formal run.

## 2. Questions and Decision Boundaries

### Q1: Does optimization improve outcome quality?

Compare optimized APS-GxP with the same-session frozen v5 APS, flat loading, and
token-matched random loading.

- A quality-superiority claim requires a positive task-paired mean difference and
  Holm-adjusted two-sided `P<.05` for the relevant contrast.
- A nonsignificant result means superiority was not detected; it does not establish
  equivalence or absence of an effect.

### Q2: Does optimization improve efficiency without a material quality loss?

An engineering efficiency finding requires all of:

- optimized APS uses at least 15% fewer mean skill-context tokens than flat;
- the paired-bootstrap 95% CI lower bound for optimized-minus-flat quality is at
  least -0.20 points on the 1-5 scale; and
- no regression gate or GxP-oriented integrity gate fails.

The -0.20 margin is an engineering decision threshold, not a clinically validated
noninferiority margin. Report it as such and also report the full CI.

### Q3: Does optimized routing provide measurable GxP-oriented governance value?

Report each deterministic metric separately. Do not create an arbitrary composite
GxP score.

- **Provenance completeness:** percentage of admitted context fragments with all
  required provenance fields populated; target 100%.
- **Manifest reproducibility:** identical context-manifest SHA-256 values across
  three repeated context-only builds of each task/arm key; target 100%.
- **Context scope:** selected skills and tokens by CURRENT, relevance-qualified
  adjacent, global, and out-of-scope categories.
- **Change-impact containment:** for a simulated one-skill version/hash change,
  number and proportion of task contexts whose manifest changes. Report the
  distribution by arm and the paired optimized-versus-flat difference.

For the locked A/B/C classification, the change-impact containment gate passes
when the mean paired optimized-minus-flat affected-task difference across simulated
skills is no greater than zero. This gate prevents a governance-advantage label when
optimized routing has broader average simulated change impact than flat loading;
the complete distribution remains the reported evidence.

These metrics support claims about measured selection behavior, not claims that
auditability, reviewer workload, or regulatory compliance improved in practice.

## 3. Frozen Experimental Panel

### Tasks and repetitions

- The same 10 prespecified synthetic tasks used in corrected v5.
- Three independent agent generations per task-arm.
- The task is the inferential unit; the three generations are within-task
  replicates.
- Seed 42 controls call order, token-matched random sampling, deterministic context
  construction, bootstrap resampling, and all generated run keys.

### Four arms

All arms use the same task text, domain system prompt, GLM-5 agent configuration,
timeout/retry policy, no-tools directive, and a fresh isolated working directory per
agent call.

1. `aps_v5_frozen`
   - Exact corrected-v5 selection behavior: band weight plus hub bonus, CURRENT
     service floor, shared greedy remainder, no query-relevance term.
   - Its context payloads must match the existing v5 checkpoint at the level of
     selected skill names, bands, status, and estimated token counts before any paid
     call is allowed.

2. `aps_gxp_optimized`
   - Same graph bands and hard CURRENT protection as v5.
   - Adds deterministic task-skill relevance for non-CURRENT ranking and admission.
   - Adds complete per-fragment provenance and a deterministic context manifest.
   - May use less than the 8000-token ceiling; it must not fill unused budget with
     context that fails the frozen relevance-admission rule.

3. `flat_8000`
   - Full 59-file corpus offered with uniform priority under the existing
     deterministic 8000-token budget and truncation machinery.
   - Selection ignores graph and task relevance.
   - Provenance instrumentation is still recorded so governance metrics can be
     computed consistently.

4. `random_token_matched`
   - Corpus order is sampled reproducibly from `seed:task_id:run_id`.
   - Its target skill-context token count equals the deterministic
     `aps_gxp_optimized` token count for the same task and run.
   - The final sampled skill may be deterministically truncated to reach the target
     within the token estimator's one-token tolerance.
   - Selection ignores graph and task relevance, but graph relationship metadata is
     annotated after selection for analysis.

Total formal generation size: `10 tasks x 4 arms x 3 runs = 120 agent calls`.

## 4. Minimal Framework Optimization

Only the following behavior changes are in scope.

### 4.1 Deterministic task-skill relevance

Build retrieval text from the normalized skill name plus stable SKILL.md metadata
(title, description, and headings). Compute a deterministic lexical relevance score
from the task text using a standard-library implementation with no external model or
network call.

- CURRENT candidates are never excluded by relevance.
- Non-CURRENT candidates must satisfy the frozen relevance-admission rule or be the
  single best fallback candidate when every non-CURRENT score is zero.
- Relevance affects non-CURRENT ranking only; it must not override the band identity
  or CURRENT service guarantee.
- All tokenization, stop words, score constants, and tie breakers are source-coded,
  tested, and included in the source hash.

The implementation task may select a simple IDF-weighted lexical overlap or BM25-like
formula, but it must document the exact equation and freeze constants before the paid
smoke. It must not use smoke judge scores to tune those constants.

### 4.2 Relevance-gated context admission

The optimized arm stops after all CURRENT content and relevance-qualified
non-CURRENT candidates have been processed. It does not add low-relevance content
solely to exhaust the 8000-token ceiling.

#### 4.2.1 Pre-smoke structural efficiency amendment

The first two no-network Stage-0 attempts used the common 8000-token ceiling for
all arms. Raising the BM25 admission threshold once from 1.75 to 10.0 reduced the
median optimized context from 7994.5 to 7257.5 tokens, but the locked health window
still failed: the median remained 57.5 tokens above 7200 and only 4/10 tasks,
rather than 6/10, used at least 15% fewer tokens than flat. No agent response or
judge outcome existed or was inspected.

The user subsequently and explicitly reopened only this pre-smoke stop condition
and authorized one minimum structural optimization. The BM25 equation, constants,
and absolute threshold remain unchanged. Instead, the optimized arm now has a
deterministic soft context cap:

`optimized_soft_cap = floor(0.84 x common_budget) = 6720 tokens`

`effective_optimized_cap = min(common_budget, max(optimized_soft_cap,
full_CURRENT_demand))`

The 84% ratio encodes a 16% context-headroom contract: one percentage point beyond
the 15% efficiency target to accommodate deterministic token-estimator/truncation
rounding. Every valid CURRENT candidate remains protected in full even if CURRENT
demand exceeds the soft cap. Only relevance-qualified non-CURRENT material is
truncated or dropped at the effective cap. The other three arms are unchanged, and
`random_token_matched` continues to match the realized optimized token count.

The existing scheduler derives its per-skill non-CURRENT truncation limit from the
effective scheduling budget. Consequently, the 6720-token cap also changes that
limit from 2000 to 1680 estimated tokens for ordinary soft-cap tasks. This is a
deterministic consequence of treating 6720 as the optimized arm's effective budget,
not a second tuned parameter. If full CURRENT demand ever exceeds the common
8000-token ceiling, the runner must fail closed because full CURRENT protection and
the common hard ceiling would be mutually incompatible.

This makes the context-budget reduction partly a property enforced by design, not
an independently discovered outcome. Formal reporting must therefore distinguish
policy compliance and realized token counts from the empirical quality-retention
test. No further relevance or context-budget tuning is permitted after this
amendment.

### 4.3 Version-linked provenance manifest

For every candidate and every admitted fragment, save:

- normalized skill name;
- repository-relative source path (never an absolute path);
- source file SHA-256 and declared version if present;
- active node and skill-bound node IDs;
- graph relation and priority band;
- lexical relevance score, hub degree, and final priority score;
- original and injected estimated tokens;
- status and machine-readable selection/drop reason;
- injected-fragment SHA-256.

The ordered manifest also records task ID, arm, seed, budget, scheduler/graph/task
hashes, and the final prompt-context SHA-256. Checkpoints must never contain API
keys, environment dumps, absolute user paths, or unrelated repository content.

## 5. Outcome Evaluation

### Quality outcome

Use the same three 1-5 dimensions as v5:

- completeness;
- terminology precision;
- structure.

`quality_score` is their arithmetic mean. The judge receives each complete stored
response, not a prefix. Record requested and returned model identifiers, response
ID, system fingerprint, token usage, prompt hash, response hash, parse status, and
finish reason.

The supported DeepSeek reasoning model uses `temperature=0` and a 2000-token output
ceiling. The original 300-token ceiling was observed during the engineering smoke
to terminate in hidden reasoning with `finish_reason=length` and empty final
content for all four calls; no scores were returned. The higher ceiling is an
engineering parseability correction made before formal execution, not an outcome
or rubric change.

Do not run forced-choice pairwise judgments in v6. The v5 audit already established
that this protocol was strongly presentation-order dependent, and it is not needed
for the optimization questions.

### Confirmatory quality family

The three two-sided task-paired contrasts are:

1. `aps_gxp_optimized - aps_v5_frozen`;
2. `aps_gxp_optimized - flat_8000`;
3. `aps_gxp_optimized - random_token_matched`.

For each, average the three replicate scores within task-arm first, then report:

- task-level arm means and SDs;
- mean paired difference;
- 10,000-resample paired-task bootstrap 95% CI;
- exact two-sided sign-flip P value;
- Holm-adjusted P value across the three contrasts;
- paired `d_z`;
- positive/negative/tied task counts; and
- leave-one-task-out range.

Dimension-level contrasts and all GxP-oriented metrics are secondary/descriptive
unless a separate multiplicity family is explicitly frozen before formal execution.

## 6. Eval-Driven Development Gates

### Regression gates

Before any paid call:

- existing v5 tests pass unchanged;
- `aps_v5_frozen` reproduces the v5 checkpoint context payloads for all 10 tasks;
- CURRENT candidates remain admitted in full wherever v5 admitted them;
- all contexts stay within budget;
- stable run keys and atomic resume behavior remain unchanged;
- the v5 runner and stored v5 results are not modified.

### Capability gates

The optimized implementation must demonstrate:

- non-CURRENT relevance scores are deterministic and vary on at least one pair of
  tasks sharing a workflow node;
- the optimized arm can stop below the 8000-token ceiling;
- every candidate has a machine-readable selection reason;
- every admitted fragment has the required provenance fields;
- repeated context-only builds produce identical manifest hashes;
- token-matched random reaches the optimized target within one estimated token;
- simulated one-skill changes produce reproducible change-impact results; and
- checkpoint validation detects missing provenance, duplicate keys, budget
  violations, absolute paths, and secret-like field names.

## 7. Staged Smoke and Adjustment Policy

### Stage 0: no-network dry run

Build all `10 tasks x 4 arms x 1 context-only run = 40 cells`, repeat context
construction three times, and validate:

- frozen-v5 parity;
- context cardinality and budgets;
- relevance-score variation;
- optimized context-token distribution;
- manifest completeness and reproducibility;
- random token matching;
- change-impact metric determinism; and
- absence of secrets and absolute paths.

### Prespecified context-health window

Across the 10 optimized dry-run contexts:

- every task has all CURRENT candidates admitted as required;
- median optimized context is between 4000 and 7200 estimated tokens;
- no optimized context exceeds 8000 tokens;
- at least 6 of 10 tasks use at least 15% fewer tokens than `flat_8000`;
- at least one non-CURRENT selection differs between the two TFL tasks that shared
  identical v5 context.

If these bounds fail, one bounded pre-smoke adjustment to relevance constants or the
admission threshold is allowed. Record before/after values and the objective failed
bound in the tracker. Do not inspect outcome scores because Stage 0 has none.

After that original adjustment remained insufficient, the user explicitly reopened
the stop condition for the single structural soft-cap amendment in section 4.2.1.
This amendment is recorded before implementation and before any paid call. It does
not authorize iterative Stage-0 fishing: the next complete Stage-0 result is
accepted as the final pre-smoke eligibility result.

### Stage 1: paid four-call smoke

After explicit user approval in the execution task, run one representative task
through all four arms once (`1 x 4 x 1 = 4 agent calls`) and judge all four complete
responses.

The representative task is fixed as `task-20-tfl-ae` because v5 gave the two TFL
tasks identical routed context and routing underperformed both nonrouted controls on
this task. Do not switch the smoke task after seeing outputs.

Check:

- zero agent errors and zero judge parse errors;
- complete responses are stored and judged without prefix truncation;
- model identifiers/fingerprints and hashes are recorded;
- isolated working directories are confirmed;
- provenance manifests contain no secrets or absolute paths;
- token-matched random is within tolerance; and
- every formal-run validator passes on the smoke checkpoint.

### Allowed smoke adjustments

One implementation-adjustment cycle is allowed only for:

- crashes, timeout/retry defects, malformed prompts, missing/duplicate records;
- incorrect budget accounting or random token matching;
- missing provenance or unstable manifest hashes;
- empty/near-empty optimized context caused by a coding error;
- judge truncation, parsing, or provenance capture defects; or
- a violation of a Stage 0 context-health bound that was not observable until the
  real agent payload was assembled.

Do not change the task panel, arms, relevance constants, thresholds, quality rubric,
judge prompt, or statistical tests because of which arm scored better in the smoke.
Any allowed code/config change invalidates the smoke checkpoint; rerun all four smoke
arms, revalidate, then freeze new source hashes.

## 8. Formal Run and Approval Boundaries

The execution task may implement, test, and complete Stage 0 without external API
calls. It must obtain explicit user approval before:

1. sending the four smoke prompts to the generation provider;
2. sending the four complete smoke responses to the judge;
3. starting the 120-call formal generation; and
4. sending the 120 complete formal responses to the judge.

Prior approvals for earlier v5 outputs do not authorize new paid generation or new
external transmission.

On 2026-07-24, the user explicitly authorized, in the controlling v6 execution
task, all four previously separate actions: the four smoke generations, transmission
of the four complete smoke responses for scalar judging, the 120 formal
generations after a validated smoke, and transmission of all 120 complete formal
responses for scalar judging. The stage prerequisites, integrity checks, immutable
configuration checks, and scope-specific CLI flags remain mandatory despite that
authorization.

For the formal run:

- freeze runner, scheduler, graph, system prompt, task panel, skill-manifest, judge
  prompt, analysis script, and this design document hashes;
- randomize call order with seed 42 while preserving stable task-arm-run keys;
- checkpoint atomically after every call;
- resume only the same immutable run configuration;
- never silently replace a failed score;
- validate exactly 120 unique generation results and 120 complete-response scalar
  judgments; and
- archive the validated source checkpoint before analysis.

## 9. Formal Result Interpretation

### Outcome A: quality and governance advantage

If optimized APS meets superiority criteria versus a nonrouted control and passes
all governance/efficiency gates, report the specific supported contrast and measured
GxP-oriented properties. Do not generalize beyond the benchmark, model, judge, and
synthetic setting.

### Outcome B: similar quality with efficiency/governance advantage

If superiority is not detected but the engineering quality-retention threshold,
token-reduction threshold, provenance gates, and change-impact results are met,
position routing as a controlled context-management mechanism rather than a proven
quality-improvement mechanism.

### Outcome C: no incremental measured value

If neither quality nor prespecified efficiency/governance gates are met, retain the
v5 routing-null conclusion and describe the optimized result as a bounded negative
finding. Do not continue tuning on the formal task outcomes.

The manuscript, response letter, tables, appendices, or submission package must not
be changed until the validated report is reviewed and an explicit evidence-based
manuscript decision is recorded in the authoritative tracker.

## 10. Planned Implementation Artifacts

- `plan/jmir_aps_gxp_v6_execution_prompt_20260724.md`
- `experiments/run_experiment_v6_aps_gxp.py`
- `experiments/analyze_aps_gxp_experiment.py`
- `tests/test_experiment_v6_aps_gxp_design.py`
- `tests/test_analyze_aps_gxp_experiment.py`
- focused provenance/relevance tests in a new or existing context-loader test file
- `experiments/results/experiment_v6_aps_gxp_<timestamp>.json`
- `paper/jmir_ai/analysis_v6_aps_gxp/`

Do not overwrite v5 source data, reports, figures, or manuscript deliverables.
