# SDTM Controlled Terminology Guide

## Purpose
Supports all Layer 2 SDTM mapping nodes. Controlled terminology (CT) ensures consistent coding across studies.

## Regulatory Basis
- **CDISC SDTM IG v3.4**: References CDISC CT throughout
- **FDA Study Data Technical Conformance Guide**: Requires CDISC CT alignment

## Essential Codelist Categories

### Subject-Level (DM Domain)
| Codelist | Variable(s) | Common Values |
|----------|-------------|---------------|
| SEX | SEX | M, F, U, UNDIFFERENTIATED |
| RACE | RACE | WHITE, BLACK OR AFRICAN AMERICAN, ASIAN, AMERICAN INDIAN OR ALASKA NATIVE, NATIVE HAWAIIAN OR OTHER PACIFIC ISLANDER, OTHER, MULTIPLE, NOT REPORTED, UNKNOWN |
| ETHNIC | ETHNIC | HISPANIC OR LATINO, NOT HISPANIC OR LATINO, NOT REPORTED, UNKNOWN |
| COUNTRY | COUNTRY | ISO 3166 alpha-3 codes |
| AGEU | AGEU | YEARS, MONTHS, WEEKS, DAYS, HOURS |

### Events (AE, DS Domains)
| Codelist | Variable(s) | Notes |
|----------|-------------|-------|
| AESEV | AESEV | MILD, MODERATE, SEVERE |
| ACN | AEACN | DRUG WITHDRAWN, DOSE REDUCED, DOSE NOT CHANGED, etc. |
| OUT | AEOUT | RECOVERED/RESOLVED, RECOVERING/RESOLVING, NOT RECOVERED/NOT RESOLVED, etc. |
| NCOMPLT | DSDECOD | COMPLETED, ADVERSE EVENT, DEATH, LOST TO FOLLOW-UP, etc. |

### Findings (LB, VS Domains)
| Codelist | Variable(s) | Notes |
|----------|-------------|-------|
| LBTESTCD | LBTESTCD | Standardized lab test short names |
| VSTESTCD | VSTESTCD | SYSBP, DIABP, PULSE, TEMP, HEIGHT, WEIGHT |
| UNIT | *ORRESU, *STRESU | SI and conventional units |
| NRIND | *NRIND | NORMAL, LOW, HIGH, ABNORMAL |

### Interventions (CM, EX Domains)
| Codelist | Variable(s) | Notes |
|----------|-------------|-------|
| ROUTE | CMROUTE, EXROUTE | ORAL, INTRAVENOUS, SUBCUTANEOUS, etc. |
| FRM | CMDOSFRM, EXDOSFRM | TABLET, CAPSULE, INJECTION, etc. |
| FREQ | CMDOSFRQ, EXDOSFRQ | QD, BID, TID, Q2W, Q4W, etc. |

## CT Version Management
- Always use the CT version specified in the study specification
- Document the CT package version in TS domain (TSPARMCD = "CTVER")
- When multiple versions exist, use the version effective at study start
- FDA submissions require CDISC CT to be from an NCI-published package

## Handling Non-Standard Terms
1. Map CRF terms to closest CDISC CT value
2. If no mapping exists, use the verbatim term in *ORRES/*TERM
3. Document non-mapped terms in the reviewer's guide
4. Consider requesting new CT terms through the CDISC submission process
