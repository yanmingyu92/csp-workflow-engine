---
name: adam-traceability-checker
description: Verify ADaM-to-SDTM traceability. Triggers on "traceability", "ADaM traceability", "SDTM to ADaM", "variable lineage", "derivation lineage", "source variable".
version: "2.0"
user-invocable: true
context: fork
model: sonnet
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
argument-hint: "[options] -- --input, --output"
---

## Runtime Configuration (Step 0)

### Dynamic Config Resolution
```yaml
config_sources:
  - path: specs/study-config.yaml
    description: Study-level metadata
  - path: specs/adam-spec.yaml
    description: ADaM derivation specifications (source variable mappings)
  - path: specs/sdtm-mapping-spec.xlsx
    description: SDTM mapping specifications

required_inputs:
  - type: dataset
    name: All ADaM datasets
    format: xpt
    path_pattern: "{adam-dir}/*.xpt"
  - type: dataset
    name: All SDTM datasets
    format: xpt
    path_pattern: "{sdtm-dir}/*.xpt"
  - type: specification
    name: ADaM derivation specification
    format: xlsx|yaml
    path_pattern: specs/adam-spec.yaml

output:
  - type: report
    name: Traceability report
    format: html|pdf
    path_pattern: "{output}"
```

Read: {adam-dir}/*.xpt, {sdtm-dir}/*.xpt, specs/adam-spec.yaml, specs/study-config.yaml

## EXECUTE NOW
Parse $ARGUMENTS: --adam-dir, --sdtm-dir, --output, --spec, --dry-run
**START NOW.**

---

## Philosophy
**Every ADaM variable must trace back to SDTM sources.** Orphan variables (those without documented SDTM lineage) indicate derivation documentation gaps that will be flagged by regulators. Traceability is the core ADaM principle: a reviewer must be able to understand how each analysis variable was derived from collected data.

**Key Principle:** Complete traceability means every ADaM variable has a documented path back to one or more SDTM source variables, with the derivation method clearly described.

---

## Input/Output Specification

### Inputs (from regulatory-graph.yaml: adam-traceability-check)
| Input | Format | Required | Source |
|-------|--------|----------|--------|
| All ADaM datasets | xpt | Yes | adam-adsl, adam-adae, adam-adlb, etc. |
| All SDTM datasets | xpt | Yes | sdtm-dm-mapping, sdtm-ae-mapping, etc. |
| ADaM derivation spec | xlsx/yaml | Yes | spec-creation |

### Outputs (to regulatory-graph.yaml: adam-traceability-check)
| Output | Format | Path Pattern | Consumers |
|--------|--------|--------------|-----------|
| Traceability report | html/pdf | reports/adam-traceability-report.html | adrg-writer, define-xml-adam |

---

## Script Execution
```bash
adam-traceability-checker --adam-dir {adam-dir} --sdtm-dir {sdtm-dir} --output {output} [--spec {spec}] [--dry-run]
```

### Arguments
| Argument | Required | Description |
|----------|----------|-------------|
| `--adam-dir` | Yes | Directory containing ADaM XPT files |
| `--sdtm-dir` | Yes | Directory containing SDTM XPT files |
| `--output` | Yes | Output path for traceability report |
| `--spec` | No | ADaM specification YAML |
| `--dry-run` | No | Show check plan without running |

---

## Key Variables

| Variable | Description |
|----------|-------------|
| ADAM_VAR | ADaM variable being checked |
| ADAM_DATASET | ADaM dataset containing the variable |
| SDTM_SOURCE | Source SDTM domain.variable |
| TRACEABLE | Yes/No/Partial |
| DERIVATION_METHOD | How the variable was derived (direct copy, transformation, aggregation) |
| EVIDENCE | Supporting evidence for traceability claim |

---

## Traceability Check Logic

```python
def check_traceability(adam_dir, sdtm_dir, adam_spec):
    """
    Verify end-to-end traceability from ADaM back to SDTM.

    For each ADaM dataset:
    1. Read all variable names from the dataset
    2. For each variable, look up source in adam-spec.yaml
    3. Verify the source SDTM domain exists and contains the source variable
    4. For derived variables, verify derivation logic is documented
    5. Flag any orphan variables (no traceability)
    """
    results = []

    for adam_file in glob(f"{adam_dir}/*.xpt"):
        adam_ds = read_xpt(adam_file)
        adam_name = Path(adam_file).stem.upper()

        for var in adam_ds.columns:
            # Look up source in spec
            source = adam_spec.get_source(adam_name, var)

            if source is None:
                results.append(TraceResult(
                    adam_dataset=adam_name,
                    adam_var=var,
                    sdtm_source="UNKNOWN",
                    traceable="No",
                    derivation_method="ORPHAN",
                    evidence=f"No source documented for {adam_name}.{var}"
                ))
                continue

            # Verify SDTM source exists
            sdtm_domain, sdtm_var = parse_source(source)
            sdtm_file = f"{sdtm_dir}/{sdtm_domain.lower()}.xpt"

            if not Path(sdtm_file).exists():
                results.append(TraceResult(
                    adam_dataset=adam_name,
                    adam_var=var,
                    sdtm_source=source,
                    traceable="No",
                    derivation_method="missing_source_domain",
                    evidence=f"SDTM domain {sdtm_domain} not found"
                ))
            else:
                sdtm_ds = read_xpt(sdtm_file)
                if sdtm_var in sdtm_ds.columns:
                    results.append(TraceResult(
                        adam_dataset=adam_name,
                        adam_var=var,
                        sdtm_source=source,
                        traceable="Yes",
                        derivation_method=source.get('method', 'direct'),
                        evidence=f"Verified: {sdtm_domain}.{sdtm_var} exists"
                    ))
                else:
                    results.append(TraceResult(
                        adam_dataset=adam_name,
                        adam_var=var,
                        sdtm_source=source,
                        traceable="Partial",
                        derivation_method="source_var_missing",
                        evidence=f"{sdtm_domain} exists but {sdtm_var} not found"
                    ))

    return results
```

---

## Output Schema

```yaml
traceability_report:
  date: "{timestamp}"
  datasets_checked: ["ADSL", "ADAE", "ADLB", "ADTTE", "ADEFF"]
  spec_version: "ADaM IG v1.3"

  summary:
    total_variables: 0
    traceable: 0
    partial: 0
    orphan: 0

  results:
    - adam_dataset: "ADSL"
      adam_var: "SAFFL"
      sdtm_source: "EX.EXDOSE + DM.ARMCD"
      traceable: "Yes"
      derivation_method: "derived"
      evidence: "EX domain and DM domain verified with required variables"

    - adam_dataset: "ADSL"
      adam_var: "TRT01P"
      sdtm_source: "DM.ARM"
      traceable: "Yes"
      derivation_method: "direct"
      evidence: "DM domain contains ARM variable"

  lineage_diagram:
    format: "mermaid"
    description: "Visual representation of ADaM-to-SDTM variable mappings"
```

---

## Edge Cases

### Multi-Source Derivations
```python
# Variables derived from multiple SDTM sources (e.g., SAFFL from EX + DM):
# - All sources must be verified
# - If any source is missing, traceability = "Partial"
# - Document multi-source derivation in report
```

### Conditional Traceability
```python
# Some variables only exist for certain populations:
# - PPROTFL: only relevant for ITT subjects
# - Treatment variables: not applicable for screen failures
# - Traceability still required for derivation logic
```

### Variables from Supplemental Domains
```python
# SUPPXX variables used in derivations:
# - Must trace through SUPPXX.QNAM -> SUPPXX.QVAL
# - Link via IDVAR/IDVARVAL to parent domain
# - Document supplemental source in report
```

### Custom/Non-Standard Variables
```python
# Non-standard ADaM variables:
# - Must have documented derivation (Method in Define.xml)
# - Traceability to SDTM still required
# - May require custom documentation in ADRG
```

---

## Integration Points

### Upstream Skills
- `/adam-adsl-builder` -- ADSL to check traceability
- `/adam-adae-builder` -- ADAE to check traceability
- `/adam-adlb-builder` -- ADLB to check traceability
- `/adam-adtte-builder` -- ADTTE to check traceability
- `/adam-adeff-builder` -- ADEFF to check traceability
- `/adam-custom-builder` -- Custom ADaM to check traceability

### Downstream Skills
- `/adrg-writer` -- Document traceability approach in ADRG
- `/define-draft-builder` -- ADaM metadata for Define.xml

### Related Skills
- `/adam-validator` -- Cross-dataset consistency checks
- `/p21-adam-validation` -- P21 ADaM-specific rules

---

## Evaluation Criteria
**Mandatory:**
- Every ADaM variable has documented SDTM source
- No orphan variables without traceability
- Multi-source derivations fully documented
- Report generated with traceable/partial/orphan counts

**Recommended:**
- Visual lineage diagram generated
- Traceability matches Define.xml Method metadata
- Coverage across all ADaM datasets

---

## Critical Constraints
**Never:**
- Skip variables without documented sources
- Accept "trust me" traceability without evidence
- Ignore custom/non-standard variables
- Produce output without validation

**Always:**
- Verify source SDTM domain and variable actually exist
- Check multi-source derivations completely
- Flag orphan variables prominently
- Generate detailed evidence for each traceability claim
- Generate traceable, reproducible results

---

## Examples
```bash
adam-traceability-checker --adam-dir output/adam/ --sdtm-dir output/sdtm/ --output reports/adam-traceability-report.html
```

### Expected Output
```
reports/adam-traceability-report.html
+-- Summary ({n_vars} total: {traceable} traceable, {partial} partial, {orphan} orphan)
+-- ADSL traceability (SAFFL, ITTFL, TRT01P, etc.)
+-- ADAE traceability (TRTEMFL, AOCCFL, ASTDT, etc.)
+-- ADLB traceability (AVAL, BASE, CHG, ABLFL, etc.)
+-- Lineage diagram (ADaM -> SDTM variable mappings)
```
