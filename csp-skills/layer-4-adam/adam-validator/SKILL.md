---
name: adam-validator
description: Validate ADaM dataset compliance. Triggers on "ADSL", "subject level", "population flags", "SAFFL", "ITTFL", "PPROTFL".
version: "2.0"
user-invocable: true
context: fork
model: sonnet
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
argument-hint: "[options] -- --input, --output"
---

## Runtime Configuration (Step 0)

### Config Resolution
1. Read ops/workflow-state.yaml for current workflow state
2. Read specs/study-config.yaml for study metadata
3. If missing, fall back to --study-config argument
4. If neither available, log error and abort

### Required Reads
ADaM datasets: {output_dir}/adam/*.xpt
Specifications: {adam_spec_path}, specs/study-config.yaml

## EXECUTE NOW
Parse $ARGUMENTS: --input, --output, --study-config, --spec, --adsl, --dry-run
**START NOW.**

---

## Philosophy
**ADaM validation checks structural compliance and content correctness.** ADaM datasets must satisfy ADaM Implementation Guide (ADaM IG v1.3) requirements: correct structure, traceability to SDTM, proper variable naming, and analytical readiness. Validation catches errors before they propagate to TFL tables and the CSR.

**Key Principle:** Each check is traceable to ADaM IG rules or study-specific requirements from the SAP. Validation reports provide actionable findings with severity levels and affected records.

---

### Inputs (from regulatory-graph.yaml node schema)
| Input | Type | Format | Required | Source |
|-------|------|--------|----------|--------|
| All ADaM datasets | dataset | xpt | Yes | output/adam/*.xpt |
| ADaM derivation specification | specification | xlsx/yaml | Yes | specs/adam-derivation-spec.xlsx |
| Study configuration | specification | yaml | Yes | specs/study-config.yaml |
| SDTM DM domain (for cross-checks) | dataset | xpt | No | output/sdtm/dm.xpt |

### Outputs (to regulatory-graph.yaml node schema)
| Output | Type | Format | Path Pattern |
|--------|------|--------|-------------|
| ADaM validation report | report | yaml | reports/adam-validation-report.yaml |

---

## Script Execution

```bash
python {script_path} \
  --input {output_dir}/adam/ \
  --output reports/adam-validation-report.yaml \
  --spec {adam_spec_path} \
  --study-config specs/study-config.yaml \
  --adsl {output_dir}/adam/adsl.xpt
```

### Arguments
| Argument | Required | Description |
|----------|----------|-------------|
| `--input` | Yes | Directory containing ADaM XPT files |
| `--output` | Yes | Output path for validation report |
| `--spec` | No | ADaM specification YAML |
| `--study-config` | Yes | Study configuration YAML |
| `--adsl` | No | Path to ADSL for cross-dataset checks |
| `--dry-run` | No | Show validation plan without running |

---

## Validation Checks

### ADSL (Subject-Level) Checks

| Check ID | Description | Severity |
|----------|-------------|----------|
| ADSL001 | One record per subject (USUBJID unique) | Error |
| ADSL002 | All DM subjects present | Error |
| ADSL003 | SAFFL derived correctly per study_config.population_definitions | Error |
| ADSL004 | ITTFL derived correctly (randomized subjects) | Error |
| ADSL005 | TRT01P populated from DM.ARM | Error |
| ADSL006 | TRT01A populated (ACTARM or ARM fallback) | Warning |
| ADSL007 | TRTSDT <= TRTEDT for treated subjects | Error |
| ADSL008 | Population flags are Y/N only | Error |
| ADSL009 | Required variables present (STUDYID, USUBJID, TRT01P, SAFFL) | Error |
| ADSL010 | No duplicate USUBJIDs | Error |

### BDS (Basic Data Structure) Checks

| Check ID | Description | Severity |
|----------|-------------|----------|
| BDS001 | PARAMCD unique within subject+timepoint | Error |
| BDS002 | AVAL and AVALC consistent (where both exist) | Error |
| BDS003 | BASE derived correctly (first post-baseline value) | Warning |
| BDS004 | CHG = AVAL - BASE (where both present) | Error |
| BDS005 | PCHG = (CHG / BASE) * 100 (where BASE != 0) | Error |
| BDS006 | ADSL merge complete (all USUBJIDs in ADSL) | Error |
| BDS007 | SAFFL inherited from ADSL | Error |
| BDS008 | Treatment variables inherited from ADSL | Error |

### ADAE-Specific Checks

| Check ID | Description | Severity |
|----------|-------------|----------|
| ADAE001 | All AE USUBJIDs exist in ADSL | Error |
| ADAE002 | TRTEMFL derived correctly per SAP and study_config | Error |
| ADAE003 | ASTDT >= TRTSDT for TRTEMFL='Y' records | Error |
| ADAE004 | AEDECOD present for all records | Error |
| ADAE005 | AEBODSYS present for all records | Error |
| ADAE006 | No orphan AE records (no ADSL match) | Error |

### Cross-Dataset Checks

| Check ID | Description | Severity |
|----------|-------------|----------|
| X001 | ADSL subject count matches DM | Error |
| X002 | All ADaM USUBJIDs exist in ADSL | Error |
| X003 | Treatment variables consistent across ADaM datasets | Error |
| X004 | Population flags consistent across ADaM datasets | Error |

---

## Validation Logic

### ADSL Structure Check
```python
def validate_adsl_structure(adsl, dm, study_config):
    """
    Validate ADSL structural compliance.

    1. One record per subject (no duplicates)
    2. Subject count matches DM
    3. All DM USUBJIDs present in ADSL
    4. Required variables non-null
    5. Treatment arms match study_config.treatment_arms
    """
    results = []

    # Check 1: No duplicate USUBJIDs
    dup = adsl[adsl.duplicated(subset='USUBJID', keep=False)]
    if len(dup) > 0:
        results.append(CheckResult('ADSL001', 'Error',
            f"{len(dup)} duplicate USUBJIDs in ADSL"))

    # Check 2: Subject count matches DM
    if len(adsl) != len(dm):
        results.append(CheckResult('ADSL002', 'Error',
            f"ADSL has {len(adsl)} subjects, DM has {len(dm)}"))

    # Check 3: All DM subjects present
    dm_subjects = set(dm['USUBJID'])
    adsl_subjects = set(adsl['USUBJID'])
    missing = dm_subjects - adsl_subjects
    if missing:
        results.append(CheckResult('ADSL002', 'Error',
            f"{len(missing)} DM subjects missing from ADSL"))

    # Check 4: Required variables non-null
    required = ['STUDYID', 'USUBJID', 'TRT01P', 'SAFFL']
    for var in required:
        null_count = adsl[var].isna().sum()
        if null_count > 0:
            results.append(CheckResult('ADSL009', 'Error',
                f"{var} has {null_count} null values"))

    # Check 5: Treatment arms from study config
    treatment_arms = study_config.get('treatment_arms', [])
    valid_arm_names = {arm['arm'] for arm in treatment_arms}
    invalid_arms = set(adsl['TRT01P'].unique()) - valid_arm_names
    if invalid_arms:
        results.append(CheckResult('ADSL005', 'Warning',
            f"TRT01P values not in study_config.treatment_arms: {invalid_arms}"))

    return results
```

### Population Flag Validation
```python
def validate_population_flags(adsl, ex, study_config):
    """
    Validate population flag derivations per study_config.

    SAFFL: per study_config.population_definitions.safety criteria
    ITTFL: per study_config.population_definitions.itt criteria
    """
    results = []
    screen_failure_code = study_config.get('screen_failure_code', 'Scrnfail')

    for _, row in adsl.iterrows():
        usubjid = row['USUBJID']
        subject_ex = ex[ex['USUBJID'] == usubjid]

        # SAFFL check using study config criteria
        has_dose = (subject_ex['EXDOSE'] > 0).any() if len(subject_ex) > 0 else False
        expected_saffl = 'Y' if has_dose else 'N'
        if row['SAFFL'] != expected_saffl:
            results.append(CheckResult('ADSL003', 'Error',
                f"SAFFL mismatch for {usubjid}: expected {expected_saffl}, got {row['SAFFL']}"))

        # ITTFL check using study config criteria
        expected_ittfl = 'Y' if row.get('ARMCD') != screen_failure_code else 'N'
        if row.get('ITTFL') != expected_ittfl:
            results.append(CheckResult('ADSL004', 'Error',
                f"ITTFL mismatch for {usubjid}: expected {expected_ittfl}, got {row.get('ITTFL')}"))

    return results
```

### ADAE Cross-Dataset Check
```python
def validate_adae_cross(adae, adsl):
    """
    Validate ADAE-ADSL consistency.

    1. All ADAE USUBJIDs exist in ADSL
    2. Treatment variables match ADSL
    3. SAFFL consistent
    """
    results = []

    adsl_subjects = set(adsl['USUBJID'])
    adae_subjects = set(adae['USUBJID'])

    # Orphan AE records
    orphans = adae_subjects - adsl_subjects
    if orphans:
        results.append(CheckResult('ADAE006', 'Error',
            f"{len(orphans)} subjects in ADAE not found in ADSL"))

    return results
```

---

## Output Schema

```yaml
adam_validation_report:
  date: "{timestamp}"
  study_id: "{study_id} from study config"
  datasets_validated: []
  spec_version: "ADaM IG v1.3"

  summary:
    total_checks: 0
    passed: 0
    errors: 0
    warnings: 0
    info: 0

  results:
    - check_id: "ADSL001"
      dataset: "ADSL"
      description: "One record per subject"
      severity: "Error"
      status: "PASS"
      details: "{n_subjects} unique USUBJIDs, no duplicates"

    - check_id: "ADAE006"
      dataset: "ADAE"
      description: "Orphan AE records"
      severity: "Error"
      status: "FAIL"
      details: "{n_orphans} subjects in ADAE not found in ADSL"
      affected_records: []
```

---

## Edge Cases

### Screen Failures in ADSL
```python
# Screen failures identified by study_config.screen_failure_code:
# - SAFFL = 'N', ITTFL = 'N'
# - TRTSDT = null, TRTEDT = null
# - Still present in ADSL (counted in total subjects)
# Not flagged as validation errors
```

### Missing Optional Variables
```python
# Optional variables (PPROTFL, ETHNIC, DTHDT):
# - Null values are acceptable
# - Do NOT flag as errors
# - May flag as warning if unexpectedly null
```

### Dose Modifications
```python
# TRT01A may differ from TRT01P:
# - Subject started on one treatment, switched to another
# - Not a validation error if ACTARM reflects actual treatment
# - Verify TRT01A = DM.ACTARM when ACTARM available
```

---

## Integration Points

### Upstream Skills
- `/adam-adsl-builder` -- ADSL to validate
- `/adam-adae-builder` -- ADAE to validate
- `/adam-adlb-builder` -- ADLB to validate
- `/adam-adtte-builder` -- ADTTE to validate
- `/adam-adeff-builder` -- ADEFF to validate

### Downstream Skills
- `/tfl-table-generator` -- Validated ADaM feeds TFL
- `/tfl-qc-validator` -- Uses validated ADaM for QC
- `/adrg-writer` -- Document validation results in ADRG

### Related Skills
- `/adam-traceability-checker` -- SDTM-to-ADaM traceability
- `/p21-adam-validation` -- P21 ADaM-specific rules
- `/define-draft-builder` -- ADaM metadata for Define.xml

---

## Evaluation Criteria

**Mandatory:**
- All SAP-defined population flags derived per study_config
- TRTSDT/TRTEDT correctly derived per SAP
- ADSL: one record per subject
- All subjects from DM represented in ADSL
- All ADaM USUBJIDs exist in ADSL
- Validation report generated with pass/fail per check

**Recommended:**
- Baseline flags aligned with SAP
- CHG/PCHG calculations validated
- Treatment variables consistent across ADaM datasets
- Zero validation errors

---

## Critical Constraints

**Never:**
- Produce output without validation
- Skip required variable checks
- Ignore cross-dataset consistency issues
- Proceed to TFL with validation errors
- Hardcode treatment arm names or ARMCD values
- Proceed if study config is missing

**Always:**
- Validate all inputs before processing
- Cross-reference ADSL with DM for completeness
- Check all ADaM datasets against ADSL
- Resolve study metadata dynamically from ops/workflow-state.yaml or --study-config
- Read treatment arms and population definitions from study config
- Document any deviations from standards
- Generate traceable, reproducible results

---

## Examples

### Basic Usage
```bash
python {script_path} \
  --input {output_dir}/adam/ \
  --output reports/adam-validation-report.yaml \
  --study-config specs/study-config.yaml
```

### With Spec
```bash
python {script_path} \
  --input {output_dir}/adam/ \
  --output reports/adam-validation-report.yaml \
  --spec {adam_spec_path} \
  --adsl {output_dir}/adam/adsl.xpt \
  --study-config specs/study-config.yaml
```

### Expected Output
```
reports/adam-validation-report.yaml
|-- Summary (total, passed, errors, warnings)
|-- ADSL checks (structure, flags, treatment)
|-- ADAE checks (merge, TRTEMFL, dates)
|-- BDS checks (PARAMCD, AVAL, BASE, CHG)
+-- Cross-dataset checks (consistency)
```
