# ADaM BDS & Analysis Dataset Guide

## Purpose
Supports Layer 4 analysis nodes: **adam-adae**, **adam-adlb**, **adam-adtte**, **adam-adeff**, **adam-custom-analysis**.

## Regulatory Basis
- **CDISC ADaM IG v1.3**: Analysis dataset structure
- **CDISC ADaM BDS Supplement**: Basic Data Structure standard
- **CDISC ADaM OCCDS Supplement**: Occurrence Data Structure (for AE analysis)
- **CDISC ADaM ADTTE Supplement**: Time-to-Event structure

---

## BDS (Basic Data Structure)

BDS is used for repeated measures data: lab tests, vital signs, efficacy assessments.

### Core Structure
| Variable | Label | Notes |
|----------|-------|-------|
| PARAM | Parameter | "Alanine Aminotransferase (U/L)" |
| PARAMCD | Parameter Code | "ALT" (≤8 chars) |
| PARAMN | Parameter (N) | Numeric identifier |
| AVAL | Analysis Value | Numeric analysis value |
| AVALC | Analysis Value (C) | Character analysis value |
| BASE | Baseline Value | Baseline AVAL |
| CHG | Change from Baseline | AVAL - BASE |
| PCHG | Percent Change from Baseline | ((AVAL - BASE) / BASE) * 100 |
| ABLFL | Baseline Record Flag | "Y" for baseline record |
| ANL01FL | Analysis Flag 01 | Custom analysis subset flag |
| AVISIT | Analysis Visit | Mapped visit name |
| AVISITN | Analysis Visit (N) | Numeric analysis visit |
| ADT | Analysis Date | Analysis-relevant date |
| ADY | Analysis Day | ADT - TRTSDT + 1 |

### Baseline Derivation
1. Identify the baseline period (typically pre-dose)
2. Select the last non-missing value in the period
3. Set ABLFL = "Y" for the selected record
4. Populate BASE for all records of the same parameter
5. Derive CHG = AVAL - BASE and PCHG = (CHG / BASE) * 100

---

## OCCDS (Occurrence Data Structure) — ADAE

For adverse event analysis datasets:

### Key Variables
| Variable | Label | Notes |
|----------|-------|-------|
| AEBODSYS | Body System | MedDRA SOC |
| AEDECOD | Dictionary-Derived Term | MedDRA PT |
| AETERM | Reported Term | Verbatim |
| AESEV | Severity | MILD, MODERATE, SEVERE |
| AESER | Serious | Y/N |
| AEREL | Relatedness | RELATED, NOT RELATED |
| AESTDTM | AE Start Datetime | From AE.AESTDTC |
| AEENDTM | AE End Datetime | From AE.AEENDTC |
| TRTEMFL | Treatment-Emergent Flag | "Y" if onset ≥ TRTSDT |
| ASTDT | Analysis Start Date | Date part of AESTDTM |
| AENDT | Analysis End Date | Date part of AEENDTM |
| CQ01NAM | Customized Query 01 Name | e.g., "Hepatotoxicity" |

### Treatment-Emergent Definition
```python
TRTEMFL = "Y" if ASTDT >= TRTSDT
         and (ASTDT <= TRTEDT + safety_followup_days)
```

---

## ADTTE (Time-to-Event)

### Key Variables
| Variable | Label | Notes |
|----------|-------|-------|
| PARAM | Parameter | "Time to First AE" |
| AVAL | Analysis Value | Time in specified units |
| CNSR | Censor | 0 = event, 1 = censored |
| EVNTDESC | Event Description | What constitutes the event |
| CNSDTDSC | Censoring Description | What constitutes censoring |
| STARTDT | Time-to-Event Origin | Analysis start date |
| ADT | Analysis Date | Event or censoring date |

### Censoring Rules
| Scenario | CNSR | ADT |
|----------|------|-----|
| Event occurred | 0 | Date of event |
| Completed study without event | 1 | End of study date |
| Lost to follow-up | 1 | Date of last contact |
| Ongoing at analysis cut-off | 1 | Cut-off date |

---

## Traceability
- **CDISC ADaM IG v1.3 Section 2**: Every ADaM variable must trace to SDTM source
- Include SRCDOM (source domain) and SRCVAR (source variable) or SRCSEQ
- Document complex derivations in the define.xml value-level metadata
- The **adam-traceability-check** node validates this chain

## Quality Criteria
- All ADaM fundamental principles satisfied
- Traceability to SDTM source maintained
- Population flags merged from ADSL
- Baseline values correctly derived
