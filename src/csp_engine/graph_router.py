"""
CSP Engine — Graph Router Module

Re-exports from scripts/graph-router.py for package-level imports.

Usage:
    from csp_engine.graph_router import GraphLoader, AdjacencyCalculator
"""

import sys
import importlib
from pathlib import Path

# Add project root to path
_project_root = Path(__file__).resolve().parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

# Import from hyphenated filename using importlib
_scripts_dir = _project_root / "scripts"
_spec = importlib.util.spec_from_file_location(
    "graph_router_impl", str(_scripts_dir / "graph-router.py")
)
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)

# Re-export classes
GraphLoader = _module.GraphLoader
StateReader = _module.StateReader
AdjacencyCalculator = _module.AdjacencyCalculator
OutputFormatter = _module.OutputFormatter

__all__ = [
    "GraphLoader",
    "StateReader",
    "AdjacencyCalculator",
    "OutputFormatter",
]
