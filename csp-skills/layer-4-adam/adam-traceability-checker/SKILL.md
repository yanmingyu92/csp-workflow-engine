---
name: adam-traceability-checker
description: Verify ADaM-to-SDTM traceability. Triggers on "traceability", "ADaM traceability", "SDTM to ADaM", "variable lineage", "derivation lineage", "source variable".
version: "1.0"
user-invocable: true
context: fork
model: sonnet
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
argument-hint: "[options] -- --input, --output"
---

## Runtime Configuration (Step 0)
Read: reports/adam-traceability-report.html

## EXECUTE NOW
Parse $ARGUMENTS: --input, --output, --spec, --validate, --dry-run
**START NOW.**

---

## Philosophy
**Every ADaM variable must trace back to SDTM sources. Orphan variables indicate derivation documentation gaps.**

---

## Script Execution
```bash
python csp-skills/layer-4-adam/adam-traceability-checker/script.py --input <input_path> --output <output_path>
```

---

## Key Variables

| Variable | Description |
|----------|-------------|
| ADAM_VAR | ADaM variable |
| SDTM_SOURCE | Source SDTM variable |
| TRACEABLE | Yes/No |

---

## Evaluation Criteria
**Mandatory:**
- Every ADaM variable has documented SDTM source
- No orphan variables without traceability

**Recommended:**
- Visual lineage diagram generated

---

## Critical Constraints
**Never:**
- Produce output without validation
- Skip required variables
- Ignore CDISC controlled terminology

**Always:**
- Validate all inputs before processing
- Document any deviations from standards
- Generate traceable, reproducible results
