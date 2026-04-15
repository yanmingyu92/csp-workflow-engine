---
name: data-validator
description: Validate raw data quality (types, ranges, duplicates). Triggers on "data quality", "raw data check", "data validation", "missing values", "duplicate records", "range check".
version: "2.0"
user-invocable: true
context: fork
model: sonnet
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
argument-hint: "[options] -- --input <raw-dir> --output <validated-dir> --checks [all|type|range|missing|duplicate|cross-form]"
---

## Runtime Configuration (Step 0)

Resolve configuration in order:
1. `$ARGUMENTS` (highest precedence)
2. `specs/study-config.yaml` -- variable definitions, expected ranges
3. `data/raw/extraction-manifest.yaml` -- expected row/column counts
4. `reports/data-quality-report.html` -- prior validation results

```yaml
config_resolution:
  study_id: "$ARGUMENTS.study_id || study-config.study_id"
  input_dir: "$ARGUMENTS.input || 'data/raw/'"
  output_dir: "$ARGUMENTS.output || 'data/validated/'"
  check_types: "$ARGUMENTS.checks || ['type', 'range', 'missing', 'duplicate', 'cross-form']"
  fail_threshold: "$ARGUMENTS.threshold || 0.05"
```

## EXECUTE NOW
Parse $ARGUMENTS: --input, --output, --checks, --threshold, --dry-run
**START NOW.**

---

## Philosophy

**Raw data validation is the first quality gate.** Catching issues here prevents cascading errors through SDTM and ADaM. Every validation check must be documented, reproducible, and traceable. The validation report serves as evidence of data integrity for regulatory submissions per ICH E6(R2).

---

## Input/Output Specification

### Inputs (matching regulatory-graph.yaml node `raw-data-validation`)
| Input | Format | Required | Source |
|-------|--------|----------|--------|
| Raw EDC datasets | csv/sas7bdat | Yes | data/raw/ |
| Extraction manifest | yaml | Yes | data/raw/extraction-manifest.yaml |
| Study configuration | yaml | Yes | specs/study-config.yaml |

### Outputs (matching regulatory-graph.yaml node `raw-data-validation`)
| Output | Format | Path Pattern | Description |
|--------|--------|--------------|-------------|
| Validated datasets | csv/sas7bdat | data/validated/ | Cleaned raw data |
| Data quality report | html/pdf | reports/data-quality-report.html | Validation results |
| Validation log | yaml | ops/raw-validation-log.yaml | Check-by-check results |

---

## Validation Check Types

### Type 1: Data Type Validation
```python
validation_rules:
  - rule_id: "TYPE-001"
    description: "Numeric fields contain only numbers or missing indicators"
    check: "is_numeric(column)"
    severity: "ERROR"
    examples:
      - field: "AGE"
        expected_type: "integer"
        valid_range: "18-120"
      - field: "WEIGHT"
        expected_type: "float"
        valid_range: "20-500"
      - field: "VISITDATE"
        expected_type: "date"
        expected_format: "ISO 8601 or documented EDC format"
```

### Type 2: Range Validation
```python
validation_rules:
  - rule_id: "RANGE-001"
    description: "Values within protocol-defined ranges"
    check: "value in [min, max]"
    severity: "WARNING"
    range_checks:
      - variable: "AGE"
        min: 18
        max: 120
        source: "Protocol eligibility criteria"
      - variable: "SYSBP"  # Systolic blood pressure
        min: 60
        max: 260
        source: "Clinical plausible range"
      - variable: "DIABP"  # Diastolic blood pressure
        min: 30
        max: 160
        source: "Clinical plausible range"
      - variable: "TEMP"   # Temperature
        min: 30.0
        max: 43.0
        source: "Clinical plausible range (Celsius)"
      - variable: "HEIGHT"
        min: 50
        max: 250
        source: "Clinical plausible range (cm)"
```

### Type 3: Missing Value Detection
```python
validation_rules:
  - rule_id: "MISS-001"
    description: "Required fields are not null"
    check: "not_null(column)"
    severity: "ERROR"
    required_fields:
      DM: ["STUDYID", "SITEID", "SUBJID", "BRTHDAT", "SEX", "RACE"]
      AE: ["STUDYID", "SITEID", "SUBJID", "AETERM", "AESTDAT"]
      LB: ["STUDYID", "SITEID", "SUBJID", "LBTEST", "LBORRES", "LBDAT"]

  - rule_id: "MISS-002"
    description: "Non-required fields missing rate > threshold"
    check: "missing_rate(column) > threshold"
    severity: "WARNING"
    threshold: 0.05  # Flag if >5% missing
```

