#!/usr/bin/env python3
"""
Graph Router — Token-Efficient Skill Loading

Computes adjacency (predecessors + current + successors) for workflow nodes
and returns only skills/MCPs bound to those nodes. Reduces context from
40+ skills to 3-8 per position.

Week 3 Enhancement: EMA skill weight updates from task outcomes.

Usage:
    python scripts/graph-router.py --node sdtm-dm-mapping --skills
    python scripts/graph-router.py --node sdtm-dm-mapping --adjacency --json
    python scripts/graph-router.py --current  # Read from workflow state
    python scripts/graph-router.py --list-nodes
    python scripts/graph-router.py --update-weights --node sdtm-dm-mapping --outcome success

Output modes:
    --skills      List skills for adjacent nodes
    --adjacency   Show graph position context
    --json        JSON output (machine-readable)
    --current     Use current node from workflow state
    --update-weights  Update EMA skill weights based on outcome
"""

import sys
import json
import yaml
import argparse
from pathlib import Path
from typing import Dict, List, Set, Optional, Any, Tuple
from collections import defaultdict
from datetime import datetime


class GraphLoader:
    """Load and parse the regulatory task graph."""

    def __init__(self, graph_path: str, layers_path: Optional[str] = None):
        self.graph_path = Path(graph_path)
        self.layers_path = Path(layers_path) if layers_path else None
        self.graph_data: Dict[str, Any] = {}
        self.layers_data: Dict[str, Any] = {}
        self.nodes: Dict[str, Dict] = {}
        self.global_skills: List[str] = []
        self.adjacency: Dict[str, Set[str]] = defaultdict(set)  # forward edges
        self.reverse_adjacency: Dict[str, Set[str]] = defaultdict(set)  # reverse edges

    def load(self) -> bool:
        """Load graph and layers files. Returns False on error."""
        try:
            with open(self.graph_path, "r", encoding="utf-8") as f:
                self.graph_data = yaml.safe_load(f)
        except FileNotFoundError:
            print(f"ERROR: Graph file not found: {self.graph_path}", file=sys.stderr)
            return False
        except yaml.YAMLError as e:
            print(f"ERROR: Invalid YAML in graph file: {e}", file=sys.stderr)
            return False

        # Load layers if available
        if self.layers_path and self.layers_path.exists():
            try:
                with open(self.layers_path, "r", encoding="utf-8") as f:
                    self.layers_data = yaml.safe_load(f)
            except Exception:
                pass  # Layers are optional

        # Extract global skills
        self.global_skills = self.graph_data.get("global_skills", [])

        # Build node map and adjacency lists
        for node in self.graph_data.get("nodes", []):
            node_id = node.get("id")
            if node_id:
                self.nodes[node_id] = node

                # Build adjacency from dependencies
                for dep in node.get("dependencies", []):
                    dep_node = dep.get("node") if isinstance(dep, dict) else dep
                    if dep_node:
                        self.adjacency[dep_node].add(node_id)
                        self.reverse_adjacency[node_id].add(dep_node)

        return True

    def get_node(self, node_id: str) -> Optional[Dict]:
        """Get node by ID."""
        return self.nodes.get(node_id)

    def get_predecessors(self, node_id: str) -> List[str]:
        """Get immediate predecessor nodes (dependencies)."""
        return sorted(self.reverse_adjacency.get(node_id, set()))

    def get_successors(self, node_id: str) -> List[str]:
        """Get immediate successor nodes (dependents)."""
        return sorted(self.adjacency.get(node_id, set()))

    def get_adjacent_nodes(self, node_id: str) -> Tuple[List[str], str, List[str]]:
        """Get (predecessors, current, successors) tuple."""
        return (self.get_predecessors(node_id), node_id, self.get_successors(node_id))

    def get_layer(self, node_id: str) -> Optional[int]:
        """Get layer number for a node."""
        node = self.get_node(node_id)
        return node.get("layer") if node else None

    def get_layer_name(self, layer_id: int) -> str:
        """Get human-readable layer name."""
        layer_names = {
            0: "Protocol & Planning",
            1: "Raw Data Management",
            2: "SDTM Creation",
            3: "SDTM Quality Control",
            4: "ADaM Creation",
            5: "TFL Generation",
            6: "Define.xml & Submission",
        }
        return layer_names.get(layer_id, f"Layer {layer_id}")

    def get_all_nodes(self) -> List[str]:
        """Get all node IDs sorted by layer."""
        return sorted(self.nodes.keys(), key=lambda n: (self.get_layer(n) or 0, n))


