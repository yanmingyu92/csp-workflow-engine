---
name: sdtm-cm-mapper
description: Map concomitant medication data to SDTM CM domain. Triggers on "CM", "concomitant medication", "conmeds", "CM domain", "CMTRT", "CMDECOD".
version: "1.0"
user-invocable: true
context: fork
model: sonnet
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
argument-hint: "[options] -- --input, --output"
---

## Runtime Configuration (Step 0)
Read: output/sdtm/cm.xpt

## EXECUTE NOW
Parse $ARGUMENTS: --input, --output, --spec, --validate, --dry-run
**START NOW.**

---

## Philosophy
**CM domain captures all medications taken by the subject. WHODrug coding is critical for standardized drug identification.**

---

## Script Execution
```bash
python csp-skills/layer-2-sdtm/sdtm-cm-mapper/script.py --input <input_path> --output <output_path>
```

---

## Key Variables

| Variable | Description |
|----------|-------------|
| CMTRT | Medication name |
| CMDECOD | WHODrug coded name |
| ATC | ATC classification |

---

## Evaluation Criteria
**Mandatory:**
- WHODrug coding applied (CMDECOD)
- ATC classification populated

**Recommended:**
- Prior vs concomitant flag derived if required

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
