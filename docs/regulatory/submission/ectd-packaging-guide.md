# eCTD Submission Packaging Guide

## Purpose
Supports Layer 6 nodes: **esub-package-assembly**, **esub-final-validation**.

## Regulatory Basis
- **ICH M8 eCTD v4.0**: Electronic Common Technical Document specification
- **FDA eCTD Guidance**: FDA-specific eCTD requirements
- **FDA Study Data Validation Rules**: Final validation before submission
- **FDA Pre-NDA/BLA Meeting Checklist**: Pre-submission planning

## eCTD Module 5 Structure

```
m5/
├── datasets/
│   ├── study-id/
│   │   ├── tabulations/     # SDTM datasets
│   │   │   ├── sdtm/
│   │   │   │   ├── dm.xpt
│   │   │   │   ├── ae.xpt
│   │   │   │   ├── lb.xpt
│   │   │   │   ├── ...
│   │   │   │   └── define.xml
│   │   │   └── legacy/      # Non-standard tabulations (if any)
│   │   └── analysis/        # ADaM datasets
│   │       └── adam/
│   │           ├── adsl.xpt
│   │           ├── adae.xpt
│   │           ├── adlb.xpt
│   │           ├── ...
│   │           └── define.xml
│   └── supportdocs/         # Supporting documentation
│       ├── sdrg.pdf          # Study Data Reviewer's Guide (SDTM)
│       ├── adrg.pdf          # Analysis Data Reviewer's Guide (ADaM)
│       └── acrf.pdf          # Annotated CRF
```

## Submission Package Components

### Required Components
| Component | Format | Description |
|-----------|--------|-------------|
| SDTM datasets | .xpt (V5 transport) | All SDTM domains |
| SDTM Define.xml | .xml | SDTM metadata |
| ADaM datasets | .xpt (V5 transport) | All ADaM datasets |
| ADaM Define.xml | .xml | ADaM metadata |
| Define stylesheets | .xsl | For rendering Define.xml |
| Annotated CRF | .pdf | CRF-to-SDTM mapping |
| SDRG | .pdf | SDTM Reviewer's Guide |
| ADRG | .pdf | ADaM Reviewer's Guide |

### File Naming Conventions
- Dataset files: lowercase domain name (e.g., `dm.xpt`, `adsl.xpt`)
- Define.xml: `define.xml` (one per tabulation/analysis)
- Supporting docs: descriptive names, lowercase

### Size and Format Requirements
- Individual file: ≤5 GB
- Total submission: no hard limit, but consider transfer time
- XPT files: SAS V5 transport format
- Text encoding: UTF-8 for XML, ASCII for XPT variable labels

## Pre-Submission Checks

### Pinnacle 21 (OpenCST) Validation
Run P21 validation on:
1. All SDTM datasets against SDTM IG standards
2. All ADaM datasets against ADaM IG standards
3. Both Define.xml files against schema

### P21 Result Categories
| Category | Action |
|----------|--------|
| Error | Must resolve before submission |
| Warning | Review and document justification |
| Notice | Informational, no action required |

### Final Validation Checklist
- [ ] All datasets are valid .xpt files
- [ ] All P21 errors resolved (0 errors)
- [ ] All P21 warnings reviewed and documented
- [ ] Define.xml renders correctly
- [ ] aCRF annotations match SDTM datasets
- [ ] SDRG covers all non-standard conventions
- [ ] ADRG explains key derivations
- [ ] File sizes within FDA limits
- [ ] Directory structure matches eCTD spec
- [ ] Package can be opened and navigated correctly

## Reviewer's Guide Structure

### SDRG (Study Data Reviewer's Guide)
1. Study overview
2. SDTM dataset inventory
3. Non-standard domain descriptions
4. Controlled terminology deviations
5. Trial design datasets explanation
6. Issues log and resolutions

### ADRG (ADaM Data Reviewer's Guide)
1. Study overview
2. Analysis datasets inventory
3. Population definitions with flag variables
4. Key derivation explanations
5. Non-standard variable documentation
6. Traceability summary
