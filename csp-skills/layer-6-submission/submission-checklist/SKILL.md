---
name: submission-checklist
description: Generate and verify submission readiness checklist. Triggers on "final validation", "submission validation", "FDA validation", "ESG gateway", "submission readiness", "pre-submission check".
version: "2.0"
user-invocable: true
context: fork
model: sonnet
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
argument-hint: "[options] -- --input <esub-dir> --output <checklist-path> --action [generate|verify|status]"
---

## Runtime Configuration (Step 0)

Resolve configuration in order:
1. `$ARGUMENTS` (highest precedence)
2. `reports/submission-readiness-report.html` -- prior status
3. `ops/submission-checklist.yaml` -- existing checklist
4. `reports/esub-validation-report.html` -- eSub validation results
5. `specs/study-config.yaml` -- study metadata

```yaml
config_resolution:
  study_id: "$ARGUMENTS.study_id || study-config.study_id"
  input_dir: "$ARGUMENTS.input || 'output/esub/'"
  output_path: "$ARGUMENTS.output || 'ops/submission-checklist.yaml'"
  action: "$ARGUMENTS.action || 'verify'"
```

## EXECUTE NOW
Parse $ARGUMENTS: --input, --output, --action, --dry-run
**START NOW.**

---

## Philosophy

**The checklist ensures nothing is missed.** Every required component must be present and validated before submission. The submission readiness checklist is the final gate: it aggregates results from all upstream validation steps into a single pass/fail determination.

---

## Input/Output Specification

### Inputs (matching regulatory-graph.yaml node `esub-final-validation`)
| Input | Format | Required | Source |
|-------|--------|----------|--------|
| eCTD submission package | directory | Yes | output/esub/ |
| eSub validation report | html | Yes | reports/esub-validation-report.html |
| Define.xml validation report | html | Yes | reports/define-xml-validation-report.html |
| TFL QC report | html | Yes | reports/tfl-qc-report.html |
| P21 SDTM validation report | xlsx | Yes | reports/p21-sdtm-report.xlsx |
| P21 ADaM validation report | xlsx | Yes | reports/p21-adam-report.xlsx |
| Study configuration | yaml | Yes | specs/study-config.yaml |

### Outputs (matching regulatory-graph.yaml node `esub-final-validation`)
| Output | Format | Path Pattern | Description |
|--------|--------|--------------|-------------|
| Submission readiness report | html/pdf | reports/submission-readiness-report.html | Final readiness assessment |
| Submission checklist | yaml | ops/submission-checklist.yaml | Machine-readable checklist |

---

## Checklist Categories

### 1. Data Completeness
```yaml
checklist_data:
  - item_id: "DATA-001"
    category: "Data Completeness"
    description: "All SDTM domains present and validated"
    check: "Verify all required domains in output/esub/"
    validation_source: "reports/p21-sdtm-report.xlsx"
    status: "COMPLETE | INCOMPLETE | FAILED"
    owner: "{data_manager}"

  - item_id: "DATA-002"
    category: "Data Completeness"
    description: "All ADaM datasets present and validated"
    check: "Verify all required ADaM datasets"
    validation_source: "reports/p21-adam-report.xlsx"
    status: "COMPLETE | INCOMPLETE | FAILED"

  - item_id: "DATA-003"
    category: "Data Completeness"
    description: "P21 SDTM validation: zero errors"
    check: "P21 SDTM report has 0 errors"
    validation_source: "reports/p21-sdtm-report.xlsx"
    status: "PASS | FAIL"
```

### 2. Metadata
```yaml
checklist_metadata:
  - item_id: "META-001"
    category: "Metadata"
    description: "Define.xml (SDTM) schema-valid"
    validation_source: "reports/define-xml-validation-report.html"
    status: "PASS | FAIL"

  - item_id: "META-002"
    category: "Metadata"
    description: "Define.xml (ADaM) schema-valid"
    validation_source: "reports/define-xml-validation-report.html"
    status: "PASS | FAIL"

  - item_id: "META-003"
    category: "Metadata"
    description: "Controlled terminology version documented"
    status: "PASS | FAIL"
```

