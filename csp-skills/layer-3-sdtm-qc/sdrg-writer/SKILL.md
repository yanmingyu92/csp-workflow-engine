---
name: sdrg-writer
description: Write SDTM Reviewers Guide (SDRG). Triggers on "SDRG", "reviewer guide", "SDTM reviewer", "reviewer's guide", "PhUSE", "study data reviewer".
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
2. Read `specs/study-config.yaml` for study metadata (`study_id`, `study_title`, `protocol_name`, `sdtm_domains`, `treatment_arms`, `site_information`, `ct_version`)
3. Resolve path patterns from `regulatory-graph.yaml` node `sdtm-reviewer-guide` definitions
4. If critical config missing, log error and abort

### Required Config Keys
| Key | Source | Fallback |
|-----|--------|----------|
| `study_id` | `specs/study-config.yaml` | Required - abort if missing |
| `study_title` | `specs/study-config.yaml` | Required - abort if missing |
| `protocol_name` | `specs/study-config.yaml` | Required - abort if missing |
| `sdtm_domains` | `specs/study-config.yaml` | Required - abort if missing |
| `treatment_arms` | `specs/study-config.yaml` | Required - abort if missing |
| `ct_version` | `specs/study-config.yaml` | Required - abort if missing |
| `output_path` | `--output` argument | `docs/sdrg.pdf` |
| `sdtm_dir` | `--input` argument | `output/sdtm/` |

## EXECUTE NOW
Parse $ARGUMENTS: --input, --output, --spec, --validate, --dry-run
**START NOW.**

---

## Philosophy
**The SDRG helps FDA reviewers understand data.** It must explain non-standard variables, data issues, and study-specific decisions. The SDRG is the narrative companion to the SDTM datasets and Define.xml -- it provides the context that machine-readable metadata alone cannot convey. Following the PhUSE SDRG template ensures consistency and completeness.

**Key Principle:** Every deviation from CDISC standards, every non-standard variable, every P21 issue, and every study-specific decision must be documented in the SDRG so that FDA reviewers can properly interpret the submitted data.

---

## Input/Output Specification

### Inputs (from `regulatory-graph.yaml` node `sdtm-reviewer-guide`)
| Input | Format | Path Pattern | Required |
|-------|--------|--------------|----------|
| All SDTM domain datasets | xpt | `output/sdtm/*.xpt` | Yes |
| P21 SDTM validation report | xlsx | `reports/p21-sdtm-report.xlsx` | Yes |
| Study configuration | yaml | `specs/study-config.yaml` | Yes |
| P21 resolution report | yaml | `ops/p21-sdtm-resolved.yaml` | No |
| Cross-domain consistency report | html | `reports/sdtm-crossdomain-report.html` | No |
| Define.xml draft | xml | `output/define/define-sdtm-draft.xml` | No |
| SDTM mapping specification | xlsx/yaml | `specs/sdtm-mapping-spec.xlsx` | No |

### Outputs (from `regulatory-graph.yaml` node `sdtm-reviewer-guide`)
| Output | Format | Path Pattern | Description |
|--------|--------|--------------|-------------|
| SDTM Reviewer's Guide (SDRG) | pdf | `docs/sdrg.pdf` | Complete reviewer's guide document |

---

## Script Execution

```bash
python csp-skills/layer-3-sdtm-qc/sdrg-writer/script.py \
  --input {sdtm_dir} \
  --output {output_path} \
  --study-config specs/study-config.yaml \
  --p21-report reports/p21-sdtm-report.xlsx
```

### Arguments
| Argument | Required | Description |
|----------|----------|-------------|
| `--input` | Yes | Directory containing SDTM XPT files |
| `--output` | Yes | Output path for SDRG (PDF) |
| `--study-config` | No | Study configuration YAML |
| `--p21-report` | No | P21 validation report XLSX |
| `--p21-resolved` | No | P21 resolution report YAML |
| `--consistency-report` | No | Cross-domain consistency report HTML |
| `--define-xml` | No | Define.xml draft for method references |
| `--mapping-spec` | No | SDTM mapping specification |
| `--dry-run` | No | Show SDRG outline without writing |

