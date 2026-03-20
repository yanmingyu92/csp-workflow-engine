---
name: adam-adlb-builder
description: Build ADLB laboratory analysis dataset (BDS). Triggers on "ADLB", "lab analysis", "BDS", "AVAL", "BASE", "CHG".
version: "1.0"
user-invocable: true
context: fork
model: sonnet
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
argument-hint: "[options] -- --input, --output"
---

## Runtime Configuration (Step 0)
Read: output/adam/adlb.xpt

## EXECUTE NOW
Parse $ARGUMENTS: --input, --output, --spec, --validate, --dry-run
**START NOW.**

---

## Philosophy
**ADLB follows BDS structure with AVAL/BASE/CHG/PCHG. Visit windowing and baseline flag (ABLFL) are critical derivations.**

---

## Script Execution
```bash
python csp-skills/layer-4-adam/adam-adlb-builder/script.py --input <input_path> --output <output_path>
```

---

## Key Variables

| Variable | Description |
|----------|-------------|
| PARAMCD | Lab parameter code |
| AVAL | Analysis value |
| BASE | Baseline value |
| CHG | Change from baseline |

---

## Evaluation Criteria
**Mandatory:**
- AVAL derived from correct source (LBSTRESN or LBORRES)
- Baseline (ABLFL) identified per SAP algorithm
- CHG = AVAL - BASE derived where applicable

**Recommended:**
- Visit windowing applied per SAP

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
