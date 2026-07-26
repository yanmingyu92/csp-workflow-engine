---
name: p21-validator
description: Run Pinnacle 21 validation on datasets. Triggers on "P21", "Pinnacle 21", "SDTM validation", "P21 validation", "compliance check", "validation report".
version: "3.0"
user-invocable: true
context: fork
model: sonnet
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
argument-hint: "[options] -- --input, --output"
---

## Runtime Configuration (Step 0)

### Config Resolution
1. Read `ops/workflow-state.yaml` for current workflow state
2. Read `specs/study-config.yaml` for study metadata (`study_id`, `sdtm_domains`, `ct_version`, `ct_package_url`)
3. Resolve path patterns from `regulatory-graph.yaml` node `p21-sdtm-validation` definitions
4. If critical config missing, log error and abort

### Required Config Keys
| Key | Source | Fallback |
|-----|--------|----------|
| `study_id` | `specs/study-config.yaml` | Required - abort if missing |
| `sdtm_domains` | `specs/study-config.yaml` | Required - abort if missing |
| `ct_version` | `specs/study-config.yaml` | Required - abort if missing |
| `ct_package_url` | `specs/study-config.yaml` | Required - abort if missing |
| `input_dir` | `--input` argument | `output/sdtm/` |
| `output_report` | `--output` argument | `reports/p21-sdtm-report.xlsx` |
| `issue_tracker` | `regulatory-graph.yaml` path_pattern | `ops/p21-sdtm-issues.yaml` |

## EXECUTE NOW
Parse $ARGUMENTS: --input, --output, --spec, --validate, --dry-run
**START NOW.**

---

## Philosophy
**Pinnacle 21 is a validation tool, not a declaration of regulatory compliance.**
Its findings depend on the product, engine/rule-catalog release, selected agency
profile, standard versions, and controlled-terminology packages. A clean run is a
quality target, but neither a zero-count report nor an individual severity label
establishes submission acceptability.

**Key Principle:** Import actual finding identifiers, severities, messages, and
record keys from the executed report. Never synthesize a rule ID or infer a
disposition from a generic example. The report and resolution log are sponsor QC
artifacts; material data issues may be summarized in the SDRG/ADRG, but the
validator workbook itself is not automatically an eCTD deliverable.

---

## Input/Output Specification

### Inputs (from `regulatory-graph.yaml` node `p21-sdtm-validation`)
| Input | Format | Path Pattern | Required |
|-------|--------|--------------|----------|
| All SDTM domain datasets | xpt | `output/sdtm/*.xpt` | Yes |
| Study configuration | yaml | `specs/study-config.yaml` | Yes |
| P21 engine config | xml | `configs/p21-config.xml` | No |
| Define.xml draft | xml | `output/define/define-sdtm-draft.xml` | No |

### Outputs (from `regulatory-graph.yaml` node `p21-sdtm-validation`)
| Output | Format | Path Pattern | Description |
|--------|--------|--------------|-------------|
| P21 SDTM validation report | xlsx | `reports/p21-sdtm-report.xlsx` | Full issue report with severity |
| P21 issue tracker | yaml | `ops/p21-sdtm-issues.yaml` | Categorized issues with resolution status |

---

## Script Execution

```bash
python csp-skills/layer-3-sdtm-qc/p21-validator/script.py \
  --input {input_dir} \
  --output {output_report} \
  --config {p21_config} \
  --study-config specs/study-config.yaml
```

### Arguments
| Argument | Required | Description |
|----------|----------|-------------|
| `--input` | Yes | Directory or single XPT file to validate |
| `--output` | Yes | Output path for P21 report (XLSX) |
| `--study-config` | No | Study configuration YAML for dynamic config |
| `--config` | No | P21 engine configuration XML |
| `--define` | No | Define.xml for metadata-based rules |
| `--ct` | No | Controlled terminology version (overrides study-config) |
| `--dry-run` | No | Show validation plan without running |

---

## Validation Rule Categories

### Versioned Rule-Catalog Handling

Do not treat prefixes such as `SD00xx` or `IG00xx` as a stable public taxonomy.
Rule IDs, severities, availability, and messages are engine-version-specific.
The executable validation record must capture:

- product/edition and engine version;
- rule-catalog or configuration version and agency profile;
- SDTM/SDTMIG or ADaM/ADaMIG versions;
- CDISC CT package date and external dictionary versions;
- input dataset and Define-XML SHA-256 values;
- exact finding ID, severity, message, dataset, variable, record keys, and count
  as returned by the engine.

### Versioned Finding Handling

Never infer a Pinnacle 21 rule identifier from a generic data-quality issue. Rule
identifiers, messages, severity, and availability must be copied verbatim from the
frozen engine output and interpreted against the matching rule catalog. Domain
review may group findings by dataset and variable, but it must retain the original
finding identifier and record keys. A remediation may change data, metadata, or
configuration only after the finding is reproduced with the recorded engine,
agency profile, standards versions, and terminology packages.

