---
name: adtte-builder
description: Build ADTTE time-to-event analysis dataset. Triggers on "ADTTE", "time-to-event", "survival".
version: "1.0"
user-invocable: true
context: fork
model: sonnet
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
argument-hint: "[options] -- --input-dir, --output, --event-type"
---

## Runtime Configuration (Step 0)
Read: output/adam/adsl.xpt, output/sdtm/ae.xpt, specs/tte-parameters.yaml

## EXECUTE NOW
**START NOW.**

---

## Philosophy
**ADTTE enables survival analysis.** Time from origin to event or censor, with proper handling of competing risks.

---

## Key Variables

| Variable | Description |
|----------|-------------|
| PARAM | Time-to-event parameter (e.g., "Time to First AE") |
| PARAMCD | Parameter code (e.g., "TTFAE") |
| AVAL | Time value (days) |
| CNSR | Censor (0=event, 1=censored) |
| EVNTDESC | Event description |
| CNSDTDSC | Censor description |

---

## Time Origins
- Randomization (common for efficacy)
- First dose (common for safety)
- Study entry (screening failures)

---

## Censoring Rules
- Study completion without event
- Lost to follow-up
- Cut-off date reached

---

## Evaluation Criteria
**Mandatory:** AVAL, CNSR for all subjects
**Recommended:** EVNTDESC, CNSDTDSC populated
