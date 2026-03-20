---
name: define-xml-builder
description: Generate final Define.xml for datasets. Triggers on "Define.xml SDTM", "SDTM Define", "define-xml SDTM", "SDTM metadata", "CRT-DD", "final Define SDTM".
version: "1.0"
user-invocable: true
context: fork
model: sonnet
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
argument-hint: "[options] -- --input, --output"
---

## Runtime Configuration (Step 0)
Read: output/define/define-sdtm.xml

## EXECUTE NOW
Parse $ARGUMENTS: --input, --output, --spec, --validate, --dry-run
**START NOW.**

---

## Philosophy
**Define.xml is the regulatory metadata standard. Schema validation, controlled terminology refs, and computational methods are required.**

---

## Script Execution
```bash
python csp-skills/layer-6-submission/define-xml-builder/script.py --input <input_path> --output <output_path>
```

---

## Key Variables

| Variable | Description |
|----------|-------------|
| DATASET | Dataset name |
| VARIABLE | Variable name |
| METHOD | Computational method |

---

## Evaluation Criteria
**Mandatory:**
- Schema-valid against Define-XML v2.1 schema
- All datasets and variables documented
- Controlled terminology references valid

**Recommended:**
- Renders correctly in stylesheet

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
