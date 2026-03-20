---
name: data-quality
description: Universal data quality checking. Global skill available at every node. Triggers on "data quality", "check data", "validate data", "completeness", "consistency".
version: "1.0"
user-invocable: true
context: fork
model: sonnet
allowed-tools: Read, Write, Grep, Glob, Bash
argument-hint: "[options] -- --input <dataset_path> --checks [all|completeness|consistency|conformance]"
---

## Runtime Configuration (Step 0)
Read: input dataset, specs/study-config.yaml

## EXECUTE NOW
Parse $ARGUMENTS: --input, --checks, --output, --threshold
**START NOW.**

---

## Philosophy
**Data quality is everyone's responsibility, at every stage.** This universal checker runs completeness, consistency, and conformance checks on any dataset at any pipeline stage. It adapts its checks based on the current graph layer.

---

## Check Categories

| Category | Description | Examples |
|----------|-------------|---------|
| Completeness | Missing values, required fields | NULL rates, mandatory field coverage |
| Consistency | Cross-variable logic | Date ordering, value ranges, duplicates |
| Conformance | Standards compliance | CDISC CT, ISO 8601, naming conventions |

---

## Layer-Adaptive Checks
- **Layer 0-1 (Protocol/Raw):** Focus on completeness, encoding, duplicates
- **Layer 2 (SDTM):** CDISC domain structure, CT conformance, key variable presence
- **Layer 3 (SDTM QC):** Cross-domain consistency, RELREC integrity
- **Layer 4 (ADaM):** Traceability, ADSL population flags, BDS structure
- **Layer 5 (TFL):** Number formatting, statistical precision, footnote completeness
- **Layer 6 (Submission):** Define.xml schema, eCTD structure

---

## Evaluation Criteria
**Mandatory:** Report all critical issues (>5% missing in key vars)
**Recommended:** Trend analysis, comparison with previous runs
