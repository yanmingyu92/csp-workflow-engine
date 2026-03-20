---
name: sdtm-lb-mapper
description: Map laboratory data to SDTM LB domain. Triggers on "LB", "lab", "laboratory", "lab data", "LB domain", "LBTEST".
version: "1.0"
user-invocable: true
context: fork
model: sonnet
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
argument-hint: "[options] -- --input, --output"
---

## Runtime Configuration (Step 0)
Read: output/sdtm/lb.xpt

## EXECUTE NOW
Parse $ARGUMENTS: --input, --output, --spec, --validate, --dry-run
**START NOW.**

---

## Philosophy
**LB domain handles unit conversions and reference ranges. Standard units (LBSTRESU) must be derived with proper conversion factors.**

---

## Script Execution
```bash
python csp-skills/layer-2-sdtm/sdtm-lb-mapper/script.py --input <input_path> --output <output_path>
```

---

## Key Variables

| Variable | Description |
|----------|-------------|
| LBTEST | Lab test name |
| LBSTRESN | Standard result numeric |
| LBNRIND | Normal range indicator |

---

## Evaluation Criteria
**Mandatory:**
- Standard units (LBSTRESU) derived with conversion factors
- Reference ranges (LBORNRLO, LBORNRHI) populated
- LBTESTCD matches CDISC controlled terminology

**Recommended:**
- LBNRIND derived from reference ranges

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
