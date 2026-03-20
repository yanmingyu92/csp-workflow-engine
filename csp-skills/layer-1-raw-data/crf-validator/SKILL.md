---
name: crf-validator
description: Validate CRF annotations against CDASH. Triggers on "CRF", "case report form", "annotated CRF", "aCRF", "CRF annotation", "CDASH".
version: "1.0"
user-invocable: true
context: fork
model: sonnet
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
argument-hint: "[options] -- --input, --output"
---

## Runtime Configuration (Step 0)
Read: docs/acrf-draft.pdf

## EXECUTE NOW
Parse $ARGUMENTS: --input, --output, --spec, --validate, --dry-run
**START NOW.**

---

## Philosophy
**CRF validation ensures all fields follow CDASH standards and map correctly to SDTM. Unmapped fields must be justified.**

---

## Script Execution
```bash
python csp-skills/layer-1-raw-data/crf-validator/script.py --input <input_path> --output <output_path>
```

---

## Key Variables

| Variable | Description |
|----------|-------------|
| FIELD_NAME | CRF field name |
| MAPPING_STATUS | Mapped/Unmapped |
| VALIDATION_RESULT | Pass/Fail |

---

## Evaluation Criteria
**Mandatory:**
- Every CRF field annotated with target SDTM domain.variable
- No unmapped fields without documented justification

**Recommended:**
- CDASH compliance verified for field naming

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
