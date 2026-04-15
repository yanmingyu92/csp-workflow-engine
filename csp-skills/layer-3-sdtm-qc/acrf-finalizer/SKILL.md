---
name: acrf-finalizer
description: Finalize annotated CRF with verified annotations. Triggers on "annotated CRF", "aCRF", "final aCRF", "CRF finalize", "CRF annotation finalization", "blank CRF".
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
3. Resolve path patterns from `regulatory-graph.yaml` node `sdtm-annotated-crf` definitions
4. If critical config missing, log error and abort

### Required Config Keys
| Key | Source | Fallback |
|-----|--------|----------|
| `study_id` | `specs/study-config.yaml` | Required - abort if missing |
| `sdtm_domains` | `specs/study-config.yaml` | Required - abort if missing |
| `input_acrf` | `--input` argument | `docs/acrf-draft.pdf` |
| `output_acrf` | `--output` argument | `docs/acrf-final.pdf` |
| `sdtm_dir` | `regulatory-graph.yaml` | `output/sdtm/` |

## EXECUTE NOW
Parse $ARGUMENTS: --input, --output, --spec, --validate, --dry-run
**START NOW.**

---

## Philosophy
**Final aCRF must exactly match produced SDTM datasets.** Every annotation links a CRF field to an actual domain.variable. The annotated CRF is a regulatory submission document that enables FDA reviewers to trace collected data back to its SDTM representation. Annotations must be verified against the final, validated SDTM datasets -- not against the draft or specification.

**Key Principle:** The aCRF serves as the bridge between the data collection instrument (CRF) and the submission datasets. Each form field must be annotated with the target SDTM domain, variable name, and where applicable, the origin type (CRF, Derived, Assigned, Protocol).

---

## Input/Output Specification

### Inputs (from `regulatory-graph.yaml` node `sdtm-annotated-crf`)
| Input | Format | Path Pattern | Required |
|-------|--------|--------------|----------|
| Draft annotated CRF | pdf | `docs/acrf-draft.pdf` | Yes |
| All SDTM domain datasets | xpt | `output/sdtm/*.xpt` | Yes |
| Study configuration | yaml | `specs/study-config.yaml` | Yes |
| SDTM mapping specification | xlsx/yaml | `specs/sdtm-mapping-spec.xlsx` | No |
| P21 validation report | xlsx | `reports/p21-sdtm-report.xlsx` | No |

### Outputs (from `regulatory-graph.yaml` node `sdtm-annotated-crf`)
| Output | Format | Path Pattern | Description |
|--------|--------|--------------|-------------|
| Final annotated CRF | pdf | `docs/acrf-final.pdf` | Verified annotations matching produced datasets |

---

## Script Execution

```bash
python csp-skills/layer-3-sdtm-qc/acrf-finalizer/script.py \
  --input {draft_acrf_path} \
  --output {final_acrf_path} \
  --study-config specs/study-config.yaml \
  --sdtm-dir output/sdtm/
```

### Arguments
| Argument | Required | Description |
|----------|----------|-------------|
| `--input` | Yes | Path to draft annotated CRF (PDF) |
| `--output` | Yes | Output path for final annotated CRF (PDF) |
| `--study-config` | No | Study configuration YAML |
| `--sdtm-dir` | No | Directory containing final SDTM XPT datasets |
| `--mapping-spec` | No | SDTM mapping specification for annotation reference |
| `--validate` | No | Validate all annotations against datasets |
| `--dry-run` | No | Show verification results without writing |

---

## Domain-Specific Derivation Logic

### Annotation Verification Process

#### Step 1: Load Configuration
```python
def load_study_config(config_path):
    """
    Load study configuration for dynamic annotation verification.

    Required keys:
      - study_id: unique study identifier
      - sdtm_domains: list of expected SDTM domains
    """
    config = read_yaml(config_path)
    required_keys = ['study_id', 'sdtm_domains']
    missing = [k for k in required_keys if k not in config]
    if missing:
        log_error(f"Missing critical study config keys: {missing}")
        abort()
    return config
```

#### Step 2: Extract Annotations from Draft aCRF
```python
def extract_annotations(acrf_pdf):
    """
    Parse the draft aCRF to extract all existing annotations.

    Returns list of annotation objects:
      - page_number: CRF page where annotation appears
      - annotation_text: the SDTM domain.variable reference
      - crf_field: the CRF field being annotated
      - position: coordinates on the page
    """
    annotations = parse_pdf_annotations(acrf_pdf)
    return annotations
```

