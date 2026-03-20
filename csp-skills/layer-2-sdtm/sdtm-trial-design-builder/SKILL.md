---
name: sdtm-trial-design-builder
description: Create FDA-required trial design datasets (TS, TA, TI, TV). Triggers on "trial design", "TS", "TA", "TI", "TV".
version: "1.0"
user-invocable: true
context: fork
model: sonnet
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
argument-hint: "[options] -- --protocol, --output-dir"
---

## Runtime Configuration (Step 0)
Read: docs/protocol.pdf, specs/study-config.yaml

## EXECUTE NOW
**START NOW.**

---

## Philosophy
**Trial design datasets define study structure.** FDA requires TS, TA, TI, TV to understand the trial's arms, visits, elements, and inclusion criteria programmatically.

---

## Trial Design Datasets

| Dataset | Purpose | Key Variables |
|---------|---------|---------------|
| TS | Trial Summary | TSPARM, TSVAL |
| TA | Trial Arms | ARM, ARMCD, TAETORD |
| TI | Trial Inclusion | IETEST, IECAT |
| TV | Trial Visits | VISIT, VISITNUM, VISTYP |

---

## Trial Summary Parameters (TS)
- Title (TSPARMCD = TITLE)
- Indication (TSPARMCD = INDIC)
- Phase (TSPARMCD = PHASE)
- Study Type (TSPARMCD = STUDYTYP)
- Planned Enrollment (TSPARMCD = PLANSUB)

---

## Evaluation Criteria
**Mandatory:** All four datasets present with required parameters
**Recommended:** All CDISC core parameters included
