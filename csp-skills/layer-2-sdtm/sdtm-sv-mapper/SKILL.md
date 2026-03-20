---
name: sdtm-sv-mapper
description: Map subject visits to SDTM SV domain. Triggers on "SV", "subject visits", "visits", "SV domain", "VISIT", "VISITNUM".
version: "1.0"
user-invocable: true
context: fork
model: sonnet
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
argument-hint: "[options] -- --input, --output"
---

## Runtime Configuration (Step 0)
Read: output/sdtm/sv.xpt

## EXECUTE NOW
Parse $ARGUMENTS: --input, --output, --spec, --validate, --dry-run
**START NOW.**

---

## Philosophy
**SV domain documents actual visit dates. Essential for ADaM visit windowing and analysis timeline construction.**

---

## Script Execution
```bash
python csp-skills/layer-2-sdtm/sdtm-sv-mapper/script.py --input <input_path> --output <output_path>
```

---

## Key Variables

| Variable | Description |
|----------|-------------|
| VISIT | Visit name |
| VISITNUM | Visit number |
| SVSTDTC | Visit start date |

---

## Evaluation Criteria
**Mandatory:**
- All protocol visits captured
- VISITNUM in ascending order within subject
- SVSTDTC in ISO 8601 format

**Recommended:**
- Unscheduled visits flagged appropriately

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
