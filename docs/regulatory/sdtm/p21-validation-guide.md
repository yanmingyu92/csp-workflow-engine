# Pinnacle 21 Validation Guide

## Purpose
Supports Layer 3 nodes: **p21-sdtm-validation**, **sdtm-crossdomain-check**, **sdtm-annotated-crf**, **sdtm-reviewer-guide**; and Layer 4 node: **p21-adam-validation**.

## Regulatory Basis
- **FDA Data Standards Catalog**: Lists required validation standards
- **FDA Pre-NDA/BLA Meeting Checklist**: Validation expectations
- **CDISC SDTM IG v3.4**: Validation rules source
- **CDISC ADaM IG v1.3**: Validation rules source
- **PhUSE Reviewer's Guide Template**: SDRG/ADRG structure

## P21 Validation Rule Categories

### SDTM Rules
| Category | Examples | Severity |
|----------|---------|----------|
| **Domain structure** | Missing required variables | Error |
| **Controlled terminology** | Values not in CDISC CT | Error/Warning |
| **Cross-domain consistency** | USUBJID in AE but not in DM | Error |
| **ISO 8601 dates** | Invalid date format | Error |
| **Variable attributes** | Label exceeds 40 chars | Warning |
| **Uniqueness** | Duplicate records | Error |
| **Reference integrity** | RELREC references invalid records | Error |

### ADaM Rules
| Category | Examples | Severity |
|----------|---------|----------|
| **ADSL structure** | Missing population flags | Error |
| **BDS structure** | Missing PARAM/PARAMCD/AVAL | Error |
| **Traceability** | Missing computational methods | Warning |
| **Cross-dataset** | USUBJID in ADAE but not in ADSL | Error |
| **Flag consistency** | ABLFL without BASE | Warning |

## Validation Workflow

### Step 1: Run P21 Validator
- Configure validation against specified SDTM IG / ADaM IG version
- Include Define.xml in validation scope
- Run against all datasets simultaneously (cross-domain checks)

### Step 2: Triage Results
| Disposition | Action |
|-------------|--------|
| Resolve | Fix the underlying data/program issue |
| Acknowledge | Document justification in reviewer's guide |
| Defer | Flag for resolution in next data transfer |
| Dismiss | Rule is not applicable (with documented justification) |

### Step 3: Document
- Zero errors required before submission
- All warnings must be reviewed and documented
- Justifications recorded in SDRG/ADRG

## Cross-Domain Checks
Specific checks that span multiple datasets:
- DM.RFSTDTC consistency with EX first dose dates
- AE.AESTDTC chronological relationship to DM.RFSTDTC
- SUPPQUAL.RDOMAIN references valid parent domains
- Define.xml references match actual dataset contents
- Variable order matches Define.xml specification

## Annotated CRF Requirements
The aCRF documents the mapping from CRF page → SDTM variable:
- Every CRF field annotated with target domain.variable
- Pre-filled fields marked as "Assigned" origin
- Derived fields reference computational method
- PDF format with clickable annotations
