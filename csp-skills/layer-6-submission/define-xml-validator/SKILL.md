---
name: define-xml-validator
description: Validate Define.xml against CDISC schema and business rules. Triggers on "Define.xml SDTM", "SDTM Define", "define-xml SDTM", "SDTM metadata", "CRT-DD", "final Define SDTM".
version: "2.0"
user-invocable: true
context: fork
model: sonnet
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
argument-hint: "[options] -- --input <define-xml> --output <report-path> --check [schema|crossref|stylesheet|all]"
---

## Runtime Configuration (Step 0)

Resolve configuration in order:
1. `$ARGUMENTS` (highest precedence)
2. `output/define/define-sdtm.xml` -- SDTM Define.xml
3. `output/define/define-adam.xml` -- ADaM Define.xml
4. `specs/study-config.yaml` -- study metadata

```yaml
config_resolution:
  study_id: "$ARGUMENTS.study_id || study-config.study_id"
  define_path: "$ARGUMENTS.input || 'output/define/'"
  output_report: "$ARGUMENTS.output || 'reports/define-xml-validation-report.html'"
  check_types: "$ARGUMENTS.check || ['schema', 'crossref', 'stylesheet']"
```

## EXECUTE NOW
Parse $ARGUMENTS: --input, --output, --check, --dry-run
**START NOW.**

---

## Philosophy

**Define.xml validation ensures schema compliance, stylesheet rendering, and cross-reference integrity.** Per FDA requirements, the Define.xml must be machine-readable and human-readable (via stylesheet). Every validation issue must be resolved before submission.

---

## Input/Output Specification

### Inputs (matching regulatory-graph.yaml node `define-xml-validation`)
| Input | Format | Required | Source |
|-------|--------|----------|--------|
| Define.xml for SDTM | xml | Yes | output/define/define-sdtm.xml |
| Define.xml for ADaM | xml | Yes | output/define/define-adam.xml |

### Outputs (matching regulatory-graph.yaml node `define-xml-validation`)
| Output | Format | Path Pattern | Description |
|--------|--------|--------------|-------------|
| Define.xml validation report | html/pdf | reports/define-xml-validation-report.html | Validation results |
| Validation log | yaml | ops/define-xml-validation-log.yaml | Machine-readable results |

---

## Validation Check Categories

### Check 1: Schema Validation
```yaml
schema_validation:
  check_id: "DEF-SCHEMA-001"
  description: "Valid XML against CDISC Define-XML v2.1 XSD"
  severity: "ERROR"
  method: "XML schema validation using XSD"
  xsd_source: "CDISC Define-XML v2.1 schema"
  checks:
    - "All required elements present"
    - "Namespace declarations correct"
    - "OID references valid"
    - "DataType values valid"
    - "Mandatory attributes populated"
```

### Check 2: Cross-Reference Integrity
```yaml
cross_reference_validation:
  check_id: "DEF-XREF-001"
  description: "All cross-references resolve correctly"
  severity: "ERROR"
  checks:
    - "ItemRef ItemOID points to valid ItemDef"
    - "CodeListRef CodeListOID points to valid CodeList"
    - "MethodRef points to valid ComputationalMethod"
    - "ValueListRef points to valid ValueListDef"
    - "No orphan elements without references"
    - "All datasets have at least one ItemRef"
```

### Check 3: Stylesheet Rendering
```yaml
stylesheet_validation:
  check_id: "DEF-STYLE-001"
  description: "Define.xml renders correctly with CDISC stylesheet"
  severity: "WARNING"
  method: "Apply CDISC XSLT, check for rendering errors"
  checks:
    - "Stylesheet processes without XSLT errors"
    - "All hyperlinks functional"
    - "Dataset list renders completely"
    - "Variable details accessible from dataset view"
    - "Controlled terminology expandable"
```

### Check 4: Business Rules
```yaml
business_rule_validation:
  check_id: "DEF-BIZ-001"
  description: "Define.xml follows FDA business rules"
  severity: "WARNING"
  checks:
    - "Standard variable names match SDTM IG"
    - "All required variables documented (STUDYID, USUBJID, DOMAIN)"
    - "Controlled terminology version documented"
    - "Origin specified for each variable (CRF, Derived, Assigned)"
    - "Role specified for each variable (Identifier, Topic, Qualifier)"
```

---

## Output Schema

```yaml
define_validation_result:
  study_id: "{study_id}"
  validation_timestamp: "{ISO_8601}"

  files_validated:
    - path: "output/define/define-sdtm.xml"
      schema_valid: true
      stylesheet_renders: true
      cross_references_valid: true
      business_rules: "PASS"
    - path: "output/define/define-adam.xml"
      schema_valid: true
      stylesheet_renders: true
      cross_references_valid: true
      business_rules: "PASS"

  issues:
    - check_id: "DEF-SCHEMA-001"
      file: "define-sdtm.xml"
      severity: "ERROR"
      description: "Missing required attribute: def:StandardVersion"
      location: "line 42"
      resolution: "Add def:StandardVersion='3.4' to MetaDataVersion"

  summary:
    total_checks: "{n_checks}"
    errors: "{n_errors}"
    warnings: "{n_warnings}"
    overall_status: "PASS | FAIL"
```

---

## Edge Cases

### Multi-Version Define.xml
- SDTM and ADaM may use different standard versions
- Validate each against its respective schema
- Document version differences in the report

### Missing Stylesheet
- If CDISC stylesheet is not available, note in report
- Stylesheet check is recommended, not mandatory

### Large Controlled Terminology Lists
- MedDRA CT is very large; validate representative samples
- Ensure CT version is documented for reproducibility

---

## Integration Points

### Upstream Skills
- `/define-xml-builder` -- Generates Define.xml to validate
- `/p21-validator` -- P21 validation results for cross-check

### Downstream Skills
- `/esub-assembler` -- Only assembles after validation passes

### Related Skills
- `/workflow` -- Track validation status

---

## Evaluation Criteria

**Mandatory:**
- Schema-valid against Define-XML v2.1 schema
- All cross-references resolve correctly
- Stylesheet renders without errors
- Zero P21 Define.xml validation errors

**Recommended:**
- All hyperlinks functional
- Business rules checked
- CT version documented

---

## Critical Constraints

**Never:**
- Pass a schema-invalid Define.xml
- Skip cross-reference validation
- Ignore stylesheet rendering errors
- Proceed to submission with unresolved Define.xml issues

**Always:**
- Validate against the correct CDISC Define-XML schema version
- Check all cross-references for broken links
- Test stylesheet rendering
- Document all findings with severity levels

---

## Examples

### Validate Both Define.xml Files
```bash
python csp-skills/layer-6-submission/define-xml-validator/script.py \
  --input output/define/ \
  --output reports/define-xml-validation-report.html \
  --check all
```

### Schema-Only Validation
```bash
python csp-skills/layer-6-submission/define-xml-validator/script.py \
  --input output/define/define-sdtm.xml \
  --output reports/define-schema-report.html \
  --check schema
```
