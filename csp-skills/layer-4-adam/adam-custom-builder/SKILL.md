---
name: adam-custom-builder
description: Build custom ADaM datasets (PK, QoL, PRO). Triggers on "custom ADaM", "PK", "pharmacokinetics", "QoL", "quality of life", "PRO".
version: "1.0"
user-invocable: true
context: fork
model: sonnet
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
argument-hint: "[options] -- --input, --output"
---

## Runtime Configuration (Step 0)
Read: output/adam/

## EXECUTE NOW
Parse $ARGUMENTS: --input, --output, --spec, --validate, --dry-run
**START NOW.**

---

## Philosophy
**Custom ADaM datasets must follow fundamental principles: traceability to SDTM, clear variable derivation, analysis-readiness.**

---

## Script Execution
```bash
python csp-skills/layer-4-adam/adam-custom-builder/script.py --input <input_path> --output <output_path>
```

---

## Key Variables

| Variable | Description |
|----------|-------------|
| PARAMCD | Parameter code |
| AVAL | Analysis value |
| DTYPE | Derivation type |

---

## Evaluation Criteria
**Mandatory:**
- Dataset follows ADaM fundamental principles
- Traceability to SDTM maintained

**Recommended:**
- Derivation logic documented in metadata

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
