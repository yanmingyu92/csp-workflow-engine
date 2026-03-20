# Clinical Trial Statistical Programming — Graph-Based Regulatory Workflow Engine

## Problem & Background

The current CSP Workflow Engine project provides a **knowledge management plugin** for Claude Code with skills, hooks, and a workflow graph layer (see `docs/workflow-graph-implementation.md`). The existing workflow graph already sketches a 6-stage SDTM-to-submission pipeline, but the **review report scored it 60/100** with 27 gaps — most critically: pseudocode-only skills, no real enforcement, no expression evaluator, and no formal state machine.

**What we need now** is to pivot toward **clinical trial statistical programming** as a first-class domain, where:

1. A **comprehensive task graph (DAG)** covers every action a statistical programmer must take, organized by regulatory phases (SDTM → ADaM → TFL → Define.xml → Submission)
2. **Skills and MCPs are bound to specific graph nodes**, providing the actual executable logic (Python scripts, MCP tool calls)
3. The **graph narrows the action space** — at any graph position, only relevant skills/MCPs are loaded, saving tokens and preventing regulatory violations
4. **Evaluation functions** allow extending the graph with new tasks/nodes while ensuring best-practice compliance
5. The whole system acts as a **retrievable documentation system** — the LLM loads only the relevant regulatory context for the current graph node

> [!IMPORTANT]
> This is a large architectural change. The plan is structured in 5 phases that can be delivered incrementally. Each phase produces usable output.

---

## User Review Required

> [!WARNING]
> **Scope of change:** This plan proposes significant new directories (`graph/`, `csp-skills/`, `mcps/`, `evaluation/`) and modifies core files like `hooks/hooks.json`, `reference/workflow-schema.yaml`, and the `/workflow` skill. The existing knowledge management functionality is **not removed** — this adds a parallel clinical-trial-specific layer.

**Decisions needing your input:**

1. **Python vs. SAS:** Should the skill scripts generate Python (using Pharmaverse/pandas) or SAS code? The plan defaults to **Python** since it's open-source and better suited for LLM-generated code. SAS templates can be added later.
2. **MCP integration:** Should we build actual MCP servers (e.g., a Pinnacle 21 interface), or start with mock MCPs that validate structure only?
3. **Graph granularity:** The plan proposes ~40 nodes across 7 layers. Should we start with the full graph, or a minimal 6-stage skeleton first?

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────────────┐
│                     REGULATORY TASK GRAPH (DAG)                      │
│                                                                      │
│  Layer 0: Protocol    Layer 1: Raw Data    Layer 2: SDTM           │
│  ┌──────────┐        ┌──────────┐         ┌──────────┐             │
│  │ SAP      │───────▶│ CRF Val  │────────▶│ DM Map   │             │
│  │ Review   │        │          │   ┌────▶│ AE Map   │             │
│  └──────────┘        └──────────┘   │     │ LB Map   │             │
│                      ┌──────────┐   │     │ ...      │             │
│                      │ EDC      │───┘     └────┬─────┘             │
│                      │ Extract  │              │                    │
│                      └──────────┘              │                    │
│                                                ▼                    │
│  Layer 3: SDTM QC    Layer 4: ADaM    Layer 5: TFL                 │
│  ┌──────────┐        ┌──────────┐     ┌──────────┐                 │
│  │ P21 Val  │───────▶│ ADSL     │────▶│ Table    │                 │
│  │ Domain   │        │ ADAE     │     │ Listing  │                 │
│  │ Consist  │        │ ADLB     │     │ Figure   │                 │
│  └──────────┘        └────┬─────┘     └────┬─────┘                 │
│                           │                │                        │
│                           ▼                ▼                        │
│  Layer 6: Define.xml          Layer 7: Submission                  │
│  ┌──────────┐                 ┌──────────┐                          │
│  │ Define   │────────────────▶│ eSub     │                          │
│  │ Generate │                 │ Package  │                          │
│  └──────────┘                 └──────────┘                          │
│                                                                      │
├──────────────────────────────────────────────────────────────────────┤
│                     GRAPH ROUTER (Token Optimizer)                    │
│                                                                      │
│  current_node → load skills for [prev_nodes + current + next_nodes] │
│  Skip all other skills. Reduce 40+ skills to 3-8 per position.     │
│                                                                      │
├──────────────────────────────────────────────────────────────────────┤
│                     EVALUATION FUNCTIONS                             │
│                                                                      │
│  can_add_node(graph, new_node) → validates against CDISC patterns  │
│  can_extend_edge(graph, src, dst) → validates dependency ordering  │
│  evaluate_completion(node) → checks outputs against regulatory spec│
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Proposed Changes

