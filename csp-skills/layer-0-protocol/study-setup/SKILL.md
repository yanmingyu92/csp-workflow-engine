---
name: study-setup
description: Configure study-level metadata including study ID, phase, treatment arms, visit schedule, and randomization. Triggers on "study setup", "protocol", "study ID", "treatment arms", "visit schedule".
version: "1.0"
user-invocable: true
context: fork
model: sonnet
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
argument-hint: "[options] — --input, --output, --validate"
---

## Runtime Configuration (Step 0)

Read: ops/workflow-state.yaml, specs/study-config.yaml

## EXECUTE NOW

Parse $ARGUMENTS: --input, --output, --validate, --dry-run

**START NOW.**

---

## Philosophy

**Study configuration is the foundation.** All downstream work depends on accurate study metadata: treatment arms, visit windows, and population definitions flow from this configuration to SDTM, ADaM, and TFL.

---

## Script Execution

```bash
python csp-skills/layer-0-protocol/study-setup/script.py --input <protocol-file> --output specs/study-config.yaml
```

---

## Evaluation Criteria

**Mandatory:**
- Study ID and phase correctly set
- Treatment arms and visit schedule defined

**Recommended:**
- Randomization scheme documented
- Stratification factors captured

---

## Critical Constraints

**Never:**
- Proceed without a study ID
- Create treatment arms not in protocol

**Always:**
- Document source of each configuration element
- Include page references for audit trail
