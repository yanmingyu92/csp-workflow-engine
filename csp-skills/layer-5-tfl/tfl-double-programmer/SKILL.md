---
name: tfl-double-programmer
description: Independent double programming for key outputs. Triggers on "double programming", "independent programming", "production vs QC", "dual programming", "verification programming", "independent verification".
version: "1.0"
user-invocable: true
context: fork
model: sonnet
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
argument-hint: "[options] -- --input, --output"
---

## Runtime Configuration (Step 0)
Read: reports/tfl-double-programming-report.html

## EXECUTE NOW
Parse $ARGUMENTS: --input, --output, --spec, --validate, --dry-run
**START NOW.**

---

## Philosophy
**Double programming provides the highest assurance. Independent code, same results. Discrepancies require root cause analysis.**

---

## Script Execution
```bash
python csp-skills/layer-5-tfl/tfl-double-programmer/script.py --input <input_path> --output <output_path>
```

---

## Key Variables

| Variable | Description |
|----------|-------------|
| TFL_ID | Output identifier |
| MATCH | Yes/No |
| ROOT_CAUSE | If mismatch, reason |

---

## Evaluation Criteria
**Mandatory:**
- Key efficacy and safety tables double-programmed
- All discrepancies resolved with documentation

**Recommended:**
- Automated comparison tools used

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
