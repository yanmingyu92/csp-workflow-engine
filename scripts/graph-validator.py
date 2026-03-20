#!/usr/bin/env python3
"""
Regulatory Task Graph Validator

Validates the DAG structure, node fields, edge types, and layer consistency
for clinical trial statistical programming workflow graphs.

Usage:
    python scripts/graph-validator.py graph/regulatory-graph.yaml
    python scripts/graph-validator.py graph/regulatory-graph.yaml graph/graph-layers.yaml
"""

import sys
import json
import yaml
from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional, Any
from collections import defaultdict, deque


class ValidationReport:
    """Collects and formats validation results."""

    def __init__(self):
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.info: List[str] = []
        self.stats: Dict[str, int] = {}

    def add_error(self, msg: str):
        """Add a blocking error."""
        self.errors.append(msg)

    def add_warning(self, msg: str):
        """Add a non-blocking warning/recommendation."""
        self.warnings.append(msg)

    def add_info(self, msg: str):
        """Add informational message."""
        self.info.append(msg)

    def set_stat(self, key: str, value: int):
        """Set a statistic value."""
        self.stats[key] = value

    def has_errors(self) -> bool:
        """Check if any errors were recorded."""
        return len(self.errors) > 0

    def print_report(self) -> bool:
        """Print formatted validation report. Returns True if has errors."""
        print("\n" + "=" * 80)
        print("REGULATORY TASK GRAPH VALIDATION REPORT")
        print("=" * 80)

        # Statistics
        if self.stats:
            print("\n## STATISTICS")
            print("-" * 80)
            for key, value in sorted(self.stats.items()):
                label = key.replace("_", " ").title()
                print(f"  {label:<40} {value}")

        # Errors (blocking)
        print("\n## ERRORS (BLOCKING)")
        print("-" * 80)
        if self.errors:
            for i, error in enumerate(self.errors, 1):
                print(f"  [{i}] {error}")
        else:
            print("  None - All validations passed!")

        # Warnings (recommendations)
        print("\n## WARNINGS (RECOMMENDATIONS)")
        print("-" * 80)
        if self.warnings:
            for i, warning in enumerate(self.warnings, 1):
                print(f"  [{i}] {warning}")
        else:
            print("  None - No recommendations!")

        # Summary
        print("\n## SUMMARY")
        print("-" * 80)
        status = "FAILED" if self.has_errors() else "PASSED"
        status_symbol = "X" if self.has_errors() else "OK"
        print(f"  Status: [{status_symbol}] {status}")
        print(f"  Total Errors: {len(self.errors)}")
        print(f"  Total Warnings: {len(self.warnings)}")
        print("=" * 80 + "\n")

        return self.has_errors()


