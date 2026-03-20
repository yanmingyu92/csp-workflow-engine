---
name: sdtm-supp-builder
description: Create SUPPXX datasets for non-standard variables. Triggers on "SUPP", "supplemental", "QNAM", "non-standard variable".
version: "1.0"
user-invocable: true
context: fork
model: sonnet
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
argument-hint: "[options] -- --input-dir, --output-dir, --spec"
---

## Runtime Configuration (Step 0)
Read: output/sdtm/*.xpt, specs/sdtm-mapping-spec.yaml

## EXECUTE NOW
**START NOW.**

---

## Philosophy
**SUPPXX captures non-standard qualifiers.** When variables don't fit standard domain structure, SUPPXX provides a compliant way to include them while maintaining referential integrity.

---

## Key Variables

| Variable | Required | Purpose |
|----------|----------|---------|
| RDOMAIN | Yes | Parent domain |
| IDVAR | Yes | ID variable (e.g., AESEQ) |
| IDVARVAL | Yes | ID variable value |
| QNAM | Yes | Qualifier name |
| QLABEL | Yes | Qualifier label |
| QVAL | Yes | Qualifier value |

---

## Common Use Cases
- Ethnicity details (SUPPDM)
- Cancer staging (SUPPDM)
- Prior medication details (SUPPCM)
- Custom visit flags

---

## Naming Convention
- QNAM: UppERCASE, max 8 characters
- Must start with letter
- No special characters

---

## Evaluation Criteria
**Mandatory:** Valid QNAM/QLABEL pairs, referential integrity
**Recommended:** Controlled terminology for QVAL where applicable
