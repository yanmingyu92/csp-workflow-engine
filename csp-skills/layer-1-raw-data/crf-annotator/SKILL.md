---
name: crf-annotator
description: Annotate blank CRF with SDTM variable targets. Triggers on "CRF", "case report form", "annotated CRF", "aCRF", "CRF annotation", "CDASH".
version: "2.0"
user-invocable: true
context: fork
model: sonnet
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
argument-hint: "[options] -- --input <blank-crf> --output <acrf-path> --mapping-spec <spec-path>"
---

## Runtime Configuration (Step 0)

Resolve configuration in order:
1. `$ARGUMENTS` (highest precedence)
2. `specs/sdtm-mapping-spec.xlsx` (or .yaml) -- mapping specifications
3. `specs/study-config.yaml` -- study-level metadata
4. `docs/acrf-draft.pdf` -- prior annotation state

```yaml
config_resolution:
  study_id: "$ARGUMENTS.study_id || study-config.study_id"
  blank_crf: "$ARGUMENTS.input || 'docs/blank-crf.pdf'"
  mapping_spec: "$ARGUMENTS.mapping_spec || 'specs/sdtm-mapping-spec.xlsx'"
  output_path: "$ARGUMENTS.output || 'docs/acrf-draft.pdf'"
```

## EXECUTE NOW
Parse $ARGUMENTS: --input, --output, --mapping-spec, --dry-run
**START NOW.**

---

## Philosophy

**The annotated CRF (aCRF) bridges clinical operations and data standards.** Every CRF field must map to a specific SDTM domain.variable. The aCRF is a required FDA submission document that provides traceability from data collection to the submitted datasets. Per the FDA Study Data Technical Conformance Guide, annotations must use CDISC standard variable names.

---

## Input/Output Specification

### Inputs (matching regulatory-graph.yaml node `crf-validation`)
| Input | Format | Required | Source |
|-------|--------|----------|--------|
| Blank CRF | pdf | Yes | docs/blank-crf.pdf |
| SDTM mapping specification | xlsx/yaml | Yes | specs/sdtm-mapping-spec.xlsx |
| Study configuration | yaml | Yes | specs/study-config.yaml |

### Outputs (matching regulatory-graph.yaml node `crf-validation`)
| Output | Format | Path Pattern | Description |
|--------|--------|--------------|-------------|
| Annotated CRF (draft) | pdf | docs/acrf-draft.pdf | CRF with SDTM annotations |
| Annotation mapping log | yaml | ops/crf-annotation-log.yaml | Mapping details per field |

---

## CDASH-to-SDTM Variable Mapping Logic

### Standard Mapping Rules

```yaml
annotation_standards:
  format: "Domain.Variable"
  font: "Helvetica 8pt, blue"
  placement: "right margin, aligned with CRF field"

  cdash_to_sdtm_mappings:
    # Demographics
    - cdash_field: "Date of Birth"
      sdtm_target: "DM.BRTHDAT"
      cdash_variable: "BRTHDAT"
      annotation: "DM.BRTHDAT"

    - cdash_field: "Sex"
      sdtm_target: "DM.SEX"
      cdash_variable: "SEX"
      annotation: "DM.SEX"

    - cdash_field: "Race"
      sdtm_target: "DM.RACE"
      cdash_variable: "RACE"
      annotation: "DM.RACE"

    # Adverse Events
    - cdash_field: "Adverse Event Term"
      sdtm_target: "AE.AETERM"
      cdash_variable: "AETERM"
      annotation: "AE.AETERM"

    - cdash_field: "Start Date/Time of AE"
      sdtm_target: "AE.AESTDTC"
      cdash_variable: "AESTDAT"
      annotation: "AE.AESTDTC"

    # Laboratory
    - cdash_field: "Lab Test"
      sdtm_target: "LB.LBTEST"
      cdash_variable: "LBTEST"
      annotation: "LB.LBTEST"

    - cdash_field: "Lab Result"
      sdtm_target: "LB.LBORRES"
      cdash_variable: "LBORRES"
      annotation: "LB.LBORRES"
```

### Annotation Format Standards

```yaml
annotation_format:
  # Each annotation follows this pattern:
  # Domain.Variable -- for single-target fields
  # Domain.Variable1, Domain.Variable2 -- for multi-target fields
  # [SUPPXX.QNAM] -- for supplemental qualifiers
  # * -- for fields that are not mapped (with footnote justification)

  color_coding:
    mapped: "blue"          # Standard SDTM mapping
    supp: "green"           # Supplemental qualifier
    derived: "purple"       # Derived variable (not direct CRF field)
    unmapped: "red"          # Unmapped with justification
    multi_target: "blue"    # Maps to multiple SDTM variables

  page_layout:
    annotation_column_width: "2 inches"
    annotation_alignment: "right-justified"
    leader_line: "dotted, 0.5pt"
    header_per_page: "Study: {study_id} | Annotated CRF Draft"
```

---

