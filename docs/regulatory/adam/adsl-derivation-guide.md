# ADaM ADSL Derivation Guide

## Purpose
Supports the **adam-adsl** node (Layer 4). ADSL (Subject-Level Analysis Dataset) is the foundational ADaM dataset — all other ADaM datasets merge ADSL for population flags and treatment variables.

## Regulatory Basis
- **CDISC ADaM IG v1.3 Section 3**: ADSL requirements
- **CDISC ADaM ADSL Supplement**: Detailed derivation guidance

## Required Variables

### Identification
| Variable | Label | Source | Derivation |
|----------|-------|--------|------------|
| STUDYID | Study Identifier | DM.STUDYID | Direct copy |
| USUBJID | Unique Subject ID | DM.USUBJID | Direct copy |
| SUBJID | Subject ID | DM.SUBJID | Direct copy |
| SITEID | Study Site ID | DM.SITEID | Direct copy |

### Treatment Variables
| Variable | Label | Derivation |
|----------|-------|------------|
| TRT01P | Planned Treatment Period 1 | From DM.ARM or randomization data |
| TRT01A | Actual Treatment Period 1 | From DM.ACTARM or dosing data |
| TRT01PN | Planned Treatment (N) | Numeric code for TRT01P |
| TRT01AN | Actual Treatment (N) | Numeric code for TRT01A |
| TRTSDTM | Datetime of First Exposure | From EX.EXSTDTC (first dose) |
| TRTSDT | Date of First Exposure | Date part of TRTSDTM |
| TRTEDTM | Datetime of Last Exposure | From EX.EXENDTC (last dose) |
| TRTEDT | Date of Last Exposure | Date part of TRTEDTM |

### Population Flags
| Variable | Label | Derivation |
|----------|-------|------------|
| ITTFL | Intent-to-Treat Flag | "Y" if randomized |
| SAFFL | Safety Population Flag | "Y" if received ≥1 dose |
| FASFL | Full Analysis Set Flag | "Y" per protocol definition |
| PPROTFL | Per-Protocol Flag | "Y" if no major protocol deviations |
| RANDFL | Randomized Flag | "Y" if randomized |
| ENRLFL | Enrolled Flag | "Y" if enrolled |
| COMPLFL | Completed Flag | "Y" if completed study per DS |

### Demographics
| Variable | Label | Source |
|----------|-------|--------|
| AGE | Age | DM.AGE |
| AGEU | Age Units | DM.AGEU |
| AGEGR1 | Age Group 1 | Derived grouping (e.g., <65, ≥65) |
| AGEGR1N | Age Group 1 (N) | Numeric code |
| SEX | Sex | DM.SEX |
| SEXN | Sex (N) | Numeric code (1=M, 2=F) |
| RACE | Race | DM.RACE |
| RACEN | Race (N) | Numeric code |
| ETHNIC | Ethnicity | DM.ETHNIC |
| BMIBL | Baseline BMI | VS-derived: WEIGHT/(HEIGHT^2) |
| WEIGHTBL | Baseline Weight | Last VS.WEIGHT before first dose |
| HEIGHTBL | Baseline Height | VS.HEIGHT at screening |

### Dates
| Variable | Label | Derivation |
|----------|-------|------------|
| RFSTDTC | Reference Start Date (Char) | DM.RFSTDTC |
| RFENDTC | Reference End Date (Char) | DM.RFENDTC |
| RANDDT | Date of Randomization | From randomization data/DS |
| DTHDT | Date of Death | From AE/DS death records |
| EOSDT | End of Study Date | From DS completion/discontinuation |
| EOSDY | End of Study Day | EOSDT - TRTSDT + 1 |

## Derivation Principles
1. **One record per subject** — ADSL has exactly one row per USUBJID
2. **Traceability** — every derived variable must trace back to SDTM source
3. **Population flags** — must be mutually consistent (e.g., SAFFL=Y implies ITTFL=Y in most study designs)
4. **Baseline values** — last non-missing value before or on first dose date

## Quality Criteria
- One record per subject (NOBS = number of subjects)
- All population flags present and consistent
- TRTSDT/TRTEDT present for all dosed subjects
- All variables trace to SDTM source
