# SDTM Supplemental Qualifiers & Related Records Guide

## Purpose
Supports Layer 2 nodes: **sdtm-suppqual**, **sdtm-relrec**, **sdtm-custom-domain**, **sdtm-trial-design**.

## Regulatory Basis
- **CDISC SDTM IG v3.4 Section 8**: Supplemental Qualifiers and Related Records
- **CDISC SDTM IG v3.4 Section 3**: Trial Design Model
- **CDISC SDTM IG v3.4 Section 4.1.2**: Custom domains

---

## SUPP-- (Supplemental Qualifiers)

Variables that cannot be mapped to standard SDTM variables go into SUPP-- datasets.

### Structure
| Variable | Label | Required | Notes |
|----------|-------|----------|-------|
| STUDYID | Study Identifier | Req | — |
| RDOMAIN | Related Domain | Req | Parent domain (e.g., "AE") |
| USUBJID | Unique Subject ID | Req | — |
| IDVAR | Identifying Variable | Req | Usually "AESEQ", "--SEQ" |
| IDVARVAL | Identifying Variable Value | Req | Sequence number value |
| QNAM | Qualifier Variable Name | Req | Short name (≤8 chars) |
| QLABEL | Qualifier Variable Label | Req | ≤40 chars |
| QVAL | Data Value | Req | — |
| QORIG | Origin | Req | "CRF", "ASSIGNED", "DERIVED" |
| QEVAL | Evaluator | Perm | "INVESTIGATOR", "SPONSOR" |

### When to Use SUPP
- Non-standard CRF fields with no SDTM variable mapping
- Sponsor-specific variables needed for analysis
- Multiple values where standard allows only one

---

## RELREC (Related Records)

Links records across domains (e.g., an AE to its concomitant medication).

### Structure
| Variable | Label | Notes |
|----------|-------|-------|
| STUDYID | Study Identifier | — |
| RDOMAIN | Related Domain | Domain being linked |
| USUBJID | Subject ID | — |
| IDVAR | Identifying Variable | e.g., "AESEQ" |
| IDVARVAL | ID Value | Sequence number |
| RELTYPE | Relationship Type | "ONE", "MANY" |
| RELID | Relationship ID | Groups related records |

---

## Trial Design Domains

### TA (Trial Arms)
Maps the treatment path for each arm through epochs.

### TE (Trial Elements)
Defines the building blocks of the trial (e.g., washout, treatment, follow-up).

### TV (Trial Visits)
Planned visit schedule with visit numbers, names, and windows.

### TS (Trial Summary)
Study-level parameters: title, phase, indication, target enrollment, etc.

### TI (Trial Inclusion/Exclusion)
Lists inclusion and exclusion criteria as structured records.

---

## Custom Domains
When standard SDTM domains don't cover a data type:
1. Follow the General Observation Class structure closest to the data
2. Use a two-character domain code not already in use
3. Document in the Define.xml and reviewer's guide
4. Include all required Identifier and Timing variables