### Phase 1: Regulatory Task Graph DAG

The core data structure: a YAML-defined DAG where each node is a regulatory task and edges are typed dependencies.

---

#### [NEW] [regulatory-graph.yaml](file:///c:/Users/yanmi/csp-workflow-engine/graph/regulatory-graph.yaml)

The master graph definition with ~40 nodes across 7 layers. Each node specifies:
- `id`, `name`, `layer`, `description`
- `skills_bound`: skills/MCPs exclusively available at this node
- `inputs_required`: what artifacts must exist before this node activates
- `outputs_produced`: what artifacts this node creates
- `regulatory_refs`: ICH/CDISC guideline references
- `dependencies`: predecessor node IDs (typed edges)
- `evaluation_criteria`: how to judge completion

```yaml
# Example node structure
nodes:
  - id: sdtm-dm-mapping
    name: "SDTM DM Domain Mapping"
    layer: 2
    description: "Map raw demographics data to SDTM DM domain per CDISC IG v3.4"
    skills_bound: [/sdtm-dm-mapper, /sdtm-validator]
    mcps_bound: [p21-validator]
    inputs_required:
      - type: specification
        name: "SDTM mapping specification"
        format: xlsx|yaml
      - type: dataset
        name: "Raw demographics data"
        format: csv|sas7bdat
    outputs_produced:
      - type: dataset
        name: "DM domain"
        format: xpt
        validation: p21-compliance
    regulatory_refs:
      - "CDISC SDTM IG v3.4 Section 6.1"
      - "FDA Study Data Technical Conformance Guide"
    dependencies:
      - node: raw-data-validation
        edge_type: requires
      - node: sdtm-spec-review
        edge_type: requires
    evaluation_criteria:
      mandatory:
        - "All required DM variables present per SDTM IG"
        - "P21 validation returns 0 errors"
      recommended:
        - "P21 validation returns 0 warnings"
        - "Controlled terminology aligned with latest CDISC CT"
```

---

#### [NEW] [graph-layers.yaml](file:///c:/Users/yanmi/csp-workflow-engine/graph/graph-layers.yaml)

Layer definitions that group nodes and define the regulatory phase boundaries:

```yaml
layers:
  - id: 0
    name: "Protocol & Planning"
    nodes: [sap-review, protocol-setup, spec-creation]
    description: "Study setup, SAP review, specification creation"
    
  - id: 1
    name: "Raw Data Management"
    nodes: [edc-extract, crf-validation, raw-data-validation, data-reconciliation]
    description: "Data acquisition, CRF validation, raw data QC"
    
  - id: 2
    name: "SDTM Creation"
    nodes: [sdtm-dm-mapping, sdtm-ae-mapping, sdtm-lb-mapping, sdtm-vs-mapping,
            sdtm-cm-mapping, sdtm-mh-mapping, sdtm-ex-mapping, sdtm-suppqual,
            sdtm-custom-domain, sdtm-relrec]
    description: "Map raw data to CDISC SDTM domains"
    
  - id: 3
    name: "SDTM Quality Control"
    nodes: [p21-sdtm-validation, sdtm-crossdomain-check, sdtm-define-draft,
            sdtm-annotated-crf, sdtm-reviewer-guide]
    description: "Validate SDTM datasets, generate supporting docs"
    
  - id: 4
    name: "ADaM Creation"
    nodes: [adam-adsl, adam-adae, adam-adlb, adam-adtte, adam-adeff,
            adam-custom-analysis, adam-traceability-check]
    description: "Derive analysis datasets from SDTM"
    
  - id: 5
    name: "TFL Generation"
    nodes: [tfl-shell-review, tfl-table-generation, tfl-listing-generation,
            tfl-figure-generation, tfl-qc-validation, tfl-double-programming]
    description: "Generate tables, figures, and listings for CSR"
    
  - id: 6
    name: "Define.xml & Submission"
    nodes: [define-xml-sdtm, define-xml-adam, define-xml-validation,
            esub-package-assembly, esub-final-validation]
    description: "Create Define.xml metadata, assemble eCTD submission"
```

