---
name: sdtm-dm-mapper
description: Map raw demographics data to SDTM DM domain per CDISC SDTM IG v3.4. Triggers on "DM", "demographics", "USUBJID", "AGE", "SEX", "RACE".
version: "3.0"
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
- `--input <raw-data-file>` (raw demographics source)

## EXECUTE NOW

Parse $ARGUMENTS: --input, --output, --spec, --study-config, --validate, --dry-run

**START NOW.**

---

## Philosophy

**DM is the anchor domain.** Every subject in a clinical trial must have exactly one DM record. USUBJID uniquely identifies subjects across all domains. Treatment arm, study reference dates, and demographic characteristics flow from DM to all downstream analyses.

**Key Principle:** DM mapping requires precise CDISC controlled terminology application. The mapper must enhance, not displace, Claude's built-in CDISC knowledge with specific study mappings.

---

## Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `--input` | Yes | Path to raw demographics data file |
| `--output` | Yes | Output path for DM XPT file |
| `--spec` | Yes | Path to SDTM mapping specification YAML |
| `--study-config` | No | Path to study config (defaults to ops/workflow-state.yaml) |
| `--validate` | No | Run validation after mapping |
| `--dry-run` | No | Show mappings without writing |

---

## Key Variables

| Variable | Required | Source | Derivation |
|----------|----------|--------|------------|
| STUDYID | Yes | study config | `{{study_id}}` from study config |
| DOMAIN | Yes | - | Fixed value: "DM" |
| USUBJID | Yes | Assigned | Sponsor-defined stable identifier, unique within the submission and consistent across all domains |
| SUBJID | Yes | RAW.DM | Subject identifier within site |
| SITEID | Yes | RAW.DM | Site identifier |
| AGE | Conditional | Source/Derived | Age at the protocol-defined reference date, only when sufficient source precision exists |
| AGEU | Conditional | Source/Assigned | Unit paired with AGE using the pinned CDISC CT package |
| SEX | Yes | RAW.DM | Map dynamically to CDISC CT C66731 |
| RACE | Yes | RAW.DM | Map dynamically to CDISC CT C74457 |
| ETHNIC | No | RAW.DM | Map dynamically to CDISC CT C66790 |
| ARM | Yes | study config | From `study_config['treatment_arms']` |
| ARMCD | Conditional | study config | Sponsor-defined planned-arm code from the approved trial design; never synthesize by truncating ARM |
| ACTARM | No | RAW.DM | Actual treatment arm (if different) |
| ACTARMCD | No | Derived | 8-character actual arm code |
| RFSTDTC | No | Derived | First exposure date (ISO 8601) |
| RFENDTC | No | Derived | Last exposure date (ISO 8601) |
| COUNTRY | Yes | RAW.DM | ISO 3166-1 alpha-3 code |
| DMDTC | No | RAW.DM | Date of demographics collection |
| DMDY | No | Derived | Study day of demographics |

---

## USUBJID Construction

**Format:** `{{study_id}}-{SITEID}-{SUBJID}`

```python
# STUDYID resolved dynamically from study config
STUDYID = study_config['study_id']  # e.g., from ops/workflow-state.yaml
SITEID = raw_dm['SITE']             # from input data
SUBJID = raw_dm['SUBJID']           # from input data

USUBJID = assign_from_approved_subject_id_algorithm(
    study_id=STUDYID,
    site_id=SITEID,
    subject_id=SUBJID,
)
```

**Validation Rules:**
- Use the sponsor-defined length needed by the delivered metadata; there is no
  universal 11-character SDTM limit
- Avoid embedding directly identifying information
- Must be unique across all subjects
- Must remain byte-for-byte consistent for the subject across all domains

---

## CDISC Controlled Terminology Tables

### SEX (CDISC CT C66731)
| Raw Value | CDISC CT | Code | Label |
|-----------|----------|------|-------|
| M, Male, 1, MALE | M | M | Male |
| F, Female, 2, FEMALE | F | F | Female |
| U, Unknown, 0, UNKNOWN | U | U | Unknown |
| UN, Undifferentiated | UN | UN | Undifferentiated |

