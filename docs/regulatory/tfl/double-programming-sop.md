# TFL Double Programming SOP

## Purpose
Supports the **tfl-double-programming** and **tfl-qc-validation** nodes (Layer 5).

## Regulatory Basis
- **Company SOP**: Independent Verification
- **Company SOP**: Double Programming
- **ICH E3**: Statistical results must be verified

## Double Programming Workflow

### Step 1: Shell Review
- Reviewer validates TFL shells against SAP
- Confirms population, endpoints, statistical methods
- Signs off on mock-up layouts

### Step 2: Primary Programming
- Primary programmer writes code from SAP/shells
- Uses ADaM datasets as input
- Generates production outputs

### Step 3: Independent Verification
- QC programmer independently writes code from SAP/shells
- Must NOT reference primary programmer's code
- Uses same ADaM datasets as input
- Generates QC outputs

### Step 4: Comparison
```
For Tables:
  - Cell-by-cell numeric comparison
  - Tolerance: exact match for counts, ±0.1 for percentages, ±0.001 for p-values

For Listings:
  - Row-by-row value comparison
  - Sort order verification

For Figures:
  - Numeric data behind figures compared
  - Visual review of figure quality
```

### Step 5: Resolution
- All discrepancies investigated
- Root cause documented (programming error, spec ambiguity, data issue)
- Corrections made and re-compared
- Final zero-discrepancy comparison documented

### Step 6: Sign-Off
- Primary programmer signs production output
- QC programmer signs QC comparison
- Lead programmer/statistician provides final approval

## QC Checklist
- [ ] Output matches shell layout
- [ ] Correct population used
- [ ] Correct statistical method applied
- [ ] Footnotes and titles accurate
- [ ] Decimal precision consistent
- [ ] All subjects accounted for
- [ ] Independent results match production results
