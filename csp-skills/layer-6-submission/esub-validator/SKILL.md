---
name: esub-validator
description: Validate eCTD submission package for FDA compliance. Triggers on "eCTD", "submission package", "eSub", "Module 5", "electronic submission", "submission assembly".
version: "2.0"
user-invocable: true
context: fork
model: sonnet
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
argument-hint: "[options] -- --input <esub-dir> --output <report-path> --checks [all|structure|naming|completeness]"
---

## Runtime Configuration (Step 0)

Resolve configuration in order:
1. `$ARGUMENTS` (highest precedence)
2. `output/esub/` -- assembled eCTD package
3. `specs/study-config.yaml` -- study metadata
4. `ops/submission-checklist.yaml` -- expected components

```yaml
config_resolution:
  study_id: "$ARGUMENTS.study_id || study-config.study_id"
  input_dir: "$ARGUMENTS.input || 'output/esub/'"
  output_report: "$ARGUMENTS.output || 'reports/esub-validation-report.html'"
  check_types: "$ARGUMENTS.checks || ['structure', 'naming', 'completeness', 'integrity']"
```

## EXECUTE NOW
Parse $ARGUMENTS: --input, --output, --checks, --dry-run
**START NOW.**

---

## Philosophy

**Final validation catches assembly errors before submission.** FDA eCTD validation tools must return clean results. A failed submission wastes weeks of time and creates regulatory risk. Every file, every reference, and every structure must be verified.

---

## Input/Output Specification

### Inputs (matching regulatory-graph.yaml node `esub-final-validation`)
| Input | Format | Required | Source |
|-------|--------|----------|--------|
| eCTD submission package | directory | Yes | output/esub/ |
| Study configuration | yaml | Yes | specs/study-config.yaml |
| Submission checklist | yaml | Yes | ops/submission-checklist.yaml |

### Outputs (matching regulatory-graph.yaml node `esub-final-validation`)
| Output | Format | Path Pattern | Description |
|--------|--------|--------------|-------------|
| Submission validation report | html/pdf | reports/esub-validation-report.html | Comprehensive validation |
| Validation log | yaml | ops/esub-validation-log.yaml | Machine-readable results |

---

## FDA Validation Check Categories

### Category 1: Directory Structure
```yaml
structure_checks:
  - check_id: "ESUB-STRUCT-001"
    description: "eCTD directory follows ICH M8 specification"
    severity: "ERROR"
    expected_structure:
      - "m5/{study_id}/5-3-clinical-study-reports/"
      - "m5/{study_id}/5-3-clinical-study-reports/5-3-1-study-reports/"
      - "m5/{study_id}/5-3-clinical-study-reports/5-3-1-study-reports/{study_id}-csr/"

  - check_id: "ESUB-STRUCT-002"
    description: "No files in root of submission package"
    severity: "ERROR"

  - check_id: "ESUB-STRUCT-003"
    description: "No extra files not referenced in index"
    severity: "WARNING"
```

### Category 2: File Naming
```yaml
naming_checks:
  - check_id: "ESUB-NAME-001"
    description: "Dataset files use lowercase domain.xpt naming"
    severity: "ERROR"
    pattern: "^[a-z]{2}\\.xpt$"

  - check_id: "ESUB-NAME-002"
    description: "Define.xml named correctly"
    severity: "ERROR"
    expected: ["define.xml", "define_adam.xml"]

  - check_id: "ESUB-NAME-003"
    description: "No spaces or special characters in filenames"
    severity: "ERROR"
```

### Category 3: Completeness
```yaml
completeness_checks:
  - check_id: "ESUB-COMP-001"
    description: "All required SDTM domains present"
    severity: "ERROR"
    required_domains: ["dm", "ae", "lb", "vs", "cm", "mh", "ex", "ds", "sv", "ts", "ta", "tv"]

  - check_id: "ESUB-COMP-002"
    description: "All required ADaM datasets present"
    severity: "ERROR"
    required_datasets: ["adsl", "adae"]

  - check_id: "ESUB-COMP-003"
    description: "Define.xml files present"
    severity: "ERROR"

  - check_id: "ESUB-COMP-004"
    description: "Annotated CRF present"
    severity: "ERROR"

  - check_id: "ESUB-COMP-005"
    description: "Reviewer's guides present"
    severity: "ERROR"
    required: ["sdrg.pdf", "adrg.pdf"]

  - check_id: "ESUB-COMP-006"
    description: "TFL outputs present"
    severity: "ERROR"
```

### Category 4: File Integrity
```yaml
integrity_checks:
  - check_id: "ESUB-INT-001"
    description: "XPT files are valid SAS transport format"
    severity: "ERROR"

  - check_id: "ESUB-INT-002"
    description: "XML files are well-formed"
    severity: "ERROR"

  - check_id: "ESUB-INT-003"
    description: "PDF files are not corrupted"
    severity: "ERROR"

  - check_id: "ESUB-INT-004"
    description: "No zero-byte files"
    severity: "ERROR"

  - check_id: "ESUB-INT-005"
    description: "Package size within FDA limits"
    severity: "WARNING"
    limit: "1 GB per submission unit"
```

---

## Output Schema

```yaml
esub_validation_result:
  study_id: "{study_id}"
  validation_timestamp: "{ISO_8601}"
  package_path: "output/esub/"

  summary:
    total_checks: "{n_checks}"
    passed: "{n_passed}"
    errors: "{n_errors}"
    warnings: "{n_warnings}"
    overall_status: "PASS | FAIL | CONDITIONAL"
    ready_for_submission: true | false

  check_results:
    - check_id: "ESUB-COMP-001"
      category: "completeness"
      status: "PASS"
      details: "All 12 required SDTM domains present"
    - check_id: "ESUB-COMP-003"
      category: "completeness"
      status: "FAIL"
      details: "define_adam.xml not found in expected location"

  missing_components: []
  extra_files: []
```

---

## Edge Cases

### Partial Submissions
- Not all studies have all domains; document which are optional
- Check against the study-specific submission checklist

### File Size Limits
- FDA recommends <1GB per submission unit
- Large datasets may need to be split
- Document total package size in validation report

### Multiple Define.xml Files
- SDTM and ADaM each have their own Define.xml
- Verify both are present and correctly named
- Validate each against its respective schema

---

## Integration Points

### Upstream Skills
- `/esub-assembler` -- Assembled package to validate
- `/define-xml-validator` -- Define.xml already validated

### Downstream Skills
- `/submission-checklist` -- Final readiness check
- `/workflow` -- Gate for submission readiness

### Related Skills
- `/data-quality` -- Pre-submission quality check

---

## Evaluation Criteria

**Mandatory:**
- All required components present
- eCTD directory structure correct
- File naming conventions followed
- Zero validation errors

**Recommended:**
- Package size within FDA limits
- Test submission to FDA ESG gateway (if available)
- All files have MD5 checksums

---

## Critical Constraints

**Never:**
- Submit a package with validation errors
- Ignore warnings without documented justification
- Skip file integrity checks
- Proceed if critical components are missing

**Always:**
- Validate the complete package before declaring submission-ready
- Document all findings with severity levels
- Cross-reference against the submission checklist
- Verify file integrity (no corrupted files)

---

## Examples

### Full Validation
```bash
python csp-skills/layer-6-submission/esub-validator/script.py \
  --input output/esub/ \
  --output reports/esub-validation-report.html \
  --checks all
```

### Structure Check Only
```bash
python csp-skills/layer-6-submission/esub-validator/script.py \
  --input output/esub/ \
  --output reports/esub-structure-report.html \
  --checks structure
```
