---
name: tfl-qc-validator
description: Independent QC validation of all TFLs. Triggers on "TFL QC", "QC", "quality control", "TFL validation", "independent QC", "output verification".
version: "1.0"
user-invocable: true
context: fork
model: sonnet
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
argument-hint: "[options] -- --input, --output"
---

## Runtime Configuration (Step 0)
Read: reports/tfl-qc-report.html

## EXECUTE NOW
Parse $ARGUMENTS: --input, --output, --spec, --validate, --dry-run
**START NOW.**

---

## Philosophy
**QC validation ensures accuracy. Every number in a table must trace back to ADaM data through reproducible code.**

---

## Script Execution
```bash
python csp-skills/layer-5-tfl/tfl-qc-validator/script.py --input <input_path> --output <output_path>
```

---

## Key Variables

| Variable | Description |
|----------|-------------|
| TFL_ID | Output identifier |
| QC_STATUS | Pass/Fail |
| DISCREPANCIES | Issue count |

---

## Evaluation Criteria
**Mandatory:**
- All TFLs independently QC'd
- Zero unresolved discrepancies

**Recommended:**
- QC programs archived

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
