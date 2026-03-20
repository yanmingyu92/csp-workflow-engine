"""
CSP Engine — Graph Validator Module

Re-exports from scripts/graph-validator.py for package-level imports.

Usage:
    from csp_engine.graph_validator import GraphValidator, ValidationReport
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
    "graph_validator_impl", str(_scripts_dir / "graph-validator.py")
)
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)

# Re-export classes
ValidationReport = _module.ValidationReport
GraphValidator = _module.GraphValidator

__all__ = [
    "ValidationReport",
    "GraphValidator",
]
