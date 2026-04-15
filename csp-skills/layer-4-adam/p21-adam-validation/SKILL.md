---
name: adam-validation
description: Validate ADaM datasets against ADaM IG and specs. Triggers on "ADaM validation", "ADaM QC".
version: "2.0"
user-invocable: true
context: fork
model: sonnet
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
argument-hint: "[options] -- --input-dir, --spec, --report"
---

## Runtime Configuration (Step 0)

### Dynamic Config Resolution
```yaml
config_sources:
  - path: specs/study-config.yaml
    description: Study-level metadata, treatment arms, population definitions
  - path: specs/adam-spec.yaml
    description: ADaM derivation specifications
  - path: specs/analysis-populations.yaml
    description: Population membership criteria
  - path: specs/sap-parsed.yaml
    description: SAP analysis specifications

required_inputs:
  - type: dataset
    name: All ADaM datasets
    format: xpt
    path_pattern: "{input-dir}/*.xpt"
  - type: specification
    name: ADaM derivation specification
    format: xlsx|yaml
    path_pattern: specs/adam-spec.yaml

output:
  - type: report
    name: P21 ADaM validation report
    format: xlsx|html
    path_pattern: "{report}"
  - type: metadata
    name: P21 ADaM issue tracker
    format: yaml
    path_pattern: ops/p21-adam-issues.yaml
```

