---
name: sdtm-vs-mapper
description: Map vital signs to SDTM VS domain. Triggers on "VS", "vital signs", "vitals", "VS domain", "blood pressure", "heart rate".
version: "1.0"
user-invocable: true
context: fork
model: sonnet
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
argument-hint: "[options] -- --input, --output"
---

## Runtime Configuration (Step 0)
Read: output/sdtm/vs.xpt

## EXECUTE NOW
Parse $ARGUMENTS: --input, --output, --spec, --validate, --dry-run
**START NOW.**

---

## Philosophy
**Vital signs require careful unit standardization. Position (VSPOS) and timing relative to dose are critical for analysis.**

---

## Script Execution
```bash
python csp-skills/layer-2-sdtm/sdtm-vs-mapper/script.py --input <input_path> --output <output_path>
```

---

## Key Variables

| Variable | Description |
|----------|-------------|
| VSTEST | Vital sign test |
| VSSTRESN | Standard result |
| VSPOS | Position |

---

## Evaluation Criteria
**Mandatory:**
- VSTESTCD matches CDISC controlled terminology
- Standard units derived

**Recommended:**
- Position (VSPOS) captured where applicable

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
