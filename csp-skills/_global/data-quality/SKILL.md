---
name: data-quality
description: Universal data quality checking. Global skill available at every node. Triggers on "data quality", "check data", "validate data", "completeness", "consistency".
version: "2.0"
user-invocable: true
context: fork
model: sonnet
allowed-tools: Read, Write, Grep, Glob, Bash
argument-hint: "[options] -- --input <dataset_path> --checks [all|completeness|consistency|conformance]"
---

## Runtime Configuration (Step 0)

Resolve configuration in order:
1. `$ARGUMENTS` (highest precedence)
2. `specs/study-config.yaml` -- study metadata and expected data structure
3. Current graph layer context (determines check types)

```yaml
config_resolution:
  study_id: "$ARGUMENTS.study_id || study-config.study_id"
  input_path: "$ARGUMENTS.input"
  check_types: "$ARGUMENTS.checks || ['completeness', 'consistency', 'conformance']"
  threshold: "$ARGUMENTS.threshold || 0.05"
  output_path: "$ARGUMENTS.output || 'ops/data-quality-check.yaml'"
```

## EXECUTE NOW
Parse $ARGUMENTS: --input, --checks, --output, --threshold
**START NOW.**

---

## Philosophy

**Data quality is everyone's responsibility, at every stage.** This universal checker runs completeness, consistency, and conformance checks on any dataset at any pipeline stage. It adapts its checks based on the current graph layer, ensuring that the right quality standards are applied at the right time.

---

## Input/Output Specification

### Inputs
| Input | Format | Required | Source |
|-------|--------|----------|--------|
| Any dataset | csv/xpt/sas7bdat | Yes | Any pipeline stage |
| Study configuration | yaml | Yes | specs/study-config.yaml |

### Outputs
| Output | Format | Path Pattern | Description |
|--------|--------|--------------|-------------|
| Quality check results | yaml | ops/data-quality-check.yaml | Pass/fail per check |
| Quality summary | text | stdout | Brief summary for workflow integration |

---

## Check Categories

| Category | Description | Examples |
|----------|-------------|---------|
| Completeness | Missing values, required fields | NULL rates, mandatory field coverage |
| Consistency | Cross-variable logic | Date ordering, value ranges, duplicates |
| Conformance | Standards compliance | CDISC CT, ISO 8601, naming conventions |

---

## Layer-Adaptive Checks

### Layer 0-1 (Protocol/Raw)
```yaml
layer_0_1_checks:
  completeness:
    - "All required CRF fields populated (non-null)"
    - "Subject enrollment count matches expected range"
    - "Visit dates not missing for completed visits"
  consistency:
    - "No duplicate USUBJID within domain"
    - "Date fields in valid calendar range"
    - "Numeric fields contain only numbers"
  conformance:
    - "Variable names follow CDASH conventions"
    - "Date fields in expected format"
    - "Categorical fields use expected value sets"
```

### Layer 2 (SDTM)
```yaml
layer_2_checks:
  completeness:
    - "All required SDTM variables present per IG"
    - "STUDYID, USUBJID, DOMAIN populated for all records"
  consistency:
    - "All subjects in non-DM domains exist in DM"
    - "Date consistency (AESTDTC <= AEENDTC)"
    - "Treatment arm consistent between DM and EX"
  conformance:
    - "CDISC controlled terminology used for standard variables"
    - "Variable names match SDTM IG"
    - "ISO 8601 date format for *DTC variables"
```

### Layer 3 (SDTM QC)
```yaml
layer_3_checks:
  completeness:
    - "P21 validation results documented"
    - "Cross-domain checks completed"
  consistency:
    - "RELREC relationships valid"
    - "SUPPXX linked to parent records"
  conformance:
    - "Define.xml draft covers all datasets"
    - "aCRF matches produced datasets"
```

### Layer 4 (ADaM)
```yaml
layer_4_checks:
  completeness:
    - "Population flags derived for all subjects (SAFFL, ITTFL)"
    - "One record per subject in ADSL"
  consistency:
    - "Traceability: every ADaM variable traces to SDTM"
    - "TRTSDT <= TRTEDT"
    - "AVAL present when AVALC present"
  conformance:
    - "ADaM IG compliance for dataset structure"
    - "BDS structure correct for BDS datasets"
    - "OCCDS structure correct for OCCDS datasets"
```

### Layer 5 (TFL)
```yaml
layer_5_checks:
  completeness:
    - "All SAP-mandated TFLs produced"
    - "All required footnotes present"
  consistency:
    - "N values in column headers match population counts"
    - "Statistical precision consistent"
  conformance:
    - "Number formatting per specifications"
    - "RTF formatting matches template"
```

### Layer 6 (Submission)
```yaml
layer_6_checks:
  completeness:
    - "All required submission components present"
    - "Define.xml covers all datasets"
  consistency:
    - "File naming follows eCTD conventions"
    - "Directory structure matches ICH M8"
  conformance:
    - "Define.xml schema-valid"
    - "XPT files valid SAS transport format"
```

---

## Output Schema

```yaml
quality_check_result:
  study_id: "{study_id}"
  check_timestamp: "{ISO_8601}"
  input_path: "{dataset_path}"
  detected_layer: "{layer_number}"

  summary:
    checks_run: "{n_checks}"
    passed: "{n_passed}"
    failed: "{n_failed}"
    warnings: "{n_warnings}"
    overall: "PASS | FAIL"

  results:
    - check_id: "COMPLETENESS-001"
      category: "completeness"
      description: "Required fields populated"
      result: "PASS"
      details: "All 8 required fields populated in {n_records} records"
    - check_id: "CONSISTENCY-001"
      category: "consistency"
      description: "No duplicate USUBJID"
      result: "FAIL"
      details: "3 duplicate USUBJIDs found"
      affected_records: ["{study_id}-{SITEID}-{SUBJID}", ...]
```

---

## Edge Cases

### Unknown Layer
- If layer cannot be determined, run all check categories
- Warn that layer-specific checks may not be appropriate

### Empty Dataset
- Report as FAIL with "empty dataset" message
- Do not crash on empty input

### Non-Standard File Formats
- Attempt to read; report format error if unsupported
- Support: CSV, XPT, SAS7BDAT, Parquet, JSON

---

## Integration Points

### This is a global skill -- available at every workflow node
- Can be invoked before or after any pipeline step
- Results feed into `/quality-report` for detailed reporting
- Results inform `/workflow` gate decisions

---

## Evaluation Criteria

**Mandatory:** Report all critical issues (>5% missing in key variables)
**Recommended:** Trend analysis, comparison with previous runs

---

## Critical Constraints

**Never:**
- Skip dependency checks
- Allow parallel execution of nodes in the same layer without explicit config
- Modify state without audit trail

**Always:**
- Validate DAG before any state transition
- Persist state to ops/workflow-state.yaml after every change
- Report frontier nodes after any action
