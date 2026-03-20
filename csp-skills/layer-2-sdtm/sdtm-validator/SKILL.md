---
name: sdtm-validator
description: Validate SDTM domain datasets against CDISC standards and P21 rules. Triggers on "SDTM validation", "validate SDTM", "P21", "compliance".
version: "1.0"
user-invocable: true
context: fork
model: sonnet
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
argument-hint: "[options] — --input, --output, --domain"
---

## Runtime Configuration (Step 0)

Read: specs/sdtm-mapping-spec.yaml, ops/workflow-state.yaml

## EXECUTE NOW

Parse $ARGUMENTS: --input, --output, --domain, --strict

**START NOW.**

---

## Philosophy

**Validation catches errors before they compound.** SDTM validation checks domain structure, controlled terminology, cross-domain consistency, and P21 conformance rules. Early validation prevents downstream issues in ADaM and TFL generation.

---

## Script Execution

```bash
python csp-skills/layer-2-sdtm/sdtm-validator/script.py --input output/sdtm/ --output reports/sdtm-validation.yaml --domain DM
```

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

**Recommended:**
- Zero P21 errors
- Zero P21 warnings
