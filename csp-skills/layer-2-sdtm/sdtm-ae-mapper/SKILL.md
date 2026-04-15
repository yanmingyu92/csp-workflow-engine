---
name: sdtm-ae-mapper
description: Map adverse event data to SDTM AE domain with MedDRA coding. Triggers on "AE", "adverse event", "AETERM", "AEDECOD", "MedDRA".
version: "1.0"
user-invocable: true
context: fork
model: sonnet
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
argument-hint: "[options] -- --input <raw-data-file> --output <output-path> --spec <mapping-spec>"
---

## Runtime Configuration (Step 0)

### Study Config Resolution
```
1. Read ops/workflow-state.yaml for treatment arm definitions and study metadata
2. If missing, fall back to --study-config <path> from kwargs
3. If neither available, raise error: "Missing study config: abort; return {}"
4. Default: --study-config default
```

### Files to Read
- `ops/workflow-state.yaml` (study config, treatment arms)
- `--spec <mapping-spec>` (SDTM mapping specification)
- `--input <raw-data-file>` (raw adverse events source)

## EXECUTE NOW

Parse $ARGUMENTS: --input, --output, --spec, --study-config, --meddra, --validate, --dry-run
**START NOW.**

---

## Philosophy
**AE captures all safety signals.** Every adverse event from treatment exposure through end of study must be captured, coded with MedDRA, and structured per SDTM AE domain specification (SDTM IG v3.4). The AE domain is the most critical safety domain and feeds directly into ADAE for analysis.

**Key Principle:** AE mapping requires precise MedDRA coding hierarchy (PT -> HLT -> HLGT -> SOC) and complete temporal documentation (start/end dates relative to treatment).

---

## Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `--input` | Yes | Path to raw adverse events data file |
| `--output` | Yes | Output path for AE XPT file |
| `--spec` | Yes | Path to SDTM mapping specification YAML |
| `--study-config` | No | Path to study config (defaults to ops/workflow-state.yaml) |
| `--meddra` | No | Path to MedDRA dictionary file |
| `--validate` | No | Run validation after mapping |
| `--dry-run` | No | Show mappings without writing |

---

## Key Variables

| Variable | Required | Source | Derivation |
|----------|----------|--------|------------|
| STUDYID | Yes | study config | `{{study_id}}` from study config |
| DOMAIN | Yes | - | Fixed value: "AE" |
| USUBJID | Yes | Derived | Format: `{{study_id}}-{SITEID}-{SUBJID}` |
| AESEQ | Yes | Derived | Sequence number within subject |
| AESPID | No | RAW.AE | Sponsor-defined identifier |
| AETERM | Yes | RAW.AE | Verbatim adverse event term |
| AEDECOD | Yes | MedDRA | MedDRA preferred term (dictionary-derived) |
| AEBODSYS | Yes | MedDRA | MedDRA primary system organ class |
| AEHLT | No | MedDRA | MedDRA high-level term |
| AEHLGT | No | MedDRA | MedDRA high-level group term |
| AESOC | No | MedDRA | MedDRA primary SOC (same as AEBODSYS for primary path) |
| AESEV | Yes | RAW.AE | Severity mapped dynamically to CDISC CT C66769 |
| AESER | Yes | RAW.AE | Seriousness (Y/N) per CDISC CT C66763 |
| AESDTH | No | RAW.AE | Results in death (Y/N) |
| AESLIFE | No | RAW.AE | Is life-threatening (Y/N) |
| AESHOSP | No | RAW.AE | Requires hospitalization (Y/N) |
| AESDISAB | No | RAW.AE | Causes disability (Y/N) |
| AESCONG | No | RAW.AE | Congenital anomaly (Y/N) |
| AESMIE | No | RAW.AE | Other medically important event (Y/N) |
| AEACN | No | RAW.AE | Action taken with study treatment |
| AEACNOTH | No | RAW.AE | Other action taken |
| AEREL | No | RAW.AE | Causality assessment |
| AERELNST | No | RAW.AE | Relationship to non-study treatment |
| AEOUT | No | RAW.AE | Outcome of adverse event |
| AESTDTC | Yes | RAW.AE | Start date/time (ISO 8601) |
| AEENDTC | No | RAW.AE | End date/time (ISO 8601) |
| AESTDY | No | Derived | Study day of AE start |
| AEENDY | No | Derived | Study day of AE end |
| AEDUR | No | Derived | Duration of AE |
| AEENRF | No | Derived | End relative to reference period |
| AEENTPT | No | Derived | End reference time point |
| AETRTEM | No | Derived | Treatment-emergent flag (SDTM-level) |

