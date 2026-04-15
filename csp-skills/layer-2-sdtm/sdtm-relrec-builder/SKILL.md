---
name: sdtm-relrec-builder
description: Build RELREC dataset for cross-domain record relationships. Triggers on "RELREC", "related records", "cross-domain relationship", "relationship", "relrec.xpt", "record linkage".
version: "1.0"
user-invocable: true
context: fork
model: sonnet
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
argument-hint: "[options] -- --input <sdtm-dir> --output <output-path> --spec <mapping-spec>"
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
- `--input <sdtm-dir>` (SDTM domain XPT files to build relationships from)

## EXECUTE NOW

Parse $ARGUMENTS: --input, --output, --spec, --study-config, --validate, --dry-run
**START NOW.**

---

## Philosophy
**RELREC documents relationships between records across domains. Critical for regulatory review of linked data.**

---

## Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `--input` | Yes | Path to SDTM directory containing XPT files |
| `--output` | Yes | Output path for RELREC XPT file |
| `--spec` | Yes | Path to SDTM mapping specification YAML |
| `--study-config` | No | Path to study config (defaults to ops/workflow-state.yaml) |
| `--validate` | No | Run validation after building |
| `--dry-run` | No | Show relationships without writing |

---

## Key Variables

| Variable | Required | Source | Derivation |
|----------|----------|--------|------------|
| STUDYID | Yes | study config | `{{study_id}}` from study config |
| RDOMAIN | Yes | spec | Related domain (dynamic from mapping spec) |
| IDVAR | Yes | spec | ID variable (dynamic from mapping spec) |
| IDVARVAL | Yes | Derived | ID value |
| RELTYPE | No | spec | Relationship type (dynamic from mapping spec) |
| RELID | Yes | Derived | Relationship identifier |

---

## Evaluation Criteria
**Mandatory:**
- All cross-domain relationships documented
- USUBJID matches DM domain

**Recommended:**
- Relationship types correctly classified

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
--input <sdtm-dir> --output <output-path> --spec <mapping-spec>
```

### With Explicit Study Config
```bash
--input <sdtm-dir> --output <output-path> --spec <mapping-spec> --study-config ops/workflow-state.yaml
```
