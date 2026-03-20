# Implementation Plan: Phase 3 — Graph Router & Token-Efficient Skill Loading

## Requirements Restatement

Implement Phase 3 of the Clinical Trial Statistical Programming Graph-Based Regulatory Workflow Engine:

1. **`scripts/graph-router.py`** — Python script that:
   - Reads `graph/regulatory-graph.yaml` to understand the DAG structure
   - Reads workflow state to find current node position
   - Computes adjacency (predecessors + current + successors)
   - Returns only skills/MCPs bound to adjacent nodes
   - Reduces skill context from 40+ to 3-8 per position

2. **`scripts/context-loader.py`** — Minimal-token context builder that:
   - Loads only SKILL.md files for active skills (from graph-router)
   - Loads only regulatory references for current node
   - Targets < 2000 tokens vs 15000+ if all skills loaded

3. **Update `skill-sources/workflow/SKILL.md`** — Integrate graph-router:
   - Replace bash/grep approach with Python graph-router calls
   - Show adjacency context in `/workflow skills` output
   - Support multiple active nodes with comparison table

---

## Current State Analysis

### Existing Infrastructure
- **Phase 1 Complete**: `graph/regulatory-graph.yaml` (45 nodes, 7 layers), `graph/graph-layers.yaml`
- **Validator exists**: `scripts/graph-validator.py` provides patterns for YAML loading, validation, reporting
- **Skills exist**: 55 CSP skills organized by layer in `csp-skills/`
- **Workflow skill**: Current `/workflow skills` uses bash/grep approach

### Key Patterns from graph-validator.py
```python
# YAML loading pattern
with open(self.graph_path, 'r', encoding='utf-8') as f:
    self.graph_data = yaml.safe_load(f)

# Adjacency tracking
self.adjacency: Dict[str, Set[str]] = defaultdict(set)
self.reverse_adjacency: Dict[str, Set[str]] = defaultdict(set)

# Node extraction with validation
for node in self.graph_data["nodes"]:
    node_id = node.get("id")
    self.nodes[node_id] = node
```

---

## Implementation Phases

### Phase 1: Graph Router Core (`graph-router.py`)

**Files to create:**
- `scripts/graph-router.py`

**Components:**

1. **GraphLoader class**
   - Load and parse `graph/regulatory-graph.yaml`
   - Build adjacency lists (forward and reverse)
   - Provide node lookup by ID

2. **StateReader class**
   - Read `ops/workflow-state.yaml` (if exists)
   - Extract current node(s) and status
   - Handle missing state gracefully

3. **AdjacencyCalculator class**
   - `get_predecessors(node_id)` — immediate predecessors via dependencies
   - `get_successors(node_id)` — nodes that depend on current
   - `get_adjacent_nodes(node_id, depth=1)` — configurable adjacency

4. **SkillCollector class**
   - Extract `skills_bound` and `mcps_bound` from adjacent nodes
   - Deduplicate skills
   - Include global_skills from graph definition

5. **CLI Interface**
   ```bash
   # Get skills for current workflow position
   python scripts/graph-router.py --skills

   # Get skills for specific node
   python scripts/graph-router.py --node sdtm-dm-mapping --skills

   # Get adjacency info
   python scripts/graph-router.py --node sdtm-dm-mapping --adjacency

   # JSON output for programmatic use
   python scripts/graph-router.py --node sdtm-dm-mapping --json
   ```

**Output format (text):**
```
--=={ graph router: sdtm-dm-mapping }==--

Current Node: SDTM DM Domain Mapping (Layer 2)

Adjacent Nodes:
  Predecessors: raw-data-validation, spec-creation
  Current: sdtm-dm-mapping
  Successors: p21-sdtm-validation, sdtm-crossdomain-check

Active Skills (6):
  /sdtm-dm-mapper      — Map raw demographics to SDTM DM
  /sdtm-validator      — Validate SDTM domain structure
  /data-validator      — Validate raw data quality
  /spec-builder        — Build mapping specifications
  /p21-validator       — Pinnacle 21 validation
  /workflow            — Global workflow skill

Context Reduction: 55 skills → 6 skills (89% reduction)
```

**Output format (JSON):**
```json
{
  "current_node": "sdtm-dm-mapping",
  "layer": 2,
  "predecessors": ["raw-data-validation", "spec-creation"],
  "successors": ["p21-sdtm-validation", "sdtm-crossdomain-check"],
  "skills": ["/sdtm-dm-mapper", "/sdtm-validator", ...],
  "mcps": ["p21-validator", "cdisc-library"],
  "stats": {
    "total_skills": 55,
    "active_skills": 6,
    "reduction_percent": 89
  }
}
```

---

### Phase 2: Context Loader (`context-loader.py`)

**Files to create:**
- `scripts/context-loader.py`

**Components:**

1. **SkillFileResolver class**
   - Map skill names to file paths: `/sdtm-dm-mapper` → `csp-skills/layer-2-sdtm/sdtm-dm-mapper/SKILL.md`
   - Handle missing skills gracefully
   - Support both CSP skills and general skills

2. **TokenEstimator class**
   - Estimate token count for content (rough: chars/4)
   - Track cumulative token usage
   - Warn when approaching limits

