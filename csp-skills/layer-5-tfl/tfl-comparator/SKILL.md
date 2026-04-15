---
name: tfl-comparator
description: Compare TFL production vs QC outputs with cell-by-cell precision. Triggers on "TFL QC", "QC", "quality control", "TFL validation", "independent QC", "output verification".
version: "2.0"
user-invocable: true
context: fork
model: sonnet
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
argument-hint: "[options] -- --production <prod-path> --qc <qc-path> --output <report-path>"
---

## Runtime Configuration (Step 0)

Resolve configuration in order:
1. `$ARGUMENTS` (highest precedence)
2. `reports/tfl-qc-report.html` -- prior comparison results
3. `output/tfl/tables/` -- production outputs
4. `output/tfl/qc/` -- QC outputs

```yaml
config_resolution:
  study_id: "$ARGUMENTS.study_id || study-config.study_id"
  production_path: "$ARGUMENTS.production || 'output/tfl/tables/'"
  qc_path: "$ARGUMENTS.qc || 'output/tfl/qc/'"
  output_report: "$ARGUMENTS.output || 'reports/tfl-comparison-report.html'"
  numeric_tolerance: "$ARGUMENTS.tolerance || 0.001"
```

## EXECUTE NOW
Parse $ARGUMENTS: --production, --qc, --output, --tolerance, --dry-run
**START NOW.**

---

## Philosophy

**Comparison must detect both content and formatting differences.** Cell-by-cell comparison for tables, pixel comparison for figures. The comparator is the engine that powers QC validation: it produces the detailed diff that QC reviewers act upon.

---

## Input/Output Specification

### Inputs (matching regulatory-graph.yaml node `tfl-qc-validation`)
| Input | Format | Required | Source |
|-------|--------|----------|--------|
| Production TFLs | rtf/pdf/text | Yes | output/tfl/tables/ |
| QC TFLs | rtf/pdf/text | Yes | output/tfl/qc/ |
| Table specifications | yaml | No | specs/table-specs.yaml |

### Outputs
| Output | Format | Path Pattern | Description |
|--------|--------|--------------|-------------|
| Comparison report | html | reports/tfl-comparison-report.html | Detailed diff |
| Discrepancy log | yaml | ops/tfl-discrepancies.yaml | Machine-readable differences |

---

## Cell-by-Cell Comparison Logic

### Table Comparison Algorithm
```python
def compare_tables(production, qc, tolerance=0.001):
    """
    Cell-by-cell comparison algorithm:

    1. Parse both tables into structured grids (row_label x column)
    2. Normalize whitespace and formatting
    3. Align rows by label (exact match first, then fuzzy)
    4. Compare each cell:
       a. Numeric values: |prod - qc| <= tolerance
       b. String values: exact match after normalization
       c. Percentages: compare as numeric after stripping '%'
    5. Report:
       a. Matched cells
       b. Mismatched cells with diff detail
       c. Missing rows (in one but not the other)
       d. Extra rows
    """
    prod_grid = parse_table(production)
    qc_grid = parse_table(qc)

    results = {
        'matched': 0,
        'mismatched': [],
        'missing_in_qc': [],
        'missing_in_prod': [],
        'total_cells': 0
    }

    # Align rows
    for prod_row in prod_grid:
        qc_row = find_matching_row(prod_row.label, qc_grid)
        if qc_row is None:
            results['missing_in_qc'].append(prod_row.label)
            continue

        # Compare cells
        for col in prod_row.columns:
            prod_val = normalize(prod_row[col])
            qc_val = normalize(qc_row[col])

            if is_numeric(prod_val) and is_numeric(qc_val):
                if abs(float(prod_val) - float(qc_val)) > tolerance:
                    results['mismatched'].append({
                        'row': prod_row.label,
                        'column': col,
                        'production': prod_val,
                        'qc': qc_val,
                        'diff': abs(float(prod_val) - float(qc_val)),
                        'type': 'numeric'
                    })
                else:
                    results['matched'] += 1
            else:
                if prod_val != qc_val:
                    results['mismatched'].append({
                        'row': prod_row.label,
                        'column': col,
                        'production': prod_val,
                        'qc': qc_val,
                        'type': 'string'
                    })
                else:
                    results['matched'] += 1
            results['total_cells'] += 1

    return results
```