Read: {input-dir}/*.xpt, specs/adam-spec.yaml, specs/analysis-populations.yaml, specs/study-config.yaml
## EXECUTE NOW
Parse $ARGUMENTS: --input-dir, --report, --spec, --dry-run
**START NOW.**

---

## Philosophy
**ADaM must support traceability and reproducibility.** Every variable must have clear derivation, and datasets must support protocol-specified analyses. This skill runs Pinnacle 21 Community/Enterprise validation on all ADaM datasets and generates a categorized issue tracker.

**Key Principle:** Zero P21 errors is the target. All warnings must be reviewed and either resolved or justified with documentation. This mirrors the p21-sdtm-validation in Layer 3 but applies ADaM-specific rules.

---

## Input/Output Specification
### Inputs (from regulatory-graph.yaml: p21-adam-validation)
| Input | Format | Required | Source |
|-------|--------|----------|--------|
| All ADaM datasets | xpt | Yes | adam-adsl, adam-adae, adam-adlb, adam-adtte, adam-adeff |
| ADaM derivation spec | xlsx/yaml | Yes | spec-creation |

### Outputs (to regulatory-graph.yaml: p21-adam-validation)
| Output | Format | Path Pattern | Consumers |
|--------|--------|--------------|-----------|
| P21 ADaM validation report | xlsx/html | reports/p21-adam-report.xlsx | adrg-writer |
| P21 ADaM issue tracker | yaml | ops/p21-adam-issues.yaml | adrg-writer |

---

## Script Execution
```bash
p21-adam-validation --input-dir {input-dir} --report {report} [--spec {spec}] [--dry-run]
```

### Arguments
| Argument | Required | Description |
|----------|----------|-------------|
| `--input-dir` | Yes | Directory containing ADaM XPT files |
| `--report` | Yes | Output path for P21 validation report |
| `--spec` | No | ADaM specification YAML |
| `--dry-run` | No | Show validation plan without running |

---

## Validation Checks
### ADaM Structure Checks
| Check Category | Description |
|----------------|-------------|
| ADSL Structure | One record per subject, all DM subjects present |
| BDS Structure | PARAMCD unique within subject+timepoint, AVAL/AVALC consistency |
| OCCDS Structure | Proper merge with ADSL, occurrence flags derived |
| Required Variables | STUDYID, USUBJID, and domain-specific required vars present |
| Variable Types | Numeric vs character types per ADaM IG |
| Controlled Terminology | CDISC CT compliance for standard variables |

### ADaM Content Checks
| Check Category | Description |
|----------------|-------------|
| Traceability | All variables have documented SDTM source |
| Consistency | Treatment variables consistent across ADaM datasets |
| Population Flags | SAFFL, ITTFL consistent between ADSL and other ADaM |
| Date Logic | TRTSDT <= TRTEDT, analysis dates in valid ranges |
| Merge Integrity | All ADaM USUBJIDs exist in ADSL |

### ADaM IG Compliance
| Rule | Description |
|------|-------------|
| ADaM IG 2.1 | Variables named per ADaM IG conventions |
| ADSL Supplement | ADSL-specific rules (one record per subject) |
| BDS Supplement | BDS-specific rules (PARAM, PARAMCD, AVAL) |
| OCCDS Supplement | OCCDS-specific rules (occurrence flags) |

---

## Validation Logic
```python
def run_p21_adam_validation(adam_dir, study_config, spec):
    """
    Run Pinnacle 21 ADaM validation on all ADaM datasets.

    1. Discover all .xpt files in adam_dir
    2. Run P21 engine with ADaM IG rules
    3. Classify issues: Error, Warning, Info
    4. Generate categorized issue tracker
    5. Cross-reference with study config for context
    """
    adam_files = glob(f"{adam_dir}/*.xpt")
    issues = []

    for adam_file in adam_files:
        ds = read_xpt(adam_file)
        dataset_name = Path(adam_file).stem.upper()

        # Structure checks
        if dataset_name == 'ADSL':
            issues.extend(validate_adsl_structure(ds, study_config))
        else:
            issues.extend(validate_bds_occds_structure(ds, dataset_name, study_config))

        # Content checks
        issues.extend(validate_adam_content(ds, dataset_name, study_config))

        # Cross-dataset checks
        issues.extend(validate_cross_dataset(ds, dataset_name, adam_dir))

    # Generate report and issue tracker
    report = generate_p21_report(issues)
    tracker = generate_issue_tracker(issues)

    return report, tracker
```

---

## Output Schema

```yaml
p21_adam_report:
  date: "{timestamp}"
  datasets_validated: ["adsl", "adae", "adlb", "adtte", "adeff"]
  spec_version: "ADaM IG v1.3"
  engine: "Pinnacle 21 Community"

  summary:
    total_checks: 0
    errors: 0
    warnings: 0
    info: 0
    target: "0 errors, all warnings reviewed"

  issues:
    - dataset: "ADSL"
      rule_id: "AD0001"
      severity: "Error|Warning|Info"
      message: "Description of the issue"
      affected_records: {n_affected}
      resolution_status: "Open|Resolved|Accepted"
      resolution_note: "Justification if accepted"

p21_adam_issue_tracker:
  format: yaml
  path: ops/p21-adam-issues.yaml
  contents:
    - rule_id: "AD0001"
      severity: "Warning"
      datasets_affected: ["ADSL"]
      description: "Issue description"
      status: "accepted"
      justification: "Reason this warning is acceptable"
      reviewer: " Statistical Programming Lead"
      date_reviewed: "{review_date}"
```

---

## Edge Cases

### P21 Engine Not Available
```python
# If P21 cannot run (license, installation issues):
# - Fall back to internal ADaM IG validation rules
# - Document that P21 was not used
# - Flag as limitation in validation report
```

### Known P21 False Positives
```python
# Some P21 rules generate false positives for valid ADaM structures:
# - Custom PARAMCD values not in CDISC CT (valid if documented)
# - Study-specific flags (e.g., PPROTFL not standard but accepted)
# - Accept with documented justification
```

### Empty ADaM Datasets
```python
# If an ADaM dataset has zero records:
# - Still validate structure (variable names, types)
# - Flag as potential data issue
# - May be valid (e.g., no SAEs in study)
```

---

## Integration Points
### Upstream Skills
- `/adam-adsl-builder` -- ADSL to validate
- `/adam-adae-builder` -- ADAE to validate
- `/adam-adlb-builder` -- ADLB to validate
- `/adam-adtte-builder` -- ADTTE to validate
- `/adam-adeff-builder` -- ADEFF to validate
- `/adam-custom-builder` -- Custom ADaM to validate
- `/adam-traceability-checker` -- Traceability report (prerequisite)

### Downstream Skills
- `/adrg-writer` -- Document P21 issues in ADRG
- `/define-xml-adam` -- ADaM Define.xml (prerequisite)

### Related Skills
- `/adam-validator` -- Internal ADaM compliance checks
- `/p21-validator` -- P21 MCP for engine execution

---

## Evaluation Criteria
**Mandatory:**
- Zero P21 errors (severity = Error)
- All warnings reviewed and justified or resolved
- Issue tracker generated with resolution status
- All ADaM datasets validated

**Recommended:**
- Zero P21 warnings
- Automated comparison with SDTM P21 results
- Issue tracker integrated with ADRG

---

## Critical Constraints
**Never:**
- Ignore P21 errors without resolution
- Suppress warnings without documentation
- Skip ADaM datasets that exist but have issues
- Proceed to TFL generation with unresolved P21 errors

**Always:**
- Run P21 on ALL ADaM datasets in the directory
- Classify all issues by severity
- Generate issue tracker with resolution workflow
- Cross-reference with study_config for context
- Generate traceable, reproducible results

---

## Examples
```bash
p21-adam-validation --input-dir output/adam/ --report reports/p21-adam-report.xlsx
```

### With Spec
```bash
p21-adam-validation --input-dir output/adam/ --report reports/p21-adam-report.xlsx --spec specs/adam-spec.yaml
```

### Expected Output
```
reports/p21-adam-report.xlsx
+-- Summary ({n_errors} errors, {n_warnings} warnings, {n_info} info)
+-- ADSL validation results
+-- ADAE validation results
+-- ADLB validation results
+-- ADTTE validation results
+-- ADEFF validation results
ops/p21-adam-issues.yaml
+-- Categorized issues with resolution status
```
