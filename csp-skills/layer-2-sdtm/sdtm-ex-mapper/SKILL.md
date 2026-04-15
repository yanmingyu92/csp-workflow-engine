---
name: sdtm-ex-mapper
description: Map exposure/dosing data to SDTM EX domain with dose calculations. Triggers on "EX", "exposure", "dosing", "EXTRT", "EXDOSE".
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
- `--input <raw-data-file>` (raw exposure/dosing source)

## EXECUTE NOW

Parse $ARGUMENTS: --input, --output, --spec, --study-config, --validate, --dry-run
**START NOW.**

---

## Philosophy
**EX tracks all treatment exposure.** Every dose administered must be captured with exact timing, route, and amount to support pharmacokinetic and efficacy analyses.

---

## Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `--input` | Yes | Path to raw exposure/dosing data file |
| `--output` | Yes | Output path for EX XPT file |
| `--spec` | Yes | Path to SDTM mapping specification YAML |
| `--study-config` | No | Path to study config (defaults to ops/workflow-state.yaml) |
| `--validate` | No | Run validation after mapping |
| `--dry-run` | No | Show mappings without writing |

---

## Key Variables

| Variable | Required | Source | Derivation |
|----------|----------|--------|------------|
| STUDYID | Yes | study config | `{{study_id}}` from study config |
| DOMAIN | Yes | - | Fixed value: "EX" |
| USUBJID | Yes | Derived | Format: `{{study_id}}-{SITEID}-{SUBJID}` |
| EXTRT | Yes | study config | Treatment name from `study_config['treatment_arms']` |
| EXDOSE | Yes | RAW.EX | Dose amount |
| EXDOSU | Yes | spec | Dose units (dynamic from mapping spec) |
| EXROUTE | Yes | spec | Route of administration (dynamic from mapping spec) |
| EXSTDTC | Yes | RAW.EX | Start date/time (ISO 8601) |
| EXENDTC | No | RAW.EX | End date/time (ISO 8601) |

---

## Dose Calculations
- Cumulative dose over study
- Relative day from first dose
- Dose intensity calculations

---

## Evaluation Criteria
**Mandatory:**
- All dosing records with valid EXTRT, EXDOSE, EXSTDTC
- EXTRT matches treatment arms from study config
- USUBJID matches DM domain

**Recommended:**
- Dose intensity derived for efficacy correlation

---

## Critical Constraints
**Never:**
- Produce output without validation
- Skip required variables
- Hardcode treatment names (read from study config)
- Proceed if study config is missing (raise error and abort)

**Always:**
- Resolve study config from `ops/workflow-state.yaml` or `--study-config`
- Read treatment names dynamically from study config
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
