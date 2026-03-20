---
name: sdtm-consistency-checker
description: Check cross-domain consistency for SDTM. Triggers on "cross-domain", "consistency check", "USUBJID check", "date consistency", "cross-domain consistency", "domain alignment".
version: "1.0"
user-invocable: true
context: fork
model: sonnet
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
argument-hint: "[options] -- --input, --output"
---

## Runtime Configuration (Step 0)
Read: reports/sdtm-crossdomain-report.html

## EXECUTE NOW
Parse $ARGUMENTS: --input, --output, --spec, --validate, --dry-run
**START NOW.**

---

## Philosophy
**Cross-domain consistency ensures USUBJID alignment, date coherence, and treatment arm agreement across all SDTM domains.**

---

## Script Execution
```bash
python csp-skills/layer-3-sdtm-qc/sdtm-consistency-checker/script.py --input <input_path> --output <output_path>
```

---

## Key Variables

| Variable | Description |
|----------|-------------|
| CHECK_ID | Check identifier |
| DOMAINS | Domains compared |
| RESULT | Pass/Fail |

---

## Evaluation Criteria
**Mandatory:**
- All subjects in non-DM domains exist in DM
- No date inconsistencies across domains

**Recommended:**
- Treatment arm consistent between DM and EX

---

## Critical Constraints
**Never:**
- Produce output without validation
- Skip required variables
- Ignore CDISC controlled terminology

**Always:**
- Validate all inputs before processing
- Document any deviations from standards
- Generate traceable, reproducible results
