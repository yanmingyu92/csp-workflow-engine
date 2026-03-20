# SDTM Events & Interventions Domain Guide

## Purpose
Supports Layer 2 events/interventions nodes: **sdtm-ae-mapping**, **sdtm-cm-mapping**, **sdtm-mh-mapping**, **sdtm-ex-mapping**, **sdtm-ds-mapping**.

## Regulatory Basis
- **CDISC SDTM IG v3.4 Section 6.2**: Events and Interventions domains
- **MedDRA coding guidelines**: For AE and MH coding

---

## AE (Adverse Events) Domain

### Key Variables
| Variable | Label | Required | Notes |
|----------|-------|----------|-------|
| AETERM | Reported Term | Req | Verbatim from CRF |
| AEDECOD | Dictionary-Derived Term | Req | MedDRA PT |
| AEBODSYS | Body System or Organ Class | Req | MedDRA SOC |
| AESEV | Severity/Intensity | Exp | MILD/MODERATE/SEVERE |
| AESER | Serious Event | Exp | Y/N |
| AEREL | Causality | Exp | RELATED/NOT RELATED |
| AEACN | Action Taken | Exp | CDISC CT |
| AEOUT | Outcome | Exp | CDISC CT |
| AESTDTC | Start Date/Time | Exp | ISO 8601 |
| AEENDTC | End Date/Time | Perm | ISO 8601 |
| AESTDY | Study Day of Start | Perm | Derived |
| AEENDY | Study Day of End | Perm | Derived |

### MedDRA Coding Hierarchy
```
SOC → HLGT → HLT → PT → LLT
(System Organ Class → ... → Preferred Term → Lowest Level Term)
```

---

## CM (Concomitant Medications) Domain

### Key Variables
| Variable | Label | Required | Notes |
|----------|-------|----------|-------|
| CMTRT | Reported Name | Req | Verbatim |
| CMDECOD | Standardized Name | Exp | WHO Drug Dictionary |
| CMCAT | Category | Perm | e.g., "PRIOR", "CONCOMITANT" |
| CMDOSE | Dose | Perm | Numeric dose value |
| CMDOSU | Dose Units | Perm | CDISC CT |
| CMROUTE | Route of Administration | Perm | CDISC CT |
| CMSTDTC | Start Date/Time | Exp | ISO 8601 |
| CMENDTC | End Date/Time | Perm | ISO 8601 |

---

## MH (Medical History) Domain

### Key Variables
| Variable | Label | Required | Notes |
|----------|-------|----------|-------|
| MHTERM | Reported Term | Req | Verbatim |
| MHDECOD | Dictionary-Derived Term | Req | MedDRA PT |
| MHBODSYS | Body System | Req | MedDRA SOC |
| MHCAT | Category | Perm | Protocol-defined categories |
| MHSTDTC | Start Date/Time | Perm | ISO 8601 (often partial) |

---

## EX (Exposure) Domain

### Key Variables
| Variable | Label | Required | Notes |
|----------|-------|----------|-------|
| EXTRT | Treatment Name | Req | From protocol/randomization |
| EXDOSE | Dose | Req | Numeric |
| EXDOSU | Dose Units | Req | CDISC CT |
| EXDOSFRM | Dose Form | Exp | CDISC CT |
| EXROUTE | Route | Exp | CDISC CT |
| EXSTDTC | Start Date/Time | Req | ISO 8601 |
| EXENDTC | End Date/Time | Req | ISO 8601 |

---

## DS (Disposition) Domain

### Key Variables
| Variable | Label | Required | Notes |
|----------|-------|----------|-------|
| DSTERM | Reported Term | Req | Verbatim |
| DSDECOD | Standardized Disposition Term | Req | CDISC CT |
| DSCAT | Category | Exp | "DISPOSITION EVENT", "PROTOCOL MILESTONE" |
| DSSTDTC | Start Date/Time | Req | ISO 8601 |
| EPOCH | Epoch | Exp | "SCREENING", "TREATMENT", "FOLLOW-UP" |

### Common DSDECOD Values
- COMPLETED, SCREEN FAILURE, ADVERSE EVENT, DEATH, LOST TO FOLLOW-UP, WITHDREW CONSENT, PHYSICIAN DECISION, PROTOCOL VIOLATION

## Study Day Derivation (All Domains)
```python
# For dates on or after RFSTDTC:
--DY = date(--DTC) - date(RFSTDTC) + 1

# For dates before RFSTDTC:
--DY = date(--DTC) - date(RFSTDTC)
# (No Day 0)
```
