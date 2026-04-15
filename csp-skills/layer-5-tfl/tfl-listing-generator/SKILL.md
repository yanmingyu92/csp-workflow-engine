---
name: tfl-listing-generator
description: Generate patient data listings from SDTM and ADaM datasets. Triggers on "listing", "data listing", "patient listing", "AE listing", "lab listing", "protocol deviation listing".
version: "2.0"
user-invocable: true
context: fork
model: sonnet
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
argument-hint: "[options] -- --input <datasets> --output <output-dir> --type [ae|lab|pd|disposition|all]"
---

## Runtime Configuration (Step 0)

Resolve configuration in order:
1. `$ARGUMENTS` (highest precedence)
2. `specs/table-specs.yaml` -- listing specifications
3. `specs/tfl-templates.yaml` -- listing formatting templates
4. `specs/study-config.yaml` -- study metadata

```yaml
config_resolution:
  study_id: "$ARGUMENTS.study_id || study-config.study_id"
  input_dir: "$ARGUMENTS.input || 'output/adam/'"
  output_dir: "$ARGUMENTS.output || 'output/tfl/listings/'"
  listing_type: "$ARGUMENTS.type || 'all'"
  template: "$ARGUMENTS.template || 'specs/tfl-templates.yaml'"
```

## EXECUTE NOW
Parse $ARGUMENTS: --input, --output, --type, --dry-run
**START NOW.**

---

## Philosophy

**Listings present subject-level detail that regulators use to verify summarized results.** Sort order, pagination, and date formatting are critical for reviewer usability. Every value in a listing must be traceable to the source dataset.

---

## Input/Output Specification

### Inputs (matching regulatory-graph.yaml node `tfl-listing-generation`)
| Input | Format | Required | Source |
|-------|--------|----------|--------|
| SDTM/ADaM datasets | xpt | Yes | output/sdtm/ and output/adam/ |
| Listing specifications | yaml | Yes | specs/table-specs.yaml |
| TFL templates | yaml | Yes | specs/tfl-templates.yaml |

### Outputs (matching regulatory-graph.yaml node `tfl-listing-generation`)
| Output | Format | Path Pattern | Description |
|--------|--------|--------------|-------------|
| Patient data listings | rtf/pdf | output/tfl/listings/ | Subject-level data listings |

---

## Listing Types and Structure

### 1. Adverse Event Listing
```yaml
ae_listing:
  title: "Listing {listing_id}: Adverse Events ({population_name})"
  sort_order: ["USUBJID", "AESTDTC", "AETERM"]
  page_break: "USUBJID"  # New page per subject
  columns:
    - name: "USUBJID"
      label: "Subject ID"
      width: "1.5in"
    - name: "TRTA"
      label: "Treatment"
      width: "1.2in"
    - name: "AETERM"
      label: "Adverse Event"
      width: "2.5in"
    - name: "AEDECOD"
      label: "MedDRA PT"
      width: "2.0in"
    - name: "AEBODSYS"
      label: "MedDRA SOC"
      width: "2.0in"
    - name: "AESEV"
      label: "Severity"
      width: "0.8in"
    - name: "AESER"
      label: "Serious"
      width: "0.6in"
    - name: "AESTDTC"
      label: "Start Date"
      width: "1.0in"
    - name: "AEENDTC"
      label: "End Date"
      width: "1.0in"
    - name: "TRTEMFL"
      label: "TEAE"
      width: "0.5in"
  date_format: "DDMONYYYY"  # e.g., 15JAN2024
```

### 2. Laboratory Abnormality Listing
```yaml
lab_listing:
  title: "Listing {listing_id}: Laboratory Abnormalities ({population_name})"
  sort_order: ["USUBJID", "LBTEST", "LBDY"]
  columns:
    - name: "USUBJID"
      label: "Subject ID"
    - name: "TRTA"
      label: "Treatment"
    - name: "LBTEST"
      label: "Lab Test"
    - name: "LBORRES"
      label: "Result"
    - name: "LBORRESU"
      label: "Units"
    - name: "LBNRIND"
      label: "Reference Range"
    - name: "LBDTC"
      label: "Collection Date"
    - name: "VISIT"
      label: "Visit"
  highlight_rules:
    - condition: "LBNRIND in ['HIGH', 'LOW']"
      format: "bold"
    - condition: "LBNRIND in ['HIGH CRITICAL', 'LOW CRITICAL']"
      format: "bold red"
```

