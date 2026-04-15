---
name: tfl-figure-generator
description: Generate analysis figures (KM curves, forest plots, waterfall, spaghetti). Triggers on "figure", "plot", "Kaplan-Meier", "forest plot", "waterfall", "spaghetti plot".
version: "2.0"
user-invocable: true
context: fork
model: sonnet
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
argument-hint: "[options] -- --input <adam-dir> --output <output-dir> --type [km|forest|waterfall|all]"
---

## Runtime Configuration (Step 0)

Resolve configuration in order:
1. `$ARGUMENTS` (highest precedence)
2. `specs/table-specs.yaml` -- figure specifications
3. `specs/tfl-templates.yaml` -- figure styling templates
4. `specs/study-config.yaml` -- study metadata, treatment arms

```yaml
config_resolution:
  study_id: "$ARGUMENTS.study_id || study-config.study_id"
  treatment_arms: "study-config.treatment_arms"
  input_dir: "$ARGUMENTS.input || 'output/adam/'"
  output_dir: "$ARGUMENTS.output || 'output/tfl/figures/'"
  figure_type: "$ARGUMENTS.type || 'all'"
  resolution: "$ARGUMENTS.dpi || 300"
```

## EXECUTE NOW
Parse $ARGUMENTS: --input, --output, --type, --dpi, --dry-run
**START NOW.**

---

## Philosophy

**Figures must be publication-quality (300+ DPI).** Kaplan-Meier, forest plots, and waterfall plots follow specific conventions established in the clinical trial literature. Every figure must have clear axis labels, legends, titles, and footnotes. Figures are included in the Clinical Study Report per ICH E3 Section 12.

---

## Input/Output Specification

