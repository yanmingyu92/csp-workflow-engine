---
name: tfl-formatter
description: Format TFL outputs with headers, footnotes, pagination per regulatory standards. Triggers on "table", "analysis table", "TFL format", "RTF format", "pagination", "footnotes".
version: "2.0"
user-invocable: true
context: fork
model: sonnet
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
argument-hint: "[options] -- --input <tfl-dir> --output <formatted-dir> --format [rtf|pdf|both]"
---

## Runtime Configuration (Step 0)

Resolve configuration in order:
1. `$ARGUMENTS` (highest precedence)
2. `specs/tfl-templates.yaml` -- formatting templates from shell review
3. `specs/study-config.yaml` -- study metadata, sponsor name
4. `specs/sap-parsed.yaml` -- table numbering and titles

```yaml
config_resolution:
  study_id: "$ARGUMENTS.study_id || study-config.study_id"
  sponsor: "$ARGUMENTS.sponsor || study-config.sponsor"
  input_dir: "$ARGUMENTS.input || 'output/tfl/tables/'"
  output_dir: "$ARGUMENTS.output || 'output/tfl/formatted/'"
  format: "$ARGUMENTS.format || 'rtf'"
  template: "$ARGUMENTS.template || 'specs/tfl-templates.yaml'"
```

## EXECUTE NOW
Parse $ARGUMENTS: --input, --output, --format, --template, --dry-run
**START NOW.**

---

## Philosophy

**Consistent formatting across all TFLs ensures professional presentation and regulatory compliance.** Page breaks, margins, fonts, and footnotes are not cosmetic -- they are required by FDA and ICH guidelines. Every TFL must follow the same formatting standards so that reviewers can focus on content, not layout inconsistencies.

---

## Input/Output Specification

### Inputs (matching regulatory-graph.yaml node `tfl-table-generation` downstream)
| Input | Format | Required | Source |
|-------|--------|----------|--------|
| Unformatted TFL outputs | rtf/text | Yes | output/tfl/tables/ |
| TFL formatting templates | yaml | Yes | specs/tfl-templates.yaml |
| Study configuration | yaml | Yes | specs/study-config.yaml |

### Outputs
| Output | Format | Path Pattern | Description |
|--------|--------|--------------|-------------|
| Formatted TFLs | rtf/pdf | output/tfl/formatted/ | Publication-ready outputs |
| Formatting log | yaml | ops/tfl-format-log.yaml | Applied formatting record |

---

## RTF Formatting Standards

### Page Layout
```yaml
page_layout:
  size: "Letter (8.5 x 11 inches)"
  orientation:
    tables: "Landscape"       # Standard for multi-column tables
    listings: "Portrait"      # Standard for narrow listings
    figures: "Landscape"      # Standard for plots
  margins:
    top: "1.0 inch"
    bottom: "1.0 inch"
    left: "1.0 inch"
    right: "1.0 inch"
  header_margin: "0.5 inch"
  footer_margin: "0.5 inch"
```

### Font Specifications
```yaml
fonts:
  title:
    family: "Courier New"
    size: "10pt"
    weight: "Bold"
    color: "Black"

  column_header:
    family: "Courier New"
    size: "9pt"
    weight: "Bold"
    color: "Black"

  body_text:
    family: "Courier New"
    size: "9pt"
    weight: "Normal"
    color: "Black"
    # Fixed-width ensures column alignment

  footnotes:
    family: "Courier New"
    size: "8pt"
    weight: "Normal"
    color: "Black"

  page_number:
    family: "Courier New"
    size: "8pt"
    weight: "Normal"
    alignment: "center"
    format: "Page X of Y"
```

### Border Rules
```yaml
borders:
  above_column_headers:
    style: "single"
    width: "1pt"
    color: "Black"

  below_column_headers:
    style: "single"
    width: "0.5pt"
    color: "Black"

  below_last_data_row:
    style: "single"
    width: "1pt"
    color: "Black"

  above_footnotes:
    style: "single"
    width: "0.5pt"
    color: "Black"

  no_borders:
    - "Between data rows"
    - "Around individual cells"
    - "Around the entire table"
```

