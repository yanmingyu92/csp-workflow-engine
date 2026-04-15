---
name: data-reconciler
description: Reconcile data across sources (EDC vs labs, SAE vs AE). Triggers on "reconciliation", "reconcile", "data reconciliation", "cross-source", "EDC vs lab", "SAE reconciliation".
version: "2.0"
user-invocable: true
context: fork
model: sonnet
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
argument-hint: "[options] -- --input <validated-dir> --output <reports-dir> --sources [edc-vs-lab|sae-vs-ae|rand-vs-treatment|all]"
---

## Runtime Configuration (Step 0)

Resolve configuration in order:
1. `$ARGUMENTS` (highest precedence)
2. `specs/study-config.yaml` -- external data sources, reconciliation rules
3. `ops/raw-validation-log.yaml` -- validation status of inputs
4. `reports/reconciliation-report.html` -- prior reconciliation results

```yaml
config_resolution:
  study_id: "$ARGUMENTS.study_id || study-config.study_id"
  input_dir: "$ARGUMENTS.input || 'data/validated/'"
  output_dir: "$ARGUMENTS.output || 'reports/'"
  source_types: "$ARGUMENTS.sources || ['edc-vs-lab', 'sae-vs-ae', 'rand-vs-treatment']"
```

## EXECUTE NOW
Parse $ARGUMENTS: --input, --output, --sources, --dry-run
**START NOW.**

---

## Philosophy

**Data reconciliation catches discrepancies between independent data sources before they propagate into SDTM.** Every subject, every event, and every value must be consistent across all sources. Unresolved discrepancies are regulatory risks that must be documented and resolved before database lock.

---

## Input/Output Specification

### Inputs (matching regulatory-graph.yaml node `data-reconciliation`)
| Input | Format | Required | Source |
|-------|--------|----------|--------|
| Validated raw datasets | csv/sas7bdat | Yes | data/validated/ |
| External lab data | csv | Conditional | data/external/labs/ |
| SAE narrative data | csv/pdf | Conditional | data/external/sae/ |
| Randomization data | csv | Conditional | data/external/randomization/ |
| Study configuration | yaml | Yes | specs/study-config.yaml |

### Outputs (matching regulatory-graph.yaml node `data-reconciliation`)
| Output | Format | Path Pattern | Description |
|--------|--------|--------------|-------------|
| Reconciliation report | html/pdf | reports/reconciliation-report.html | Discrepancy findings |
| Discrepancy log | yaml | ops/discrepancy-log.yaml | Machine-readable discrepancies |
| Resolution tracker | yaml | ops/discrepancy-resolution.yaml | Status of each discrepancy |

---

## Reconciliation Types

### 1. EDC vs External Laboratory Reconciliation
```python
reconciliation_rules:
  - rule_id: "RECON-LAB-001"
    name: "Lab record count match"
    description: "Every lab result in EDC has a corresponding external lab record"
    method: "match_on(subject_id, test_name, collection_date)"
    severity: "ERROR"
    key_fields:
      edc: ["USUBJID", "LBTEST", "LBDAT"]
      external: ["PATIENT_ID", "TEST_NAME", "COLLECTION_DATE"]

  - rule_id: "RECON-LAB-002"
    name: "Lab value consistency"
    description: "Lab values in EDC match external lab file"
    method: "compare_values(edc_value, external_value, tolerance=0.01)"
    severity: "ERROR"
    tolerance:
      numeric: 0.01  # 1% tolerance for numeric comparisons
      categorical: "exact_match"
      units: "exact_match"

  - rule_id: "RECON-LAB-003"
    name: "Subject count match"
    description: "Same subjects in EDC lab forms and external lab file"
    method: "set_comparison(edc_subjects, external_subjects)"
    severity: "WARNING"
```

### 2. SAE vs AE Reconciliation
```python
reconciliation_rules:
  - rule_id: "RECON-SAE-001"
    name: "All SAEs recorded in AE domain"
    description: "Every serious adverse event in SAE form has a corresponding AE record"
    method: "match_on(subject_id, ae_term, start_date)"
    severity: "ERROR"
    logic: "SAE ⊆ AE (every SAE must appear in AE dataset)"

  - rule_id: "RECON-SAE-002"
    name: "Seriousness flags consistent"
    description: "AESER='Y' in AE matches SAE form"
    method: "compare_flags(ae.aeser, sae.exists)"
    severity: "ERROR"

  - rule_id: "RECON-SAE-003"
    name: "SAE dates match AE dates"
    description: "Start and end dates for SAEs match between SAE form and AE records"
    method: "compare_dates(ae.aestdat, sae.sae_start_date)"
    severity: "WARNING"
```

