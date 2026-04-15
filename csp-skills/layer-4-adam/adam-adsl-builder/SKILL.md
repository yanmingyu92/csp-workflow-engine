---
name: adsl-builder
description: Build ADSL subject-level dataset with all derived variables. Triggers on "ADSL", "subject level", "population flags".
version: "2.0"
user-invocable: true
context: fork
model: sonnet
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
argument-hint: "[options] -- --input-dir, --output"
---

## EXECUTE NOW
Parse $ARGUMENTS: --input-dir, --output, --spec, --validate, --dry-run

**Principle:** ADSL = 1 record per subject. Foundation for all ADaM analyses.

**Inputs:** SDTM DM, EX, DS, SV domains (xpt), study-config.yaml
**Output:** ADSL dataset (xpt)

## Script
```bash
adam-adsl-builder --input-dir {input-dir} --output {output} [--spec {spec}] [--validate] [--dry-run]
```

---

## Key Variables

| Variable | Source | Derivation |
|----------|--------|------------|
| STUDYID | DM | From study config |
| USUBJID | DM | {study_id}-{SITEID}-{SUBJID} |
| TRT01P | DM.ARM | Planned treatment |
| TRT01A | DM.ACTARM/ARM | Actual treatment |
| TRTSDT | EX | First dose date (min EXSTDTC where EXDOSE>0) |
| TRTEDT | EX | Last dose date (max EXENDTC where EXDOSE>0) |
| TRTSDBJ | Derived | Always 1 for randomized |
| TRTEDJ | Derived | (TRTEDT-TRTSDT).days + 1 |
| SAFFL | Derived | Y if ARMCD != screen_failure_code AND EXDOSE>0 |
| ITTFL | Derived | Y if ARMCD != screen_failure_code |
| PPROTFL | Derived | Y if ITTFL=Y AND COMPLTFL=Y AND no major deviations |
| COMPLTFL | DS | Y if DSTERM contains Completed |
| DISCONFL | Derived | Y if COMPLTFL=N AND not screen failure |
| AGEGR1 | Derived | AGE < cutoff -> <cutoff, else >=cutoff |
| DTHFL | DS | Y if DSTERM contains Death |

---

## Population Flag Derivation

```python
screen_code = study_config.get("screen_failure_code", "Scrnfail")
SAFFL = "Y" if DM.ARMCD != screen_code and any(EX.EXDOSE > 0) else "N"
ITTFL = "Y" if DM.ARMCD != screen_code else "N"
PPROTFL = "Y" if ITTFL == "Y" and COMPLTFL == "Y" and no_major_deviations else "N"
```

---

## Merge Logic

```python
def build_adsl(sdtm_dir, study_config):
    dm = read_xpt(f"{sdtm_dir}/dm.xpt")
    assert dm["USUBJID"].is_unique, "DM must have 1 record per subject"
    ex = read_xpt(f"{sdtm_dir}/ex.xpt")
    trt_dates = ex.groupby("USUBJID").agg(TRTSDT=("EXSTDTC", "min"), TRTEDT=("EXENDTC", "max")).reset_index()
    adsl = dm.merge(trt_dates, on="USUBJID", how="left")
    ds = read_xpt(f"{sdtm_dir}/ds.xpt")
    adsl = derive_population_flags(adsl, ex, ds, study_config)
    assert adsl["USUBJID"].is_unique and len(adsl) == len(dm)
    return adsl
```

---

## Edge Cases

| Scenario | Action |
|----------|--------|
| Screen failure | SAFFL=N, ITTFL=N, no TRTSDT/TRTEDT |
| Randomized but never dosed | SAFFL=N, ITTFL=Y, TRTSDT=null |
| Cross-over study | TRT01P/TRT01A for period 01; may need TRT02P/TRT02A |
| Partial EXSTDTC | Impute start=01, end=last day of month |
| EX subject not in DM | Flag error, do NOT add to ADSL |
| ARM != ACTARM | Preserve both in TRT01P, TRT01A; document |

---

## Integration

**Up:** /sdtm-dm-mapper, /sdtm-ex-mapper, /sdtm-ds-mapper, /study-setup, /sap-parser
**Down:** /adam-adae-builder, /adam-adeff-builder, /adam-adtte-builder, /adam-validator, /tfl-demographics
**Related:** /adam-traceability-checker, /define-draft-builder, /adrg-writer

---

## Constraints

**Never:** Create >1 record per subject, Drop subjects from DM, Set SAFFL=Y without EX records, Hardcode treatment arms
**Always:** Start with DM as backbone, Left-join other domains, Validate 1:1 subject constraint, Resolve params from study_config