**Dynamic Mapping Logic:**
```python
# Load CT mappings dynamically from --spec or CDISC CT publication
# The map below is a fallback when no spec-provided mapping exists

sex_map = {
    'M': 'M', 'MALE': 'M', '1': 'M',
    'F': 'F', 'FEMALE': 'F', '2': 'F',
    'U': 'U', 'UNKNOWN': 'U', '0': 'U',
    'UN': 'UN', 'UNDIFFERENTIATED': 'UN'
}

# Override with spec-provided mappings if available
if spec_sex_map:
    sex_map.update(spec_sex_map)

SEX = sex_map.get(raw_sex.upper().strip(), 'U')
```

### RACE (CDISC CT C74457)
| Raw Value | CDISC CT | Label |
|-----------|----------|-------|
| WHITE, 1, W | WHITE | White |
| BLACK OR AFRICAN AMERICAN, BLACK, 2 | BLACK OR AFRICAN AMERICAN | Black or African American |
| ASIAN, 3, A | ASIAN | Asian |
| AMERICAN INDIAN..., AIAN, 4 | AMERICAN INDIAN OR ALASKA NATIVE | American Indian or Alaska Native |
| NATIVE HAWAIIAN..., NHPI, 5 | NATIVE HAWAIIAN OR OTHER PACIFIC ISLANDER | Native Hawaiian or Other Pacific Islander |
| MULTIPLE, MULTIRACIAL, 6 | MULTIPLE | Multiple |
| OTHER, 7 | OTHER | Other |
| UNKNOWN, UNK, 9 | UNKNOWN | Unknown |

**Dynamic Mapping Logic:**
```python
# Race mappings loaded dynamically; fallback defaults shown
race_map = {
    'WHITE': 'WHITE', '1': 'WHITE', 'W': 'WHITE',
    'BLACK': 'BLACK OR AFRICAN AMERICAN', '2': 'BLACK OR AFRICAN AMERICAN',
    'BLACK OR AFRICAN AMERICAN': 'BLACK OR AFRICAN AMERICAN',
    'ASIAN': 'ASIAN', '3': 'ASIAN', 'A': 'ASIAN',
    'AMERICAN INDIAN OR ALASKA NATIVE': 'AMERICAN INDIAN OR ALASKA NATIVE',
    'NATIVE HAWAIIAN OR OTHER PACIFIC ISLANDER': 'NATIVE HAWAIIAN OR OTHER PACIFIC ISLANDER',
    'MULTIPLE': 'MULTIPLE', 'MULTIRACIAL': 'MULTIPLE',
    'OTHER': 'OTHER', '7': 'OTHER',
    'UNKNOWN': 'UNKNOWN', '9': 'UNKNOWN'
}

# Override with spec-provided mappings if available
if spec_race_map:
    race_map.update(spec_race_map)
```

### ETHNIC (CDISC CT C66790)
| Raw Value | CDISC CT | Label |
|-----------|----------|-------|
| HISPANIC, HISPANIC OR LATINO, 1 | HISPANIC OR LATINO | Hispanic or Latino |
| NOT HISPANIC, NOT HISPANIC OR LATINO, 2 | NOT HISPANIC OR LATINO | Not Hispanic or Latino |
| NOT REPORTED, 3 | NOT REPORTED | Not Reported |
| UNKNOWN, 4 | UNKNOWN | Unknown |

---

## AGE Derivation Logic

```python
from datetime import date

def calculate_age(birth_date, reference_date):
    """
    Calculate age in years from birth date to reference date.

    Args:
        birth_date: datetime.date or ISO 8601 string
        reference_date: datetime.date or ISO 8601 string (typically RFSTDTC)

    Returns:
        int: Age in complete years
    """
    if isinstance(birth_date, str):
        birth_date = parse_iso_date(birth_date)
    if isinstance(reference_date, str):
        reference_date = parse_iso_date(reference_date)

    # Calculate age in years
    age = reference_date.year - birth_date.year

    # Adjust if birthday hasn't occurred yet this year
    if (reference_date.month, reference_date.day) < (birth_date.month, birth_date.day):
        age -= 1

    # Validate range (typically 18-100 for adult trials)
    if age < 0 or age > 120:
        log_warning(f"Age {age} outside expected range")

    return age

# Derivation
AGE, AGEU = derive_age_only_when_source_precision_supports_it(
    BRTHDAT,
    protocol_reference_date,
    source_age,
    source_age_unit,
)
```

---

## ARM/ARMCD Derivation

### ARM Mapping (Dynamic from Study Config)

ARM values are read dynamically from `study_config['treatment_arms']` resolved via:
1. `ops/workflow-state.yaml` (preferred)
2. `--study-config <path>` (fallback)

