---
name: sdtm-custom-builder
description: Build custom SDTM domains (FA, QS, biomarkers). Triggers on "custom domain", "non-standard domain", "FA", "QS", "biomarker", "questionnaire".
version: "1.0"
user-invocable: true
context: fork
model: sonnet
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
argument-hint: "[options] -- --input, --output"
---

## Runtime Configuration (Step 0)
Read: output/sdtm/

## EXECUTE NOW
Parse $ARGUMENTS: --input, --output, --spec, --validate, --dry-run
**START NOW.**

---

## Philosophy
**Custom domains follow Findings About (FA) or general observation class structure. Two-character domain code required.**

---

## Script Execution
```bash
python csp-skills/layer-2-sdtm/sdtm-custom-builder/script.py --input <input_path> --output <output_path>
```

---

## Key Variables

| Variable | Description |
|----------|-------------|
| DOMAIN | Custom domain code |
| TESTCD | Test code |
| ORRES | Original result |

---

## Evaluation Criteria
**Mandatory:**
- Domain code follows CDISC two-character naming convention
- Dataset-level metadata documented

**Recommended:**
- Justification written for custom domain necessity

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
