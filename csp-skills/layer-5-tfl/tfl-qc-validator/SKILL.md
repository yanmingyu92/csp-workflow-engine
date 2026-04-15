---
name: tfl-qc-validator
description: Independent QC validation of all TFL outputs. Triggers on "TFL QC", "QC", "quality control", "TFL validation", "independent QC", "output verification".
version: "2.0"
user-invocable: true
context: fork
model: sonnet
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
argument-hint: "[options] -- --input <tfl-dir> --qc-input <qc-dir> --output <report-path>"
---

## Runtime Configuration (Step 0)

Resolve configuration in order:
1. `$ARGUMENTS` (highest precedence)
2. `reports/tfl-qc-report.html` -- prior QC results
3. `output/tfl/tables/` -- production TFLs
4. `specs/table-specs.yaml` -- expected outputs

```yaml
config_resolution:
  study_id: "$ARGUMENTS.study_id || study-config.study_id"
  production_dir: "$ARGUMENTS.input || 'output/tfl/tables/'"
  qc_dir: "$ARGUMENTS.qc_input || 'output/tfl/qc/'"
  output_report: "$ARGUMENTS.output || 'reports/tfl-qc-report.html'"
  tolerance: "$ARGUMENTS.tolerance || 0.001"
```

## EXECUTE NOW
Parse $ARGUMENTS: --input, --qc-input, --output, --tolerance, --dry-run
**START NOW.**

---

## Philosophy

**QC validation ensures accuracy.** Every number in a table must trace back to ADaM data through reproducible code. The QC process is independent: separate programmer, separate code, same specifications. Discrepancies must be investigated to root cause before the output can be considered final.

---

## Input/Output Specification

### Inputs (matching regulatory-graph.yaml node `tfl-qc-validation`)
| Input | Format | Required | Source |
|-------|--------|----------|--------|
| Production TFLs | rtf/pdf | Yes | output/tfl/tables/ |
| ADaM datasets | xpt | Yes | output/adam/ |
| Table specifications | yaml | Yes | specs/table-specs.yaml |
| QC outputs (independent) | rtf/pdf | Yes | output/tfl/qc/ |

### Outputs (matching regulatory-graph.yaml node `tfl-qc-validation`)
| Output | Format | Path Pattern | Description |
|--------|--------|--------------|-------------|
| TFL QC report | html/pdf | reports/tfl-qc-report.html | QC comparison results |
| QC issue log | yaml | ops/tfl-qc-issues.yaml | Discrepancies found |

---

## QC Comparison Methodology

### Cell-by-Cell Comparison (Tables)
```yaml
comparison_method:
  type: "cell_by_cell"
  steps:
    1. "Parse production table into structured grid"
    2. "Parse QC table into structured grid"
    3. "Align rows by label (exact or fuzzy match)"
    4. "Compare each cell value"

  numeric_tolerance: 0.001  # For floating-point comparison
  string_comparison: "case_sensitive, whitespace_normalized"

  discrepancy_classification:
    CRITICAL:
      description: "Different statistical results (counts, means, p-values)"
      action: "MUST resolve before finalization"
      examples:
        - "n count differs between production and QC"
        - "Mean value differs beyond tolerance"
        - "p-value differs in 4th decimal place"

    HIGH:
      description: "Different categorization or grouping"
      action: "Must investigate, may be acceptable with justification"
      examples:
        - "Subject classified in different treatment group"
        - "Different sort order of rows"

    MEDIUM:
      description: "Formatting differences"
      action: "Should align, may be acceptable"
      examples:
        - "Different decimal precision"
        - "Different footnote wording"

    LOW:
      description: "Cosmetic differences"
      action: "Acceptable if content matches"
      examples:
        - "Extra whitespace"
        - "Different font rendering"
```

### Figure Comparison
```yaml
figure_comparison:
  method: "pixel_comparison"
  tolerance: "5% pixel difference"
  also_check:
    - "Title matches specification"
    - "Axis labels correct"
    - "Legend matches treatment groups"
    - "Statistical annotations present"
```

---

## Output Schema

```yaml
qc_result:
  study_id: "{study_id}"
  qc_timestamp: "{ISO_8601}"

  summary:
    total_tfls_checked: "{n_tfls}"
    matched: "{n_matched}"
    discrepancies_found: "{n_discrepancies}"
    critical_issues: "{n_critical}"
    overall_status: "PASS | FAIL | CONDITIONAL"

  tfl_results:
    - tfl_id: "Table 14.1.3"
      title: "Demographics"
      production_path: "output/tfl/tables/table-14.1.3.rtf"
      qc_path: "output/tfl/qc/table-14.1.3-qc.rtf"
      status: "MATCH"
      discrepancies: []

    - tfl_id: "Table 14.2.1"
      title: "AE Summary"
      status: "DISCREPANCY"
      discrepancies:
        - row: "TEAE n"
          column: "{treatment_arm_1}"
          production_value: "72"
          qc_value: "73"
          classification: "CRITICAL"
          root_cause: "PENDING"
          resolution: "OPEN"
```

---

## Edge Cases

### Minor Floating-Point Differences
- Values differing only in rounding (e.g., 75.1 vs 75.10000001) are acceptable
- Use tolerance-based comparison for numeric values
- Document tolerance used in the QC report

### Missing QC Output
- If QC output is missing for a required TFL: status = "NO_QC" (treated as critical)
- All SAP-required TFLs must have both production and QC outputs

### Extra Rows or Columns
- Production may have rows not in QC (or vice versa)
- Flag as discrepancy for investigation
- May indicate different data filtering or derivation logic

---

## Integration Points

### Upstream Skills
- `/tfl-table-generator` -- Production TFLs to validate
- `/tfl-double-programmer` -- Independent QC outputs
- `/tfl-comparator` -- Automated comparison engine

### Downstream Skills
- `/workflow` -- QC pass/fail gates

### Related Skills
- `/data-quality` -- Pre-QC data checks

---

## Evaluation Criteria

**Mandatory:**
- All TFLs independently QC'd
- Zero unresolved critical discrepancies
- QC comparison report generated

**Recommended:**
- QC programs archived for audit trail
- Root cause documented for all discrepancies
- Comparison automated (not manual)

---

## Critical Constraints

**Never:**
- Mark a TFL as "passed" without actual comparison
- Ignore discrepancies or suppress findings
- Manually adjust production to match QC without root cause

**Always:**
- Compare production vs independent QC output
- Classify all discrepancies by severity
- Document root cause for each discrepancy
- Resolve all critical issues before finalization

---

## Examples

### Full QC Validation
```bash
python csp-skills/layer-5-tfl/tfl-qc-validator/script.py \
  --input output/tfl/tables/ \
  --qc-input output/tfl/qc/ \
  --output reports/tfl-qc-report.html
```

### Single TFL QC
```bash
python csp-skills/layer-5-tfl/tfl-qc-validator/script.py \
  --input output/tfl/tables/table-14.1.3.rtf \
  --qc-input output/tfl/qc/table-14.1.3-qc.rtf \
  --output reports/tfl-qc-report.html
```
