---
name: crf-annotator
description: Annotate blank CRF with SDTM variable targets. Triggers on "CRF", "case report form", "annotated CRF", "aCRF", "CRF annotation", "CDASH".
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
**The annotated CRF (aCRF) bridges clinical operations and data standards. Every CRF field must map to a specific SDTM domain.variable.**

---

## Script Execution
```bash
python csp-skills/layer-1-raw-data/crf-annotator/script.py --input <input_path> --output <output_path>
```

---

## Key Variables

| Variable | Description |
|----------|-------------|
| CRF_FIELD | Source field from CRF |
| SDTM_DOMAIN | Target SDTM domain |
| SDTM_VARIABLE | Target SDTM variable |

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
