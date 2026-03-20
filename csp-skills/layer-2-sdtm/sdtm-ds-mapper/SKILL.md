---
name: sdtm-ds-mapper
description: Map disposition data to SDTM DS domain for subject status tracking. Triggers on "DS", "disposition", "DSTERM", "EOSSTT".
version: "1.0"
user-invocable: true
context: fork
model: sonnet
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
argument-hint: "[options] -- --input, --output, --spec"
---

## Runtime Configuration (Step 0)
Read: specs/sdtm-mapping-spec.yaml, data/raw/ds.csv

## EXECUTE NOW
**START NOW.**

---

## Philosophy
**DS tracks every subject journey.** From randomization to completion or discontinuation, disposition records form the audit trail for study conduct and primary analysis populations.

---

## Key Variables

| Variable | Required | Source |
|----------|----------|--------|
| DSDECOD | Yes | Standardized term |
| DSTERM | Yes | Verbatim term |
| DSCAT | Yes | Category (DISPOSITION) |
| DSSCAT | No | Subcategory |
| DSSTDTC | Yes | Date of event |

---

## Standard Disposition Terms
- COMPLETED
- DISCONTINUED
- SCREEN FAILURE
- ADVERSE EVENT
- WITHDRAWAL BY SUBJECT
- PROTOCOL VIOLATION

---

## Evaluation Criteria
**Mandatory:** All subjects with disposition record
**Recommended:** Primary reason for discontinuation captured
