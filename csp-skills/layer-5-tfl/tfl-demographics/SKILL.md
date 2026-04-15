---
name: demographics-table
description: Generate demographics summary table by treatment. Triggers on "demographics", "Table 1".
version: "2.0"
user-invocable: true
context: fork
model: haiku
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
argument-hint: "[options] -- --input <adsl-xpt> --output <output-path> --population <flag>"
---

## Runtime Configuration (Step 0)

Resolve configuration in order:
1. `$ARGUMENTS` (highest precedence)
2. `specs/study-config.yaml` -- treatment_arms, study_id, age_group_cutoffs
3. `specs/table-specs.yaml` -- table numbering, population definitions
4. `output/adam/adsl.xpt` -- source dataset

```yaml
config_resolution:
  study_id: "$ARGUMENTS.study_id || study-config.study_id"
  treatment_arms: "study-config.treatment_arms"
  population_flag: "$ARGUMENTS.population || 'SAFFL'"
  age_group_cutoff: "study-config.age_group_cutoff || 65"
  output_format: "$ARGUMENTS.format || 'rtf'"
```

## EXECUTE NOW
**START NOW.**

---

## Philosophy

**Demographics establish cohort comparability.** Table 1 confirms randomization balanced treatment groups. This table is critical for:
- Verifying randomization success
- Identifying potential selection bias
- Establishing baseline comparability for efficacy analyses
- Supporting regulatory submissions (FDA, EMA)

**Key Principle:** Demographics tables describe the study population, not test hypotheses. p-values are optional and should be interpreted cautiously.

---

## Input/Output Specification

### Inputs (matching regulatory-graph.yaml node `tfl-table-generation`)
| Input | Format | Required | Source |
|-------|--------|----------|--------|
| ADSL dataset | xpt | Yes | output/adam/adsl.xpt |
| Study configuration | yaml | Yes | specs/study-config.yaml |
| Table specifications | yaml | Yes | specs/table-specs.yaml |

### Outputs
| Output | Format | Path Pattern | Description |
|--------|--------|--------------|-------------|
| Demographics table | rtf/pdf/text | output/tfl/tables/demographics.rtf | Formatted table |

---

## Table Structure

### Standard Row Layout

| Row Label | Statistics | Format |
|-----------|------------|--------|
| **Age (years)** | n, Mean (SD), Median, Range | Continuous |
| **Age Group** | | |
| &nbsp;&nbsp;<{cutoff} | n (%) | Categorical |
| &nbsp;&nbsp;>={cutoff} | n (%) | Categorical |
| **Sex** | | |
| &nbsp;&nbsp;Male | n (%) | Categorical |
| &nbsp;&nbsp;Female | n (%) | Categorical |
| **Race** | | |
| &nbsp;&nbsp;White | n (%) | Categorical |
| &nbsp;&nbsp;Black or African American | n (%) | Categorical |
| &nbsp;&nbsp;Asian | n (%) | Categorical |
| &nbsp;&nbsp;Other | n (%) | Categorical |

### Column Headers (Dynamic from study config)

Column headers are derived from `study-config.treatment_arms` and actual ADSL subject counts:

```
{ARM_LABEL_1}    {ARM_LABEL_2}    ...    Total
(N={n_arm_1})    (N={n_arm_2})    ...    (N={n_total})
```

Where:
- `{ARM_LABEL_*}` comes from treatment arm definitions in study config
- `{n_arm_*}` is computed from ADSL filtered by population flag
- `{n_total}` is the sum across all treatment arms

---

## Statistics Formulas

### Continuous Variables (Age)
```
n = count of non-missing values
Mean = sum(values) / n
SD = sqrt(sum((value - mean)^2) / (n-1))
Median = middle value when sorted
Range = f"{min} - {max}"
```

### Categorical Variables (Sex, Race, Age Group)
```
n = count of subjects in category
% = (n / N_treatment) * 100, rounded to 1 decimal
```

### Age Group Derivation
```python
cutoff = study_config.get('age_group_cutoff', 65)
if age < cutoff:
    age_group = f"<{cutoff}"
else:
    age_group = f">={cutoff}"
```

---

## CDISC Controlled Terminology References

### SEX (CDISC CT C66731)
| Raw Value | CDISC CT | Label |
|-----------|----------|-------|
| M, Male, 1 | M | Male |
| F, Female, 2 | F | Female |
| U, Unknown, 0 | U | Unknown |
| UN | UN | Undifferentiated |

### RACE (CDISC CT C74457)
| CDISC CT Value | Label |
|----------------|-------|
| WHITE | White |
| BLACK OR AFRICAN AMERICAN | Black or African American |
| ASIAN | Asian |
| AMERICAN INDIAN OR ALASKA NATIVE | American Indian or Alaska Native |
| NATIVE HAWAIIAN OR OTHER PACIFIC ISLANDER | Native Hawaiian or Other Pacific Islander |
| MULTIPLE | Multiple |
| OTHER | Other |
| UNKNOWN | Unknown |

