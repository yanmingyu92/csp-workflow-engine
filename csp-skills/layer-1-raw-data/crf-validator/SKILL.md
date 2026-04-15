---
name: crf-validator
description: Validate CRF annotations against CDASH and SDTM standards. Triggers on "CRF", "case report form", "annotated CRF", "aCRF", "CRF annotation", "CDASH".
version: "2.0"
user-invocable: true
context: fork
model: sonnet
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
argument-hint: "[options] -- --input <acrf-path> --mapping-spec <spec-path> --output <report-path>"
---

## Runtime Configuration (Step 0)

Resolve configuration in order:
1. `$ARGUMENTS` (highest precedence)
2. `docs/acrf-draft.pdf` -- annotated CRF to validate
3. `specs/sdtm-mapping-spec.xlsx` -- mapping specifications
4. `specs/study-config.yaml` -- study metadata

```yaml
config_resolution:
  study_id: "$ARGUMENTS.study_id || study-config.study_id"
  acrf_path: "$ARGUMENTS.input || 'docs/acrf-draft.pdf'"
  mapping_spec: "$ARGUMENTS.mapping_spec || 'specs/sdtm-mapping-spec.xlsx'"
  output_report: "$ARGUMENTS.output || 'reports/crf-validation-report.html'"
```

## EXECUTE NOW
Parse $ARGUMENTS: --input, --output, --mapping-spec, --dry-run
**START NOW.**

---

## Philosophy

**CRF validation ensures all fields follow CDASH standards and map correctly to SDTM.** Unmapped fields must be justified. This is the quality gate between CRF annotation and data collection. Per CDISC CDASH v2.2, field names, data types, and controlled terminology must align with standards.

---

## Input/Output Specification

### Inputs (matching regulatory-graph.yaml node `crf-validation`)
| Input | Format | Required | Source |
|-------|--------|----------|--------|
| Annotated CRF (draft) | pdf | Yes | docs/acrf-draft.pdf |
| SDTM mapping specification | xlsx/yaml | Yes | specs/sdtm-mapping-spec.xlsx |
| Study configuration | yaml | Yes | specs/study-config.yaml |
| Annotation mapping log | yaml | Yes | ops/crf-annotation-log.yaml |

### Outputs (matching regulatory-graph.yaml node `crf-validation`)
| Output | Format | Path Pattern | Description |
|--------|--------|--------------|-------------|
| CRF validation report | html | reports/crf-validation-report.html | Validation findings |
| Validation log | yaml | ops/crf-validation-log.yaml | Machine-readable results |

---

## Validation Check Categories

### Check Category 1: Annotation Completeness
```python
validation_rules:
  - rule_id: "ANN-001"
    name: "All fields annotated"
    description: "Every CRF field has an SDTM annotation or unmapped justification"
    severity: "ERROR"
    check: "for each field: annotation exists OR justification documented"

  - rule_id: "ANN-002"
    name: "Annotation format valid"
    description: "Annotations follow Domain.Variable format"
    severity: "ERROR"
    check: "annotation matches pattern /^[A-Z]{2}\.[A-Z][A-Z0-9_]+$/"
    valid_examples: ["DM.SEX", "AE.AETERM", "LB.LBTEST"]
    invalid_examples: ["sex", "AE.AE Term", "lb.test"]
```

### Check Category 2: CDASH Compliance
```python
validation_rules:
  - rule_id: "CDASH-001"
    name: "CDASH variable name match"
    description: "CRF field names match CDASH standard names"
    severity: "WARNING"
    check: "cdash_name_in_standard(field_name, domain)"
    cdash_reference: "CDISC CDASH v2.2"

  - rule_id: "CDASH-002"
    name: "CDASH data type compliance"
    description: "Field data types match CDASH specifications"
    severity: "WARNING"
    check: "data_type_matches(field_type, cdash_expected_type)"

  - rule_id: "CDASH-003"
    name: "Required CDASH fields present"
    description: "All CDASH-required fields for the domain are present in the CRF"
    severity: "ERROR"
    check: "required_cdash_fields_present(domain)"
    required_fields_by_domain:
      AE: ["AETERM", "AESTDAT", "AEENDAT", "AESEV", "AESER", "AEREL", "AEACN"]
      DM: ["BRTHDAT", "SEX", "RACE", "ETHNIC"]
      LB: ["LBTEST", "LBORRES", "LBORRESU", "LBDAT"]
```