class GraphValidator:
    """Validates regulatory task graph structure and consistency."""

    VALID_EDGE_TYPES = {"requires", "enables", "validates"}
    REQUIRED_NODE_FIELDS = {"id", "name", "layer", "description"}
    VALID_LAYERS = set(range(7))  # 0-6

    def __init__(self, graph_path: str, layers_path: Optional[str] = None):
        """Initialize validator with file paths."""
        self.graph_path = Path(graph_path)
        self.layers_path = Path(layers_path) if layers_path else None
        self.report = ValidationReport()
        self.graph_data: Dict[str, Any] = {}
        self.layers_data: Dict[str, Any] = {}
        self.nodes: Dict[str, Dict] = {}
        self.edges: List[Tuple[str, str, str]] = []  # (from, to, edge_type)
        self.adjacency: Dict[str, Set[str]] = defaultdict(set)
        self.reverse_adjacency: Dict[str, Set[str]] = defaultdict(set)

    def load_files(self) -> bool:
        """Load YAML files. Returns False on critical error."""
        try:
            with open(self.graph_path, "r", encoding="utf-8") as f:
                self.graph_data = yaml.safe_load(f)
            self.report.add_info(f"Loaded graph: {self.graph_path}")
        except FileNotFoundError:
            self.report.add_error(f"Graph file not found: {self.graph_path}")
            return False
        except yaml.YAMLError as e:
            self.report.add_error(f"Invalid YAML in graph file: {e}")
            return False
        except Exception as e:
            self.report.add_error(f"Failed to load graph file: {e}")
            return False

        if self.layers_path and self.layers_path.exists():
            try:
                with open(self.layers_path, "r", encoding="utf-8") as f:
                    self.layers_data = yaml.safe_load(f)
                self.report.add_info(f"Loaded layers: {self.layers_path}")
            except Exception as e:
                self.report.add_warning(
                    f"Failed to load layers file (will skip layer validation): {e}"
                )
                self.layers_data = {}

        return True

    def validate_dag_structure(self) -> bool:
        """Validate DAG structure: cycles, dependencies, edge types.

        Returns True if valid, False otherwise.
        """
        print("  [1/3] Validating DAG structure...")

        # Extract nodes
        if "nodes" not in self.graph_data:
            self.report.add_error("No 'nodes' section found in graph")
            return False

        # Build node map
        for node in self.graph_data["nodes"]:
            if not isinstance(node, dict):
                self.report.add_error(f"Invalid node format (expected dict): {node}")
                continue

            node_id = node.get("id")
            if not node_id:
                self.report.add_error(f"Node missing 'id' field: {node}")
                continue

            if node_id in self.nodes:
                self.report.add_error(f"Duplicate node ID: '{node_id}'")
                continue

            self.nodes[node_id] = node

        # Extract edges from dependencies
        for node_id, node in self.nodes.items():
            dependencies = node.get("dependencies", [])

            if not isinstance(dependencies, list):
                self.report.add_error(f"Node '{node_id}' dependencies must be a list")
                continue

            for dep in dependencies:
                if not isinstance(dep, dict):
                    self.report.add_error(
                        f"Invalid dependency format in node '{node_id}': {dep}"
                    )
                    continue

                dep_node = dep.get("node")
                edge_type = dep.get("edge_type")

                if not dep_node:
                    self.report.add_error(
                        f"Dependency missing 'node' field in '{node_id}': {dep}"
                    )
                    continue

                if not edge_type:
                    self.report.add_error(
                        f"Dependency missing 'edge_type' in '{node_id}': {dep}"
                    )
                    continue

                # Check if dependency node exists
                if dep_node not in self.nodes:
                    self.report.add_error(
                        f"Node '{node_id}' depends on non-existent node '{dep_node}'"
                    )
                    continue

                # Validate edge type
                if edge_type not in self.VALID_EDGE_TYPES:
                    self.report.add_error(
                        f"Invalid edge type '{edge_type}' from '{dep_node}' to '{node_id}'. "
                        f"Valid types: {', '.join(sorted(self.VALID_EDGE_TYPES))}"
                    )
                    continue

                # Check for self-loops
                if dep_node == node_id:
                    self.report.add_error(
                        f"Self-loop detected: node '{node_id}' depends on itself"
                    )
                    continue

                # Store edge
                self.edges.append((dep_node, node_id, edge_type))
                self.adjacency[dep_node].add(node_id)
                self.reverse_adjacency[node_id].add(dep_node)

        # Check for cycles using Kahn's algorithm (topological sort)
        cycle_detected = self._detect_cycles()

        if cycle_detected:
            self.report.add_error("Graph contains cycles - not a valid DAG")
            return False
        else:
            self.report.add_info("DAG validation: No cycles detected (valid DAG)")

        return True

    def _detect_cycles(self) -> bool:
        """Detect cycles using Kahn's algorithm (topological sort).

        Returns True if cycle detected, False otherwise.
        """
        # Calculate in-degrees
        in_degree = {node_id: 0 for node_id in self.nodes}
        for node_id in self.nodes:
            in_degree[node_id] = len(self.reverse_adjacency[node_id])

        # Initialize queue with nodes having no incoming edges
        queue = deque([node_id for node_id in self.nodes if in_degree[node_id] == 0])
        visited_count = 0
        topological_order = []

        # Process nodes
        while queue:
            current = queue.popleft()
            topological_order.append(current)
            visited_count += 1

            # Reduce in-degree of neighbors
            for neighbor in self.adjacency[current]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        # If we didn't visit all nodes, there's a cycle
        has_cycle = visited_count != len(self.nodes)

        if has_cycle:
            # Find nodes involved in cycle
            unvisited = [node_id for node_id in self.nodes if in_degree[node_id] > 0]
            self.report.add_error(
                f"Cycle detected! Nodes in cycle: {', '.join(sorted(unvisited))}"
            )

        return has_cycle

    def validate_node_structure(self) -> bool:
        """Validate node structure and required fields.

        Returns True if valid, False otherwise.
        """
        print("  [2/3] Validating node structure...")

        all_valid = True

        for node_id, node in self.nodes.items():
            # Check required fields
            missing_fields = self.REQUIRED_NODE_FIELDS - set(node.keys())
            if missing_fields:
                self.report.add_error(
                    f"Node '{node_id}' missing required fields: {', '.join(sorted(missing_fields))}"
                )
                all_valid = False

            # Validate layer value
            layer = node.get("layer")
            if layer is not None:
                if not isinstance(layer, int):
                    self.report.add_error(
                        f"Node '{node_id}' has non-integer layer: {layer}"
                    )
                    all_valid = False
                elif layer not in self.VALID_LAYERS:
                    self.report.add_error(
                        f"Node '{node_id}' has invalid layer '{layer}'. "
                        f"Must be integer in range 0-6"
                    )
                    all_valid = False

            # Validate skills naming convention
            skills = node.get("skills_bound", [])
            if not isinstance(skills, list):
                self.report.add_warning(
                    f"Node '{node_id}' skills_bound should be a list"
                )
            else:
                for skill in skills:
                    if not isinstance(skill, str):
                        self.report.add_warning(
                            f"Node '{node_id}' has non-string skill: {skill}"
                        )
                    elif not skill.startswith("/"):
                        self.report.add_warning(
                            f"Node '{node_id}' skill '{skill}' doesn't follow naming convention "
                            "(should start with '/')"
                        )

            # Validate MCPs naming convention
            mcps = node.get("mcps_bound", [])
            if not isinstance(mcps, list):
                self.report.add_warning(f"Node '{node_id}' mcps_bound should be a list")
            else:
                for mcp in mcps:
                    if not isinstance(mcp, str):
                        self.report.add_warning(
                            f"Node '{node_id}' has non-string MCP: {mcp}"
                        )

        return all_valid

    def validate_layer_consistency(self) -> bool:
        """Validate layer consistency between graph and layers files.

        Returns True if valid, False otherwise.
        """
        print("  [3/3] Validating layer consistency...")

        if not self.layers_data or "layers" not in self.layers_data:
            self.report.add_warning(
                "No layers data available - skipping layer consistency check"
            )
            return True

        valid = True

        # Extract nodes per layer from graph
        graph_layer_nodes: Dict[int, Set[str]] = defaultdict(set)
        for node_id, node in self.nodes.items():
            layer = node.get("layer")
            if layer is not None:
                graph_layer_nodes[layer].add(node_id)

        # Extract nodes per layer from layers file
        layers_map: Dict[int, Set[str]] = {}
        for layer_def in self.layers_data["layers"]:
            layer_id = layer_def.get("id")
            if layer_id is not None:
                layers_map[layer_id] = set(layer_def.get("nodes", []))

        # Check consistency for each layer
        all_layers = sorted(set(graph_layer_nodes.keys()) | set(layers_map.keys()))

        for layer_id in all_layers:
            graph_nodes = graph_layer_nodes.get(layer_id, set())
            layers_nodes = layers_map.get(layer_id, set())

            # Check for nodes in graph but not in layers file
            orphan_in_graph = graph_nodes - layers_nodes
            if orphan_in_graph:
                self.report.add_warning(
                    f"Layer {layer_id}: Nodes in graph but not in layers file: "
                    f"{', '.join(sorted(orphan_in_graph))}"
                )

            # Check for nodes in layers file but not in graph
            orphan_in_layers = layers_nodes - graph_nodes
            if orphan_in_layers:
                self.report.add_error(
                    f"Layer {layer_id}: Nodes in layers file but not in graph: "
                    f"{', '.join(sorted(orphan_in_layers))}"
                )
                valid = False

        # Check for any nodes in layers file that reference non-existent nodes
        all_layer_nodes = set()
        for nodes_set in layers_map.values():
            all_layer_nodes.update(nodes_set)

        undefined_nodes = all_layer_nodes - set(self.nodes.keys())
        if undefined_nodes:
            self.report.add_error(
                f"Layers file references undefined nodes: {', '.join(sorted(undefined_nodes))}"
            )
            valid = False

        return valid

    def generate_statistics(self):
        """Generate validation statistics."""
        self.report.set_stat("total_nodes", len(self.nodes))
        self.report.set_stat("total_edges", len(self.edges))

        # Count by edge type
        edge_type_counts: Dict[str, int] = defaultdict(int)
        for _, _, edge_type in self.edges:
            edge_type_counts[edge_type] += 1

        for edge_type in sorted(edge_type_counts.keys()):
            count = edge_type_counts[edge_type]
            self.report.set_stat(f"edges_{edge_type}", count)

        # Count nodes per layer
        layer_counts: Dict[int, int] = defaultdict(int)
        for node in self.nodes.values():
            layer = node.get("layer")
            if layer is not None:
                layer_counts[layer] += 1

        for layer in sorted(layer_counts.keys()):
            count = layer_counts[layer]
            self.report.set_stat(f"layer_{layer}_nodes", count)

    def validate(self) -> bool:
        """Run all validations. Returns True if valid, False otherwise."""
        print("=" * 80)
        print("REGULATORY TASK GRAPH VALIDATOR")
        print("=" * 80)
        print(f"\nGraph file: {self.graph_path}")
        if self.layers_path:
            print(f"Layers file: {self.layers_path}")
        print()

        # Load files
        if not self.load_files():
            self.report.print_report()
            return False

        print("\nRunning validations...")
        print("-" * 80)

        # Run validations
        dag_valid = self.validate_dag_structure()
        node_valid = self.validate_node_structure()
        layer_valid = self.validate_layer_consistency()

        # Generate statistics
        self.generate_statistics()

        # Print report
        has_errors = self.report.print_report()

        return not has_errors


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("=" * 80)
        print("REGULATORY TASK GRAPH VALIDATOR")
        print("=" * 80)
        print("\nUsage:")
        print("  python scripts/graph-validator.py <graph.yaml> [layers.yaml]")
        print("\nExample:")
        print("  python scripts/graph-validator.py graph/regulatory-graph.yaml")
        print(
            "  python scripts/graph-validator.py graph/regulatory-graph.yaml graph/graph-layers.yaml"
        )
        print("\nDescription:")
        print("  Validates the regulatory task graph structure, dependencies,")
        print("  node fields, edge types, and layer consistency.")
        print("=" * 80)
        sys.exit(1)

    graph_path = sys.argv[1]
    layers_path = sys.argv[2] if len(sys.argv) > 2 else None

    # Auto-detect layers file if not provided
    if not layers_path:
        graph_dir = Path(graph_path).parent
        default_layers = graph_dir / "graph-layers.yaml"
        if default_layers.exists():
            layers_path = str(default_layers)
            print(f"Auto-detected layers file: {layers_path}\n")

    validator = GraphValidator(graph_path, layers_path)
    success = validator.validate()

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
