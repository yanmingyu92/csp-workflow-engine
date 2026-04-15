---
name: sdtm-ds-mapper
description: Map disposition data to SDTM DS domain for subject status tracking. Triggers on "DS", "disposition", "DSTERM", "EOSSTT".
version: "1.0"
user-invocable: true
context: fork
model: sonnet
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
argument-hint: "[options] -- --input <raw-data-file> --output <output-path> --spec <mapping-spec>"
---

## Runtime Configuration (Step 0)

### Study Config Resolution
```
1. Read ops/workflow-state.yaml for treatment arm definitions and study metadata
2. If missing, fall back to --study-config <path> from kwargs
3. If neither available, raise error: "Missing study config: abort; return {}"
4. Default: --study-config default
```

### Files to Read
- `ops/workflow-state.yaml` (study config, treatment arms)
- `--spec <mapping-spec>` (SDTM mapping specification)
- `--input <raw-data-file>` (raw disposition source)

## EXECUTE NOW

Parse $ARGUMENTS: --input, --output, --spec, --study-config, --validate, --dry-run
**START NOW.**

---

## Philosophy
**DS tracks every subject journey.** From randomization to completion or discontinuation, disposition records form the audit trail for study conduct and primary analysis populations.

---

## Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `--input` | Yes | Path to raw disposition data file |
| `--output` | Yes | Output path for DS XPT file |
| `--spec` | Yes | Path to SDTM mapping specification YAML |
| `--study-config` | No | Path to study config (defaults to ops/workflow-state.yaml) |
| `--validate` | No | Run validation after mapping |
| `--dry-run` | No | Show mappings without writing |

---

## Key Variables

| Variable | Required | Source | Derivation |
|----------|----------|--------|------------|
| STUDYID | Yes | study config | `{{study_id}}` from study config |
| DOMAIN | Yes | - | Fixed value: "DS" |
| USUBJID | Yes | Derived | Format: `{{study_id}}-{SITEID}-{SUBJID}` |
| DSDECOD | Yes | spec | Standardized term (dynamic from mapping spec) |
| DSTERM | Yes | RAW.DS | Verbatim term |
| DSCAT | Yes | - | Category (DISPOSITION) |
| DSSCAT | No | spec | Subcategory (dynamic from mapping spec) |
| DSSTDTC | Yes | RAW.DS | Date of event (ISO 8601) |

---

## Standard Disposition Terms
Disposition terms are loaded dynamically from `--spec <mapping-spec>`. Common standard terms include:
- COMPLETED
- DISCONTINUED
- SCREEN FAILURE
- ADVERSE EVENT
- WITHDRAWAL BY SUBJECT
- PROTOCOL VIOLATION

Terms must be validated against the mapping spec and CDISC controlled terminology at runtime.

---

## Evaluation Criteria
**Mandatory:**
- All subjects with disposition record
- USUBJID matches DM domain
- Disposition terms validated against mapping spec

**Recommended:**
- Primary reason for discontinuation captured
- Dates in ISO 8601 format

---

## Critical Constraints
**Never:**
- Produce output without validation
- Skip required variables
- Ignore CDISC controlled terminology
- Hardcode disposition terms
- Proceed if study config is missing (raise error and abort)

**Always:**
- Resolve study config from `ops/workflow-state.yaml` or `--study-config`
- Load disposition terms dynamically from mapping spec
- Validate all inputs before processing
- Document any deviations from standards
- Generate traceable, reproducible results

---

## Examples

### Basic Usage
```bash
--input <raw-data-file> --output <output-path> --spec <mapping-spec>
```

### With Explicit Study Config
```bash
--input <raw-data-file> --output <output-path> --spec <mapping-spec> --study-config ops/workflow-state.yaml
```
