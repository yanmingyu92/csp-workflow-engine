---
name: tfl-formatter
description: Format TFL outputs with headers, footnotes, pagination. Triggers on "table", "analysis table", "demographics table", "safety table", "efficacy table", "disposition table".
version: "1.0"
user-invocable: true
context: fork
model: sonnet
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
argument-hint: "[options] -- --input, --output"
---

## Runtime Configuration (Step 0)
Read: output/tfl/tables/

## EXECUTE NOW
Parse $ARGUMENTS: --input, --output, --spec, --validate, --dry-run
**START NOW.**

---

## Philosophy
**Consistent formatting across all TFLs ensures professional presentation. Page breaks, margins, and fonts matter.**

---

## Script Execution
```bash
python csp-skills/layer-5-tfl/tfl-formatter/script.py --input <input_path> --output <output_path>
```

---

## Key Variables

| Variable | Description |
|----------|-------------|
| TFL_ID | Output identifier |
| FORMAT | RTF/PDF |
| PAGES | Page count |

---

## Evaluation Criteria
**Mandatory:**
- All SAP-mandated tables produced
- Statistical results match independent QC
- Formatting matches shell specifications

**Recommended:**
- Consistent decimal precision across tables

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
