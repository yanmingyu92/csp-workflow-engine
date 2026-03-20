---
name: acrf-finalizer
description: Finalize annotated CRF with verified annotations. Triggers on "annotated CRF", "aCRF", "final aCRF", "CRF finalize", "CRF annotation finalization", "blank CRF".
version: "1.0"
user-invocable: true
context: fork
model: sonnet
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
argument-hint: "[options] -- --input, --output"
---

## Runtime Configuration (Step 0)
Read: docs/acrf-final.pdf

## EXECUTE NOW
Parse $ARGUMENTS: --input, --output, --spec, --validate, --dry-run
**START NOW.**

---

## Philosophy
**Final aCRF must exactly match produced SDTM datasets. Every annotation links a CRF field to an actual domain.variable.**

---

## Script Execution
```bash
python csp-skills/layer-3-sdtm-qc/acrf-finalizer/script.py --input <input_path> --output <output_path>
```

---

## Key Variables

| Variable | Description |
|----------|-------------|
| CRF_PAGE | CRF page number |
| ANNOTATION | SDTM mapping annotation |
| VERIFIED | Yes/No |

---

## Evaluation Criteria
**Mandatory:**
- Every annotation matches produced dataset variable

**Recommended:**
- Annotations include origin type

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
