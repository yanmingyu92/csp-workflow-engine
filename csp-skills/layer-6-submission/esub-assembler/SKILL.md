---
name: esub-assembler
description: Assemble eCTD Module 5 submission package. Triggers on "eCTD", "submission package", "eSub", "Module 5", "electronic submission", "submission assembly".
version: "1.0"
user-invocable: true
context: fork
model: sonnet
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
argument-hint: "[options] -- --input, --output"
---

## Runtime Configuration (Step 0)
Read: output/esub/

## EXECUTE NOW
Parse $ARGUMENTS: --input, --output, --spec, --validate, --dry-run
**START NOW.**

---

## Philosophy
**eCTD structure must follow FDA guidance precisely. Directory naming, file placement, and reference linkage are critical.**

---

## Script Execution
```bash
python csp-skills/layer-6-submission/esub-assembler/script.py --input <input_path> --output <output_path>
```

---

## Key Variables

| Variable | Description |
|----------|-------------|
| COMPONENT | Package component |
| PATH | eCTD path |
| STATUS | Included/Missing |

---

## Evaluation Criteria
**Mandatory:**
- All required components present
- eCTD directory structure correct
- File naming conventions followed

**Recommended:**
- Package size within FDA limits

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
