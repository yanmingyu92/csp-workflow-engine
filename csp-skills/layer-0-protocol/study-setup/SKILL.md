---
name: study-setup
description: Configure study-level metadata including study ID, phase, treatment arms, visit schedule, and randomization. Triggers on "study setup", "protocol", "study ID", "treatment arms", "visit schedule".
version: "1.0"
user-invocable: true
context: fork
model: sonnet
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
argument-hint: "[options] -- --input <protocol-file> --output <output-path> --validate --dry-run"
---

## Runtime Configuration

### Config Resolution
1. Read ops/workflow-state.yaml for current workflow state
2. Read specs/study-config.yaml for study metadata (if exists)
3. If study-config missing, fall back to --study-config <path> argument
4. If neither available, log error and abort

### Required Reads
- ops/workflow-state.yaml -- Current workflow state
- Protocol document (via --input argument)

### Arguments
| Argument | Required | Description |
|----------|----------|-------------|
| `--input` | Yes | Path to protocol document (PDF, DOCX, MD) |
| `--output` | Yes | Output path for study-config.yaml |
| `--study-config` | No | Path to existing study config for update |
| `--validate` | No | Validate extracted content |
| `--dry-run` | No | Show what would be extracted without writing |

---

## Philosophy

**Study configuration is the foundation.** All downstream work depends on accurate study metadata: treatment arms, visit windows, and population definitions flow from this configuration to SDTM, ADaM, and TFL.

**Key Principle:** Study configuration should be extracted once from the protocol/SAP and stored as a single source of truth. All downstream skills reference this configuration rather than re-extracting from source documents.

---

## Input/Output Specification

### Inputs (from regulatory-graph.yaml node schema: protocol-setup)
| Input | Type | Format | Required | Source |
|-------|------|--------|----------|--------|
| Study protocol | document | pdf, docx, md | Yes | User-provided via --input |
| Workflow state | metadata | yaml | No | ops/workflow-state.yaml |

### Outputs (to regulatory-graph.yaml node schema: protocol-setup)
| Output | Type | Format | Path Pattern |
|--------|------|--------|-------------|
| Study configuration | specification | yaml | specs/study-config.yaml |
| Treatment arm details | specification | yaml | specs/treatment-arms.yaml |
| Visit schedule | specification | yaml | specs/visit-schedule.yaml |
| Population definitions | specification | yaml | specs/populations.yaml |

---

## Extraction Targets

### Study Identification
- **STUDYID**: Protocol study identifier (e.g., "{study_id} from study config")
- **STUDYTITLE**: Full study title ("{study_title}")
- **INDICATION**: Disease or condition being studied
- **PHASE**: Trial phase (I, II, III, II/III)

### Treatment Arms
- **ARMLIST**: List of treatment arms with descriptions (read from study_config.treatment_arms)
- **RANDOMIZATION**: Randomization ratio ("{randomization_ratio}")
- **STRATFACT**: Stratification factors

### Visit Schedule
- **VISITS**: Visit names and windows ("{visit_name}", "{visit_window}")
- **VISITNUM**: Visit numbers
- **VISITDY**: Study day of visits

### Population Definitions
- **ITTDEF**: Intent-to-treat population definition
- **SAFDEF**: Safety population definition
- **PPDEF**: Per-protocol population definition

---

## Output Schema

```yaml
# specs/study-config.yaml
schema_version: "1.0"
extraction_date: "{extraction_date}"
source_document: "{source_document}"

study_identification:
  studyid: "{study_id} from study config"
  study_title: "{study_title}"
  indication: "{indication}"
  phase: "{phase}"
  sponsor: "{sponsor}"

treatment_arms:
  # Read ARMCD mappings from study_config.treatment_arms
  - arm: "{arm_name}"
    armcd: "{armcd}"
    description: "{arm_description}"
    dose: "{dose}"
    route: "{route}"

randomization:
  ratio: "{randomization_ratio}"
  method: "{randomization_method}"
  stratification_factors:
    - "Age group (<{age_cutoff} from study config, >={age_cutoff} from study config)"
    - "{stratification_factor}"

visit_schedule:
  - visit: "{visit_name}"
    visitnum: "{visit_number}"
    window_days: "{visit_window}"
    visitdy: "{visit_study_day}"
  # ... additional visits per protocol

population_definitions:
  itt:
    definition: "{itt_definition}"
    flag_variable: "ITTFL"
    derivation: "{itt_derivation}"
  safety:
    definition: "{safety_definition}"
    flag_variable: "SAFFL"
    derivation: "{safety_derivation}"
  per_protocol:
    definition: "{pp_definition}"
    flag_variable: "PPROTFL"
    derivation: "{pp_derivation}"

reference_dates:
  first_dose_reference: "{first_dose_reference}"
  last_dose_reference: "{last_dose_reference}"
  study_start_date: "{study_start_date}"

target_enrollment: "{target_enrollment}"
target_completion: "{target_completion}"
treatment_duration_weeks: "{treatment_duration_weeks}"
```