Potential data issues that are not emitted by the frozen engine are reported in a
separate sponsor-QC section without a fabricated Pinnacle 21 identifier.

---

## Validation Process

### Step 1: Load Configuration
```python
def load_study_config(config_path):
    """
    Load study configuration for dynamic validation parameters.

    Required keys:
      - study_id: unique study identifier
      - sdtm_domains: list of expected SDTM domains
      - ct_version: controlled terminology package version
      - ct_package_url: URL for CT package
    """
    config = read_yaml(config_path)
    required_keys = ['study_id', 'sdtm_domains', 'ct_version', 'ct_package_url']
    missing = [k for k in required_keys if k not in config]
    if missing:
        log_error(f"Missing critical study config keys: {missing}")
        abort()
    return config
```

### Step 2: Run P21 Engine
```python
def run_p21_validation(sdtm_dir, study_config, define_xml=None):
    """
    Execute P21 validation on all SDTM datasets.

    1. Load all XPT files from sdtm_dir matching study_config.sdtm_domains
    2. Run the configured, version-pinned engine and rule catalog
    3. Preserve returned findings without rewriting identifiers or severity
    4. Check controlled terminology against the pinned package date
    5. Generate issue report
    """
    datasets = load_xpt_files(sdtm_dir, domains=study_config['sdtm_domains'])
    issues = []

    for dataset in datasets:
        domain_issues = validate_domain(dataset, rules=SDTM_IG_3_4)
        issues.extend(domain_issues)

        if define_xml:
            metadata_issues = validate_against_define(dataset, define_xml)
            issues.extend(metadata_issues)

    return issues
```

### Step 3: Classify Issues
```python
def classify_issues(issues):
    """
    Separate issues by severity for triage.
    """
    errors = [i for i in issues if i.severity == 'Error']
    warnings = [i for i in issues if i.severity == 'Warning']
    info = [i for i in issues if i.severity == 'Info']

    return {
        'errors': errors,      # MUST fix
        'warnings': warnings,  # MUST review and justify or fix
        'info': info           # SHOULD review
    }
```

### Step 4: Generate Tracking File
```python
def generate_issue_tracking(issues, output_path, study_id):
    """
    Create ops/p21-sdtm-issues.yaml for issue tracking.

    All USUBJID references use format: {study_id}-{SITEID}-{SUBJID}
    """
    tracking = []
    for issue in issues:
        tracking.append({
            'rule_id': issue.rule_id,
            'dataset': issue.dataset,
            'variable': issue.variable,
            'severity': issue.severity,
            'message': issue.message,
            'resolution': 'open',  # open, fixed, justified, deferred
            'notes': ''
        })

    write_yaml(tracking, output_path)
```

---

## Output Schema

```yaml
p21_report:
  format: XLSX
  sheets:
    - name: "Issues"
      columns:
        - name: Dataset
          type: string
          description: "Domain name from {sdtm_domains}"
        - name: Variable
          type: string
          description: "Variable with issue"
        - name: Rule_ID
          type: string
          description: "P21 rule identifier (e.g., SD0007)"
        - name: Severity
          type: string
          enum: ["Error", "Warning", "Info"]
        - name: Message
          type: string
          description: "Issue description"
        - name: USUBJID
          type: string
          description: "Affected subject(s), format: {study_id}-{SITEID}-{SUBJID}"
        - name: Value
          type: string
          description: "Current value causing issue"
        - name: Count
          type: integer
          description: "Number of occurrences"

    - name: "Summary"
      columns:
        - name: Dataset
          type: string
        - name: Errors
          type: integer
        - name: Warnings
          type: integer
        - name: Info
          type: integer

  issue_tracking:
    file: "{issue_tracker_path from regulatory-graph.yaml}"
    format:
      - rule_id: "SD0007"
        dataset: "DM"
        severity: "Error"
        resolution: "fixed"
        notes: "Derived RFSTDTC from EX domain"
```

---

## Edge Cases

### False Positive Warnings
```python
# Some P21 warnings are acceptable:
# - SD0043 "Variable is not expected" -> may be study-specific
# - SD0059 "Duplicate records" -> may be valid (e.g., multiple AEs same day)
# Document justification in issue tracking file
```

### Controlled Terminology Version Mismatch
```python
# CT version in Define.xml doesn't match P21 engine:
# - Resolve ct_version from study-config.yaml
# - Update CT in Define.xml to match submission requirement
# - Or configure P21 to use specific CT version from study config
# - Document CT version used in validation
```

### Empty Datasets
```python
# Domain exists but has zero records:
# - May be valid (e.g., no MH records collected)
# - P21 may flag as warning
# - Justify in issue tracking if expected
# - Only validate domains listed in study_config.sdtm_domains
```

