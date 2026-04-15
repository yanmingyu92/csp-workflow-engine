---
name: adam-adeff-builder
description: Build ADEFF efficacy analysis dataset. Triggers on "ADEFF", "efficacy", "primary endpoint", "responder", "efficacy analysis", "response rate".
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
    description: Study-level metadata, treatment arms
  - path: specs/adam-spec.yaml
    description: ADaM derivation specifications
  - path: specs/sap-parsed.yaml
    description: Primary/secondary endpoint definitions, responder criteria

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
    name: ADEFF dataset(s)
    format: xpt
    path_pattern: "{output}"
```

Read: {adsl-path}, {input-dir}/*.xpt, specs/adam-spec.yaml, specs/study-config.yaml, specs/sap-parsed.yaml

## EXECUTE NOW
Parse $ARGUMENTS: --input-dir, --output, --adsl, --spec, --validate, --dry-run
**START NOW.**

---

## Philosophy
**ADEFF derives primary endpoint variables per SAP.** Responder flags and derived parameters follow BDS or OCCDS structure depending on endpoint type. ADEFF is the most study-specific ADaM dataset -- its structure and derivation are driven entirely by the SAP.

**Key Principle:** Primary endpoint derivation must exactly match the SAP definition. Any deviation must be documented and justified.

---

## Input/Output Specification

### Inputs (from regulatory-graph.yaml: adam-adeff)
| Input | Format | Required | Source |
|-------|--------|----------|--------|
| SDTM source domains | xpt | Yes | Various sdtm-*-mapping |
| ADSL dataset | xpt | Yes | adam-adsl |
| ADaM derivation spec | xlsx/yaml | Yes | spec-creation |

### Outputs (to regulatory-graph.yaml: adam-adeff)
| Output | Format | Path Pattern | Consumers |
|--------|--------|--------------|-----------|
| ADEFF dataset | xpt | output/adam/adeff.xpt | adam-validator, tfl-table-generator |

---

## Script Execution

```bash
adam-adeff-builder --input-dir {input-dir} --output {output} --adsl {adsl-path} [--spec {spec}] [--validate] [--dry-run]
```

### Arguments
| Argument | Required | Description |
|----------|----------|-------------|
| `--input-dir` | Yes | Directory containing SDTM XPT files |
| `--output` | Yes | Output path for adeff.xpt |
| `--adsl` | Yes | Path to ADSL dataset |
| `--spec` | No | ADaM specification YAML |
| `--validate` | No | Run ADaM validation after build |
| `--dry-run` | No | Show derivations without writing |

---

## Key Variables

| Variable | Source | Description |
|----------|--------|-------------|
| USUBJID | ADSL | Unique subject identifier ({study_id}-{SITEID}-{SUBJID}) |
| PARAMCD | Derived | Parameter code (endpoint-specific) |
| PARAM | Derived | Parameter description |
| AVAL | Derived | Analysis value (numeric) |
| AVALC | Derived | Analysis value (character, e.g., "Y"/"N" for responders) |
| BASE | Derived | Baseline value |
| CHG | Derived | Change from baseline (AVAL - BASE) |
| PCHG | Derived | Percent change from baseline |
| ABLFL | Derived | Baseline record flag |
| DTYPE | Derived | Derivation type (observed, LOCF, AVERAGE, WORST) |
| TRTP | ADSL | Planned treatment |
| TRTA | ADSL | Actual treatment |
| ITTFL | ADSL | Intent-to-treat population flag |
| EFFFL | ADSL | Efficacy population flag |

---

## PARAMCD and AVAL Derivation Patterns

### Continuous Endpoints (BDS Structure)
```python
def derive_continuous_endpoint(source_data, paramcd, param, baseline_visit, study_config):
    """
    Derive continuous efficacy endpoint per BDS structure.
    1. Identify baseline value (ABLFL = 'Y')
    2. Derive AVAL from source domain per visit
    3. Calculate CHG = AVAL - BASE
    4. Calculate PCHG = (CHG / BASE) * 100
    """
    baseline_records = source_data[source_data['VISIT'] == baseline_visit]
    baseline = baseline_records.groupby('USUBJID').last().reset_index()

    post_baseline = source_data[source_data['VISITNUM'] > baseline_visit_num]
    merged = post_baseline.merge(
        baseline[['USUBJID', 'AVAL']], on='USUBJID', how='left', suffixes=('', '_BASE')
    )
    merged['BASE'] = merged['AVAL_BASE']
    merged['CHG'] = merged['AVAL'] - merged['BASE']
    merged['PCHG'] = (merged['CHG'] / merged['BASE']) * 100
    return merged
```

### Responder Endpoints (OCCDS Structure)
```python
def derive_responder(subject_data, responder_criteria, study_config):
    """
    Derive responder flag per SAP definition.
    responder_criteria comes from sap-parsed.yaml.
    """
    is_responder = evaluate_criteria(subject_data, responder_criteria)
    return {
        'AVALC': 'Y' if is_responder else 'N',
        'AVAL': 1 if is_responder else 0,
    }
