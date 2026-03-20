# SDTM Demographics (DM) Domain Guide

## Purpose
Supports the **sdtm-dm-mapping** node (Layer 2). DM is the foundational SDTM domain — every analysis links back to DM for subject-level information.

## Regulatory Basis
- **CDISC SDTM IG v3.4 Section 6.1**: Demographics domain specification
- **FDA Study Data Technical Conformance Guide**: Required DM variables and controlled terminology

## Required Variables

| Variable | Label | Type | Required | Controlled Term |
|----------|-------|------|----------|-----------------|
| STUDYID | Study Identifier | Char | Req | — |
| DOMAIN | Domain Abbreviation | Char | Req | "DM" |
| USUBJID | Unique Subject ID | Char | Req | — |
| SUBJID | Subject ID | Char | Req | — |
| RFSTDTC | Subject Ref Start Date | Char | Exp | ISO 8601 |
| RFENDTC | Subject Ref End Date | Char | Exp | ISO 8601 |
| RFXSTDTC | Date/Time of First Study Treatment | Char | Exp | ISO 8601 |
| RFXENDTC | Date/Time of Last Study Treatment | Char | Exp | ISO 8601 |
| SITEID | Study Site Identifier | Char | Req | — |
| BRTHDTC | Date/Time of Birth | Char | Perm | ISO 8601 |
| AGE | Age | Num | Exp | — |
| AGEU | Age Units | Char | Exp | AGEU CT |
| SEX | Sex | Char | Req | SEX CT |
| RACE | Race | Char | Exp | RACE CT |
| ETHNIC | Ethnicity | Char | Perm | ETHNIC CT |
| ARMCD | Planned Arm Code | Char | Req | — |
| ARM | Description of Planned Arm | Char | Req | — |
| ACTARMCD | Actual Arm Code | Char | Req | — |
| ACTARM | Description of Actual Arm | Char | Req | — |
| COUNTRY | Country | Char | Req | ISO 3166 |
| DMDTC | Date/Time of Collection | Char | Perm | ISO 8601 |
| DMDY | Study Day of Collection | Num | Perm | — |

## Derivation Rules

### USUBJID Construction
```
USUBJID = STUDYID || "-" || SITEID || "-" || SUBJID
```

### AGE Derivation
```python
AGE = floor((RFSTDTC - BRTHDTC) / 365.25)  # in YEARS
AGEU = "YEARS"
```

### Reference Dates
- **RFSTDTC**: Date of informed consent (or first study event)
- **RFENDTC**: Date of last study contact
- **RFXSTDTC**: First dose date
- **RFXENDTC**: Last dose date

### Treatment Arms
| Scenario | ARMCD | ARM |
|----------|-------|-----|
| As planned and received | = ACTARMCD | = ACTARM |
| Treatment switch | Planned ≠ Actual arm | Document both |
| Screen failure | "SCRNFAIL" | "Screen Failure" |
| Not treated | "NOTTRT" | "Not Treated" |

## Controlled Terminology
- SEX: "M" (Male), "F" (Female), "U" (Unknown)
- RACE: "WHITE", "BLACK OR AFRICAN AMERICAN", "ASIAN", etc. (CDISC CT)
- ETHNIC: "HISPANIC OR LATINO", "NOT HISPANIC OR LATINO", "NOT REPORTED", "UNKNOWN"

## Quality Criteria
- All required variables present per SDTM IG
- USUBJID uniquely identifies each subject
- Controlled terminology matches CDISC CT
- P21 validation returns 0 errors