class StateReader:
    """Read workflow state to find current node position."""

    def __init__(self, state_path: str = "ops/workflow-state.yaml"):
        self.state_path = Path(state_path)
        self.state_data: Dict[str, Any] = {}

    def load(self) -> bool:
        """Load workflow state. Returns False if not found."""
        if not self.state_path.exists():
            return False

        try:
            with open(self.state_path, "r", encoding="utf-8") as f:
                self.state_data = yaml.safe_load(f)
            return True
        except Exception:
            return False

    def get_current_node(self) -> Optional[str]:
        """Get current workflow node from state."""
        # Try multiple possible locations
        if "current_node" in self.state_data:
            return self.state_data["current_node"]

        workflow = self.state_data.get("workflow", {})
        if "current_node" in workflow:
            return workflow["current_node"]
        if "current_stage" in workflow:
            return workflow["current_stage"]

        # Check stages for in_progress status
        stages = self.state_data.get("stages", [])
        if isinstance(stages, list):
            for stage in stages:
                if stage.get("status") == "in_progress":
                    return stage.get("id")

        return None

    def get_active_nodes(self) -> List[str]:
        """Get all nodes currently in progress."""
        nodes = []
        current = self.get_current_node()
        if current:
            nodes.append(current)

        # Check for multiple in_progress stages
        stages = self.state_data.get("stages", [])
        if isinstance(stages, list):
            for stage in stages:
                if stage.get("status") == "in_progress":
                    node_id = stage.get("id")
                    if node_id and node_id not in nodes:
                        nodes.append(node_id)

        return nodes


class SkillWeightManager:
    """
    Week 3: EMA-based skill weight management.

    Loads/saves skill weights from JSON and updates them based on task outcomes.
    Uses Exponential Moving Average: new_weight = 0.9 * old_weight + 0.1 * outcome
    """

    DEFAULT_WEIGHT = 0.5
    EMA_ALPHA = 0.1  # Weight for new outcome (0.1 = 10% new, 90% old)

    def __init__(self, weights_path: str = "data/experiences/skill_weights.json"):
        self.weights_path = Path(weights_path)
        self.weights: Dict[str, Dict[str, float]] = {}  # {node_id: {skill_name: weight}}
        self._load_weights()

    def _load_weights(self) -> bool:
        """Load weights from JSON file."""
        if not self.weights_path.exists():
            return False

        try:
            with open(self.weights_path, 'r', encoding='utf-8') as f:
                self.weights = json.load(f)
            return True
        except (json.JSONDecodeError, IOError) as e:
            print(f"Warning: Could not load skill weights: {e}", file=sys.stderr)
            return False

    def _save_weights(self) -> bool:
        """Save weights to JSON file."""
        try:
            # Ensure directory exists
            self.weights_path.parent.mkdir(parents=True, exist_ok=True)

            with open(self.weights_path, 'w', encoding='utf-8') as f:
                json.dump({
                    'weights': self.weights,
                    'updated_at': datetime.now().isoformat(),
                    'version': '1.0'
                }, f, indent=2)
            return True
        except IOError as e:
            print(f"Warning: Could not save skill weights: {e}", file=sys.stderr)
            return False

    def get_weight(self, node_id: str, skill_name: str) -> float:
        """Get weight for a skill at a node (default: 0.5)."""
        return self.weights.get(node_id, {}).get(skill_name, self.DEFAULT_WEIGHT)

    def update_weight(self, node_id: str, skill_name: str, outcome: float) -> float:
        """
        Update skill weight using EMA.

        Args:
            node_id: Graph node identifier
            skill_name: Skill name (with or without leading /)
            outcome: Task outcome (1.0 = success, 0.0 = failure, or partial)

        Returns:
            New weight value
        """
        # Normalize skill name
        clean_skill = skill_name.lstrip('/')

        # Get current weight
        old_weight = self.get_weight(node_id, clean_skill)

        # Apply EMA: new = 0.9 * old + 0.1 * outcome
        new_weight = (1 - self.EMA_ALPHA) * old_weight + self.EMA_ALPHA * outcome

        # Store
        if node_id not in self.weights:
            self.weights[node_id] = {}
        self.weights[node_id][clean_skill] = new_weight

        return new_weight

    def update_weights_batch(
        self,
        node_id: str,
        skills: List[str],
        outcome: float
    ) -> Dict[str, float]:
        """
        Update weights for multiple skills at once.

        Args:
            node_id: Graph node identifier
            skills: List of skill names
            outcome: Task outcome (1.0 = success, 0.0 = failure)

        Returns:
            Dict of skill_name -> new_weight
        """
        new_weights = {}
        for skill in skills:
            new_weights[skill] = self.update_weight(node_id, skill, outcome)

        self._save_weights()
        return new_weights

    def get_sorted_skills(
        self,
        node_id: str,
        skills: List[str],
        descending: bool = True
    ) -> List[str]:
        """
        Sort skills by their weight for a node.

        Args:
            node_id: Graph node identifier
            skills: List of skill names to sort
            descending: Sort in descending order (highest weight first)

        Returns:
            Sorted list of skill names
        """
        weighted = [(skill, self.get_weight(node_id, skill)) for skill in skills]
        weighted.sort(key=lambda x: x[1], reverse=descending)
        return [skill for skill, _ in weighted]

    def get_all_weights(self) -> Dict[str, Dict[str, float]]:
        """Get all weights (for debugging/export)."""
        return self.weights.copy()


