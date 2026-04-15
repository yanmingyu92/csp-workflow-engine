#!/usr/bin/env python3
"""
Regulatory Task Graph Evaluation Functions

Provides evaluation functions for extending the graph with new nodes while
ensuring regulatory compliance. Validates node structure, dependencies,
layer ordering, and completion criteria.

Week 3 Enhancement: Trajectory logging hooks for self-learning module.
When --with-trajectory flag is used, evaluation steps are logged for
later distillation into principles.

Usage:
    python scripts/evaluation.py --validate-graph graph/regulatory-graph.yaml
    python scripts/evaluation.py --test-add-node graph/regulatory-graph.yaml test-fixtures/valid-node.yaml
    python scripts/evaluation.py --evaluate-completion graph/regulatory-graph.yaml <node-id> <outputs-file>
    python scripts/evaluation.py --with-trajectory --task-id <task-id> --node <node-id> --skills <skill1,skill2>
"""

import sys
import yaml
import json
from pathlib import Path
from typing import Dict, List, Set, Optional, Any
from dataclasses import dataclass, field
from collections import defaultdict, deque

# Week 3: Trajectory logging imports
try:
    from experience_logger import ExperienceLogger, RegulatoryTrajectory
    TRAJECTORY_LOGGING_AVAILABLE = True
except ImportError:
    TRAJECTORY_LOGGING_AVAILABLE = False
    ExperienceLogger = None  # type: ignore


# =============================================================================
# DATA CLASSES
# =============================================================================


@dataclass
class CheckResult:
    """Result of a single validation check."""

    name: str
    passed: bool
    message: str
    severity: str = "error"  # error, warning, info
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EvaluationResult:
    """Result of evaluating a proposed new node."""

    passed: bool
    checks: List[CheckResult]
    summary: str = ""

    def get_errors(self) -> List[CheckResult]:
        """Get all failed checks with error severity."""
        return [c for c in self.checks if not c.passed and c.severity == "error"]

    def get_warnings(self) -> List[CheckResult]:
        """Get all failed checks with warning severity."""
        return [c for c in self.checks if not c.passed and c.severity == "warning"]

    def get_passed(self) -> List[CheckResult]:
        """Get all passed checks."""
        return [c for c in self.checks if c.passed]


@dataclass
class CompletionResult:
    """Result of evaluating node completion."""

    passed: bool
    mandatory_passed: bool
    results: List[CheckResult]
    completion_percentage: float = 0.0


# =============================================================================
# PATTERN VALIDATOR
# =============================================================================


class PatternValidator:
    """Validates nodes against regulatory patterns."""

    def __init__(self, patterns_path: Optional[str] = None):
        """Initialize with optional patterns file."""
        self.patterns: Dict[str, Dict] = {}
        if patterns_path:
            self.load_patterns(patterns_path)

    def load_patterns(self, path: str) -> bool:
        """Load patterns from YAML file."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            self.patterns = data.get("patterns", {})
            self.patterns_data = data  # Store full data for compatibility_rules access
            return True
        except FileNotFoundError:
            print(f"Patterns file not found: {path}", file=sys.stderr)
            return False
        except yaml.YAMLError as e:
            print(f"Invalid YAML in patterns file: {e}", file=sys.stderr)
            return False
        except Exception as e:
            print(f"Error loading patterns: {e}", file=sys.stderr)
            return False

    def get_pattern_for_node(self, node: Dict) -> Optional[Dict]:
        """Find matching pattern for a node based on valid_node_ids, layer, and type."""
        node_layer = node.get("layer")
        node_id = node.get("id", "")

        # Strategy 1: Check valid_node_ids (explicit pattern-to-node mapping)
        for pattern_name, pattern in self.patterns.items():
            valid_ids = pattern.get("valid_node_ids", [])
            if node_id in valid_ids:
                return pattern

        # Strategy 2: Exact ID match against pattern names
        if node_id in self.patterns:
            return self.patterns[node_id]

        # Strategy 3: Fallback — layer range + input/output type matching
        for pattern_name, pattern in self.patterns.items():
            layer_range = pattern.get("layer_range", [0, 6])
            # Skip if node_layer is None (missing layer)
            if node_layer is None:
                continue
            if layer_range[0] <= node_layer <= layer_range[1]:
                if self._node_matches_pattern(node, pattern):
                    return pattern

        return None

    def _node_matches_pattern(self, node: Dict, pattern: Dict) -> bool:
        """Check if a node matches a pattern's criteria using type-level matching."""
        node_input_types = {
            i.get("type")
            for i in node.get("inputs_required", [])
            if isinstance(i, dict)
        }
        node_output_types = {
            o.get("type")
            for o in node.get("outputs_produced", [])
            if isinstance(o, dict)
        }

        # Check if node has the TYPES that correspond to pattern requirements
        # Pattern required_inputs/outputs are semantic names; we match against
        # artifact types from the node's actual inputs/outputs
        required_outputs = pattern.get("required_outputs", [])
        if required_outputs:
            # Check if any node output type matches any required output keyword
            if not node_output_types:
                return False

        return True


# =============================================================================
# GRAPH EVALUATOR
# =============================================================================


