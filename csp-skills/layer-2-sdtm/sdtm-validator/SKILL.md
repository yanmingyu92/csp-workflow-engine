---
name: sdtm-validator
description: Validate SDTM domain datasets against CDISC standards and P21 rules. Triggers on "SDTM validation", "validate SDTM", "P21", "compliance".
version: "1.0"
user-invocable: true
context: fork
model: sonnet
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
argument-hint: "[options] -- --input <sdtm-dir> --output <report-path> --spec <mapping-spec>"
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
- `--input <sdtm-dir>` (SDTM domain XPT files to validate)

## EXECUTE NOW

Parse $ARGUMENTS: --input, --output, --spec, --study-config, --domain, --strict

**START NOW.**

---

## Philosophy

**Validation catches errors before they compound.** SDTM validation checks domain structure, controlled terminology, cross-domain consistency, and P21 conformance rules. Early validation prevents downstream issues in ADaM and TFL generation.

---

## Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `--input` | Yes | Path to SDTM directory containing XPT files |
| `--output` | Yes | Output path for validation report |
| `--spec` | No | Path to SDTM mapping specification YAML |
| `--study-config` | No | Path to study config (defaults to ops/workflow-state.yaml) |
| `--domain` | No | Specific domain to validate (e.g., DM, AE) |
| `--strict` | No | Treat warnings as errors |

---

## Validation Categories

| Category | Severity | Examples |
|----------|----------|----------|
| Structure | Error | Missing required variables, duplicate keys |
| Terminology | Error | Invalid CT values |
| Consistency | Error | USUBJID not in DM |
| Format | Warning | Date format issues, length warnings |

---

## Evaluation Criteria

**Mandatory:**
- All required variables present
- USUBJID uniquely identifies subjects
- Controlled terminology valid
- Treatment arms match study config

**Recommended:**
- Zero P21 errors
- Zero P21 warnings

---

## Critical Constraints
**Never:**
- Skip validation steps
- Ignore P21 findings
- Use hardcoded study-specific validation rules
- Proceed if study config is missing (raise error and abort)

**Always:**
- Resolve study config from `ops/workflow-state.yaml` or `--study-config`
- Validate treatment arms against study config dynamically
- Validate USUBJID format against study config
- Generate traceable, reproducible results

---

## Examples

### Basic Usage
```bash
--input <sdtm-dir> --output <report-path> --spec <mapping-spec>
```

### Domain-Specific Validation
```bash
--input <sdtm-dir> --output <report-path> --spec <mapping-spec> --domain DM
```

### With Explicit Study Config
```bash
--input <sdtm-dir> --output <report-path> --spec <mapping-spec> --study-config ops/workflow-state.yaml
```
