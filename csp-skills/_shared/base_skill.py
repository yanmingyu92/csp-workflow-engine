#!/usr/bin/env python3
"""
Base CSP Skill Class

Foundation class for all Clinical Trial Statistical Programming skills.
Provides common patterns for:
- Configuration management
- Input/output handling
- Validation
- Error reporting
- Graph node binding
"""

import sys
import json
import yaml
import argparse
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
from enum import Enum


class SkillStatus(Enum):
    """Skill execution status."""

    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"
    SKIPPED = "skipped"
    DRY_RUN = "dry_run"


@dataclass
class SkillResult:
    """Result of skill execution."""

    status: SkillStatus
    message: str
    outputs: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "status": self.status.value,
            "message": self.message,
            "outputs": self.outputs,
            "errors": self.errors,
            "warnings": self.warnings,
            "metrics": self.metrics,
            "timestamp": self.timestamp,
        }

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=2)


@dataclass
class SkillConfig:
    """Configuration for skill execution."""

    input_path: Path
    output_path: Path
    spec_path: Optional[Path] = None
    study_config_path: Optional[Path] = None
    validate_only: bool = False
    dry_run: bool = False
    verbose: bool = False
    strict_mode: bool = False
    output_format: str = "xpt"

    @classmethod
    def from_args(cls, args: argparse.Namespace) -> "SkillConfig":
        """Create config from parsed arguments."""
        return cls(
            input_path=Path(args.input) if args.input else None,
            output_path=Path(args.output) if args.output else None,
            spec_path=Path(args.spec) if hasattr(args, "spec") and args.spec else None,
            study_config_path=(
                Path(args.study_config)
                if hasattr(args, "study_config") and args.study_config
                else None
            ),
            validate_only=getattr(args, "validate_only", False),
            dry_run=getattr(args, "dry_run", False),
            verbose=getattr(args, "verbose", False),
            strict_mode=getattr(args, "strict", False),
            output_format=getattr(args, "format", "xpt"),
        )


