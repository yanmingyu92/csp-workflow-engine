---
name: tfl-template-builder
description: Build reusable TFL programming templates from approved shells. Triggers on "TFL shell", "mock-up", "table shell", "listing shell", "figure shell", "TFL template".
version: "2.0"
user-invocable: true
context: fork
model: sonnet
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
argument-hint: "[options] -- --input <shells-dir> --output <template-path> --format [yaml|python|r]"
---

## Runtime Configuration (Step 0)

Resolve configuration in order:
1. `$ARGUMENTS` (highest precedence)
2. `output/tfl/shells/` -- approved shell files
3. `ops/approved-shells.yaml` -- list of approved shells
4. `specs/tfl-templates.yaml` -- existing templates

```yaml
config_resolution:
  study_id: "$ARGUMENTS.study_id || study-config.study_id"
  shell_dir: "$ARGUMENTS.input || 'output/tfl/shells/'"
  output_template: "$ARGUMENTS.output || 'specs/tfl-templates.yaml'"
  format: "$ARGUMENTS.format || 'yaml'"
```

## EXECUTE NOW
Parse $ARGUMENTS: --input, --output, --format, --dry-run
**START NOW.**

---

## Philosophy

**Templates standardize output generation.** Header/footer macros, statistical formatting, and pagination logic are encapsulated into reusable templates. This ensures consistency across all TFLs and reduces programming effort.

---

## Input/Output Specification

### Inputs (matching regulatory-graph.yaml node `tfl-shell-review`)
| Input | Format | Required | Source |
|-------|--------|----------|--------|
| Approved TFL shells | docx/xlsx/rtf | Yes | output/tfl/shells/ |
| Approved shell list | yaml | Yes | ops/approved-shells.yaml |
| Study configuration | yaml | Yes | specs/study-config.yaml |

### Outputs (matching regulatory-graph.yaml node `tfl-shell-review`)
| Output | Format | Path Pattern | Description |
|--------|--------|--------------|-------------|
| TFL programming templates | yaml | specs/tfl-templates.yaml | Reusable template definitions |

---

## Template Structure

### Header/Footer Macro Template
```yaml
header_template:
  left: "Protocol: {study_id}"
  center: ""
  right: "Confidential"

footer_template:
  left: "{table_id}"
  center: "Page {page} of {total_pages}"
  right: "Generated: {timestamp}"
```

### Table Template
```yaml
table_template:
  type: "table"
  rtf_specs:
    orientation: "Landscape"
    page_size: "Letter"
    margins: "1 inch"
    font: "Courier New 9pt"
    title_font: "Courier New 10pt Bold"
    max_rows_per_page: 35

  column_header_format:
    alignment: "center"
    border_bottom: "single 0.5pt"
    border_top: "single 1pt"

  body_format:
    alignment: "left for labels, center for data"
    row_spacing: "single"

  footnote_format:
    font: "Courier New 8pt"
    separator: "single 0.5pt line"
    required_notes:
      - "Protocol: {study_id}"
      - "Population: {population_name}"
      - "Source: {source_dataset}"
      - "N = number of subjects in treatment group"
```

### Listing Template
```yaml
listing_template:
  type: "listing"
  rtf_specs:
    orientation: "Portrait"
    page_size: "Letter"
    margins: "0.75 inch"
    font: "Courier New 8pt"
    max_rows_per_page: 45

  page_break_variable: "USUBJID"
  repeat_headers: true
  sort_order_notation: "USUBJID > VISIT > SEQ"
```

### Figure Template
```yaml
figure_template:
  type: "figure"
  output_specs:
    format: "PNG"
    dpi: 300
    width: "10 inches"
    height: "7 inches"

  title_specs:
    font: "sans-serif 12pt"
    position: "top center"

  axis_specs:
    label_font: "sans-serif 10pt"
    tick_font: "sans-serif 8pt"

  legend_specs:
    position: "bottom"
    font: "sans-serif 9pt"
```

---

## Output Schema

```yaml
template_output:
  study_id: "{study_id}"
  generated_at: "{ISO_8601}"
  templates:
    - template_id: "std-table"
      type: "table"
      format: "rtf"
      applies_to: ["Table 14.*"]
    - template_id: "std-listing"
      type: "listing"
      format: "rtf"
      applies_to: ["Listing 16.*"]
    - template_id: "std-figure"
      type: "figure"
      format: "png"
      applies_to: ["Figure 14.*"]
```

---

## Edge Cases

### Non-Standard Table Layouts
- Some SAP tables may require custom layouts not covered by standard templates
- Create custom template with justification documented
- Flag non-standard templates for review

### Mixed Orientation Requirements
- Some tables landscape, some portrait
- Template must specify orientation per TFL

---

## Integration Points

### Upstream Skills
- `/tfl-shell-reviewer` -- Provides approved shell list
- `/sap-parser` -- TFL requirements from SAP

### Downstream Skills
- `/tfl-table-generator` -- Uses templates for formatting
- `/tfl-formatter` -- Applies template formatting rules
- `/tfl-listing-generator` -- Uses listing templates

### Related Skills
- `/workflow` -- Track template building status

---

## Evaluation Criteria

**Mandatory:**
- Templates cover all approved shells
- Header/footer macros defined
- Page layout specifications complete

**Recommended:**
- Templates validated against sample output
- Pagination strategy embedded in templates

---

## Critical Constraints

**Never:**
- Build templates from unapproved shells
- Use inconsistent formatting across template types
- Hardcode treatment arm names in templates

**Always:**
- Use dynamic references for treatment arms and study identifiers
- Include all required footnote placeholders
- Generate templates from approved shells only
- Document template-to-shell mapping

---

## Examples

### Build Templates
```bash
python csp-skills/layer-5-tfl/tfl-template-builder/script.py \
  --input output/tfl/shells/ \
  --output specs/tfl-templates.yaml \
  --format yaml
```