class AdjacencyCalculator:
    """Calculate skill/MCP sets based on graph adjacency."""

    def __init__(self, graph: GraphLoader, weight_manager: SkillWeightManager = None):
        self.graph = graph
        self.weight_manager = weight_manager  # Week 3: Optional weight manager

    def get_skills_for_node(self, node_id: str) -> Tuple[List[str], List[str]]:
        """Get (skills, mcps) for a single node."""
        node = self.graph.get_node(node_id)
        if not node:
            return ([], [])

        skills = node.get("skills_bound", [])
        mcps = node.get("mcps_bound", [])

        return (skills, mcps)

    def get_active_skills(self, node_id: str) -> Dict[str, Any]:
        """
        Get all active skills/MCPs for a node position.
        Returns skills from: predecessors + current + successors + global.

        Week 3 Enhancement: Sort skills by EMA weight if weight_manager available.
        """
        predecessors, current, successors = self.graph.get_adjacent_nodes(node_id)

        all_skills: Set[str] = set()
        all_mcps: Set[str] = set()

        # Add global skills (always available)
        all_skills.update(self.graph.global_skills)

        # Collect from adjacent nodes
        for adj_node in predecessors + [current] + successors:
            skills, mcps = self.get_skills_for_node(adj_node)
            all_skills.update(skills)
            all_mcps.update(mcps)

        # Week 3: Sort skills by weight if weight_manager available
        if self.weight_manager:
            sorted_skills = self.weight_manager.get_sorted_skills(
                current, list(all_skills), descending=True
            )
        else:
            sorted_skills = sorted(all_skills)

        return {
            "current_node": current,
            "layer": self.graph.get_layer(current),
            "layer_name": self.graph.get_layer_name(self.graph.get_layer(current) or 0),
            "predecessors": predecessors,
            "successors": successors,
            "skills": sorted_skills,
            "mcps": sorted(all_mcps),
            "stats": {
                "total_skills": len(all_skills),
                "total_mcps": len(all_mcps),
                "adjacent_nodes": len(predecessors) + 1 + len(successors),
                "reduction_ratio": f"{len(self.graph.nodes)} nodes -> {len(predecessors) + 1 + len(successors)} adjacent",
            },
        }

    def get_all_skills(self) -> List[str]:
        """Get all skills in the graph (for comparison)."""
        all_skills: Set[str] = set(self.graph.global_skills)
        for node in self.graph.nodes.values():
            all_skills.update(node.get("skills_bound", []))
        return sorted(all_skills)


