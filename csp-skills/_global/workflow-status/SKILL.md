---
name: workflow-status
description: Quick workflow status dashboard. Global skill available at every node. Triggers on "status", "where am I", "progress report".
version: "1.0"
user-invocable: true
context: fork
model: haiku
allowed-tools: Read, Grep, Glob
argument-hint: "[options] -- --format [brief|detail|json]"
---

## Runtime Configuration (Step 0)
Read: ops/workflow-state.yaml, graph/regulatory-graph.yaml

## EXECUTE NOW
**START NOW.** Read-only status check — never modify state.

---

## Philosophy
**Instant situational awareness.** Show the user exactly where they are in the pipeline, what's done, what's next, and estimated completion. Uses lightweight model (haiku) for minimal token cost.

---

## Output Format

### Brief (default)
```
Layer 2: SDTM Creation | 12/45 nodes (27%) | Next: sdtm-lb-mapping
```

### Detail
```
Completed: protocol-setup → sap-review → spec-creation → edc-extract → ...
Current:   sdtm-dm-mapping
Frontier:  sdtm-ae-mapping, sdtm-lb-mapping, sdtm-vs-mapping
Progress:  ████████░░░░░░░░ 27%
```

---

## Evaluation Criteria
**Mandatory:** Accurate node counts, correct frontier computation
**Recommended:** Progress bar, estimated time, layer summary
