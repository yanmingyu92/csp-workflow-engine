---
name: data-extract
description: Extract raw clinical data from EDC system or data repository. Triggers on "EDC", "data extraction", "raw data", "data cut", "extract data".
version: "2.0"
user-invocable: true
context: fork
model: sonnet
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
argument-hint: "[options] -- --input <edc-path> --output <output-dir> --format [csv|sas7bdat|both]"
---

## Runtime Configuration (Step 0)

Resolve configuration in order:
1. `$ARGUMENTS` (highest precedence)
2. `specs/study-config.yaml` -- study_id, treatment_arms, visit_schedule
3. `ops/workflow-state.yaml` -- current node, data_cut_date
4. `data/raw/extraction-manifest.yaml` -- prior extraction state

```yaml
config_resolution:
  study_id: "$ARGUMENTS.study_id || study-config.study_id"
  data_cut_date: "$ARGUMENTS.data_cut_date || workflow-state.data_cut_date || today()"
  output_format: "$ARGUMENTS.format || study-config.extraction_format || 'csv'"
  edc_system: "$ARGUMENTS.edc_system || study-config.edc_system || 'auto-detect'"
```

## EXECUTE NOW

Parse $ARGUMENTS: --input, --output, --format, --data-cut-date, --dry-run
**START NOW.**

---

## Philosophy

**Data extraction is the gateway to analysis.** Raw data from EDC systems must be extracted, documented, and validated before any mapping or derivation can begin. The extraction manifest provides traceability for regulatory submissions under 21 CFR Part 11. Every extraction is an immutable snapshot: source data is never modified during extraction.

---

## Input/Output Specification

### Inputs (matching regulatory-graph.yaml node `edc-extract`)
| Input | Format | Required | Source |
|-------|--------|----------|--------|
| Study configuration | yaml | Yes | specs/study-config.yaml |
| EDC export files | csv/sas7bdat/xml | Yes | EDC system export |
| Data transfer specification | yaml | No | specs/dts-spec.yaml |

### Outputs (matching regulatory-graph.yaml node `edc-extract`)
| Output | Format | Path Pattern | Description |
|--------|--------|--------------|-------------|
| Raw datasets | csv/sas7bdat | data/raw/{domain}.csv | One file per CRF form/domain |
| Extraction manifest | yaml | data/raw/extraction-manifest.yaml | Timestamp, data cut, row counts |
| EDC audit trail | csv | data/raw/audit-trail.csv | Optional: EDC change history |

---

## EDC Extraction Manifest Format

The extraction manifest is the regulatory artifact that documents exactly what was extracted, when, and from where.

```yaml
# data/raw/extraction-manifest.yaml
extraction_id: "{study_id}-extract-{timestamp}"
study_id: "{study_id}"
data_cut_date: "{data_cut_date}"
extraction_timestamp: "{ISO_8601_timestamp}"
edc_system: "{edc_system_name}"
edc_version: "{edc_version}"
operator: "{extracted_by}"
config_file: "specs/study-config.yaml"

datasets:
  - domain: "DM"
    source: "edc://forms/demographics"
    filename: "data/raw/dm.csv"
    row_count: {n_subjects}
    column_count: 42
    hash_md5: "{md5_checksum}"
    encoding: "UTF-8"
  - domain: "AE"
    source: "edc://forms/adverse-events"
    filename: "data/raw/ae.csv"
    row_count: "{n_ae_records}"
    column_count: 38
    hash_md5: "{md5_checksum}"
    encoding: "UTF-8"
  # ... one entry per extracted domain

quality_summary:
  total_subjects: {n_subjects}
  total_records: "{total_record_count}"
  forms_extracted: "{n_forms}"
  extraction_duration_seconds: "{duration}"
```

---

## Domain-Specific Extraction Logic

### Raw Data Structure Requirements

Each extracted domain must follow this structure:

| Column Pattern | Description | Example |
|----------------|-------------|---------|
| STUDYID | Study identifier | "{study_id}" |
| SITEID | Site identifier | "001", "002" |
| SUBJID | Subject number within site | "001", "002" |
| VISIT | Visit name | "Screening", "Week 4" |
| VisitDate | Collection date | ISO 8601 date |
| FormVar_* | CRF form variables | Domain-specific |

### EDC System Handling

| EDC System | Export Format | Key Considerations |
|------------|---------------|-------------------|
| Medidata Rave | XML/CSV | Extract via Rave Web Services; handle Rave date formats |
| Oracle InForm | CSV/SAS7BDAT | Use Inform Data Export utility; handle multi-select encoding |
| Veeva Vault CDMS | CSV | Use Vault API; handle form versioning |
| Castor EDC | CSV/JSON | REST API extraction; handle calculated fields |

