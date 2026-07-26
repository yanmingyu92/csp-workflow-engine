# APS-GxP v6 Analysis

Source SHA-256: `fb9f787a6e95e2bd0813c7f7b90fd986e64adeba09305645572a3875df927aa0`
Dry run: `false`

## Task-Level Arm Means

| Arm | Tasks | Mean quality | SD across tasks |
|---|---:|---:|---:|
| aps_v5_frozen | 10 | 4.23 | 0.52 |
| aps_gxp_optimized | 10 | 4.24 | 0.44 |
| flat_8000 | 10 | 4.07 | 0.60 |
| random_token_matched | 10 | 4.03 | 0.50 |

## Confirmatory Quality Contrasts

Replicates are averaged within task. CIs use 10,000 paired-task bootstrap resamples; P values are exact two-sided sign-flip tests with Holm adjustment across the three locked contrasts.

| Contrast | Tasks | Difference | 95% CI | Exact P | Holm P | dz | Signs (+/-/=) | LOTO range |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| aps_gxp_optimized - aps_v5_frozen | 10 | 0.01 | [-0.14, 0.17] | 1.000 | 1.000 | 0.04 | 4/4/2 | [-0.04, 0.05] |
| aps_gxp_optimized - flat_8000 | 10 | 0.18 | [0.01, 0.33] | .102 | .270 | 0.63 | 6/2/2 | [0.14, 0.23] |
| aps_gxp_optimized - random_token_matched | 10 | 0.21 | [0.02, 0.40] | .090 | .270 | 0.66 | 7/3/0 | [0.16, 0.26] |

## GxP-Oriented Governance Metrics

These are separate deterministic architectural proxies; they do not establish operational GxP compliance.

- Provenance completeness: 100.00%
- Manifest reproducibility: 100.00%

### Context Scope

| Arm | Category | Skills | Tokens |
|---|---|---:|---:|
| random_token_matched | current | 1 | 3113 |
| random_token_matched | relevance_qualified_adjacent | 16 | 30839 |
| random_token_matched | global | 7 | 7204 |
| random_token_matched | out_of_scope | 82 | 129373 |
| aps_v5_frozen | current | 54 | 122088 |
| aps_v5_frozen | relevance_qualified_adjacent | 93 | 117642 |
| aps_v5_frozen | global | 0 | 0 |
| aps_v5_frozen | out_of_scope | 0 | 0 |
| flat_8000 | current | 6 | 5895 |
| flat_8000 | relevance_qualified_adjacent | 54 | 58974 |
| flat_8000 | global | 0 | 0 |
| flat_8000 | out_of_scope | 150 | 174711 |
| aps_gxp_optimized | current | 54 | 122088 |
| aps_gxp_optimized | relevance_qualified_adjacent | 36 | 43767 |
| aps_gxp_optimized | global | 6 | 4674 |
| aps_gxp_optimized | out_of_scope | 0 | 0 |

## Efficiency and Frozen Decision

- Optimized-versus-flat mean skill-token reduction: 28.82%
- Prespecified 15% reduction gate: PASS
- Token reduction is partly policy-enforced by the frozen 84% soft-cap design; quality retention remains empirical.
- Outcome: **B — similar quality with efficiency/governance advantage**


## Complete-Response Judging Integrity

Status: **PASS**
Policy: `full_stored_response_no_character_truncation`
Validation errors: 0
