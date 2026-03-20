---
name: sap-parser
description: Parse Statistical Analysis Plan (SAP) to extract endpoints, populations, statistical methods, and TFL shell specifications. Triggers on "SAP", "statistical analysis plan", "endpoints", "analysis populations", "ITT", "mITT", "safety population".
version: "1.0"
user-invocable: true
context: fork
model: sonnet
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
argument-hint: "[options] — --input, --output, --validate, --dry-run"
---

## Runtime Configuration (Step 0)

REQUIRED: Read these files to configure behavior:
1. `ops/workflow-state.yaml` — Current workflow state
2. `specs/study-config.yaml` — Study configuration (if exists)
3. `docs/sap.pdf` or `docs/sap.docx` — SAP document

If no SAP document found, prompt user to provide path.

---

## EXECUTE NOW

Parse $ARGUMENTS: --input, --output, --validate, --dry-run

**START NOW.** Begin SAP parsing immediately.

---

## Philosophy

**The SAP IS the specification.** Every table, figure, and listing in the CSR traces back to definitions in the SAP. This skill makes the SAP machine-readable, enabling automated spec generation and downstream programming.

**Three outputs:**
1. **Endpoints** — Primary, secondary, exploratory with statistical methods
2. **Populations** — ITT, mITT, PP, Safety with inclusion criteria
3. **TFL Shells** — List of all tables, figures, listings with shells

---

## Script Execution

```bash
python csp-skills/layer-0-protocol/sap-parser/script.py --input <sap-file> --output specs/sap-parsed.yaml
```

### Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `--input` | Yes | Path to SAP document (PDF or DOCX) |
| `--output` | Yes | Output path for parsed YAML |
| `--validate` | No | Validate extracted content only |
| `--dry-run` | No | Show what would be extracted without writing |

---

## Input/Output Specification

See spec.yaml for full I/O schema.

### Inputs

| Input | Type | Format | Required |
|-------|------|--------|----------|
| SAP Document | document | PDF, DOCX | Yes |
| Study Config | specification | YAML | No |

### Outputs

| Output | Type | Format | Description |
|--------|------|--------|-------------|
| Parsed SAP | specification | YAML | Machine-readable endpoints, populations, methods |
| TFL Shell List | specification | YAML | All TFL shells with metadata |

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
- Infer statistical methods not explicitly stated in SAP
- Create populations not defined in SAP
- Skip the primary endpoint extraction
- Proceed if SAP document is missing

**Always:**
- Validate extracted content against SAP
- Document any ambiguities or missing information
- Include page references for extracted content
- Create structured YAML output

---

## Output Format

```yaml
schema_version: 1
sap_metadata:
  study_id: "{from study-config}"
  document_title: "{SAP title}"
  document_version: "{version if available}"
  extraction_date: "{timestamp}"

endpoints:
  primary:
    - id: "EP001"
      name: "{endpoint name}"
      description: "{description}"
      hypothesis:
        null: "{H0}"
        alternative: "{H1}"
      method: "{statistical method}"
      population: "{analysis population}"
      dataset: "{ADaM dataset}"
      multiplicity: "{adjustment strategy}"
      page_ref: "{SAP page number}"
  secondary:
    - id: "EP002"
      # ...

populations:
  - id: "ITT"
    name: "Intent-to-Treat"
    description: "{criteria}"
    derivation:
      dataset: "ADSL"
      flag_variable: "ITTFL"
    page_ref: "{page}"
  - id: "SAF"
    name: "Safety"
    # ...

methods:
  - id: "M001"
    name: "Cochran-Mantel-Haenszel test"
    description: "{description}"
    parameters:
      alpha: 0.05
      strata: ["stratification factors"]
    page_ref: "{page}"

tfl_shells:
  tables:
    - id: "Table 14.1-1"
      title: "{table title}"
      population: "{population}"
      purpose: "{demographics/efficacy/safety}"
  figures:
    - id: "Figure 14.1-1"
      # ...
  listings:
    - id: "Listing 16.1-1"
      # ...

issues:
  - type: "warning|error"
    message: "{ambiguity or missing info}"
    page_ref: "{page}"
```

---

## Integration Points

### Downstream Skills

- `/spec-builder` — Uses parsed SAP to create mapping specs
- `/adam-adeff-builder` — Uses endpoint definitions for ADEFF
- `/tfl-shell-reviewer` — Uses TFL shell list

### MCPs

None required (document parsing is local).

---

## Examples

### Basic Usage

```bash
python csp-skills/layer-0-protocol/sap-parser/script.py \
  --input docs/sap.pdf \
  --output specs/sap-parsed.yaml
```

### Validate Only

```bash
python csp-skills/layer-0-protocol/sap-parser/script.py \
  --input docs/sap.pdf \
  --validate
```

### With Study Config

```bash
python csp-skills/layer-0-protocol/sap-parser/script.py \
  --input docs/sap.pdf \
  --output specs/sap-parsed.yaml \
  --study-config specs/study-config.yaml
```
