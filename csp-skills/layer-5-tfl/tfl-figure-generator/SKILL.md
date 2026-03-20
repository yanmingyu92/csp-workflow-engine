---
name: tfl-figure-generator
description: Generate analysis figures (KM curves, forest plots). Triggers on "figure", "plot", "Kaplan-Meier", "forest plot", "waterfall", "spaghetti plot".
version: "1.0"
user-invocable: true
context: fork
model: sonnet
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
argument-hint: "[options] -- --input, --output"
---

## Runtime Configuration (Step 0)
Read: output/tfl/figures/

## EXECUTE NOW
Parse $ARGUMENTS: --input, --output, --spec, --validate, --dry-run
**START NOW.**

---

## Philosophy
**Figures must be publication-quality (300+ DPI). Kaplan-Meier, forest plots, and waterfall plots follow specific conventions.**

---

## Script Execution
```bash
python csp-skills/layer-5-tfl/tfl-figure-generator/script.py --input <input_path> --output <output_path>
```

---

## Key Variables

| Variable | Description |
|----------|-------------|
| FIGURE_ID | Figure identifier |
| TYPE | KM/Forest/Waterfall/Bar |
| RESOLUTION | DPI |

---

## Evaluation Criteria
**Mandatory:**
- All SAP-mandated figures produced
- Axis labels and legends correct

**Recommended:**
- Publication-quality resolution (300+ DPI)

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
