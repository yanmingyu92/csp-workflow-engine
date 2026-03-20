---
name: workflow
description: Track and manage regulatory workflow progression. Global skill available at every graph node. Triggers on "workflow", "progress", "status", "advance", "next step".
version: "1.0"
user-invocable: true
context: fork
model: sonnet
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
argument-hint: "[options] -- --action [advance|status|history|reset]"
---

## Runtime Configuration (Step 0)
Read: ops/workflow-state.yaml, graph/regulatory-graph.yaml

## EXECUTE NOW
Parse $ARGUMENTS: --action, --node, --force
**START NOW.**

---

## Philosophy
**The workflow controller is the heartbeat of the regulatory pipeline.** It tracks which graph nodes are complete, in-progress, or pending, and determines valid next actions based on the DAG dependency structure. Only nodes whose predecessors are all complete may be activated.

---

## Actions

| Action | Description |
|--------|-------------|
| `status` | Show current workflow state — active node, completed nodes, available frontier |
| `advance` | Move to the next valid node (checks all predecessors are complete) |
| `history` | Show completed node history with timestamps |
| `reset` | Reset workflow state (requires --force) |

---

## Frontier Computation
The **frontier** is the set of nodes whose predecessors are all marked complete but which are not yet started. This is computed via:
1. Build in-degree from uncompleted dependencies
2. Nodes with in-degree 0 that are not complete = frontier

---

## Evaluation Criteria
**Mandatory:** Never advance past incomplete prerequisites
**Recommended:** Log all state transitions with ISO 8601 timestamps

---

## Critical Constraints
**Never:**
- Skip dependency checks
- Allow parallel execution of nodes in the same layer without explicit config
- Modify state without audit trail

**Always:**
- Validate DAG before any state transition
- Persist state to ops/workflow-state.yaml after every change
- Report frontier nodes after any action
