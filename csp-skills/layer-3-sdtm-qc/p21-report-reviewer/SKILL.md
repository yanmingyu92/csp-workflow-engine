---
name: p21-report-reviewer
description: Review and categorize P21 validation issues. Triggers on "P21", "Pinnacle 21", "SDTM validation", "P21 validation", "compliance check", "validation report".
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
2. Read `specs/study-config.yaml` for study metadata (`study_id`, `sdtm_domains`, `ct_version`)
3. Resolve path patterns from `regulatory-graph.yaml` node `p21-sdtm-validation` definitions
4. If critical config missing, log error and abort

### Required Config Keys
| Key | Source | Fallback |
|-----|--------|----------|
| `study_id` | `specs/study-config.yaml` | Required - abort if missing |
| `sdtm_domains` | `specs/study-config.yaml` | Required - abort if missing |
| `ct_version` | `specs/study-config.yaml` | Required - abort if missing |
| `input_report` | `--input` argument | `reports/p21-sdtm-report.xlsx` |
| `output_resolved` | `--output` argument | `ops/p21-sdtm-resolved.yaml` |
| `issue_tracker` | `--issues` argument | `ops/p21-sdtm-issues.yaml` |

## EXECUTE NOW
Parse $ARGUMENTS: --input, --output, --spec, --validate, --dry-run
**START NOW.**

---

## Philosophy
**Systematic review of P21 issues ensures nothing is missed.** Each issue must be resolved, justified, or tracked to closure. The P21 report reviewer triages issues by severity, identifies patterns, recommends fixes, and produces an audit-ready resolution log.

**Key Principle:** Not all P21 warnings require fixes -- some are false positives or acceptable for the study design. However, every issue must have a documented disposition (fixed, justified, or deferred with rationale).

---

## Input/Output Specification

### Inputs (from `regulatory-graph.yaml` node `p21-sdtm-validation`)
| Input | Format | Path Pattern | Required |
|-------|--------|--------------|----------|
| P21 SDTM validation report | xlsx | `reports/p21-sdtm-report.xlsx` | Yes |
| P21 issue tracker | yaml | `ops/p21-sdtm-issues.yaml` | No |
| Study configuration | yaml | `specs/study-config.yaml` | Yes |
| All SDTM domain datasets | xpt | `output/sdtm/*.xpt` | No |

### Outputs
| Output | Format | Path Pattern | Description |
|--------|--------|--------------|-------------|
| P21 resolution report | yaml | `ops/p21-sdtm-resolved.yaml` | Issues with dispositions and notes |

---

## Script Execution

```bash
python csp-skills/layer-3-sdtm-qc/p21-report-reviewer/script.py \
  --input {p21_report_path} \
  --output {resolved_issues_path} \
  --study-config specs/study-config.yaml
```

### Arguments
| Argument | Required | Description |
|----------|----------|-------------|
| `--input` | Yes | P21 report XLSX file |
| `--output` | Yes | Output path for resolved issues YAML |
| `--study-config` | No | Study configuration YAML |
| `--issues` | No | Existing issue tracking YAML (to update) |
| `--auto-justify` | No | Auto-justify known false positives |
| `--dry-run` | No | Show review without writing |

---

## Issue Classification

### Severity Triage
| Severity | Action Required | Disposition Options |
|----------|----------------|-------------------|
| Error | MUST fix before submission | Fixed, Deferred (with sponsor approval) |
| Warning | MUST review and justify or fix | Fixed, Justified, Deferred |
| Info | SHOULD review | Reviewed, Ignored |

### Disposition Categories
| Disposition | Code | Description |
|-------------|------|-------------|
| Fixed | FIX | Root cause identified and corrected in dataset |
| Justified | JUS | Issue is acceptable per study design or CDISC guidance |
| Deferred | DEF | Issue acknowledged, to be resolved later (requires tracking) |
| False Positive | FP | P21 rule incorrectly triggered (document why) |
| Not Applicable | NA | Rule does not apply to this study |

---

## Review Process

### Step 1: Load Configuration
```python
def load_study_config(config_path):
    """
    Load study configuration for dynamic review parameters.
    """
    config = read_yaml(config_path)
    required_keys = ['study_id', 'sdtm_domains', 'ct_version']
    missing = [k for k in required_keys if k not in config]
    if missing:
        log_error(f"Missing critical study config keys: {missing}")
        abort()
    return config
```

