---
name: define-xml-builder
description: Generate final Define.xml for SDTM and ADaM datasets. Triggers on "Define.xml SDTM", "SDTM Define", "define-xml SDTM", "SDTM metadata", "CRT-DD", "final Define SDTM".
version: "2.0"
user-invocable: true
context: fork
model: sonnet
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
argument-hint: "[options] -- --input <datasets-dir> --draft <draft-xml> --output <define-xml>"
---

## Runtime Configuration (Step 0)

Resolve configuration in order:
1. `$ARGUMENTS` (highest precedence)
2. `output/define/define-sdtm-draft.xml` -- draft from Layer 3
3. `specs/sdtm-mapping-spec.xlsx` -- mapping specifications
4. `specs/adam-derivation-spec.xlsx` -- ADaM derivation specifications
5. `specs/study-config.yaml` -- study metadata

```yaml
config_resolution:
  study_id: "$ARGUMENTS.study_id || study-config.study_id"
  input_dir: "$ARGUMENTS.input || 'output/sdtm/'"
  draft_xml: "$ARGUMENTS.draft || 'output/define/define-sdtm-draft.xml'"
  output_path: "$ARGUMENTS.output || 'output/define/define-sdtm.xml'"
  define_version: "2.1"
```

## EXECUTE NOW
Parse $ARGUMENTS: --input, --draft, --output, --validate, --dry-run
**START NOW.**

---

## Philosophy

**Define.xml is the regulatory metadata standard.** It provides machine-readable descriptions of every dataset, variable, controlled terminology, and computational method. Per CDISC Define-XML v2.1, the file must be schema-valid, include all value-level metadata, and render correctly with the CDISC stylesheet.

---

## Input/Output Specification

### Inputs (matching regulatory-graph.yaml node `define-xml-sdtm`)
| Input | Format | Required | Source |
|-------|--------|----------|--------|
| All SDTM/ADaM datasets | xpt | Yes | output/sdtm/ or output/adam/ |
| Define.xml draft | xml | Yes | output/define/define-sdtm-draft.xml |
| Mapping/derivation specifications | xlsx/yaml | Yes | specs/ |
| Study configuration | yaml | Yes | specs/study-config.yaml |

### Outputs (matching regulatory-graph.yaml node `define-xml-sdtm`)
| Output | Format | Path Pattern | Description |
|--------|--------|--------------|-------------|
| Define.xml (final) | xml | output/define/define-sdtm.xml | Schema-valid metadata |
| Define.xml (ADaM) | xml | output/define/define-adam.xml | ADaM metadata |

---

## Define.xml Structure (CDISC Define-XML v2.1)

### Document-Level Metadata
```xml
<?xml version="1.0" encoding="UTF-8"?>
<ODM xmlns="http://www.cdisc.org/ns/odm/v1.3"
     xmlns:def="http://www.cdisc.org/ns/def/v2.1"
     FileType="Snapshot"
     FileOID="{study_id}-define-{timestamp}"
     CreationDateTime="{ISO_8601}">
  <Study OID="{study_id}">
    <GlobalVariables>
      <StudyName>{study_id}</StudyName>
      <StudyDescription>{study_description}</StudyDescription>
      <ProtocolName>{protocol_name}</ProtocolName>
    </GlobalVariables>
    <MetaDataVersion OID="CDISC.Define.{study_id}"
                     Name="{study_id} Define.xml"
                     def:DefineVersion="2.1.0"
                     def:StandardName="CDISC SDTM"
                     def:StandardVersion="3.4">
```

### ItemGroupDef (Dataset-Level)
```xml
<ItemGroupDef OID="IG.DM" Name="DM" Domain="DM"
              Repeating="No" IsReferenceData="No"
              def:Structure="One record per subject"
              def:DatasetName="DM"
              def:HasNoData="No">
  <Description><TranslatedText>Demographics</TranslatedText></Description>
  <ItemRef ItemOID="IT.DM.STUDYID" OrderNumber="1" Mandatory="Yes"/>
  <ItemRef ItemOID="IT.DM.USUBJID" OrderNumber="2" Mandatory="Yes"/>
  <!-- ... all variables ... -->
</ItemGroupDef>
```

