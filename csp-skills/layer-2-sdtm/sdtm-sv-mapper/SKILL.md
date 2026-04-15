---
name: sdtm-sv-mapper
description: Map subject visits to SDTM SV domain. Triggers on "SV", "subject visits", "visits", "SV domain", "VISIT", "VISITNUM".
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
- `--input <raw-data-file>` (raw subject visits source)

## EXECUTE NOW

Parse $ARGUMENTS: --input, --output, --spec, --study-config, --validate, --dry-run
**START NOW.**

---

## Philosophy
**SV domain documents actual visit dates. Essential for ADaM visit windowing and analysis timeline construction.**

---

## Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `--input` | Yes | Path to raw subject visits data file |
| `--output` | Yes | Output path for SV XPT file |
| `--spec` | Yes | Path to SDTM mapping specification YAML |
| `--study-config` | No | Path to study config (defaults to ops/workflow-state.yaml) |
| `--validate` | No | Run validation after mapping |
| `--dry-run` | No | Show mappings without writing |

---

## Key Variables

| Variable | Required | Source | Derivation |
|----------|----------|--------|------------|
| STUDYID | Yes | study config | `{{study_id}}` from study config |
| DOMAIN | Yes | - | Fixed value: "SV" |
| USUBJID | Yes | Derived | Format: `{{study_id}}-{SITEID}-{SUBJID}` |
| VISIT | Yes | spec | Visit name (dynamic from mapping spec) |
| VISITNUM | Yes | spec | Visit number (dynamic from mapping spec) |
| SVSTDTC | Yes | RAW.SV | Visit start date (ISO 8601) |
| SVENDTC | No | RAW.SV | Visit end date (ISO 8601) |

---

## Evaluation Criteria
**Mandatory:**
- All protocol visits captured
- VISITNUM in ascending order within subject
- SVSTDTC in ISO 8601 format
- USUBJID matches DM domain

**Recommended:**
- Unscheduled visits flagged appropriately

---

## Critical Constraints
**Never:**
- Produce output without validation
- Skip required variables
- Ignore CDISC controlled terminology
- Hardcode visit names (read from mapping spec)
- Proceed if study config is missing (raise error and abort)

**Always:**
- Resolve study config from `ops/workflow-state.yaml` or `--study-config`
- Load visit definitions dynamically from mapping spec
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
