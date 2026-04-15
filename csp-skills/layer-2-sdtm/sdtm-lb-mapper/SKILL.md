---
name: sdtm-lb-mapper
description: Map laboratory data to SDTM LB domain. Triggers on "LB", "lab", "laboratory", "lab data", "LB domain", "LBTEST".
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
- `--input <raw-data-file>` (raw laboratory source)

## EXECUTE NOW

Parse $ARGUMENTS: --input, --output, --spec, --study-config, --validate, --dry-run
**START NOW.**

---

## Philosophy
**LB domain handles unit conversions and reference ranges. Standard units (LBSTRESU) must be derived with proper conversion factors.**

---

## Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `--input` | Yes | Path to raw laboratory data file |
| `--output` | Yes | Output path for LB XPT file |
| `--spec` | Yes | Path to SDTM mapping specification YAML |
| `--study-config` | No | Path to study config (defaults to ops/workflow-state.yaml) |
| `--validate` | No | Run validation after mapping |
| `--dry-run` | No | Show mappings without writing |

---

## Key Variables

| Variable | Required | Source | Derivation |
|----------|----------|--------|------------|
| STUDYID | Yes | study config | `{{study_id}}` from study config |
| DOMAIN | Yes | - | Fixed value: "LB" |
| USUBJID | Yes | Derived | Format: `{{study_id}}-{SITEID}-{SUBJID}` |
| LBTEST | Yes | spec | Lab test name (dynamic from mapping spec) |
| LBTESTCD | Yes | spec | Lab test code (dynamic from mapping spec) |
| LBSTRESN | Yes | Derived | Standard result numeric |
| LBSTRESU | Yes | spec | Standard result units (dynamic from mapping spec) |
| LBNRIND | No | Derived | Normal range indicator |
| LBORNRLO | No | spec | Reference range lower limit |
| LBORNRHI | No | spec | Reference range upper limit |

---

## Evaluation Criteria
**Mandatory:**
- Standard units (LBSTRESU) derived with conversion factors
- Reference ranges (LBORNRLO, LBORNRHI) populated
- LBTESTCD matches CDISC controlled terminology
- USUBJID matches DM domain

**Recommended:**
- LBNRIND derived from reference ranges

---

## Critical Constraints
**Never:**
- Produce output without validation
- Skip required variables
- Ignore CDISC controlled terminology
- Proceed if study config is missing (raise error and abort)

**Always:**
- Resolve study config from `ops/workflow-state.yaml` or `--study-config`
- Load test codes and units dynamically from mapping spec
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
