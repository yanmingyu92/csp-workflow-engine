---
name: tfl-shell-reviewer
description: Review TFL shells from SAP and validate layout specifications. Triggers on "TFL shell", "mock-up", "table shell", "listing shell", "figure shell", "TFL template".
version: "2.0"
user-invocable: true
context: fork
model: sonnet
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
argument-hint: "[options] -- --input <shell-dir> --output <review-report> --spec <sap-spec>"
---

## Runtime Configuration (Step 0)

Resolve configuration in order:
1. `$ARGUMENTS` (highest precedence)
2. `specs/sap-parsed.yaml` -- parsed SAP with TFL requirements
3. `specs/table-specs.yaml` -- existing table specifications
4. `output/tfl/shells/` -- shell files to review

```yaml
config_resolution:
  study_id: "$ARGUMENTS.study_id || study-config.study_id"
  shell_dir: "$ARGUMENTS.input || 'output/tfl/shells/'"
  output_report: "$ARGUMENTS.output || 'reports/tfl-shell-review.html'"
  sap_spec: "$ARGUMENTS.spec || 'specs/sap-parsed.yaml'"
```

## EXECUTE NOW
Parse $ARGUMENTS: --input, --output, --spec, --dry-run
**START NOW.**

---

## Philosophy

**TFL shells define the exact layout.** Headers, footnotes, and page layout must match SAP specifications precisely. Shells are the contract between the statistical programmer and the SAP author. Any deviation from the shell must be approved by the study statistician.

---

## Input/Output Specification

### Inputs (matching regulatory-graph.yaml node `tfl-shell-review`)
| Input | Format | Required | Source |
|-------|--------|----------|--------|
| TFL shell files | docx/xlsx/rtf | Yes | output/tfl/shells/ |
| Parsed SAP specifications | yaml | Yes | specs/sap-parsed.yaml |
| Study configuration | yaml | Yes | specs/study-config.yaml |

### Outputs (matching regulatory-graph.yaml node `tfl-shell-review`)
| Output | Format | Path Pattern | Description |
|--------|--------|--------------|-------------|
| Shell review report | html | reports/tfl-shell-review.html | Completeness and accuracy review |
| Approved shell list | yaml | ops/approved-shells.yaml | Shells ready for programming |

---

## Shell Review Checklist

### Completeness Check
```yaml
completeness_checks:
  - check_id: "SHELL-001"
    description: "Every SAP-specified TFL has a corresponding shell"
    severity: "ERROR"
    source: "Cross-reference sap-parsed.yaml tfl_list vs shells/"

  - check_id: "SHELL-002"
    description: "Each shell has title, table ID, population"
    severity: "ERROR"

  - check_id: "SHELL-003"
    description: "Column headers match treatment arms in study config"
    severity: "ERROR"
    validation: "shell.columns ⊆ study-config.treatment_arms + ['Total']"

  - check_id: "SHELL-004"
    description: "Footnotes are present and complete"
    severity: "WARNING"
    required_footnotes:
      - "Protocol ({study_id})"
      - "Population definition"
      - "Source dataset"
      - "N definition"
```

### Layout Validation
```yaml
layout_checks:
  - check_id: "LAYOUT-001"
    description: "Row order matches SAP specification"
    severity: "WARNING"

  - check_id: "LAYOUT-002"
    description: "Statistics format specified (n, Mean, SD, etc.)"
    severity: "WARNING"

  - check_id: "LAYOUT-003"
    description: "Decimal precision defined for all numeric columns"
    severity: "WARNING"

  - check_id: "LAYOUT-004"
    description: "Pagination strategy documented"
    severity: "RECOMMENDED"
```

---

## Output Schema

```yaml
shell_review_result:
  study_id: "{study_id}"
  review_timestamp: "{ISO_8601}"

  summary:
    total_shells_required: "{n_required}"
    shells_found: "{n_found}"
    shells_missing: "{n_missing}"
    shells_approved: "{n_approved}"
    shells_needing_revision: "{n_revision}"

  required_tfls:
    - tfl_id: "Table 14.1.3"
      title: "Demographics"
      shell_found: true
      shell_path: "output/tfl/shells/table-14.1.3-shell.docx"
      issues:
        - "Missing footnote for N definition"
      status: "NEEDS_REVISION"
    - tfl_id: "Figure 14.4.1"
      title: "KM Plot - Overall Survival"
      shell_found: false
      shell_path: null
      issues:
        - "No shell file found"
      status: "MISSING"
```

---

## Edge Cases

### Shells in Multiple Formats
- Some shells may be .docx, others .xlsx, others .rtf
- Review each format appropriately
- Standardize output format recommendation

### Ambiguous SAP Requirements
- SAP may specify analysis intent without exact layout
- Flag ambiguous specifications for statistician clarification
- Document assumptions made

---

## Integration Points

### Upstream Skills
- `/sap-parser` -- Provides parsed SAP with TFL requirements
- `/study-setup` -- Treatment arm definitions

### Downstream Skills
- `/tfl-template-builder` -- Builds templates from approved shells
- `/tfl-table-generator` -- Programs tables from approved shells
- `/tfl-figure-generator` -- Programs figures from approved shells

### Related Skills
- `/workflow` -- Track shell review status

---

## Evaluation Criteria

**Mandatory:**
- All SAP-specified TFLs have shells
- Headers/footnotes match SAP specifications
- Shell review report generated

**Recommended:**
- Pagination strategy defined
- Decimal precision specified
- Sort order documented

---

## Critical Constraints

**Never:**
- Approve a shell without cross-referencing the SAP
- Skip validation of treatment arm columns against study config
- Proceed to programming without approved shells

**Always:**
- Cross-reference every shell against the SAP
- Document any deviations from SAP layout
- Flag missing or incomplete shells
- Generate review report for traceability

---

## Examples

### Review All Shells
```bash
python csp-skills/layer-5-tfl/tfl-shell-reviewer/script.py \
  --input output/tfl/shells/ \
  --spec specs/sap-parsed.yaml \
  --output reports/tfl-shell-review.html
```
