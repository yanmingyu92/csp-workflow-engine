---
name: spec-reviewer
description: Review and validate mapping specifications. Triggers on "mapping specification", "SDTM spec", "ADaM spec", "TFL spec", "derivation spec", "specification".
version: "1.0"
user-invocable: true
context: fork
model: sonnet
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
argument-hint: "[options] -- --input, --output"
---

## Runtime Configuration (Step 0)
Read: specs/sdtm-mapping-spec.xlsx, specs/adam-derivation-spec.xlsx, specs/tfl-shells.xlsx

## EXECUTE NOW
Parse $ARGUMENTS: --input, --output, --spec, --validate, --dry-run
**START NOW.**

---

## Philosophy
**Spec review catches ambiguities and gaps before programming begins. Coverage and completeness checks are essential.**

---

## Script Execution
```bash
python csp-skills/layer-0-protocol/spec-reviewer/script.py --input <input_path> --output <output_path>
```

---

## Key Variables

| Variable | Description |
|----------|-------------|
| SPEC_SECTION | Specification section |
| STATUS | Approved/Needs Review |
| COMMENTS | Review comments |

---

## Evaluation Criteria
**Mandatory:**
- SDTM mapping spec covers all collected CRF variables
- ADaM spec covers all SAP endpoints
- TFL shells match SAP appendix

**Recommended:**
- Specs reviewed and signed off

---

## Critical Constraints
**Never:**
- Produce output without validation
- Skip required variables
- Ignore CDISC controlled terminology

**Always:**
- Validate all inputs before processing
- Document any deviations from standards
- Generate traceable, reproducible results