---

#### [MODIFY] [workflow-schema.yaml](file:///c:/Users/yanmi/csp-workflow-engine/reference/workflow-schema.yaml)

Extend the existing schema to support the richer graph structure:

- Add `layer` property to stage schema
- Add `skills_bound` and `mcps_bound` to stage schema
- Add `inputs_required` and `outputs_produced` with typed artifact definitions
- Add `regulatory_refs` for traceability
- Add `evaluation_criteria` block (mandatory + recommended checks)
- Add `adjacency_context` to control which neighbors' skills are also loaded

---

### Phase 2: Skills & MCPs Bound to Graph Nodes

Create real, executable Python skills for each graph node. These replace the pseudocode in the current SKILL.md files.

---

#### [NEW] `csp-skills/` directory

Each subdirectory corresponds to a graph node and contains:
- `SKILL.md` — the agent instruction file (references the Python script)
- `script.py` — the actual executable logic
- `spec.yaml` — input/output schema for this skill

Example structure:
```
csp-skills/
├── sdtm-dm-mapper/
│   ├── SKILL.md          # Agent prompt: how to use this skill
│   ├── script.py         # Python: reads raw data, maps to DM domain
│   └── spec.yaml         # I/O schema: what goes in, what comes out
├── sdtm-ae-mapper/
│   ├── SKILL.md
│   ├── script.py
│   └── spec.yaml
├── p21-validator/
│   ├── SKILL.md
│   ├── script.py         # Python: calls Pinnacle 21 API or validates locally
│   └── spec.yaml
├── adam-adsl-builder/
│   ├── SKILL.md
│   ├── script.py
│   └── spec.yaml
├── tfl-generator/
│   ├── SKILL.md
│   ├── script.py
│   └── spec.yaml
└── define-xml-builder/
    ├── SKILL.md
    ├── script.py
    └── spec.yaml
```

---

#### [NEW] `mcps/` directory

MCP server configurations for external tool integration:

```
mcps/
├── p21-validator/
│   ├── mcp-config.json    # MCP server config for Pinnacle 21
│   └── README.md          # Setup instructions
├── cdisc-library/
│   ├── mcp-config.json    # MCP for CDISC Library API (CT, IG lookups)
│   └── README.md
└── data-quality/
    ├── mcp-config.json    # MCP for data quality checks
    └── README.md
```

---

### Phase 3: Graph Router — Token-Efficient Skill Loading

The key innovation: the agent never loads all skills. It loads only skills for the current node and adjacent nodes (predecessors + successors), reducing context from 40+ skills to 3-8.

---

#### [NEW] [graph-router.py](file:///c:/Users/yanmi/csp-workflow-engine/scripts/graph-router.py)

Python script that:
1. Reads `graph/regulatory-graph.yaml`
2. Reads `ops/workflow-state.yaml` to find current node
3. Computes adjacency: `{prev_nodes} ∪ {current_node} ∪ {next_nodes}`
4. Returns only the skills bound to those nodes
5. When multiple nodes are in-progress, checks formal (predecessor) and next (successor) nodes to decide best action

```python
def get_active_skills(graph, state):
    """Return only skills relevant to current graph position."""
    current = state.current_node
    node = graph.get_node(current)
    
    # Adjacency = predecessors + current + successors
    predecessors = graph.get_predecessors(current)
    successors = graph.get_successors(current)
    adjacent = predecessors + [current] + successors
    
    # Collect skills from adjacent nodes only
    skills = []
    for adj_node_id in adjacent:
        adj_node = graph.get_node(adj_node_id)
        skills.extend(adj_node.skills_bound)
        skills.extend(adj_node.mcps_bound)
    
    return deduplicate(skills)
```

---

#### [MODIFY] [workflow/SKILL.md](file:///c:/Users/yanmi/csp-workflow-engine/skill-sources/workflow/SKILL.md)

Update the `/workflow skills` command to use graph-router.py instead of the current grep-based approach:

- Call `graph-router.py` to get filtered skills
- Show adjacency context: "You are at node X. Predecessor nodes: [...]. Next possible nodes: [...]"
- When multiple nodes are active, show comparison table

---

#### [NEW] [context-loader.py](file:///c:/Users/yanmi/csp-workflow-engine/scripts/context-loader.py)

