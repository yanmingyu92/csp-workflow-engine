---
name: sdtm-vs-mapper
description: Map vital signs to SDTM VS domain. Triggers on "VS", "vital signs", "vitals", "VS domain", "blood pressure", "heart rate".
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
- `--input <raw-data-file>` (raw vital signs source)

## EXECUTE NOW

Parse $ARGUMENTS: --input, --output, --spec, --study-config, --validate, --dry-run
**START NOW.**

---

## Philosophy
**Vital signs require careful unit standardization. Position (VSPOS) and timing relative to dose are critical for analysis.**

---

## Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `--input` | Yes | Path to raw vital signs data file |
| `--output` | Yes | Output path for VS XPT file |
| `--spec` | Yes | Path to SDTM mapping specification YAML |
| `--study-config` | No | Path to study config (defaults to ops/workflow-state.yaml) |
| `--validate` | No | Run validation after mapping |
| `--dry-run` | No | Show mappings without writing |

---

## Key Variables

| Variable | Required | Source | Derivation |
|----------|----------|--------|------------|
| STUDYID | Yes | study config | `{{study_id}}` from study config |
| DOMAIN | Yes | - | Fixed value: "VS" |
| USUBJID | Yes | Derived | Format: `{{study_id}}-{SITEID}-{SUBJID}` |
| VSTEST | Yes | spec | Vital sign test (dynamic from mapping spec) |
| VSTESTCD | Yes | spec | Test code (dynamic from mapping spec) |
| VSSTRESN | Yes | Derived | Standard result |
| VSSTRESU | Yes | spec | Standard units (dynamic from mapping spec) |
| VSPOS | No | spec | Position (dynamic from mapping spec) |

---

## Evaluation Criteria
**Mandatory:**
- VSTESTCD matches CDISC controlled terminology
- Standard units derived
- USUBJID matches DM domain

**Recommended:**
- Position (VSPOS) captured where applicable

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
