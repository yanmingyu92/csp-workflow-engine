---
name: adtte-builder
description: Build ADTTE time-to-event analysis dataset. Triggers on "ADTTE", "time-to-event", "survival".
version: "2.0"
user-invocable: true
context: fork
model: sonnet
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
argument-hint: "[options] -- --input-dir, --output, --event-type"
---

## Runtime Configuration (Step 0)

### Dynamic Config Resolution
```yaml
config_sources:
  - path: specs/study-config.yaml
    description: Study-level metadata, treatment arms, time origins
  - path: specs/adam-spec.yaml
    description: ADaM derivation specifications
  - path: specs/sap-parsed.yaml
    description: TTE endpoint definitions from SAP
  - path: specs/tte-parameters.yaml
    description: TTE parameter definitions (PARAMCD, PARAM, censor rules)

required_inputs:
  - type: dataset
    name: SDTM domains (AE, DS, DM)
    format: xpt
    path_pattern: "{input-dir}/ae.xpt, {input-dir}/ds.xpt, {input-dir}/dm.xpt"
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
    name: ADTTE dataset (adtte.xpt)
    format: xpt
    path_pattern: "{output}"
```

Read: {adsl-path}, {input-dir}/ae.xpt, {input-dir}/ds.xpt, {input-dir}/dm.xpt, specs/tte-parameters.yaml, specs/study-config.yaml

## EXECUTE NOW
Parse $ARGUMENTS: --input-dir, --output, --adsl, --event-type, --spec, --validate, --dry-run
**START NOW.**

---

## Philosophy
**ADTTE enables survival analysis.** Time from a defined origin (e.g., randomization, first dose) to a clinical event or censoring. Each record represents one TTE parameter per subject. Proper handling of censoring, competing risks, and time origins is critical for regulatory acceptance.

**Key Principle:** Every TTE parameter must have clearly defined STARTDT (time origin), event definition, censoring rules, and AVAL derivation. These must match the SAP exactly.

---

## Input/Output Specification

### Inputs (from regulatory-graph.yaml: adam-adtte)
| Input | Format | Required | Source |
|-------|--------|----------|--------|
| SDTM AE domain | xpt | Conditional | sdtm-ae-mapping |
| SDTM DS domain | xpt | Conditional | sdtm-ds-mapping |
| SDTM DM domain | xpt | Yes | sdtm-dm-mapping |
| ADSL dataset | xpt | Yes | adam-adsl |
| ADaM derivation spec | xlsx/yaml | Yes | spec-creation |

### Outputs (to regulatory-graph.yaml: adam-adtte)
| Output | Format | Path Pattern | Consumers |
|--------|--------|--------------|-----------|
| ADTTE dataset | xpt | output/adam/adtte.xpt | adam-validator, tfl-figure-generator (KM curves) |

---

## Script Execution

```bash
adam-adtte-builder --input-dir {input-dir} --output {output} --adsl {adsl-path} --event-type {event-type} [--spec {spec}] [--validate] [--dry-run]
```

### Arguments
| Argument | Required | Description |
|----------|----------|-------------|
| `--input-dir` | Yes | Directory containing SDTM XPT files |
| `--output` | Yes | Output path for adtte.xpt |
| `--adsl` | Yes | Path to ADSL dataset |
| `--event-type` | No | TTE event type filter (e.g., "TTFAE", "OS", "PFS") |
| `--spec` | No | ADaM specification YAML |
| `--validate` | No | Run ADaM validation after build |
| `--dry-run` | No | Show derivations without writing |

---

## Key Variables

| Variable | Source | Description |
|----------|--------|-------------|
| USUBJID | ADSL | Unique subject identifier ({study_id}-{SITEID}-{SUBJID}) |
| PARAM | Derived | Time-to-event parameter description |
| PARAMCD | Derived | Parameter code (e.g., "TTFAE", "OS", "PFS") |
| AVAL | Derived | Time value in days (ADT - STARTDT + 1) |
| CNSR | Derived | Censor flag (0=event observed, 1=censored) |
| ADT | Derived | Date of event or censoring |
| STARTDT | Derived | Time origin date |
| EVNTDESC | Derived | Event description |
| CNSDTDSC | Derived | Censor description |
| TRTP | ADSL | Planned treatment |
| TRTA | ADSL | Actual treatment |
| SAFFL | ADSL | Safety population flag |
| ITTFL | ADSL | Intent-to-treat population flag |

---

## PARAMCD and PARAM Derivation