## Domain-Specific Annotation Patterns

### Demographics (DM)
- BRTHDAT -> DM.BRTHDAT (with footnote: "Age derived from BRTHDAT and reference date")
- SEX -> DM.SEX (map CDISC CT: M, F, U, UN)
- RACE -> DM.RACE (map CDISC CT: WHITE, BLACK OR AFRICAN AMERICAN, etc.)
- ETHNIC -> DM.ETHNIC

### Adverse Events (AE)
- AETERM -> AE.AETERM (verbatim term)
- AE coded term -> AE.AEDECOD (from MedDRA coding)
- AE body system -> AE.AEBODSYS (from MedDRA SOC)
- AE severity -> AE.AESEV (MILD, MODERATE, SEVERE per CDISC CT)
- AE seriousness -> AE.AESER (Y/N)
- AE start date -> AE.AESTDTC (ISO 8601 format)

### Laboratory (LB)
- LBTEST -> LB.LBTEST (CDISC CT for lab test name)
- LBORRES -> LB.LBORRES (original result)
- LBORRESU -> LB.LBORRESU (original units)
- LBSTRESC -> LB.LBSTRESC (standardized character result)
- LBSTRESN -> LB.LBSTRESN (standardized numeric result)
- LBSTRESU -> LB.LBSTRESU (standardized units)

---

## Output Schema

```yaml
annotation_result:
  study_id: "{study_id}"
  annotation_date: "{ISO_8601}"
  source_crf: "docs/blank-crf.pdf"
  output_acrf: "docs/acrf-draft.pdf"
  mapping_spec: "specs/sdtm-mapping-spec.xlsx"

  statistics:
    total_fields: "{n_fields}"
    mapped: "{n_mapped}"
    unmapped: "{n_unmapped}"
    multi_target: "{n_multi}"
    supp_qualifier: "{n_supp}"

  field_annotations:
    - crf_page: 1
      field_name: "Date of Birth"
      field_location: "x:120, y:340"
      annotation: "DM.BRTHDAT"
      annotation_type: "mapped"
      cdash_compliant: true
    - crf_page: 1
      field_name: "Subject Initials"
      annotation: "*"
      annotation_type: "unmapped"
      justification: "Not collected per GDPR; not mapped to SDTM"
```

---

## Edge Cases

### Fields Not Mapping to Standard SDTM
- Some CRF fields have no standard SDTM variable
- Annotate with "[SUPPDM.QNAM]" if mapped to supplemental qualifier
- Annotate with "*" if unmapped, with footnote justification
- Document in the annotation log why standard mapping is not applicable

### Multi-Target Fields
- Single CRF field may map to multiple SDTM variables (e.g., a combined date-time field)
- Annotate all targets separated by commas
- Example: "VS.VSDTC, VS.VSTPT" for a vital signs date/time field

### CDASH Non-Compliance
- EDC may use non-CDASH variable names
- Annotate with standard SDTM target, note CDASH deviation
- Document the actual EDC field name vs expected CDASH name

### Repeating Sections
- CRF with repeating sections (e.g., multiple AE rows) need annotations once with "(repeat)" note
- Document the expected maximum number of repetitions

---

## Integration Points

### Upstream Skills
- `/study-setup` -- Treatment arm definitions, visit schedule
- `/spec-builder` -- SDTM mapping specifications

### Downstream Skills
- `/crf-validator` -- Validates annotations against CDASH
- `/acrf-finalizer` -- Finalizes aCRF after SDTM datasets are produced

### Related Skills
- `/data-quality` -- Quality checks on CRF completeness
- `/workflow` -- Track aCRF completion status

---

## Evaluation Criteria

**Mandatory:**
- Every CRF field annotated with target SDTM domain.variable
- No unmapped fields without documented justification
- Annotations use CDISC standard variable names
- Annotation format follows FDA TCG guidelines

**Recommended:**
- CDASH compliance verified for field naming
- Color-coding applied for mapping types
- Annotation log generated for traceability

---

## Critical Constraints

**Never:**
- Leave a CRF field without annotation or justification
- Use non-standard variable names in annotations
- Produce aCRF without referencing the mapping specification
- Skip the annotation log (required for traceability)

**Always:**
- Use CDISC SDTM variable names (Domain.Variable format)
- Document all unmapped fields with justification
- Include study identifier on every page
- Generate the annotation log alongside the annotated PDF

---

## Examples

### Basic Annotation
```bash
python csp-skills/layer-1-raw-data/crf-annotator/script.py \
  --input docs/blank-crf.pdf \
  --output docs/acrf-draft.pdf \
  --mapping-spec specs/sdtm-mapping-spec.xlsx
```

### Dry Run
```bash
python csp-skills/layer-1-raw-data/crf-annotator/script.py \
  --input docs/blank-crf.pdf \
  --output docs/acrf-draft.pdf \
  --mapping-spec specs/sdtm-mapping-spec.xlsx \
  --dry-run
```
