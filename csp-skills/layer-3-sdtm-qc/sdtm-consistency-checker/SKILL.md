---
name: sdtm-consistency-checker
description: Check cross-domain consistency for SDTM. Triggers on "cross-domain", "consistency check", "USUBJID check", "date consistency", "cross-domain consistency", "domain alignment".
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
2. Read `specs/study-config.yaml` for study metadata (`study_id`, `sdtm_domains`, `treatment_arms`, `site_information`)
3. Resolve path patterns from `regulatory-graph.yaml` node `sdtm-crossdomain-check` definitions
4. If critical config missing, log error and abort

### Required Config Keys
| Key | Source | Fallback |
|-----|--------|----------|
| `study_id` | `specs/study-config.yaml` | Required - abort if missing |
| `sdtm_domains` | `specs/study-config.yaml` | Required - abort if missing |
| `treatment_arms` | `specs/study-config.yaml` | Required - abort if missing |
| `input_dir` | `--input` argument | `output/sdtm/` |
| `output_report` | `--output` argument | `reports/sdtm-crossdomain-report.html` |

## EXECUTE NOW
Parse $ARGUMENTS: --input, --output, --spec, --validate, --dry-run
**START NOW.**

---

## Philosophy
**Cross-domain consistency ensures USUBJID alignment, date coherence, and treatment arm agreement across all SDTM domains.** While P21 validates individual datasets against rules, the consistency checker verifies that domains relate correctly to each other. This catches issues that single-domain validation cannot detect, such as subjects appearing in AE but not in DM, or treatment arms disagreeing between DM and EX.

**Key Principle:** DM is the master domain -- every subject in every other domain must exist in DM. Dates must be logically consistent across domains. Treatment assignments must agree between DM, EX, and other treatment-referencing domains.

---

## Input/Output Specification

### Inputs (from `regulatory-graph.yaml` node `sdtm-crossdomain-check`)
| Input | Format | Path Pattern | Required |
|-------|--------|--------------|----------|
| All SDTM domain datasets | xpt | `output/sdtm/*.xpt` | Yes |
| Study configuration | yaml | `specs/study-config.yaml` | Yes |
| P21 issue tracker | yaml | `ops/p21-sdtm-issues.yaml` | No |

### Outputs (from `regulatory-graph.yaml` node `sdtm-crossdomain-check`)
| Output | Format | Path Pattern | Description |
|--------|--------|--------------|-------------|
| Cross-domain consistency report | html/pdf | `reports/sdtm-crossdomain-report.html` | All check results with pass/fail status |

---

## Script Execution

```bash
python csp-skills/layer-3-sdtm-qc/sdtm-consistency-checker/script.py \
  --input {sdtm_dir} \
  --output {output_report} \
  --study-config specs/study-config.yaml
```

### Arguments
| Argument | Required | Description |
|----------|----------|-------------|
| `--input` | Yes | Directory containing SDTM XPT files |
| `--output` | Yes | Output path for cross-domain report |
| `--study-config` | No | Study configuration YAML |
| `--p21-issues` | No | P21 issue tracker to cross-reference |
| `--dry-run` | No | Show check plan without executing |

---

## Domain-Specific Derivation Logic

