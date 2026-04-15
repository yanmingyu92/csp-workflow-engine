---
name: tfl-double-programmer
description: Independent double programming for key outputs. Triggers on "double programming", "independent programming", "production vs QC", "dual programming", "verification programming", "independent verification".
version: "2.0"
user-invocable: true
context: fork
model: sonnet
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
argument-hint: "[options] -- --input <adam-dir> --spec <table-spec> --output <qc-dir>"
---

## Runtime Configuration (Step 0)

Resolve configuration in order:
1. `$ARGUMENTS` (highest precedence)
2. `specs/table-specs.yaml` -- table specifications
3. `specs/sap-parsed.yaml` -- SAP analysis methods
4. `output/adam/*.xpt` -- source ADaM datasets
5. `output/tfl/tables/` -- production outputs to compare against

```yaml
config_resolution:
  study_id: "$ARGUMENTS.study_id || study-config.study_id"
  input_dir: "$ARGUMENTS.input || 'output/adam/'"
  table_spec: "$ARGUMENTS.spec || 'specs/table-specs.yaml'"
  output_dir: "$ARGUMENTS.output || 'output/tfl/qc/'"
  tables_to_double_program: "$ARGUMENTS.tables || 'key_tables'"
```

## EXECUTE NOW
Parse $ARGUMENTS: --input, --spec, --output, --tables, --dry-run
**START NOW.**

---

## Philosophy

**Double programming provides the highest assurance of accuracy.** Independent code, same specifications, same data. The QC programmer must not see the production code before writing their own. Discrepancies require root cause analysis to determine which is correct, not just which matches the other.

---

## Input/Output Specification

### Inputs (matching regulatory-graph.yaml node `tfl-double-programming`)
| Input | Format | Required | Source |
|-------|--------|----------|--------|
| ADaM datasets | xpt | Yes | output/adam/ |
| Table specifications | yaml | Yes | specs/table-specs.yaml |
| SAP parsed specifications | yaml | Yes | specs/sap-parsed.yaml |
| Study configuration | yaml | Yes | specs/study-config.yaml |

### Outputs (matching regulatory-graph.yaml node `tfl-double-programming`)
| Output | Format | Path Pattern | Description |
|--------|--------|--------------|-------------|
| QC TFL outputs | rtf/pdf | output/tfl/qc/ | Independent QC outputs |
| Double programming report | html | reports/tfl-double-programming-report.html | Comparison results |

---

## Double Programming Process

### Independence Requirements
```yaml
independence_rules:
  - "QC programmer must NOT see production code before writing QC code"
  - "QC programmer uses same table specifications and ADaM datasets"
  - "QC programmer may use a different programming language or approach"
  - "Results are compared after both are complete"
```

### Tables Requiring Double Programming
```yaml
key_tables:
  - category: "Primary Efficacy"
    required: true
    examples:
      - "Primary endpoint analysis table"
      - "Key secondary endpoint tables"

  - category: "Safety Summary"
    required: true
    examples:
      - "AE summary table"
      - "Serious AE table"

  - category: "Demographics"
    required: false
    examples:
      - "Demographics table (Table 1)"
    note: "Usually single-programmed due to simplicity"

  - category: "Supportive Analyses"
    required: false
    examples:
      - "Sensitivity analyses"
      - "Subgroup analyses"
```

### QC Programming Checklist
```yaml
qc_checklist:
  pre_programming:
    - "Read table specification independently"
    - "Identify source dataset and variables"
    - "Define filtering criteria (population, flags)"
    - "Specify statistical method from SAP"
    - "Write QC code without referencing production code"

  post_programming:
    - "Generate QC output"
    - "Compare with production output using /tfl-comparator"
    - "Investigate any discrepancies to root cause"
    - "Document root cause and resolution"
    - "Archive QC code for audit trail"
```

