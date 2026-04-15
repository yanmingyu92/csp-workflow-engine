---
name: adrg-writer
description: Write ADaM Reviewers Guide (ADRG). Triggers on "ADRG", "ADaM reviewer", "ADaM reviewer guide", "ADaM reviewer's guide", "derivation documentation", "PhUSE ADRG".
version: "2.0"
user-invocable: true
context: fork
model: sonnet
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
argument-hint: "[options] -- --input, --output"
---

## Runtime Configuration (Step 0)

### Dynamic Config Resolution
```yaml
config_sources:
  - path: specs/study-config.yaml
    description: Study-level metadata, study ID, treatment arms
  - path: specs/adam-spec.yaml
    description: ADaM derivation specifications
  - path: specs/sap-parsed.yaml
    description: Analysis endpoint definitions
  - path: reports/adam-traceability-report.html
    description: Traceability report (evidence for derivations)
  - path: reports/p21-adam-report.xlsx
    description: P21 ADaM validation report

required_inputs:
  - type: dataset
    name: All ADaM datasets
    format: xpt
    path_pattern: "{adam-dir}/*.xpt"
  - type: report
    name: P21 ADaM validation report
    format: xlsx|html
    path_pattern: reports/p21-adam-report.xlsx
  - type: report
    name: Traceability report
    format: html|pdf
    path_pattern: reports/adam-traceability-report.html

output:
  - type: document
    name: ADaM Reviewer's Guide (ADRG)
    format: pdf
    path_pattern: "{output}"
```

