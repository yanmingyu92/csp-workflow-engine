# V7 Oracle Figure Catalog

## Figure 1 -- Held-out oracle retrieval diagnostics

Purpose: compare graph + BM25 and BM25-only retrieval coverage, precision, dilution, and redundancy. Source: cell-level frozen manifests and registry-required sections. Caveat: registry requirements are task-level section declarations.

File: `figures/figure-01-oracle-retrieval.svg`

## Figure 2 -- Criterion-level error decomposition

Purpose: separate retrieval failures from evidence-present generator, derivation, schema, hallucination, citation, and judge discordance. Source: deterministic criterion histories. Caveat: classes are rule-based and mutually exclusive by precedence.

File: `figures/figure-02-error-decomposition.svg`

## Figure 3 -- Evidence delta versus output delta

Purpose: show whether output changes coincide with graph-only required-evidence gain. Source: task-level paired graph/BM25 oracle metrics and deterministic scores. Caveat: all required-section recall deltas are zero, so the graph-benefit conditional question is unidentified in V7.

File: `figures/figure-03-evidence-output-delta.svg`