class BaseCSPSkill:
    """
    Base class for all CSP skills.

    Each skill should:
    1. Set GRAPH_NODE_ID to match regulatory-graph.yaml
    2. Set REQUIRED_INPUT_VARS for validation
    3. Set OUTPUT_VARS for output verification
    4. Implement run() method
    """

    # Override in subclasses
    GRAPH_NODE_ID: str = ""
    REQUIRED_INPUT_VARS: List[str] = []
    OUTPUT_VARS: List[str] = []
    SKILL_NAME: str = ""
    SKILL_VERSION: str = "1.0.0"

    def __init__(self, config: SkillConfig):
        """Initialize skill with configuration."""
        self.config = config
        self.spec: Dict[str, Any] = {}
        self.study_config: Dict[str, Any] = {}
        self.input_data: Dict[str, Any] = {}
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.metrics: Dict[str, Any] = {}

    def load_spec(self, path: Optional[Path] = None) -> Dict[str, Any]:
        """Load specification file (YAML or Excel)."""
        spec_path = path or self.config.spec_path
        if not spec_path:
            return {}

        if spec_path.suffix in [".yaml", ".yml"]:
            with open(spec_path, "r", encoding="utf-8") as f:
                self.spec = yaml.safe_load(f) or {}
        elif spec_path.suffix in [".xlsx", ".xls"]:
            # For Excel specs, we'd need openpyxl - return placeholder
            self.warnings.append(f"Excel spec loading not implemented: {spec_path}")
            self.spec = {}
        else:
            raise ValueError(f"Unsupported spec format: {spec_path.suffix}")

        return self.spec

    def load_study_config(self, path: Optional[Path] = None) -> Dict[str, Any]:
        """Load study configuration."""
        config_path = path or self.config.study_config_path
        if not config_path:
            return {}

        with open(config_path, "r", encoding="utf-8") as f:
            self.study_config = yaml.safe_load(f) or {}

        return self.study_config

    def validate_inputs(self) -> Tuple[bool, List[str]]:
        """
        Validate that all required inputs are present.

        Returns:
            Tuple of (is_valid, list of missing items)
        """
        missing = []

        # Check input path exists
        if self.config.input_path and not self.config.input_path.exists():
            missing.append(f"Input path does not exist: {self.config.input_path}")

        # Check required variables (override in subclass for specific validation)
        if self.REQUIRED_INPUT_VARS and self.input_data:
            for var in self.REQUIRED_INPUT_VARS:
                if var not in self.input_data:
                    missing.append(f"Required variable missing: {var}")

        return len(missing) == 0, missing

    def validate_outputs(self, output_data: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        Validate that all required outputs are present.

        Returns:
            Tuple of (is_valid, list of missing items)
        """
        missing = []

        for var in self.OUTPUT_VARS:
            if var not in output_data:
                missing.append(f"Required output variable missing: {var}")

        return len(missing) == 0, missing

    def log_error(self, message: str):
        """Log an error message."""
        self.errors.append(message)
        if self.config.verbose:
            print(f"[ERROR] {message}", file=sys.stderr)

    def log_warning(self, message: str):
        """Log a warning message."""
        self.warnings.append(message)
        if self.config.verbose:
            print(f"[WARN] {message}", file=sys.stderr)

    def log_info(self, message: str):
        """Log an info message (only in verbose mode)."""
        if self.config.verbose:
            print(f"[INFO] {message}")

    def run(self) -> SkillResult:
        """
        Execute the skill.

        Override in subclasses with specific implementation.

        Standard flow:
        1. Load specifications
        2. Load input data
        3. Validate inputs
        4. Execute mapping/transformation
        5. Validate outputs
        6. Write outputs
        """
        raise NotImplementedError("Subclasses must implement run()")

    def create_result(
        self,
        status: SkillStatus,
        message: str,
        outputs: Optional[Dict[str, Any]] = None,
    ) -> SkillResult:
        """Create a standardized skill result."""
        return SkillResult(
            status=status,
            message=message,
            outputs=outputs or {},
            errors=self.errors,
            warnings=self.warnings,
            metrics=self.metrics,
        )


def create_argument_parser(
    skill_name: str, description: str
) -> argparse.ArgumentParser:
    """Create standard argument parser for CSP skills."""
    parser = argparse.ArgumentParser(
        prog=f"csp-{skill_name}",
        description=description,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--input", "-i", required=True, help="Input file or directory path"
    )
    parser.add_argument(
        "--output", "-o", required=True, help="Output file or directory path"
    )
    parser.add_argument("--spec", "-s", help="Specification file path (YAML or Excel)")
    parser.add_argument("--study-config", help="Study configuration file path")
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Only validate inputs, do not produce output",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable verbose output"
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Enable strict mode (treat warnings as errors)",
    )
    parser.add_argument(
        "--format",
        "-f",
        choices=["xpt", "csv", "sas7bdat"],
        default="xpt",
        help="Output format (default: xpt)",
    )

    return parser


def main_wrapper(skill_class: type, skill_name: str, description: str):
    """
    Standard main function wrapper for CSP skills.

    Usage in script.py:
        if __name__ == "__main__":
            main_wrapper(MySkill, "my-skill", "My skill description")
    """
    parser = create_argument_parser(skill_name, description)
    args = parser.parse_args()

    config = SkillConfig.from_args(args)
    skill = skill_class(config)

    try:
        result = skill.run()

        # Output result
        print(result.to_json())

        # Exit with appropriate code
        if result.status == SkillStatus.ERROR:
            sys.exit(1)
        elif result.status == SkillStatus.WARNING and config.strict_mode:
            sys.exit(2)
        else:
            sys.exit(0)

    except Exception as e:
        error_result = SkillResult(
            status=SkillStatus.ERROR,
            message=f"Skill execution failed: {str(e)}",
            errors=[str(e)],
        )
        print(error_result.to_json())
        sys.exit(1)