### Common TTE Parameters
```python
# TTE parameters are defined in specs/tte-parameters.yaml
# Each parameter specifies:
# - PARAMCD: parameter code
# - PARAM: parameter description
# - time_origin: STARTDT source (e.g., TRTSDT, RFSTDTC)
# - event_source: SDTM domain and filter for events
# - censor_source: SDTM domain and filter for censoring
# - competing_risk: optional competing event definition

# Example parameter definitions:
TTE_PARAMS = {
    'TTFAE': {
        'PARAM': 'Time to First Treatment-Emergent Adverse Event',
        'time_origin': 'TRTSDT',
        'event_source': {'domain': 'AE', 'filter': 'TRTEMFL == "Y"'},
        'censor_rules': ['study_completion', 'data_cutoff'],
    },
    'OS': {
        'PARAM': 'Overall Survival',
        'time_origin': 'TRTSDT',
        'event_source': {'domain': 'DS', 'filter': 'DSTERM contains "Death"'},
        'censor_rules': ['last_contact', 'data_cutoff'],
    },
    'PFS': {
        'PARAM': 'Progression-Free Survival',
        'time_origin': 'TRTSDT',
        'event_source': {'domain': 'custom', 'filter': 'progression or death'},
        'censor_rules': ['last_assessment', 'data_cutoff'],
    },
}
```

---

## AVAL Derivation

```python
def derive_aval(adt, startdt, study_config):
    """
    AVAL = time from origin to event/censor in days.
    Default: AVAL = (ADT - STARTDT) + 1
    Unit controlled by study_config.tte_unit (default: 'DAYS')
    """
    if adt is None or startdt is None:
        return None

    days = (adt - startdt).days + 1
    unit = study_config.get('tte_unit', 'DAYS')
    if unit == 'MONTHS':
        return days / 30.4375
    elif unit == 'WEEKS':
        return days / 7.0
    return days
```

---

## Censoring Derivation

```python
def derive_censoring(subject_data, param_def, study_config):
    """
    Derive CNSR, ADT, EVNTDESC, CNSDTDSC for one subject for one TTE parameter.

    CNSR = 0: event observed
    CNSR = 1: censored (no event observed during observation period)

    Censoring reasons (applied in priority order):
    1. Study completed without event -> CNSR = 1, CNSDTDSC = "Study Completed"
    2. Lost to follow-up -> CNSR = 1, CNSDTDSC = "Lost to Follow-up"
    3. Data cutoff reached -> CNSR = 1, CNSDTDSC = "Data Cutoff"
    4. Withdrew consent -> CNSR = 1, CNSDTDSC = "Withdrew Consent"
    """
    event_records = find_event(subject_data, param_def)

    if event_records is not None and len(event_records) > 0:
        event = event_records.sort_values('event_date').iloc[0]
        return {
            'CNSR': 0, 'ADT': event['event_date'],
            'EVNTDESC': event['event_description'], 'CNSDTDSC': '',
        }
    else:
        censor_date, censor_reason = determine_censor(subject_data, study_config)
        return {
            'CNSR': 1, 'ADT': censor_date,
            'EVNTDESC': '', 'CNSDTDSC': censor_reason,
        }
```

---

## Time Origins

```python
# Time origins are parameter-specific, defined in tte-parameters.yaml
# Common time origins:
# - TRTSDT: First dose date (common for safety TTE endpoints)
# - RFSTDTC: Randomization date (common for efficacy TTE endpoints)
# - RFICDT: Informed consent date (screening failures)

def get_startdt(subject_adsl, param_def):
    """Get time origin date for a subject based on parameter definition."""
    origin_field = param_def.get('time_origin', 'TRTSDT')
    return subject_adsl.get(origin_field)
```

---

## Merge Logic

```python
def build_adtte(sdtm_dir, adsl_path, study_config, param_defs):
    """
    Build ADTTE by deriving TTE parameters for all subjects.

    1. Load ADSL (one record per subject)
    2. Load relevant SDTM domains (AE, DS) for event detection
    3. For each TTE parameter:
       a. Determine time origin (STARTDT) per subject
       b. Find earliest event matching parameter definition
       c. If no event, determine censor date and reason
       d. Derive AVAL = ADT - STARTDT + 1
       e. Derive CNSR (0=event, 1=censored)
    4. Concatenate all parameter records
    """
    adsl = read_xpt(adsl_path)
    all_params = []
    for paramcd, param_def in param_defs.items():
        param_records = derive_tte_parameter(adsl, sdtm_dir, paramcd, param_def, study_config)
        all_params.append(param_records)

    adtte = pd.concat(all_params, ignore_index=True)
    assert not adtte.duplicated(subset=['USUBJID', 'PARAMCD']).any()
    return adtte
```

---

## Output Schema

