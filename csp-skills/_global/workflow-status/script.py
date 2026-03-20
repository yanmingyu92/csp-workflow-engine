#!/usr/bin/env python3
"""Workflow Status - Quick read-only status dashboard."""

import sys
import yaml
from pathlib import Path
from typing import Dict, Set
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "_shared"))

from base_skill import (
    BaseCSPSkill,
    SkillConfig,
    SkillResult,
    SkillStatus,
    create_argument_parser,
)


class WorkflowStatus(BaseCSPSkill):
    """Quick workflow status dashboard."""

    GRAPH_NODE_ID = "_global_workflow_status"
    REQUIRED_INPUT_VARS = []
    OUTPUT_VARS = ["progress", "current", "frontier"]
    SKILL_NAME = "workflow-status"
    SKILL_VERSION = "1.0.0"

    def run(self) -> SkillResult:
        """Show workflow status."""
        graph = self._load_graph()
        state = self._load_state()

        if not graph:
            return self.create_result(SkillStatus.ERROR, "Cannot load graph")

        nodes = {n["id"]: n for n in graph.get("nodes", [])}
        completed = set(state.get("completed", []))
        current = state.get("current_node")
        total = len(nodes)

        # Compute frontier
        frontier = []
        for nid, node in nodes.items():
            if nid in completed:
                continue
            deps = {d["node"] for d in node.get("dependencies", [])}
            if deps.issubset(completed):
                frontier.append(nid)

        # Layer progress
        layer_progress = defaultdict(lambda: {"total": 0, "done": 0})
        for nid, node in nodes.items():
            layer = node.get("layer", 0)
            layer_progress[layer]["total"] += 1
            if nid in completed:
                layer_progress[layer]["done"] += 1

        pct = (len(completed) / total * 100) if total else 0
        bar_len = 20
        filled = int(bar_len * len(completed) / total) if total else 0
        bar = "█" * filled + "░" * (bar_len - filled)

        return self.create_result(
            SkillStatus.SUCCESS,
            f"{bar} {pct:.0f}% | {len(completed)}/{total} nodes | Current: {current or 'none'} | Frontier: {len(frontier)}",
            outputs={
                "completed_count": len(completed),
                "total_nodes": total,
                "percentage": round(pct, 1),
                "current_node": current,
                "frontier": sorted(frontier),
                "layer_progress": dict(layer_progress),
            },
        )

    def _load_graph(self):
        path = self.config.input_path or Path("graph/regulatory-graph.yaml")
        if not Path(path).exists():
            return None
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def _load_state(self):
        path = self.config.output_path or Path("ops/workflow-state.yaml")
        if Path(path).exists():
            with open(path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        return {}


def main():
    parser = create_argument_parser(
        "workflow-status", "Quick workflow status dashboard"
    )
    args = parser.parse_args()
    config = SkillConfig.from_args(args)
    result = WorkflowStatus(config).run()
    print(result.to_json())
    sys.exit(0 if result.status in [SkillStatus.SUCCESS, SkillStatus.WARNING] else 1)


if __name__ == "__main__":
    main()