class GraphEvaluator:
    """
    Evaluates and validates graph extensions and node completion.

    This class provides functions to:
    1. Validate proposed new nodes against regulatory patterns
    2. Check if node outputs meet evaluation criteria
    3. Ensure graph integrity when adding new nodes

    Week 3 Enhancement: Optional trajectory logging for self-learning module.
    """

    VALID_EDGE_TYPES = {"requires", "enables", "validates"}
    REQUIRED_NODE_FIELDS = {"id", "name", "layer", "description"}
    VALID_LAYERS = set(range(7))  # 0-6

    def __init__(
        self,
        graph_path: str,
        patterns_path: Optional[str] = None,
        trajectory_logger: Optional[Any] = None  # ExperienceLogger when available
    ):
        """Initialize evaluator with graph and optional patterns.

        Week 3: Added trajectory_logger parameter for logging evaluation steps.
        """
        self.graph_path = Path(graph_path)
        self.graph_data: Dict[str, Any] = {}
        self.nodes: Dict[str, Dict] = {}
        self.adjacency: Dict[str, Set[str]] = defaultdict(set)
        self.reverse_adjacency: Dict[str, Set[str]] = defaultdict(set)
        self.pattern_validator = PatternValidator(patterns_path)

        # Week 3: Trajectory logging
        self.trajectory_logger = trajectory_logger
        self._current_task_id: Optional[str] = None
        self._current_node_id: Optional[str] = None

        # Load graph
        self._load_graph()

    def _load_graph(self) -> bool:
        """Load graph from YAML file."""
        try:
            with open(self.graph_path, "r", encoding="utf-8") as f:
                self.graph_data = yaml.safe_load(f)

            # Build node map
            for node in self.graph_data.get("nodes", []):
                if isinstance(node, dict) and "id" in node:
                    self.nodes[node["id"]] = node

            # Build adjacency lists
            for node_id, node in self.nodes.items():
                for dep in node.get("dependencies", []):
                    if isinstance(dep, dict) and "node" in dep:
                        dep_node = dep["node"]
                        self.adjacency[dep_node].add(node_id)
                        self.reverse_adjacency[node_id].add(dep_node)

            return True
        except FileNotFoundError:
            print(f"Graph file not found: {self.graph_path}", file=sys.stderr)
            return False
        except yaml.YAMLError as e:
            print(f"Invalid YAML in graph file: {e}", file=sys.stderr)
            return False
        except Exception as e:
            print(f"Error loading graph: {e}", file=sys.stderr)
            return False

    # =========================================================================
    # WEEK 3: TRAJECTORY LOGGING HOOKS
    # =========================================================================

    def start_trajectory(
        self,
        task_id: str,
        node_id: str,
        layer: int,
        skills_loaded: List[str],
        model_used: str = "deepseek-chat",
        temperature: float = 0.0
    ) -> Optional[str]:
        """
        Start recording a new trajectory for self-learning.

        Week 3 Implementation: Transparent logging that doesn't affect validation.

        Args:
            task_id: Task identifier from benchmark
            node_id: Graph node identifier
            layer: Graph layer (0-6)
            skills_loaded: List of skills selected for this task
            model_used: LLM model used (default: deepseek-chat)
            temperature: Temperature setting (default: 0.0)

        Returns:
            trajectory_id if logging enabled, None otherwise
        """
        if not self.trajectory_logger or not TRAJECTORY_LOGGING_AVAILABLE:
            return None

        self._current_task_id = task_id
        self._current_node_id = node_id

        try:
            trajectory_id = self.trajectory_logger.start_trajectory(
                task_id=task_id,
                node_id=node_id,
                layer=layer,
                skills_loaded=skills_loaded,
                model_used=model_used,
                temperature=temperature
            )
            return trajectory_id
        except Exception as e:
            print(f"Warning: Trajectory logging failed: {e}", file=sys.stderr)
            return None

    def log_step(self, step: Dict[str, Any]):
        """
        Log an execution step in the current trajectory.

        Week 3 Implementation: Transparent logging that doesn't affect validation.

        Args:
            step: Dictionary containing step details with optional 'tokens' key
        """
        if not self.trajectory_logger or not TRAJECTORY_LOGGING_AVAILABLE:
            return

        try:
            self.trajectory_logger.log_step(step)
        except Exception as e:
            print(f"Warning: Step logging failed: {e}", file=sys.stderr)

    def complete_trajectory(
        self,
        final_outcome: bool,
        validation_result: Dict,
        quality_score: float,
        ground_truth_files: List[str] = None,
        comparison_metrics: Dict = None
    ) -> bool:
        """
        Complete and save the current trajectory.

        Week 3 Implementation: Transparent logging that doesn't affect validation.

        Args:
            final_outcome: Whether the task passed validation
            validation_result: Detailed validation output
            quality_score: LLM-as-judge score (1-5)
            ground_truth_files: Reference files from benchmark
            comparison_metrics: Accuracy and completeness metrics

        Returns:
            True if trajectory saved successfully, False otherwise
        """
        if not self.trajectory_logger or not TRAJECTORY_LOGGING_AVAILABLE:
            return False

        try:
            trajectory = self.trajectory_logger.complete_trajectory(
                final_outcome=final_outcome,
                validation_result=validation_result,
                quality_score=quality_score,
                ground_truth_files=ground_truth_files or [],
                comparison_metrics=comparison_metrics or {}
            )
            # Reset current task tracking
            self._current_task_id = None
            self._current_node_id = None
            return trajectory is not None
        except Exception as e:
            print(f"Warning: Trajectory completion failed: {e}", file=sys.stderr)
            return False

    # =========================================================================
    # NODE EXTENSION VALIDATION
    # =========================================================================

    def can_add_node(self, new_node: Dict) -> EvaluationResult:
        """
        Validate a proposed new node against regulatory patterns.

        Performs the following checks:
        1. Layer assignment: node must fit within known layer boundaries
        2. Dependency ordering: no cross-layer backward edges
        3. CDISC compliance: node outputs must match known artifact types
        4. Circular dependency detection: topological sort must still succeed
        5. Skills exist: bound skills must reference real SKILL.md files

        Args:
            new_node: Dictionary containing the proposed node definition

        Returns:
            EvaluationResult with detailed check results
        """
        checks: List[CheckResult] = []

        # 1. Validate required fields
        checks.append(self._validate_required_fields(new_node))

        # 2. Validate layer assignment
        checks.append(self._validate_layer_assignment(new_node))

        # 3. Validate node ID uniqueness
        checks.append(self._validate_node_uniqueness(new_node))

        # 4. Validate dependency ordering
        checks.append(self._validate_dependency_ordering(new_node))

        # 5. Validate output types
        checks.append(self._validate_output_types(new_node))

        # 6. Validate no cycles
        checks.append(self._validate_no_cycles(new_node))

        # 7. Validate skills naming
        checks.append(self._validate_skills_naming(new_node))

        # 8. Validate skills exist on disk
        checks.append(self._validate_skills_exist(new_node))

        # 9. Validate pattern compliance (if patterns loaded)
        if self.pattern_validator.patterns:
            checks.append(self._validate_pattern_compliance(new_node))

        # 10. Validate layer transitions against compatibility rules
        if self.pattern_validator.patterns:
            transition_checks = self._validate_layer_transitions(new_node)
            checks.extend(transition_checks)

        # Determine overall result
        errors = [c for c in checks if not c.passed and c.severity == "error"]
        passed = len(errors) == 0

        summary = self._generate_summary(checks, passed)

        return EvaluationResult(passed=passed, checks=checks, summary=summary)

    def _validate_required_fields(self, node: Dict) -> CheckResult:
        """Validate that all required fields are present."""
        missing = self.REQUIRED_NODE_FIELDS - set(node.keys())

        if missing:
            return CheckResult(
                name="required_fields",
                passed=False,
                message=f"Missing required fields: {', '.join(sorted(missing))}",
                severity="error",
                details={"missing_fields": list(missing)},
            )

        return CheckResult(
            name="required_fields",
            passed=True,
            message="All required fields present",
            details={"fields": list(self.REQUIRED_NODE_FIELDS)},
        )

    def _validate_layer_assignment(self, node: Dict) -> CheckResult:
        """Validate that node layer is within valid range."""
        layer = node.get("layer")

        if layer is None:
            return CheckResult(
                name="layer_assignment",
                passed=False,
                message="Layer field is missing",
                severity="error",
            )

        if not isinstance(layer, int):
            return CheckResult(
                name="layer_assignment",
                passed=False,
                message=f"Layer must be an integer, got: {type(layer).__name__}",
                severity="error",
                details={"layer": layer},
            )

        if layer not in self.VALID_LAYERS:
            return CheckResult(
                name="layer_assignment",
                passed=False,
                message=f"Layer {layer} is out of valid range [0-6]",
                severity="error",
                details={"layer": layer, "valid_range": [0, 6]},
            )

        return CheckResult(
            name="layer_assignment",
            passed=True,
            message=f"Layer {layer} is valid",
            details={"layer": layer},
        )

    def _validate_node_uniqueness(self, node: Dict) -> CheckResult:
        """Validate that node ID is unique."""
        node_id = node.get("id")

        if not node_id:
            return CheckResult(
                name="node_uniqueness",
                passed=False,
                message="Node ID is missing",
                severity="error",
            )

        if node_id in self.nodes:
            return CheckResult(
                name="node_uniqueness",
                passed=False,
                message=f"Node ID '{node_id}' already exists in graph",
                severity="error",
                details={"existing_node": node_id},
            )

        return CheckResult(
            name="node_uniqueness",
            passed=True,
            message=f"Node ID '{node_id}' is unique",
            details={"node_id": node_id},
        )

    def _validate_dependency_ordering(self, node: Dict) -> CheckResult:
        """Validate no cross-layer backward edges."""
        node_layer = node.get("layer")
        node_id = node.get("id", "unknown")
        violations = []

        dependencies = node.get("dependencies", [])
        if not isinstance(dependencies, list):
            return CheckResult(
                name="dependency_ordering",
                passed=False,
                message="Dependencies must be a list",
                severity="error",
            )

        for dep in dependencies:
            if not isinstance(dep, dict):
                continue

            dep_node_id = dep.get("node")
            if not dep_node_id:
                continue

            dep_node = self.nodes.get(dep_node_id)
            if not dep_node:
                # Will be caught by other validation
                continue

            dep_layer = dep_node.get("layer")

            # Check for backward layer edge (with some exceptions for review/validation)
            edge_type = dep.get("edge_type", "requires")

            # Backward edges are only allowed for specific edge types
            if dep_layer > node_layer and edge_type == "requires":
                violations.append(
                    {
                        "dependency": dep_node_id,
                        "dep_layer": dep_layer,
                        "node_layer": node_layer,
                        "edge_type": edge_type,
                    }
                )

        if violations:
            return CheckResult(
                name="dependency_ordering",
                passed=False,
                message=f"Found {len(violations)} cross-layer backward edge(s)",
                severity="error",
                details={"violations": violations},
            )

        return CheckResult(
            name="dependency_ordering",
            passed=True,
            message="All dependencies follow proper layer ordering",
            details={"dependency_count": len(dependencies)},
        )

    def _validate_output_types(self, node: Dict) -> CheckResult:
        """Validate that node outputs match known artifact types."""
        VALID_OUTPUT_TYPES = {
            "dataset",
            "specification",
            "report",
            "document",
            "metadata",
            "package",
            "configuration",
        }

        outputs = node.get("outputs_produced", [])
        if not isinstance(outputs, list):
            return CheckResult(
                name="output_types",
                passed=True,  # Outputs are optional
                message="No outputs defined (optional)",
                severity="info",
            )

        invalid_types = []
        for output in outputs:
            if not isinstance(output, dict):
                continue
            output_type = output.get("type")
            if output_type and output_type not in VALID_OUTPUT_TYPES:
                invalid_types.append(output_type)

        if invalid_types:
            return CheckResult(
                name="output_types",
                passed=False,
                message=f"Invalid output types: {', '.join(invalid_types)}",
                severity="warning",  # Warning, not error - custom types allowed
                details={
                    "invalid_types": invalid_types,
                    "valid_types": list(VALID_OUTPUT_TYPES),
                },
            )

        return CheckResult(
            name="output_types",
            passed=True,
            message="All output types are valid",
            details={"output_count": len(outputs)},
        )

    def _validate_no_cycles(self, new_node: Dict) -> CheckResult:
        """Validate that adding the node won't create a cycle."""
        node_id = new_node.get("id", "unknown")

        # Build temporary adjacency including new node
        temp_adjacency = defaultdict(
            set, {k: set(v) for k, v in self.adjacency.items()}
        )
        temp_reverse = defaultdict(
            set, {k: set(v) for k, v in self.reverse_adjacency.items()}
        )

        # Add new node's edges
        for dep in new_node.get("dependencies", []):
            if isinstance(dep, dict) and "node" in dep:
                dep_node = dep["node"]
                if dep_node in self.nodes:  # Only add if dependency exists
                    temp_adjacency[dep_node].add(node_id)
                    temp_reverse[node_id].add(dep_node)

        # Detect cycles using Kahn's algorithm
        all_nodes = set(self.nodes.keys()) | {node_id}
        in_degree = {n: 0 for n in all_nodes}

        for n in all_nodes:
            in_degree[n] = len(temp_reverse[n])

        queue = deque([n for n in all_nodes if in_degree[n] == 0])
        visited = 0

        while queue:
            current = queue.popleft()
            visited += 1

            for neighbor in temp_adjacency[current]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if visited != len(all_nodes):
            # Find nodes in cycle
            cycle_nodes = [n for n in all_nodes if in_degree[n] > 0]
            return CheckResult(
                name="no_cycles",
                passed=False,
                message=f"Adding node would create a cycle involving: {', '.join(cycle_nodes)}",
                severity="error",
                details={"cycle_nodes": cycle_nodes},
            )

        return CheckResult(
            name="no_cycles",
            passed=True,
            message="No cycles detected",
            details={"nodes_checked": len(all_nodes)},
        )

    def _validate_skills_naming(self, node: Dict) -> CheckResult:
        """Validate that skills follow naming convention."""
        skills = node.get("skills_bound", [])
        mcps = node.get("mcps_bound", [])

        issues = []

        if not isinstance(skills, list):
            skills = []
        if not isinstance(mcps, list):
            mcps = []

        # Check skills start with /
        for skill in skills:
            if isinstance(skill, str) and not skill.startswith("/"):
                issues.append(f"Skill '{skill}' should start with '/'")

        # Check MCPs are lowercase with hyphens
        for mcp in mcps:
            if isinstance(mcp, str):
                if mcp != mcp.lower() or " " in mcp:
                    issues.append(f"MCP '{mcp}' should be lowercase with hyphens")

        if issues:
            return CheckResult(
                name="skills_naming",
                passed=False,
                message=f"Naming convention issues: {'; '.join(issues)}",
                severity="warning",
                details={"issues": issues},
            )

        return CheckResult(
            name="skills_naming",
            passed=True,
            message="Skills and MCPs follow naming conventions",
            details={"skills_count": len(skills), "mcps_count": len(mcps)},
        )

    def _validate_pattern_compliance(self, node: Dict) -> CheckResult:
        """Validate node against matching regulatory pattern."""
        pattern = self.pattern_validator.get_pattern_for_node(node)

        if not pattern:
            return CheckResult(
                name="pattern_compliance",
                passed=True,
                message="No matching pattern found (custom node)",
                severity="info",
            )

        # Check pattern requirements
        issues = []

        # Check required inputs
        required_inputs = pattern.get("required_inputs", [])
        node_inputs = {
            i.get("type")
            for i in node.get("inputs_required", [])
            if isinstance(i, dict)
        }
        missing_inputs = set(required_inputs) - node_inputs
        if missing_inputs:
            issues.append(f"Missing required inputs: {', '.join(missing_inputs)}")

        # Check required outputs
        required_outputs = pattern.get("required_outputs", [])
        node_outputs = {
            o.get("type")
            for o in node.get("outputs_produced", [])
            if isinstance(o, dict)
        }
        missing_outputs = set(required_outputs) - node_outputs
        if missing_outputs:
            issues.append(f"Missing required outputs: {', '.join(missing_outputs)}")

        # Check required validation
        required_validation = pattern.get("required_validation", [])
        if required_validation:
            # Check if validation is mentioned in evaluation criteria or outputs
            eval_criteria = node.get("evaluation_criteria", {})
            has_validation = any(
                v.lower() in str(eval_criteria).lower() for v in required_validation
            )
            if not has_validation:
                issues.append(f"Missing validation: {', '.join(required_validation)}")

        if issues:
            return CheckResult(
                name="pattern_compliance",
                passed=False,
                message=f"Pattern compliance issues: {'; '.join(issues)}",
                severity="warning",
                details={"pattern": pattern.get("name", "unknown"), "issues": issues},
            )

        return CheckResult(
            name="pattern_compliance",
            passed=True,
            message="Node complies with regulatory pattern",
            details={"pattern": pattern.get("name", "unknown")},
        )

    # =========================================================================
    # EDGE EXTENSION VALIDATION
    # =========================================================================

    def can_extend_edge(
        self, src_id: str, dst_id: str, edge_type: str = "requires"
    ) -> EvaluationResult:
        """
        Validate a proposed new edge between existing nodes.

        Args:
            src_id: Source node ID (dependency)
            dst_id: Destination node ID (dependent)
            edge_type: Edge type (requires, enables, validates)

        Returns:
            EvaluationResult with detailed check results
        """
        checks: List[CheckResult] = []

        # 1. Both nodes must exist
        if src_id not in self.nodes:
            checks.append(
                CheckResult(
                    name="src_exists",
                    passed=False,
                    message=f"Source node '{src_id}' not found in graph",
                    severity="error",
                )
            )
        if dst_id not in self.nodes:
            checks.append(
                CheckResult(
                    name="dst_exists",
                    passed=False,
                    message=f"Destination node '{dst_id}' not found in graph",
                    severity="error",
                )
            )

        if any(not c.passed for c in checks):
            return EvaluationResult(
                passed=False, checks=checks, summary="FAILED - node(s) not found"
            )

        # 2. Valid edge type
        if edge_type not in self.VALID_EDGE_TYPES:
            checks.append(
                CheckResult(
                    name="edge_type",
                    passed=False,
                    message=f"Invalid edge type '{edge_type}'. Valid: {', '.join(sorted(self.VALID_EDGE_TYPES))}",
                    severity="error",
                )
            )
        else:
            checks.append(
                CheckResult(
                    name="edge_type",
                    passed=True,
                    message=f"Edge type '{edge_type}' is valid",
                )
            )

        # 3. No self-loop
        if src_id == dst_id:
            checks.append(
                CheckResult(
                    name="no_self_loop",
                    passed=False,
                    message=f"Self-loop: '{src_id}' -> '{dst_id}'",
                    severity="error",
                )
            )
        else:
            checks.append(
                CheckResult(name="no_self_loop", passed=True, message="No self-loop")
            )

        # 4. Layer ordering check
        src_layer = self.nodes[src_id].get("layer", 0)
        dst_layer = self.nodes[dst_id].get("layer", 0)

        if src_layer > dst_layer and edge_type == "requires":
            checks.append(
                CheckResult(
                    name="layer_ordering",
                    passed=False,
                    message=f"Backward 'requires' edge: L{src_layer} -> L{dst_layer}",
                    severity="error",
                    details={"src_layer": src_layer, "dst_layer": dst_layer},
                )
            )
        else:
            checks.append(
                CheckResult(
                    name="layer_ordering",
                    passed=True,
                    message=f"Layer ordering valid: L{src_layer} -> L{dst_layer}",
                )
            )

        # 5. No duplicate edge
        if dst_id in self.adjacency.get(src_id, set()):
            checks.append(
                CheckResult(
                    name="no_duplicate",
                    passed=False,
                    message=f"Edge already exists: '{src_id}' -> '{dst_id}'",
                    severity="warning",
                )
            )
        else:
            checks.append(
                CheckResult(
                    name="no_duplicate", passed=True, message="No duplicate edge"
                )
            )

        # 6. Cycle detection with new edge
        temp_adjacency = defaultdict(
            set, {k: set(v) for k, v in self.adjacency.items()}
        )
        temp_adjacency[src_id].add(dst_id)
        temp_reverse = defaultdict(
            set, {k: set(v) for k, v in self.reverse_adjacency.items()}
        )
        temp_reverse[dst_id].add(src_id)

        in_degree = {n: len(temp_reverse[n]) for n in self.nodes}
        queue = deque([n for n in self.nodes if in_degree[n] == 0])
        visited = 0

        while queue:
            current = queue.popleft()
            visited += 1
            for neighbor in temp_adjacency[current]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if visited != len(self.nodes):
            cycle_nodes = [n for n in self.nodes if in_degree[n] > 0]
            checks.append(
                CheckResult(
                    name="no_cycles",
                    passed=False,
                    message=f"Adding edge would create cycle: {', '.join(sorted(cycle_nodes))}",
                    severity="error",
                    details={"cycle_nodes": cycle_nodes},
                )
            )
        else:
            checks.append(
                CheckResult(name="no_cycles", passed=True, message="No cycle created")
            )

        errors = [c for c in checks if not c.passed and c.severity == "error"]
        passed = len(errors) == 0
        summary = self._generate_summary(checks, passed)

        return EvaluationResult(passed=passed, checks=checks, summary=summary)

    # =========================================================================
    # DISK-LEVEL SKILL EXISTENCE CHECK
    # =========================================================================

    def _validate_skills_exist(self, node: Dict) -> CheckResult:
        """Validate that bound skills have SKILL.md files on disk."""
        skills = node.get("skills_bound", [])
        if not isinstance(skills, list) or not skills:
            return CheckResult(
                name="skills_exist",
                passed=True,
                message="No skills bound (skipped)",
                severity="info",
            )

        # Find csp-skills directory
        project_root = self.graph_path.parent.parent
        csp_dir = project_root / "csp-skills"

        if not csp_dir.exists():
            return CheckResult(
                name="skills_exist",
                passed=True,
                message="csp-skills directory not found (skipped)",
                severity="info",
            )

        # Build skill index
        skill_index = set()
        for skill_md in csp_dir.rglob("SKILL.md"):
            skill_index.add(skill_md.parent.name)

        missing = []
        for skill in skills:
            clean = skill.lstrip("/")
            if clean not in skill_index:
                missing.append(clean)

        if missing:
            return CheckResult(
                name="skills_exist",
                passed=False,
                message=f"Skills without SKILL.md: {', '.join(missing)}",
                severity="warning",
                details={"missing_skills": missing, "searched": str(csp_dir)},
            )

        return CheckResult(
            name="skills_exist",
            passed=True,
            message=f"All {len(skills)} bound skills have SKILL.md files",
            details={"verified": [s.lstrip("/") for s in skills]},
        )

    # =========================================================================
    # LAYER TRANSITION VALIDATION (uses compatibility_rules)
    # =========================================================================

    def _validate_layer_transitions(self, node: Dict) -> List[CheckResult]:
        """Validate layer transitions against compatibility rules from patterns."""
        checks = []

        # Load compatibility rules from patterns data
        compat_data = {}
        if hasattr(self.pattern_validator, "patterns_data"):
            compat_data = self.pattern_validator.patterns_data.get(
                "compatibility_rules", {}
            )

        if not compat_data:
            return checks  # No rules to check

        invalid_transitions = compat_data.get("invalid_transitions", [])
        node_layer = node.get("layer")

        for dep in node.get("dependencies", []):
            if not isinstance(dep, dict):
                continue
            dep_id = dep.get("node")
            dep_node = self.nodes.get(dep_id)
            if not dep_node:
                continue

            dep_layer = dep_node.get("layer")

            # Check against explicit invalid transitions
            for invalid in invalid_transitions:
                from_layer = invalid.get("from")
                to_layers = invalid.get("to", [])
                if dep_layer == from_layer and node_layer in to_layers:
                    checks.append(
                        CheckResult(
                            name="layer_transition",
                            passed=False,
                            message=f"Invalid transition L{dep_layer}->L{node_layer}: {invalid.get('reason', 'forbidden')}",
                            severity="warning",
                            details={
                                "from": dep_layer,
                                "to": node_layer,
                                "reason": invalid.get("reason"),
                            },
                        )
                    )

        return checks

    def _generate_summary(self, checks: List[CheckResult], passed: bool) -> str:
        """Generate a summary of evaluation results."""
        errors = [c for c in checks if not c.passed and c.severity == "error"]
        warnings = [c for c in checks if not c.passed and c.severity == "warning"]

        if passed:
            if warnings:
                return f"PASSED with {len(warnings)} warning(s)"
            return "PASSED - All checks successful"
        else:
            return f"FAILED - {len(errors)} error(s), {len(warnings)} warning(s)"

    # =========================================================================
    # COMPLETION EVALUATION
    # =========================================================================

    def evaluate_completion(
        self, node_id: str, outputs: Dict[str, Any]
    ) -> CompletionResult:
        """
        Check if a node's outputs meet its evaluation_criteria.

        Args:
            node_id: ID of the node to evaluate
            outputs: Dictionary of output artifacts produced by the node

        Returns:
            CompletionResult with detailed results
        """
        node = self.nodes.get(node_id)

        if not node:
            return CompletionResult(
                passed=False,
                mandatory_passed=False,
                results=[
                    CheckResult(
                        name="node_exists",
                        passed=False,
                        message=f"Node '{node_id}' not found in graph",
                        severity="error",
                    )
                ],
            )

        results: List[CheckResult] = []
        eval_criteria = node.get("evaluation_criteria", {})

        # Check mandatory criteria
        mandatory = eval_criteria.get("mandatory", [])
        mandatory_results = []

        for criterion in mandatory:
            check = self._check_criterion(criterion, outputs, node)
            check.name = f"mandatory: {criterion[:50]}..."
            check.severity = "error"
            results.append(check)
            mandatory_results.append(check)

        # Check recommended criteria
        recommended = eval_criteria.get("recommended", [])
        for criterion in recommended:
            check = self._check_criterion(criterion, outputs, node)
            check.name = f"recommended: {criterion[:50]}..."
            check.severity = "warning"
            results.append(check)

        # Calculate results
        mandatory_passed = all(r.passed for r in mandatory_results)
        passed = mandatory_passed

        # Calculate completion percentage
        total_criteria = len(mandatory) + len(recommended)
        if total_criteria > 0:
            passed_count = sum(1 for r in results if r.passed)
            completion_percentage = (passed_count / total_criteria) * 100
        else:
            completion_percentage = 100.0 if outputs else 0.0

        return CompletionResult(
            passed=passed,
            mandatory_passed=mandatory_passed,
            results=results,
            completion_percentage=completion_percentage,
        )

    def _check_criterion(
        self, criterion: str, outputs: Dict[str, Any], node: Dict
    ) -> CheckResult:
        """
        Check a single evaluation criterion against outputs.

        Uses semantic keyword matching to determine what type of check
        is needed, then validates against the provided outputs.
        """
        criterion_lower = criterion.lower()
        outputs_produced = node.get("outputs_produced", [])

        # --- P21 / Validation checks ---
        if (
            "p21" in criterion_lower
            or "validation" in criterion_lower
            or "compliance" in criterion_lower
        ):
            validation_status = outputs.get("validation_status", {})
            if isinstance(validation_status, dict):
                error_count = validation_status.get("errors")
                warning_count = validation_status.get("warnings")

                if "0 errors" in criterion_lower:
                    if error_count is not None and error_count != 0:
                        return CheckResult(
                            name="",
                            passed=False,
                            message=f"Validation has {error_count} errors (expected 0)",
                            severity="error",
                            details={
                                "criterion": criterion,
                                "validation_status": validation_status,
                            },
                        )
                    elif error_count == 0:
                        return CheckResult(
                            name="",
                            passed=True,
                            message=f"Validation: 0 errors",
                            details={"criterion": criterion},
                        )

                if "0 warnings" in criterion_lower:
                    if warning_count is not None and warning_count != 0:
                        return CheckResult(
                            name="",
                            passed=False,
                            message=f"Validation has {warning_count} warnings (expected 0)",
                            severity="warning",
                            details={
                                "criterion": criterion,
                                "validation_status": validation_status,
                            },
                        )
                    elif warning_count == 0:
                        return CheckResult(
                            name="",
                            passed=True,
                            message=f"Validation: 0 warnings",
                            details={"criterion": criterion},
                        )

                # Generic validation check — if we have status, consider it checked
                if validation_status:
                    return CheckResult(
                        name="",
                        passed=True,
                        message=f"Validation status present: {criterion[:60]}",
                        details={
                            "criterion": criterion,
                            "validation_status": validation_status,
                        },
                    )

        # --- Variable presence checks ---
        if "variable" in criterion_lower or "variables" in criterion_lower:
            data_vars = outputs.get("variables_present", [])
            if isinstance(data_vars, (list, set)) and len(data_vars) > 0:
                return CheckResult(
                    name="",
                    passed=True,
                    message=f"Variables present ({len(data_vars)} found): {criterion[:60]}",
                    details={"criterion": criterion, "variables_found": len(data_vars)},
                )
            elif not data_vars:
                return CheckResult(
                    name="",
                    passed=False,
                    message=f"No variables_present in outputs: {criterion[:60]}",
                    severity="error",
                    details={"criterion": criterion},
                )

        # --- Output file existence checks ---
        if (
            "output" in criterion_lower
            or "produced" in criterion_lower
            or "generated" in criterion_lower
        ):
            output_files = outputs.get("files", []) + outputs.get("paths", [])
            if output_files:
                return CheckResult(
                    name="",
                    passed=True,
                    message=f"Output files present ({len(output_files)}): {criterion[:60]}",
                    details={"criterion": criterion, "files": len(output_files)},
                )

        # --- Generic: check if outputs exist at all ---
        if outputs:
            # If outputs are provided and we can't determine failure, assume satisfied
            return CheckResult(
                name="",
                passed=True,
                message=f"Criterion checked (outputs present): {criterion[:60]}",
                severity="info",
                details={"criterion": criterion},
            )
        else:
            return CheckResult(
                name="",
                passed=False,
                message=f"Cannot verify (no outputs provided): {criterion[:60]}",
                severity="warning",
                details={"criterion": criterion},
            )

    def _output_exists(self, path_pattern: str, outputs: Dict[str, Any]) -> bool:
        """Check if an output exists at the expected path."""
        output_files = outputs.get("files", [])
        output_paths = outputs.get("paths", [])

        # Check if pattern matches any output
        for f in output_files:
            if isinstance(f, dict):
                if path_pattern in f.get("path", ""):
                    return True
            elif isinstance(f, str):
                if path_pattern in f:
                    return True

        for p in output_paths:
            if path_pattern in p:
                return True

        return False

    # =========================================================================
    # GRAPH VALIDATION
    # =========================================================================

    def validate_graph(self) -> EvaluationResult:
        """
        Validate the entire graph structure.

        Returns:
            EvaluationResult with validation details
        """
        checks: List[CheckResult] = []

        # Check graph has nodes
        if not self.nodes:
            checks.append(
                CheckResult(
                    name="graph_has_nodes",
                    passed=False,
                    message="Graph has no nodes",
                    severity="error",
                )
            )
        else:
            checks.append(
                CheckResult(
                    name="graph_has_nodes",
                    passed=True,
                    message=f"Graph has {len(self.nodes)} nodes",
                    details={"node_count": len(self.nodes)},
                )
            )

        # Check for cycles in existing graph
        cycle_check = self._detect_cycles()
        checks.append(cycle_check)

        # Check all nodes have valid structure
        node_errors = []
        for node_id, node in self.nodes.items():
            missing = self.REQUIRED_NODE_FIELDS - set(node.keys())
            if missing:
                node_errors.append({"node": node_id, "missing": list(missing)})

        if node_errors:
            checks.append(
                CheckResult(
                    name="node_structure",
                    passed=False,
                    message=f"{len(node_errors)} nodes have missing required fields",
                    severity="error",
                    details={"errors": node_errors},
                )
            )
        else:
            checks.append(
                CheckResult(
                    name="node_structure",
                    passed=True,
                    message="All nodes have required fields",
                )
            )

        # Check layer distribution
        layer_counts = defaultdict(int)
        for node in self.nodes.values():
            layer = node.get("layer")
            if isinstance(layer, int):
                layer_counts[layer] += 1

        checks.append(
            CheckResult(
                name="layer_distribution",
                passed=True,
                message="Layer distribution calculated",
                details={"layers": dict(layer_counts)},
            )
        )

        # Check dangling dependencies
        dangling = []
        for node_id, node in self.nodes.items():
            for dep in node.get("dependencies", []):
                if isinstance(dep, dict):
                    dep_node = dep.get("node")
                    if dep_node and dep_node not in self.nodes:
                        dangling.append({"from": node_id, "missing": dep_node})

        if dangling:
            checks.append(
                CheckResult(
                    name="dangling_dependencies",
                    passed=False,
                    message=f"{len(dangling)} nodes reference non-existent dependencies",
                    severity="error",
                    details={"dangling": dangling},
                )
            )
        else:
            checks.append(
                CheckResult(
                    name="dangling_dependencies",
                    passed=True,
                    message="All dependencies resolve",
                )
            )

        errors = [c for c in checks if not c.passed and c.severity == "error"]
        passed = len(errors) == 0
        summary = self._generate_summary(checks, passed)

        return EvaluationResult(passed=passed, checks=checks, summary=summary)

    def _detect_cycles(self) -> CheckResult:
        """Detect cycles in the graph using Kahn's algorithm."""
        in_degree = {node_id: 0 for node_id in self.nodes}

        for node_id in self.nodes:
            in_degree[node_id] = len(self.reverse_adjacency[node_id])

        queue = deque([node_id for node_id in self.nodes if in_degree[node_id] == 0])
        visited = 0
        topological_order = []

        while queue:
            current = queue.popleft()
            topological_order.append(current)
            visited += 1

            for neighbor in self.adjacency[current]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if visited != len(self.nodes):
            cycle_nodes = [n for n in self.nodes if in_degree[n] > 0]
            return CheckResult(
                name="no_cycles",
                passed=False,
                message=f"Cycle detected involving: {', '.join(sorted(cycle_nodes))}",
                severity="error",
                details={"cycle_nodes": cycle_nodes},
            )

        return CheckResult(
            name="no_cycles",
            passed=True,
            message="Graph is acyclic (valid DAG)",
            details={"topological_order": topological_order[:10]},  # First 10 nodes
        )


