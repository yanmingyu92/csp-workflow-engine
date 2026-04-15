---
name: spec-reviewer
description: Review and validate mapping specifications. Triggers on "mapping specification", "SDTM spec", "ADaM spec", "TFL spec", "derivation spec", "specification".
version: "1.0"
user-invocable: true
context: fork
model: sonnet
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
argument-hint: "[options] -- --input <spec-path> --output <report-path> --spec <spec-type> --validate"
---

## Runtime Configuration

### Config Resolution
1. Read ops/workflow-state.yaml for current workflow state
2. Read specs/study-config.yaml for study metadata (if exists)
3. If study-config missing, fall back to --study-config <path> argument
4. If neither available, log error and abort

### Required Reads
- ops/workflow-state.yaml -- Current workflow state
- specs/study-config.yaml -- Study configuration
- Specification document(s) to review (via --input)

### Arguments
| Argument | Required | Description |
|----------|----------|-------------|
| `--input` | Yes | Path to specification file to review |
| `--output` | Yes | Output path for review report |
| `--spec` | No | Specification type: sdtm, adam, tfl (auto-detected if omitted) |
| `--study-config` | No | Path to study configuration |
| `--validate` | No | Run validation checks and produce report |

---

## Philosophy

**Spec review catches ambiguities and gaps before programming begins. Coverage and completeness checks are essential.**

---

## Input/Output Specification

### Inputs (from regulatory-graph.yaml node schema: spec-creation)
| Input | Type | Format | Required | Source |
|-------|------|--------|----------|--------|
| SDTM mapping specification | specification | xlsx, yaml | No | specs/sdtm-mapping-spec.xlsx |
| ADaM derivation specification | specification | xlsx, yaml | No | specs/adam-derivation-spec.xlsx |
| TFL shell specifications | specification | xlsx, docx | No | specs/tfl-shells.xlsx |
| Study configuration | specification | yaml | Yes | specs/study-config.yaml |
| Workflow state | metadata | yaml | No | ops/workflow-state.yaml |

### Outputs (to regulatory-graph.yaml node schema: spec-creation)
| Output | Type | Format | Path Pattern |
|--------|------|--------|-------------|
| Review report | report | html, pdf, yaml | reports/spec-review-report.yaml |
| Issue tracker | metadata | yaml | ops/spec-issues.yaml |

---

## Domain-Specific Content

### Key Variables

| Variable | Description |
|----------|-------------|
| SPEC_SECTION | Specification section under review |
| STATUS | Approved / Needs Review / Rejected |
| COMMENTS | Review comments and findings |
| SEVERITY | CRITICAL / HIGH / MEDIUM / LOW |
| CDISC_COMPLIANCE | Pass / Fail / N/A |

### Review Checks

#### SDTM Mapping Spec Review
- All CRF variables mapped to SDTM targets
- Controlled terminology matches CDISC CT latest version
- Variable naming follows SDTM IG conventions
- Required variables present per domain
- Origin types correctly specified (CRF, Derived, Assigned)

#### ADaM Derivation Spec Review
- All SAP endpoints covered by derivations
- Traceability to SDTM source variables documented
- Population flags defined per SAP
- Treatment variable definitions consistent with study config
- Dataset structure (ADSL/BDS/OCCDS) appropriate for analysis

#### TFL Shell Review
- All SAP-listed TFLs have corresponding shells
- Column headers use treatment arm names from study config
- Population references match SAP definitions
- Statistical methods match SAP specifications

---

## Output Schema

```yaml
schema_version: "1.0"
study_id: "{study_id} from study config"
review_date: "{extraction_date}"
spec_file: "{spec_file_path}"

summary:
  total_sections: "{total_sections}"
  approved: "{approved_count}"
  needs_review: "{needs_review_count}"
  rejected: "{rejected_count}"

findings:
  - section: "{spec_section}"
    variable: "{variable_name}"
    status: "{status}"
    severity: "{severity}"
    check: "{check_description}"
    finding: "{finding_detail}"
    recommendation: "{recommendation}"

issues:
  - id: "{issue_id}"
    type: "error|warning|info"
    section: "{spec_section}"
    description: "{issue_description}"
    resolution: "{resolution_status}"
```

---

## Edge Cases

### Incomplete Specifications
- If spec is missing required sections, flag as CRITICAL
- Generate list of expected sections vs. found sections

### Version Mismatches
- If spec references a different study config version, flag discrepancy
- Recommend re-generation with current study config

### Non-Standard Variables
- Document all non-standard variables with justification requirements
- Flag if SUPPXX structure should be used instead

---

## Integration Points

### Upstream Skills
- `/spec-builder` -- Generates specifications for review
- `/study-setup` -- Provides study configuration
- `/sap-parser` -- Provides SAP for cross-reference

### Downstream Skills
- `/sdtm-*-mapper` -- Consumes approved SDTM mapping spec
- `/adam-*-builder` -- Consumes approved ADaM derivation spec
- `/tfl-*-generator` -- Consumes approved TFL shells

### MCPs
- `cdisc-library` -- CDISC controlled terminology validation

---

## Evaluation Criteria

**Mandatory:**
- SDTM mapping spec covers all collected CRF variables
- ADaM spec covers all SAP endpoints
- TFL shells match SAP appendix

**Recommended:**
- Specs reviewed and signed off
- Variable naming follows CDISC conventions
- All findings categorized by severity
- Resolution tracking in place

---

## Critical Constraints

**Never:**
- Hardcode study-specific values (study ID, treatment arms, dates, file paths)
- Proceed if required configuration is missing
- Produce output without validation
- Skip required variables
- Ignore CDISC controlled terminology

**Always:**
- Resolve study metadata dynamically from ops/workflow-state.yaml or --study-config
- Read treatment arm definitions from study config, not hardcoded mappings
- Validate all inputs before processing
- Document any deviations from standards
- Generate traceable, reproducible results

---

## Examples

### Review SDTM Spec
```bash
spec-reviewer --input specs/sdtm-mapping-spec.yaml --output reports/spec-review-report.yaml --spec sdtm
```

### Review ADaM Spec
```bash
spec-reviewer --input specs/adam-derivation-spec.yaml --output reports/spec-review-report.yaml --spec adam
```

### Review TFL Shells
```bash
spec-reviewer --input specs/tfl-shells.yaml --output reports/spec-review-report.yaml --spec tfl
```

### With Explicit Study Config
```bash
spec-reviewer --input specs/sdtm-mapping-spec.yaml --output reports/spec-review-report.yaml --study-config specs/study-config.yaml
```
