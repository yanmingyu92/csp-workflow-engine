"""
CSP Engine — Context Loader Module

Re-exports from scripts/context-loader.py for package-level imports.

Usage:
    from csp_engine.context_loader import ContextBuilder, AdaptivePriorityScheduler
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
    "context_loader_impl", str(_scripts_dir / "context-loader.py")
)
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)

# Re-export classes
PriorityBand = _module.PriorityBand
SkillInfo = _module.SkillInfo
ContextResult = _module.ContextResult
TokenEstimator = _module.TokenEstimator
SkillLocator = _module.SkillLocator
AdaptivePriorityScheduler = _module.AdaptivePriorityScheduler
ContextBuilder = _module.ContextBuilder

__all__ = [
    "PriorityBand",
    "SkillInfo",
    "ContextResult",
    "TokenEstimator",
    "SkillLocator",
    "AdaptivePriorityScheduler",
    "ContextBuilder",
]
