---
name: adam-adlb-builder
description: Build ADLB laboratory analysis dataset (BDS). Triggers on "ADLB", "lab analysis", "BDS", "AVAL", "BASE", "CHG".
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
    description: Study-level metadata, treatment arms, visit schedule
  - path: specs/adam-spec.yaml
    description: ADaM derivation specifications
  - path: specs/sap-parsed.yaml
    description: Lab analysis specifications from SAP

required_inputs:
  - type: dataset
    name: SDTM LB domain
    format: xpt
    path_pattern: "{input-dir}/lb.xpt"
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
    name: ADLB dataset (adlb.xpt)
    format: xpt
    path_pattern: "{output}"
```

Read: {adsl-path}, {input-dir}/lb.xpt, specs/adam-spec.yaml, specs/study-config.yaml

## EXECUTE NOW
Parse $ARGUMENTS: --input-dir, --output, --adsl, --spec, --validate, --dry-run
**START NOW.**

---

## Philosophy
**ADLB follows BDS (Basic Data Structure) with AVAL/BASE/CHG/PCHG.** Visit windowing and baseline flag (ABLFL) are critical derivations. The lab dataset is one of the most complex BDS datasets due to the large number of parameters, reference ranges, and shift analyses.

**Key Principle:** Every lab parameter must have a properly identified baseline (ABLFL), correct unit conversion, and consistent reference range flags. Shift tables are a key analysis output.

---

## Input/Output Specification

### Inputs (from regulatory-graph.yaml: adam-adlb)
| Input | Format | Required | Source |
|-------|--------|----------|--------|
| SDTM LB domain | xpt | Yes | sdtm-lb-mapping |
| ADSL dataset | xpt | Yes | adam-adsl |
| ADaM derivation spec | xlsx/yaml | Yes | spec-creation |

### Outputs (to regulatory-graph.yaml: adam-adlb)
| Output | Format | Path Pattern | Consumers |
|--------|--------|--------------|-----------|
| ADLB dataset | xpt | output/adam/adlb.xpt | adam-validator, tfl-table-generator |

---

## Script Execution

```bash
adam-adlb-builder --input-dir {input-dir} --output {output} --adsl {adsl-path} [--spec {spec}] [--validate] [--dry-run]
```

### Arguments
| Argument | Required | Description |
|----------|----------|-------------|
| `--input-dir` | Yes | Directory containing SDTM XPT files |
| `--output` | Yes | Output path for adlb.xpt |
| `--adsl` | Yes | Path to ADSL dataset |
| `--spec` | No | ADaM specification YAML |
| `--validate` | No | Run ADaM validation after build |
| `--dry-run` | No | Show derivations without writing |

---

## Key Variables

| Variable | Source | Description |
|----------|--------|-------------|
| USUBJID | ADSL/LB | Unique subject identifier ({study_id}-{SITEID}-{SUBJID}) |
| PARAMCD | Derived | Lab parameter code (mapped from LBTESTCD) |
| PARAM | Derived | Lab parameter description |
| AVAL | Derived | Analysis value (from LBSTRESN) |
| AVALC | Derived | Analysis value character (from LBSTRESC) |
| BASE | Derived | Baseline value (from ABLFL='Y' record) |
| CHG | Derived | Change from baseline (AVAL - BASE) |
| PCHG | Derived | Percent change from baseline ((CHG/BASE)*100) |
| ABLFL | Derived | Baseline record flag |
| ANRIND | Derived | Analysis reference range indicator (L/N/H) |
| BNRIND | Derived | Baseline reference range indicator |
| TRTP | ADSL | Planned treatment |
| TRTA | ADSL | Actual treatment |
| SAFFL | ADSL | Safety population flag |

---

## PARAMCD Derivation

```python
# PARAMCD is derived from LBTESTCD via mapping in specs/adam-spec.yaml
# Example mappings (actual values from config, not hardcoded):
# LBTESTCD -> PARAMCD mapping driven by adam-spec.yaml
# Each PARAMCD has associated PARAM (description) and AVAL derivation
```

---

## AVAL Derivation

```python
def derive_aval(lb_record, study_config):
    """
    AVAL = analysis value from LBSTRESN (standardized numeric result).
    If LBSTRESN is null, attempt to parse LBORRES as numeric.
    Unit conversion is already handled in SDTM LB mapping.
    """
    if pd.notna(lb_record['LBSTRESN']):
        return lb_record['LBSTRESN']
    try:
        return float(lb_record['LBORRES'])
    except (ValueError, TypeError):
        return None