---

## SDRG Section Structure (PhUSE Template)

### Section 1: Introduction
```python
def write_introduction(study_config, sdtm_dir):
    """
    Generate the SDRG introduction section.

    Contents:
    - Study identifier: {study_id from study config}
    - Study title: {study_title from study config}
    - Protocol name: {protocol_name from study config}
    - Purpose of the SDRG
    - Overview of submitted datasets
    - SDTM implementation guide version (3.4)
    - Controlled terminology version: {ct_version from study config}
    - List of submitted domains: {sdtm_domains from study config}
    """
    intro = Section("Introduction")
    intro.add_paragraph(
        f"This Reviewer's Guide accompanies the SDTM submission datasets for "
        f"study {study_config['study_id']}: {study_config['study_title']}."
    )
    intro.add_paragraph(
        f"The datasets were created following CDISC SDTM Implementation Guide v3.4 "
        f"using Controlled Terminology version {study_config['ct_version']}."
    )

    # List submitted domains
    domains = study_config['sdtm_domains']
    intro.add_table(
        title="Submitted SDTM Datasets",
        headers=["Domain", "Description", "Records"],
        rows=[(d, get_domain_description(d), count_records(sdtm_dir, d)) for d in domains]
    )

    return intro
```

### Section 2: Study Design
```python
def write_study_design(study_config, sdtm_dir):
    """
    Document the study design and treatment arms.

    Contents:
    - Study design description (from protocol)
    - Treatment arms: dynamically read from study_config.treatment_arms
    - Site information: countries from study_config.site_information
    - Randomization scheme
    - Blinding information
    """
    design = Section("Study Design")

    # Treatment arms table - DYNAMIC from study config
    arms_table = []
    for arm in study_config['treatment_arms']:
        arms_table.append((arm['armcd'], arm['arm']))
    design.add_table(
        title="Treatment Arms",
        headers=["Planned Arm Code (ARMCD)", "Planned Arm (ARM)"],
        rows=arms_table
    )

    # Countries table - DYNAMIC from study config
    countries = sorted({site['country'] for site in study_config['site_information']})
    design.add_paragraph(
        f"The study includes sites in the following countries: {', '.join(countries)}"
    )

    # Trial design datasets
    if os.path.exists(os.path.join(sdtm_dir, "ts.xpt")):
        ts = load_xpt(os.path.join(sdtm_dir, "ts.xpt"))
        design.add_paragraph(
            "Trial design parameters are documented in the TS (Trial Summary) dataset."
        )

    return design
```

### Section 3: Data Standards
```python
def write_data_standards(study_config, sdtm_dir, define_xml_path):
    """
    Document data standards used.

    Contents:
    - SDTM IG version (3.4)
    - Controlled terminology: {ct_version from study config}
    - Define.xml version (2.1)
    - CDISC CT package: {ct_package_url from study config}
    - Any deviations from CDISC standards
    """
    standards = Section("Data Standards")
    standards.add_paragraph(
        f"SDTM Implementation Guide: v3.4\n"
        f"Controlled Terminology: {study_config['ct_version']}\n"
        f"Define-XML: v2.1"
    )
    return standards
```

### Section 4: Dataset Descriptions
```python
def write_dataset_descriptions(sdtm_dir, study_config):
    """
    For each domain in study_config.sdtm_domains, describe:
    - Domain purpose and structure
    - Key variables
    - Number of records and subjects
    - Any non-standard variables
    - Derivation methods
    """
    descriptions = Section("Dataset Descriptions")

    for domain in study_config['sdtm_domains']:
        filepath = os.path.join(sdtm_dir, f"{domain.lower()}.xpt")
        if not os.path.exists(filepath):
            descriptions.add_paragraph(f"Domain {domain}: Not submitted (no data collected)")
            continue

        ds = load_xpt(filepath)
        domain_desc = DomainDescription(
            domain=domain,
            description=get_domain_description(domain),
            records=len(ds),
            subjects=ds['USUBJID'].nunique() if 'USUBJID' in ds.columns else 0,
            variables=list(ds.columns),
            key_variables=get_key_variables(domain)
        )
        descriptions.add_subsection(domain_desc)

    return descriptions
```