### Type 4: Duplicate Detection
```python
validation_rules:
  - rule_id: "DUP-001"
    description: "No duplicate records within domain"
    check: "is_unique(dataset, key_columns)"
    severity: "ERROR"
    key_columns:
      DM: ["STUDYID", "SITEID", "SUBJID"]
      AE: ["STUDYID", "SITEID", "SUBJID", "AETERM", "AESTDAT", "AESEQ"]
      LB: ["STUDYID", "SITEID", "SUBJID", "LBTEST", "LBDAT", "LBTIM"]
      VS: ["STUDYID", "SITEID", "SUBJID", "VSTEST", "VSDAT", "VSTIM"]

  - rule_id: "DUP-002"
    description: "Duplicate subject identifiers across domains"
    check: "cross_domain_subject_check()"
    severity: "ERROR"
```

### Type 5: Cross-Form Consistency
```python
validation_rules:
  - rule_id: "CROSS-001"
    description: "Subjects in all domains exist in DM"
    check: "all_subjects_in_dm(domain_datasets)"
    severity: "ERROR"

  - rule_id: "CROSS-002"
    description: "Date ordering is logical"
    check: "informed_consent_date <= first_dose_date <= last_dose_date <= eos_date"
    severity: "WARNING"

  - rule_id: "CROSS-003"
    description: "Visit dates consistent across forms"
    check: "visit_dates_match(domain_datasets)"
    severity: "WARNING"
```

---

## Output Schema

```yaml
validation_result:
  study_id: "{study_id}"
  validation_timestamp: "{ISO_8601}"
  input_dir: "data/raw/"
  output_dir: "data/validated/"

  summary:
    total_checks: "{n_checks}"
    passed: "{n_passed}"
    failed: "{n_failed}"
    warnings: "{n_warnings}"
    overall_status: "PASS | FAIL"

  checks:
    - rule_id: "TYPE-001"
      domain: "DM"
      variable: "AGE"
      result: "PASS"
      details: "All 254 values are valid integers"
    - rule_id: "MISS-001"
      domain: "AE"
      variable: "AESEV"
      result: "FAIL"
      details: "12 records (2.3%) have missing severity"
      affected_records: "{n_affected}"

  datasets_validated:
    - domain: "DM"
      input_rows: {n_subjects}
      output_rows: "{n_validated}"
      excluded_rows: "{n_excluded}"
      issues_found: "{n_issues}"
```

---

## Edge Cases

### Partially Completed Forms
- Some CRF forms may be partially completed: validate what exists, flag missing sections
- Distinguish between "not yet entered" and "intentionally blank"

### Out-of-Range Values
- Values outside clinical ranges are flagged but not removed
- Report includes context: is the value clinically implausible or just unusual?
- All out-of-range findings documented in the quality report with severity

### Character Encoding Issues
- Non-ASCII characters in free-text fields (AETERM, CMTRT)
- Line breaks within fields that break CSV parsing
- Null bytes embedded in text fields

### Multi-Source Merges
- When raw data comes from multiple EDC exports, verify subject overlap
- Check for conflicting data when the same subject appears in multiple files

---

## Integration Points

### Upstream Skills
- `/data-extract` -- Provides raw EDC datasets and extraction manifest
- `/study-setup` -- Study configuration with protocol-defined ranges

### Downstream Skills
- `/data-reconciler` -- Cross-source reconciliation of validated data
- `/quality-report` -- Formatted quality report from validation results
- `/sdtm-dm-mapper` -- Consumes validated raw demographics data

### Related Skills
- `/data-quality` -- Universal quality checker (lighter validation)
- `/crf-validator` -- Validates CRF structure, not data content

---

## Evaluation Criteria

**Mandatory:**
- All datasets pass type/format validation
- Duplicate records identified and documented with affected USUBJIDs
- Quality report generated with pass/fail for each check
- Required fields have zero missing values (or all missing documented)
- Cross-form subject consistency verified

**Recommended:**
- Range checks applied per protocol-defined limits
- Missing value threshold analysis with trend reporting
- Validation report includes actionable recommendations
- Results comparable across multiple data cuts

---

## Critical Constraints

**Never:**
- Produce validated output without running all mandatory checks
- Silently drop records without documentation
- Ignore CDISC controlled terminology for standard variables
- Alter raw data values during validation (flag only)
- Proceed if extraction manifest is missing or incomplete

**Always:**
- Validate all inputs before processing
- Document any deviations from standard validation rules
- Generate traceable, reproducible results with timestamps
- Preserve original values alongside flagged issues
- Log all validation checks with rule IDs for audit trail

---

## Examples

### Basic Validation
```bash
python csp-skills/layer-1-raw-data/data-validator/script.py \
  --input data/raw/ \
  --output data/validated/ \
  --checks all
```

### Targeted Validation
```bash
python csp-skills/layer-1-raw-data/data-validator/script.py \
  --input data/raw/ \
  --output data/validated/ \
  --checks type,missing,duplicate \
  --threshold 0.05 \
  --study-config specs/study-config.yaml
```

### Expected Output
```
reports/data-quality-report.html
data/validated/
  dm.csv
  ae.csv
  lb.csv
  vs.csv
  cm.csv
  mh.csv
  ex.csv
  ds.csv
  sv.csv
ops/raw-validation-log.yaml
```