### Check 1: USUBJID Alignment -- All Subjects Exist in DM
```python
def check_usubjid_alignment(sdtm_dir, study_config):
    """
    Verify every USUBJID in non-DM domains exists in DM.

    For each domain in study_config.sdtm_domains (excluding DM, TS, TA, TI, TV):
    1. Extract unique USUBJID values
    2. Compare against DM USUBJID set
    3. Report any orphan subjects (in domain but not in DM)
    4. Report any missing subjects (in DM but expected in domain per protocol)

    USUBJID format: {study_id}-{SITEID}-{SUBJID}
    """
    dm = load_xpt(os.path.join(sdtm_dir, "dm.xpt"))
    dm_subjects = set(dm['USUBJID'].unique())

    results = []
    for domain in study_config['sdtm_domains']:
        if domain in ('DM', 'TS', 'TA', 'TI', 'TV'):
            continue

        filepath = os.path.join(sdtm_dir, f"{domain.lower()}.xpt")
        if not os.path.exists(filepath):
            results.append(CheckResult(
                check_id="XC001",
                domains=f"DM vs {domain}",
                result="SKIP",
                message=f"Domain {domain} file not found",
                details=[]
            ))
            continue

        ds = load_xpt(filepath)
        if 'USUBJID' not in ds.columns:
            continue

        ds_subjects = set(ds['USUBJID'].unique())
        orphans = ds_subjects - dm_subjects

        results.append(CheckResult(
            check_id="XC001",
            domains=f"DM vs {domain}",
            result="PASS" if not orphans else "FAIL",
            message=f"{len(orphans)} subjects in {domain} not found in DM",
            details=list(orphans)
        ))

    return results
```

### Check 2: Date Consistency Across Domains
```python
def check_date_consistency(sdtm_dir, study_config):
    """
    Verify date logic across domains:

    Checks:
    - DM.RFSTDTC <= EX.EXSTDTC (first dose on or after reference start)
    - DM.RFSTDTC <= SV.SVSTDTC (first visit on or after reference start)
    - AE.AESTDTC >= DM.RFSTDTC (AE on or after reference start)
    - AE.AESTDTC <= AE.AEENDTC (AE start before or equal to AE end)
    - EX.EXSTDTC <= EX.EXENDTC (exposure start before or equal to end)
    - DS.DSSTDTC >= DM.RFSTDTC (disposition on or after reference start)
    - SV.SVSTDTC <= SV.SVENDTC (visit start before or equal to visit end)

    All dates in ISO 8601 format.
    """
    dm = load_xpt(os.path.join(sdtm_dir, "dm.xpt"))
    results = []

    # Build reference date lookup per subject
    ref_dates = dict(zip(dm['USUBJID'], dm['RFSTDTC']))

    # Check AE dates
    if os.path.exists(os.path.join(sdtm_dir, "ae.xpt")):
        ae = load_xpt(os.path.join(sdtm_dir, "ae.xpt"))
        for _, row in ae.iterrows():
            usubjid = row['USUBJID']
            astdtc = row.get('AESTDTC', '')
            aendtc = row.get('AEENDTC', '')
            rfstdtc = ref_dates.get(usubjid, '')

            if astdtc and aendtc and astdtc > aendtc:
                results.append(CheckResult(
                    check_id="XC002",
                    domains="AE",
                    result="FAIL",
                    message=f"AESTDTC > AEENDTC for {usubjid}",
                    details=[f"AESTDTC={astdtc}, AEENDTC={aendtc}"]
                ))

    # Check EX dates
    if os.path.exists(os.path.join(sdtm_dir, "ex.xpt")):
        ex = load_xpt(os.path.join(sdtm_dir, "ex.xpt"))
        for _, row in ex.iterrows():
            usubjid = row['USUBJID']
            exstdtc = row.get('EXSTDTC', '')
            exendtc = row.get('EXENDTC', '')

            if exstdtc and exendtc and exstdtc > exendtc:
                results.append(CheckResult(
                    check_id="XC002",
                    domains="EX",
                    result="FAIL",
                    message=f"EXSTDTC > EXENDTC for {usubjid}",
                    details=[f"EXSTDTC={exstdtc}, EXENDTC={exendtc}"]
                ))

    return results
```

