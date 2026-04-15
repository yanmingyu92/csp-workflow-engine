---
name: define-draft-builder
description: Generate draft Define.xml metadata for SDTM. Triggers on "Define.xml draft", "SDTM Define", "define draft", "dataset metadata", "variable metadata", "CRT-DD".
version: "1.0"
user-invocable: true
context: fork
model: sonnet
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
argument-hint: "[options] -- --input, --output"
---

## Runtime Configuration (Step 0)

1. Read `ops/workflow-state.yaml` for current workflow state
2. Read `specs/study-config.yaml` for study metadata
3. If critical config missing, log error and abort

### Required Config Keys
| Key | Source | Fallback |
|-----|--------|----------|
| `study_id`, `study_title`, `protocol_name` | `specs/study-config.yaml` | Required |
| `treatment_arms`, `site_information`, `sdtm_domains` | `specs/study-config.yaml` | Required |
| `ct_version`, `ct_package_url` | `specs/study-config.yaml` | Required |
| `input_dir` | `--input` argument | `output/sdtm/` |
| `output_xml` | `--output` argument | `output/define/define-sdtm-draft.xml` |

## EXECUTE NOW
Parse $ARGUMENTS: --input, --output, --spec, --validate, --dry-run
**START NOW.**

---

## Define.xml Structure

### Top-Level Template
```xml
<?xml version="1.0" encoding="UTF-8"?>
<ODM xmlns="http://www.cdisc.org/ns/odm/v1.3"
     ODMVersion="1.3.2" FileType="Snapshot"
     FileOID="define-{study_id}" CreationDateTime="{timestamp}">
  <Study OID="{study_id}">
    <GlobalVariables>
      <StudyName>{study_id}</StudyName>
      <StudyDescription>{study_title}</StudyDescription>
      <ProtocolName>{protocol_name}</ProtocolName>
    </GlobalVariables>
    <MetaDataVersion OID="CDISC.SDTMIG.3.4" Name="SDTM IG v3.4">
      <Include href="{ct_package_url}"/>
      <!-- ItemGroupDefs, ItemDefs, CodeListDefs, MethodDefs, ValueListDefs -->
    </MetaDataVersion>
  </Study>
</ODM>
```

---

## Core Metadata Elements

### Dataset (ItemGroupDef)
```xml
<ItemGroupDef OID="IG.DM" Name="DM" Domain="DM" Repeating="No"
              Purpose="Tabulation" KeyVariables="USUBJID">
  <Description><TranslatedText xml:lang="en">Demographics</TranslatedText></Description>
  <ItemRef ItemOID="IT.DM.STUDYID" OrderNumber="1" Mandatory="Yes"/>
  <!-- ... additional variable references -->
</ItemGroupDef>
```

### Variable (ItemDef)
```xml
<ItemDef OID="IT.DM.SEX" Name="SEX" DataType="text" Length="1" Mandatory="Yes">
  <Description><TranslatedText xml:lang="en">Sex</TranslatedText></Description>
  <CodeListRef CodeListOID="CL.SEX"/>
</ItemDef>
```

### Method (MethodDef)
```xml
<MethodDef OID="MT.USUBJID" Name="USUBJID Construction" Type="Computation">
  <Description><TranslatedText xml:lang="en">
    USUBJID = {study_id}-{SITEID}-{SUBJID}. Max 11 chars, alphanumeric with hyphens.
  </TranslatedText></Description>
</MethodDef>
```

---

## CT Reference Table (CDISC CT OIDs — must not be changed)

| Variable | Codelist | CDISC CT OID | Key Values |
|----------|----------|-------------|------------|
| SEX | Sex | **C66731** | M, F, U, UN |
| RACE | Race | **C74457** | WHITE, BLACK OR AFRICAN AMERICAN, ASIAN, OTHER, UNKNOWN |
| ETHNIC | Ethnicity | **C66790** | HISPANIC OR LATINO, NOT HISPANIC OR LATINO, NOT REPORTED, UNKNOWN |
| ARMCD | Arm Code | **C99073** | **DYNAMIC** from `study_config.treatment_arms` |
| AESEV | Severity | **C66769** | MILD, MODERATE, SEVERE |
| AESER/Yes-No | Yes/No | **C66763** | Y, N |
| COUNTRY | Country | ISO 3166 | **DYNAMIC** from `study_config.site_information` |
| DOMAIN | Domain Abbrev | **C66734** | **DYNAMIC** from `study_config.sdtm_domains` |
| AEOUT | Outcome | **C66770** | RECOVERED/RESOLVED, NOT RECOVERED/NOT RESOLVED, FATAL |
| AEACN | Action Taken | **C66767** | DRUG WITHDRAWN, DOSE REDUCED, DOSE NOT CHANGED |