### ETHNIC (CDISC CT C66790)
| CDISC CT Value | Label |
|----------------|-------|
| HISPANIC OR LATINO | Hispanic or Latino |
| NOT HISPANIC OR LATINO | Not Hispanic or Latino |
| NOT REPORTED | Not Reported |
| UNKNOWN | Unknown |

---

## Output Schema

```yaml
output_format:
  type: table
  formats: [rtf, pdf, text]

table_structure:
  title: "Table 14.1.3: Demographics by Treatment Group ({population_name})"
  columns:
    - row_label: string
    - treatment_groups: "dynamic from study config"
    - total: string

rows:
  - row_label: "Age (years)"
    statistics:
      - n: integer
      - mean_sd: "XX.X (XX.X)"
      - median: "XX.X"
      - range: "XX-XX"
  - row_label: "  <{cutoff}"
    statistics:
      - n: integer
      - percent: "XX.X%"
```

---

## Edge Cases

### Missing Values
- Exclude from n count but include in denominator N
- Report missing count in footnotes if >5%

### Age Calculation
```python
# From ADSL with BRTHDAT and reference date
if BRTHDAT is missing:
    age = ADSL.AGE  # Use pre-calculated age
else:
    age = int((reference_date - BRTHDAT).days / 365.25)
    ageu = "YEARS"
```

### Race Grouping
- Map all non-standard race values to "Other"
- "MULTIPLE" race maps to "Multiple" (combine with "Other" if low count)
- "UNKNOWN" or missing maps to "Unknown" (separate row)

### Age Group Boundaries
- Protocol-specified cutoffs take precedence
- Default: <65 vs >=65 years
- For pediatric studies: <18, 18-64, >=65

---

## Integration Points

### Upstream Skills
- `/adam-adsl-builder` -- Source dataset with AGE, SEX, RACE, TRT01P
- `/study-setup` -- Treatment arm definitions, population flags
- `/sap-parser` -- Population definitions (ITT, Safety)

### Downstream Skills
- `/tfl-formatter` -- Final formatting (RTF, PDF)
- `/tfl-qc-validator` -- Validate output against shell
- `/tfl-shell-reviewer` -- Review against SAP shells

### Related Skills
- `/data-quality` -- Check ADSL completeness before table generation
- `/workflow` -- Track table completion status

---

## Evaluation Criteria

**Mandatory:**
- Age, Sex, Race by treatment group
- All required variables present in ADSL
- Correct N values in column headers (computed dynamically)
- Statistics calculated with proper precision

**Recommended:**
- p-values for group comparisons (if requested)
- Ethnicity row if collected
- Age group breakdown consistent with protocol
- Missing value footnote if applicable

---

## Critical Constraints

**Never:**
- Calculate statistics before validating population flags
- Include p-values without statistical justification
- Use non-CDISC controlled terminology for SEX, RACE, ETHNIC
- Output table without column headers with dynamically computed N values
- Mix continuous and categorical statistics in the same row
- Proceed if ADSL dataset is missing or empty
- Change age group definitions without protocol specification

**Always:**
- Validate ADSL dataset exists with required variables (AGE, SEX, RACE, TRT01P)
- Use population flag for filtering (default: SAFFL)
- Calculate all statistics with proper precision (1 decimal for %, 1 decimal for continuous)
- Format output per table shell specification
- Include table number and title
- Add footnotes: protocol ({study_id}), sponsor, analysis population, data cutoff
- Document any deviations from standard format

---

## Examples

### Basic Usage
```bash
python csp-skills/layer-5-tfl/tfl-demographics/script.py \
  --input output/adam/adsl.xpt \
  --output output/tfl/tables/demographics.rtf
```

### With Study Config
```bash
python csp-skills/layer-5-tfl/tfl-demographics/script.py \
  --input output/adam/adsl.xpt \
  --output output/tfl/tables/demographics.rtf \
  --study-config specs/study-config.yaml \
  --population SAFFL
```

### Expected Output Format
```
Table 14.1.3: Demographics by Treatment Group (Safety Population)

                        {Arm1}        {Arm2}        ...    Total
                        (N={n1})      (N={n2})      ...    (N={nt})
Age (years)
  n                    {n}           {n}           ...    {n}
  Mean (SD)            XX.X (XX.X)   XX.X (XX.X)   ...    XX.X (XX.X)
  Median               XX.X          XX.X          ...    XX.X
  Range                XX-XX         XX-XX         ...    XX-XX
Age Group
  <{cutoff}            XX (XX.X%)    XX (XX.X%)    ...    XX (XX.X%)
  >={cutoff}           XX (XX.X%)    XX (XX.X%)    ...    XX (XX.X%)
Sex
  Male                 XX (XX.X%)    XX (XX.X%)    ...    XX (XX.X%)
  Female               XX (XX.X%)    XX (XX.X%)    ...    XX (XX.X%)
Race
  White                XX (XX.X%)    XX (XX.X%)    ...    XX (XX.X%)
  Black or African
    American           XX (XX.X%)    XX (XX.X%)    ...    XX (XX.X%)
  Asian                XX (XX.X%)    XX (XX.X%)    ...    XX (XX.X%)
  Other                XX (XX.X%)    XX (XX.X%)    ...    XX (XX.X%)
```
