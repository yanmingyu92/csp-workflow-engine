---
name: quality-report
description: Generate data quality report with metrics and visualizations. Triggers on "data quality", "raw data check", "data validation", "missing values", "duplicate records", "range check".
version: "1.0"
user-invocable: true
context: fork
model: sonnet
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
argument-hint: "[options] -- --input, --output"
---

## Runtime Configuration (Step 0)
Read: reports/data-quality-report.html, data/validated/

## EXECUTE NOW
Parse $ARGUMENTS: --input, --output, --spec, --validate, --dry-run
**START NOW.**

---

## Philosophy
**Quality reports provide stakeholders with actionable insights. Every metric must be traceable to a specific validation check.**

---

## Script Execution
```bash
python csp-skills/layer-1-raw-data/quality-report/script.py --input <input_path> --output <output_path>
```

---

## Key Variables

| Variable | Description |
|----------|-------------|
| METRIC | Quality metric name |
| VALUE | Metric value |
| THRESHOLD | Acceptable threshold |

---

## Evaluation Criteria
**Mandatory:**
- All datasets pass type/format validation
- Duplicate records identified and documented
- Quality report generated

**Recommended:**
- Range checks applied per protocol-defined limits

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