```

### Derived Parameters (DTYPE)
```python
# DTYPE flags records derived by aggregation:
# DTYPE = null: observed data
# DTYPE = "AVERAGE": average of multiple assessments per visit
# DTYPE = "LOCF": last observation carried forward
# DTYPE = "WORST": worst value across visits
```

---

## Output Schema

```yaml
adeff_dataset:
  name: ADEFF
  label: "Efficacy Analysis Dataset"
  class: "BDS"
  structure: "One record per subject per parameter per visit"
  key_variables: ["STUDYID", "USUBJID", "PARAMCD", "AVISITN"]

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
      derivation: "From sap-parsed.yaml endpoint definitions"
    - name: PARAM
      type: Char(200)
      label: "Parameter"
      required: true
      derivation: "From sap-parsed.yaml endpoint definitions"
    - name: AVAL
      type: Num
      label: "Analysis Value"
      required: true
      derivation: "Endpoint-specific per SAP"
    - name: AVALC
      type: Char(200)
      label: "Analysis Value (C)"
      required: false
    - name: BASE
      type: Num
      label: "Baseline Value"
      required: false
      derivation: "Value at baseline visit"
    - name: CHG
      type: Num
      label: "Change from Baseline"
      required: false
      derivation: "AVAL - BASE"
    - name: PCHG
      type: Num
      label: "Percent Change from Baseline"
      required: false
      derivation: "(CHG / BASE) * 100"
    - name: ABLFL
      type: Char(1)
      label: "Baseline Flag"
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
    - name: ITTFL
      type: Char(1)
      label: "Intent-To-Treat Population Flag"
      required: true
      source: ADSL
```

---

## Edge Cases

### Missing Baseline Values
```python
# If baseline is missing:
# - BASE = null, CHG = null, PCHG = null
# - AVAL still populated if observed
# - LOCF or other imputation per SAP sensitivity analysis
```

### Post-Baseline Missing Visits
```python
# Missing visits:
# - No record for that subject-parameter-visit combination
# - Sensitivity analyses may impute (LOCF, BOCF, WORST)
```

### Responder Definition Ambiguity
```python
# Responder criteria must match SAP exactly:
# - Threshold values from SAP (not hardcoded)
# - If SAP is ambiguous, document interpretation in ADRG
```

### Treatment Discontinuation Before Assessment
```python
# Subject discontinued before efficacy assessment:
# - Include in ITT analysis per SAP
# - Use observed or imputed data per SAP
```

---

## Integration Points

### Upstream Skills
- `/adam-adsl-builder` -- ADSL with treatment and population variables
- `/sdtm-*-mapper` -- Source domains for efficacy data
- `/sap-parser` -- Primary/secondary endpoint definitions

### Downstream Skills
- `/adam-validator` -- Validate ADEFF compliance
- `/tfl-table-generator` -- Efficacy summary tables
- `/tfl-figure-generator` -- Efficacy figures
- `/adrg-writer` -- Document ADEFF derivation in ADRG

### Related Skills
- `/adam-traceability-checker` -- Verify source-to-ADEFF traceability
- `/define-draft-builder` -- ADEFF metadata for Define.xml

---

## Evaluation Criteria

**Mandatory:**
- Primary endpoint derivation matches SAP exactly
- Responder definition consistent with SAP
- AVAL and AVALC consistent (where both exist)
- ADSL variables merged correctly

**Recommended:**
- Sensitivity analysis derivations included
- CHG and PCHG derived where applicable
- Baseline flag (ABLFL) correctly identified
- Visit windowing applied per SAP

---

## Critical Constraints

**Never:**
- Deviate from SAP endpoint definition without documentation
- Hardcode threshold values or responder criteria
- Produce output without validation
- Skip required variables
- Use non-CDISC controlled terminology for PARAMCD

**Always:**
- Read endpoint definitions from sap-parsed.yaml (dynamic)
- Validate all inputs before processing
- Document any deviations from standards in ADRG
- Generate traceable, reproducible results

---

## Examples

### Basic Usage
```bash
adam-adeff-builder --input-dir output/sdtm/ --output output/adam/adeff.xpt --adsl output/adam/adsl.xpt
```

### With Validation
```bash
adam-adeff-builder --input-dir output/sdtm/ --output output/adam/adeff.xpt --adsl output/adam/adsl.xpt --validate
```

### Expected Output
```
ADEFF ({n_subjects} * {n_params} * {n_visits} records)
+-- ID: STUDYID, USUBJID ({study_id}-{SITEID}-{SUBJID})
+-- Parameter: PARAMCD, PARAM (from SAP definitions)
+-- Analysis: AVAL, AVALC, BASE, CHG, PCHG
+-- Visit: AVISIT, AVISITN, ABLFL
+-- Derivation: DTYPE (observed, LOCF, etc.)
+-- Treatment: TRTP, TRTA (from ADSL)
+-- Population: ITTFL, EFFFL (from ADSL)
```