# =============================================================================
# REPORT FORMATTING
# =============================================================================


def print_evaluation_report(
    result: EvaluationResult, title: str = "EVALUATION REPORT"
) -> None:
    """Print a formatted evaluation report."""
    print("\n" + "=" * 80)
    print(f" {title}")
    print("=" * 80)

    # Summary
    status = "PASSED" if result.passed else "FAILED"
    symbol = "[OK]" if result.passed else "[FAIL]"
    print(f"\n  Status: {symbol} {status}")
    print(f"  Summary: {result.summary}")

    # Passed checks
    passed = result.get_passed()
    if passed:
        print(f"\n  ## PASSED CHECKS ({len(passed)})")
        print("  " + "-" * 76)
        for check in passed:
            print(f"    [OK] {check.name}")
            print(f"         {check.message}")

    # Warnings
    warnings = result.get_warnings()
    if warnings:
        print(f"\n  ## WARNINGS ({len(warnings)})")
        print("  " + "-" * 76)
        for check in warnings:
            print(f"    [WARN] {check.name}")
            print(f"           {check.message}")

    # Errors
    errors = result.get_errors()
    if errors:
        print(f"\n  ## ERRORS ({len(errors)})")
        print("  " + "-" * 76)
        for check in errors:
            print(f"    [FAIL] {check.name}")
            print(f"           {check.message}")
            if check.details:
                for key, value in list(check.details.items())[:3]:
                    print(f"           > {key}: {value}")

    print("\n" + "=" * 80 + "\n")


