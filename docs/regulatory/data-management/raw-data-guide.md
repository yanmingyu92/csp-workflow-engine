# Raw Data Management Guide

## Purpose
Supports Layer 1 nodes: **edc-extract**, **crf-validation**, **raw-data-validation**, **data-reconciliation**.

## Regulatory Basis
- **ICH E6(R2)**: Data Management — electronic data capture requirements
- **21 CFR Part 11**: Electronic Records — audit trail requirements
- **CDISC CDASH v2.2**: Clinical Data Acquisition Standards Harmonization
- **FDA Study Data Technical Conformance Guide**: Expected data formats

## EDC Data Extraction

### Standard Export Formats
| Format | Use Case | Notes |
|--------|----------|-------|
| CSV | Universal interchange | UTF-8 encoding required |
| SAS7BDAT | Traditional pharma standard | SAS transport for submission |
| SAS XPORT (XPT) | FDA submission format | V5 transport files |

### Extraction Checklist
1. All CRF forms included in export
2. All subjects (including screen failures, if needed)
3. Audit trail data exported separately
4. Data cut-off date documented
5. Export timestamp recorded

## CRF Validation

### CDASH Alignment Checks
- Variable names follow CDASH naming conventions
- Controlled terminology matches CDISC CT
- Data types match CDASH specifications

### CRF Annotation
The annotated CRF (aCRF) maps each CRF field to its SDTM destination:
- Source field → SDTM domain.variable
- Pre-populated fields noted
- Derived fields flagged
- Visit-based vs. non-visit-based collection identified

## Data Quality Checks

### Completeness
- All expected subjects present
- All expected visits present per protocol design
- No unexpected missing forms

### Consistency
- Date logic (e.g., start date ≤ end date)
- Cross-form consistency (demographics vs. disposition)
- Duplicate record detection

### Conformance
- Value ranges within expected limits
- Controlled terminology alignment
- Character encoding validation (no special characters that break XPT)

## Data Reconciliation
- Compare EDC exports against external data (lab central, IVRS/IXRS)
- Document and resolve discrepancies before SDTM mapping
- Generate reconciliation report with match rates