### ItemDef (Variable-Level)
```xml
<ItemDef OID="IT.DM.SEX" Name="SEX" DataType="text" Length="$SEX_LENGTH"
         def:Label="Sex">
  <Description><TranslatedText>Sex of the subject</TranslatedText></Description>
  <CodeListRef CodeListOID="CL.SEX"/>
</ItemDef>
```

### CodeList (Controlled Terminology)
```xml
<CodeList OID="CL.SEX" Name="SEX" DataType="text">
  <CodeListItem CodedValue="M" def:Rank="1">
    <Decode><TranslatedText>Male</TranslatedText></Decode>
  </CodeListItem>
  <CodeListItem CodedValue="F" def:Rank="2">
    <Decode><TranslatedText>Female</TranslatedText></Decode>
  </CodeListItem>
</CodeList>
```

### ComputationalMethod
```xml
<def:ComputationalMethod OID="CM.USUBJID" Name="USUBJID Derivation">
  <Description>
    <TranslatedText>USUBJID = STUDYID || '-' || SITEID || '-' || SUBJID</TranslatedText>
  </Description>
</def:ComputationalMethod>
```

---

## Validation Approach

1. Schema validation against CDISC Define-XML v2.1 XSD
2. Business rule validation (cross-references, completeness)
3. Stylesheet rendering test (CDISC provided XSL)
4. P21 Define.xml validation

---

## Output Schema

```yaml
define_xml_result:
  study_id: "{study_id}"
  generated_at: "{ISO_8601}"
  schema_version: "2.1"
  output_path: "output/define/define-sdtm.xml"

  datasets_documented: "{n_datasets}"
  variables_documented: "{n_variables}"
  codelists_documented: "{n_codelists}"
  methods_documented: "{n_methods}"

  validation:
    schema_valid: true
    stylesheet_renders: true
    p21_errors: 0
```

---

## Edge Cases

### Value-Level Metadata
- Some variables require value-level metadata (e.g., VSTESTCD has different attributes per test)
- Must define ValueListDef for these variables
- Document in the ItemDef with def:ValueListRef

### Supplemental Qualifiers
- SUPPXX datasets must reference their parent domains via RELDEF
- Document the relationship in the Define.xml structure

### Custom Domains
- Non-standard domains must document justification
- Include custom domain metadata with def:CustomDomain attribute

---

## Integration Points

### Upstream Skills
- `/define-draft-builder` -- Draft Define.xml from Layer 3
- `/p21-validator` -- P21 validation results
- `/adam-traceability-checker` -- Traceability for ADaM Define

### Downstream Skills
- `/define-xml-validator` -- Validates final Define.xml
- `/esub-assembler` -- Includes Define.xml in submission package

### Related Skills
- `/data-quality` -- Quality checks on metadata
- `/workflow` -- Track Define.xml generation status

---

## Evaluation Criteria

**Mandatory:**
- Schema-valid against Define-XML v2.1 schema
- All datasets and variables documented
- Controlled terminology references valid (CDISC CT version documented)
- Computational methods documented for derived variables

**Recommended:**
- Renders correctly in CDISC stylesheet
- Value-level metadata for key variables
- Hyperlinks functional

---

## Critical Constraints

**Never:**
- Generate Define.xml without validating against schema
- Omit controlled terminology references
- Use hardcoded study-specific values in templates
- Skip computational method documentation

**Always:**
- Include CDISC Define-XML v2.1 namespace declarations
- Document the CT version used for each codelist
- Validate schema compliance before output
- Generate from both draft and actual datasets

---

## Examples

### Build SDTM Define.xml
```bash
python csp-skills/layer-6-submission/define-xml-builder/script.py \
  --input output/sdtm/ \
  --draft output/define/define-sdtm-draft.xml \
  --output output/define/define-sdtm.xml
```

### Build ADaM Define.xml
```bash
python csp-skills/layer-6-submission/define-xml-builder/script.py \
  --input output/adam/ \
  --draft output/define/define-adam-draft.xml \
  --output output/define/define-adam.xml
```
