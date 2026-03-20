---
name: sdrg-writer
description: Write SDTM Reviewers Guide (SDRG). Triggers on "SDRG", "reviewer guide", "SDTM reviewer", "reviewer's guide", "PhUSE", "study data reviewer".
version: "1.0"
user-invocable: true
context: fork
model: sonnet
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
argument-hint: "[options] -- --input, --output"
---

## Runtime Configuration (Step 0)
Read: docs/sdrg.pdf

## EXECUTE NOW
Parse $ARGUMENTS: --input, --output, --spec, --validate, --dry-run
**START NOW.**

---

## Philosophy
**The SDRG helps FDA reviewers understand data. It must explain non-standard variables, data issues, and study-specific decisions.**

---

## Script Execution
```bash
python csp-skills/layer-3-sdtm-qc/sdrg-writer/script.py --input <input_path> --output <output_path>
```

---

## Key Variables

| Variable | Description |
|----------|-------------|
| SECTION | Guide section |
| CONTENT | Section content |

---

## Evaluation Criteria
**Mandatory:**
- All P21 issues addressed in guide
- Non-standard variables justified

**Recommended:**
- Follows PhUSE SDRG template structure

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