Read: {adam-dir}/*.xpt, reports/p21-adam-report.xlsx, reports/adam-traceability-report.html, specs/adam-spec.yaml, specs/study-config.yaml
## EXECUTE NOW
Parse $ARGUMENTS: --adam-dir, --output, --p21-report, --traceability-report, --dry-run
**START NOW.**

---

## Philosophy
**The ADRG documents all ADaM derivation logic for FDA reviewer consumption.** Following the PhUSE ADRG template structure ensures completeness and regulatory acceptance. The ADRG is the primary document a reviewer uses to understand the analysis datasets.

**Key Principle:** Every derivation must be explained with sufficient detail for a statistical reviewer to reproduce the analysis. The ADRG complements Define.xml by providing narrative context that structured metadata cannot convey.

---

## Input/Output Specification
### Inputs (from regulatory-graph.yaml: adam-reviewer-guide)
| Input | Format | Required | Source |
|-------|--------|----------|--------|
| All ADaM datasets | xpt | Yes | adam-adsl, adam-adae, adam-adlb, etc. |
| P21 ADaM validation report | xlsx/html | Yes | p21-adam-validation |
| Traceability report | html/pdf | Yes | adam-traceability-check |

### Outputs (to regulatory-graph.yaml: adam-reviewer-guide)
| Output | Format | Path Pattern | Consumers |
|--------|--------|--------------|-----------|
| ADRG document | pdf | docs/adrg.pdf | esub-package-assembly, final submission |

---

## Script Execution
```bash
adrg-writer --adam-dir {adam-dir} --output {output} [--p21-report {p21-report}] [--traceability-report {traceability-report}] [--dry-run]
```

### Arguments
| Argument | Required | Description |
|----------|----------|-------------|
| `--adam-dir` | Yes | Directory containing ADaM XPT files |
| `--output` | Yes | Output path for ADRG document |
| `--p21-report` | No | P21 ADaM validation report path |
| `--traceability-report` | No | Traceability report path |
| `--dry-run` | No | Show ADRG outline without writing |

---

## PhUSE ADRG Template Structure

```yaml
adrg_sections:
  1_title_page:
    - Study title
    - Protocol number
    - Study ID from study config (not hardcoded)
    - Sponsor name
    - Date

  2_introduction:
    - Purpose of the ADRG
    - Scope of analysis datasets
    - Regulatory references (ICH E3, ICH E9, ADaM IG)

  3_study_design:
    - Study objectives
    - Treatment arms from study_config.treatment_arms (dynamic)
    - Analysis populations from study_config.population_definitions (dynamic)
    - Visit schedule overview

  4_dataset_descriptions:
    for_each_dataset:
      - Dataset name and label
      - Structure (ADSL, BDS, OCCDS)
      - Key variables
      - Number of records and subjects ({n_subjects} from data)
      - Merge/derivation logic summary

  5_derivation_details:
    for_each_derived_variable:
      - Variable name and label
      - SDTM source(s) from traceability report
      - Derivation algorithm (pseudocode or narrative)
      - Assumptions and deviations

  6_traceability_approach:
    - Summary of traceability methodology
    - Reference to traceability report
    - ADaM-to-SDTM mapping summary

  7_p21_issues:
    - Summary of P21 validation results
    - Justification for any warnings
    - Resolution status for each issue

  8_data_issues_and_notes:
    - Missing data handling
    - Partial date imputation rules
    - Non-standard variable justifications
    - Protocol deviations affecting analysis

  9_appendices:
    - Analysis population definitions (from SAP)
    - Treatment arm descriptions (from study config)
    - Variable listing with source traceability
```

---

## Key Content
```python
def generate_adrg(adam_dir, study_config, traceability_report, p21_report):
    """
    Generate ADRG content from ADaM datasets and supporting documents.

    1. Read study config for study metadata
    2. Read each ADaM dataset for structure and variable info
    3. Read traceability report for derivation evidence
    4. Read P21 report for issue documentation
    5. Generate narrative sections per PhUSE template
    """
    study_id = study_config.get('study_id')  # Dynamic, not hardcoded

    adrg = ADRGDocument(study_id=study_id)

    # Section 2: Introduction
    adrg.add_introduction(study_config)

    # Section 3: Study Design
    adrg.add_study_design(study_config)

    # Section 4: Dataset Descriptions
    for adam_file in glob(f"{adam_dir}/*.xpt"):
        ds = read_xpt(adam_file)
        adrg.add_dataset_description(
            name=Path(adam_file).stem.upper(),
            structure=classify_structure(ds),
            key_vars=derive_key_variables(ds),
            n_records=len(ds),
            n_subjects=ds['USUBJID'].nunique()
        )

    # Section 5: Derivation Details
    adrg.add_derivations(traceability_report)

    # Section 7: P21 Issues
    adrg.add_p21_issues(p21_report)

    return adrg
```

---

## Output Schema

```yaml
adrg_document:
  format: pdf
  template: "PhUSE ADRG Template"
  sections:
    - title_page:
        study_id: "{study_id from study config}"
        study_title: "{study_title from study config}"
    - introduction:
        purpose: "Document ADaM dataset derivation logic"
        scope: "All ADaM datasets"
    - study_design:
        treatment_arms: "from study_config.treatment_arms"
        populations: "from study_config.population_definitions"
    - dataset_descriptions: "one section per ADaM dataset"
    - derivation_details: "one section per derived variable"
    - traceability: "methodology and evidence"
    - p21_issues: "justification for warnings"
    - data_notes: "imputation rules, non-standard variables"
    - appendices: "population definitions, variable listing"
```

---

## Edge Cases

### Empty or Minimal ADaM Datasets
```python
# If an ADaM dataset has very few records:
# - Still document in ADRG
# - Note small sample size
# - May indicate data issue
```

### Non-Standard Variables
```python
# If ADaM has non-standard variables:
# - Must justify in ADRG section on deviations
# - Explain why standard variable was insufficient
# - Document naming convention
```

### P21 Warnings Requiring Justification
```python
# For each P21 warning:
# - Describe the issue
# - Explain why it is acceptable
# - Reference protocol or SAP if applicable
# - Mark resolution status (accepted, fixed, waived)
```

### Missing Traceability for Some Variables
```python
# If traceability is incomplete:
# - Document known derivation even if automated check failed
# - Provide manual traceability evidence
# - Flag for reviewer attention
```

---

## Integration Points
### Upstream Skills
- `/adam-adsl-builder` -- ADSL dataset for ADRG documentation
- `/adam-adae-builder` -- ADAE dataset for ADRG documentation
- `/adam-adlb-builder` -- ADLB dataset for ADRG documentation
- `/adam-adtte-builder` -- ADTTE dataset for ADRG documentation
- `/adam-traceability-checker` -- Traceability evidence
- `/p21-adam-validation` -- P21 validation results

### Downstream Skills
- `/esub-assembler` -- ADRG included in eCTD package
- `/define-xml-adam` -- ADRG complements Define.xml

### Related Skills
- `/define-draft-builder` -- ADaM metadata for Define.xml

---

## Evaluation Criteria
**Mandatory:**
- All ADaM datasets described
- Derivation logic documented for key variables
- Traceability approach explained
- P21 issues addressed
- Study ID and treatment arms from study config (not hardcoded)

**Recommended:**
- Follows PhUSE ADRG template structure
- Population definitions included from study config
- Visual diagrams for complex derivations

---

## Critical Constraints
**Never:**
- Hardcode study ID, treatment arm names, or subject counts
- Omit P21 warning justifications
- Skip derivation documentation for any derived variable
- Use study-specific example data (use placeholders)

**Always:**
- Use dynamic references from study_config for all study-specific values
- Document all derivation logic narrative
- Include traceability evidence
- Address all P21 warnings with justification
- Generate traceable, reproducible results

---

## Examples
```bash
adrg-writer --adam-dir output/adam/ --output docs/adrg.pdf
```

### With Supporting Reports
```bash
adrg-writer --adam-dir output/adam/ --output docs/adrg.pdf --p21-report reports/p21-adam-report.xlsx --traceability-report reports/adam-traceability-report.html
```

### Expected Output
```
docs/adrg.pdf
+-- Title Page ({study_id}, {study_title})
+-- Introduction (purpose, scope)
+-- Study Design ({n_treatment_arms} arms from study config)
+-- Dataset Descriptions ({n_datasets} datasets)
+-- Derivation Details (per-variable derivation logic)
+-- Traceability Approach
+-- P21 Issue Justifications
+-- Data Issues and Notes
+-- Appendices
```
