# TFL Programming Guide

## Purpose
Supports Layer 5 nodes: **tfl-shell-review**, **tfl-table-generation**, **tfl-listing-generation**, **tfl-figure-generation**, **tfl-qc-validation**, **tfl-double-programming**.

## Regulatory Basis
- **ICH E3**: Structure and Content of Clinical Study Reports
  - Section 11: Safety evaluation (tables, summaries)
  - Section 12: Figures (efficacy, PK)
  - Section 14: Listings (individual patient data)
- **Company SOP**: Double Programming and Independent Verification

---

## Tables

### Standard Table Types
| Category | Examples | Source ADaM |
|----------|---------|-------------|
| Demographics | Subject disposition, baseline characteristics | ADSL |
| Safety | AE summary, lab shift, vital signs | ADAE, ADLB, ADVS |
| Efficacy | Primary/secondary endpoints, responder analysis | ADEFF, ADLB |
| PK | Concentration summary, PK parameters | ADPC, ADPP |

### Table Structure
```
Title: Table X.X.X - [Description] (Population, Dataset)
┌────────────────────────────────────────────────────────┐
│ Header Rows: Treatment groups with column headers       │
├────────────────────────────────────────────────────────┤
│ Body: Statistics by parameter/category                  │
│   n (%)  for categorical                               │
│   n, Mean, SD, Median, Min, Max  for continuous        │
├────────────────────────────────────────────────────────┤
│ Footnotes: Data source, abbreviations, methods          │
│ Program: [program name]  Output: [output file]          │
└────────────────────────────────────────────────────────┘
```

### Formatting Standards
- Decimal precision: consistent within each parameter
- Big N in column headers: `Treatment A (N=XX)`
- Percentages: n (XX.X%) based on non-missing denominator
- P-values: X.XXX format (or <0.001)
- Page orientation: portrait for narrow tables, landscape for wide

---

## Listings

### Standard Listing Types
| Category | Content |
|----------|---------|
| Adverse Events | Individual AE records by subject |
| Lab Results | Individual lab values by subject/visit |
| Protocol Deviations | Deviations by subject |
| Concomitant Medications | Medications by subject |
| Efficacy | Individual endpoint values by subject/visit |

### Listing Structure
- Sort order: typically by treatment, site, subject, date
- Include SUBJID, visit, date, parameter, result
- Flag: clinically significant values, baseline values

---

## Figures

### Standard Figure Types
| Type | Use Case | Format |
|------|----------|--------|
| Kaplan-Meier | Time-to-event survival curves | PNG/PDF |
| Forest Plot | Subgroup analysis comparison | PNG/PDF |
| Waterfall | Individual response | PNG/PDF |
| Spaghetti | Individual trajectories over time | PNG/PDF |
| Box Plot | Distribution comparison | PNG/PDF |
| Bar Chart | Categorical comparisons | PNG/PDF |

### Figure Quality
- Resolution: ≥300 DPI for print
- Axes labeled with units
- Legend clearly identifying treatment groups
- Color-blind accessible color palette

---

## QC and Double Programming

### QC Approach
1. **Independent programming**: Second programmer creates output from specs
2. **Compare**: Match results cell-by-cell (tables) or value-by-value (listings)
3. **Resolve**: Investigate and document any discrepancies
4. **Sign-off**: Both programmer and QC reviewer sign off

### Comparison Methods
- Automated diff for table cell values
- Tolerance-based comparison for floating-point results (e.g., ±0.01)
- Visual inspection for figures

### Documentation
- QC log showing comparison results
- Discrepancy resolution notes
- Sign-off record with date and initials
