---
name: sdtm-relrec-builder
description: Build RELREC dataset for cross-domain record relationships. Triggers on "RELREC", "related records", "cross-domain relationship", "relationship", "relrec.xpt", "record linkage".
version: "1.0"
user-invocable: true
context: fork
model: sonnet
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
argument-hint: "[options] -- --input, --output"
---

## Runtime Configuration (Step 0)
Read: output/sdtm/relrec.xpt

## EXECUTE NOW
Parse $ARGUMENTS: --input, --output, --spec, --validate, --dry-run
**START NOW.**

---

## Philosophy
**RELREC documents relationships between records across domains. Critical for regulatory review of linked data.**

---

## Script Execution
```bash
python csp-skills/layer-2-sdtm/sdtm-relrec-builder/script.py --input <input_path> --output <output_path>
```

---

## Key Variables

| Variable | Description |
|----------|-------------|
| RDOMAIN | Related domain |
| IDVAR | ID variable |
| IDVARVAL | ID value |

---

## Evaluation Criteria
**Mandatory:**
- All cross-domain relationships documented

**Recommended:**
- Relationship types correctly classified

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
