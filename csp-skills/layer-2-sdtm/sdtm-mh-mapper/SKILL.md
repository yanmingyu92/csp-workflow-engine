---
name: sdtm-mh-mapper
description: Map medical history to SDTM MH domain. Triggers on "MH", "medical history", "MH domain", "MHTERM", "MHDECOD", "past medical history".
version: "1.0"
user-invocable: true
context: fork
model: sonnet
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
argument-hint: "[options] -- --input, --output"
---

## Runtime Configuration (Step 0)
Read: output/sdtm/mh.xpt

## EXECUTE NOW
Parse $ARGUMENTS: --input, --output, --spec, --validate, --dry-run
**START NOW.**

---

## Philosophy
**Medical history captures pre-existing conditions. MedDRA coding standardizes condition identification across studies.**

---

## Script Execution
```bash
python csp-skills/layer-2-sdtm/sdtm-mh-mapper/script.py --input <input_path> --output <output_path>
```

---

## Key Variables

| Variable | Description |
|----------|-------------|
| MHTERM | Medical history term |
| MHDECOD | MedDRA coded term |
| MHBODSYS | Body system |

---

## Evaluation Criteria
**Mandatory:**
- MedDRA coding applied

**Recommended:**
- MHCAT categorization consistent

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
