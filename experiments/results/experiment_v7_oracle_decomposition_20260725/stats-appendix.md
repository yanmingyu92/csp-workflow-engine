# V7 Oracle Statistical Appendix

## Estimands and units

The task is the independent unit. Three repetitions are averaged within task and arm before task-level graph-minus-BM25 inference. The oracle retrieval estimands are derived from frozen registry requirements and manifest membership; no arm score enters retrieval classification or router tuning.

| Task-level graph minus BM25 estimand | Mean | Bootstrap 95% CI | LOO range | LOO sign changes |
|---|---:|---:|---:|---:|
| Required-section recall | 0.0000 | [0.0000, 0.0000] | [0.0000, 0.0000] | 0 |
| Required-section precision | -0.0019 | [-0.0155, 0.0088] | [-0.0041, 0.0035] | 2 |
| Required-token precision | -0.0038 | [-0.0143, 0.0022] | [-0.0048, 0.0010] | 1 |
| Deterministic output score | 0.0087 | [-0.0280, 0.0451] | [-0.0012, 0.0188] | 1 |
| Output score excluding provenance criterion | 0.0005 | [-0.0493, 0.0491] | [-0.0140, 0.0150] | 5 |

Bootstrap intervals use 10,000 deterministic task-level resamples with fixed metric-specific seeds. LOO values omit one task at a time.

## Sensitivity analyses

The substantive-score sensitivity removes provenance-citation criterion weight before rescoring each cell. It tests whether any graph/BM25 difference is driven only by the explicit evidence-ID criterion; it does not repair generator or retrieval errors.

Lexical-overlap, multi-hop, and task-category strata are exploratory. They were not preregistered for superiority, have small unequal task counts, and are not multiplicity-adjusted.

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

## Evidence/output table

```json
{"evidence_unchanged__output_improved": 12, "evidence_unchanged__output_unchanged": 52, "evidence_unchanged__output_worsened": 8}
```

## Limitations

- The frozen registry supplies task-level provenance sections; the same declared section union is conservatively mapped to each atomic criterion because no finer criterion-to-section field exists.
- Registry section matching is exact by skill and heading substring. It does not infer unregistered semantic evidence.
- No graph-only arm exists. Evidence-delta/output-delta conditioning has no evidence-improved observations.
- Repetitions share task prompts and frozen retrieval logic; they are not treated as independent sample-size inflation.
- Error attribution is conservative and deterministic. Unresolvable semantics remain in the explicit unresolved class.
- No cross-version mean comparison is performed, and no unregistered post hoc superiority claim is made.
