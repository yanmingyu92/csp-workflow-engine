---
name: data-reconciler
description: Reconcile data across sources (EDC vs labs, SAE vs AE). Triggers on "reconciliation", "reconcile", "data reconciliation", "cross-source", "EDC vs lab", "SAE reconciliation".
version: "1.0"
user-invocable: true
context: fork
model: sonnet
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
argument-hint: "[options] -- --input, --output"
---

## Runtime Configuration (Step 0)
Read: reports/reconciliation-report.html

## EXECUTE NOW
Parse $ARGUMENTS: --input, --output, --spec, --validate, --dry-run
**START NOW.**

---

## Philosophy
**Data reconciliation catches discrepancies between independent data sources before they propagate into SDTM.**

---

## Script Execution
```bash
python csp-skills/layer-1-raw-data/data-reconciler/script.py --input <input_path> --output <output_path>
```

---

## Key Variables

| Variable | Description |
|----------|-------------|
| SOURCE_A | First data source |
| SOURCE_B | Second data source |
| DISCREPANCY | Difference found |

---

## Evaluation Criteria
**Mandatory:**
- All cross-source discrepancies documented

**Recommended:**
- Discrepancy resolution tracked

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
