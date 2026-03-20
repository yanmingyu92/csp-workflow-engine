---
name: data-extract
description: Extract raw clinical data from EDC system or data repository. Triggers on "EDC", "data extraction", "raw data", "data cut", "extract data".
version: "1.0"
user-invocable: true
context: fork
model: sonnet
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
argument-hint: "[options] — --input, --output, --format"
---

## Runtime Configuration (Step 0)

Read: specs/study-config.yaml, ops/workflow-state.yaml

## EXECUTE NOW

Parse $ARGUMENTS: --input, --output, --format, --dry-run

**START NOW.**

---

## Philosophy

**Data extraction is the gateway to analysis.** Raw data from EDC systems must be extracted, documented, and validated before any mapping or derivation can begin. The extraction manifest provides traceability for regulatory submissions.

---

## Script Execution

```bash
python csp-skills/layer-1-raw-data/data-extract/script.py --input <edc-path> --output data/raw/
```

---

## Outputs

| Output | Path | Description |
|--------|------|-------------|
| Raw datasets | data/raw/ | One file per CRF form/domain |
| Extraction manifest | data/raw/extraction-manifest.yaml | Timestamp, data cut, row counts |

---

## Evaluation Criteria

**Mandatory:**
- All CRF forms extracted
- Extraction manifest documents data cut date
- Row counts verified against EDC

**Recommended:**
- Data exported in both CSV and SAS7BDAT formats
- Include EDC audit trail

---

## Critical Constraints

**Never:**
- Modify source data during extraction
- Skip extraction manifest creation
- Proceed without documenting data cut criteria