### Missing Study Config
```python
# If specs/study-config.yaml is missing or incomplete:
# - Log error with specific missing keys
# - Abort validation rather than use hardcoded defaults
# - Provide actionable error message directing user to configure study
```

### Domain-Specific Validation Gaps
```python
# If study_config.sdtm_domains does not include a domain that exists in output/sdtm/:
# - Warn the user about unexpected datasets
# - Validate anyway to catch issues, but flag for config review
# - If domain is expected but missing, that is an error
```

---

## Integration Points

### Upstream Skills
- `/sdtm-dm-mapper` -- DM domain to validate
- `/sdtm-ae-mapper` -- AE domain to validate
- `/sdtm-ex-mapper` -- EX domain to validate
- `/sdtm-validator` -- Pre-P21 structural validation
- `/define-draft-builder` -- Define.xml for metadata validation
- `/study-setup` -- Study configuration providing study_id, sdtm_domains, ct_version

### Downstream Skills
- `/p21-report-reviewer` -- Detailed review and resolution of issues
- `/sdtm-consistency-checker` -- Cross-domain consistency validation
- `/sdrg-writer` -- Document P21 results in SDRG

### Related Skills
- `/data-quality` -- Data quality checks before validation
- `/sdtm-supp-builder` -- Supplemental qualifiers that may trigger issues

---

## Evaluation Criteria

**Mandatory:**
- Every returned finding has a documented disposition based on source data,
  specifications, and the active rule documentation
- No unresolved finding that the study team classifies as submission-blocking
- Validation report generated in XLSX format
- Issue tracking file created at path from regulatory-graph.yaml
- Study config loaded with all required keys
- CT version from study config used for validation

**Recommended:**
- Independent confirmation that engine/configuration/version metadata and input
  hashes are complete
- All informational items reviewed
- CT version documented in report metadata
- Define.xml referenced for metadata rules

---

## Critical Constraints

**Never:**
- Treat a tool severity alone as a regulatory disposition
- Ignore warnings without documented justification
- Suppress valid P21 rules to achieve zero issues
- Skip validation after dataset modifications
- Produce output without validation
- Use hardcoded CT version -- always resolve from study config
- Use hardcoded domain list -- always resolve from study config

**Always:**
- Run P21 on all SDTM datasets before submission
- Document resolution for every error and warning
- Track issues in the path specified by regulatory-graph.yaml
- Re-validate after fixing issues
- Retain the report and resolution log in the controlled QC evidence package;
  summarize material issues in the appropriate reviewer guide when required

---

## Audited Validation and Provenance Rules (V7-RS-P21-2026-07)

### Constraints

- Never invent a finding identifier, severity, or remediation. Use the exact
  values returned by the pinned engine/rule catalog.
- A change from one engine or rule-catalog version to another requires a new run;
  findings from different versions are not silently merged.
- The validation workbook is retained QC evidence, not automatically a submitted
  dataset or eCTD document. The SDRG/ADRG records material conformance issues and
  explanations when applicable.
- If the engine is unavailable, record `validation_not_run` and fail the gate.
  Do not emulate a proprietary rule catalog with a handcrafted list.

### Output Schema

```yaml
validation_run:
  engine_product: string
  engine_version: string
  rule_catalog_version: string
  agency_profile: string
  standard_name: string
  standard_version: string
  ct_package_date: string
  external_dictionary_versions: {}
  input_sha256: {}
  findings:
    - finding_id: string
      severity: string
      message: string
      dataset: string
      variable: string
      record_keys: {}
      count: integer
      disposition: open|fixed|explained|not_applicable
      evidence: string
```

### Change Impact

Changing the engine, rule catalog, standard version, CT package, external
dictionary, dataset, or Define-XML hash invalidates the prior validation-run
manifest and requires revalidation plus downstream reviewer-guide impact review.
It does not by itself change raw data or authorize a dataset correction.
- Generate traceable, reproducible results
- Resolve study_id from study config, never hardcode
- Resolve path patterns from regulatory-graph.yaml node definitions

---

## Examples

### Basic Usage
```bash
python csp-skills/layer-3-sdtm-qc/p21-validator/script.py \
  --input output/sdtm/ \
  --output reports/p21-sdtm-report.xlsx \
  --study-config specs/study-config.yaml
```

### With Define.xml and CT
```bash
python csp-skills/layer-3-sdtm-qc/p21-validator/script.py \
  --input output/sdtm/ \
  --output reports/p21-sdtm-report.xlsx \
  --study-config specs/study-config.yaml \
  --define output/define/define-sdtm-draft.xml \
  --ct "{ct_version from study-config.yaml}"
```

### Expected Output
```
reports/p21-sdtm-report.xlsx
+-- Issues sheet (rule_id, dataset, variable, severity, message, USUBJID)
+-- Summary sheet (dataset, error_count, warning_count, info_count)
+-- ops/p21-sdtm-issues.yaml (tracking file with resolution status)
```
