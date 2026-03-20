---
name: tfl-listing-generator
description: Generate patient data listings. Triggers on "listing", "data listing", "patient listing", "AE listing", "lab listing", "protocol deviation listing".
version: "1.0"
user-invocable: true
context: fork
model: sonnet
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
argument-hint: "[options] -- --input, --output"
---

## Runtime Configuration (Step 0)
Read: output/tfl/listings/

## EXECUTE NOW
Parse $ARGUMENTS: --input, --output, --spec, --validate, --dry-run
**START NOW.**

---

## Philosophy
**Listings present subject-level detail. Sort order, pagination, and date formatting are critical for reviewer usability.**

---

## Script Execution
```bash
python csp-skills/layer-5-tfl/tfl-listing-generator/script.py --input <input_path> --output <output_path>
```

---

## Key Variables

| Variable | Description |
|----------|-------------|
| LISTING_ID | Listing identifier |
| TITLE | Listing title |
| SORT_ORDER | Sort variables |

---

## Evaluation Criteria
**Mandatory:**
- All SAP-mandated listings produced
- Subject-level data accurate

**Recommended:**
- Listings sorted per protocol

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