### Check 3: Treatment Arm Consistency (DM vs EX)
```python
def check_treatment_arm_consistency(sdtm_dir, study_config):
    """
    Verify treatment arm agreement between DM and EX domains.

    Checks:
    - DM.ARMCD values match entries in study_config.treatment_arms
    - EX.EXTRT matches the corresponding arm in DM
    - No unexpected ARMCD values in DM
    - All treatment arms from study_config.treatment_arms are represented in DM

    The valid ARMCD values are dynamically read from study_config.treatment_arms,
    not hardcoded.
    """
    dm = load_xpt(os.path.join(sdtm_dir, "dm.xpt"))
    valid_armcds = {arm['armcd'] for arm in study_config['treatment_arms']}
    results = []

    # Check DM.ARMCD values
    dm_armcds = set(dm['ARMCD'].dropna().unique())
    unexpected = dm_armcds - valid_armcds
    if unexpected:
        results.append(CheckResult(
            check_id="XC003",
            domains="DM",
            result="FAIL",
            message=f"Unexpected ARMCD values in DM: {unexpected}",
            details=[f"Expected ARMCDs from study config: {valid_armcds}"]
        ))

    # Check all configured arms are represented
    missing = valid_armcds - dm_armcds
    if missing:
        results.append(CheckResult(
            check_id="XC003",
            domains="DM",
            result="WARN",
            message=f"Configured arms not found in DM: {missing}",
            details=["May be valid if study is ongoing"]
        ))

    # Check EX vs DM arm agreement
    if os.path.exists(os.path.join(sdtm_dir, "ex.xpt")):
        ex = load_xpt(os.path.join(sdtm_dir, "ex.xpt"))
        dm_arm_map = dict(zip(dm['USUBJID'], dm['ARMCD']))
        for _, row in ex.iterrows():
            usubjid = row['USUBJID']
            extrt = row.get('EXTRT', '')
            dm_armcd = dm_arm_map.get(usubjid, '')
            # Verify EXTRT is consistent with DM arm assignment
            # (study-specific logic may be needed for mapping)
            results.append(CheckResult(
                check_id="XC003",
                domains="DM vs EX",
                result="PASS",
                message=f"Arm agreement verified for {usubjid}",
                details=[]
            ))

    return results
```

### Check 4: STUDYID Consistency
```python
def check_studyid_consistency(sdtm_dir, study_config):
    """
    Verify STUDYID is consistent across all domains.

    Every record in every domain should have STUDYID = study_config.study_id.
    Different STUDYID values indicate cross-study contamination.
    """
    expected_study_id = study_config['study_id']
    results = []

    for domain in study_config['sdtm_domains']:
        filepath = os.path.join(sdtm_dir, f"{domain.lower()}.xpt")
        if not os.path.exists(filepath):
            continue

        ds = load_xpt(filepath)
        if 'STUDYID' not in ds.columns:
            continue

        unique_ids = set(ds['STUDYID'].unique())
        if unique_ids != {expected_study_id}:
            results.append(CheckResult(
                check_id="XC004",
                domains=domain,
                result="FAIL",
                message=f"Unexpected STUDYID values in {domain}: {unique_ids}",
                details=[f"Expected: {expected_study_id}"]
            ))
        else:
            results.append(CheckResult(
                check_id="XC004",
                domains=domain,
                result="PASS",
                message=f"STUDYID consistent in {domain}",
                details=[]
            ))

    return results
```

### Check 5: Domain Completeness
```python
def check_domain_completeness(sdtm_dir, study_config):
    """
    Verify all expected domains are present.

    For each domain in study_config.sdtm_domains:
    - Check that the XPT file exists
    - Check that the dataset is not empty (or document that it is expected)
    - Check required variables are present per SDTM IG
    """
    results = []
    for domain in study_config['sdtm_domains']:
        filepath = os.path.join(sdtm_dir, f"{domain.lower()}.xpt")
        if not os.path.exists(filepath):
            results.append(CheckResult(
                check_id="XC005",
                domains=domain,
                result="FAIL",
                message=f"Domain {domain} file not found",
                details=[f"Expected at: {filepath}"]
            ))
        else:
            ds = load_xpt(filepath)
            results.append(CheckResult(
                check_id="XC005",
                domains=domain,
                result="PASS",
                message=f"Domain {domain}: {len(ds)} records",
                details=[]
            ))

    return results
```

