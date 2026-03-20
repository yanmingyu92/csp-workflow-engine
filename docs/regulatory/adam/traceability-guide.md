# ADaM Traceability Guide

## Purpose
Supports the **adam-traceability-check** node (Layer 4) and **adam-reviewer-guide** node.

## Regulatory Basis
- **CDISC ADaM IG v1.3 Section 2**: Fundamental principles — traceability
- **FDA Study Data Technical Conformance Guide**: Traceability requirements
- **PhUSE ADaM Reviewer's Guide Template**: How to document traceability

## Traceability Principle
> Every result in a clinical study report must be traceable back through the analysis dataset, the tabulation dataset, and the CRF/source data.

```
CSR Result ← TFL Output ← ADaM Variable ← SDTM Variable ← CRF Field
```

## Traceability Variables

| ADaM Variable | Purpose | Example |
|---------------|---------|---------|
| SRCDOM | Source Domain | "LB" |
| SRCVAR | Source Variable | "LBSTRESN" |
| SRCSEQ | Source Sequence Number | Links to specific SDTM record |

## Traceability Levels

### Level 1: Variable-Level (Metadata)
- Documented in Define.xml
- Each ADaM variable has an origin (CRF, Derived, Assigned)
- Derivation methods described in computational algorithms

### Level 2: Record-Level (Data)
- ADaM records link to SDTM via SRCDOM/SRCVAR/SRCSEQ
- For 1:1 mappings: direct link
- For many:1 derivations: document the aggregation logic

### Level 3: Result-Level (Output)
- TFL programs reference specific ADaM variables
- Analysis populations match ADSL flag definitions
- Statistical methods match SAP specifications

## Common Traceability Issues
1. **Missing SRCDOM/SRCVAR** — always populate for derived variables
2. **Broken links** — SRCSEQ values that don't match SDTM --SEQ
3. **Undocumented derivations** — complex algorithms without Define.xml entries
4. **Population mismatches** — TFL population ≠ ADSL population flag

## Reviewer's Guide Structure
1. Study overview and dataset inventory
2. ADaM datasets and their relationship to SDTM
3. Analysis population definitions
4. Key derivation explanations
5. Non-standard variables and their justification
6. Known issues and deviations from ADaM IG
