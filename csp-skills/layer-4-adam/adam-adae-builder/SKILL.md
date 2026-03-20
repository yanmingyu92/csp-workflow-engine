---
name: adae-builder
description: Build ADAE adverse events analysis dataset from SDTM AE. Triggers on "ADAE", "adverse events analysis".
version: "1.0"
user-invocable: true
context: fork
model: sonnet
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
argument-hint: "[options] -- --input-dir, --output"
---

## Runtime Configuration (Step 0)
Read: output/adam/adsl.xpt, output/sdtm/ae.xpt, specs/adam-spec.yaml

## EXECUTE NOW
**START NOW.**

---

## Philosophy
**ADAE enables safety analysis.** Each adverse event is annotated with treatment, population flags, and derived variables for summarization.

---

## Key Variables

| Variable | Source | Description |
|----------|--------|-------------|
| AETERM | AE | Adverse event term |
| AEDECOD | AE | MedDRA preferred term |
| TRTA | ADSL | Actual treatment |
| SAFFL | ADSL | Safety population |
| ASTDT | AE | Analysis start date |
| ASTDY | Derived | Analysis start day |

---

## Treatment-Emergent Flag
- **TRTEMFL**: Y if AE start >= first dose date and <= last dose + X days

---

## Severity Analysis
- Group by AESEV for severity summaries
- Cross-tabulate with treatment

---

## Evaluation Criteria
**Mandatory:** Merged with ADSL, TRTEMFL derived
**Recommended:** Analysis dates/days, severity groupings