```

---

## Baseline Derivation (ABLFL, BASE)

```python
def derive_baseline(adlb_by_subject_param, study_config):
    """
    Identify baseline record and derive BASE.
    Baseline definition from study_config.baseline_method (default: 'last_pre_dose'):
    - 'last_pre_dose': Last non-missing value on or before TRTSDT
    - 'protocol_visit': Value from specific visit
    """
    baseline_method = study_config.get('baseline_method', 'last_pre_dose')

    if baseline_method == 'last_pre_dose':
        pre_dose = adlb_by_subject_param[
            (adlb_by_subject_param['ADT'] <= subject_trtsdt) &
            (adlb_by_subject_param['AVAL'].notna())
        ]
        if len(pre_dose) > 0:
            baseline = pre_dose.sort_values('ADT').iloc[-1]
            baseline['ABLFL'] = 'Y'
            baseline['BASE'] = baseline['AVAL']
            return baseline
```

---

## CHG and PCHG Derivation

```python
def derive_chg_pchg(adlb_dataset):
    """
    CHG = AVAL - BASE (post-baseline only)
    PCHG = (CHG / BASE) * 100 (where BASE != 0)
    """
    mask_post_base = (adlb_dataset['ABLFL'] != 'Y') & adlb_dataset['BASE'].notna()
    adlb_dataset.loc[mask_post_base, 'CHG'] = (
        adlb_dataset.loc[mask_post_base, 'AVAL'] - adlb_dataset.loc[mask_post_base, 'BASE']
    )
    mask_pchg = mask_post_base & (adlb_dataset['BASE'] != 0)
    adlb_dataset.loc[mask_pchg, 'PCHG'] = (
        adlb_dataset.loc[mask_pchg, 'CHG'] / adlb_dataset.loc[mask_pchg, 'BASE']
    ) * 100
    return adlb_dataset
```

---

## ANRIND and Shift Variables

```python
def derive_anrind(aval, anrlo, anrhi):
    """ANRIND = 'L' if AVAL < ANRLO, 'N' if normal, 'H' if AVAL > ANRHI."""
    if aval is None or anrlo is None or anrhi is None:
        return None
    if aval < anrlo: return 'L'
    elif aval > anrhi: return 'H'
    else: return 'N'

def derive_shift(bnrind, anrind):
    """Shift from baseline: concatenation of BNRIND + ANRIND (e.g., 'LN', 'NH')."""
    if bnrind and anrind: return bnrind + anrind
    return None
```

---

## Visit Windowing

```python
def apply_visit_windowing(adlb_dataset, study_config):
    """
    Assign analysis visits (AVISIT, AVISITN) based on visit window rules.
    Visit windows defined in study_config.visit_windows.
    """
    visit_windows = study_config.get('visit_windows', [])
    for window in visit_windows:
        mask = (
            (adlb_dataset['ADY'] >= window['start_day']) &
            (adlb_dataset['ADY'] <= window['end_day'])
        )
        adlb_dataset.loc[mask, 'AVISIT'] = window['avisit']
        adlb_dataset.loc[mask, 'AVISITN'] = window['avisitn']
    return adlb_dataset
```

---

## Merge Logic

```python
def build_adlb(sdtm_dir, adsl_path, study_config):
    """
    Build ADLB by merging LB with ADSL.
    1. Load LB and ADSL
    2. Merge ADSL for treatment/population
    3. Derive PARAMCD, AVAL, visit windowing
    4. Derive ABLFL, BASE, CHG, PCHG
    5. Derive ANRIND, BNRIND, shift
    """
    lb = read_xpt(f"{sdtm_dir}/lb.xpt")
    adsl = read_xpt(adsl_path)
    adlb = lb.merge(adsl, on='USUBJID', how='left')
    adlb = derive_paramcd(adlb, study_config)
    adlb = derive_aval_all(adlb)
    adlb = apply_visit_windowing(adlb, study_config)
    adlb = derive_baseline_all(adlb, study_config)
    adlb = derive_chg_pchg(adlb)
    adlb = derive_anrind_all(adlb)
    adlb = derive_shift_all(adlb)
    return adlb
