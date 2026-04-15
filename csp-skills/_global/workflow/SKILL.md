---
name: workflow
description: Track and manage regulatory workflow progression. Global skill available at every graph node. Triggers on "workflow", "progress", "status", "advance", "next step".
version: "2.0"
user-invocable: true
context: fork
model: sonnet
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
argument-hint: "[options] -- --action [advance|status|history|reset]"
---

## Runtime Configuration (Step 0)

Resolve configuration in order:
1. `$ARGUMENTS` (highest precedence)
2. `ops/workflow-state.yaml` -- current workflow state
3. `graph/regulatory-graph.yaml` -- DAG definition

```yaml
config_resolution:
  study_id: "$ARGUMENTS.study_id || study-config.study_id"
  action: "$ARGUMENTS.action || 'status'"
  target_node: "$ARGUMENTS.node"
  force: "$ARGUMENTS.force || false"
  graph_definition: "graph/regulatory-graph.yaml"
  state_file: "ops/workflow-state.yaml"
```

## EXECUTE NOW
Parse $ARGUMENTS: --action, --node, --force
**START NOW.**

---

## Philosophy

**The workflow controller is the heartbeat of the regulatory pipeline.** It tracks which graph nodes are complete, in-progress, or pending, and determines valid next actions based on the DAG dependency structure. Only nodes whose predecessors are all complete may be activated.

---

## Input/Output Specification

### Inputs
| Input | Format | Required | Source |
|-------|--------|----------|--------|
| Workflow state | yaml | Yes | ops/workflow-state.yaml |
| Regulatory graph | yaml | Yes | graph/regulatory-graph.yaml |

### Outputs
| Output | Format | Path Pattern | Description |
|--------|--------|--------------|-------------|
| Updated workflow state | yaml | ops/workflow-state.yaml | State after action |

---

## Actions

| Action | Description |
|--------|-------------|
| `status` | Show current workflow state -- active node, completed nodes, available frontier |
| `advance` | Move to the next valid node (checks all predecessors are complete) |
| `history` | Show completed node history with timestamps |
| `reset` | Reset workflow state (requires --force) |

---

## Workflow State Schema

```yaml
# ops/workflow-state.yaml
workflow:
  study_id: "{study_id}"
  created_at: "{ISO_8601}"
  last_updated: "{ISO_8601}"

  current_nodes: ["sdtm-dm-mapping"]  # Currently active

  completed:
    - node_id: "protocol-setup"
      completed_at: "2024-01-15T10:30:00Z"
      status: "COMPLETE"
      outputs: ["specs/study-config.yaml"]
    - node_id: "sap-review"
      completed_at: "2024-01-16T14:00:00Z"
      status: "COMPLETE"
      outputs: ["specs/sap-parsed.yaml"]

  frontier:
    - "sdtm-ae-mapping"
    - "sdtm-lb-mapping"
    - "sdtm-vs-mapping"

  blocked:
    - node_id: "p21-sdtm-validation"
      blocked_by: ["sdtm-dm-mapping", "sdtm-ae-mapping", "sdtm-lb-mapping", "sdtm-vs-mapping"]
```

---

## Frontier Computation

The **frontier** is the set of nodes whose predecessors are all marked complete but which are not yet started. Computed via:

1. Build in-degree map from uncompleted dependencies
2. For each uncompleted node, count incomplete predecessors
3. Nodes with in-degree 0 that are not complete = frontier

```python
def compute_frontier(graph, completed_nodes):
    """
    Compute the next available nodes.

    Returns set of node IDs that can be started now.
    """
    frontier = set()
    for node in graph.nodes:
        if node.id in completed_nodes:
            continue
        deps = node.get_dependencies(edge_type='requires')
        if all(d in completed_nodes for d in deps):
            frontier.add(node.id)
    return frontier
```

---

## State Transition Rules

```yaml
transition_rules:
  advance:
    preconditions:
      - "Target node exists in regulatory-graph.yaml"
      - "All 'requires' dependencies are marked COMPLETE"
      - "Node is in frontier set"
    actions:
      - "Add node to current_nodes"
      - "Update last_updated timestamp"
      - "Recompute frontier"
    postconditions:
      - "Node appears in current_nodes"
      - "State file persisted"

  complete:
    preconditions:
      - "Node is in current_nodes"
      - "All required outputs exist on disk"
    actions:
      - "Move node from current_nodes to completed"
      - "Record completion timestamp"
      - "Recompute frontier"
    postconditions:
      - "Node appears in completed with timestamp"
      - "Frontier updated"

  reset:
    preconditions:
      - "--force flag provided"
    actions:
      - "Clear all state"
      - "Re-initialize from graph definition"
```

---

## Edge Cases

### Circular Dependencies
- The graph is a DAG; circular dependencies indicate a configuration error
- Validate graph on load; fail if cycles detected

### Parallel Node Execution
- Multiple nodes can be active simultaneously (e.g., sdtm-ae-mapping and sdtm-lb-mapping)
- Track each independently in current_nodes

### Partial Completion
- If a node fails partway, it remains in current_nodes with a status indicator
- Do not mark as complete until all outputs are verified

---

## Integration Points

### Global Skill -- available at every workflow node
- Invoked by all other skills to check prerequisites
- `/workflow-status` -- Lightweight read-only status view
- `/data-quality` -- Quality gate at each transition

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