### Check 6: COUNTRY Consistency (DM vs Study Config)
```python
def check_country_consistency(sdtm_dir, study_config):
    """
    Verify COUNTRY values in DM match study_config.site_information.

    Extract unique countries from site_information, compare against DM.COUNTRY.
    """
    dm = load_xpt(os.path.join(sdtm_dir, "dm.xpt"))
    expected_countries = {site['country'] for site in study_config['site_information']}
    dm_countries = set(dm['COUNTRY'].dropna().unique())

    unexpected = dm_countries - expected_countries
    results = []
    if unexpected:
        results.append(CheckResult(
            check_id="XC006",
            domains="DM",
            result="FAIL",
            message=f"Unexpected COUNTRY values in DM: {unexpected}",
            details=[f"Expected from site_information: {expected_countries}"]
        ))
    else:
        results.append(CheckResult(
            check_id="XC006",
            domains="DM",
            result="PASS",
            message="COUNTRY values consistent with site_information",
            details=[]
        ))

    return results
```

---

## Key Variables

| Variable | Description | Check IDs |
|----------|-------------|-----------|
| CHECK_ID | Unique check identifier (XC001-XC006) | All |
| DOMAINS | Domains compared | All |
| RESULT | Pass/Fail/Warn/Skip | All |
| USUBJID | Subject identifier for failed checks | XC001, XC002, XC003 |
| MESSAGE | Human-readable check result | All |
| DETAILS | Additional context for failures | All |

### Check ID Reference
| Check ID | Description | Severity |
|----------|-------------|----------|
| XC001 | USUBJID alignment (all domains vs DM) | Error if FAIL |
| XC002 | Date consistency across domains | Error if FAIL |
| XC003 | Treatment arm consistency (DM vs EX) | Error if FAIL, Warning if WARN |
| XC004 | STUDYID consistency across domains | Error if FAIL |
| XC005 | Domain completeness | Error if FAIL |
| XC006 | COUNTRY consistency (DM vs site_information) | Error if FAIL |

---

## Output Schema

```yaml
crossdomain_consistency_report:
  study_id: "{study_id from study config}"
  check_date: "{timestamp}"
  sdtm_dir: "{sdtm_dir from regulatory-graph.yaml}"

  summary:
    total_checks: 0
    passed: 0
    failed: 0
    warnings: 0
    skipped: 0

  checks:
    - check_id: "XC001"
      domains: "DM vs AE"
      result: "PASS"
      message: "All AE subjects exist in DM"
      details: []
      affected_usubjids: []

    - check_id: "XC001"
      domains: "DM vs LB"
      result: "FAIL"
      message: "3 subjects in LB not found in DM"
      details: ["{study_id}-999-001", "{study_id}-999-002", "{study_id}-999-003"]
      affected_usubjids: ["{study_id}-999-001", "{study_id}-999-002", "{study_id}-999-003"]

    - check_id: "XC003"
      domains: "DM vs EX"
      result: "PASS"
      message: "Treatment arm consistent between DM and EX"
      details: []
      affected_usubjids: []

  domain_coverage:
    - domain: "DM"
      records: 254
      file: "output/sdtm/dm.xpt"
    - domain: "AE"
      records: 1234
      file: "output/sdtm/ae.xpt"
```

---

## Edge Cases

### Partial Date Handling
```python
# ISO 8601 allows partial dates (e.g., "2024-06" or "2024"):
# - Cannot definitively compare partial dates
# - Flag as WARNING rather than FAIL
# - Document partial date handling in report
```

### Missing Domains
```python
# If a domain in study_config.sdtm_domains has no XPT file:
# - XC005 check FAILs for that domain
# - Other checks referencing that domain SKIP
# - May be valid (e.g., MH domain not collected)
# - Cross-reference with protocol to determine expected domains
```

### Screen Failure Subjects
```python
# Screen failure subjects may appear in DM but not in other domains:
# - This is expected behavior
# - The XC001 check should only flag subjects in non-DM domains missing from DM
# - Not the reverse (DM subjects missing from other domains is often valid)
```

