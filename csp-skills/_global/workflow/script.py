#!/usr/bin/env python3
"""Workflow Controller - Track and manage regulatory workflow progression."""

import sys
import json
import yaml
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Set, Optional, Any
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "_shared"))

from base_skill import (
    BaseCSPSkill,
    SkillConfig,
    SkillResult,
    SkillStatus,
    create_argument_parser,
)


class WorkflowController(BaseCSPSkill):
    """Track and manage regulatory workflow progression."""

    GRAPH_NODE_ID = "_global_workflow"
    REQUIRED_INPUT_VARS = []
    OUTPUT_VARS = ["status", "frontier", "completed"]
    SKILL_NAME = "workflow"
    SKILL_VERSION = "1.0.0"

    DEFAULT_STATE_PATH = Path("ops/workflow-state.yaml")
    DEFAULT_GRAPH_PATH = Path("graph/regulatory-graph.yaml")

    def run(self) -> SkillResult:
        """Execute workflow action."""
        action = getattr(self.config, "action", "status") or "status"
        self.log_info(f"Workflow action: {action}")

        if self.config.dry_run:
            return self.create_result(SkillStatus.DRY_RUN, f"Would execute: {action}")

        # Load graph
        graph = self._load_graph()
        if not graph:
            return self.create_result(SkillStatus.ERROR, "Cannot load graph")

        # Load or init state
        state = self._load_state()

        if action == "status":
            return self._status(graph, state)
        elif action == "advance":
            return self._advance(graph, state)
        elif action == "history":
            return self._history(state)
        elif action == "reset":
            return self._reset(state)
        else:
            return self.create_result(SkillStatus.ERROR, f"Unknown action: {action}")

    def _load_graph(self) -> Optional[Dict]:
        graph_path = self.config.input_path or self.DEFAULT_GRAPH_PATH
        if not Path(graph_path).exists():
            return None
        with open(graph_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def _load_state(self) -> Dict:
        state_path = self.config.output_path or self.DEFAULT_STATE_PATH
        if Path(state_path).exists():
            with open(state_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        return {"completed": [], "current_node": None, "history": []}

    def _save_state(self, state: Dict):
        state_path = self.config.output_path or self.DEFAULT_STATE_PATH
        Path(state_path).parent.mkdir(parents=True, exist_ok=True)
        with open(state_path, "w", encoding="utf-8") as f:
            yaml.dump(state, f, default_flow_style=False)

    def _compute_frontier(self, graph: Dict, completed: Set[str]) -> List[str]:
        """Compute frontier: nodes whose predecessors are all complete."""
        nodes = {n["id"]: n for n in graph.get("nodes", [])}
        frontier = []
        for nid, node in nodes.items():
            if nid in completed:
                continue
            deps = {d["node"] for d in node.get("dependencies", [])}
            if deps.issubset(completed):
                frontier.append(nid)
        return sorted(frontier)

    def _status(self, graph: Dict, state: Dict) -> SkillResult:
        completed = set(state.get("completed", []))
        current = state.get("current_node")
        frontier = self._compute_frontier(graph, completed)
        total = len(graph.get("nodes", []))

        return self.create_result(
            SkillStatus.SUCCESS,
            f"Workflow: {len(completed)}/{total} complete, {len(frontier)} frontier nodes",
            outputs={
                "completed_count": len(completed),
                "total_nodes": total,
                "current_node": current,
                "frontier": frontier,
                "completed": sorted(completed),
            },
        )

    def _advance(self, graph: Dict, state: Dict) -> SkillResult:
        completed = set(state.get("completed", []))
        current = state.get("current_node")
        frontier = self._compute_frontier(graph, completed)

        if current:
            # Mark current as complete
            completed.add(current)
            state["completed"] = sorted(completed)
            state["history"] = state.get("history", [])
            state["history"].append(
                {
                    "node": current,
                    "action": "completed",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )

        # Recalculate frontier
        frontier = self._compute_frontier(graph, completed)
        if frontier:
            next_node = frontier[0]
            state["current_node"] = next_node
            state["history"].append(
                {
                    "node": next_node,
                    "action": "started",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )
            self._save_state(state)
            return self.create_result(
                SkillStatus.SUCCESS,
                f"Advanced to: {next_node} (frontier: {len(frontier)})",
                outputs={"current_node": next_node, "frontier": frontier},
            )
        else:
            state["current_node"] = None
            self._save_state(state)
            return self.create_result(
                SkillStatus.SUCCESS,
                "All nodes complete — workflow finished",
                outputs={"current_node": None, "frontier": []},
            )

    def _history(self, state: Dict) -> SkillResult:
        history = state.get("history", [])
        return self.create_result(
            SkillStatus.SUCCESS,
            f"Workflow history: {len(history)} entries",
            outputs={"history": history},
        )

    def _reset(self, state: Dict) -> SkillResult:
        state = {
            "completed": [],
            "current_node": None,
            "history": [
                {"action": "reset", "timestamp": datetime.now(timezone.utc).isoformat()}
            ],
        }
        self._save_state(state)
        return self.create_result(SkillStatus.SUCCESS, "Workflow state reset")


def main():
    parser = create_argument_parser("workflow", "Track and manage regulatory workflow")
    parser.add_argument(
        "--action", choices=["status", "advance", "history", "reset"], default="status"
    )
    args = parser.parse_args()
    config = SkillConfig.from_args(args)
    config.action = args.action
    result = WorkflowController(config).run()
    print(result.to_json())
    sys.exit(0 if result.status in [SkillStatus.SUCCESS, SkillStatus.WARNING] else 1)


if __name__ == "__main__":
    main()