### Section 5: P21 Validation Summary
```python
def write_p21_summary(p21_report_path, p21_resolved_path, study_config):
    """
    Document P21 validation results and resolutions.

    Contents:
    - P21 engine version used
    - CT version: {ct_version from study config}
    - Summary: errors, warnings, info counts
    - For each error: rule, description, resolution
    - For each warning: rule, description, justification
    - For justified warnings: detailed rationale

    All USUBJID references use format: {study_id}-{SITEID}-{SUBJID}
    """
    p21 = Section("Pinnacle 21 Validation Summary")

    if p21_report_path and os.path.exists(p21_report_path):
        report = parse_p21_report(p21_report_path)
        p21.add_paragraph(
            f"P21 validation was performed using Controlled Terminology version "
            f"{study_config['ct_version']}.\n"
            f"Results: {report.error_count} errors, {report.warning_count} warnings, "
            f"{report.info_count} informational items."
        )

        # Document each error resolution
        if p21_resolved_path and os.path.exists(p21_resolved_path):
            resolved = read_yaml(p21_resolved_path)
            for issue in resolved.get('issues', []):
                if issue['severity'] == 'Error':
                    p21.add_paragraph(
                        f"Rule {issue['rule_id']} ({issue['severity']}): {issue['message']}\n"
                        f"Resolution: {issue['resolution_notes']}"
                    )
                elif issue['disposition'] == 'justified':
                    p21.add_paragraph(
                        f"Rule {issue['rule_id']} (Warning - Justified): {issue['message']}\n"
                        f"Justification: {issue['resolution_notes']}"
                    )
    else:
        p21.add_paragraph("P21 validation report not available at time of SDRG generation.")

    return p21
```

### Section 6: Non-Standard Variables
```python
def write_nonstandard_variables(sdtm_dir, study_config, mapping_spec):
    """
    Document all non-standard variables and justify their inclusion.

    For each non-standard variable:
    - Variable name and domain
    - Reason for inclusion
    - Source of data
    - Reference to Define.xml MethodDef

    Non-standard = not in SDTM IG standard variables for the domain
    """
    nonstandard = Section("Non-Standard Variables")

    for domain in study_config['sdtm_domains']:
        filepath = os.path.join(sdtm_dir, f"{domain.lower()}.xpt")
        if not os.path.exists(filepath):
            continue

        ds = load_xpt(filepath)
        standard_vars = get_standard_variables(domain)
        non_std = [v for v in ds.columns if v not in standard_vars]

        for var in non_std:
            justification = lookup_justification(var, domain, mapping_spec)
            nonstandard.add_paragraph(
                f"{domain}.{var}: {justification}\n"
                f"This variable is documented in the Define.xml with a "
                f"study-specific CodeListDef."
            )

    return nonstandard
```

### Section 7: Cross-Domain Notes
```python
def write_crossdomain_notes(consistency_report_path, study_config):
    """
    Document cross-domain consistency findings.

    Contents:
    - USUBJID alignment status
    - Date consistency status
    - Treatment arm agreement status
    - Any discrepancies found and their resolution
    """
    notes = Section("Cross-Domain Consistency Notes")

    if consistency_report_path and os.path.exists(consistency_report_path):
        report = parse_consistency_report(consistency_report_path)
        for check in report.checks:
            if check.result == 'FAIL':
                notes.add_paragraph(
                    f"Check {check.check_id} ({check.domains}): {check.message}\n"
                    f"Resolution: {check.resolution_notes}"
                )
            elif check.result == 'WARN':
                notes.add_paragraph(
                    f"Check {check.check_id} ({check.domains}): {check.message}\n"
                    f"Note: {check.resolution_notes}"
                )

    return notes
```

