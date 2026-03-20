# Define.xml Guide

## Purpose
Supports Layer 3/6 nodes: **sdtm-define-draft**, **define-xml-sdtm**, **define-xml-adam**, **define-xml-validation**.

## Regulatory Basis
- **CDISC Define-XML v2.1**: Metadata standard for study data
- **FDA Study Data Technical Conformance Guide**: Requires Define.xml with all submissions

## Define.xml Structure

### Top-Level Elements
```xml
<ODM>
  <Study>
    <GlobalVariables/>      <!-- Study name, description, protocol -->
    <MetaDataVersion>
      <def:Standards/>      <!-- SDTM IG, ADaM IG, CT versions -->
      <ItemGroupDef/>       <!-- Dataset definitions -->
      <ItemDef/>            <!-- Variable definitions -->
      <CodeList/>           <!-- Controlled terminology -->
      <MethodDef/>          <!-- Computational algorithms -->
      <def:CommentDef/>     <!-- Comments and documentation -->
      <def:leaf/>           <!-- External document references -->
    </MetaDataVersion>
  </Study>
</ODM>
```

### Dataset Metadata (ItemGroupDef)
For each dataset (.xpt file):
| Attribute | Description | Example |
|-----------|-------------|---------|
| Name | Dataset name | "DM" |
| SASDatasetName | SAS name (≤8 chars) | "DM" |
| Domain | CDISC domain | "DM" |
| Purpose | "Tabulation" or "Analysis" | "Tabulation" |
| Structure | Record structure | "One record per subject" |
| Label | Dataset label | "Demographics" |
| Location | File path | "dm.xpt" |

### Variable Metadata (ItemDef)
For each variable:
| Attribute | Description |
|-----------|-------------|
| Name | Variable name |
| Label | Variable label (≤40 chars for SDTM) |
| DataType | text, integer, float, date, datetime |
| Length | Variable length |
| Origin | CRF, Derived, Assigned, Protocol, Predecessor |
| Role | Identifier, Topic, Qualifier, etc. |
| Comment | Documentation reference |
| CodeList | Reference to controlled terminology |

### Computational Methods (MethodDef)
For derived variables, document the algorithm:
```
Method: Derivation of AGE
Type: Computation
Description: AGE = floor((RFSTDTC - BRTHDTC) / 365.25)
             AGEU = "YEARS"
```

### Value-Level Metadata (def:ValueListDef)
For BDS ADaM datasets where derivation depends on parameter:
- Different derivation methods per PARAMCD
- Only required for ADaM, not SDTM

## SDTM vs ADaM Define.xml Differences

| Aspect | SDTM Define | ADaM Define |
|--------|-------------|-------------|
| Purpose | "Tabulation" | "Analysis" |
| Label length | ≤40 chars | ≤200 chars |
| Origin | CRF, Derived, Assigned | Predecessor, Derived, Assigned |
| Value-level metadata | Rarely used | Required for BDS |
| Where clauses | Rare | Common for parameter-level |

## Validation
- Schema validation against Define-XML v2.1 XSD
- Controlled terminology references must resolve
- All datasets and variables in data must be documented
- All hyperlinks must be functional
- Stylesheet rendering check (visual review)

## Quality Criteria
- Schema-valid against Define-XML v2.1
- All datasets and variables documented
- Controlled terminology references valid
- Renders correctly in stylesheet
- All hyperlinks functional
