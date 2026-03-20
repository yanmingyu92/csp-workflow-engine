---
name: tfl-comparator
description: Compare TFL production vs QC outputs. Triggers on "TFL QC", "QC", "quality control", "TFL validation", "independent QC", "output verification".
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
**Comparison must detect both content and formatting differences. Cell-by-cell comparison for tables, pixel comparison for figures.**

---

## Script Execution
```bash
python csp-skills/layer-5-tfl/tfl-comparator/script.py --input <input_path> --output <output_path>
```

---

## Key Variables

| Variable | Description |
|----------|-------------|
| TFL_ID | Output identifier |
| MATCH_STATUS | Match/Mismatch |
| DIFF_COUNT | Number of differences |

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
