---
name: spec-builder
description: Create or review mapping specifications for SDTM, ADaM, and TFL. Triggers on "mapping specification", "SDTM spec", "ADaM spec", "TFL spec", "derivation spec".
version: "1.0"
user-invocable: true
context: fork
model: sonnet
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
argument-hint: "[options] -- --input <input-path> --output <output-path> --type <spec-type> --validate --dry-run"
---

## Runtime Configuration

### Config Resolution
1. Read ops/workflow-state.yaml for current workflow state
2. Read specs/study-config.yaml for study metadata (if exists)
3. If study-config missing, fall back to --study-config <path> argument
4. If neither available, log error and abort

### Required Reads
- ops/workflow-state.yaml -- Current workflow state
- specs/sap-parsed.yaml -- Parsed SAP specifications
- specs/study-config.yaml -- Study configuration

### Arguments
| Argument | Required | Description |
|----------|----------|-------------|
| `--input` | Yes | Path to parsed SAP or study config |
| `--output` | Yes | Output path for generated specification |
| `--type` | Yes | Specification type: sdtm, adam, tfl |
| `--study-config` | No | Path to study configuration |
| `--validate` | No | Validate generated specification |
| `--dry-run` | No | Show what would be generated without writing |

---

## Philosophy

**Specifications drive all downstream work.** The mapping spec defines how raw data becomes SDTM, the derivation spec defines how SDTM becomes ADaM, and TFL shells define how ADaM becomes tables and figures.

---

## Input/Output Specification

### Inputs (from regulatory-graph.yaml node schema: spec-creation)
| Input | Type | Format | Required | Source |
|-------|------|--------|----------|--------|
| Parsed SAP specifications | specification | yaml | Yes | specs/sap-parsed.yaml (from sap-review node) |
| Study configuration | specification | yaml | Yes | specs/study-config.yaml (from protocol-setup node) |
| Workflow state | metadata | yaml | No | ops/workflow-state.yaml |

### Outputs (to regulatory-graph.yaml node schema: spec-creation)
| Output | Type | Format | Path Pattern |
|--------|------|--------|-------------|
| SDTM mapping specification | specification | xlsx, yaml | specs/sdtm-mapping-spec.xlsx |
| ADaM derivation specification | specification | xlsx, yaml | specs/adam-derivation-spec.xlsx |
| TFL shell specifications | specification | xlsx, docx | specs/tfl-shells.xlsx |

---

## Specification Types

| Type | Output | Description |
|------|--------|-------------|
| sdtm | sdtm-mapping-spec.yaml | SDTM domain mapping specifications |
| adam | adam-derivation-spec.yaml | ADaM dataset derivation specifications |
| tfl | tfl-shells.yaml | TFL shell specifications |

---

## Domain-Specific Content

### SDTM Mapping Specification
- Domain-level mappings (source variable to target SDTM variable)
- Controlled terminology requirements per domain
- Variable origin (CRF, derived, protocol)
- Codelist and format specifications
- Mapping rules and transformation logic

### ADaM Derivation Specification
- Dataset structure (ADSL, BDS, OCCDS)
- Parameter definitions (PARAM/PARAMCD)
- Derivation logic for key variables (AVAL, BASE, CHG, flags)
- Population flag definitions from SAP
- Treatment variable definitions from study config

### TFL Shell Specifications
- Table/figure/listing identifiers from SAP
- Column headers using treatment arm names from study config
- Population references from SAP
- Statistical display formatting
- Header and footnote templates

---

## Output Schema

### SDTM Mapping Spec
```yaml
schema_version: "1.0"
study_id: "{study_id} from study config"
extraction_date: "{extraction_date}"

domains:
  - domain: "{domain_code}"
    label: "{domain_label}"
    structure: "{domain_structure}"
    variables:
      - variable: "{variable_name}"
        label: "{variable_label}"
        type: "{data_type}"
        length: "{length}"
        origin: "{origin}"
        codelist: "{codelist_name}"
        mapping_rule: "{mapping_logic}"
        source: "{source_variable}"
        page_ref: "{spec_page}"
```

### ADaM Derivation Spec
```yaml
schema_version: "1.0"
study_id: "{study_id} from study config"
extraction_date: "{extraction_date}"

datasets:
  - dataset: "{dataset_name}"
    label: "{dataset_label}"
    structure: "{ADSL|BDS|OCCDS}"
    key_variables: ["{key_var}"]
    variables:
      - variable: "{variable_name}"
        label: "{variable_label}"
        type: "{data_type}"
        derivation: "{derivation_logic}"
        source_datasets: ["{source_dataset}"]
        source_variables: ["{source_variable}"]
```

### TFL Shell Spec
```yaml
schema_version: "1.0"
study_id: "{study_id} from study config"
extraction_date: "{extraction_date}"

tables:
  - id: "{table_id}"
    title: "{table_title}"
    population: "{population}"
    columns: "{column_headers_from_study_config_treatment_arms}"
    rows: "{row_definitions}"
    statistics: "{statistical_methods}"
```

---

## Edge Cases

### Missing SAP Endpoints
- If SAP parsing is incomplete, flag missing endpoints
- Generate skeleton specs with TODO markers for missing derivations

### Non-Standard Domains
- Document justification for custom/non-standard domain usage
- Reference CDISC IG sections where applicable

### Conflicting Definitions
- If SAP and protocol conflict, flag discrepancy
- Default to SAP for statistical definitions, protocol for design elements

---

## Integration Points

### Upstream Skills
- `/study-setup` -- Provides study-config.yaml
- `/sap-parser` -- Provides sap-parsed.yaml

### Downstream Skills
- `/spec-reviewer` -- Reviews generated specifications
- `/sdtm-*-mapper` -- Uses SDTM mapping spec for domain creation
- `/adam-*-builder` -- Uses ADaM derivation spec
- `/tfl-*-generator` -- Uses TFL shells

### MCPs
- `cdisc-library` -- CDISC controlled terminology lookup

---

## Evaluation Criteria

**Mandatory:**
- SDTM mapping spec covers all collected CRF variables
- ADaM spec covers all SAP endpoints
- TFL shells match SAP appendix

**Recommended:**
- Specs reviewed and signed off
- Variable naming follows CDISC conventions

---

## Critical Constraints

**Never:**
- Hardcode study-specific values (study ID, treatment arms, dates, file paths)
- Proceed if required configuration is missing
- Create specs without SAP reference
- Skip required CDISC variables
- Use non-standard naming conventions

**Always:**
- Resolve study metadata dynamically from ops/workflow-state.yaml or --study-config
- Read treatment arm definitions from study config, not hardcoded mappings
- Reference SAP endpoints for ADaM specs
- Include controlled terminology requirements
- Document derivation logic

---

## Examples

### SDTM Spec Generation
```bash
spec-builder --type sdtm --input specs/sap-parsed.yaml --output specs/sdtm-mapping-spec.yaml
```

### ADaM Spec Generation
```bash
spec-builder --type adam --input specs/sap-parsed.yaml --output specs/adam-derivation-spec.yaml
```

### TFL Shell Generation
```bash
spec-builder --type tfl --input specs/sap-parsed.yaml --output specs/tfl-shells.yaml
```

### With Explicit Study Config
```bash
spec-builder --type sdtm --input specs/sap-parsed.yaml --output specs/sdtm-mapping-spec.yaml --study-config specs/study-config.yaml
```