### Inputs (matching regulatory-graph.yaml node `tfl-figure-generation`)
| Input | Format | Required | Source |
|-------|--------|----------|--------|
| ADaM datasets | xpt | Yes | output/adam/*.xpt |
| Figure specifications | yaml | Yes | specs/table-specs.yaml |
| TFL templates | yaml | Yes | specs/tfl-templates.yaml |

### Outputs (matching regulatory-graph.yaml node `tfl-figure-generation`)
| Output | Format | Path Pattern | Description |
|--------|--------|--------------|-------------|
| Analysis figures | png/pdf | output/tfl/figures/ | Publication-quality figures |

---

## Figure Types

### 1. Kaplan-Meier Survival Curves
```yaml
km_figure:
  title: "Figure {figure_id}: Kaplan-Meier Plot of {endpoint_name}"
  source_dataset: "adtte.xpt"
  required_vars: ["AVAL", "CNSR", "TRTA", "STARTDT"]

  plot_specs:
    x_axis: "Time ({time_unit})"
    y_axis: "Probability of Survival"
    x_range: "[0, max_time]"
    y_range: "[0, 1.0]"
    line_styles: "distinct per treatment group (color + pattern)"
    censor_marks: "|"  # Vertical tick marks for censored observations
    at_risk_table: true  # Number at risk below the plot
    confidence_bands: false  # Optional CI shading
    median_lines: true  # Horizontal line at 0.5, vertical at median

  statistics_overlay:
    - "Log-rank p-value"
    - "Median survival time per group"
    - "Hazard ratio (95% CI) if applicable"

  legend:
    position: "bottom or right"
    labels: "treatment groups from study config"
```

### 2. Forest Plot
```yaml
forest_plot:
  title: "Figure {figure_id}: Forest Plot of Subgroup Analysis"
  source_dataset: "adeff.xpt or adsl.xpt"

  plot_specs:
    x_axis: "Hazard Ratio (95% CI)"  # or Odds Ratio
    reference_line: 1.0  # Vertical line at null value
    labels_left: "Subgroup labels"
    labels_right: "N, Event %, HR (95% CI)"
    overall_row: true  # Overall estimate at top or bottom
    square_size: "weighted by subgroup size"
    colors: "distinct per treatment comparison"

  subgroups:
    - "Overall"
    - "Age < {cutoff} vs >= {cutoff}"
    - "Sex: Male vs Female"
    - "Race: White vs Non-White"
    # ... from SAP subgroup analysis plan
```

### 3. Waterfall Plot
```yaml
waterfall_plot:
  title: "Figure {figure_id}: Waterfall Plot of Best Overall Response"
  source_dataset: "adeff.xpt"

  plot_specs:
    x_axis: "Subjects (sorted by change)"
    y_axis: "Percent Change from Baseline"
    y_range: "[-100, max_change]"
    bars: "one per subject, colored by response category"
    reference_lines: ["-30%", "20%"]  # Response thresholds per protocol

  color_categories:
    CR: "dark green"  # Complete Response
    PR: "light green"  # Partial Response
    SD: "gray"         # Stable Disease
    PD: "red"           # Progressive Disease
```

### 4. Spaghetti Plot
```yaml
spaghetti_plot:
  title: "Figure {figure_id}: Individual Subject Trajectories"
  source_dataset: "adlb.xpt or adeff.xpt"

  plot_specs:
    x_axis: "Visit/Time"
    y_axis: "{parameter_name} Value"
    lines: "one per subject, semi-transparent"
    by_group: "treatment arm (faceted or colored)"
    mean_line: "bold overlay showing group mean"

  styling:
    line_alpha: 0.3  # Semi-transparent for readability
    mean_line_width: 2
    mean_line_alpha: 1.0
```

---

## Output Quality Standards

```yaml
quality_standards:
  resolution:
    minimum: 300 DPI
    recommended: 600 DPI for print

  file_formats:
    primary: "PNG (300+ DPI)"
    alternative: "PDF (vector)"
    never: "JPEG (lossy)"

  color_palette:
    primary: "colorblind-friendly palette"
    recommended_palettes: ["Okabe-Ito", "Color Brewer qualitative"]
    grayscale_safe: true  # Must be readable in B&W

  dimensions:
    width: "7-10 inches"
    height: "5-7 inches"
    aspect_ratio: "maintained (no distortion)"

  fonts:
    title: "sans-serif, 12pt"
    axis_labels: "sans-serif, 10pt"
    tick_labels: "sans-serif, 8pt"
    legend: "sans-serif, 9pt"
    footnotes: "sans-serif, 8pt"
```

---

## Output Schema

```yaml
figure_output:
  figure_id: "Figure {n}"
  title: "{title}"
  source_datasets: ["adtte.xpt"]
  type: "km | forest | waterfall | spaghetti"
  format: "png"
  resolution: 300
  dimensions: "10x7 inches"
  file_path: "output/tfl/figures/figure-{n}-{name}.png"
  footnotes:
    - "Protocol: {study_id}"
    - "Population: {population_name}"
    - "{statistical_method_note}"
```

---

## Edge Cases

### Small Sample Sizes
- KM curves with few subjects: show individual data points
- Forest plot with subgroups <10: suppress or note "N too small"

### Censored Observations
- All censored observations must be marked on KM curves
- At-risk table must account for censoring

### Missing Data in Figures
- Subjects with missing values excluded from figure
- Document number of excluded subjects in footnote

### Multi-Page Figures
- Large forest plots may span multiple pages
- Continue subgroup rows with repeated column headers

---

## Integration Points

### Upstream Skills
- `/adam-adtte-builder` -- ADTTE for KM curves
- `/adam-adeff-builder` -- ADEFF for waterfall, forest plots
- `/adam-adlb-builder` -- ADLB for spaghetti plots
- `/tfl-shell-reviewer` -- Figure shell specifications

### Downstream Skills
- `/tfl-qc-validator` -- Validate figure accuracy
- `/tfl-comparator` -- Compare production vs QC figures

### Related Skills
- `/workflow` -- Track figure completion

---

## Evaluation Criteria

**Mandatory:**
- All SAP-mandated figures produced
- Axis labels and legends correct
- 300+ DPI resolution
- Colorblind-friendly palette

**Recommended:**
- Vector format (PDF) in addition to raster
- At-risk tables on KM plots
- Statistical annotations (p-values, HRs)

---

## Critical Constraints

**Never:**
- Generate figures below 300 DPI
- Use lossy formats (JPEG) for regulatory figures
- Distort aspect ratios
- Omit axis labels or legends
- Use color-only encoding (must work in grayscale)

**Always:**
- Use 300+ DPI resolution
- Include title, axis labels, and legend
- Add footnotes: protocol, population, method
- Use colorblind-friendly color palette
- Validate source data before plotting

---

## Examples

### Generate All Figures
```bash
python csp-skills/layer-5-tfl/tfl-figure-generator/script.py \
  --input output/adam/ \
  --output output/tfl/figures/ \
  --type all \
  --dpi 300
```

### KM Curve Only
```bash
python csp-skills/layer-5-tfl/tfl-figure-generator/script.py \
  --input output/adam/adtte.xpt \
  --output output/tfl/figures/km-overall-survival.png \
  --type km \
  --dpi 600
```