class OutputFormatter:
    """Format router output for different modes."""

    @staticmethod
    def format_skills(result: Dict[str, Any], show_context: bool = True) -> str:
        """Format skills output for display."""
        lines = []

        if show_context:
            lines.append(f"--=={{ graph router: {result['current_node']} }}==--")
            lines.append("")
            lines.append(f"Layer {result['layer']}: {result['layer_name']}")
            lines.append("")

            if result["predecessors"]:
                lines.append(f"Predecessor Nodes ({len(result['predecessors'])}):")
                for p in result["predecessors"]:
                    lines.append(f"  - {p}")
                lines.append("")

            lines.append(f"Current Node: {result['current_node']}")
            lines.append("")

            if result["successors"]:
                lines.append(f"Successor Nodes ({len(result['successors'])}):")
                for s in result["successors"]:
                    lines.append(f"  + {s}")
                lines.append("")

        lines.append(f"Active Skills ({result['stats']['total_skills']}):")
        for skill in result["skills"]:
            lines.append(f"  {skill}")
        lines.append("")

        if result["mcps"]:
            lines.append(f"Active MCPs ({result['stats']['total_mcps']}):")
            for mcp in result["mcps"]:
                lines.append(f"  {mcp}")
            lines.append("")

        lines.append("-" * 60)
        lines.append(f"Context reduction: {result['stats']['reduction_ratio']}")
        lines.append(
            f"Skills loaded: {result['stats']['total_skills']} of {result['stats'].get('total_graph_skills', '?')}"
        )

        return "\n".join(lines)

    @staticmethod
    def format_adjacency(result: Dict[str, Any]) -> str:
        """Format adjacency context for display."""
        lines = []
        lines.append(f"--=={{ graph adjacency: {result['current_node']} }}==--")
        lines.append("")
        lines.append(f"Layer: {result['layer']} ({result['layer_name']})")
        lines.append("")

        lines.append("Graph Position:")
        lines.append("  " + "-" * 40)

        for p in result["predecessors"]:
            lines.append(f"  [PREV]  {p}")

        lines.append(f"  [NOW]   {result['current_node']} <-- current")

        for s in result["successors"]:
            lines.append(f"  [NEXT]  {s}")

        lines.append("  " + "-" * 40)
        lines.append("")

        lines.append(f"Adjacent Nodes: {result['stats']['adjacent_nodes']}")
        lines.append(f"Active Skills:  {result['stats']['total_skills']}")
        lines.append(f"Active MCPs:    {result['stats']['total_mcps']}")

        return "\n".join(lines)

    @staticmethod
    def format_json(result: Dict[str, Any]) -> str:
        """Format as JSON."""
        return json.dumps(result, indent=2)


def find_graph_files(script_dir: Path) -> Tuple[str, Optional[str]]:
    """Find graph files relative to script location."""
    # Try relative to script location
    project_root = script_dir.parent
    graph_path = project_root / "graph" / "regulatory-graph.yaml"
    layers_path = project_root / "graph" / "graph-layers.yaml"

    if graph_path.exists():
        return (str(graph_path), str(layers_path) if layers_path.exists() else None)

    # Try current working directory
    cwd = Path.cwd()
    graph_path = cwd / "graph" / "regulatory-graph.yaml"
    layers_path = cwd / "graph" / "graph-layers.yaml"

    if graph_path.exists():
        return (str(graph_path), str(layers_path) if layers_path.exists() else None)

    # Default paths
    return ("graph/regulatory-graph.yaml", "graph/graph-layers.yaml")


