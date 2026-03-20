# Study Setup & Protocol Guide

## Purpose
Supports the **protocol-setup** graph node (Layer 0). Establishes project infrastructure and extracts key protocol parameters.

## Regulatory Basis
- **ICH E6(R2)**: Good Clinical Practice — defines data management and quality standards
- **FDA Study Data Technical Conformance Guide**: Specifies expected study data structure

## Protocol Elements for Programming

### Study Design Parameters
| Parameter | Source | Programming Impact |
|-----------|--------|-------------------|
| Randomization scheme | Protocol Section 5 | ADSL: TRT01P, TRT01A derivation |
| Blinding | Protocol Section 5 | Unblinding procedures |
| Study phases | Protocol Section 3 | APERIOD, APERIODC in ADaM |
| Visit schedule | Protocol Section 6 | TV, TA, TS domain creation |

### Key Dates
- First Subject First Visit (FSFV)
- Database Lock (DBL)
- Analysis cut-off date
- Unblinding date

### Directory Structure
```
study-root/
├── raw/                  # Source data (EDC exports)
├── sdtm/                 # SDTM datasets (.xpt)
├── adam/                  # ADaM datasets (.xpt)
├── tfl/                  # Tables, Figures, Listings
├── specs/                # Mapping specs, derivation specs
├── programs/             # SAS/Python programs
├── docs/                 # Study documentation
└── define/               # Define.xml files
```

## Specification Creation
The **spec-creation** node (also Layer 0) creates:
1. SDTM mapping specification — maps raw variables to SDTM domains
2. ADaM derivation specification — defines analysis variable derivations
3. TFL shell specifications — layout templates for each output

### Spec Standards
- CDISC SDTM IG v3.4 for SDTM mapping terms
- CDISC ADaM IG v1.3 for derivation conventions
- Company SOPs for naming and versioning
