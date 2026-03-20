---
name: define-draft-builder
description: Generate draft Define.xml metadata for SDTM. Triggers on "Define.xml draft", "SDTM Define", "define draft", "dataset metadata", "variable metadata", "CRT-DD".
version: "1.0"
user-invocable: true
context: fork
model: sonnet
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
argument-hint: "[options] -- --input, --output"
---

## Runtime Configuration (Step 0)
Read: output/define/define-sdtm-draft.xml

## EXECUTE NOW
Parse $ARGUMENTS: --input, --output, --spec, --validate, --dry-run
**START NOW.**

---

## Philosophy
**Draft Define.xml captures dataset/variable metadata early. Feeds into final Define.xml in Layer 6.**

---

## Script Execution
```bash
python csp-skills/layer-3-sdtm-qc/define-draft-builder/script.py --input <input_path> --output <output_path>
```

---

## Key Variables

| Variable | Description |
|----------|-------------|
| DATASET | Dataset name |
| VARIABLE | Variable name |
| LABEL | Variable label |

---

## Evaluation Criteria
**Mandatory:**
- All datasets and variables described
- Controlled terminology references included

**Recommended:**
- Value-level metadata for key variables

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