```

---

## Output Schema

```yaml
adlb_dataset:
  name: ADLB
  label: "Laboratory Analysis Dataset"
  class: "BDS"
  structure: "One record per subject per parameter per visit"
  key_variables: ["STUDYID", "USUBJID", "PARAMCD", "AVISITN"]

  variables:
    - name: USUBJID
      type: Char(11)
      label: "Unique Subject Identifier"
      required: true
      source: LB/ADSL
    - name: PARAMCD
      type: Char(8)
      label: "Parameter Code"
      required: true
      derivation: "Mapped from LBTESTCD via adam-spec.yaml"
    - name: PARAM
      type: Char(200)
      label: "Parameter"
      required: true
    - name: AVAL
      type: Num
      label: "Analysis Value"
      required: true
      derivation: "From LBSTRESN"
    - name: BASE
      type: Num
      label: "Baseline Value"
      required: false
      derivation: "AVAL where ABLFL='Y'"
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
    - name: ANRIND
      type: Char(1)
      label: "Analysis Reference Range Indicator"
      required: false
      derivation: "L/N/H based on ANRLO/ANRHI"
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

### Multiple Lab Records Same Visit Same Parameter
```python
# If multiple records for same USUBJID+PARAMCD+AVISIT:
# - Use record closest to protocol-specified visit date
# - Or: use worst value (for safety parameters)
# - Method specified in adam-spec.yaml
```

### Missing Reference Ranges
```python
# ANRLO/ANRHI null: ANRIND = null, shift cannot be derived
```

### Unit Conversion Issues
```python
# If LBSTRESN and LBORRES disagree: use LBSTRESN (standardized)
```

### Missing Baseline for Some Parameters
```python
# Subject has post-baseline lab but no baseline:
# - BASE = null, CHG = null, PCHG = null
# - AVAL still populated for observed value summaries
```

---

## Integration Points

### Upstream Skills
- `/adam-adsl-builder` -- ADSL with treatment and population variables
- `/sdtm-lb-mapper` -- LB domain with standardized results
- `/sap-parser` -- Lab analysis specifications

### Downstream Skills
- `/adam-validator` -- Validate ADLB compliance
- `/tfl-table-generator` -- Lab summary tables, shift tables
- `/adrg-writer` -- Document ADLB derivation in ADRG

### Related Skills
- `/adam-traceability-checker` -- Verify LB-to-ADLB traceability
- `/define-draft-builder` -- ADLB metadata for Define.xml

---

## Evaluation Criteria

**Mandatory:**
- AVAL derived from correct source (LBSTRESN)
- Baseline (ABLFL) identified per SAP algorithm
- CHG = AVAL - BASE derived where applicable
- PARAMCD unique within subject+timepoint
- ADSL merge complete

**Recommended:**
- Visit windowing applied per SAP
- ANRIND and shift variables derived
- PCHG calculated for applicable parameters

---

## Critical Constraints

**Never:**
- Use non-standard units for AVAL (must use LBSTRESN)
- Assign ABLFL = 'Y' to more than one record per subject+parameter
- Hardcode reference range values

**Always:**
- Validate all inputs before processing
- Derive BASE from ABLFL='Y' record only
- Calculate CHG only for post-baseline records
- Document baseline definition and visit windowing in ADRG
- Generate traceable, reproducible results

---

## Examples

### Basic Usage
```bash
adam-adlb-builder --input-dir output/sdtm/ --output output/adam/adlb.xpt --adsl output/adam/adsl.xpt
```

### Expected Output
```
ADLB ({n_records} records)
+-- ID: STUDYID, USUBJID ({study_id}-{SITEID}-{SUBJID})
+-- Parameter: PARAMCD, PARAM (from adam-spec mapping)
+-- Analysis: AVAL, BASE, CHG, PCHG, ABLFL
+-- Reference: ANRIND, BNRIND, shift
+-- Visit: AVISIT, AVISITN (windowed)
+-- Treatment: TRTP, TRTA (from ADSL)
+-- Population: SAFFL (from ADSL)
```
