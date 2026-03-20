# SDTM Findings Domain Guide

## Purpose
Supports Layer 2 findings nodes: **sdtm-lb-mapping**, **sdtm-vs-mapping**, **sdtm-sv-mapping**.

## Regulatory Basis
- **CDISC SDTM IG v3.4 Section 6.3**: Findings domains

---

## LB (Laboratory Tests) Domain

### Key Variables
| Variable | Label | Required | Notes |
|----------|-------|----------|-------|
| LBTESTCD | Lab Test Short Name | Req | CDISC CT (e.g., ALT, AST, BILI) |
| LBTEST | Lab Test Name | Req | Full name |
| LBCAT | Category | Exp | "CHEMISTRY", "HEMATOLOGY", "URINALYSIS" |
| LBORRES | Result (Original) | Exp | As reported by lab |
| LBORRESU | Original Units | Exp | Original units |
| LBSTRESC | Result (Standardized Char) | Exp | Standardized result |
| LBSTRESN | Result (Standardized Num) | Exp | Numeric standardized |
| LBSTRESU | Standard Units | Exp | SI or conventional |
| LBNRIND | Reference Range Indicator | Exp | "NORMAL", "LOW", "HIGH" |
| LBORNRLO | Reference Range Lower | Exp | Original scale |
| LBORNRHI | Reference Range Upper | Exp | Original scale |
| LBDTC | Date/Time of Lab Test | Exp | ISO 8601 |
| VISITNUM | Visit Number | Exp | Numeric visit identifier |
| VISIT | Visit Name | Exp | Character visit label |
| LBBLFL | Baseline Flag | Exp | "Y" for baseline record |

### Unit Standardization
```python
# Example: Convert mg/dL to mmol/L for glucose
LBSTRESN = LBORRES * conversion_factor
LBSTRESU = "mmol/L"
```

### Baseline Flag Rules
1. Last non-missing value before or on first dose date
2. One baseline per test per subject
3. Set LBBLFL = "Y" for selected baseline records

---

## VS (Vital Signs) Domain

### Key Variables
| Variable | Label | Required | Notes |
|----------|-------|----------|-------|
| VSTESTCD | Vital Signs Test Code | Req | SYSBP, DIABP, PULSE, TEMP, HEIGHT, WEIGHT |
| VSTEST | Vital Signs Test Name | Req | Full name |
| VSORRES | Result (Original) | Exp | As recorded |
| VSORRESU | Original Units | Exp | — |
| VSSTRESC | Result (Standardized Char) | Exp | — |
| VSSTRESN | Result (Standardized Num) | Exp | — |
| VSSTRESU | Standard Units | Exp | — |
| VSPOS | Vital Signs Position | Perm | "STANDING", "SITTING", "SUPINE" |
| VSLOC | Location | Perm | "LEFT ARM", "RIGHT ARM" |
| VSDTC | Date/Time | Exp | ISO 8601 |
| VISITNUM | Visit Number | Exp | — |
| VSBLFL | Baseline Flag | Exp | "Y" |

---

## SV (Subject Visits) Domain

### Key Variables
| Variable | Label | Required | Notes |
|----------|-------|----------|-------|
| VISITNUM | Visit Number | Req | Numeric, unique per visit |
| VISIT | Visit Name | Req | "SCREENING", "WEEK 1", etc. |
| SVSTDTC | Start Date/Time of Visit | Req | ISO 8601 |
| SVENDTC | End Date/Time of Visit | Perm | ISO 8601 |
| EPOCH | Epoch | Exp | "SCREENING", "TREATMENT", "FOLLOW-UP" |

### Visit Windowing
- Define visit windows in the mapping specification
- Assign actual visits to scheduled visit windows
- Handle unscheduled visits with VISITNUM between scheduled values
- Document window rules for traceability