def main():
    parser = argparse.ArgumentParser(
        description="Graph Router - Token-efficient skill loading for regulatory workflow",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/graph-router.py --node sdtm-dm-mapping --skills
  python scripts/graph-router.py --node sdtm-dm-mapping --adjacency
  python scripts/graph-router.py --current --json
  python scripts/graph-router.py --list-nodes
        """,
    )

    parser.add_argument("--node", "-n", help="Node ID to query")
    parser.add_argument(
        "--current",
        "-c",
        action="store_true",
        help="Use current node from workflow state",
    )
    parser.add_argument(
        "--skills", "-s", action="store_true", help="Output active skills"
    )
    parser.add_argument(
        "--adjacency", "-a", action="store_true", help="Output adjacency context"
    )
    parser.add_argument("--json", "-j", action="store_true", help="Output as JSON")
    parser.add_argument(
        "--list-nodes", "-l", action="store_true", help="List all available nodes"
    )
    parser.add_argument("--graph", "-g", help="Path to graph YAML file")
    parser.add_argument("--layers", help="Path to layers YAML file")
    parser.add_argument(
        "--state", help="Path to workflow state file", default="ops/workflow-state.yaml"
    )
    parser.add_argument(
        "--no-context", action="store_true", help="Hide context, show only skills"
    )
    # Week 3: EMA weight management arguments
    parser.add_argument(
        "--update-weights",
        action="store_true",
        help="Update EMA skill weights based on task outcome"
    )
    parser.add_argument(
        "--outcome",
        type=float,
        choices=[0.0, 1.0],
        help="Task outcome for weight update (1.0=success, 0.0=failure)"
    )
    parser.add_argument(
        "--skills-list",
        help="Comma-separated list of skills to update weights for (use with --update-weights)"
    )
    parser.add_argument(
        "--weights-file",
        default="data/experiences/skill_weights.json",
        help="Path to skill weights JSON file"
    )
    parser.add_argument(
        "--with-weights",
        action="store_true",
        help="Sort skills by EMA weight in output"
    )

    args = parser.parse_args()

    # Find graph files
    script_dir = Path(__file__).parent
    graph_path, layers_path = find_graph_files(script_dir)

    # Override with command line args if provided
    if args.graph:
        graph_path = args.graph
    if args.layers:
        layers_path = args.layers

    # Load graph
    loader = GraphLoader(graph_path, layers_path)
    if not loader.load():
        sys.exit(1)

    # Week 3: Initialize weight manager if needed
    weight_manager = None
    if args.with_weights or args.update_weights:
        weight_manager = SkillWeightManager(args.weights_file)

    calculator = AdjacencyCalculator(loader, weight_manager=weight_manager)

    # Handle --list-nodes
    if args.list_nodes:
        print("--=={ available nodes }==--")
        print()

        current_layer = None
        for node_id in loader.get_all_nodes():
            layer = loader.get_layer(node_id)
            if layer != current_layer:
                current_layer = layer
                print(f"\n## Layer {layer}: {loader.get_layer_name(layer)}")

            node = loader.get_node(node_id)
            name = node.get("name", node_id) if node else node_id
            print(f"  {node_id:<25} {name}")

        print(f"\nTotal: {len(loader.nodes)} nodes across 7 layers")
        sys.exit(0)

    # Week 3: Handle --update-weights
    if args.update_weights:
        if not args.node:
            print("ERROR: --node is required for --update-weights", file=sys.stderr)
            sys.exit(1)
        if args.outcome is None:
            print("ERROR: --outcome is required for --update-weights (1.0=success, 0.0=failure)", file=sys.stderr)
            sys.exit(1)
        if not args.skills_list:
            print("ERROR: --skills-list is required for --update-weights", file=sys.stderr)
            sys.exit(1)

        # Initialize weight manager
        weight_manager = SkillWeightManager(args.weights_file)

        # Parse skills list
        skills = [s.strip() for s in args.skills_list.split(',') if s.strip()]

        # Update weights
        new_weights = weight_manager.update_weights_batch(
            node_id=args.node,
            skills=skills,
            outcome=args.outcome
        )

        print(f"--=={{ weight update: {args.node} }}==--")
        print(f"Outcome: {'SUCCESS' if args.outcome == 1.0 else 'FAILURE'}")
        print(f"Skills updated: {len(new_weights)}")
        print()
        for skill, weight in sorted(new_weights.items(), key=lambda x: x[1], reverse=True):
            print(f"  {skill:<30} → {weight:.3f}")
        print()
        print(f"Weights saved to: {args.weights_file}")
        sys.exit(0)

    # Determine target node
    target_node = args.node

    if args.current or (not target_node):
        state_reader = StateReader(args.state)
        if state_reader.load():
            target_node = state_reader.get_current_node()
            if not target_node:
                print("No current node found in workflow state.", file=sys.stderr)
                print(
                    "Specify --node or initialize workflow with /workflow init",
                    file=sys.stderr,
                )
                sys.exit(1)
        elif args.current:
            print(f"Workflow state not found: {args.state}", file=sys.stderr)
            print(
                "Specify --node or initialize workflow with /workflow init",
                file=sys.stderr,
            )
            sys.exit(1)
        else:
            # Default to entry node
            target_node = "protocol-setup"
            print(
                f"No workflow state. Defaulting to entry node: {target_node}",
                file=sys.stderr,
            )

    # Verify node exists
    if not loader.get_node(target_node):
        print(f"ERROR: Node not found: {target_node}", file=sys.stderr)
        print(f"Use --list-nodes to see available nodes", file=sys.stderr)
        sys.exit(1)

    # Calculate result
    result = calculator.get_active_skills(target_node)
    result["stats"]["total_graph_skills"] = len(calculator.get_all_skills())

    # Output
    if args.json:
        print(OutputFormatter.format_json(result))
    elif args.adjacency:
        print(OutputFormatter.format_adjacency(result))
    else:
        # Default: skills output
        print(OutputFormatter.format_skills(result, show_context=not args.no_context))


if __name__ == "__main__":
    main()
