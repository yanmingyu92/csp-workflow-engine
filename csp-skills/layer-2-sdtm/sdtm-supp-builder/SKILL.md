---
name: sdtm-supp-builder
description: Create SUPPXX datasets for non-standard variables. Triggers on "SUPP", "supplemental", "QNAM", "non-standard variable".
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
- `--spec <mapping-spec>` (SDTM mapping specification with SUPP qualifiers)
- `--input <sdtm-dir>` (SDTM domain XPT files)

## EXECUTE NOW

Parse $ARGUMENTS: --input, --output, --spec, --study-config, --validate, --dry-run
**START NOW.**

---

## Philosophy
**SUPPXX captures non-standard qualifiers.** When variables don't fit standard domain structure, SUPPXX provides a compliant way to include them while maintaining referential integrity.

---

## Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `--input` | Yes | Path to SDTM directory containing XPT files |
| `--output` | Yes | Output path for SUPP directory |
| `--spec` | Yes | Path to SDTM mapping specification YAML |
| `--study-config` | No | Path to study config (defaults to ops/workflow-state.yaml) |
| `--validate` | No | Run validation after building |
| `--dry-run` | No | Show qualifiers without writing |

---

## Key Variables

| Variable | Required | Source | Derivation |
|----------|----------|--------|------------|
| STUDYID | Yes | study config | `{{study_id}}` from study config |
| RDOMAIN | Yes | spec | Parent domain (dynamic from mapping spec) |
| USUBJID | Yes | Derived | Format: `{{study_id}}-{SITEID}-{SUBJID}` |
| IDVAR | Yes | spec | ID variable (e.g., AESEQ) |
| IDVARVAL | Yes | Derived | ID variable value |
| QNAM | Yes | spec | Qualifier name (dynamic from mapping spec) |
| QLABEL | Yes | spec | Qualifier label (dynamic from mapping spec) |
| QVAL | Yes | Derived | Qualifier value |

---

## Common Use Cases
- Ethnicity details (SUPPDM)
- Cancer staging (SUPPDM)
- Prior medication details (SUPPCM)
- Custom visit flags

---

## Naming Convention
- QNAM: UPPERCASE, max 8 characters
- Must start with letter
- No special characters
- Defined in `--spec <mapping-spec>`, not hardcoded

---

## Evaluation Criteria
**Mandatory:**
- Valid QNAM/QLABEL pairs
- Referential integrity with parent domain
- USUBJID matches DM domain

**Recommended:**
- Controlled terminology for QVAL where applicable

---

## Critical Constraints
**Never:**
- Produce output without validation
- Hardcode QNAM/QLABEL pairs (read from spec)
- Proceed if study config is missing (raise error and abort)

**Always:**
- Resolve study config from `ops/workflow-state.yaml` or `--study-config`
- Load supplemental qualifier definitions from mapping spec
- Validate referential integrity
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