#### Step 3: Verify Annotations Against Produced Datasets
```python
def verify_annotations(annotations, sdtm_dir, study_config):
    """
    Cross-reference every annotation against the actual SDTM datasets.

    For each annotation:
    1. Parse domain.variable from annotation text (e.g., "DM.SEX", "AE.AETERM")
    2. Load the corresponding dataset from sdtm_dir
    3. Verify the variable exists in the dataset
    4. Verify the variable is populated (not all null)
    5. Check origin type matches expectation (CRF, Derived, Assigned)
    6. For coded variables, verify values match controlled terminology

    Returns verification results per annotation:
      - verified: True/False
      - variable_exists: True/False
      - data_present: True/False
      - origin_type: matched origin
      - issues: list of discrepancies
    """
    results = []
    for annotation in annotations:
        domain, variable = parse_annotation(annotation)
        if domain not in study_config['sdtm_domains']:
            results.append(VerificationResult(
                annotation=annotation,
                verified=False,
                issues=[f"Domain {domain} not in study_config.sdtm_domains"]
            ))
            continue

        dataset = load_xpt(os.path.join(sdtm_dir, f"{domain.lower()}.xpt"))
        result = verify_against_dataset(annotation, dataset)
        results.append(result)

    return results
```

#### Step 4: Identify Unannotated CRF Fields
```python
def find_unannotated_fields(acrf_pdf, sdtm_dir, mapping_spec):
    """
    Compare CRF fields against annotations to find gaps.

    A CRF field without an annotation is a potential issue:
    - If mapped to a non-standard variable -> should be annotated with SUPPXX reference
    - If intentionally not collected -> document reason
    - If oversight -> flag for annotation
    """
    crf_fields = extract_crf_fields(acrf_pdf)
    annotated_fields = extract_annotated_fields(acrf_pdf)
    unannotated = set(crf_fields) - set(annotated_fields)

    gaps = []
    for field in unannotated:
        mapping = lookup_mapping(field, mapping_spec)
        if mapping and mapping.target_variable:
            gaps.append(UnannotatedField(
                field=field,
                expected_annotation=mapping.target_variable,
                reason="Missing annotation for mapped field"
            ))

    return gaps
```

#### Step 5: Generate Final aCRF
```python
def generate_final_acrf(draft_acrf, verification_results, output_path):
    """
    Produce the final annotated CRF with:
    1. All verified annotations marked with checkmark
    2. Origin type labels (e.g., "[CRF]", "[Derived]", "[Assigned]")
    3. Annotation key/legend on first page
    4. Unannotated fields flagged for reviewer attention

    Output: PDF with finalized, verified annotations.
    """
    # Add verification stamps to annotations
    for result in verification_results:
        if result.verified:
            stamp_verified(draft_acrf, result.annotation)
        else:
            stamp_issue(draft_acrf, result.annotation, result.issues)

    # Add annotation key page
    add_annotation_key(draft_acrf)

    # Write final PDF
    write_pdf(draft_acrf, output_path)
```

---

## Key Variables

| Variable | Description | Origin |
|----------|-------------|--------|
| CRF_PAGE | CRF page number | Extracted from PDF |
| ANNOTATION | SDTM mapping annotation (domain.variable) | Draft aCRF |
| VERIFIED | Yes/No - annotation matches produced dataset | Verification step |
| ORIGIN_TYPE | CRF, Derived, Assigned, Protocol | Mapping spec |
| DOMAIN | Target SDTM domain (from {sdtm_domains}) | Study config |
| VARIABLE | Target SDTM variable name | Mapping spec |

### Annotation Format Standard
```
Domain.Variable [OriginType]
Example: DM.SEX [CRF]
Example: DM.RFSTDTC [Derived]
Example: AE.AETERM [CRF]
Example: AE.AEDECOD [Assigned - MedDRA coding]
```

---

## Output Schema

```yaml
acrf_finalization_report:
  study_id: "{study_id from study config}"
  source_acrf: "{draft_acrf_path from regulatory-graph.yaml}"
  output_acrf: "{final_acrf_path from regulatory-graph.yaml}"
  verification_date: "{timestamp}"

  summary:
    total_annotations: 0
    verified: 0
    failed_verification: 0
    unannotated_fields: 0

  annotations:
    - page: 1
      annotation: "DM.SUBJID"
      origin_type: "CRF"
      verified: true
      issues: []

    - page: 3
      annotation: "AE.AETERM"
      origin_type: "CRF"
      verified: true
      issues: []

    - page: 3
      annotation: "AE.AEDECOD"
      origin_type: "Assigned - MedDRA"
      verified: true
      issues: []

  unannotated_fields:
    - page: 5
      field: "Investigator Comment"
      expected_annotation: "SUPPAE.COMMENT"
      status: "Missing annotation"
```

---

