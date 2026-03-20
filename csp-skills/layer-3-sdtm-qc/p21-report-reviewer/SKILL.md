---
name: p21-report-reviewer
description: Review and categorize P21 validation issues. Triggers on "P21", "Pinnacle 21", "SDTM validation", "P21 validation", "compliance check", "validation report".
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
**Systematic review of P21 issues ensures nothing is missed. Each issue must be resolved, justified, or tracked.**

---

## Script Execution
```bash
python csp-skills/layer-3-sdtm-qc/p21-report-reviewer/script.py --input <input_path> --output <output_path>
```

---

## Key Variables

| Variable | Description |
|----------|-------------|
| ISSUE_ID | Issue identifier |
| RESOLUTION | Fix/Justify/Defer |
| STATUS | Open/Closed |

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
