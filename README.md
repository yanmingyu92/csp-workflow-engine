# CSP Workflow Engine

**Graph-based regulatory workflow engine for clinical trial statistical programming.**

A workflow orchestration system that enforces regulatory compliance through typed skill binding, validation gates, and token-efficient context loading for AI-assisted clinical trial programming.

**v0.1.0** · Python 3.9+ · MIT License

---

## Overview

CSP Workflow Engine manages the complete clinical trial statistical programming pipeline from raw data through regulatory submission. It provides:

- **Regulatory graph navigation** - 7-layer workflow from Protocol to Submission
- **Typed skill binding** - Skills are bound to specific workflow nodes
- **Validation gates** - Quality checkpoints between workflow layers
- **Token-efficient context loading** - Only loads relevant skills for current node

---

## Regulatory Workflow Layers

| Layer | Phase | Description |
|-------|-------|-------------|
| 0 | Protocol & Planning | Study design, analysis plans |
| 1 | Raw Data Management | Data collection, cleaning |
| 2 | SDTM Creation | CDISC SDTM mapping |
| 3 | SDTM Quality Control | P21 validation, consistency checks |
| 4 | ADaM Creation | Analysis dataset derivation |
| 5 | TFL Generation | Tables, figures, listings |
| 6 | Define.xml & Submission | Regulatory package assembly |

---

## Core Components

### `evaluation.py`
Graph extension validation and completion checking. Validates that workflow extensions maintain regulatory compliance.

### `graph_router.py`
Token-efficient skill loading via adjacency. Only loads skills from current node and immediate neighbors to minimize context usage.

### `context_loader.py`
Adaptive priority token budget controller. Manages context window allocation for optimal AI performance.

### `graph_validator.py`
DAG structure and layer consistency validation. Ensures workflow graph is well-formed and follows regulatory ordering.

---

## Installation

```bash
pip install csp-workflow-engine
```

Or install from source:

```bash
git clone https://github.com/yanmingyu92/csp-workflow-engine.git
cd csp-workflow-engine
pip install -e .
```

---

## Quick Start

```python
from csp_engine import GraphValidator, GraphRouter

# Validate a workflow graph
validator = GraphValidator()
validator.validate("graph/regulatory-graph.yaml")

# Route to current workflow node
router = GraphRouter("graph/regulatory-graph.yaml")
router.activate_node("sdtm-dm-creation")
```

---

## Project Structure

```
csp-workflow-engine/
|-- src/csp_engine/           # Core engine modules
|   |-- __init__.py
|   |-- evaluation.py         # Graph extension validation
|   |-- graph_router.py       # Skill loading via adjacency
|   |-- context_loader.py     # Token budget control
|   +-- graph_validator.py    # DAG structure validation
|-- scripts/                  # CLI utilities
|   |-- evaluation.py
|   |-- graph-validator.py
|   |-- graph-router.py
|   +-- context-loader.py
|-- graph/                    # Workflow graph definitions
|-- reference/                # Schema and documentation
|   +-- workflow-schema.yaml  # Complete schema definition
|-- hooks/                    # Claude Code hooks
|-- skills/                   # Workflow skills
|-- skill-sources/            # Skill templates
+-- mcps/                     # MCP server configs
```

---

## Workflow Schema

The engine uses a typed schema for workflow definitions:

- **Workflow** - Top-level container with stages
- **Stage** - Ordered workflow phases with skills allowed/blocked
- **Validation Gate** - Quality checkpoints with pass conditions
- **Regulatory Node** - Task nodes with layer, skills, MCPs, inputs/outputs
- **Artifact** - Typed inputs/outputs (dataset, report, specification, etc.)

See `reference/workflow-schema.yaml` for the complete schema.

---

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/

# Validate a graph
python scripts/graph-validator.py graph/regulatory-graph.yaml
```

---

## License

MIT License - see [LICENSE](LICENSE) for details.