```python
# ARM/ARMCD derived dynamically from study config — no hardcoded arm names
# study_config['treatment_arms'] provides the mapping table at runtime
#
# Example structure in ops/workflow-state.yaml:
#   treatment_arms:
#     - name: "Placebo"
#       code: "Pbo"
#     - name: "<Treatment A>"
#       code: "<ArmCode1>"
#     - name: "<Treatment B>"
#       code: "<ArmCode2>"
#     - name: "Screen Failure"
#       code: "Scrnfail"
```

### ARMCD Rules (Approved Trial-Design Mapping)
```python
def derive_armcd(arm_text, study_config):
    """
    Resolve ARMCD from the approved trial-design mapping.

    Rules:
    1. Use the exact sponsor-defined code from the approved specification
    2. Preserve stable meaning across DM, TA, and downstream metadata
    3. Do not generate a fallback by truncating ARM text
    """
    # Load arm mappings dynamically from study config
    armcd_map = {}
    for arm in study_config.get('treatment_arms', []):
        armcd_map[arm['name']] = arm['code']

    # Check explicit mapping first
    for key, code in armcd_map.items():
        if key.lower() in arm_text.lower():
            return code

    raise ValueError(f"No approved ARMCD mapping for {arm_text!r}")
```

---

## Reference Date Derivation (RFSTDTC, RFENDTC)

```python
def derive_reference_dates(usubjid, ex_dataset):
    """
    Derive RFSTDTC (first exposure) and RFENDTC (last exposure) from EX domain.

    RFSTDTC = earliest EXSTDTC for subject
    RFENDTC = latest EXENDTC for subject
    """
    subject_ex = ex_dataset[ex_dataset['USUBJID'] == usubjid]

    if len(subject_ex) == 0:
        log_warning(f"No EX records for {usubjid}")
        return None, None

    rfstdtc = subject_ex['EXSTDTC'].min()
    rfendtc = subject_ex['EXENDTC'].max()

    return rfstdtc, rfendtc
```

---

## Output Schema

```yaml
dm_domain:
  name: DM
  label: Demographics
  variables:
    - name: STUDYID
      type: Char(8)
      label: Study Identifier
      required: true
    - name: DOMAIN
      type: Char(2)
      label: Domain Abbreviation
      required: true
    - name: USUBJID
      type: Char(11)
      label: Unique Subject Identifier
      required: true
      key: true
    - name: SUBJID
      type: Char(8)
      label: Subject Identifier for the Study
      required: true
    - name: SITEID
      type: Char(8)
      label: Study Site Identifier
      required: true
    - name: AGE
      type: Num
      label: Age
      required: true
    - name: AGEU
      type: Char(5)
      label: Age Units
      required: true
    - name: SEX
      type: Char(1)
      label: Sex
      required: true
    - name: RACE
      type: Char(40)
      label: Race
      required: true
    - name: ETHNIC
      type: Char(22)
      label: Ethnicity
      required: false
    - name: ARM
      type: Char(40)
      label: Description of Planned Arm
      required: true
    - name: ARMCD
      type: Char(8)
      label: Planned Arm Code
      required: true
    - name: ACTARM
      type: Char(40)
      label: Description of Actual Arm
      required: false
    - name: ACTARMCD
      type: Char(8)
      label: Actual Arm Code
      required: false
    - name: COUNTRY
      type: Char(3)
      label: Country
      required: true
    - name: RFSTDTC
      type: Char(10)
      label: Subject Reference Start Date
      required: false
    - name: RFENDTC
      type: Char(10)
      label: Subject Reference End Date
      required: false
```

---

## Edge Cases

### Missing BRTHDAT
```python
if BRTHDAT is missing:
    # Use pre-calculated age from raw data if available
    if 'AGE' in raw_dm.columns:
        AGE = raw_dm['AGE']
    else:
        AGE = None
        log_warning(f"Cannot calculate AGE for {USUBJID}: BRTHDAT missing")
```

### Screen Failures
```python
# Screen failure code is dynamic from study_config, not hardcoded
screen_fail_code = get_screen_fail_code(study_config)  # e.g., 'Scrnfail'
if ARMCD == screen_fail_code:
    # Screen failures typically have:
    # - No EX records (RFSTDTC/RFENDTC = null)
    # - ARM from study_config['treatment_arms']
    # - Exclude from efficacy analyses
    RFSTDTC = None
    RFENDTC = None
```

