---
name: spec-builder
description: Create or review mapping specifications for SDTM, ADaM, and TFL. Triggers on "mapping specification", "SDTM spec", "ADaM spec", "TFL spec", "derivation spec".
version: "1.0"
user-invocable: true
context: fork
model: sonnet
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
argument-hint: "[options] — --input, --output, --type, --validate"
---

## Runtime Configuration (Step 0)

Read: ops/workflow-state.yaml, specs/sap-parsed.yaml, specs/study-config.yaml

## EXECUTE NOW

Parse $ARGUMENTS: --input, --output, --type, --validate, --dry-run

**START NOW.**

---

## Philosophy

**Specifications drive all downstream work.** The mapping spec defines how raw data becomes SDTM, the derivation spec defines how SDTM becomes ADaM, and TFL shells define how ADaM becomes tables and figures.

---

## Script Execution

```bash
python csp-skills/layer-0-protocol/spec-builder/script.py --type sdtm --input specs/sap-parsed.yaml --output specs/sdtm-mapping-spec.yaml
```

---

## Specification Types

| Type | Output | Description |
|------|--------|-------------|
| sdtm | sdtm-mapping-spec.yaml | SDTM domain mapping specifications |
| adam | adam-derivation-spec.yaml | ADaM dataset derivation specifications |
| tfl | tfl-shells.yaml | TFL shell specifications |

---

## Evaluation Criteria

**Mandatory:**
- SDTM mapping spec covers all collected CRF variables
- ADaM spec covers all SAP endpoints
- TFL shells match SAP appendix

**Recommended:**
- Specs reviewed and signed off
- Variable naming follows CDISC conventions

---

## Critical Constraints

**Never:**
- Create specs without SAP reference
- Skip required CDISC variables
- Use non-standard naming conventions

**Always:**
- Reference SAP endpoints for ADaM specs
- Include controlled terminology requirements
- Document derivation logic
