---
name: demographics-table
description: Generate demographics summary table by treatment. Triggers on "demographics", "Table 1".
version: "1.0"
user-invocable: true
context: fork
model: haiku
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
argument-hint: "[options] -- --input, --output, --population"
---

## Runtime Configuration (Step 0)
Read: output/adam/adsl.xpt, specs/table-specs.yaml

## EXECUTE NOW
**START NOW.**

---

## Philosophy
**Demographics establish cohort comparability.** Table 1 confirms randomization balanced treatment groups.

---

## Table Structure

| Row Group | Variables |
|-----------|-----------|
| Age | n, Mean (SD), Median, Range |
| Age Group | <65, >=65 (n, %) |
| Sex | Male, Female (n, %) |
| Race | White, Other (n, %) |

---

## Statistics
- Continuous: n, Mean, SD, Median, Min, Max
- Categorical: n (%)

---

## Column Headers
- Placebo (N=XX)
- Treatment A (N=XX)
- Total (N=XX)

---

## Evaluation Criteria
**Mandatory:** Age, Sex, Race by treatment
**Recommended:** p-values for group comparisons