### Step 2: Load and Parse Report
```python
def load_p21_report(report_path):
    """
    Parse P21 XLSX report into structured issues.

    USUBJID format: {study_id}-{SITEID}-{SUBJID} (resolved from study config)
    """
    issues = parse_xlsx(report_path, sheet='Issues')

    for issue in issues:
        issue.dataset = issue.row['Dataset']
        issue.variable = issue.row['Variable']
        issue.rule_id = issue.row['Rule ID']
        issue.severity = issue.row['Severity']
        issue.message = issue.row['Message']
        issue.usubjid = issue.row.get('USUBJID', '')
        issue.count = issue.row.get('Count', 1)

    return issues
```

### Step 3: Categorize by Pattern
```python
def categorize_issues(issues):
    """
    Group related issues to identify patterns.

    Categories:
    - Missing variables: required variables not populated
    - CT violations: controlled terminology not matching CDISC
    - Date format: ISO 8601 format issues
    - Cross-domain: inconsistencies between domains
    - Structural: key variable, ordering issues
    """
    categories = {
        'missing_vars': [],      # SD0001, SD0002
        'ct_violations': [],     # SD02xx
        'date_format': [],       # SD005x
        'cross_domain': [],      # SD03xx
        'structural': [],        # SD00xx, IG00xx
        'warnings_review': [],   # SD04xx
    }

    for issue in issues:
        if 'missing' in issue.message.lower():
            categories['missing_vars'].append(issue)
        elif 'controlled terminology' in issue.message.lower():
            categories['ct_violations'].append(issue)
        elif 'date' in issue.message.lower():
            categories['date_format'].append(issue)
        # ... additional categorization

    return categories
```

### Step 4: Generate Recommendations
```python
def generate_recommendations(issues, sdtm_dir, study_config):
    """
    For each issue, generate a fix recommendation.

    Uses domain knowledge to suggest specific fixes:
    - SD0007 (RFSTDTC missing) -> "Derive from first EX.EXSTDTC"
    - SD1002 (Invalid ARMCD) -> "Use 8-char max alphanumeric, check study_config.treatment_arms"
    - SD0020 (AGEU missing) -> "Set AGEU = 'YEARS'"
    - SD1003 (Invalid DSDECOD) -> "Use CDISC CT C66769 disposition terms"
    """
    recommendations = []
    for issue in issues:
        rec = lookup_fix_recommendation(issue.rule_id, issue.dataset)
        recommendations.append({
            'issue': issue,
            'recommendation': rec.fix_steps,
            'auto_fixable': rec.auto_fixable,
            'domain_affected': issue.dataset
        })

    return recommendations
```

---

## Common Issue Patterns and Fixes

### Missing Required Variables
```yaml
pattern: "Missing required variable"
common_causes:
  - Variable not mapped from raw data
  - Derivation logic missing
  - Source data column renamed
resolution_steps:
  - Check mapping spec for variable derivation
  - Verify raw data source
  - Apply mapping or derivation
  - Re-validate
```

### Controlled Terminology Mismatches
```yaml
pattern: "CT value not found in codelist"
common_causes:
  - Raw value not mapped to CDISC CT
  - Wrong CT version referenced (check study_config.ct_version)
  - Study-specific value not in standard CT
resolution_steps:
  - Verify CT mapping in mapping spec
  - Check CT version in Define.xml matches study config
  - Add study-specific mapping or SUPPQUAL
  - Re-validate
```

### Date Format Issues
```yaml
pattern: "Date does not conform to ISO 8601"
common_causes:
  - Raw date in non-ISO format
  - Partial date not properly handled
  - Missing date not left blank
resolution_steps:
  - Standardize date parsing in mapper
  - Use ISO 8601 format (YYYY-MM-DD)
  - Leave missing dates as empty string
  - Re-validate
```

### ARMCD Value Mismatches
```yaml
pattern: "ARMCD value not found in codelist"
common_causes:
  - ARMCD values do not match study_config.treatment_arms
  - Typo in arm code assignment
resolution_steps:
  - Compare dataset ARMCD values against study_config.treatment_arms
  - Correct mapping to use planned arm codes
  - Re-validate
```

---

## Output Schema

