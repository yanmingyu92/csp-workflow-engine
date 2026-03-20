---
name: adam-validation
description: Validate ADaM datasets against ADaM IG and specs. Triggers on "ADaM validation", "ADaM QC".
version: "1.0"
user-invocable: true
context: fork
model: sonnet
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
argument-hint: "[options] -- --input-dir, --spec, --report"
---

## Runtime Configuration (Step 0)
Read: output/adam/*.xpt, specs/adam-spec.yaml, specs/analysis-populations.yaml

## EXECUTE NOW
**START NOW.**

---

## Philosophy
**ADaM must support traceability and reproducibility.** Every variable must have clear derivation, and datasets must support protocol-specified analyses.

---

## Validation Checks

### Structure
- 1 record per subject in ADSL
- Required variables present
- Variable types correct

### Consistency
- Merge with SDTM succeeds
- Treatment assignment matches DM
- Population counts consistent

### Traceability
- All variables in spec
- Derivation documented
- Source variables retained

---

## Common Issues
- Missing TRTA in analysis datasets
- Date format inconsistencies
- Population flag mismatches

---

## Evaluation Criteria
**Mandatory:** All ADaM IG requirements met
**Recommended:** Analysis traceability documented
