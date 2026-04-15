---
name: quality-report
description: Generate data quality report with metrics and visualizations. Triggers on "data quality", "raw data check", "data validation", "missing values", "duplicate records", "range check".
version: "2.0"
user-invocable: true
context: fork
model: sonnet
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
argument-hint: "[options] -- --input <validation-log> --output <report-path> --format [html|pdf|both]"
---

## Runtime Configuration (Step 0)

Resolve configuration in order:
1. `$ARGUMENTS` (highest precedence)
2. `ops/raw-validation-log.yaml` -- validation check results
3. `ops/discrepancy-log.yaml` -- reconciliation findings
4. `reports/data-quality-report.html` -- prior report for trend comparison

```yaml
config_resolution:
  study_id: "$ARGUMENTS.study_id || study-config.study_id"
  validation_log: "$ARGUMENTS.input || 'ops/raw-validation-log.yaml'"
  reconciliation_log: "ops/discrepancy-log.yaml"
  output_path: "$ARGUMENTS.output || 'reports/data-quality-report.html'"
  report_format: "$ARGUMENTS.format || 'html'"
```

## EXECUTE NOW
Parse $ARGUMENTS: --input, --output, --format, --dry-run
**START NOW.**

---

## Philosophy

**Quality reports provide stakeholders with actionable insights.** Every metric must be traceable to a specific validation check. The report serves as evidence of data integrity for internal review and regulatory submission. Reports must be human-readable (HTML/PDF) and machine-parseable (embedded YAML metadata).

---

## Input/Output Specification

### Inputs
| Input | Format | Required | Source |
|-------|--------|----------|--------|
| Raw validation log | yaml | Yes | ops/raw-validation-log.yaml |
| Discrepancy log | yaml | No | ops/discrepancy-log.yaml |
| Extraction manifest | yaml | Yes | data/raw/extraction-manifest.yaml |
| Study configuration | yaml | Yes | specs/study-config.yaml |

### Outputs
| Output | Format | Path Pattern | Description |
|--------|--------|--------------|-------------|
| Quality report | html/pdf | reports/data-quality-report.html | Stakeholder-facing report |
| Quality summary | yaml | ops/quality-summary.yaml | Machine-readable metrics |

---

## Report Structure

### Section 1: Executive Summary
```yaml
executive_summary:
  study_id: "{study_id}"
  report_date: "{ISO_8601_date}"
  data_cut_date: "{data_cut_date}"
  overall_status: "PASS | FAIL | CONDITIONAL"
  total_subjects: "{n_subjects}"
  total_records: "{total_records}"
  critical_issues: "{n_critical}"
  warnings: "{n_warnings}"
  data_completeness: "{completeness_pct}%"
```

### Section 2: Domain-Level Metrics
```yaml
domain_metrics:
  - domain: "DM"
    records: {n_subjects}
    variables: 42
    completeness: "98.5%"
    issues:
      - type: "missing"
        variable: "ETHNIC"
        count: 3
        percent: "1.2%"
        severity: "WARNING"
    quality_score: "98.5"

  - domain: "AE"
    records: "{n_ae_records}"
    variables: 38
    completeness: "99.1%"
    issues:
      - type: "duplicate"
        description: "2 records with same subject/term/start date"
        severity: "ERROR"
    quality_score: "99.1"
```

### Section 3: Trend Analysis
```yaml
trend_analysis:
  data_cuts_compared:
    - date: "2024-03-31"
      completeness: "96.2%"
      issues: 45
    - date: "2024-06-30"
      completeness: "98.5%"
      issues: 12
  trend: "IMPROVING"
```

### Section 4: Recommendations
```yaml
recommendations:
  - priority: "HIGH"
    action: "Resolve 3 missing ETHNIC values in DM before database lock"
    affected_subjects: ["{study_id}-{SITEID}-{SUBJID}", ...]
  - priority: "MEDIUM"
    action: "Investigate 2 duplicate AE records for root cause"
    affected_subjects: ["{study_id}-{SITEID}-{SUBJID}", ...]
```

---

## Quality Metrics Computation

### Completeness Score
```python
completeness = (total_non_null_values / total_expected_values) * 100
# Per-domain and per-variable
# Required fields weighted higher than optional fields
```

### Consistency Score
```python
consistency = (total_consistent_records / total_compared_records) * 100
# Cross-form date consistency
# Cross-source value consistency
# Treatment arm consistency
```

### Overall Quality Score
```python
quality_score = (
    0.4 * completeness +
    0.3 * consistency +
    0.2 * type_conformance +
    0.1 * range_compliance
)
# Weighted composite score
```

---

## Output Schema

```yaml
quality_report:
  metadata:
    study_id: "{study_id}"
    generated_at: "{ISO_8601}"
    report_version: "2.0"
    source_logs:
      - "ops/raw-validation-log.yaml"
      - "ops/discrepancy-log.yaml"
      - "data/raw/extraction-manifest.yaml"

  summary:
    overall_score: "{quality_score}"
    status: "PASS | FAIL | CONDITIONAL"
    total_issues: "{n_issues}"
    critical_issues: "{n_critical}"

  domain_summaries:
    - domain: "DM"
      score: "{domain_score}"
      records: "{n_records}"
      issues: "{n_issues}"
```

---

## Edge Cases

### Empty Validation Log
- If validation has not been run, report cannot be generated
- Error message directing user to run `/data-validator` first

### No Prior Report for Trend
- First report: skip trend section
- Note in report that trend analysis will be available after second data cut

### All Checks Pass
- Report still generated with full metrics
- Include positive findings (not just issues)
- Document the validation coverage

---

## Integration Points

### Upstream Skills
- `/data-validator` -- Validation results feed into this report
- `/data-reconciler` -- Reconciliation findings feed into this report
- `/data-extract` -- Extraction manifest for metadata

### Downstream Skills
- `/workflow` -- Quality gate decision point
- `/sdtm-dm-mapper` -- Proceeds only after quality report passes

### Related Skills
- `/data-quality` -- Lighter-weight quality checks at any stage

---

## Evaluation Criteria

**Mandatory:**
- All datasets covered in the report
- Every validation check result included
- Executive summary with clear pass/fail status
- Actionable recommendations for all issues

**Recommended:**
- Trend analysis across data cuts
- Visual charts (completeness heatmap, issue distribution)
- Comparison with quality benchmarks

---

## Critical Constraints

**Never:**
- Generate report from incomplete validation results
- Suppress or downplay critical issues
- Omit the data cut date and study identifier
- Generate report without validation log

**Always:**
- Include timestamp and study identifier in report
- Provide actionable recommendations for each issue
- Make the report reproducible from the same input logs
- Include both human-readable and machine-readable sections

---

## Examples

### Generate Full Report
```bash
python csp-skills/layer-1-raw-data/quality-report/script.py \
  --input ops/raw-validation-log.yaml \
  --output reports/data-quality-report.html \
  --format html \
  --study-config specs/study-config.yaml
```

### PDF Report with Trends
```bash
python csp-skills/layer-1-raw-data/quality-report/script.py \
  --input ops/raw-validation-log.yaml \
  --output reports/data-quality-report.pdf \
  --format pdf \
  --compare-prior reports/data-quality-report-prev.html
```