---

## MedDRA Coding Hierarchy

### Coding Structure
```
SOC (System Organ Class)
  +-- HLGT (High-Level Group Term)
       +-- HLT (High-Level Term)
            +-- PT (Preferred Term) <- AEDECOD
                 +-- LLT (Lowest Level Term) <- AETERM maps here
```

### Coding Logic
```python
def meddra_code(aeterm, meddra_dictionary):
    """
    Map verbatim AE term to MedDRA coding hierarchy.

    1. Match AETERM to MedDRA LLT (Lowest Level Term)
    2. Derive PT (Preferred Term) = AEDECOD
    3. Derive HLT (High-Level Term) = AEHLT
    4. Derive HLGT (High-Level Group Term) = AEHLGT
    5. Derive SOC (System Organ Class) = AEBODSYS

    Uses primary SOC path for multi-SOC terms.
    """
    llt_match = meddra_dictionary.find_llt(aeterm)

    if llt_match:
        return {
            'AEDECOD': llt_match.pt,
            'AEHLT': llt_match.hlt,
            'AEHLGT': llt_match.hlgt,
            'AEBODSYS': llt_match.soc,  # Primary SOC
            'AESOC': llt_match.soc,
        }
    else:
        # Uncoded term -- flag for manual review
        log_warning(f"Uncoded AE term: {aeterm}")
        return {
            'AEDECOD': None,
            'AEHLT': None,
            'AEHLGT': None,
            'AEBODSYS': None,
            'AESOC': None,
        }
```

### MedDRA Version
```python
# Document the MedDRA version used for coding
# Must be specified in study config (ops/workflow-state.yaml or --study-config)
# Update if newer version required by regulatory authority
meddra_version = study_config.get('meddra_version', 'latest')
```

---

## CDISC Controlled Terminology

### AESEV (Severity) - CDISC CT C66769
| Raw Value | CDISC CT | Label |
|-----------|----------|-------|
| Mild, 1, MILD | MILD | Mild |
| Moderate, 2, MOD | MODERATE | Moderate |
| Severe, 3, SEV | SEVERE | Severe |

```python
# Severity mappings loaded dynamically from --spec; fallback defaults shown
sev_map = {
    'MILD': 'MILD', '1': 'MILD', 'M': 'MILD',
    'MODERATE': 'MODERATE', '2': 'MODERATE', 'MOD': 'MODERATE',
    'SEVERE': 'SEVERE', '3': 'SEVERE', 'SEV': 'SEVERE'
}

# Override with spec-provided mappings if available
if spec_sev_map:
    sev_map.update(spec_sev_map)
```

### AESER (Seriousness) - CDISC CT C66763
```python
# AESER = 'Y' if ANY serious criterion is met
# Serious criteria: AESDTH, AESLIFE, AESHOSP, AESDISAB, AESCONG, AESMIE
if any([AESDTH == 'Y', AESLIFE == 'Y', AESHOSP == 'Y',
        AESDISAB == 'Y', AESCONG == 'Y', AESMIE == 'Y']):
    AESER = 'Y'
else:
    AESER = 'N'
```

### AEACN (Action Taken) - CDISC CT C66767
| Raw Value | CDISC CT | Label |
|-----------|----------|-------|
| Dose Reduced | DOSE REDUCED | Dose Reduced |
| Dose Not Changed | DOSE NOT CHANGED | Dose Not Changed |
| Drug Withdrawn | DRUG WITHDRAWN | Drug Withdrawn |
| Dose Increased | DOSE INCREASED | Dose Increased |
| Not Applicable | NOT APPLICABLE | Not Applicable |

### AEOUT (Outcome) - CDISC CT C66770
| Raw Value | CDISC CT | Label |
|-----------|----------|-------|
| Recovered/Resolved | RECOVERED/RESOLVED | Recovered/Resolved |
| Not Recovered/Not Resolved | NOT RECOVERED/NOT RESOLVED | Not Recovered/Not Resolved |
| Fatal | FATAL | Fatal |
| Recovered/Resolved with Sequelae | RECOVERED/RESOLVED WITH SEQUELAE | Recovered/Resolved with Sequelae |
| Unknown | UNKNOWN | Unknown |