Minimal-token context builder that constructs the LLM prompt context:
- Load only the `SKILL.md` files for active skills (from graph-router)
- Load only the regulatory references for the current node
- Exclude all other documentation
- Target: < 2000 tokens for routing context, vs. 15000+ if all skills loaded

---

### Phase 4: Evaluation Functions — Extensibility with Guardrails

Allow users (or the LLM itself) to add new nodes to the graph while ensuring regulatory compliance.

---

#### [NEW] [evaluation.py](file:///c:/Users/yanmi/csp-workflow-engine/scripts/evaluation.py)

```python
def can_add_node(graph, new_node):
    """Validate a proposed new node against regulatory patterns."""
    checks = []
    
    # 1. Layer assignment: node must fit within known layer boundaries
    checks.append(validate_layer_assignment(new_node))
    
    # 2. Dependency ordering: no cross-layer backward edges
    checks.append(validate_dependency_ordering(graph, new_node))
    
    # 3. CDISC compliance: node outputs must match known artifact types
    checks.append(validate_output_types(new_node))
    
    # 4. Circular dependency detection: topological sort must still succeed
    checks.append(validate_no_cycles(graph, new_node))
    
    # 5. Skills exist: bound skills must reference real SKILL.md files
    checks.append(validate_skills_exist(new_node))
    
    return EvaluationResult(checks)

def evaluate_completion(graph, node_id, outputs):
    """Check if a node's outputs meet its evaluation_criteria."""
    node = graph.get_node(node_id)
    results = []
    
    for criterion in node.evaluation_criteria.mandatory:
        results.append(check_criterion(criterion, outputs))
    
    mandatory_pass = all(r.passed for r in results if r.is_mandatory)
    return CompletionResult(mandatory_pass, results)
```

---

#### [NEW] [regulatory-patterns.yaml](file:///c:/Users/yanmi/csp-workflow-engine/graph/regulatory-patterns.yaml)

Templates for common node patterns that evaluation functions validate against:

```yaml
patterns:
  sdtm-domain-mapping:
    required_inputs: [raw-data, mapping-spec]
    required_outputs: [xpt-dataset]
    required_validation: [p21-compliance]
    layer_range: [2, 2]
    
  adam-derivation:
    required_inputs: [sdtm-dataset, analysis-spec]
    required_outputs: [adam-dataset]
    required_validation: [adam-compliance, traceability]
    layer_range: [4, 4]
    
  tfl-generation:
    required_inputs: [adam-dataset, tfl-shell]
    required_outputs: [report-output]
    required_validation: [qc-review]
    layer_range: [5, 5]
```

---

### Phase 5: Documentation System — LLM-Retrievable Regulatory Context

Turn regulatory guidance into graph-anchored, LLM-retrievable documents.

---

#### [NEW] `docs/regulatory/` directory

Regulatory reference documents chunked and indexed by graph node:

```
docs/regulatory/
├── sdtm/
│   ├── dm-domain-guide.md        # Anchored to: sdtm-dm-mapping
│   ├── ae-domain-guide.md        # Anchored to: sdtm-ae-mapping
│   ├── controlled-terminology.md # Anchored to: all Layer 2 nodes
│   └── supplemental-qualifiers.md
├── adam/
│   ├── adsl-derivation-guide.md  # Anchored to: adam-adsl
│   ├── bds-structure-guide.md    # Anchored to: adam-adae, adam-adlb
│   └── traceability-guide.md     # Anchored to: adam-traceability-check
├── tfl/
│   ├── table-programming-guide.md
│   ├── figure-best-practices.md
│   └── double-programming-sop.md
├── submission/
│   ├── define-xml-guide.md
│   └── ectd-packaging-guide.md
└── index.yaml                    # Maps each doc to its graph node(s)
```

---

#### [NEW] [doc-index.yaml](file:///c:/Users/yanmi/csp-workflow-engine/docs/regulatory/index.yaml)

Maps documents to graph nodes for retrieval:

```yaml
documents:
  - path: sdtm/dm-domain-guide.md
    anchored_to: [sdtm-dm-mapping]
    summary: "SDTM DM domain variables, controlled terms, derivation rules"
    token_cost: ~800
    
  - path: adam/adsl-derivation-guide.md
    anchored_to: [adam-adsl]
    summary: "ADSL population flags, baseline derivations, treatment assignments"
    token_cost: ~1200
```

The `context-loader.py` from Phase 3 uses this index to load only relevant docs.

---

## File Change Summary

