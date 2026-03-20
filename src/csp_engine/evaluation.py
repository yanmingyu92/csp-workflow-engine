"""
CSP Engine — Evaluation Module

Re-exports from scripts/evaluation.py for package-level imports.

Usage:
    from csp_engine.evaluation import GraphEvaluator, PatternValidator
    from csp_engine.evaluation import EvaluationResult, CompletionResult
"""

import sys
from pathlib import Path

# Add project root to path so scripts/ is importable
_project_root = Path(__file__).resolve().parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from scripts.evaluation import (  # noqa: E402
    GraphEvaluator,
    PatternValidator,
    EvaluationResult,
    CompletionResult,
    CheckResult,
    print_evaluation_report,
    print_completion_report,
)

__all__ = [
    "GraphEvaluator",
    "PatternValidator",
    "EvaluationResult",
    "CompletionResult",
    "CheckResult",
    "print_evaluation_report",
    "print_completion_report",
]