---

## Date Derivation

### AESTDTC / AEENDTC (ISO 8601)
```python
def format_ae_dates(raw_start, raw_end):
    """
    Format AE dates to ISO 8601.

    Partial date handling:
    - "2024-03-15" -> "2024-03-15"
    - "2024-03"    -> "2024-03"  (preserve partial)
    - "2024"       -> "2024"     (preserve partial)
    - null         -> ""         (missing date)
    """
    aestdtc = format_iso_date(raw_start) if raw_start else ""
    aeendtc = format_iso_date(raw_end) if raw_end else ""
    return aestdtc, aeendtc
```

### AESTDY / AEENDY (Study Days)
```python
def derive_study_days(aestdtc, aeendtc, rfstdtc):
    """
    Study day relative to reference start date (RFSTDTC from DM).

    AESTDY = (AESTDTC - RFSTDTC) + 1
    If AESTDTC < RFSTDTC: negative study day
    Partial dates: use imputed date for calculation

    AEENDY = (AEENDTC - RFSTDTC) + 1
    """
    if aestdtc and rfstdtc:
        aestdy = (parse_iso_date(aestdtc) - parse_iso_date(rfstdtc)).days + 1
    else:
        aestdy = None

    if aeendtc and rfstdtc:
        aeendy = (parse_iso_date(aeendtc) - parse_iso_date(rfstdtc)).days + 1
    else:
        aeendy = None

    return aestdy, aeendy
```

---

## AESEQ Derivation

```python
def derive_aeseq(ae_dataset):
    """
    Derive AESEQ: sequential number within each subject.

    AESEQ = 1, 2, 3, ... per USUBJID
    Ordered by AESTDTC (earliest first), then AETERM alphabetically.
    """
    ae_dataset = ae_dataset.sort_values(['USUBJID', 'AESTDTC', 'AETERM'])
    ae_dataset['AESEQ'] = ae_dataset.groupby('USUBJID').cumcount() + 1
    return ae_dataset
```

---

## Output Schema

```yaml
ae_domain:
  name: AE
  label: "Adverse Events"
  class: "Events"
  structure: "One record per adverse event per subject per start date"
  key_variables: ["STUDYID", "USUBJID", "AESEQ"]

  variables:
    - name: STUDYID
      type: Char(12)
      label: "Study Identifier"
      required: true
    - name: DOMAIN
      type: Char(2)
      label: "Domain Abbreviation"
      required: true
    - name: USUBJID
      type: Char(11)
      label: "Unique Subject Identifier"
      required: true
    - name: AESEQ
      type: Num
      label: "Sequence Number"
      required: true
    - name: AETERM
      type: Char(200)
      label: "Reported Term for the Adverse Event"
      required: true
    - name: AEDECOD
      type: Char(100)
      label: "Dictionary-Derived Term"
      required: true
    - name: AEBODSYS
      type: Char(100)
      label: "Body System or Organ Class"
      required: true
    - name: AESEV
      type: Char(10)
      label: "Severity/Intensity"
      required: true
    - name: AESER
      type: Char(1)
      label: "Serious Event"
      required: true
    - name: AESTDTC
      type: Char(20)
      label: "Start Date/Time of Adverse Event"
      required: false
    - name: AEENDTC
      type: Char(20)
      label: "End Date/Time of Adverse Event"
      required: false
    - name: AEACN
      type: Char(30)
      label: "Action Taken with Study Treatment"
      required: false
    - name: AEREL
      type: Char(30)
      label: "Causality"
      required: false
    - name: AEOUT
      type: Char(40)
      label: "Outcome of Adverse Event"
      required: false
```

---

## Edge Cases

### Partial Dates
```python
# AESTDTC = "2024-03" (missing day):
#   Preserve as "2024-03" in SDTM (do NOT impute at SDTM level)
#   Imputation happens at ADaM level (ADAE.ASTDT)
# AESTDTC = "2024" (missing month and day):
#   Preserve as "2024" in SDTM
# AESTDTC = null (completely missing):
#   Leave empty string, document in data issues
```