### 3. Protocol Deviation Listing
```yaml
pd_listing:
  title: "Listing {listing_id}: Protocol Deviations"
  sort_order: ["SITEID", "USUBJID", "DEVDATE"]
  columns:
    - name: "SITEID"
      label: "Site"
    - name: "USUBJID"
      label: "Subject ID"
    - name: "DEVCAT"
      label: "Category"
    - name: "DEVTERM"
      label: "Description"
    - name: "DEVDATE"
      label: "Date"
    - name: "DEVEVAL"
      label: "Impact Assessment"
```

### 4. Disposition Listing
```yaml
disposition_listing:
  title: "Listing {listing_id}: Subject Disposition"
  sort_order: ["SITEID", "USUBJID"]
  page_break: "SITEID"
  columns:
    - name: "SITEID"
      label: "Site"
    - name: "USUBJID"
      label: "Subject ID"
    - name: "TRT01P"
      label: "Planned Treatment"
    - name: "TRT01A"
      label: "Actual Treatment"
    - name: "DSDECOD"
      label: "Disposition"
    - name: "DSTERM"
      label: "Reason"
    - name: "EOSSTT"
      label: "End of Study Status"
```

---

## Output Schema

```yaml
listing_output:
  listing_id: "Listing 16.{n}"
  title: "{title}"
  population: "{population_name}"
  source_datasets: ["adae.xpt", "adsl.xpt"]
  format: "rtf"

  sort_order: ["USUBJID", "AESTDTC", "AETERM"]
  page_break_variable: "USUBJID"

  columns:
    - name: "USUBJID"
      label: "Subject ID"
      width: "1.5in"
      align: "left"

  pagination:
    rows_per_page: 40
    repeat_headers: true

  footnotes:
    - "Protocol: {study_id}"
    - "Population: {population_name}"
    - "Date format: DD-MON-YYYY"
```

---

## Edge Cases

### Long Free-Text Fields
- AETERM, CMTRT may be very long: truncate with "..." if exceeds column width
- Provide full text in appendix if truncation occurs

### Missing Dates in Listings
- Display as "MISSING" or "NK" per study convention
- Do not leave blank cells (ambiguous)

### Multi-Page Subjects
- When a subject spans multiple pages, repeat the subject ID column
- Use "Subject: {study_id}-{SITEID}-{SUBJID} (continued)" on subsequent pages

### Visit Date Formatting
- Standard format: DDMONYYYY (e.g., 15JAN2024)
- Partial dates: Document imputation (e.g., "UNK-JAN-2024")

---

## Integration Points

### Upstream Skills
- `/tfl-table-generator` -- Generates summary tables for comparison
- `/tfl-template-builder` -- Provides listing templates
- `/adam-adsl-builder` -- ADSL for subject-level data

### Downstream Skills
- `/tfl-formatter` -- Final RTF/PDF formatting
- `/tfl-qc-validator` -- Validates listing accuracy

### Related Skills
- `/data-quality` -- Quality checks on listing data
- `/workflow` -- Track listing completion

---

## Evaluation Criteria

**Mandatory:**
- All SAP-mandated listings produced
- Subject-level data accurate and traceable to source
- Sort order matches SAP specification
- Date formatting consistent

**Recommended:**
- Listings sorted per protocol with configurable sort order
- Highlighting of clinically significant values
- Page breaks at logical boundaries (per subject, per site)

---

## Critical Constraints

**Never:**
- Suppress subjects or records from listings without documentation
- Alter data values during listing generation
- Omit required columns per SAP specification
- Use inconsistent date formatting across listings

**Always:**
- Validate source datasets before listing generation
- Include all required footnotes
- Sort data per SAP specification
- Apply consistent formatting per template
- Generate traceable, reproducible results

---

## Examples

### Generate All Listings
```bash
python csp-skills/layer-5-tfl/tfl-listing-generator/script.py \
  --input output/adam/ \
  --output output/tfl/listings/ \
  --type all
```

### AE Listing Only
```bash
python csp-skills/layer-5-tfl/tfl-listing-generator/script.py \
  --input output/adam/ \
  --output output/tfl/listings/ae-listing.rtf \
  --type ae
```
