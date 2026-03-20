---
name: adam-validator
description: Validate ADaM dataset compliance. Triggers on "ADSL", "subject level", "population flags", "SAFFL", "ITTFL", "PPROTFL".
version: "1.0"
user-invocable: true
context: fork
model: sonnet
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
argument-hint: "[options] -- --input, --output"
---

## Runtime Configuration (Step 0)
Read: output/adam/adsl.xpt

## EXECUTE NOW
Parse $ARGUMENTS: --input, --output, --spec, --validate, --dry-run
**START NOW.**

---

## Philosophy
**ADaM validation checks structural compliance (ADSL one-record-per-subject, BDS required vars) and content correctness.**

---

## Script Execution
```bash
python csp-skills/layer-4-adam/adam-validator/script.py --input <input_path> --output <output_path>
```

---

## Key Variables

| Variable | Description |
|----------|-------------|
| CHECK_ID | Validation check |
| RESULT | Pass/Fail |
| DATASET | Dataset validated |

---

## Evaluation Criteria
**Mandatory:**
- All SAP-defined population flags derived
- TRTSDT/TRTEDT correctly derived per SAP
- One record per subject
- All subjects from DM represented

**Recommended:**
- Baseline flag variables aligned with SAP

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
