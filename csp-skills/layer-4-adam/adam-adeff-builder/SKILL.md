---
name: adam-adeff-builder
description: Build ADEFF efficacy analysis dataset. Triggers on "ADEFF", "efficacy", "primary endpoint", "responder", "efficacy analysis", "response rate".
version: "1.0"
user-invocable: true
context: fork
model: sonnet
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
argument-hint: "[options] -- --input, --output"
---

## Runtime Configuration (Step 0)
Read: output/adam/adeff.xpt

## EXECUTE NOW
Parse $ARGUMENTS: --input, --output, --spec, --validate, --dry-run
**START NOW.**

---

## Philosophy
**ADEFF derives primary endpoint variables per SAP. Responder flags and derived parameters follow BDS or OCCDS structure.**

---

## Script Execution
```bash
python csp-skills/layer-4-adam/adam-adeff-builder/script.py --input <input_path> --output <output_path>
```

---

## Key Variables

| Variable | Description |
|----------|-------------|
| PARAMCD | Parameter code |
| AVAL | Analysis value |
| AVALC | Character analysis value |

---

## Evaluation Criteria
**Mandatory:**
- Primary endpoint derivation matches SAP exactly
- Responder definition consistent with SAP

**Recommended:**
- Sensitivity analyses derivations included

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
