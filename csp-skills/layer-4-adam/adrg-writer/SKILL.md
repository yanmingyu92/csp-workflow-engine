---
name: adrg-writer
description: Write ADaM Reviewers Guide (ADRG). Triggers on "ADRG", "ADaM reviewer", "ADaM reviewer guide", "ADaM reviewer's guide", "derivation documentation", "PhUSE ADRG".
version: "1.0"
user-invocable: true
context: fork
model: sonnet
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
argument-hint: "[options] -- --input, --output"
---

## Runtime Configuration (Step 0)
Read: docs/adrg.pdf

## EXECUTE NOW
Parse $ARGUMENTS: --input, --output, --spec, --validate, --dry-run
**START NOW.**

---

## Philosophy
**The ADRG documents all ADaM derivation logic for FDA review. PhUSE template structure ensures completeness.**

---

## Script Execution
```bash
python csp-skills/layer-4-adam/adrg-writer/script.py --input <input_path> --output <output_path>
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
- All ADaM datasets described
- Derivation logic documented for key variables
- Traceability approach explained

**Recommended:**
- Follows PhUSE ADRG template structure

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