## Edge Cases

### Study-Specific Variables Not in Standard Domains
```python
# CRF fields mapped to SUPPXX (supplemental qualifiers):
# - Annotation should reference SUPPXX.QNAM=XXXXX
# - Verify QNAM exists in SUPP dataset
# - Document in aCRF annotation key
```

### Multi-Page CRF Forms
```python
# A single CRF form may span multiple pages:
# - Verify annotations are consistent across pages
# - Each page should have its own page-level annotation header
# - Repeating forms (e.g., vital signs) must have annotations per visit
```

### Variables Derived from Multiple CRF Fields
```python
# Some SDTM variables are derived from multiple CRF fields:
# - Annotate each contributing field separately
# - Note the derivation logic in the annotation
# - Example: BMI derived from HEIGHT and WEIGHT -> annotate both fields
```

### Draft aCRF Missing or Incomplete
```python
# If draft aCRF is not found at expected path:
# - Check regulatory-graph.yaml for crf-validation node path_pattern
# - Verify CRF annotation skill completed successfully
# - Cannot finalize without draft - abort with actionable error
```

### P21 Validation Discrepancies
```python
# If P21 validation found issues with annotated variables:
# - Cross-reference P21 issues with aCRF annotations
# - Flag annotations for variables with P21 errors
# - Do NOT finalize aCRF until P21 errors are resolved
```

### Annotated but Variable Not in Dataset
```python
# If an annotation references a variable that does not exist in the dataset:
# - Flag as FAILED verification
# - Check if variable was renamed or removed
# - Either update annotation or add variable to dataset
```

---

## Integration Points

### Upstream Skills
- `/crf-annotator` -- Produces the draft aCRF (Layer 1)
- `/crf-validator` -- Validates CRF fields against CDASH (Layer 1)
- `/p21-validator` -- P21 validation must be complete before finalization
- `/sdtm-dm-mapper` -- DM domain variables for annotation verification
- `/sdtm-ae-mapper` -- AE domain variables for annotation verification
- `/study-setup` -- Study configuration providing study_id, sdtm_domains

### Downstream Skills
- `/sdrg-writer` -- SDRG references the annotated CRF
- `/esub-assembler` -- Includes final aCRF in submission package

### Related Skills
- `/define-draft-builder` -- Define.xml should match aCRF annotations
- `/sdtm-supp-builder` -- SUPPXX variable annotations

---

## Evaluation Criteria

**Mandatory:**
- Every annotation matches a produced dataset variable (verified = true)
- No unannotated CRF fields that map to SDTM variables
- Annotation key/legend present on first page
- Origin type labeled for every annotation
- All domains from `study_config.sdtm_domains` represented in annotations

**Recommended:**
- All annotations include origin type (CRF, Derived, Assigned)
- Supplemental qualifier annotations present for non-standard variables
- Annotation style consistent across all pages
- P21 validation results cross-referenced with annotations

---

## Critical Constraints

**Never:**
- Produce output without validating annotations against datasets
- Skip required variables in annotation verification
- Ignore CDISC controlled terminology in coded variable annotations
- Finalize aCRF before P21 validation is complete (errors must be resolved)
- Hardcode study_id or domain references
- Accept unverified annotations

**Always:**
- Validate all inputs before processing
- Verify every annotation against the actual produced SDTM dataset
- Cross-reference with study_config.sdtm_domains
- Document any deviations from standards
- Generate traceable, reproducible results
- Include annotation key explaining annotation format
- Flag all unannotated CRF fields for review
- Resolve path patterns from regulatory-graph.yaml

---

## Examples

### Basic Usage
```bash
python csp-skills/layer-3-sdtm-qc/acrf-finalizer/script.py \
  --input docs/acrf-draft.pdf \
  --output docs/acrf-final.pdf \
  --study-config specs/study-config.yaml
```

### With Full Verification
```bash
python csp-skills/layer-3-sdtm-qc/acrf-finalizer/script.py \
  --input docs/acrf-draft.pdf \
  --output docs/acrf-final.pdf \
  --study-config specs/study-config.yaml \
  --sdtm-dir output/sdtm/ \
  --mapping-spec specs/sdtm-mapping-spec.xlsx \
  --validate
```

### Expected Output
```
docs/acrf-final.pdf
+-- Annotation key page (legend for annotation format)
+-- Annotated CRF pages with verified annotations
+-- Origin type labels ([CRF], [Derived], [Assigned])
+-- Verification stamps (checkmark for verified, flag for issues)

ops/acrf-verification-report.yaml
+-- Summary (total, verified, failed, unannotated counts)
+-- Per-annotation verification results
+-- List of unannotated CRF fields
```