### New Files (20+)

| Path | Phase | Purpose |
|------|-------|---------|
| `graph/regulatory-graph.yaml` | 1 | Master DAG definition |
| `graph/graph-layers.yaml` | 1 | Layer definitions |
| `graph/regulatory-patterns.yaml` | 4 | Validation patterns for extensibility |
| `csp-skills/sdtm-dm-mapper/SKILL.md` | 2 | SDTM DM domain mapping skill |
| `csp-skills/sdtm-dm-mapper/script.py` | 2 | Python implementation |
| `csp-skills/sdtm-dm-mapper/spec.yaml` | 2 | I/O schema |
| `csp-skills/p21-validator/SKILL.md` | 2 | Pinnacle 21 validation skill |
| `csp-skills/p21-validator/script.py` | 2 | Python implementation |
| `csp-skills/adam-adsl-builder/SKILL.md` | 2 | ADaM ADSL builder skill |
| `csp-skills/adam-adsl-builder/script.py` | 2 | Python implementation |
| `csp-skills/tfl-generator/SKILL.md` | 2 | TFL generation skill |
| `csp-skills/define-xml-builder/SKILL.md` | 2 | Define.xml builder skill |
| `mcps/p21-validator/mcp-config.json` | 2 | MCP server configuration |
| `mcps/cdisc-library/mcp-config.json` | 2 | CDISC Library MCP config |
| `scripts/graph-router.py` | 3 | Token-efficient skill routing |
| `scripts/context-loader.py` | 3 | Minimal-token context builder |
| `scripts/evaluation.py` | 4 | Graph extension validation |
| `docs/regulatory/sdtm/*.md` | 5 | SDTM regulatory guides |
| `docs/regulatory/adam/*.md` | 5 | ADaM regulatory guides |
| `docs/regulatory/index.yaml` | 5 | Document-to-graph-node index |

### Modified Files

| Path | Phase | Changes |
|------|-------|---------|
| `reference/workflow-schema.yaml` | 1 | Add layer, skills_bound, mcps_bound, evaluation_criteria |
| `skill-sources/workflow/SKILL.md` | 3 | Use graph-router for skill filtering |
| `hooks/hooks.json` | 3 | Add graph-router hook to SessionStart |
| `skill-sources/ralph/SKILL.md` | 3 | Add graph-aware routing check |

---

## Verification Plan

### Automated Tests

**Phase 1 — Graph validation:**
```bash
# Verify graph YAML is valid and acyclic
python scripts/evaluation.py --validate-graph graph/regulatory-graph.yaml
# Expected: "Graph valid: 40 nodes, 0 cycles, 7 layers"
```

**Phase 3 — Router token efficiency:**
```bash
# Test that router returns only adjacent skills
python scripts/graph-router.py --node sdtm-dm-mapping --graph graph/regulatory-graph.yaml
# Expected: returns 3-8 skills, not all 40+
```

**Phase 4 — Evaluation function tests:**
```bash
# Test adding a valid node
python scripts/evaluation.py --test-add-node graph/regulatory-graph.yaml test-fixtures/valid-node.yaml
# Expected: PASS

# Test adding a node with circular dependency
python scripts/evaluation.py --test-add-node graph/regulatory-graph.yaml test-fixtures/circular-node.yaml
# Expected: FAIL — "Circular dependency detected"

# Test adding a node with invalid layer crossing
python scripts/evaluation.py --test-add-node graph/regulatory-graph.yaml test-fixtures/invalid-layer-node.yaml
# Expected: FAIL — "Cross-layer backward edge not allowed"
```

### Manual Verification

1. **Graph review:** After creating `regulatory-graph.yaml`, visually inspect the Mermaid diagram (generated by `/workflow graph`) to confirm the DAG covers the full CDISC workflow
2. **Token measurement:** Count tokens loaded by `context-loader.py` at several graph positions — target < 2000 tokens per position vs. 15000+ if all skills are loaded
3. **Skill routing check:** At each graph node, verify that only the bound skills are returned and blocked skills are actually rejected
4. **User walkthrough:** Walk through a simulated SDTM mapping task to verify the system loads correct skills, docs, and regulatory context at each step

> [!TIP]
> **Phased delivery:** Each phase is independently valuable. Phase 1 alone gives you the regulatory DAG structure. Phase 1+3 gives you token-efficient routing. All 5 phases give you the complete system.
