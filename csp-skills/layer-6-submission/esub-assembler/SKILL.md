---
name: esub-assembler
description: Assemble eCTD Module 5 submission package with correct directory structure. Triggers on "eCTD", "submission package", "eSub", "Module 5", "electronic submission", "submission assembly".
version: "2.0"
user-invocable: true
context: fork
model: sonnet
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
argument-hint: "[options] -- --input <source-dirs> --output <esub-dir> --config <study-config>"
---

## Runtime Configuration (Step 0)

Resolve configuration in order:
1. `$ARGUMENTS` (highest precedence)
2. `specs/study-config.yaml` -- study metadata
3. `output/esub/` -- prior assembly state
4. `ops/submission-checklist.yaml` -- checklist of required components

```yaml
config_resolution:
  study_id: "$ARGUMENTS.study_id || study-config.study_id"
  output_dir: "$ARGUMENTS.output || 'output/esub/'"
  config: "$ARGUMENTS.config || 'specs/study-config.yaml'"
```

## EXECUTE NOW
Parse $ARGUMENTS: --input, --output, --config, --dry-run
**START NOW.**

---

## Philosophy

**eCTD structure must follow FDA guidance precisely.** Directory naming, file placement, and reference linkage are critical. Per ICH M8 eCTD v4.0, the directory structure and file naming must conform to regional specifications. A single misplaced file can cause submission rejection.

---

## Input/Output Specification

### Inputs (matching regulatory-graph.yaml node `esub-package-assembly`)
| Input | Format | Required | Source |
|-------|--------|----------|--------|
| SDTM datasets | xpt | Yes | output/sdtm/ |
| ADaM datasets | xpt | Yes | output/adam/ |
| Define.xml files | xml | Yes | output/define/ |
| TFL outputs | rtf/pdf | Yes | output/tfl/formatted/ |
| Annotated CRF | pdf | Yes | docs/acrf-final.pdf |
| Reviewer's guides | pdf | Yes | docs/sdrg.pdf, docs/adrg.pdf |

### Outputs (matching regulatory-graph.yaml node `esub-package-assembly`)
| Output | Format | Path Pattern | Description |
|--------|--------|--------------|-------------|
| eCTD submission package | directory | output/esub/ | Complete eCTD structure |

---

## eCTD Directory Structure

```
output/esub/
  m5/
    {study_id}/
      5-3-clinical-study-reports/
        5-3-1-study-reports/
          {study_id}-clinical-study-report/
            {study_id}-csr.pdf
            tabular/
              sdtm/
                dm.xpt
                ae.xpt
                lb.xpt
                vs.xpt
                cm.xpt
                mh.xpt
                ex.xpt
                ds.xpt
                sv.xpt
                ts.xpt
                ta.xpt
                ti.xpt
                tv.xpt
                supp*.xpt
                relrec.xpt
              adam/
                adsl.xpt
                adae.xpt
                adlb.xpt
                adtte.xpt
                adeff.xpt
              define.xml              # SDTM Define.xml
              define_adam.xml         # ADaM Define.xml
              acrf.pdf                # Annotated CRF
              sdrg.pdf                # SDTM Reviewer's Guide
              adrg.pdf                # ADaM Reviewer's Guide
              xpt/
                blankcrf.pdf
            listing/
              ae-listing.pdf
              lab-listing.pdf
              disposition-listing.pdf
              pd-listing.pdf
            figures/
              figure-14.4.1.pdf
              figure-14.4.2.pdf
  index.xml                           # eCTD index file
```

---

## File Naming Conventions

```yaml
naming_conventions:
  datasets: "{domain}.xpt"            # lowercase domain code
  define_xml: "define.xml"             # SDTM Define.xml
  define_adam: "define_adam.xml"       # ADaM Define.xml
  acrf: "acrf.pdf"
  sdrg: "sdrg.pdf"
  adrg: "adrg.pdf"
  tables: "t-{table_id}-{short_title}.rtf"
  listings: "l-{listing_id}-{short_title}.pdf"
  figures: "f-{figure_id}-{short_title}.png"
```

---

## Output Schema

```yaml
assembly_result:
  study_id: "{study_id}"
  assembled_at: "{ISO_8601}"
  output_dir: "output/esub/"

  components:
    - component: "SDTM Datasets"
      expected: "{n_sdtm}"
      found: "{n_found}"
      status: "COMPLETE | INCOMPLETE"
      path: "m5/{study_id}/5-3-clinical-study-reports/.../sdtm/"

    - component: "ADaM Datasets"
      expected: "{n_adam}"
      found: "{n_found}"
      status: "COMPLETE | INCOMPLETE"

    - component: "Define.xml (SDTM)"
      path: "m5/.../define.xml"
      status: "PRESENT | MISSING"

    - component: "Define.xml (ADaM)"
      path: "m5/.../define_adam.xml"
      status: "PRESENT | MISSING"

    - component: "Annotated CRF"
      path: "m5/.../acrf.pdf"
      status: "PRESENT | MISSING"

    - component: "SDRG"
      status: "PRESENT | MISSING"

    - component: "ADRG"
      status: "PRESENT | MISSING"

    - component: "TFLs"
      expected: "{n_tfls}"
      found: "{n_found}"
      status: "COMPLETE | INCOMPLETE"
```

---

## Edge Cases

### Missing Components
- If a required component is missing: log the absence, do not create placeholder
- Report clearly which components are missing
- Allow partial assembly with documented gaps

### Large Dataset Files
- XPT files may be large; verify no file exceeds FDA limits
- Compress if needed (FDA accepts gzip for some file types)

### Multiple Study Reports
- If multiple studies in one submission, each gets its own subdirectory
- Follow eCTD backbone for linking

---

## Integration Points

### Upstream Skills
- `/define-xml-builder` -- Define.xml files
- `/define-xml-validator` -- Validated Define.xml
- `/tfl-formatter` -- Formatted TFL outputs
- `/tfl-qc-validator` -- QC-passed TFLs
- `/sdtm-reviewer-guide` -- SDRG document
- `/adam-reviewer-guide` -- ADRG document

### Downstream Skills
- `/esub-validator` -- Validates assembled package
- `/submission-checklist` -- Checks completeness

### Related Skills
- `/workflow` -- Track assembly status

---

## Evaluation Criteria

**Mandatory:**
- All required components present in correct locations
- eCTD directory structure follows ICH M8 specification
- File naming conventions followed
- Define.xml and datasets in same directory

**Recommended:**
- Package size within FDA limits (1GB per submission unit)
- All files have correct MIME types
- Index file generated

---

## Critical Constraints

**Never:**
- Include files that have not passed validation
- Use non-standard directory names
- Hardcode study identifiers in directory paths
- Omit any required document (aCRF, SDRG, ADRG, Define.xml)

**Always:**
- Follow eCTD directory structure per ICH M8
- Use dynamic study identifier from config
- Verify all components are present before assembly
- Generate assembly manifest for traceability

---

## Examples

### Full Assembly
```bash
python csp-skills/layer-6-submission/esub-assembler/script.py \
  --output output/esub/ \
  --config specs/study-config.yaml
```

### Dry Run
```bash
python csp-skills/layer-6-submission/esub-assembler/script.py \
  --output output/esub/ \
  --config specs/study-config.yaml \
  --dry-run
```