### Subject Identifier Construction

```python
# USUBJID derivation from raw EDC data
USUBJID = f"{study_id}-{SITEID.zfill(3)}-{SUBJID.zfill(3)}"
# Example: "{study_id}-001-001", "{study_id}-002-015"
```

---

## Output Schema

```yaml
output_schema:
  raw_dataset:
    type: "tabular"
    format: "csv | sas7bdat"
    encoding: "UTF-8"
    columns:
      - name: "STUDYID"
        type: "string"
        description: "Study identifier"
      - name: "SITEID"
        type: "string"
        description: "Site identifier"
      - name: "SUBJID"
        type: "string"
        description: "Subject number"
    constraints:
      - "No duplicate STUDYID-SITEID-SUBJID combinations within domain"
      - "All date fields in ISO 8601 format or raw EDC format (document which)"

  extraction_manifest:
    type: "yaml"
    required_fields:
      - "extraction_id"
      - "study_id"
      - "data_cut_date"
      - "extraction_timestamp"
      - "datasets[].domain"
      - "datasets[].row_count"
      - "datasets[].hash_md5"
```

---

## Edge Cases

### Partial Data Cuts
- Data cut date may fall mid-visit: document which partial visits are included
- Some subjects may have incomplete CRFs: extract all available data
- EDC lock status varies by site: document site-level lock status

### Multi-Part Exports
- Large EDC exports may be split into multiple files: merge by domain
- Different EDC forms may be exported separately: unify by subject identifiers
- Handle EDC-specific delimiters and quoting conventions

### Encoding Issues
- EDC exports may contain mixed encodings (UTF-8, Latin-1)
- Special characters in free-text fields (AETERM, CMTRT) must be preserved
- Null representations vary by EDC: detect and standardize (empty string, "NULL", "N/A", ".")

### Date Format Variability
- EDC date formats: DD-MON-YYYY, YYYY-MM-DD, MM/DD/YYYY
- Document source date format in extraction manifest
- Preserve original format in raw extraction; conversion happens during validation

---

## Integration Points

### Upstream Skills
- `/study-setup` -- Study configuration with EDC system details
- `/workflow` -- Tracks extraction completion status

### Downstream Skills
- `/data-validator` -- Validates extracted raw datasets
- `/data-reconciler` -- Cross-source reconciliation
- `/quality-report` -- Quality metrics from extraction

### Related Skills
- `/crf-annotator` -- Maps CRF fields to SDTM targets
- `/data-quality` -- Universal quality checks on extracted data

---

## Evaluation Criteria

**Mandatory:**
- All CRF forms extracted (verified against study-config visit schedule)
- Extraction manifest documents data cut date and extraction timestamp
- Row counts verified against EDC system dashboard counts
- Each dataset has MD5 checksum recorded
- Subject count matches expected enrollment

**Recommended:**
- Data exported in both CSV and SAS7BDAT formats
- Include EDC audit trail for traceability
- Verify no subject data from sites not yet locked (if applicable)
- Validate STUDYID consistency across all extracted domains

---

## Critical Constraints

**Never:**
- Modify source data during extraction (immutable extraction)
- Skip extraction manifest creation
- Proceed without documenting data cut criteria
- Alter EDC date formats during extraction (preserve originals)
- Mix data from different data cuts in the same extraction
- Extract data without verifying EDC system connectivity and credentials

**Always:**
- Generate MD5 checksums for all extracted files
- Document the EDC system version and export tool version
- Include subject counts in the manifest for reconciliation
- Preserve EDC variable names (rename happens during mapping, not extraction)
- Record the operator and timestamp for 21 CFR Part 11 compliance

---

## Examples

### Basic Extraction
```bash
python csp-skills/layer-1-raw-data/data-extract/script.py \
  --input edc-exports/ \
  --output data/raw/ \
  --study-config specs/study-config.yaml \
  --format csv
```

### Extraction with Data Cut
```bash
python csp-skills/layer-1-raw-data/data-extract/script.py \
  --input edc-exports/ \
  --output data/raw/ \
  --study-config specs/study-config.yaml \
  --data-cut-date 2024-06-30 \
  --format both \
  --dry-run
```

### Expected Output
```
data/raw/
  extraction-manifest.yaml
  dm.csv
  ae.csv
  lb.csv
  vs.csv
  cm.csv
  mh.csv
  ex.csv
  ds.csv
  sv.csv
  audit-trail.csv
```