### Missing MedDRA Coding
```python
# AETERM provided but no AEDECOD:
# - Flag as uncoded -- requires manual MedDRA coding
# - Do NOT leave AETERM blank
# - Do NOT auto-assign AEDECOD without dictionary lookup
# - Log for MedDRA coder review
```

### Multiple AEs Same Day
```python
# Subject reports multiple AEs on same start date:
# - Each gets a separate AESEQ
# - Order by AETERM alphabetically
# - All remain in dataset (no deduplication)
```

### Continuing AEs (No End Date)
```python
# AEENDTC is null:
# - Event may be ongoing at data cutoff
# - AEOUT may be "NOT RECOVERED/NOT RESOLVED"
# - AEDUR should be null (cannot calculate without end date)
```

### Pre-Treatment AEs
```python
# AE start date before first dose (AESTDTC < RFSTDTC):
# - Include in AE domain
# - AESTDY will be negative (or zero)
# - Treatment-emergent flag (AETRTEM) = 'N'
```

---

## Integration Points

### Upstream Skills
- `/study-setup` -- Study configuration, treatment definitions
- `/data-validator` -- Raw AE data validation before mapping

### Downstream Skills
- `/adam-adae-builder` -- ADAE analysis dataset from AE
- `/sdtm-validator` -- Validate AE domain output
- `/define-draft-builder` -- AE metadata for Define.xml
- `/p21-validator` -- P21 compliance check

### Related Skills
- `/sdtm-supp-builder` -- Supplemental qualifiers for AE
- `/sdtm-relrec-builder` -- AE relationships to other domains
- `/data-quality` -- Check AE data completeness

---

## P21 Validation -- Common AE Failures

| Rule ID | Message | How to Avoid |
|---------|---------|--------------|
| SD0001 | AETERM is missing | Always populate verbatim term |
| SD0002 | AEDECOD is missing | Complete MedDRA coding before output |
| SD0003 | AEBODSYS is missing | Derive from MedDRA hierarchy |
| SD1001 | AESER inconsistent with seriousness criteria | AESER='Y' iff any criterion='Y' |
| SD0051 | AESTDTC format invalid | Use ISO 8601 format |
| SD0053 | AEENDTC before AESTDTC | Validate date logic |

---

## Evaluation Criteria

**Mandatory:**
- All AE records coded with MedDRA PT (AEDECOD) and SOC (AEBODSYS)
- AESEQ unique within each subject
- USUBJID matches DM domain
- Dates in ISO 8601 format
- AESER consistent with seriousness criteria flags

**Recommended:**
- Complete MedDRA hierarchy (PT, HLT, HLGT, SOC)
- Study days derived for all records with valid dates
- Treatment-emergent flag derived
- Severity mapping complete

---

## Critical Constraints

**Never:**
- Auto-assign MedDRA coding without dictionary lookup
- Leave AETERM blank
- Deduplicate AE records without source verification
- Use non-CDISC controlled terminology
- Proceed if raw AE data is missing or empty
- Modify verbatim terms (AETERM must match source exactly)
- Proceed if study config is missing (raise error and abort)

**Always:**
- Resolve study config from `ops/workflow-state.yaml` or `--study-config`
- Map AESEV dynamically to CDISC CT C66769
- Derive AESER from individual seriousness criteria
- Validate USUBJID against DM domain
- Document MedDRA version used for coding
- Generate traceable, reproducible results

---

## Examples

### Basic Usage
```bash
# Input and output paths are argument-driven, not hardcoded
--input <raw-data-file> --output <output-path> --spec <mapping-spec>
```

### With MedDRA Dictionary
```bash
--input <raw-data-file> --output <output-path> --spec <mapping-spec> --meddra <meddra-dict-path> --validate
```

### With Explicit Study Config
```bash
--input <raw-data-file> --output <output-path> --spec <mapping-spec> --study-config ops/workflow-state.yaml
```

### Expected Output Record (dynamic values from study config)
```
USUBJID: {{study_id}}-{SITEID}-{SUBJID}
DOMAIN: AE
AESEQ: {seq}
AETERM: {verbatim_term}
AEDECOD: {meddra_pt}
AEBODSYS: {meddra_soc}
AESEV: {severity}
AESER: {seriousness}
AESTDTC: {start_date}
AEENDTC: {end_date}
AEACN: {action_taken}
AEREL: {causality}
AEOUT: {outcome}
```
