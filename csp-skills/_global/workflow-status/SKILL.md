---
name: workflow-status
description: Quick workflow status dashboard. Global skill available at every node. Triggers on "status", "where am I", "progress report".
version: "2.0"
user-invocable: true
context: fork
model: haiku
allowed-tools: Read, Grep, Glob
argument-hint: "[options] -- --format [brief|detail|json]"
---

## Runtime Configuration (Step 0)

Resolve configuration in order:
1. `$ARGUMENTS` (highest precedence)
2. `ops/workflow-state.yaml` -- current workflow state
3. `graph/regulatory-graph.yaml` -- DAG definition

```yaml
config_resolution:
  study_id: "$ARGUMENTS.study_id || study-config.study_id"
  format: "$ARGUMENTS.format || 'brief'"
  state_file: "ops/workflow-state.yaml"
  graph_file: "graph/regulatory-graph.yaml"
```

## EXECUTE NOW
**START NOW.** Read-only status check -- never modify state.

---

## Philosophy

**Instant situational awareness.** Show the user exactly where they are in the pipeline, what is done, what is next, and estimated completion. Uses lightweight model (haiku) for minimal token cost.

---

## Input/Output Specification

### Inputs
| Input | Format | Required | Source |
|-------|--------|----------|--------|
| Workflow state | yaml | Yes | ops/workflow-state.yaml |
| Regulatory graph | yaml | Yes | graph/regulatory-graph.yaml |

### Outputs
| Output | Format | Description |
|--------|--------|-------------|
| Status display | text/json | Current progress information (stdout only) |

---

## Output Format

### Brief (default)
```
Layer 2: SDTM Creation | 12/45 nodes (27%) | Next: sdtm-lb-mapping
```

### Detail
```
Completed: protocol-setup -> sap-review -> spec-creation -> edc-extract -> ...
Current:   sdtm-dm-mapping
Frontier:  sdtm-ae-mapping, sdtm-lb-mapping, sdtm-vs-mapping
Progress:  ████████░░░░░░░░ 27%
```

### JSON
```json
{
  "study_id": "{study_id}",
  "current_layer": 2,
  "layer_name": "SDTM Creation",
  "completed_nodes": 12,
  "total_nodes": 45,
  "progress_percent": 27,
  "frontier": ["sdtm-ae-mapping", "sdtm-lb-mapping", "sdtm-vs-mapping"],
  "timestamp": "{ISO_8601}"
}
```

---

## Layer Summary

| Layer | Name | Node Count |
|-------|------|------------|
| 0 | Protocol & Specs | 3 |
| 1 | Raw Data | 4 |
| 2 | SDTM Mapping | 10+ |
| 3 | SDTM QC | 5 |
| 4 | ADaM | 6+ |
| 5 | TFL Generation | 6 |
| 6 | Submission | 5 |

---

## Edge Cases

### No Workflow State
- If ops/workflow-state.yaml does not exist, show "Workflow not initialized"
- Suggest running `/workflow --action advance` to start

### Corrupted State
- If state file is malformed, show error with recovery suggestion
- Never crash; always produce readable output

---

## Integration Points

### Global Skill -- available at every workflow node
- Read-only companion to `/workflow` (which modifies state)
- Can be called at any time without side effects
- Minimal token cost (haiku model)

---

## Evaluation Criteria

**Mandatory:** Accurate node counts, correct frontier computation
**Recommended:** Progress bar, estimated time, layer summary

---

## Critical Constraints

**Never:**
- Modify workflow state (this is read-only)
- Show stale data without checking state file freshness

**Always:**
- Read state from ops/workflow-state.yaml
- Compute frontier from current graph definition
- Return accurate counts