```yaml
p21_resolution_report:
  source_report: "{p21_report_path from regulatory-graph.yaml}"
  study_id: "{study_id from study config}"
  review_date: "{timestamp}"
  reviewer: "{reviewer_id}"

  summary:
    total_issues: 0
    errors: 0
    warnings: 0
    info: 0
    fixed: 0
    justified: 0
    deferred: 0

  issues:
    - rule_id: "SD0007"
      dataset: "DM"
      variable: "RFSTDTC"
      severity: "Error"
      message: "RFSTDTC is missing for X subjects"
      disposition: "fixed"
      resolution_notes: "Derived RFSTDTC from first EX.EXSTDTC record per subject"
      affected_usubjids: ["{study_id}-{SITEID}-{SUBJID}", ...]
      count: 5
      verified: true

    - rule_id: "SD0043"
      dataset: "DM"
      variable: "CUSTOMVAR"
      severity: "Warning"
      message: "Variable is not expected in domain"
      disposition: "justified"
      resolution_notes: "Study-specific variable required by SAP, documented in Define.xml"
      affected_usubjids: []
      count: 254
      verified: true
```

---

## Edge Cases

### Mass Warnings (Same Rule, Many Records)
```python
# Same rule fires for hundreds of records:
# - Don't review individually
# - Identify root cause (e.g., CT mapping missing for entire variable)
# - Fix once, re-validate to clear all
# - Document batch resolution
```

### Conflicting Rules
```python
# Two P21 rules conflict:
# - E.g., SD0043 "Variable not expected" vs requirement to include
# - Document study-specific justification
# - Reference CDISC clarification or waiver if applicable
```

### Issues Introduced by Fixes
```python
# Fixing one issue creates another:
# - Re-validate after each batch of fixes
# - Track regression issues separately
# - May need to adjust mapping logic rather than patching data
```

### Missing Input Report
```python
# If the P21 report file is not found at the expected path:
# - Check regulatory-graph.yaml path_pattern for correct location
# - Verify p21-validator completed successfully in workflow state
# - Abort review rather than work with stale data
```

### Study Config Mismatch
```python
# If study config domains don't match the report's datasets:
# - Flag the discrepancy
# - Some domains may have been added/removed since validation
# - Validate that all sdtm_domains from config are represented
```

---

## Integration Points

### Upstream Skills
- `/p21-validator` -- Generates the P21 report being reviewed
- `/sdtm-validator` -- Pre-P21 structural validation
- `/study-setup` -- Provides study config with treatment arms and domain list

### Downstream Skills
- `/sdrg-writer` -- Document P21 resolution in SDRG
- `/define-draft-builder` -- Update Define.xml metadata if needed
- `/sdtm-consistency-checker` -- Cross-domain checks for CT issues

### Related Skills
- `/sdtm-dm-mapper` -- Fix DM-specific issues
- `/sdtm-ae-mapper` -- Fix AE-specific issues
- `/data-quality` -- Root cause analysis

---

## Evaluation Criteria

**Mandatory:**
- All errors have disposition = "fixed"
- All warnings reviewed and dispositioned (fixed, justified, or deferred)
- Resolution notes document the "why" for each disposition
- Verified flag set after re-validation
- Study config loaded with all required keys

**Recommended:**
- Pattern analysis identifying root causes
- Batch fix recommendations for mass issues
- Zero deferred items (all resolved)
- Summary statistics in resolution report

---

## Critical Constraints

**Never:**
- Mark an error as "justified" (errors MUST be fixed)
- Close an issue without verifying the fix
- Ignore warnings without documented rationale
- Bulk-dismiss issues without individual review
- Submit resolution report without re-validation
- Use hardcoded study_id or domain references

**Always:**
- Review every issue individually (batch patterns may mask unique cases)
- Document specific justification text for each disposition
- Re-validate after fixes to confirm resolution
- Track deferred items with expected resolution date
- Generate traceable, reproducible results
- Resolve study_id from study config for USUBJID references
- Resolve path patterns from regulatory-graph.yaml

---

## Examples

### Basic Usage
```bash
python csp-skills/layer-3-sdtm-qc/p21-report-reviewer/script.py \
  --input reports/p21-sdtm-report.xlsx \
  --output ops/p21-sdtm-resolved.yaml \
  --study-config specs/study-config.yaml
```

### With Existing Issue Tracking
```bash
python csp-skills/layer-3-sdtm-qc/p21-report-reviewer/script.py \
  --input reports/p21-sdtm-report.xlsx \
  --output ops/p21-sdtm-resolved.yaml \
  --issues ops/p21-sdtm-issues.yaml \
  --study-config specs/study-config.yaml \
  --auto-justify
```

### Expected Output
```
ops/p21-sdtm-resolved.yaml
+-- Summary (total, fixed, justified, deferred counts)
+-- Issues list with dispositions and notes
+-- Verification status per issue
```