### Section 8: Supplemental Qualifiers
```python
def write_suppqual_notes(sdtm_dir, study_config):
    """
    Document supplemental qualifier datasets.

    For each SUPPXX dataset:
    - Parent domain reference
    - QNAM values and their descriptions
    - Reason for using SUPPQUAL instead of standard variable
    """
    supp = Section("Supplemental Qualifiers")

    for domain in study_config['sdtm_domains']:
        supp_path = os.path.join(sdtm_dir, f"supp{domain.lower()}.xpt")
        if not os.path.exists(supp_path):
            continue

        supp_ds = load_xpt(supp_path)
        qnam_values = supp_ds['QNAM'].unique()
        for qnam in qnam_values:
            supp.add_paragraph(
                f"SUPP{domain} - QNAM={qnam}: "
                f"{get_qlabel(supp_ds, qnam)}\n"
                f"Reason: Non-standard variable, cannot be represented in standard {domain} domain."
            )

    return supp
```

---

## Key Variables

| Variable | Description | Source |
|----------|-------------|--------|
| SECTION | SDRG section name | PhUSE template |
| CONTENT | Section content | Generated from study data |
| study_id | Study identifier | study_config.study_id |
| ct_version | CT package version | study_config.ct_version |
| sdtm_domains | List of submitted domains | study_config.sdtm_domains |
| treatment_arms | Treatment arm descriptions | study_config.treatment_arms |

### PhUSE SDRG Section Order
1. Introduction
2. Study Design
3. Data Standards
4. Dataset Descriptions
5. P21 Validation Summary
6. Non-Standard Variables
7. Cross-Domain Consistency Notes
8. Supplemental Qualifiers
9. Data Issues and Resolutions
10. Abbreviations

---

## Output Schema

```yaml
sdrg_document:
  format: PDF
  path: "{output_path from regulatory-graph.yaml}"
  study_id: "{study_id from study config}"
  generation_date: "{timestamp}"

  sections:
    - title: "Introduction"
      required: true
      content: "Study identification, purpose, dataset overview"
    - title: "Study Design"
      required: true
      content: "Treatment arms from study_config.treatment_arms, countries from site_information"
    - title: "Data Standards"
      required: true
      content: "SDTM IG v3.4, CT version from study_config.ct_version"
    - title: "Dataset Descriptions"
      required: true
      content: "Per-domain descriptions for {sdtm_domains}"
    - title: "P21 Validation Summary"
      required: true
      content: "P21 results, error resolutions, warning justifications"
    - title: "Non-Standard Variables"
      required: true
      content: "Justifications for all non-standard variables"
    - title: "Cross-Domain Consistency Notes"
      required: false
      content: "Consistency check results and resolutions"
    - title: "Supplemental Qualifiers"
      required: false
      content: "SUPPXX documentation"
    - title: "Data Issues and Resolutions"
      required: true
      content: "Summary of all data issues encountered and resolved"
    - title: "Abbreviations"
      required: false
      content: "Abbreviation reference table"
```

---

## Edge Cases

### No P21 Validation Report Available
```python
# If P21 report is not yet generated:
# - Note in SDRG that P21 validation is pending
# - Generate remaining sections
# - Flag for update once P21 is complete
# - Do NOT leave P21 section empty -- state "pending"
```

### Empty Domains
```python
# If a domain in study_config.sdtm_domains has zero records:
# - Document in Dataset Descriptions that domain was created but has no data
# - Explain reason (e.g., "No medical history was collected in this study")
# - Include empty domain in dataset list for completeness
```

### No Non-Standard Variables
```python
# If all variables are standard SDTM:
# - State "No non-standard variables were used in this submission"
# - Do NOT omit the section -- explicitly state there are none
```

### Missing Study Config
```python
# If specs/study-config.yaml is missing or incomplete:
# - Log error with specific missing keys
# - Abort SDRG generation -- cannot produce without study metadata
# - Provide actionable error message
```