---

## Treatment Arm Derivation

### ARM to ARMCD Mapping
Read ARMCD mappings from study_config.treatment_arms.

**Derivation Rules:**
1. Maximum 8 characters, alphanumeric only
2. Preserve recognizable abbreviation of treatment name
3. Use underscore for multi-word treatments
4. Document mapping in study-config.yaml

---

## Visit Schedule Derivation

### Standard Visit Structure
```yaml
visit_schedule:
  - visit: "{visit_name}"
    visitnum: "{visit_number}"  # Sequential number
    window_days: "{visit_window}"  # Days from previous visit
    visitdy: "{visit_study_day}"  # Study day (cumulative)
    required: true  # Is visit required?
```

### Visit Day Calculation
```python
def calculate_visitdy(visitnum, visit_schedule):
    """
    Calculate study day (VISITDY) for each visit.

    VISITDY = cumulative days from Day 1 (first dose)
    """
    cumulative_days = 1  # Day 1 = first dose
    for visit in visit_schedule:
        if visit.visitnum == 1:
            visit.visitdy = None  # Screening has no study day
        elif visit.visitnum == 2:
            visit.visitdy = 1  # Baseline = Day 1
        else:
            cumulative_days += visit.window_days
            visit.visitdy = cumulative_days
    return visit_schedule
```

---

## Population Flag Derivation

### Population Definitions Reference
| Population | Flag Variable | Definition |
|------------|---------------|------------|
| Intent-to-Treat | ITTFL | All randomized subjects |
| Safety | SAFFL | Received >=1 dose of study drug |
| Per-Protocol | PPROTFL | Completed without major violations |
| Efficacy | EFFFL | ITT + minimum efficacy data |
| mITT | MITTFL | ITT with major deviations excluded |

### Derivation Logic
```python
# Safety Population
SAFFL = 'Y' if (RANDFL == 'Y' and EX.EXDOSE > 0) else 'N'

# Intent-to-Treat
ITTFL = 'Y' if RANDFL == 'Y' else 'N'

# Per-Protocol
PPROTFL = 'Y' if (ITTFL == 'Y' and COMPLTFL == 'Y' and MAJORDEV != 'Y') else 'N'
```

---

## Edge Cases

### Protocol Not Available
```python
if protocol_file is missing:
    # Prompt user to provide protocol path
    protocol_path = prompt_user("Please provide path to protocol document")
    # Or use minimal configuration
    study_config = create_minimal_config(studyid, phase)
```

### Multi-Center Studies
```yaml
site_information:
  central_randomization: true
  sites:
    - siteid: "{site_id}"
      country: "{country}"
```

### Adaptive Designs
```yaml
adaptive_design:
  enabled: false
  interim_analyses: []
  modification_rules: []
```

---

## Integration Points

### Downstream Skills
- `/sap-parser` -- Uses study-config for endpoint alignment
- `/spec-builder` -- Uses treatment arms for mapping specs
- `/sdtm-dm-mapper` -- Uses ARM, ARMCD mappings
- `/sdtm-trial-design-builder` -- Uses visit schedule for TV domain
- `/adam-adsl-builder` -- Uses population definitions for SAFFL, ITTFL, PPROTFL
- `/tfl-demographics` -- Uses treatment groups for column headers

### Configuration Files Created
- `specs/study-config.yaml` -- Primary study configuration
- `specs/treatment-arms.yaml` -- Treatment arm details
- `specs/visit-schedule.yaml` -- Visit definitions
- `specs/populations.yaml` -- Population definitions

---

## Evaluation Criteria

**Mandatory:**
- Study ID and phase correctly set
- Treatment arms and visit schedule defined
- Output schema validates against YAML schema
- All required fields populated

**Recommended:**
- Randomization scheme documented
- Stratification factors captured
- Population definitions with derivation logic
- Source page references included

---

## Critical Constraints

**Never:**
- Hardcode study-specific values (study ID, treatment arms, dates, file paths)
- Proceed if required configuration is missing
- Proceed without a study ID
- Create treatment arms not in protocol
- Skip validation of output schema
- Overwrite existing study-config without backup

**Always:**
- Resolve study metadata dynamically from ops/workflow-state.yaml or --study-config
- Read treatment arm definitions from study config, not hardcoded mappings
- Document source of each configuration element
- Include page references for audit trail
- Validate output against schema before writing
- Create backup of existing configuration

---

## Examples

### Basic Usage
```bash
study-setup --input {protocol_path} --output specs/study-config.yaml
```

### With Validation
```bash
study-setup --input {protocol_path} --output specs/study-config.yaml --validate
```

### Expected Output
```yaml
# specs/study-config.yaml
study_identification:
  studyid: "{study_id} from study config"
  phase: "{phase}"

treatment_arms:
  # Read ARMCD mappings from study_config.treatment_arms
  - arm: "{arm_name}"
    armcd: "{armcd}"

randomization:
  ratio: "{randomization_ratio}"
```