### Floating-Point Tolerance
```yaml
tolerance_rules:
  counts: 0        # Integer counts must match exactly
  percentages: 0.1  # Allow 0.1% difference (rounding)
  means: 0.01       # Allow 0.01 difference in means
  p_values: 0.0001  # Allow 4th decimal place difference
  cis: 0.01         # Allow CI boundary differences
```

### Figure Comparison
```python
def compare_figures(production_path, qc_path, pixel_tolerance=0.05):
    """
    Pixel-level comparison for figures:
    1. Load both images
    2. Resize to same dimensions if needed
    3. Compute pixel-by-pixel difference
    4. Report % of different pixels
    5. Generate side-by-side comparison image

    Also compare text annotations:
    - Title
    - Axis labels
    - Legend entries
    - Statistical annotations
    """
    prod_img = load_image(production_path)
    qc_img = load_image(qc_path)

    diff_percent = compute_pixel_diff(prod_img, qc_img)

    if diff_percent > pixel_tolerance * 100:
        return {'status': 'DIFFER', 'diff_percent': diff_percent}
    else:
        return {'status': 'MATCH', 'diff_percent': diff_percent}
```

---

## Output Schema

```yaml
comparison_result:
  study_id: "{study_id}"
  comparison_timestamp: "{ISO_8601}"

  summary:
    total_outputs_compared: "{n_outputs}"
    exact_matches: "{n_exact}"
    within_tolerance: "{n_tolerance}"
    discrepancies: "{n_disc}"
    critical_discrepancies: "{n_critical}"

  detailed_results:
    - tfl_id: "Table 14.1.3"
      production: "output/tfl/tables/table-14.1.3.rtf"
      qc: "output/tfl/qc/table-14.1.3-qc.rtf"
      match_status: "EXACT"
      total_cells: "{n_cells}"
      matched_cells: "{n_matched}"
      mismatched_cells: 0

    - tfl_id: "Table 14.2.1"
      match_status: "DISCREPANCY"
      total_cells: "{n_cells}"
      matched_cells: "{n_matched}"
      mismatched_cells: "{n_mismatched}"
      differences:
        - row: "TEAE"
          column: "{treatment_arm_1} n"
          production: "72"
          qc: "73"
          absolute_diff: 1
          classification: "CRITICAL"
```

---

## Edge Cases

### Different Row Ordering
- Production may sort AE rows differently than QC
- Align by row label, not by position
- Flag if same data appears in different rows

### Missing Rows in One Output
- Subject may be in production but not QC (or vice versa)
- Report as "missing_in_qc" or "missing_in_production"
- Require root cause investigation

### Precision Differences
- Production: "75.1", QC: "75.10" -- cosmetic, not content
- Normalize before comparison
- Only flag if numeric values differ beyond tolerance

---

## Integration Points

### Upstream Skills
- `/tfl-table-generator` -- Production outputs
- `/tfl-double-programmer` -- QC outputs

### Downstream Skills
- `/tfl-qc-validator` -- Uses comparison results for QC report
- `/workflow` -- Gate decisions based on match status

### Related Skills
- `/data-quality` -- Pre-comparison data validation

---

## Evaluation Criteria

**Mandatory:**
- Cell-by-cell comparison for all tables
- Numeric tolerance documented and applied
- Discrepancies classified by severity

**Recommended:**
- Pixel comparison for figures
- Side-by-side diff visualization
- Automated re-comparison after fixes

---

## Critical Constraints

**Never:**
- Skip comparison for any TFL
- Use tolerance to hide real differences
- Report "match" without actual comparison

**Always:**
- Apply documented tolerance consistently
- Classify all differences by severity
- Generate machine-readable discrepancy log
- Preserve original values in discrepancy records

---

## Examples

### Compare All TFLs
```bash
python csp-skills/layer-5-tfl/tfl-comparator/script.py \
  --production output/tfl/tables/ \
  --qc output/tfl/qc/ \
  --output reports/tfl-comparison-report.html
```

### Compare Single Table
```bash
python csp-skills/layer-5-tfl/tfl-comparator/script.py \
  --production output/tfl/tables/table-14.1.3.rtf \
  --qc output/tfl/qc/table-14.1.3-qc.rtf \
  --output reports/comparison-14.1.3.html \
  --tolerance 0.001
```