### Check Category 3: SDTM Mapping Correctness
```python
validation_rules:
  - rule_id: "SDTM-001"
    name: "SDTM target variable exists"
    description: "Annotated SDTM variable exists in CDISC SDTM IG"
    severity: "ERROR"
    check: "variable_in_sdtm_ig(domain, variable)"

  - rule_id: "SDTM-002"
    name: "Mapping matches specification"
    description: "CRF annotation matches the SDTM mapping specification"
    severity: "ERROR"
    check: "annotation_matches_spec(field, mapping_spec)"

  - rule_id: "SDTM-003"
    name: "Controlled terminology alignment"
    description: "CRF value lists match CDISC controlled terminology"
    severity: "WARNING"
    check: "crf_values_subset_of_cdisc_ct(domain, variable)"
```

---

## Output Schema

```yaml
crf_validation_result:
  study_id: "{study_id}"
  validation_timestamp: "{ISO_8601}"
  acrf_validated: "docs/acrf-draft.pdf"

  summary:
    total_fields: "{n_fields}"
    passed: "{n_passed}"
    warnings: "{n_warnings}"
    errors: "{n_errors}"
    unmapped_with_justification: "{n_justified}"
    unmapped_without_justification: "{n_unjustified}"
    overall_status: "PASS | FAIL"

  validation_checks:
    - rule_id: "ANN-001"
      status: "PASS"
      details: "All 156 CRF fields have annotations"
    - rule_id: "CDASH-003"
      status: "FAIL"
      details: "AE form missing required CDASH field: AEACN (Action Taken)"
      affected_pages: [3, 4]

  unmapped_fields:
    - field_name: "Subject Initials"
      page: 1
      justification: "Not collected per GDPR requirements"
      status: "JUSTIFIED"
    - field_name: "Investigator Signature"
      page: 12
      justification: null
      status: "UNJUSTIFIED"
```

---

## Edge Cases

### Study-Specific Non-Standard Fields
- Studies may collect data in non-standard CRF fields
- These must be annotated with SUPPXX targets and justified
- Document the clinical rationale for non-standard collection

### Partial Annotations
- CRF may be partially annotated if still under development
- Validate what exists, flag incomplete forms
- Do not fail on forms marked as "draft" in the annotation log

### Version Differences
- CRF may have multiple versions (amendments)
- Validate that each version is annotated separately
- Document which CRF version corresponds to which protocol amendment

---

## Integration Points

### Upstream Skills
- `/crf-annotator` -- Produces the annotated CRF to validate
- `/spec-builder` -- Mapping specifications used for validation

### Downstream Skills
- `/data-extract` -- Extraction uses validated CRF structure
- `/acrf-finalizer` -- Finalizes aCRF after validation passes

### Related Skills
- `/data-quality` -- Data quality checks
- `/workflow` -- Track validation status

---

## Evaluation Criteria

**Mandatory:**
- Every CRF field validated against CDASH and SDTM standards
- No unmapped fields without documented justification
- Annotation format verified (Domain.Variable pattern)
- Validation report with pass/fail per check

**Recommended:**
- CDASH compliance verified for all field names
- Controlled terminology alignment checked
- Cross-reference with mapping specification verified

---

## Critical Constraints

**Never:**
- Validate without the mapping specification
- Pass a CRF with unmapped fields lacking justification
- Use outdated CDASH or SDTM standards for validation
- Skip validation of controlled terminology fields

**Always:**
- Validate against the latest CDISC CDASH and SDTM IG versions
- Document all findings with severity levels
- Generate machine-readable validation log
- Compare annotations against the mapping specification

---

## Examples

### Full Validation
```bash
python csp-skills/layer-1-raw-data/crf-validator/script.py \
  --input docs/acrf-draft.pdf \
  --mapping-spec specs/sdtm-mapping-spec.xlsx \
  --output reports/crf-validation-report.html
```

### Dry Run
```bash
python csp-skills/layer-1-raw-data/crf-validator/script.py \
  --input docs/acrf-draft.pdf \
  --mapping-spec specs/sdtm-mapping-spec.xlsx \
  --dry-run
```