```yaml
adtte_dataset:
  name: ADTTE
  label: "Time-to-Event Analysis Dataset"
  class: "BDS"
  structure: "One record per subject per parameter"
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
      derivation: "From tte-parameters.yaml"
    - name: PARAM
      type: Char(200)
      label: "Parameter Description"
      required: true
      derivation: "From tte-parameters.yaml"
    - name: AVAL
      type: Num
      label: "Analysis Value (time in days)"
      required: true
      derivation: "ADT - STARTDT + 1"
    - name: CNSR
      type: Num
      label: "Censor (0=event, 1=censored)"
      required: true
      derivation: "0 if event observed, 1 if censored"
    - name: ADT
      type: Num
      label: "Analysis Date (event or censor)"
      required: true
      derivation: "Date of event or censoring"
    - name: STARTDT
      type: Num
      label: "Time Origin Date"
      required: true
      source: ADSL (TRTSDT or RFSTDTC)
    - name: EVNTDESC
      type: Char(200)
      label: "Event Description"
      required: false
    - name: CNSDTDSC
      type: Char(200)
      label: "Censor Description"
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
```

---

## Edge Cases

### Subjects with No Treatment (Screen Failures)
```python
# If TRTSDT is null (screen failure):
# - STARTDT = RFSTDTC or null
# - CNSR = 1 (censored)
# - Define in study_config.tte_screen_failure_handling
```

### Events on Same Day as Time Origin
```python
# Event date = STARTDT:
# - AVAL = 1 (one day of exposure)
# - CNSR = 0 (event observed)
```

### Competing Risks
```python
# For PFS: progression and death are both events
# - Use earliest competing event date
# - Document handling in ADRG
```

### Multiple Events of Same Type
```python
# For TTFAE: multiple AEs possible
# - Use earliest event date (first occurrence)
# - ADT = min(ASTDT) among qualifying events
```

### Partial Dates in Event Records
```python
# For TTE: impute conservatively toward event (minimize AVAL)
# Document imputation rules in ADRG
```

### Data Cutoff Handling
```python
# study_config.data_cutoff_date:
# - Events after cutoff: censored at cutoff
# - Ongoing subjects: censored at cutoff or last contact
```

---

## Integration Points

### Upstream Skills
- `/adam-adsl-builder` -- ADSL with treatment dates, population flags
- `/sdtm-ae-mapper` -- AE domain for event detection
- `/sdtm-ds-mapper` -- DS domain for death/disposition events
- `/sap-parser` -- TTE endpoint definitions from SAP

### Downstream Skills
- `/adam-validator` -- Validate ADTTE compliance
- `/tfl-figure-generator` -- Kaplan-Meier curves, forest plots
- `/tfl-table-generator` -- Survival summary tables
- `/adrg-writer` -- Document ADTTE derivation in ADRG

### Related Skills
- `/adam-traceability-checker` -- Verify SDTM-to-ADTTE traceability
- `/define-draft-builder` -- ADTTE metadata for Define.xml

---

## Evaluation Criteria

**Mandatory:**
- CNSR correctly derived (0=event, 1=censored) per SAP
- AVAL = ADT - STARTDT + 1 (or per SAP-defined formula)
- All SAP-defined TTE endpoints covered
- One record per subject per parameter
- STARTDT consistent across subjects for same parameter

**Recommended:**
- EVNTDESC and CNSDTDSC populated for all records
- Multiple imputation for partial dates documented
- Competing risks handled per SAP

---

## Critical Constraints

**Never:**
- Use CNSR = 0 for censored subjects
- Produce negative AVAL values
- Create duplicate USUBJID+PARAMCD records
- Proceed if ADSL is missing or empty
- Hardcode event definitions

**Always:**
- Derive PARAMCD/PARAM from configuration
- Use STARTDT from ADSL per parameter definition
- Validate CNSR values are only 0 or 1
- Validate AVAL > 0 for all records
- Document all censoring rules in ADRG
- Generate traceable, reproducible results

---

## Examples

### Basic Usage
```bash
adam-adtte-builder --input-dir output/sdtm/ --output output/adam/adtte.xpt --adsl output/adam/adsl.xpt
```

### Specific Event Type
```bash
adam-adtte-builder --input-dir output/sdtm/ --output output/adam/adtte.xpt --adsl output/adam/adsl.xpt --event-type TTFAE
```

### Expected Output
```
ADTTE ({n_subjects} * {n_params} records)
+-- ID: STUDYID, USUBJID ({study_id}-{SITEID}-{SUBJID})
+-- Parameter: PARAMCD, PARAM (from tte-parameters.yaml)
+-- Time: AVAL (days), STARTDT, ADT
+-- Event/Censor: CNSR, EVNTDESC, CNSDTDSC
+-- Treatment: TRTP, TRTA (from ADSL)
+-- Population: SAFFL, ITTFL (from ADSL)
```
