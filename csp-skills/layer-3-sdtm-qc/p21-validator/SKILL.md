---
name: p21-validator
description: Run Pinnacle 21 validation on datasets. Triggers on "P21", "Pinnacle 21", "SDTM validation", "P21 validation", "compliance check", "validation report".
version: "1.0"
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
**P21 validation is the industry standard compliance gate.** Zero errors is mandatory for submission; warnings must be reviewed and justified. P21 checks SDTM datasets against CDISC implementation guide rules, FDA/EMA conformance rules, and controlled terminology consistency.

**Key Principle:** Every P21 issue must be triaged -- errors are resolved, warnings are justified or fixed, and informational items are reviewed. The validation report becomes part of the regulatory submission package.

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

### SDTM Conformance Rules (FDA)
| Category | Description | Severity |
|----------|-------------|----------|
| SD00xx | Structural checks (variables, keys, order) | Error |
| SD01xx | Data type and format checks | Error |
| SD02xx | Value-level checks (CT, ranges) | Error/Warning |
| SD03xx | Cross-domain consistency | Error |
| SD04xx | Business rule checks | Warning |
| SD05xx | Dataset-level checks | Info |

### Implementation Guide Rules (SDTM IG v3.4)
| Category | Description | Severity |
|----------|-------------|----------|
| IG00xx | Required variable presence | Error |
| IG01xx | Variable labeling | Warning |
| IG02xx | Domain structure compliance | Error |
| IG03xx | Controlled terminology | Error/Warning |

### Common P21 Errors by Domain

#### DM Domain
| Rule ID | Message | Fix |
|---------|---------|-----|
| SD0001 | Missing required variable | Add STUDYID, DOMAIN, USUBJID |
| SD0007 | RFSTDTC is missing | Derive from first EX record |
| SD1002 | Invalid ARMCD format | Use 8-char max, alphanumeric only |
| SD0020 | AGEU missing | Always populate as "YEARS" |
| SD0051 | Date format invalid | Use ISO 8601 (YYYY-MM-DD) |

#### AE Domain
| Rule ID | Message | Fix |
|---------|---------|-----|
| SD0001 | AETERM is missing | Populate verbatim term |
| SD0002 | AEDECOD is missing | Complete MedDRA coding |
| SD0003 | AEBODSYS is missing | Derive from MedDRA hierarchy |
| SD1001 | AESER inconsistent | AESER='Y' iff any criterion='Y' |
| SD0051 | AESTDTC format invalid | Use ISO 8601 format |

#### EX Domain
| Rule ID | Message | Fix |
|---------|---------|-----|
| SD0001 | EXTRT is missing | Populate treatment name from study config |
| SD0002 | EXDOSE is missing | Populate dose amount |
| SD0051 | EXSTDTC format invalid | Use ISO 8601 format |
| SD0053 | EXENDTC before EXSTDTC | Validate date logic |

#### DS Domain
| Rule ID | Message | Fix |
|---------|---------|-----|
| SD0001 | DSTERM is missing | Populate disposition term |
| SD0002 | DSDECOD is missing | Map to standard disposition term |
| SD1003 | Invalid DSDECOD value | Use CDISC CT C66769 |

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
    2. Apply SDTM IG v3.4 rules
    3. Apply FDA conformance rules
    4. Check controlled terminology consistency using study_config.ct_version
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
- Zero P21 errors (severity = Error)
- All warnings reviewed and justified or resolved
- Validation report generated in XLSX format
- Issue tracking file created at path from regulatory-graph.yaml
- Study config loaded with all required keys
- CT version from study config used for validation

**Recommended:**
- Zero P21 warnings
- All informational items reviewed
- CT version documented in report metadata
- Define.xml referenced for metadata rules

---

## Critical Constraints

**Never:**
- Submit datasets with unresolved P21 errors
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
- Include P21 report in submission package
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