### Treatment Arms with Complex Descriptions
```python
# If treatment_arms entries have additional fields (dose, route, etc.):
# - Include all available fields in the Study Design section table
# - Cross-reference with TA domain if available
# - Ensure ARMCD descriptions match Define.xml
```

---

## Integration Points

### Upstream Skills
- `/p21-validator` -- P21 validation report required for SDRG
- `/p21-report-reviewer` -- P21 resolution report with justifications
- `/sdtm-consistency-checker` -- Cross-domain consistency results
- `/define-draft-builder` -- Define.xml method references
- `/study-setup` -- Study configuration providing all study metadata

### Downstream Skills
- `/esub-assembler` -- Includes SDRG in submission package

### Related Skills
- `/define-xml-builder` -- Define.xml must be consistent with SDRG descriptions
- `/acrf-finalizer` -- aCRF annotations should match SDRG descriptions

---

## Evaluation Criteria

**Mandatory:**
- All P21 issues addressed in guide (errors resolved, warnings justified)
- Non-standard variables justified with rationale
- Treatment arms listed from study_config.treatment_arms (not hardcoded)
- CT version from study_config.ct_version (not hardcoded)
- Domain list from study_config.sdtm_domains (not hardcoded)
- Study ID from study_config.study_id (not hardcoded)
- Follows PhUSE SDRG template structure
- All 10 sections present (even if some state "Not applicable")

**Recommended:**
- P21 validation summary includes rule-by-rule documentation
- Cross-domain consistency results documented
- Supplemental qualifiers explained
- Abbreviation table included
- Data issues section provides timeline of resolutions

---

## Critical Constraints

**Never:**
- Produce output without validation
- Skip required sections
- Ignore CDISC controlled terminology
- Hardcode treatment arm names -- always read from `study_config.treatment_arms`
- Hardcode CT version -- always use `study_config.ct_version`
- Hardcode domain list -- always use `study_config.sdtm_domains`
- Hardcode study_id -- always use `study_config.study_id`
- Submit SDRG before P21 validation is complete
- Omit justification for non-standard variables

**Always:**
- Validate all inputs before processing
- Use PhUSE SDRG template structure
- Document any deviations from standards
- Generate traceable, reproducible results
- Resolve all study metadata from study config
- Resolve path patterns from regulatory-graph.yaml
- Include P21 validation summary with rule details
- Cross-reference Define.xml for method descriptions

---

## Examples

### Basic Usage
```bash
python csp-skills/layer-3-sdtm-qc/sdrg-writer/script.py \
  --input output/sdtm/ \
  --output docs/sdrg.pdf \
  --study-config specs/study-config.yaml \
  --p21-report reports/p21-sdtm-report.xlsx
```

### With Full Context
```bash
python csp-skills/layer-3-sdtm-qc/sdrg-writer/script.py \
  --input output/sdtm/ \
  --output docs/sdrg.pdf \
  --study-config specs/study-config.yaml \
  --p21-report reports/p21-sdtm-report.xlsx \
  --p21-resolved ops/p21-sdtm-resolved.yaml \
  --consistency-report reports/sdtm-crossdomain-report.html \
  --define-xml output/define/define-sdtm-draft.xml
```

### Expected Output
```
docs/sdrg.pdf
+-- Section 1: Introduction (study identification, dataset overview)
+-- Section 2: Study Design (treatment arms from study config, countries)
+-- Section 3: Data Standards (SDTM IG v3.4, CT version from study config)
+-- Section 4: Dataset Descriptions (per domain from study_config.sdtm_domains)
+-- Section 5: P21 Validation Summary (error resolutions, warning justifications)
+-- Section 6: Non-Standard Variables (justifications)
+-- Section 7: Cross-Domain Consistency Notes
+-- Section 8: Supplemental Qualifiers
+-- Section 9: Data Issues and Resolutions
+-- Section 10: Abbreviations
```