3. **ContextBuilder class**
   - Load skill files for active skills
   - Load regulatory references from node definition
   - Load docs/regulatory/* if anchored to current node
   - Assemble minimal context prompt

4. **CLI Interface**
   ```bash
   # Build context for current position
   python scripts/context-loader.py --build

   # Build context for specific node
   python scripts/context-loader.py --node sdtm-dm-mapping --build

   # Estimate tokens only
   python scripts/context-loader.py --node sdtm-dm-mapping --estimate

   # Output context to file
   python scripts/context-loader.py --node sdtm-dm-mapping --output context.txt
   ```

**Output format:**
```
--=={ context loader: sdtm-dm-mapping }==--

Skills Loaded (6):
  ✓ /sdtm-dm-mapper (423 tokens)
  ✓ /sdtm-validator (312 tokens)
  ✓ /data-validator (287 tokens)
  ✓ /spec-builder (198 tokens)
  ✓ /p21-validator (456 tokens)
  ✓ /workflow (534 tokens)

Regulatory References (3):
  ✓ CDISC SDTM IG v3.4 Section 6.1
  ✓ FDA Study Data Technical Conformance Guide
  ✓ CDISC SDTM IG v3.4

Documentation Loaded:
  - docs/regulatory/sdtm/dm-domain-guide.md (823 tokens)

Total Context: 3,033 tokens
Target: < 2,000 tokens (WARNING: exceeds target)
```

---

### Phase 3: Workflow Skill Integration

**Files to modify:**
- `skill-sources/workflow/SKILL.md`

**Changes:**

1. **Replace `/workflow skills` implementation**
   - Remove bash/grep logic
   - Call `graph-router.py` via subprocess
   - Parse JSON output
   - Display formatted results

2. **Enhance `/workflow status`**
   - Include adjacency context
   - Show active skills count

3. **Add `/workflow context` command**
   - Show full context for current position
   - Token usage estimation

4. **Update skill routing section**
   ```markdown
   ### /workflow skills

   Show skills filtered by workflow position using graph-router.

   **Execution:**
   ```python
   # Call graph-router for current node
   result = subprocess.run(
       ["python", "scripts/graph-router.py", "--json"],
       capture_output=True, text=True
   )
   data = json.loads(result.stdout)

   # Display formatted output
   print(f"Current Node: {data['current_node']} (Layer {data['layer']})")
   print(f"Active Skills: {len(data['skills'])}")
   for skill in data['skills']:
       print(f"  {skill}")
   ```
```

---

### Phase 4: Workflow State Schema

**Files to create:**
- `ops/workflow-state.yaml` (template)

**Schema:**
```yaml
schema_version: 1
workflow:
  id: csp-regulatory-pipeline
  name: Clinical Trial Statistical Programming Pipeline
  current_node: sdtm-dm-mapping
  started: "2025-01-15T10:30:00Z"

nodes:
  - id: sdtm-dm-mapping
    status: in_progress
    started: "2025-01-15T10:30:00Z"

  - id: raw-data-validation
    status: completed
    completed_at: "2025-01-15T09:45:00Z"

history:
  - timestamp: "2025-01-15T09:45:00Z"
    event: "node_completed"
    node: "raw-data-validation"
  - timestamp: "2025-01-15T10:30:00Z"
    event: "node_started"
    node: "sdtm-dm-mapping"
```

---

## Dependencies

### Internal
- `graph/regulatory-graph.yaml` — DAG definition (exists)
- `graph/graph-layers.yaml` — Layer definitions (exists)
- `csp-skills/**/*.md` — Skill files (exists)
- `scripts/graph-validator.py` — Pattern reference (exists)

### External (Python stdlib only)
- `yaml` — PyYAML (likely already installed)
- `json` — stdlib
- `argparse` — stdlib
- `pathlib` — stdlib
- `subprocess` — stdlib

---

## Risks & Mitigations

| Risk | Severity | Mitigation |
|------|----------|------------|
| Missing workflow state file | LOW | Default to Layer 0 entry node (protocol-setup) |
| Invalid graph YAML | LOW | Reuse validation logic from graph-validator.py |
| Skill file not found | MEDIUM | Skip with warning, continue loading others |
| Token estimation inaccuracy | LOW | Use conservative char/4 ratio, allow override |
| Performance on large graphs | LOW | Cache graph in memory, < 100 nodes is trivial |

---

## Verification Plan

### Automated Tests

```bash
# Test 1: Graph router returns skills for known node
python scripts/graph-router.py --node sdtm-dm-mapping --json | jq '.skills | length'
# Expected: 4-8 skills (not 55)

# Test 2: Adjacency calculation
python scripts/graph-router.py --node sdtm-dm-mapping --adjacency
# Expected: Shows predecessors (raw-data-validation, spec-creation) and successors

# Test 3: Context loader estimates tokens
python scripts/context-loader.py --node sdtm-dm-mapping --estimate
# Expected: < 3000 tokens

# Test 4: JSON output is valid
python scripts/graph-router.py --node sdtm-dm-mapping --json | python -m json.tool
# Expected: Valid JSON with all expected fields
```

### Manual Verification

1. **Run `/workflow skills`** at different positions — verify 3-8 skills shown, not all 55
2. **Check token savings** — compare full context load vs router-filtered
3. **Test edge cases** — missing state, invalid node ID, first/last nodes

---

## Estimated Complexity: MEDIUM

| Component | Effort |
|-----------|--------|
| graph-router.py | 2-3 hours |
| context-loader.py | 1-2 hours |
| workflow SKILL.md updates | 1 hour |
| Testing & verification | 1 hour |
| **Total** | **5-7 hours** |

---

## File Change Summary

### New Files (2)
| Path | Purpose |
|------|---------|
| `scripts/graph-router.py` | Token-efficient skill routing |
| `scripts/context-loader.py` | Minimal-token context builder |

### Modified Files (1)
| Path | Changes |
|------|---------|
| `skill-sources/workflow/SKILL.md` | Integrate graph-router, add /workflow context command |

---

**WAITING FOR CONFIRMATION**: Proceed with this plan? (yes/no/modify)