### Pagination Rules
```yaml
pagination:
  max_rows_per_page: 35
  repeat_on_each_page:
    - "Title"
    - "Column headers"
    - "N header row"
  continued_title_suffix: " (continued)"
  page_numbering: "Page X of Y"
  page_number_position: "bottom center"
  min_orphan_rows: 3  # Minimum rows before page break
  min_widow_rows: 3   # Minimum rows after page break
```

### Header/Footer Templates
```yaml
header:
  left: "Protocol: {study_id}"
  center: ""
  right: "Confidential"

footer:
  left: ""
  center: "Page {page} of {total_pages}"
  right: ""
```

---

## Title and Footnote Standards

### Title Format
```
{table_id}: {table_title} ({population_name})
```

### Required Footnotes (in order)
1. Protocol: {study_id}
2. Population: {population_name} ({population_flag} = 'Y')
3. Source: {source_dataset} dataset
4. N = number of subjects in treatment group
5. Variable-specific notes (e.g., "Age derived from ADSL.AGE")
6. Statistical method notes (if applicable)
7. Data cutoff: {data_cut_date}

---

## Output Schema

```yaml
formatting_result:
  study_id: "{study_id}"
  formatted_at: "{ISO_8601}"
  template_used: "specs/tfl-templates.yaml"

  outputs:
    - tfl_id: "table-14.1.3"
      input: "output/tfl/tables/demographics-raw.rtf"
      output: "output/tfl/formatted/table-14.1.3-demographics.rtf"
      pages: "{n_pages}"
      format: "rtf"
      status: "SUCCESS"
```

---

## Edge Cases

### Wide Tables Exceeding Page Width
- Reduce font size to 8pt (minimum)
- Switch to landscape orientation
- Split table into multiple parts if still too wide
- Consider abbreviating column headers

### Tables with Many Small Categories
- Consolidate categories with <1% into "Other" if specified by SAP
- Maintain consistent pagination across similar tables

### Unicode Characters in Data
- Ensure RTF encoding supports special characters
- Convert non-RTF-safe characters to nearest equivalent

---

## Integration Points

### Upstream Skills
- `/tfl-table-generator` -- Produces unformatted tables
- `/tfl-listing-generator` -- Produces unformatted listings
- `/tfl-shell-reviewer` -- Provides formatting templates
- `/tfl-template-builder` -- Builds reusable formatting macros

### Downstream Skills
- `/tfl-qc-validator` -- Validates formatted output
- `/tfl-comparator` -- Compares formatted outputs

### Related Skills
- `/workflow` -- Track formatting completion

---

## Evaluation Criteria

**Mandatory:**
- All TFLs formatted per template specifications
- Consistent fonts, margins, borders across all outputs
- Correct pagination with repeated headers
- All required footnotes present

**Recommended:**
- Consistent decimal precision across tables
- Page numbering in "Page X of Y" format
- Professional quality suitable for regulatory submission

---

## Critical Constraints

**Never:**
- Output TFLs without applying formatting template
- Mix font families within the same document
- Suppress footnotes to fit more data on a page
- Modify data values during formatting

**Always:**
- Apply the formatting template to every TFL
- Include all required footnotes
- Use fixed-width fonts for column alignment
- Validate that output matches the approved shell layout
- Generate formatting log for traceability

---

## Examples

### Format All TFLs
```bash
python csp-skills/layer-5-tfl/tfl-formatter/script.py \
  --input output/tfl/tables/ \
  --output output/tfl/formatted/ \
  --format rtf \
  --template specs/tfl-templates.yaml
```

### Format Single TFL
```bash
python csp-skills/layer-5-tfl/tfl-formatter/script.py \
  --input output/tfl/tables/demographics-raw.rtf \
  --output output/tfl/formatted/table-14.1.3-demographics.rtf \
  --format rtf
```
