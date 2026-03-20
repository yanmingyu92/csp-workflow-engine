---
name: p21-validator
description: Run Pinnacle 21 validation on datasets. Triggers on "P21", "Pinnacle 21", "SDTM validation", "P21 validation", "compliance check", "validation report".
version: "1.0"
user-invocable: true
context: fork
model: sonnet
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
argument-hint: "[options] -- --input, --output"
---

## Runtime Configuration (Step 0)
Read: reports/p21-sdtm-report.xlsx, ops/p21-sdtm-issues.yaml

## EXECUTE NOW
Parse $ARGUMENTS: --input, --output, --spec, --validate, --dry-run
**START NOW.**

---

## Philosophy
**P21 validation is the industry standard compliance gate. Zero errors is mandatory; warnings must be reviewed and justified.**

---

## Script Execution
```bash
python csp-skills/layer-3-sdtm-qc/p21-validator/script.py --input <input_path> --output <output_path>
```

---

## Key Variables

| Variable | Description |
|----------|-------------|
| RULE_ID | P21 rule ID |
| SEVERITY | Error/Warning/Info |
| MESSAGE | Issue description |

---

## Evaluation Criteria
**Mandatory:**
- Zero P21 errors (severity = Error)
- All warnings reviewed and justified or resolved

**Recommended:**
- Zero P21 warnings

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