### Multiple Races
```python
if multiple_race_values:
    # If subject reported multiple races
    RACE = "MULTIPLE"
    # Document original values in SUPPDM if needed
```

---

## Integration Points

### Upstream Skills
- `/study-setup` -- Study configuration, treatment arm definitions
- `/data-validator` -- Raw data validation before mapping

### Downstream Skills
- `/sdtm-validator` -- Validate DM domain output
- `/sdtm-ex-mapper` -- Requires USUBJID from DM
- `/adam-adsl-builder` -- Source for subject-level analysis

### Related Skills
- `/sdtm-supp-builder` -- Supplemental qualifiers for DM
- `/define-draft-builder` -- DM metadata for Define.xml
- `/p21-validator` -- P21 compliance check

---

## Evaluation Criteria

**Mandatory:**
- All required DM variables present per SDTM IG v3.4
- USUBJID uniquely identifies each subject (no duplicates)
- Controlled terminology matches CDISC CT exactly
- AGE is integer in valid range (0-120)
- ARMCD matches the approved trial-design specification exactly

**Recommended:**
- P21 validation returns 0 errors
- All subjects have ARM populated
- RFSTDTC/RFENDTC derived for non-screen failures
- No orphan subjects (all USUBJIDs exist in EX)

---

## Critical Constraints

**Never:**
- Create duplicate USUBJIDs
- Allow missing STUDYID, DOMAIN, USUBJID
- Use non-CDISC controlled terminology for SEX, RACE, ETHNIC
- Hardcode treatment arm names or ARMCD values
- Truncate ARMCD without documentation
- Proceed if raw data is missing or empty
- Proceed if study config is missing (raise error and abort)
- Skip validation of derived variables

**Always:**
- Resolve study config from `ops/workflow-state.yaml` or `--study-config`
- Read treatment arms dynamically from study config
- Validate controlled terminology before output
- Check for orphan subjects (no matching records in EX)
- Document any mapped values that differ from source
- Log all mapping decisions and deviations
- Generate traceable, reproducible results

---

## Audited Derivation and Version Constraints (V7-RS-SDTM-DM-2026-07)

### Edge Cases

- Never truncate `USUBJID` to 11 characters and never regenerate it separately
  by domain. Assign it once under a sponsor-controlled algorithm and verify exact
  cross-domain consistency.
- When a birth date or reference date is partial, do not manufacture a complete
  date to derive SDTM `AGE`. Use a collected age when appropriate or leave AGE
  missing and document the limitation. Do not divide day counts by 365.25.
- Derive study day only from complete dates. The SDTM rule has no day zero:
  `--DY = date - RFSTDTC + 1` on/after RFSTDTC and
  `--DY = date - RFSTDTC` before RFSTDTC.
- `ARMCD`, `ARM`, `ACTARMCD`, and `ACTARM` follow the approved trial design and
  subject path. Planned and actual arm values are not inferred from free text.

### Validation

1. Verify one DM record per submitted subject and exact `USUBJID` consistency.
2. Verify `ARMCD`/`ARM` against the pinned TA/TE trial-design metadata.
3. Verify CT values against the pinned CT package date, not an unversioned list.
4. Record source-field, mapping-spec version, CT package, and transformation hash
   for each derived/assigned field.

---

## Examples

### Basic Usage
```bash
# Input and output paths are argument-driven, not hardcoded
--input <raw-data-file> --output <output-path> --spec <mapping-spec>
```

### With Validation
```bash
--input <raw-data-file> --output <output-path> --spec <mapping-spec> --validate
```

### With Explicit Study Config
```bash
--input <raw-data-file> --output <output-path> --spec <mapping-spec> --study-config ops/workflow-state.yaml
```

### Expected Output Record (dynamic values from study config)
```
USUBJID: {{study_id}}-{SITEID}-{SUBJID}
DOMAIN: DM
SUBJID: {SUBJID}
SITEID: {SITEID}
AGE: {age}
AGEU: YEARS
SEX: {sex_cd}
RACE: {race_cd}
ETHNIC: {ethnic_cd}
ARM: {arm_name}                    # from study_config['treatment_arms']
ARMCD: {arm_code}                  # derived dynamically from study config
COUNTRY: {country_code}
RFSTDTC: {rfstdtc}
RFENDTC: {rfendtc}
```
