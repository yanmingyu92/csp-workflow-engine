---
name: sap-parser
description: Parse Statistical Analysis Plan (SAP) to extract endpoints, populations, statistical methods, and TFL shell specifications. Triggers on "SAP", "statistical analysis plan", "endpoints", "analysis populations", "ITT", "mITT", "safety population".
version: "1.0"
user-invocable: true
context: fork
model: sonnet
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
argument-hint: "[options] -- --input <sap-file> --output <output-path> --validate --dry-run"
---

## Runtime Configuration

### Config Resolution
1. Read ops/workflow-state.yaml for current workflow state
2. Read specs/study-config.yaml for study metadata (if exists)
3. If study-config missing, fall back to --study-config <path> argument
4. If neither available, log error and abort

### Required Reads
- ops/workflow-state.yaml -- Current workflow state
- specs/study-config.yaml -- Study configuration (if exists)
- SAP document (via --input argument)

### Arguments
| Argument | Required | Description |
|----------|----------|-------------|
| `--input` | Yes | Path to SAP document (PDF or DOCX) |
| `--output` | Yes | Output path for parsed YAML |
| `--study-config` | No | Path to study configuration |
| `--validate` | No | Validate extracted content only |
| `--dry-run` | No | Show what would be extracted without writing |

---

## Philosophy

**The SAP IS the specification.** Every table, figure, and listing in the CSR traces back to definitions in the SAP. This skill makes the SAP machine-readable, enabling automated spec generation and downstream programming.

**Three outputs:**
1. **Endpoints** -- Primary, secondary, exploratory with statistical methods
2. **Populations** -- ITT, mITT, PP, Safety with inclusion criteria
3. **TFL Shells** -- List of all tables, figures, listings with shells

---

## Input/Output Specification

### Inputs (from regulatory-graph.yaml node schema: sap-review)
| Input | Type | Format | Required | Source |
|-------|------|--------|----------|--------|
| SAP Document | document | pdf, docx | Yes | User-provided via --input |
| Study configuration | specification | yaml | No | specs/study-config.yaml or --study-config |
| Workflow state | metadata | yaml | No | ops/workflow-state.yaml |

### Outputs (to regulatory-graph.yaml node schema: sap-review)
| Output | Type | Format | Path Pattern |
|--------|------|--------|-------------|
| Parsed SAP specifications | specification | yaml | specs/sap-parsed.yaml |
| TFL shell list | specification | yaml | specs/sap-parsed.yaml (tfl_shells section) |

---

## Extraction Targets

### Primary Endpoints

Extract for each endpoint:
- Endpoint name and description
- Statistical hypothesis (null/alternative)
- Analysis method (e.g., "CMH test", "ANOVA", "log-rank")
- Multiplicity adjustment strategy
- Analysis population
- Data sources (ADaM datasets)

### Secondary Endpoints

Same structure as primary endpoints.

### Analysis Populations

Extract for each population:
- Population name (ITT, mITT, PP, Safety)
- Inclusion criteria
- Exclusion criteria (if specified)
- Derived from (SDTM/ADaM variables)

### Statistical Methods

Catalog all methods:
- Method name
- When used (endpoint type)
- Parameters (alpha, CI levels)
- Assumptions

### TFL Shells

Extract shell appendix:
- Table/Figure/Listing number
- Title
- Population
- Analysis purpose

---

## Output Schema

```yaml
schema_version: 1
sap_metadata:
  study_id: "{study_id} from study config"
  document_title: "{study_title}"
  document_version: "{version if available}"
  extraction_date: "{extraction_date}"

endpoints:
  primary:
    - id: "{endpoint_id}"
      name: "{endpoint_name}"
      description: "{endpoint_description}"
      hypothesis:
        null: "{H0}"
        alternative: "{H1}"
      method: "{statistical_method}"
      population: "{analysis_population}"
      dataset: "{ADaM_dataset}"
      multiplicity: "{adjustment_strategy}"
      page_ref: "{SAP_page_number}"
  secondary:
    - id: "{endpoint_id}"
      # Same structure as primary

populations:
  - id: "{population_id}"
    name: "{population_name}"
    description: "{population_criteria}"
    derivation:
      dataset: "ADSL"
      flag_variable: "{flag_variable}"
    page_ref: "{page_ref}"

methods:
  - id: "{method_id}"
    name: "{method_name}"
    description: "{method_description}"
    parameters:
      alpha: "{alpha_level}"
      strata: ["{stratification_factors}"]
    page_ref: "{page_ref}"

tfl_shells:
  tables:
    - id: "{table_id}"
      title: "{table_title}"
      population: "{population}"
      purpose: "{analysis_purpose}"
  figures:
    - id: "{figure_id}"
      # Same structure as tables
  listings:
    - id: "{listing_id}"
      # Same structure as tables

issues:
  - type: "warning|error"
    message: "{ambiguity_or_missing_info}"
    page_ref: "{page_ref}"
```

---

## Edge Cases

### SAP Not Available
- If no SAP document is found, prompt user to provide path via --input
- Log error and abort if --input is not provided

### Ambiguous Population Definitions
- Flag any population definitions that do not clearly state inclusion/exclusion criteria
- Document ambiguities in the issues section of output

### Missing TFL Shell Appendix
- If no shell appendix is found, log warning
- Generate skeleton TFL list from endpoint definitions

---

## Integration Points

### Downstream Skills
- `/spec-builder` -- Uses parsed SAP to create mapping specs
- `/adam-adeff-builder` -- Uses endpoint definitions for ADEFF
- `/tfl-shell-reviewer` -- Uses TFL shell list
- `/adam-adsl-builder` -- Uses population definitions

### MCPs
None required (document parsing is local).

---

## Evaluation Criteria

**Mandatory:**
- All primary and secondary endpoints extracted
- Analysis populations defined (ITT, mITT, PP, Safety)
- Statistical methods catalogued per endpoint

**Recommended:**
- Subgroup analyses identified
- Multiplicity adjustment strategy documented
- Sensitivity analyses documented
- Interim analysis specifications (if applicable)

---

## Critical Constraints

**Never:**
- Hardcode study-specific values (study ID, treatment arms, dates, file paths)
- Proceed if required configuration is missing
- Infer statistical methods not explicitly stated in SAP
- Create populations not defined in SAP
- Skip the primary endpoint extraction
- Proceed if SAP document is missing

**Always:**
- Resolve study metadata dynamically from ops/workflow-state.yaml or --study-config
- Read treatment arm definitions from study config, not hardcoded mappings
- Validate extracted content against SAP
- Document any ambiguities or missing information
- Include page references for extracted content
- Create structured YAML output

---

## Examples

### Basic Usage
```bash
sap-parser --input {sap_path} --output specs/sap-parsed.yaml
```

### Validate Only
```bash
sap-parser --input {sap_path} --validate
```

### With Study Config
```bash
sap-parser --input {sap_path} --output specs/sap-parsed.yaml --study-config specs/study-config.yaml
```