### Example CodeListDef (SEX)
```xml
<CodeList OID="CL.SEX" Name="Sex" DataType="text">
  <CodeListItem CodedValue="M" OrderNumber="1">
    <Decode><TranslatedText>Male</TranslatedText></Decode>
  </CodeListItem>
  <!-- F, U, UN follow same pattern -->
  <Alias Name="C66731" Context="nci:ExtCodeID"/>
</CodeList>
```

### Dynamic CodeLists
- **ARMCD (C99073):** Generate `CodeListItem` entries from `study_config.treatment_arms` — each has `armcd` (code) and `arm` (decoded text). Do NOT hardcode.
- **COUNTRY (ISO 3166):** Generate `EnumeratedItem` entries from unique countries in `study_config.site_information`. Do NOT hardcode.
- **CT Package:** Set `<Include href="{ct_package_url}"/>` from study config. Document version from `ct_version`.

---

## Value-Level Metadata
```xml
<ValueListDef OID="VL.DM.ARM">
  <ItemRef ItemOID="IT.DM.ARM">
    <!-- GENERATED: For each arm in study_config.treatment_arms: -->
    <WhereClauseRef WhereClauseOID="WC.DM.ARM.{arm.armcd}"/>
  </ItemRef>
</ValueListDef>
<WhereClauseDef OID="WC.DM.ARM.{arm.armcd}">
  <RangeCheck ItemOID="IT.DM.ARMCD" Comparator="EQ">
    <CheckValue>{arm.armcd}</CheckValue>
  </RangeCheck>
</WhereClauseDef>
```

---

## Edge Cases
- **SUPPQUAL:** Document SUPPDM variables with QNAM/QVAL; reference via RELID/RELREC
- **Custom variables without CDISC CT:** Create study-specific CodeListDef with EnumeratedItem; do NOT assign a CDISC CT OID
- **Multi-source variables:** Use compound MethodDef referencing all source domains (e.g., SAFFL from DM+EX)
- **Missing treatment_arms or site_information:** Log error and abort — cannot generate ARMCD/COUNTRY CodeListDefs
- **Derivations:** AGE = floor((RFSTDTC - BRTHDAT) / 365.25); RFSTDTC = earliest EXSTDTC from EX domain

---

## Evaluation Criteria

**Mandatory:**
- All datasets/variables with correct data types; valid XML per Define.xml 2.1.0
- CT references with CDISC CT OIDs (C66731, C66734, C66763, C66769, C66770, C66790, C74457, C99073)
- MethodDefs for all derived variables; key variables identified per dataset
- ARMCD from `study_config.treatment_arms`, COUNTRY from `site_information`
- CT version from `ct_version`, Include href from `ct_package_url`, domains from `sdtm_domains`

**Recommended:** Value-level metadata, SUPPQUAL metadata, RELREC relationships, Comments for complex derivations

---

## Output Priority (prevent truncation)

When generating specs for **multiple datasets**, prioritize completeness over verbosity:
1. **ALL datasets + ALL variables first** — never truncate a variable table mid-row
2. Use compact variable tables: `Name | Label | Type | Length | CT Ref` (5 cols, not 9)
3. Reference CodeList OIDs inline (e.g., `CL.SEX (C66731)`) instead of separate CodeListDef section
4. Omit full XML markup — use specification tables instead
5. Include MethodDefs as a brief table, not individual XML blocks

---

## Critical Constraints

**Never:**
- Produce output without CT package version from study config
- Use placeholder OIDs — must reference real CDISC CT OIDs
- Skip required variables; generate invalid XML; ignore CDISC CT
- Use study-specific codes where CDISC CT exists
- Hardcode arm names, country codes, CT version, CT package URL, or domain list

**Always:**
- Validate inputs before processing; validate output XML against Define.xml 2.1.0 XSD
- Include CDISC CT OIDs for all coded variables; document derivation methods
- Generate ARMCD/COUNTRY/USUBJID dynamically from study config
- Set Include href from `study_config.ct_package_url`

---

## Example Usage
```bash
python csp-skills/layer-3-sdtm-qc/define-draft-builder/script.py \
  --input output/sdtm/ \
  --output output/define/define-sdtm-draft.xml \
  --study-config specs/study-config.yaml \
  --validate
```
