---
name: adam-custom-builder
description: Build custom ADaM datasets (PK, QoL, PRO). Triggers on "custom ADaM", "PK", "pharmacokinetics", "QoL", "quality of life", "PRO".
version: "2.0"
user-invocable: true
context: fork
model: sonnet
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
argument-hint: "[options] -- --input, --output, --dataset-type"
---

## Runtime Configuration (Step 0)

### Dynamic Config Resolution
```yaml
config_sources:
  - path: specs/study-config.yaml
    description: Study-level metadata, treatment arms
  - path: specs/adam-spec.yaml
    description: ADaM derivation specifications
  - path: specs/sap-parsed.yaml
    description: Analysis specifications from SAP

required_inputs:
  - type: dataset
    name: SDTM source domains
    format: xpt
    path_pattern: "{input-dir}/*.xpt"
  - type: dataset
    name: ADSL dataset
    format: xpt
    path_pattern: "{adsl-path}"
  - type: specification
    name: ADaM derivation specification
    format: xlsx|yaml
    path_pattern: specs/adam-spec.yaml

output:
  - type: dataset
    name: Custom ADaM datasets
    format: xpt
    path_pattern: "{output}"
```

Read: {adsl-path}, {input-dir}/*.xpt, specs/adam-spec.yaml, specs/study-config.yaml

## EXECUTE NOW
Parse $ARGUMENTS: --input-dir, --output, --adsl, --dataset-type, --spec, --validate, --dry-run
**START NOW.**

---

## Philosophy
**Custom ADaM datasets must follow fundamental principles: traceability to SDTM, clear variable derivation, and analysis-readiness.** Whether building PK (pharmacokinetics), QoL (quality of life), or PRO (patient-reported outcomes), datasets, the ADaM IG fundamental principles apply.

**Key Principle:** Custom does not mean non-standard. Custom ADaM datasets must adhere to the same rigor as standard ADaM structures (ADSL, BDS, OCCDS) and maintain complete traceability to SDTM sources.

---

## Input/Output Specification

### Inputs (from regulatory-graph.yaml: adam-custom-analysis)
| Input | Format | Required | Source |
|-------|--------|----------|--------|
| SDTM source domains | xpt | Yes | Various sdtm-*-mapping |
| ADSL dataset | xpt | Yes | adam-adsl |
| ADaM derivation spec | xlsx/yaml | Yes | spec-creation |

### Outputs (to regulatory-graph.yaml: adam-custom-analysis)
| Output | Format | Path Pattern | Consumers |
|--------|--------|--------------|-----------|
| Custom ADaM datasets | xpt | output/adam/ | adam-validator, adam-traceability-checker |

---

## Script Execution

```bash
adam-custom-builder --input-dir {input-dir} --output {output} --adsl {adsl-path} --dataset-type {type} [--spec {spec}] [--validate] [--dry-run]
```

### Arguments
| Argument | Required | Description |
|----------|----------|-------------|
| `--input-dir` | Yes | Directory containing SDTM XPT files |
| `--output` | Yes | Output path for custom ADaM dataset |
| `--adsl` | Yes | Path to ADSL dataset |
| `--dataset-type` | No | Type: PK, QoL, PRO, or OTHER |
| `--spec` | No | ADaM specification YAML |
| `--validate` | No | Run ADaM validation after build |
| `--dry-run` | No | Show derivations without writing |

---

## Key Variables

| Variable | Source | Description |
|----------|--------|-------------|
| USUBJID | ADSL | Unique subject identifier ({study_id}-{SITEID}-{SUBJID}) |
| PARAMCD | Derived | Parameter code (dataset-specific) |
| PARAM | Derived | Parameter description |
| AVAL | Derived | Analysis value |
| AVALC | Derived | Analysis value (character) |
| DTYPE | Derived | Derivation type (observed, LOCF, AVERAGE, WORST) |
| TRTP | ADSL | Planned treatment |
| TRTA | ADSL | Actual treatment |
| SAFFL | ADSL | Safety population flag |
| ITTFL | ADSL | Intent-to-treat population flag |

---

## PK Dataset (ADPC) Derivation

```python
# Pharmacokinetic dataset following BDS structure
# Key variables:
# PARAMCD: PK parameter code (e.g., "AUC0_24", "CMAX", "TMAX", "TROUGH", "CLCR")
# PARAM: PK parameter description
# AVAL: analysis value (concentration or derived PK parameter)
# AVALC: character representation
# VISIT: PK sampling timepoint
# ARELTM1: relative time from dose (hours)

# PK parameters are defined in adam-spec.yaml:
# study_config.pk_parameters:
#   - paramcd: "AUC0_24"
#     param: "Area Under the Curve 0-24h"
#     aval_source: "calculated from PC domain"
#   - paramcd: "CMAX"
#     param: "Maximum Concentration"
#     aval_source: "observed from PC domain"
#   - paramcd: "TMAX"
#     param: "Time to Maximum Concentration"
#     aval_source: "observed from PC domain"

def derive_pk_parameters(pc_data, pk_param_defs, adsl, study_config):
    """
    Derive PK parameters from PC (Pharmacokinetic Concentrations) domain.

    1. Load PC domain (one record per timepoint per subject)
    2. Merge ADSL for treatment and demographic data
    3. Calculate non-compartmental analysis (NCA) parameters:
       - CMAX: maximum observed concentration
       - TMAX: time of maximum concentration
       - AUC: area under the curve (trapezoidal method)
       - CLCR: clearance
    4. Each NCA parameter becomes a separate PARAMCD
    """
    pc = read_xpt(f"{input_dir}/pc.xpt")
    adpc = pc.merge(adsl, on='USUBJID', how='left')

    for paramcd, param_def in pk_param_defs.items():
        if param_def['method'] == 'CMAX':
            adpc = derive_cmax(adpc, pc, param_def)
        elif param_def['method'] == 'AUC':
            adpc = derive_auc(adpc, pc, param_def)
        elif param_def['method'] == 'TMAX':
            adpc = derive_tmax(adpc, pc, param_def)

    return adpc
```

---

## QoL/PRO Dataset Derivation
```python
# Quality of Life / Patient-Reported Outcome dataset following BDS structure
# Key variables:
# PARAMCD: QoL/PRO questionnaire item code (e.g., "QS01", "QS02")
# PARAM: Questionnaire item description
# AVAL: numeric score
# AVALC: response category
# BASE: baseline score
# CHG: change from baseline
# AVISIT: analysis visit

# QoL parameters defined in adam-spec.yaml:
# study_config.qol_parameters:
#   - paramcd: "QS01"
#     param: "Physical Functioning Score"
#     source_questionnaire: "SF-36"
#     scoring_method: "sum_scale"

def derive_qol_dataset(qs_data, qol_param_defs, adsl, study_config):
    """
    Derive QoL/PRO dataset from QS (Questionnaires) domain.

    1. Load QS domain (one record per question per visit per subject)
    2. Merge ADSL for treatment and demographic data
    3. Score questionnaire items per scoring algorithm
    4. Calculate BASE, CHG, PCHG per BDS conventions
    5. Apply visit windowing
    """
    qs = read_xpt(f"{input_dir}/qs.xpt")
    adqol = qs.merge(adsl, on='USUBJID', how='left')

    # Score items per questionnaire-specific algorithm
    for paramcd, param_def in qol_param_defs.items():
        adqol = score_questionnaire_item(adqol, paramcd, param_def)

    # Baseline and change derivations
    adqol = derive_baseline_all(adqol, study_config)
    adqol = derive_chg_pchg(adqol)

    return adqol
```

---

## Output Schema

```yaml
custom_adam_dataset:
  name: "{dataset_name}"
  label: "{dataset_label}"
  class: "BDS"  # or "OCCDS" depending on dataset type
  structure: "One record per subject per parameter per visit/occasion"
  key_variables: ["STUDYID", "USUBJID", "PARAMCD"]

  variables:
    - name: USUBJID
      type: Char(11)
      label: "Unique Subject Identifier"
      required: true
      source: ADSL
    - name: PARAMCD
      type: Char(8)
      label: "Parameter Code"
      required: true
      derivation: "From adam-spec.yaml parameter definitions"
    - name: PARAM
      type: Char(200)
      label: "Parameter"
      required: true
      derivation: "From adam-spec.yaml parameter definitions"
    - name: AVAL
      type: Num
      label: "Analysis Value"
      required: true
      derivation: "Dataset-specific per SAP"
    - name: AVALC
      type: Char(200)
      label: "Analysis Value (C)"
      required: false
    - name: DTYPE
      type: Char(8)
      label: "Derivation Type"
      required: false
    - name: TRTP
      type: Char(40)
      label: "Planned Treatment"
      required: true
      source: ADSL
    - name: TRTA
      type: Char(40)
      label: "Actual Treatment"
      required: true
      source: ADSL
    - name: SAFFL
      type: Char(1)
      label: "Safety Population Flag"
      required: true
      source: ADSL
```

---

## Edge Cases

### Missing PK Sampling Timepoints
```python
# If PC domain has missing timepoints:
# - Cannot derive AUC (requires full profile)
# - CMAX and TMAX may still be derivable from available points
# - Flag subjects with incomplete PK profiles
# - Document missing data handling in ADRG
```

### Questionnaire Scoring with Missing Items
```python
# If some questionnaire items are missing:
# - Apply scoring rules per questionnaire manual (e.g., prorate, half-rule)
# - Document scoring method in ADRG
# - May need to set AVAL = null if too many items missing
```

### Cross-Period PK Data
```python
# Multiple dosing periods in PK studies:
# - AEXPRFDY or ARELTM1 used to distinguish periods
# - AUC calculated per period separately
# - May need PARAMCD suffixes (AUC0_24P1, AUC0_24P2)
```

### Non-Standard ADaM Structure
```python
# If dataset does not fit BDS or OCCDS:
# - Must still follow ADaM fundamental principles
# - Document justification for non-standard structure in ADRG
# - Ensure traceability is maintained
```

---

## Integration Points

### Upstream Skills
- `/adam-adsl-builder` -- ADSL with treatment and population variables
- `/sdtm-pc-mapper` -- PC domain for PK data (if applicable)
- `/sdtm-qs-mapper` -- QS domain for QoL/PRO data (if applicable)
- `/study-setup` -- Custom parameter definitions
- `/sap-parser` -- Custom analysis specifications

### Downstream Skills
- `/adam-validator` -- Validate custom ADaM compliance
- `/tfl-table-generator` -- Custom analysis tables
- `/adrg-writer` -- Document custom dataset derivation in ADRG

### Related Skills
- `/adam-traceability-checker` -- Verify custom ADaM traceability
- `/define-draft-builder` -- Custom ADaM metadata for Define.xml

---

## Evaluation Criteria

**Mandatory:**
- Dataset follows ADaM fundamental principles
- Traceability to SDTM maintained
- PARAMCD/PARAM properly defined per adam-spec.yaml
- ADSL merge complete
- Structure clearly documented (BDS or OCCDS)

**Recommended:**
- Derivation logic documented in metadata
- Visit windowing applied where applicable
- DTYPE populated for derived records

---

## Critical Constraints

**Never:**
- Create custom variables that conflict with CDISC standard variable names
- Omit traceability documentation
- Skip ADSL merge
- Use non-CDISC controlled terminology

**Always:**
- Follow ADaM IG fundamental principles
- Maintain traceability to SDTM sources
- Merge ADSL for treatment and population variables
- Document dataset structure and derivation in ADRG
- Generate traceable, reproducible results

---

## Examples

### PK Dataset
```bash
adam-custom-builder --input-dir output/sdtm/ --output output/adam/adpc.xpt --adsl output/adam/adsl.xpt --dataset-type PK
```

### QoL Dataset
```bash
adam-custom-builder --input-dir output/sdtm/ --output output/adam/adqol.xpt --adsl output/adam/adsl.xpt --dataset-type QoL
```

### Expected Output
```
Custom ADaM ({dataset_name}, {n_records} records)
+-- ID: STUDYID, USUBJID ({study_id}-{SITEID}-{SUBJID})
+-- Parameter: PARAMCD, PARAM (from adam-spec.yaml)
+-- Analysis: AVAL, AVALC, DTYPE
+-- Treatment: TRTP, TRTA (from ADSL)
+-- Population: SAFFL, ITTFL (from ADSL)
```
