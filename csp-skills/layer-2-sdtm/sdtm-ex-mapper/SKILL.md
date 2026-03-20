---
name: sdtm-ex-mapper
description: Map exposure/dosing data to SDTM EX domain with dose calculations. Triggers on "EX", "exposure", "dosing", "EXTRT", "EXDOSE".
version: "1.0"
user-invocable: true
context: fork
model: sonnet
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
argument-hint: "[options] -- --input, --output, --spec"
---

## Runtime Configuration (Step 0)
Read: specs/sdtm-mapping-spec.yaml, data/raw/ex.csv

## EXECUTE NOW
**START NOW.**

---

## Philosophy
**EX tracks all treatment exposure.** Every dose administered must be captured with exact timing, route, and amount to support pharmacokinetic and efficacy analyses.

---

## Key Variables

| Variable | Required | Source |
|----------|----------|--------|
| EXTRT | Yes | Treatment name |
| EXDOSE | Yes | Dose amount |
| EXDOSU | Yes | Dose units |
| EXROUTE | Yes | Route of administration |
| EXSTDTC | Yes | Start date/time |
| EXENDTC | No | End date/time |

---

## Dose Calculations
- Cumulative dose over study
- Relative day from first dose
- Dose intensity calculations

---

## Evaluation Criteria
**Mandatory:** All dosing records with valid EXTRT, EXDOSE, EXSTDTC
**Recommended:** Dose intensity derived for efficacy correlation
