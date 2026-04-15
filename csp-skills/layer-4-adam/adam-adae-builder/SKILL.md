---
name: adae-builder
description: Build ADAE adverse events analysis dataset from SDTM AE
version: "2.0"
user-invocable: true
context: fork
model: sonnet
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
argument-hint: "[options] -- --input-dir, --output"
---

## EXECUTE NOW
Parse $ARGUMENTS: --input-dir, --output, --adsl, --spec, --validate, --dry-run

**Principle:** ADAE = 1:many with ADSL (one subject can have many AEs). Inherit treatment/population from ADSL.

**Inputs:** SDTM AE (xpt), ADSL (xpt), ADaM spec (yaml)
**Output:** ADAE dataset (xpt)

## Script
```bash
adam-adae-builder --input-dir {input-dir} --output {output} --adsl {adsl-path} [--spec {spec}] [--validate] [--dry-run]
```

## Key Variables
| Variable | Source | Description |
|----------|--------|-------------|
| USUBJID | AE/ADSL | Unique subject identifier |
| AEDECOD/AEBODSYS | AE | MedDRA PT / SOC |
| TRTA/TRTP | ADSL | Actual/Planned treatment |
| SAFFL | ADSL | Safety population flag |
| ASTDT/AENDT | Derived | Analysis start/end dates |
| TRTEMFL | Derived | Treatment-emergent flag |
| AOCCFL | Derived | First occurrence flag |
| ADURN | Derived | Duration in days |

---

## TRTEMFL Derivation

```python
def derive_trtemfl(astdt, trtsdt, trtedt, saffl, cfg):
    w = cfg.get('teae_window_days', 30)
    if saffl != 'Y': return 'N'
    if not astdt or not trtsdt: return ''
    if astdt < trtsdt: return 'N'
    if trtedt and astdt > trtedt + timedelta(days=w): return 'N'
    return 'Y'
```

**Edges:** Missing date -> '' (indeterminate); Partial -> impute 01; Pre-tx -> 'N' include; Same day -> 'Y'; Window from cfg only

---

## Date Derivations

```python
def derive_dates(aestdtc, aeendtc):
    if not aestdtc: astdt = None
    elif len(aestdtc) >= 10: astdt = parse(aestdtc[:10])
    elif len(aestdtc) == 7: astdt = parse(aestdtc + "-01")
    elif len(aestdtc) == 4: astdt = parse(aestdtc + "-01-01")
    if not aeendtc: aendt = None
    elif len(aeendtc) >= 10: aendt = parse(aeendtc[:10])
    elif len(aeendtc) == 7: aendt = last_day(aeendtc)
    elif len(aeendtc) == 4: aendt = parse(aeendtc + "-12-31")
    return astdt, aendt

def derive_study_days(astdt, aendt, trtsdt):
    return ((astdt - trtsdt).days + 1 if astdt and trtsdt else None,
            (aendt - trtsdt).days + 1 if aendt and trtsdt else None)
```

---

## AOCCFL (First Occurrence)

```python
def derive_aoccfl(adae):
    adae['AOCCFL'] = 'N'
    teae = adae[adae['TRTEMFL']=='Y'].sort_values(['USUBJID','AEDECOD','ASTDT'])
    for (uid, decod), _ in teae.groupby(['USUBJID','AEDECOD']).first().iterrows():
        m = (adae['USUBJID']==uid) & (adae['AEDECOD']==decod) & (adae['TRTEMFL']=='Y')
        adae.at[adae[m].sort_values('ASTDT').index[0], 'AOCCFL'] = 'Y'
    return adae
```

---

## Duration & Severity

- ADURN: `(aendt - astdt).days + 1` if both exist else None
- AESEV: CDISC CT C66769 (MILD/MODERATE/SEVERE)
- AESER: 'Y' if any of AESDTH/AESLIFE/AESHOSP/AESDISAB/AESCONG/AESMIE

---

## Merge

```python
def build_adae(sdtm_dir, adsl_path, cfg):
    ae, adsl = read_xpt(f"{sdtm_dir}/ae.xpt"), read_xpt(adsl_path)
    adae = ae.merge(adsl, on='USUBJID', how='left')
    assert adae['USUBJID'].notna().all()
    return derive_all(adae, cfg)
```

---

## Output Schema

| Variable | Type | Source |
|----------|------|--------|
| USUBJID | Char(11) | AE/ADSL |
| TRTA/TRTP | Char(40) | ADSL |
| SAFFL | Char(1) | ADSL |
| AETERM/AEDECOD/AEBODSYS | Char(200/100) | AE |
| AESEV/AESER | Char(10/1) | AE |
| TRTEMFL | Char(1) | Derived |
| AOCCFL | Char(1) | Derived |
| ASTDT/AENDT | Num | Derived |
| ASTDY | Num | Derived |
| ADURN | Num | Derived |

---

## Edge Cases

| Scenario | Action |
|----------|--------|
| Missing AESTDTC | TRTEMFL='', include |
| Partial date | Impute start=01, end=last |
| Pre-tx AE | TRTEMFL='N', include |
| Duplicate AE | Keep all, AOCCFL first |
| AESDTH='Y' | Check ADSL.DTHFL |
| Missing AEDECOD | Flag, AETERM fallback |

---

## Integration

**Up:** `/adam-adsl-builder`, `/sdtm-ae-mapper`, `/study-setup`
**Down:** `/adam-validator`, `/tfl-table-generator`, `/adrg-writer`
**Related:** `/adam-traceability-checker`, `/data-quality`

---

## Constraints

**Never:** Exclude orphans, default TRTEMFL='Y', hardcode window, dedupe blindly
**Always:** Merge ADSL->AE, document imputation, validate vs SAP, use cfg for window