### Root Cause Classification
```yaml
root_cause_categories:
  - category: "SPECIFICATION_AMBIGUITY"
    description: "Table specification was unclear, led to different interpretations"
    resolution: "Clarify specification with statistician, update both"

  - category: "DATA_FILTERING"
    description: "Different filtering applied (population flag, visit, etc.)"
    resolution: "Align filtering, verify with SAP"

  - category: "STATISTICAL_METHOD"
    description: "Different statistical method or implementation"
    resolution: "Verify method against SAP, correct as needed"

  - category: "ROUNDING_PRECISION"
    description: "Different rounding approach"
    resolution: "Align to specification, document precision rules"

  - category: "PROGRAMMING_ERROR_PROD"
    description: "Production code had a bug"
    resolution: "Fix production, re-run, re-compare"

  - category: "PROGRAMMING_ERROR_QC"
    description: "QC code had a bug"
    resolution: "Fix QC, re-run, re-compare"

  - category: "SOFTWARE_DIFFERENCE"
    description: "Different software produced different precision"
    resolution: "Document, accept if within tolerance"
```

---

## Output Schema

```yaml
double_programming_result:
  study_id: "{study_id}"
  timestamp: "{ISO_8601}"

  tables_double_programmed:
    - tfl_id: "Table 14.3.1"
      title: "Primary Efficacy Analysis"
      production_path: "output/tfl/tables/table-14.3.1.rtf"
      qc_path: "output/tfl/qc/table-14.3.1-qc.rtf"
      qc_programmer: "{programmer_id}"
      match_status: "MATCH | DISCREPANCY"
      discrepancies:
        - description: "n count differs for {treatment_arm}"
          production_value: "72"
          qc_value: "73"
          root_cause: "DATA_FILTERING"
          resolution: "Production used SAFFL='Y', QC used ITTFL='Y'. Aligned to SAFFL per SAP."
          resolved: true
```

---

## Edge Cases

### Different Programming Languages
- Production in SAS, QC in Python (or vice versa) is acceptable
- Different languages may produce slightly different floating-point results
- Apply tolerance-based comparison

### Specification Interpretation Differences
- If the SAP is ambiguous, both programmers may interpret differently
- Document the ambiguity and get statistician clarification
- Update specification for future reference

### Unable to Match
- If production and QC cannot be reconciled, escalate to statistician
- The statistician determines the correct approach
- Both outputs are corrected if needed

---

## Integration Points

### Upstream Skills
- `/tfl-table-generator` -- Production outputs (QC programmer must not see code)
- `/adam-adsl-builder` -- ADSL for QC programming
- `/sap-parser` -- Specifications for QC programming

### Downstream Skills
- `/tfl-comparator` -- Automated comparison of production vs QC
- `/tfl-qc-validator` -- Overall QC validation report

### Related Skills
- `/workflow` -- Track double programming status

---

## Evaluation Criteria

**Mandatory:**
- Key efficacy and safety tables double-programmed
- All discrepancies resolved with documented root cause
- QC code archived for audit trail

**Recommended:**
- Automated comparison tools used
- QC programmer uses different approach than production

---

## Critical Constraints

**Never:**
- Allow QC programmer to see production code before writing QC code
- Dismiss discrepancies without root cause analysis
- Modify QC to match production without understanding the difference

**Always:**
- Maintain independence between production and QC programming
- Document root cause for every discrepancy
- Archive all QC code and outputs
- Use the same ADaM datasets and specifications
- Resolve all discrepancies before finalization

---

## Examples

### Double Program Key Tables
```bash
python csp-skills/layer-5-tfl/tfl-double-programmer/script.py \
  --input output/adam/ \
  --spec specs/table-specs.yaml \
  --output output/tfl/qc/ \
  --tables key_tables
```

### Double Program Single Table
```bash
python csp-skills/layer-5-tfl/tfl-double-programmer/script.py \
  --input output/adam/ \
  --spec specs/table-specs.yaml \
  --output output/tfl/qc/table-14.3.1-qc.rtf \
  --tables table-14.3.1
```
