---
name: tfl-template-builder
description: Build reusable TFL programming templates. Triggers on "TFL shell", "mock-up", "table shell", "listing shell", "figure shell", "TFL template".
version: "1.0"
user-invocable: true
context: fork
model: sonnet
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
argument-hint: "[options] -- --input, --output"
---

## Runtime Configuration (Step 0)
Read: specs/tfl-templates.yaml

## EXECUTE NOW
Parse $ARGUMENTS: --input, --output, --spec, --validate, --dry-run
**START NOW.**

---

## Philosophy
**Templates standardize output generation. Header/footer macros, statistical formatting, and pagination logic are encapsulated.**

---

## Script Execution
```bash
python csp-skills/layer-5-tfl/tfl-template-builder/script.py --input <input_path> --output <output_path>
```

---

## Key Variables

| Variable | Description |
|----------|-------------|
| TEMPLATE_ID | Template identifier |
| TYPE | Table/Listing/Figure |
| FORMAT | Template format |

---

## Evaluation Criteria
**Mandatory:**
- All SAP-specified TFLs have shells
- Headers/footnotes match SAP specifications

**Recommended:**
- Pagination strategy defined

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
