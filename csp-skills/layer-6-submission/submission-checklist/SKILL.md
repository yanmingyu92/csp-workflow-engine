---
name: submission-checklist
description: Generate submission readiness checklist. Triggers on "final validation", "submission validation", "FDA validation", "ESG gateway", "submission readiness", "pre-submission check".
version: "1.0"
user-invocable: true
context: fork
model: sonnet
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
argument-hint: "[options] -- --input, --output"
---

## Runtime Configuration (Step 0)
Read: reports/submission-readiness-report.html, ops/submission-checklist.yaml

## EXECUTE NOW
Parse $ARGUMENTS: --input, --output, --spec, --validate, --dry-run
**START NOW.**

---

## Philosophy
**The checklist ensures nothing is missed. Every required component must be present and validated before submission.**

---

## Script Execution
```bash
python csp-skills/layer-6-submission/submission-checklist/script.py --input <input_path> --output <output_path>
```

---

## Key Variables

| Variable | Description |
|----------|-------------|
| ITEM | Checklist item |
| STATUS | Complete/Pending/Missing |
| OWNER | Responsible party |

---

## Evaluation Criteria
**Mandatory:**
- All FDA validation checks pass
- Readiness checklist 100% complete

**Recommended:**
- Test submission to FDA ESG gateway (if available)

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