### 3. Randomization vs Treatment Reconciliation
```python
reconciliation_rules:
  - rule_id: "RECON-RAND-001"
    name: "Treatment arm assignment match"
    description: "Actual treatment received matches randomized assignment"
    method: "compare_values(dm.arm, randomization.assigned_arm)"
    severity: "WARNING"
    note: "Mismatch may indicate protocol deviation or randomization error"

  - rule_id: "RECON-RAND-002"
    name: "All randomized subjects in DM"
    description: "Every subject in randomization list appears in demographics"
    method: "set_comparison(randomized_subjects, dm_subjects)"
    severity: "ERROR"

  - rule_id: "RECON-RAND-003"
    name: "Randomization strata consistent"
    description: "Stratification factors in randomization match DM values"
    method: "compare_strata(randomization.strata, dm.demographic_values)"
    severity: "WARNING"
```

---

## Output Schema

```yaml
reconciliation_result:
  study_id: "{study_id}"
  reconciliation_timestamp: "{ISO_8601}"
  source_pairs_checked:
    - source_a: "EDC Lab Forms"
      source_b: "Central Lab File"
      records_compared: "{n_records}"
      matches: "{n_matches}"
      discrepancies: "{n_discrepancies}"
    - source_a: "SAE Forms"
      source_b: "AE Domain"
      records_compared: "{n_records}"
      matches: "{n_matches}"
      discrepancies: "{n_discrepancies}"

  discrepancies:
    - discrepancy_id: "DISC-001"
      rule_id: "RECON-LAB-002"
      severity: "ERROR"
      subject: "{study_id}-{SITEID}-{SUBJID}"
      source_a_value: "142.5 mg/dL"
      source_b_value: "142.0 mg/dL"
      field: "GLUCOSE result"
      status: "OPEN"
      assigned_to: "{data_manager}"
```

---

## Edge Cases

### Date Format Mismatches
- EDC uses DD-MON-YYYY, external lab uses YYYY-MM-DD
- Solution: Normalize both to ISO 8601 before comparison
- Partial dates: Document imputation method used

### Unit Conversion Reconciliation
- EDC may record in mg/dL while external lab reports in mmol/L
- Must apply correct conversion factors before comparison
- Document all conversions in the reconciliation report

### Missing External Data
- External lab file may not include all sites or visits
- Distinguish between "missing from external" vs "not yet transferred"
- Flag but do not fail if external data is known to be incomplete

### Multiple SAE Reports for Same Event
- SAE may be reported multiple times (initial, follow-up, final)
- Reconcile against the most updated AE record
- Document which SAE report version was used

---

## Integration Points

### Upstream Skills
- `/data-validator` -- Validated raw datasets required before reconciliation
- `/data-extract` -- Raw data extraction including external data files
- `/study-setup` -- Treatment arm definitions, randomization scheme

### Downstream Skills
- `/quality-report` -- Incorporates reconciliation findings
- `/sdtm-dm-mapper` -- Uses reconciled treatment arm assignments

### Related Skills
- `/data-quality` -- Universal quality checks
- `/workflow` -- Track reconciliation completion

---

## Evaluation Criteria

**Mandatory:**
- All cross-source discrepancies documented with severity
- Subject-level matching verified (no orphan records)
- Date and value comparisons with documented tolerance
- Discrepancy resolution tracked with status and owner

**Recommended:**
- Trend analysis across multiple reconciliation runs
- Automated re-reconciliation after discrepancy resolution
- Statistical summary of discrepancy rates by source pair

---

## Critical Constraints

**Never:**
- Produce reconciliation report without validating input data
- Ignore discrepancies or suppress findings
- Reconcile against unvalidated external data
- Proceed to SDTM mapping with unresolved critical discrepancies

**Always:**
- Validate all inputs before reconciliation
- Document any deviations from standard reconciliation rules
- Generate traceable, reproducible results
- Assign ownership for every open discrepancy
- Preserve source values alongside reconciliation results

---

## Examples

### Full Reconciliation
```bash
python csp-skills/layer-1-raw-data/data-reconciler/script.py \
  --input data/validated/ \
  --output reports/ \
  --sources all \
  --study-config specs/study-config.yaml
```

### SAE-AE Reconciliation Only
```bash
python csp-skills/layer-1-raw-data/data-reconciler/script.py \
  --input data/validated/ \
  --output reports/ \
  --sources sae-vs-ae
```

### Expected Output
```
reports/reconciliation-report.html
ops/discrepancy-log.yaml
ops/discrepancy-resolution.yaml
```
