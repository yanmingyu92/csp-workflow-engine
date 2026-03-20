---
name: sdtm-ae-mapper
description: Map adverse event data to SDTM AE domain with MedDRA coding. Triggers on "AE", "adverse event", "AETERM", "AEDECOD", "MedDRA".
version: "1.0"
user-invocable: true
context: fork
model: sonnet
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
argument-hint: "[options] — --input, --output, --spec"
---

## Runtime Configuration (Step 0)
Read: specs/sdtm-mapping-spec.yaml, data/raw/ae.csv

## EXECUTE NOW
**START NOW.**

---

## Philosophy
**AE captures all safety signals.** Every adverse event must from treatment exposure to the end of study must be captured, coded with MedDRA, and analyzed for safety signals.

---

## Key Variables

| Variable | Required | Source |
|----------|----------|--------|
| AETERM | Yes | Raw AE text |
| AEDECOD | Yes | MedDRA coding |
| AEBODSYS | Yes | MedDRA body system |
| AESEV | Yes | Severity |
| AESER | Yes | Seriousness |
| AEREL | Yes | Relationship |

---

## Evaluation Criteria
**Mandatory:** All AE records coded with MedDRA PT and SOC
**Recommended:** Treatment-emergent flag derived