### 3. Documentation
```yaml
checklist_documentation:
  - item_id: "DOC-001"
    category: "Documentation"
    description: "SDTM Reviewer's Guide (SDRG) present"
    check: "docs/sdrg.pdf exists"
    status: "COMPLETE | MISSING"

  - item_id: "DOC-002"
    category: "Documentation"
    description: "ADaM Reviewer's Guide (ADRG) present"
    check: "docs/adrg.pdf exists"
    status: "COMPLETE | MISSING"

  - item_id: "DOC-003"
    category: "Documentation"
    description: "Annotated CRF (final) present"
    check: "docs/acrf-final.pdf exists"
    status: "COMPLETE | MISSING"
```

### 4. TFL Quality
```yaml
checklist_tfl:
  - item_id: "TFL-001"
    category: "TFL Quality"
    description: "All SAP-mandated TFLs produced"
    validation_source: "reports/tfl-qc-report.html"
    status: "PASS | FAIL"

  - item_id: "TFL-002"
    category: "TFL Quality"
    description: "All TFL QC discrepancies resolved"
    validation_source: "reports/tfl-qc-report.html"
    status: "PASS | FAIL"

  - item_id: "TFL-003"
    category: "TFL Quality"
    description: "Key tables double-programmed"
    validation_source: "reports/tfl-double-programming-report.html"
    status: "PASS | FAIL"
```

### 5. Package Integrity
```yaml
checklist_package:
  - item_id: "PKG-001"
    category: "Package Integrity"
    description: "eCTD directory structure correct"
    validation_source: "reports/esub-validation-report.html"
    status: "PASS | FAIL"

  - item_id: "PKG-002"
    category: "Package Integrity"
    description: "File naming conventions followed"
    status: "PASS | FAIL"

  - item_id: "PKG-003"
    category: "Package Integrity"
    description: "Package size within FDA limits (<1GB)"
    status: "PASS | FAIL"
```

---

## Output Schema

```yaml
submission_readiness:
  study_id: "{study_id}"
  assessment_date: "{ISO_8601}"
  overall_status: "READY | NOT_READY | CONDITIONAL"

  readiness_percentage: "{pct_complete}%"

  categories:
    - category: "Data Completeness"
      items: "{n_items}"
      complete: "{n_complete}"
      status: "PASS | FAIL"
    - category: "Metadata"
      status: "PASS | FAIL"
    - category: "Documentation"
      status: "PASS | FAIL"
    - category: "TFL Quality"
      status: "PASS | FAIL"
    - category: "Package Integrity"
      status: "PASS | FAIL"

  blocking_issues:
    - item_id: "DATA-003"
      description: "P21 SDTM validation has 3 unresolved errors"
      action_required: "Resolve P21 errors before submission"

  recommendations:
    - "Archive all validation reports for submission record"
    - "Test submission to FDA ESG gateway if available"
    - "Schedule pre-submission meeting with FDA"
```

---

## Edge Cases

### Conditional Readiness
- Package may be "ready" with documented waivers for non-critical items
- Document all waivers and justifications
- Require sign-off for any conditional items

### Missing Validation Reports
- If a validation report is missing, that category cannot be verified
- Status = "UNVERIFIED" (treated as blocking)

---

## Integration Points

### Upstream Skills
- `/esub-validator` -- eSub validation results
- `/define-xml-validator` -- Define.xml validation results
- `/tfl-qc-validator` -- TFL QC results
- `/p21-validator` -- P21 validation results

### Downstream Skills
- `/workflow` -- Final gate for submission

### Related Skills
- `/data-quality` -- Final quality assessment

---

## Evaluation Criteria

**Mandatory:**
- All FDA validation checks pass
- Readiness checklist 100% complete
- All blocking issues resolved

**Recommended:**
- Test submission to FDA ESG gateway
- All waivers documented and signed off
- Audit trail complete

---

## Critical Constraints

**Never:**
- Declare "ready" with unresolved blocking issues
- Skip validation report checks
- Submit without 100% checklist completion

**Always:**
- Aggregate results from all upstream validation steps
- Classify items as blocking vs. non-blocking
- Document all waivers and justifications
- Generate both human-readable and machine-readable reports

---

## Examples

### Generate Checklist
```bash
python csp-skills/layer-6-submission/submission-checklist/script.py \
  --input output/esub/ \
  --output ops/submission-checklist.yaml \
  --action generate
```

### Verify Readiness
```bash
python csp-skills/layer-6-submission/submission-checklist/script.py \
  --input output/esub/ \
  --output reports/submission-readiness-report.html \
  --action verify
```

### Status Check
```bash
python csp-skills/layer-6-submission/submission-checklist/script.py \
  --input output/esub/ \
  --output ops/submission-checklist.yaml \
  --action status
```
