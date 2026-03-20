---
name: sdtm-dm-mapper
description: Map raw demographics data to SDTM DM domain per CDISC SDTM IG v3.4. Triggers on "DM", "demographics", "USUBJID", "AGE", "SEX", "RACE".
version: "1.0"
user-invocable: true
context: fork
model: sonnet
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
argument-hint: "[options] — --input, --output, --spec"
---

## Runtime Configuration (Step 0)

Read: specs/sdtm-mapping-spec.yaml, specs/study-config.yaml, data/raw/dm.csv

## EXECUTE NOW

Parse $ARGUMENTS: --input, --output, --spec, --validate, --dry-run

**START NOW.**

---

## Philosophy

**DM is the anchor domain.** Every subject in a clinical trial must have exactly one DM record. USUBJID uniquely identifies subjects across all domains. Treatment arm, study reference dates, and demographic characteristics flow from DM to all downstream analyses.

---

## Script Execution

```bash
python csp-skills/layer-2-sdtm/sdtm-dm-mapper/script.py --input data/raw/dm.csv --output output/sdtm/dm.xpt --spec specs/sdtm-mapping-spec.yaml
```

---

## Key Variables

| Variable | Required | Source | Derivation |
|----------|----------|--------|------------|
| STUDYID | Yes | RAW.DM | Study identifier |
| DOMAIN | Yes | - | "DM" |
| USUBJID | Yes | RAW.DM | Concatenate STUDYID-SITEID-SUBJID |
| SUBJID | Yes | RAW.DM | Subject identifier |
| SITEID | Yes | RAW.DM | Site identifier |
| AGE | Yes | RAW.DM | Age in years |
| AGEU | Yes | - | "YEARS" |
| SEX | Yes | RAW.DM | Map to CDISC CT C66731 |
| RACE | Yes | RAW.DM | Map to CDISC CT C74457 |
| ETHNIC | No | RAW.DM | Map to CDISC CT C66790 |
| ARM | Yes | RAW.DM | Assigned treatment arm |
| ARMCD | Yes | RAW.DM | 8-character arm code |
| ACTARM | No | RAW.DM | Actual treatment arm |
| ACTARMCD | No | RAW.DM | Actual arm code |
| RFSTDTC | No | EX | First exposure date |
| RFENDTC | No | EX | Last exposure date |
| COUNTRY | Yes | RAW.DM | ISO 3166-1 alpha-3 |

---

## Evaluation Criteria

**Mandatory:**
- All required DM variables present per SDTM IG
- USUBJID uniquely identifies each subject
- Controlled terminology matches CDISC CT

**Recommended:**
- P21 validation returns 0 warnings
- All subjects have ARM populated

---

## Critical Constraints

**Never:**
- Create duplicate USUBJIDs
- Allow missing STUDYID, DOMAIN, USUBJID
- Use non-CDISC controlled terminology

**Always:**
- Validate controlled terminology before output
- Check for orphan subjects (no matching records in EX)
- Document any mapped values that differ from source
