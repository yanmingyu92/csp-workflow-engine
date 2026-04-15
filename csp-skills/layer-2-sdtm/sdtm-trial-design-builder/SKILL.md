---
name: sdtm-trial-design-builder
description: Create FDA-required trial design datasets (TS, TA, TI, TV). Triggers on "trial design", "TS", "TA", "TI", "TV".
version: "1.0"
user-invocable: true
context: fork
model: sonnet
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
argument-hint: "[options] -- --input <protocol-file> --output <output-dir> --spec <mapping-spec>"
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
- `ops/workflow-state.yaml` (study config, treatment arms, study metadata)
- `--spec <mapping-spec>` (SDTM mapping specification)
- `--input <protocol-file>` (protocol document source)

## EXECUTE NOW

Parse $ARGUMENTS: --input, --output, --spec, --study-config, --validate, --dry-run
**START NOW.**

---

## Philosophy
**Trial design datasets define study structure.** FDA requires TS, TA, TI, TV to understand the trial's arms, visits, elements, and inclusion criteria programmatically.

---

## Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `--input` | Yes | Path to protocol document file |
| `--output` | Yes | Output directory for trial design XPT files |
| `--spec` | Yes | Path to SDTM mapping specification YAML |
| `--study-config` | No | Path to study config (defaults to ops/workflow-state.yaml) |
| `--validate` | No | Run validation after building |
| `--dry-run` | No | Show datasets without writing |

---

## Trial Design Datasets

| Dataset | Purpose | Key Variables |
|---------|---------|---------------|
| TS | Trial Summary | TSPARM, TSVAL |
| TA | Trial Arms | ARM, ARMCD, TAETORD |
| TI | Trial Inclusion | IETEST, IECAT |
| TV | Trial Visits | VISIT, VISITNUM, VISTYP |

---

## Trial Summary Parameters (TS)
All parameters are resolved dynamically from study config (`ops/workflow-state.yaml`) and `--spec <mapping-spec>`:
- Title (TSPARMCD = TITLE) -- from `study_config['study_title']`
- Indication (TSPARMCD = INDIC) -- from study config
- Phase (TSPARMCD = PHASE) -- from study config
- Study Type (TSPARMCD = STUDYTYP) -- from study config
- Planned Enrollment (TSPARMCD = PLANSUB) -- from study config
- Study ID (TSPARMCD = STUDYID) -- `{{study_id}}` from study config

---

## Trial Arms (TA)
ARM and ARMCD values are read dynamically from `study_config['treatment_arms']` resolved via:
1. `ops/workflow-state.yaml` (preferred)
2. `--study-config <path>` (fallback)

No hardcoded treatment arm names.

---

## Evaluation Criteria
**Mandatory:**
- All four datasets present with required parameters
- Treatment arms match study config
- USUBJID format consistent with DM domain

**Recommended:**
- All CDISC core parameters included

---

## Critical Constraints
**Never:**
- Hardcode treatment arm names or study metadata
- Use hardcoded study IDs (read from study config)
- Proceed if study config is missing (raise error and abort)

**Always:**
- Resolve study config from `ops/workflow-state.yaml` or `--study-config`
- Read all study metadata dynamically
- Validate all inputs before processing
- Generate traceable, reproducible results

---

## Examples

### Basic Usage
```bash
--input <protocol-file> --output <output-dir> --spec <mapping-spec>
```

### With Explicit Study Config
```bash
--input <protocol-file> --output <output-dir> --spec <mapping-spec> --study-config ops/workflow-state.yaml
```