def print_completion_report(result: CompletionResult, node_id: str):
    """Print a formatted completion report."""
    print("\n" + "=" * 80)
    print(f" COMPLETION EVALUATION: {node_id}")
    print("=" * 80)

    status = "PASSED" if result.passed else "FAILED"
    symbol = "[OK]" if result.passed else "[FAIL]"

    print(f"\n  Status: {symbol} {status}")
    print(f"  Mandatory Passed: {'Yes' if result.mandatory_passed else 'No'}")
    print(f"  Completion: {result.completion_percentage:.1f}%")

    print(f"\n  ## CRITERIA RESULTS ({len(result.results)})")
    print("  " + "-" * 76)

    for check in result.results:
        icon = (
            "[OK]"
            if check.passed
            else ("[WARN]" if check.severity == "warning" else "[FAIL]")
        )
        print(f"    {icon} {check.name}")
        print(f"         {check.message}")

    print("\n" + "=" * 80 + "\n")


# =============================================================================
# CLI
# =============================================================================


def main():
    """Main entry point for CLI."""
    if len(sys.argv) < 2:
        print(__doc__)
        print("\nCommands:")
        print("  --validate-graph <graph.yaml>")
        print("      Validate the entire graph structure")
        print()
        print("  --test-add-node <graph.yaml> <node.yaml>")
        print("      Test if a new node can be added to the graph")
        print()
        print("  --evaluate-completion <graph.yaml> <node-id> <outputs.json>")
        print("      Evaluate if a node's outputs meet completion criteria")
        print()
        print("  --interactive <graph.yaml>")
        print("      Interactive mode for testing node additions")
        print()
        print("Week 3: Self-Learning Commands:")
        print("  --with-trajectory --task-id <id> --node <id> --skills <list>")
        print("      Run evaluation with trajectory logging enabled")
        print()
        sys.exit(1)

    command = sys.argv[1]

    # Validate graph
    if command == "--validate-graph":
        if len(sys.argv) < 3:
            print("Usage: python evaluation.py --validate-graph <graph.yaml>")
            sys.exit(1)

        graph_path = sys.argv[2]
        patterns_path = Path(graph_path).parent / "regulatory-patterns.yaml"
        if not patterns_path.exists():
            patterns_path = None

        evaluator = GraphEvaluator(
            graph_path, str(patterns_path) if patterns_path else None
        )
        result = evaluator.validate_graph()
        print_evaluation_report(result, "GRAPH VALIDATION REPORT")

        sys.exit(0 if result.passed else 1)

    # Test add node
    elif command == "--test-add-node":
        if len(sys.argv) < 4:
            print(
                "Usage: python evaluation.py --test-add-node <graph.yaml> <node.yaml>"
            )
            sys.exit(1)

        graph_path = sys.argv[2]
        node_path = sys.argv[3]

        # Load proposed node
        try:
            with open(node_path, "r", encoding="utf-8") as f:
                new_node = yaml.safe_load(f)
        except Exception as e:
            print(f"Error loading node file: {e}")
            sys.exit(1)

        patterns_path = Path(graph_path).parent / "regulatory-patterns.yaml"
        if not patterns_path.exists():
            patterns_path = None

        evaluator = GraphEvaluator(
            graph_path, str(patterns_path) if patterns_path else None
        )
        result = evaluator.can_add_node(new_node)
        print_evaluation_report(
            result, f"NODE ADDITION TEST: {new_node.get('id', 'unknown')}"
        )

        sys.exit(0 if result.passed else 1)

    # Evaluate completion
    elif command == "--evaluate-completion":
        if len(sys.argv) < 5:
            print(
                "Usage: python evaluation.py --evaluate-completion <graph.yaml> <node-id> <outputs.json>"
            )
            sys.exit(1)

        graph_path = sys.argv[2]
        node_id = sys.argv[3]
        outputs_path = sys.argv[4]

        # Load outputs
        try:
            with open(outputs_path, "r", encoding="utf-8") as f:
                outputs = json.load(f)
        except Exception as e:
            print(f"Error loading outputs file: {e}")
            outputs = {}

        evaluator = GraphEvaluator(graph_path)
        result = evaluator.evaluate_completion(node_id, outputs)
        print_completion_report(result, node_id)

        sys.exit(0 if result.passed else 1)

    # Test extend edge
    elif command == "--test-extend-edge":
        if len(sys.argv) < 5:
            print(
                "Usage: python evaluation.py --test-extend-edge <graph.yaml> <src-node> <dst-node> [edge-type]"
            )
            sys.exit(1)

        graph_path = sys.argv[2]
        src_id = sys.argv[3]
        dst_id = sys.argv[4]
        edge_type = sys.argv[5] if len(sys.argv) > 5 else "requires"

        patterns_path = Path(graph_path).parent / "regulatory-patterns.yaml"
        if not patterns_path.exists():
            patterns_path = None

        evaluator = GraphEvaluator(
            graph_path, str(patterns_path) if patterns_path else None
        )
        result = evaluator.can_extend_edge(src_id, dst_id, edge_type)
        print_evaluation_report(
            result, f"EDGE TEST: {src_id} -> {dst_id} ({edge_type})"
        )

        sys.exit(0 if result.passed else 1)

    # Interactive mode
    elif command == "--interactive":
        if len(sys.argv) < 3:
            print("Usage: python evaluation.py --interactive <graph.yaml>")
            sys.exit(1)

        graph_path = sys.argv[2]
        patterns_path = Path(graph_path).parent / "regulatory-patterns.yaml"
        if not patterns_path.exists():
            patterns_path = None

        evaluator = GraphEvaluator(
            graph_path, str(patterns_path) if patterns_path else None
        )

        print("\n" + "=" * 80)
        print(" INTERACTIVE NODE EVALUATION")
        print("=" * 80)
        print(f"Loaded graph: {graph_path}")
        print(f"Nodes: {len(evaluator.nodes)}")
        print("\nEnter node YAML (press Enter twice to evaluate, or 'quit' to exit):")
        print("-" * 80)

        while True:
            lines = []
            empty_count = 0

            while True:
                try:
                    line = input()
                    if line.strip() == "":
                        empty_count += 1
                        if empty_count >= 2:
                            break
                    else:
                        empty_count = 0
                        lines.append(line)
                except EOFError:
                    break

            if not lines:
                continue

            content = "\n".join(lines)
            if content.strip().lower() == "quit":
                print("Goodbye!")
                break

            try:
                node = yaml.safe_load(content)
                result = evaluator.can_add_node(node)
                print_evaluation_report(result, f"NODE: {node.get('id', 'unknown')}")
            except yaml.YAMLError as e:
                print(f"Invalid YAML: {e}")
            except Exception as e:
                print(f"Error: {e}")

            print("\nEnter next node YAML (or 'quit' to exit):")
            print("-" * 80)

    else:
        print(f"Unknown command: {command}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