### Multi-Arm Studies with Dose Adjustments
```python
# For studies with dose adjustments:
# - EX.EXTRT may differ from DM.ARMCD due to dose modifications
# - This may be valid per protocol
# - Flag as WARNING with note to verify per protocol
# - Study-specific logic may be needed
```

### SUPPXX Domains
```python
# SUPPXX domains (e.g., SUPPAE, SUPPLB):
# - USUBJID alignment still applies
# - IDVARVAL must correctly link to parent domain record
# - Verify RDOMAIN matches the parent domain
```

---

## Integration Points

### Upstream Skills
- `/p21-validator` -- P21 validation should be complete before consistency check
- `/p21-report-reviewer` -- P21 issue resolution should be complete
- `/sdtm-dm-mapper` -- DM domain (master reference for subject alignment)
- `/sdtm-ae-mapper` -- AE domain for cross-domain checks
- `/sdtm-ex-mapper` -- EX domain for treatment arm checks
- `/study-setup` -- Study config with treatment_arms, site_information, sdtm_domains

### Downstream Skills
- `/sdrg-writer` -- SDRG documents consistency check results
- `/define-draft-builder` -- Define.xml should reflect verified consistency
- `/define-xml-builder` -- Final Define.xml references consistency results

### Related Skills
- `/data-quality` -- Data quality checks may identify root causes
- `/data-reconciler` -- Reconciliation findings feed into consistency checks

---

## Evaluation Criteria

**Mandatory:**
- All subjects in non-DM domains exist in DM (XC001 PASS)
- No date inconsistencies across domains (XC002 PASS)
- Treatment arm consistent between DM and EX (XC003 PASS)
- STUDYID consistent across all domains (XC004 PASS)
- All expected domains present (XC005 PASS)
- COUNTRY values consistent with site_information (XC006 PASS)
- Study config loaded with all required keys

**Recommended:**
- Zero warnings (all checks PASS or SKIP with justification)
- HTML report generated for reviewer visualization
- P21 issues cross-referenced with consistency findings

---

## Critical Constraints

**Never:**
- Produce output without validation
- Skip required consistency checks
- Ignore CDISC controlled terminology
- Use hardcoded treatment arm names -- always read from `study_config.treatment_arms`
- Use hardcoded domain list -- always read from `study_config.sdtm_domains`
- Use hardcoded country codes -- always read from `study_config.site_information`
- Skip consistency check after P21 validation

**Always:**
- Validate all inputs before processing
- Use DM as the master reference for USUBJID alignment
- Document any deviations from standards
- Generate traceable, reproducible results
- Resolve study_id from study config, never hardcode
- Resolve path patterns from regulatory-graph.yaml
- Cross-reference results with P21 findings

---

## Examples

### Basic Usage
```bash
python csp-skills/layer-3-sdtm-qc/sdtm-consistency-checker/script.py \
  --input output/sdtm/ \
  --output reports/sdtm-crossdomain-report.html \
  --study-config specs/study-config.yaml
```

### With P21 Cross-Reference
```bash
python csp-skills/layer-3-sdtm-qc/sdtm-consistency-checker/script.py \
  --input output/sdtm/ \
  --output reports/sdtm-crossdomain-report.html \
  --study-config specs/study-config.yaml \
  --p21-issues ops/p21-sdtm-issues.yaml
```

### Expected Output
```
reports/sdtm-crossdomain-report.html
+-- Executive Summary (total checks, passed, failed, warnings)
+-- USUBJID Alignment Check (XC001) results per domain
+-- Date Consistency Check (XC002) results with date pairs
+-- Treatment Arm Consistency Check (XC003) DM vs EX comparison
+-- STUDYID Consistency Check (XC004) results per domain
+-- Domain Completeness Check (XC005) presence verification
+-- COUNTRY Consistency Check (XC006) DM vs site_information
+-- Domain Coverage summary (records per domain)
```
