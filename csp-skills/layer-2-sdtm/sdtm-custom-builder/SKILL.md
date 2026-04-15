---
name: sdtm-custom-builder
description: Build custom SDTM domains (FA, QS, biomarkers). Triggers on "custom domain", "non-standard domain", "FA", "QS", "biomarker", "questionnaire".
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
- `--input <raw-data-file>` (raw custom domain source)

## EXECUTE NOW

Parse $ARGUMENTS: --input, --output, --spec, --study-config, --validate, --dry-run
**START NOW.**

---

## Philosophy
**Custom domains follow Findings About (FA) or general observation class structure. Two-character domain code required.**

---

## Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `--input` | Yes | Path to raw custom domain data file |
| `--output` | Yes | Output path for custom domain XPT file |
| `--spec` | Yes | Path to SDTM mapping specification YAML |
| `--study-config` | No | Path to study config (defaults to ops/workflow-state.yaml) |
| `--validate` | No | Run validation after mapping |
| `--dry-run` | No | Show mappings without writing |

---

## Key Variables

| Variable | Required | Source | Derivation |
|----------|----------|--------|------------|
| STUDYID | Yes | study config | `{{study_id}}` from study config |
| DOMAIN | Yes | - | Custom domain code (2 chars) |
| USUBJID | Yes | Derived | Format: `{{study_id}}-{SITEID}-{SUBJID}` |
| TESTCD | Yes | spec | Test code |
| ORRES | Yes | RAW | Original result |

---

## Evaluation Criteria
**Mandatory:**
- Domain code follows CDISC two-character naming convention
- Dataset-level metadata documented
- USUBJID matches DM domain

**Recommended:**
- Justification written for custom domain necessity

---

## Critical Constraints
**Never:**
- Produce output without validation
- Skip required variables
- Ignore CDISC controlled terminology
- Proceed if study config is missing (raise error and abort)

**Always:**
- Resolve study config from `ops/workflow-state.yaml` or `--study-config`
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
