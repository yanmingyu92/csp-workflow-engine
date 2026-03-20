# Statistical Analysis Plan (SAP) Review Guide

## Purpose
This guide supports SAP review at the **sap-review** graph node (Layer 0). The SAP is the bridge between the clinical protocol and the statistical programming deliverables.

## Regulatory Basis
- **ICH E9**: Statistical Principles for Clinical Trials — the primary standard for SAP content
- **ICH E3**: Structure and Content of Clinical Study Reports — defines what the CSR must contain, which the SAP must plan for

## Key SAP Sections to Extract

### 1. Study Objectives & Endpoints
| Element | What to Extract | Downstream Impact |
|---------|----------------|-------------------|
| Primary endpoint(s) | Variable name, definition, time point | Drives ADSL/ADTTE derivation |
| Secondary endpoints | Variable name, definition | Drives BDS ADaM datasets |
| Exploratory endpoints | Variable name, definition | Lower priority, may skip in initial programming |

### 2. Analysis Populations
| Population | Typical Definition | ADaM Flag |
|-----------|-------------------|-----------|
| Intent-to-Treat (ITT) | All randomized subjects | `ITTFL = 'Y'` |
| Modified ITT (mITT) | ITT minus protocol violations | `MITTFL = 'Y'` |
| Per-Protocol (PP) | Completed treatment per protocol | `PPFL = 'Y'` |
| Safety | All subjects who received ≥1 dose | `SAFFL = 'Y'` |

### 3. Statistical Methods
- Summary statistics (n, mean, SD, median, min, max)
- Hypothesis tests (identify test type, significance level)
- Confidence intervals (level, method)
- Multiplicity adjustment (Bonferroni, Hochberg, gatekeeping)
- Missing data handling (LOCF, MMRM, multiple imputation)
- Subgroup analyses (pre-specified subgroups)

### 4. TFL Shell Specifications
- Number and type of each table, figure, listing
- Population for each output
- Layout specifications (page orientation, decimal places)
- Footnotes and data source references

## Parsing Workflow
1. Extract structured data into `specs/sap-parsed.yaml`
2. Cross-reference endpoints with protocol objectives
3. Map each TFL shell to its source ADaM dataset
4. Flag any ambiguities for programmer review

## Quality Criteria
- **Mandatory**: All primary/secondary endpoints extracted, all populations defined
- **Recommended**: Subgroup analyses identified, multiplicity strategy documented
