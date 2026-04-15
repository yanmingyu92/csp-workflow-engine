---
name: tfl-table-generator
description: Generate analysis tables from ADaM datasets. Triggers on "table", "analysis table", "demographics table", "safety table", "efficacy table", "disposition table".
version: "2.0"
user-invocable: true
context: fork
model: sonnet
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
argument-hint: "[options] -- --input <adam-dir> --output <output-dir> --spec <table-spec>"
---

## Runtime Configuration (Step 0)

Resolve configuration in order:
1. `$ARGUMENTS` (highest precedence)
2. `output/adam/*.xpt` -- available ADaM datasets
3. `specs/table-specs.yaml` -- table specifications from SAP
4. `specs/sap-parsed.yaml` -- parsed SAP endpoints and methods
5. `output/tfl/shells/` -- approved table shells

```yaml
config_resolution:
  study_id: "$ARGUMENTS.study_id || study-config.study_id"
  treatment_arms: "study-config.treatment_arms"
  input_dir: "$ARGUMENTS.input || 'output/adam/'"
  output_dir: "$ARGUMENTS.output || 'output/tfl/tables/'"
  table_spec: "$ARGUMENTS.spec || 'specs/table-specs.yaml'"
```

## EXECUTE NOW
Parse $ARGUMENTS: --input, --output, --spec, --format, --dry-run
**START NOW.**

---

## Philosophy

**Analysis tables follow SAP specifications.** Statistical formatting (p-values, CIs, descriptive statistics) must be precise and reproducible. Every table traces to the SAP, uses validated ADaM datasets, and matches the approved table shell exactly.

**Key Principle:** Tables must be independently reproducible. The double-programming QC process requires that two independent programmers produce identical results using the same specifications.

---

## Input/Output Specification

