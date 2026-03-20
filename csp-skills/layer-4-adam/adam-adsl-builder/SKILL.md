---
name: adsl-builder
description: Build ADSL subject-level dataset with all derived variables. Triggers on "ADSL", "subject level", "population flags".
version: "1.0"
user-invocable: true
context: fork
model: sonnet
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
argument-hint: "[options] -- --input-dir, --output"
---

## Runtime Configuration (Step 0)
Read: output/sdtm/dm.xpt, output/sdtm/ds.xpt, output/sdtm/ex.xpt, specs/adam-spec.yaml

## EXECUTE NOW
**START NOW.**

---

## Philosophy
**ADSL is the foundation of all ADaM analyses.** One record per subject, containing all subject-level flags, treatment assignments, and derived characteristics needed for analysis.

---

## Key Variables

| Variable | Category | Description |
|----------|----------|-------------|
| USUBJID | ID | Unique subject identifier |
| TRT01P | Treatment | Planned treatment |
| TRT01A | Treatment | Actual treatment |
| SAFFL | Population | Safety population flag |
| ITTFL | Population | Intent-to-treat flag |
| COMPLTFL | Disposition | Completed study flag |

---

## Population Flags
- **SAFFL**: Received at least one dose of study drug
- **ITTFL**: Randomized subjects
- **PPROTFL**: Per-protocol (no major violations)

---

## Evaluation Criteria
**Mandatory:** 1:1 merge with DM, all population flags derived
**Recommended:** Treatment dates, disposition flags, baseline characteristics
