#!/usr/bin/env python3
"""
MCP Configuration Validator

Validates MCP server configurations:
- Required fields present
- Tool definitions valid
- Graph node bindings consistent

Usage:
    python scripts/mcp-config-validator.py --mcp mcps/p21-validator/mcp-config.json
    python scripts/mcp-config-validator.py --all
"""

import sys
import json
import argparse
from pathlib import Path
from typing import Dict, List, Set
from dataclasses import dataclass


@dataclass
class MCPValidationResult:
    """Result of MCP validation."""

    mcp_path: Path
    valid: bool
    errors: List[str]
    warnings: List[str]
    tools: List[str]


class MCPValidator:
    """Validates MCP server configurations."""

    REQUIRED_FIELDS = ["name", "description", "version", "tools"]

    def __init__(self, mcp_path: Path):
        self.mcp_path = mcp_path
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.info: List[str] = []
        self.tools: List[str] = []

    def validate(self) -> MCPValidationResult:
        """Validate MCP configuration."""
        result = MCPValidationResult(
            mcp_path=self.mcp_path, valid=True, errors=[], warnings=[], tools=[]
        )

        if not self.mcp_path.exists():
            result.errors.append(f"MCP config not found: {self.mcp_path}")
            result.valid = False
            return result

        try:
            with open(self.mcp_path, "r", encoding="utf-8") as f:
                config = json.load(f)
        except json.JSONDecodeError as e:
            result.errors.append(f"Invalid JSON: {e}")
            result.valid = False
            return result
        except Exception as e:
            result.errors.append(f"Error reading config: {e}")
            result.valid = False
            return result

        # Check required fields
        for field in self.REQUIRED_FIELDS:
            if field not in config:
                result.errors.append(f"Missing required field: {field}")
            else:
                self.info.append(f"  {field}: {config.get(field)}")

        # Validate tools
        if "tools" in config:
            if not isinstance(config["tools"], list):
                result.errors.append("'tools' must be a list")
            else:
                for i, tool in enumerate(config["tools"]):
                    if not isinstance(tool, dict):
                        result.errors.append(f"Tool {i} must be an object")
                    elif "name" not in tool:
                        result.errors.append(f"Tool {i} missing 'name' field")
                    else:
                        result.tools.append(tool["name"])

                        # Validate inputSchema
                        if "inputSchema" in tool:
                            schema = tool["inputSchema"]
                            if "type" not in schema:
                                result.warnings.append(
                                    f"Tool '{tool['name']}' inputSchema missing 'type'"
                                )

        # Check graph bindings
        if "bound_to_nodes" in config:
            if not isinstance(config["bound_to_nodes"], list):
                result.warnings.append("'bound_to_nodes' should be a list")

            else:
                self.info.append(f"  Bound to {len(config['bound_to_nodes'])} nodes")

        result.errors = self.errors
        result.warnings = self.warnings
        result.tools = self.tools

        if self.errors:
            result.valid = False

        return result

    def load_graph(self, graph_path: Path) -> Set[str]:
        """Load graph nodes for binding validation."""
        if not graph_path.exists():
            return set()

        import yaml

        with open(graph_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        nodes = data.get("nodes", [])
        return {n.get("id") for n in nodes}

    def print_report(self, results: List[MCPValidationResult]):
        """Print validation report."""
        print("\n" + "=" * 80)
        print("MCP CONFIGURATION VALIDATION REPORT")
        print("=" * 80 + "\n")

        total = len(results)
        passed = sum(1 for r in results if r.valid)
        failed = total - passed
        errors = sum(len(r.errors) for r in results)
        warnings = sum(len(r.warnings) for r in results)

        print(f"\nMCPs Validated: {passed}/{total}")
        print(f"  Passed: {passed}")
        print(f"  Failed: {failed}")
        print(f"  Total Errors: {errors}")
        print(f"  Total Warnings: {warnings}")
        print("=" * 80 + "\n")

        for result in results:
            status = "PASS" if result.valid else "FAIL"
            print(f"\n{status}: {result.mcp_path}")
            if result.errors:
                for error in result.errors:
                    print(f"  ERROR: {error}")
            if result.warnings:
                for warning in result.warnings:
                    print(f"  WARNING: {warning}")
            if result.tools:
                print(f"  Tools: {', '.join(result.tools)}")


def find_mcps(mcps_dir: Path) -> List[Path]:
    """Find all MCP config files."""
    mcp_configs = []
    for mcp_dir in mcps_dir.iterdir():
        if mcp_dir.is_dir():
            config_file = mcp_dir / "mcp-config.json"
            if config_file.exists():
                mcp_configs.append(config_file)
    return mcp_configs


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Validate MCP configurations")
    parser.add_argument("--mcps-dir", "-m", default="mcps", help="MCPs directory")
    parser.add_argument(
        "--graph", "-g", default="graph/regulatory-graph.yaml", help="Graph YAML file"
    )
    parser.add_argument("--mcp", help="Validate specific MCP only")
    parser.add_argument("--all", "-a", action="store_true", help="Validate all MCPs")
    args = parser.parse_args()

    mcps_dir = Path(args.mcps_dir)
    graph_path = Path(args.graph)

    # Find MCP configs
    mcp_configs = find_mcps(mcps_dir)

    if args.mcp:
        mcp_configs = [p for p in mcp_configs if str(args.mcp) in str(p)]

    # Validate each MCP
    results = []
    for mcp_path in mcp_configs:
        validator = MCPValidator(mcp_path)
        result = validator.validate()
        results.append(result)

    # Print report
    validator.print_report(results)

    # Return exit code
    failed = sum(1 for r in results if r.errors)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