### Inputs (matching regulatory-graph.yaml node `tfl-table-generation`)
| Input | Format | Required | Source |
|-------|--------|----------|--------|
| ADaM datasets | xpt | Yes | output/adam/*.xpt |
| Table specifications | yaml | Yes | specs/table-specs.yaml |
| TFL programming templates | yaml | Yes | specs/tfl-templates.yaml |
| SAP parsed specs | yaml | Yes | specs/sap-parsed.yaml |

### Outputs (matching regulatory-graph.yaml node `tfl-table-generation`)
| Output | Format | Path Pattern | Description |
|--------|--------|--------------|-------------|
| Analysis tables | rtf/pdf | output/tfl/tables/ | Formatted analysis tables |

---

## Table Types

### Descriptive Statistics Tables
```python
def generate_descriptive_table(adsl, variables, treatment_var='TRT01A'):
    """
    Generate descriptive statistics table (e.g., demographics).

    Continuous variables: n, Mean, SD, Median, Min, Max
    Categorical variables: n (%)
    """
    results = {}
    for var in variables:
        if is_continuous(var):
            stats = compute_continuous_stats(adsl, var, treatment_var)
        else:
            stats = compute_categorical_stats(adsl, var, treatment_var)
        results[var] = stats
    return results
```

### Frequency Tables (AE, Disposition)
```python
def generate_frequency_table(adae, group_var, treatment_var='TRTA'):
    """
    Generate frequency count table (e.g., AE by SOC/PT).

    Statistics: n, % by treatment group
    Sorted by SOC, then PT alphabetically
    Include total column
    """
    freq = adae.groupby([group_var, treatment_var]).size().unstack(fill_value=0)
    pct = freq.div(freq.sum(axis=0), axis=1) * 100
    return freq, pct
```

### Inferential Statistics Tables (Efficacy)
```python
def generate_inferential_table(adam_bds, endpoint, method='cmh'):
    """
    Generate table with statistical tests (p-values, CIs).

    Methods:
    - CMH: Cochran-Mantel-Haenszel (categorical, stratified)
    - ANCOVA: Analysis of covariance (continuous, adjusted)
    - Logistic: Logistic regression (binary endpoints)
    - Log-rank: Time-to-event comparison
    """
    if method == 'cmh':
        result = cmh_test(adam_bds, endpoint, strata=['SITEID'])
    elif method == 'ancova':
        result = ancova(adam_bds, endpoint, covariates=['BASE'])
    return result
```

---

## Statistical Methods Reference

### Continuous Variable Statistics
```python
def compute_continuous_stats(data, variable, treatment_var):
    """
    Compute: n, Mean (SD), Median, Range

    Formatting:
    - n: integer
    - Mean (SD): "XX.X (XX.XX)" -- 1 decimal for mean, 2 for SD
    - Median: "XX.X" -- 1 decimal
    - Range: "XX-XX" -- integer or 1 decimal
    """
    stats = {}
    for trt in data[treatment_var].unique():
        subset = data[data[treatment_var] == trt][variable].dropna()

        stats[trt] = {
            'n': len(subset),
            'mean_sd': f"{subset.mean():.1f} ({subset.std(ddof=1):.2f})",
            'median': f"{subset.median():.1f}",
            'range': f"{subset.min():.0f}-{subset.max():.0f}"
        }

    return stats
```

### P-Value Methods
```python
# CMH Test (Cochran-Mantel-Haenszel)
# Use for: Categorical comparisons, stratified
# Python: statsmodels StratifiedTable

# Fisher's Exact Test
# Use for: Small sample sizes, 2x2 tables
# Python: scipy.stats.fisher_exact

# ANCOVA
# Use for: Continuous endpoints, baseline-adjusted
# Python: statsmodels OLS

# Log-Rank Test
# Use for: Time-to-event comparisons
# Python: lifelines.statistics.logrank_test
```

---

## Table Formatting Standards

### RTF Formatting
```yaml
rtf_formatting:
  page_size: "Letter"
  orientation: "Landscape"
  margins: "1 inch all sides"
  font: "Courier New 9pt"
  header_font: "Courier New 10pt Bold"
  title_font: "Courier New 10pt Bold"

  borders:
    top: "Single line above column headers"
    bottom: "Single line below last data row"
    header_separator: "Single line below column headers"

  pagination:
    max_rows_per_page: 35
    repeat_headers: true
    page_numbers: "Page X of Y"

  footnotes:
    font: "Courier New 8pt"
    separator: "Single line above footnotes"
    required_notes:
      - "Protocol: {study_id}"
      - "Population: {population_name}"
      - "N = number of subjects in treatment group"
```

### Column Headers (Dynamic)
```
Standard format (derived from study config treatment arms):
                                    {Arm1}        {Arm2}        ...    Total
                                    (N={n1})      (N={n2})      ...    (N={nt})
─────────────────────────────────────────────────────────────────────────────────
```

### Decimal Precision Rules
```yaml
precision:
  continuous:
    n: "integer"
    mean: "1 decimal"
    sd: "2 decimal (in parentheses after mean)"
    median: "1 decimal"
    range: "integer or 1 decimal"
  categorical:
    n: "integer"
    percent: "1 decimal"
  inferential:
    p_value: "4 decimal places (e.g., 0.0123)"
    ci: "2 decimal places (e.g., 0.12, 0.34)"
    estimate: "3 decimal places"
```

---

## Output Schema

```yaml
table_output:
  table_id: "Table 14.1.3"
  title: "Demographics by Treatment Group ({population_name})"
  population: "SAFFL"
  source_dataset: "ADSL"
  format: "rtf"

  columns:
    - label: "Statistic"
      align: "left"
    - label: "treatment groups from study config"
      align: "center"
    - label: "Total (N={n_total})"
      align: "center"

  rows:
    - block: "Age (years)"
      type: "continuous"
      variable: "AGE"
      statistics: ["n", "Mean (SD)", "Median", "Range"]
    - block: "Age Group"
      type: "categorical"
      variable: "AGEGR1"
    - block: "Sex"
      type: "categorical"
      variable: "SEX"
    - block: "Race"
      type: "categorical"
      variable: "RACE"

  footnotes:
    - "Protocol: {study_id}"
    - "Population: {population_name} ({population_flag} = 'Y')"
    - "Source: ADSL dataset"
    - "N = number of subjects with non-missing data"
```

---

## Edge Cases

### Zero Counts in Categories
- Still show the row with "0 (0.0%)"
- Do not suppress empty categories unless the category was not collected

### Small Cell Sizes
- Categories with <5 subjects: still display n (%)
- Consider footnote about small cell sizes
- Use Fisher's exact test instead of CMH for p-values

### Missing Data Footnotes
- If >5% missing for any variable, add footnote

### Multi-Page Tables
- Repeat column headers on each page
- Add "(continued)" to title on subsequent pages

---

## Integration Points

### Upstream Skills
- `/adam-adsl-builder` -- ADSL for subject-level tables
- `/adam-adae-builder` -- ADAE for AE tables
- `/adam-adtte-builder` -- ADTTE for time-to-event tables
- `/tfl-shell-reviewer` -- Review shells before programming
- `/tfl-demographics` -- Specialized demographics table

### Downstream Skills
- `/tfl-qc-validator` -- Validate output against shell
- `/tfl-formatter` -- Final RTF/PDF formatting
- `/tfl-comparator` -- Compare production vs QC outputs
- `/tfl-double-programmer` -- Independent QC programming

### Related Skills
- `/data-quality` -- Check ADaM completeness before table generation
- `/workflow` -- Track table completion status

---

## Evaluation Criteria

**Mandatory:**
- All SAP-mandated tables produced
- Statistical results match independent QC
- Formatting matches shell specifications
- Correct N values in column headers (dynamically computed)
- Footnotes include protocol ({study_id}), population, source

**Recommended:**
- Consistent decimal precision across tables
- p-values reported for comparative analyses
- Tables numbered per SAP convention
- Empty categories handled consistently

---

## Critical Constraints

**Never:**
- Produce output without validation
- Use unvalidated ADaM datasets
- Modify statistics to match expected results
- Skip required footnotes
- Change table structure from shell specification
- Proceed if source datasets are missing

**Always:**
- Validate ADaM datasets before use
- Match table shell exactly
- Include footnotes: protocol ({study_id}), population, source, N definition
- Use proper decimal precision
- Sort rows per SAP specification
- Generate traceable, reproducible results

---

## Examples

### Basic Usage
```bash
python csp-skills/layer-5-tfl/tfl-table-generator/script.py \
  --input output/adam/ \
  --output output/tfl/tables/ \
  --spec specs/table-specs.yaml
```

### Single Table
```bash
python csp-skills/layer-5-tfl/tfl-table-generator/script.py \
  --input output/adam/ \
  --output output/tfl/tables/ae-summary.rtf \
  --shell output/tfl/shells/ae-summary-shell.rtf \
  --format rtf
```

### Expected Output
```
output/tfl/tables/
  table-14.1.3-demographics.rtf
  table-14.1.4-disposition.rtf
  table-14.2.1-ae-summary.rtf
  table-14.2.2-ae-by-socpt.rtf
  table-14.3.1-primary-efficacy.rtf
```
