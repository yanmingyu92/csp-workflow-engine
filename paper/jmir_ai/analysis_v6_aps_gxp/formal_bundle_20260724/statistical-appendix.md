# Statistical Appendix

Unit of analysis: task. Three generations are averaged within each task-arm cell before inference.

Uncertainty: 10,000-resample paired-task percentile bootstrap 95% CI. Inference: exact two-sided sign-flip test, Holm-adjusted across the three frozen quality contrasts. Effect size: paired Cohen d_z.

| Contrast | n tasks | Mean difference | 95% CI | Exact P | Holm P | d_z |
|---|---:|---:|---:|---:|---:|---:|
| aps_gxp_optimized - aps_v5_frozen | 10 | 0.01 | [-0.14, 0.17] | 1.000 | 1.000 | 0.04 |
| aps_gxp_optimized - flat_8000 | 10 | 0.18 | [0.01, 0.33] | .102 | .270 | 0.63 |
| aps_gxp_optimized - random_token_matched | 10 | 0.21 | [0.02, 0.40] | .090 | .270 | 0.66 |

The -0.20 optimized-minus-flat CI lower-bound threshold is an engineering quality-retention rule, not a validated clinical noninferiority margin. Dimension-level analyses are descriptive.
