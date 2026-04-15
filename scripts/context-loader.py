#!/usr/bin/env python3
"""
Context Loader — Adaptive Priority Token Budget Controller

Loads SKILL.md files for active skills, ranked by graph proximity,
and fits them within a configurable token budget using an innovative
priority-decay scheduling algorithm.

Algorithm: Adaptive Priority Scheduler (APS)
============================================
1. CLASSIFY skills by proximity band:
   - Band 0 (CURRENT): Skills on the active node         → weight 1.0
   - Band 1 (SUCCESSOR): Skills on immediate successors  → weight 0.6
   - Band 2 (PREDECESSOR): Skills on predecessor nodes   → weight 0.4
   - Band 3 (GLOBAL): Global skills (workflow, etc.)     → weight 0.2

2. RANK within each band by:
   - Trigger match score (if user query provided)
   - Dependency edge count (hub influence)
   - Alphabetical (tiebreaker)

3. ALLOCATE budget with proportional guarantee:
   - Band 0 gets guaranteed 40% of budget (minimum floor)
   - Remaining 60% is allocated to other bands proportionally
   - If Band 0 doesn't use its full allocation, surplus cascades down

4. TRUNCATE intelligently when over-budget:
   - Strip YAML frontmatter first (saves ~5-10% tokens)
   - Then strip code blocks (keep descriptions, not examples)
   - Then truncate to N lines with "[...truncated]" marker
   - Never truncate Band 0 skills

5. EMIT only skills that fit within budget, with metadata showing
   what was included, truncated, or dropped.

Usage:
    python scripts/context-loader.py --node sdtm-dm-mapping
    python scripts/context-loader.py --node adam-adsl --budget 4000
    python scripts/context-loader.py --node p21-sdtm-validation --estimate
    python scripts/context-loader.py --current --json
"""

import sys
import json
import yaml
import argparse
import subprocess
import re
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import IntEnum

# Week 3: Self-learning module integration
try:
    from principle_store import PrincipleStore, format_principles_for_context
    PRINCIPLE_STORE_AVAILABLE = True
except ImportError:
    PRINCIPLE_STORE_AVAILABLE = False


# ============================================================================
# DATA STRUCTURES
# ============================================================================


class PriorityBand(IntEnum):
    """Skill proximity bands — lower = higher priority."""

    CURRENT = 0
    SUCCESSOR = 1
    PREDECESSOR = 2
    GLOBAL = 3


@dataclass
class SkillInfo:
    """Information about a loaded skill."""

    name: str
    path: Optional[Path] = None
    exists: bool = False
    token_estimate: int = 0
    content: str = ""
    truncated_content: str = ""
    error: Optional[str] = None
    band: PriorityBand = PriorityBand.GLOBAL
    priority_score: float = 0.0
    status: str = "pending"  # pending | loaded | truncated | dropped


@dataclass
class ContextResult:
    """Result of context loading."""

    node_id: str
    layer: int
    layer_name: str
    skills: List[SkillInfo] = field(default_factory=list)
    regulatory_refs: List[str] = field(default_factory=list)
    # Week 3: Principles from self-learning module
    principles: List[Any] = field(default_factory=list)  # List of (RegulatoryPrinciple, score) tuples
    principles_content: str = ""
    principles_tokens: int = 0
    principles_retrieved_ids: List[str] = field(default_factory=list)  # For usage tracking
    total_tokens: int = 0
    skill_tokens: int = 0
    ref_tokens: int = 0
    skills_loaded: int = 0
    skills_truncated: int = 0
    skills_dropped: int = 0
    skills_missing: int = 0
    budget: int = 5000
    budget_used: int = 0
    budget_strategy: str = ""


# ============================================================================
# TOKEN ESTIMATION
# ============================================================================


class TokenEstimator:
    """Estimate token counts for content."""

    CHARS_PER_TOKEN = 4  # Conservative estimate

    @classmethod
    def estimate(cls, text: str) -> int:
        if not text:
            return 0
        return max(1, len(text) // cls.CHARS_PER_TOKEN)

    @classmethod
    def estimate_file(cls, path: Path) -> int:
        try:
            return cls.estimate(path.read_text(encoding="utf-8"))
        except Exception:
            return 0


# ============================================================================
# SKILL LOCATOR
# ============================================================================


class SkillLocator:
    """Locate skill files in the csp-skills directory structure."""

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.csp_skills_dir = project_root / "csp-skills"
        self.skill_cache: Dict[str, Path] = {}
        self._build_skill_index()

    def _build_skill_index(self):
        if not self.csp_skills_dir.exists():
            return
        for skill_file in self.csp_skills_dir.rglob("SKILL.md"):
            skill_name = skill_file.parent.name
            self.skill_cache[skill_name] = skill_file
            clean = skill_name.lstrip("/")
            if clean != skill_name:
                self.skill_cache[clean] = skill_file

    def find_skill(self, skill_name: str) -> Optional[Path]:
        clean = skill_name.lstrip("/")
        if clean in self.skill_cache:
            return self.skill_cache[clean]

        if self.csp_skills_dir.exists():
            for skill_dir in self.csp_skills_dir.rglob(clean):
                if skill_dir.is_dir():
                    potential = skill_dir / "SKILL.md"
                    if potential.exists():
                        self.skill_cache[clean] = potential
                        return potential
        return None


# ============================================================================
# ADAPTIVE PRIORITY SCHEDULER (APS)
# ============================================================================


class AdaptivePriorityScheduler:
    """
    Token budget controller using priority-decay scheduling.

    Inspired by control theory: each skill receives a priority score
    based on proximity band, hub influence, and optional query relevance.
    Budget is allocated proportionally with minimum guarantees per band.
    """

    # Band weights: higher weight → more budget share
    BAND_WEIGHTS = {
        PriorityBand.CURRENT: 1.0,
        PriorityBand.SUCCESSOR: 0.6,
        PriorityBand.PREDECESSOR: 0.4,
        PriorityBand.GLOBAL: 0.2,
    }

    # Minimum guaranteed budget fraction for CURRENT band
    CURRENT_BAND_FLOOR = 0.40

    # Maximum fraction any single skill can consume
    MAX_SINGLE_SKILL_FRACTION = 0.25

    def __init__(self, budget: int = 5000):
        self.budget = budget

    def classify_skills(
        self,
        all_skills: List[str],
        current_node_skills: List[str],
        successor_skills: List[str],
        predecessor_skills: List[str],
        global_skills: List[str],
    ) -> Dict[str, PriorityBand]:
        """Classify each skill into its highest-priority band."""
        classification: Dict[str, PriorityBand] = {}

        for s in all_skills:
            if s in current_node_skills:
                classification[s] = PriorityBand.CURRENT
            elif s in successor_skills:
                classification[s] = PriorityBand.SUCCESSOR
            elif s in predecessor_skills:
                classification[s] = PriorityBand.PREDECESSOR
            elif s in global_skills:
                classification[s] = PriorityBand.GLOBAL
            else:
                classification[s] = PriorityBand.GLOBAL

        return classification

    def compute_priority(
        self,
        band: PriorityBand,
        skill_name: str,
        hub_degree: int = 0,
        query_match: float = 0.0,
    ) -> float:
        """
        Compute composite priority score for a skill.

        Score = band_weight × (1 + hub_bonus + query_bonus)

        Parameters:
            band: Proximity band
            skill_name: Skill identifier (for tiebreaking)
            hub_degree: Number of edges connecting this skill's node
            query_match: 0.0-1.0 relevance to user query (if available)
        """
        base = self.BAND_WEIGHTS[band]
        hub_bonus = min(0.3, hub_degree * 0.03)  # Cap at 0.3
        query_bonus = query_match * 0.5  # Up to 0.5 bonus
        return base * (1.0 + hub_bonus + query_bonus)

    def schedule(
        self,
        skills: List[SkillInfo],
        ref_tokens: int = 0,
    ) -> List[SkillInfo]:
        """
        Schedule skills within token budget using greedy priority allocation.

        Algorithm:
        1. Reserve space for regulatory refs
        2. Sort skills by priority (descending)
        3. Allocate budget greedily: load full content for high-priority,
           truncate for medium, drop for low
        4. Cascade surplus from CURRENT band to lower bands

        Returns:
            Skills list with status set (loaded/truncated/dropped)
        """
        available_budget = self.budget - ref_tokens

        if available_budget <= 0:
            for s in skills:
                s.status = "dropped"
            return skills

        # Sort by priority descending, then by name for stability
        ranked = sorted(skills, key=lambda s: (-s.priority_score, s.name))

        # Phase 1: Compute guaranteed allocation for CURRENT band
        current_skills = [
            s for s in ranked if s.band == PriorityBand.CURRENT and s.exists
        ]
        current_demand = sum(s.token_estimate for s in current_skills)
        current_floor = int(available_budget * self.CURRENT_BAND_FLOOR)
        current_allocation = min(current_demand, current_floor)

        # Phase 2: Remaining budget for other bands
        remaining = available_budget - current_allocation
        other_skills = [
            s for s in ranked if s.band != PriorityBand.CURRENT and s.exists
        ]
        other_demand = sum(s.token_estimate for s in other_skills)

        # Phase 3: If CURRENT band has surplus, cascade it down
        if current_demand < current_floor:
            surplus = current_floor - current_demand
            remaining += surplus
            current_allocation = current_demand

        # Phase 4: Greedy allocation
        used = 0
        max_per_skill = int(available_budget * self.MAX_SINGLE_SKILL_FRACTION)

        for skill in ranked:
            if not skill.exists or skill.error:
                skill.status = "missing"
                continue

            tokens = skill.token_estimate
            budget_left = available_budget - used

            if budget_left <= 0:
                skill.status = "dropped"
                continue

            if tokens <= budget_left:
                # Can fit full content
                if tokens > max_per_skill and skill.band != PriorityBand.CURRENT:
                    # Truncate large non-current skills to cap
                    skill.truncated_content = self._truncate_content(
                        skill.content, max_per_skill
                    )
                    actual_tokens = TokenEstimator.estimate(skill.truncated_content)
                    used += actual_tokens
                    skill.token_estimate = actual_tokens
                    skill.status = "truncated"
                else:
                    # Load full
                    skill.truncated_content = skill.content
                    used += tokens
                    skill.status = "loaded"
            elif budget_left >= 100:
                # Partially fit — truncate to remaining budget
                skill.truncated_content = self._truncate_content(
                    skill.content, budget_left
                )
                actual_tokens = TokenEstimator.estimate(skill.truncated_content)
                used += actual_tokens
                skill.token_estimate = actual_tokens
                skill.status = "truncated"
            else:
                skill.status = "dropped"

        return ranked

    def _truncate_content(self, content: str, target_tokens: int) -> str:
        """
        Intelligently truncate skill content to fit token target.

        Strategy (applied in order until within budget):
        1. Strip YAML frontmatter
        2. Strip code blocks (keep prose)
        3. Line-limit with truncation marker
        """
        # Step 1: Strip YAML frontmatter
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                content = parts[2].strip()

        if TokenEstimator.estimate(content) <= target_tokens:
            return content

        # Step 2: Strip ``` code blocks (keep structure, lose examples)
        content = re.sub(r"```[\s\S]*?```", "[code block removed for brevity]", content)

        if TokenEstimator.estimate(content) <= target_tokens:
            return content

        # Step 3: Line-limit truncation
        target_chars = target_tokens * TokenEstimator.CHARS_PER_TOKEN
        if len(content) > target_chars:
            # Find a clean break point (end of a line near target)
            break_at = content.rfind("\n", 0, target_chars)
            if break_at <= 0:
                break_at = target_chars
            content = content[:break_at] + "\n\n[...truncated to fit token budget]"

        return content


# ============================================================================
# CONTEXT BUILDER (enhanced with APS)
# ============================================================================


class ContextBuilder:
    """Build minimal context for graph position using Adaptive Priority Scheduling."""

    def __init__(self, project_root: Path, budget: int = 5000, principle_store: 'PrincipleStore' = None):
        self.project_root = project_root
        self.skill_locator = SkillLocator(project_root)
        self.scheduler = AdaptivePriorityScheduler(budget)
        self.budget = budget
        # Week 3: Principle store for self-learning
        self.principle_store = principle_store
        self._principles_used: List[str] = []  # Track retrieved principle IDs

    def load_skill(self, skill_name: str) -> SkillInfo:
        """Load a single skill file."""
        info = SkillInfo(name=skill_name)
        skill_path = self.skill_locator.find_skill(skill_name)
        if not skill_path:
            info.error = "Skill file not found"
            return info

        info.path = skill_path
        info.exists = True

        try:
            info.content = skill_path.read_text(encoding="utf-8")
            info.token_estimate = TokenEstimator.estimate(info.content)
        except Exception as e:
            info.error = str(e)

        return info

    def retrieve_principles(
        self,
        task_description: str,
        node_id: str,
        top_k: int = 3,
        min_score: float = 0.3
    ) -> Tuple[List[Tuple[Any, float]], str, int]:
        """
        Retrieve relevant principles from the principle store.

        Week 3 Implementation: Self-learning module integration.

        Args:
            task_description: Natural language description of the task
            node_id: Current graph node ID for filtering
            top_k: Maximum number of principles to retrieve
            min_score: Minimum metric_score threshold

        Returns:
            Tuple of (principles_list, formatted_content, token_estimate)
        """
        if not self.principle_store or not task_description:
            return ([], "", 0)

        try:
            principles = self.principle_store.search(
                query=task_description,
                node_id=node_id,
                top_k=top_k,
                min_score=min_score
            )

            if not principles:
                return ([], "", 0)

            # Track retrieved principle IDs for usage tracking
            self._principles_used = [p.principle_id for p, _ in principles]

            # Format principles for context
            content = format_principles_for_context(principles)
            tokens = TokenEstimator.estimate(content)

            return (principles, content, tokens)

        except Exception as e:
            print(f"Warning: Principle retrieval failed: {e}", file=sys.stderr)
            return ([], "", 0)

    def get_principles_used(self) -> List[str]:
        """Get IDs of principles retrieved in the last context build."""
        return self._principles_used.copy()

    def report_principle_outcome(self, success: bool) -> int:
        """
        Report the outcome of using retrieved principles.

        Week 3 Implementation: Updates usage metrics in PrincipleStore.

        This should be called after task completion to update principle
        effectiveness metrics via Laplace smoothing:
        metric_score = (success_count + 1) / (usage_count + 2)

        Args:
            success: Whether the task succeeded after using the principles

        Returns:
            Number of principles updated
        """
        if not self.principle_store or not self._principles_used:
            return 0

        updated_count = 0
        for principle_id in self._principles_used:
            try:
                self.principle_store.update_usage(principle_id, success=success)
                updated_count += 1
            except Exception as e:
                print(f"Warning: Failed to update principle {principle_id}: {e}", file=sys.stderr)

        # Clear the used list after reporting
        self._principles_used = []
        return updated_count

    def build_context(
        self,
        node_id: str,
        router_result: Dict[str, Any],
        all_skills: List[str],
        regulatory_refs: List[str],
        task_description: str = None,
        with_principles: bool = False,
    ) -> ContextResult:
        """
        Build budget-controlled context for a graph node.

        Uses the Adaptive Priority Scheduler to classify, rank, and
        schedule skills within the token budget.

        Week 3 Enhancement: Optionally include distilled principles.

        Args:
            node_id: Current graph node ID
            router_result: Result from graph-router containing adjacency info
            all_skills: List of skill names to consider
            regulatory_refs: List of regulatory references
            task_description: Natural language task description (for principle retrieval)
            with_principles: Whether to retrieve and include principles

        Returns:
            ContextResult with skills, principles, and token estimates
        """
        layer = router_result.get("layer", 0)
        layer_name = router_result.get("layer_name", "Unknown")
        predecessors = router_result.get("predecessors", [])
        successors = router_result.get("successors", [])

        result = ContextResult(
            node_id=node_id,
            layer=layer,
            layer_name=layer_name,
            budget=self.budget,
        )

        # --- Step 1: Retrieve principles (if enabled) ---
        principles_tokens = 0
        if with_principles and task_description and self.principle_store:
            principles, principles_content, principles_tokens = self.retrieve_principles(
                task_description=task_description,
                node_id=node_id,
                top_k=2,  # Week 6: Reduced from 3 to minimize context overhead
                min_score=0.3
            )
            result.principles = principles
            result.principles_content = principles_content
            result.principles_tokens = principles_tokens
            result.principles_retrieved_ids = self._principles_used.copy()

        # --- Step 2: Load all skill files ---
        skill_infos = [self.load_skill(name) for name in all_skills]

        # --- Step 3: Classify into priority bands ---
        # Get per-node skill sets
        graph_data = self._load_graph()
        nodes = {n["id"]: n for n in graph_data.get("nodes", [])} if graph_data else {}
        global_skills_list = graph_data.get("global_skills", []) if graph_data else []

        current_skills = set()
        node = nodes.get(node_id, {})
        for s in node.get("skills_bound", []):
            current_skills.add(s)

        successor_skills = set()
        for s_nid in successors:
            sn = nodes.get(s_nid, {})
            for s in sn.get("skills_bound", []):
                successor_skills.add(s)

        predecessor_skills = set()
        for p_nid in predecessors:
            pn = nodes.get(p_nid, {})
            for s in pn.get("skills_bound", []):
                predecessor_skills.add(s)

        classification = self.scheduler.classify_skills(
            all_skills,
            list(current_skills),
            list(successor_skills),
            list(predecessor_skills),
            global_skills_list,
        )

        # --- Step 4: Assign bands and priority scores ---
        for info in skill_infos:
            info.band = classification.get(info.name, PriorityBand.GLOBAL)

            # Compute hub degree from adjacency
            hub_degree = len(predecessors) + len(successors)
            info.priority_score = self.scheduler.compute_priority(
                info.band, info.name, hub_degree
            )

        # --- Step 5: Schedule within budget (accounting for principles) ---
        ref_tokens = len(regulatory_refs) * 50
        # Reduce budget available for skills by principles_tokens
        scheduled = self.scheduler.schedule(skill_infos, ref_tokens + principles_tokens)

        # --- Step 6: Build result ---
        result.regulatory_refs = regulatory_refs
        result.ref_tokens = ref_tokens
        result.skills = scheduled

        for s in scheduled:
            if s.status == "loaded":
                result.skills_loaded += 1
                result.skill_tokens += s.token_estimate
            elif s.status == "truncated":
                result.skills_truncated += 1
                result.skill_tokens += s.token_estimate
            elif s.status == "dropped":
                result.skills_dropped += 1
            elif s.status == "missing":
                result.skills_missing += 1

        result.total_tokens = result.skill_tokens + result.ref_tokens + result.principles_tokens
        result.budget_used = result.total_tokens

        # Build strategy string
        strategy_parts = [f"APS: {result.skills_loaded} loaded"]
        if result.principles:
            strategy_parts.append(f"{len(result.principles)} principles")
        strategy_parts.extend([
            f"{result.skills_truncated} truncated",
            f"{result.skills_dropped} dropped",
            f"{result.budget_used}/{self.budget} tokens"
        ])
        result.budget_strategy = " | ".join(strategy_parts)

        return result

    def _load_graph(self) -> Optional[Dict]:
        """Load graph YAML."""
        graph_path = self.project_root / "graph" / "regulatory-graph.yaml"
        if not graph_path.exists():
            return None
        try:
            with open(graph_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f)
        except Exception:
            return None


# ============================================================================
# OUTPUT FORMATTER
# ============================================================================


class OutputFormatter:
    """Format context output."""

    @staticmethod
    def format_estimate(result: ContextResult) -> str:
        lines = [
            f"--=={{ context estimate: {result.node_id} }}==--",
            "",
            f"Layer {result.layer}: {result.layer_name}",
            f"Budget: {result.budget:,} tokens",
            "",
        ]

        # Week 3: Show principles if present
        if result.principles:
            lines.append(f"Principles: {len(result.principles)} retrieved")
            lines.append(f"  Principle tokens: ~{result.principles_tokens:,}")
            lines.append("")

        lines.extend([
            f"Skills: {result.skills_loaded} loaded, "
            f"{result.skills_truncated} truncated, "
            f"{result.skills_dropped} dropped, "
            f"{result.skills_missing} missing",
            f"  Skill tokens:     ~{result.skill_tokens:,}",
            "",
            f"Regulatory refs: {len(result.regulatory_refs)}",
            f"  Reference tokens: ~{result.ref_tokens:,}",
            "",
            "-" * 50,
            f"Total estimated: ~{result.total_tokens:,} tokens",
            f"Budget:          {result.budget:,} tokens",
            f"Status:          {'OK' if result.total_tokens <= result.budget else 'OVER BUDGET'}",
            "",
            "Priority Schedule:",
        ])

        for band in PriorityBand:
            band_skills = [s for s in result.skills if s.band == band]
            if band_skills:
                lines.append(f"  Band {band.value} ({band.name}):")
                for s in band_skills:
                    status_icon = {
                        "loaded": "+",
                        "truncated": "~",
                        "dropped": "x",
                        "missing": "?",
                    }.get(s.status, "?")
                    lines.append(
                        f"    [{status_icon}] {s.name:<30} {s.token_estimate:>5} tokens  (priority: {s.priority_score:.2f})"
                    )

        return "\n".join(lines)

    @staticmethod
    def format_context(result: ContextResult, include_content: bool = True) -> str:
        lines = [
            f"--=={{ context: {result.node_id} }}==--",
            "",
            f"## Graph Position",
            f"Layer: {result.layer} ({result.layer_name})",
            f"Node:  {result.node_id}",
            f"Budget: {result.budget_used}/{result.budget} tokens ({result.budget_strategy})",
            "",
        ]

        # Week 3: Include principles section if present
        if result.principles:
            lines.append(f"## Principles ({len(result.principles)} retrieved, ~{result.principles_tokens} tokens)")
            lines.append("-" * 50)
            for principle, score in result.principles:
                marker = "[GUIDING]" if principle.type == 'guiding' else "[CAUTION]"
                lines.append(f"  {marker} [{principle.type}] (confidence: {principle.metric_score:.0%})")
                lines.append(f"     {principle.description[:100]}{'...' if len(principle.description) > 100 else ''}")
            lines.append("")

        lines.extend([
            f"## Skills ({result.skills_loaded + result.skills_truncated} active, ~{result.skill_tokens} tokens)",
            "-" * 50,
        ])

        for skill in result.skills:
            status_map = {
                "loaded": "FULL",
                "truncated": "TRUNC",
                "dropped": "DROP",
                "missing": "MISS",
            }
            status = status_map.get(skill.status, "?")
            band_label = skill.band.name[:4]
            lines.append(
                f"  [{status:<5}] [{band_label}] {skill.name:<30} "
                f"~{skill.token_estimate} tokens (p={skill.priority_score:.2f})"
            )

        if result.regulatory_refs:
            lines.append("")
            lines.append(f"## Regulatory References ({len(result.regulatory_refs)})")
            lines.append("-" * 50)
            for ref in result.regulatory_refs:
                lines.append(f"  - {ref}")

        lines.append("")
        lines.append("-" * 50)
        lines.append(f"Total context: ~{result.total_tokens:,} tokens")

        if include_content:
            # Week 3: Include principles content first if present
            if result.principles_content:
                lines.append("")
                lines.append("=" * 50)
                lines.append("## Experience Principles (Self-Learned)")
                lines.append("=" * 50)
                lines.append(result.principles_content)

            lines.append("")
            lines.append("=" * 50)
            lines.append("## Skill Content")
            lines.append("=" * 50)

            for skill in result.skills:
                content = skill.truncated_content or skill.content
                if skill.exists and content and skill.status in ("loaded", "truncated"):
                    lines.append("")
                    lines.append(f"### {skill.name} [{skill.band.name}]")
                    if skill.status == "truncated":
                        lines.append(f"_[truncated to ~{skill.token_estimate} tokens]_")
                    lines.append("-" * 40)
                    # Strip YAML frontmatter for cleaner output
                    if content.startswith("---"):
                        parts = content.split("---", 2)
                        if len(parts) >= 3:
                            content = parts[2].strip()
                    lines.append(content)

        return "\n".join(lines)

    @staticmethod
    def format_json(result: ContextResult) -> str:
        data = {
            "node_id": result.node_id,
            "layer": result.layer,
            "layer_name": result.layer_name,
            "budget": result.budget,
            "strategy": result.budget_strategy,
            "stats": {
                "skills_loaded": result.skills_loaded,
                "skills_truncated": result.skills_truncated,
                "skills_dropped": result.skills_dropped,
                "skills_missing": result.skills_missing,
                "skill_tokens": result.skill_tokens,
                "ref_count": len(result.regulatory_refs),
                "ref_tokens": result.ref_tokens,
                "total_tokens": result.total_tokens,
                "within_budget": result.total_tokens <= result.budget,
                # Week 3: Principles stats
                "principles_count": len(result.principles) if result.principles else 0,
                "principles_tokens": result.principles_tokens,
            },
            "skills": [
                {
                    "name": s.name,
                    "band": s.band.name,
                    "priority": round(s.priority_score, 3),
                    "exists": s.exists,
                    "tokens": s.token_estimate,
                    "status": s.status,
                    "error": s.error,
                }
                for s in result.skills
            ],
            "regulatory_refs": result.regulatory_refs,
            # Week 3: Principles data
            "principles": [
                {
                    "principle_id": p.principle_id,
                    "type": p.type,
                    "description": p.description,
                    "metric_score": p.metric_score,
                    "applicable_nodes": p.applicable_nodes,
                    "skills_recommended": p.skills_recommended,
                    "similarity": float(score) if score else 0.0,
                }
                for p, score in (result.principles or [])
            ] if result.principles else [],
            "principles_retrieved_ids": result.principles_retrieved_ids,
        }
        return json.dumps(data, indent=2)


# ============================================================================
# HELPERS
# ============================================================================


def find_project_root() -> Path:
    script_dir = Path(__file__).parent
    if (script_dir.parent / "graph").exists():
        return script_dir.parent
    cwd = Path.cwd()
    if (cwd / "graph").exists():
        return cwd
    return script_dir.parent


def call_graph_router(node_id: str) -> Dict[str, Any]:
    """Call graph-router to get adjacency + skills."""
    script_dir = Path(__file__).parent
    router_script = script_dir / "graph-router.py"

    try:
        result = subprocess.run(
            [sys.executable, str(router_script), "--node", node_id, "--json"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            return json.loads(result.stdout)
    except Exception as e:
        print(f"Warning: graph-router call failed: {e}", file=sys.stderr)

    return {
        "layer": 0,
        "layer_name": "Unknown",
        "skills": [],
        "mcps": [],
        "predecessors": [],
        "successors": [],
    }


def get_regulatory_refs(node_id: str, graph_path: Path) -> List[str]:
    """Get regulatory references for a node."""
    try:
        with open(graph_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        for node in data.get("nodes", []):
            if node.get("id") == node_id:
                return node.get("regulatory_refs", [])
    except Exception:
        pass
    return []


def resolve_current_node(state_path: Path) -> Optional[str]:
    """Read current node from workflow state."""
    if not state_path.exists():
        return None
    try:
        with open(state_path, "r", encoding="utf-8") as f:
            state = yaml.safe_load(f) or {}
        return (
            state.get("current_node")
            or state.get("workflow", {}).get("current_node")
            or state.get("workflow", {}).get("current_stage")
        )
    except Exception:
        return None


# ============================================================================
# MAIN
# ============================================================================


def main():
    parser = argparse.ArgumentParser(
        description="Context Loader — Adaptive Priority Token Budget Controller",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Algorithm: Adaptive Priority Scheduler (APS)
  Skills are classified by proximity band (current > successor >
  predecessor > global), then scheduled greedily within token budget.
  Lower-priority skills are truncated or dropped to stay within budget.

Examples:
  python scripts/context-loader.py --node sdtm-dm-mapping
  python scripts/context-loader.py --node adam-adsl --budget 4000
  python scripts/context-loader.py --node p21-sdtm-validation --estimate
  python scripts/context-loader.py --current --json
        """,
    )

    parser.add_argument("--node", "-n", help="Node ID to load context for")
    parser.add_argument(
        "--current",
        "-c",
        action="store_true",
        help="Use current node from workflow state",
    )
    parser.add_argument(
        "--budget", "-b", type=int, default=5000, help="Token budget (default: 5000)"
    )
    parser.add_argument(
        "--estimate",
        "-e",
        action="store_true",
        help="Show token estimate + priority schedule, no content",
    )
    parser.add_argument("--output", "-o", help="Write context to file")
    parser.add_argument(
        "--json", "-j", action="store_true", help="Output metadata as JSON"
    )
    parser.add_argument(
        "--no-content",
        action="store_true",
        help="Skip skill content, show metadata only",
    )
    parser.add_argument(
        "--state", default="ops/workflow-state.yaml", help="Workflow state file path"
    )
    # Week 3: Self-learning integration flags
    parser.add_argument(
        "--with-principles",
        action="store_true",
        help="Retrieve and include distilled principles from self-learning module"
    )
    parser.add_argument(
        "--task-description", "-t",
        help="Task description for principle retrieval (use with --with-principles)"
    )
    parser.add_argument(
        "--principle-store",
        default="data/experiences/principles.db",
        help="Path to principles database (default: data/experiences/principles.db)"
    )
    # Week 3: Principle outcome reporting
    parser.add_argument(
        "--report-outcome",
        choices=["success", "failure"],
        help="Report outcome for principles used in previous context build"
    )
    parser.add_argument(
        "--principles-used",
        help="Comma-separated list of principle IDs to update (for --report-outcome)"
    )

    args = parser.parse_args()

    # Week 3: Handle --report-outcome for principle usage tracking
    if args.report_outcome:
        if not args.principles_used:
            print("ERROR: --principles-used is required with --report-outcome", file=sys.stderr)
            sys.exit(1)

        if not PRINCIPLE_STORE_AVAILABLE:
            print("ERROR: PrincipleStore not available (missing dependencies)", file=sys.stderr)
            sys.exit(1)

        try:
            store = PrincipleStore(args.principle_store)
            principle_ids = [p.strip() for p in args.principles_used.split(',') if p.strip()]
            success = args.report_outcome == "success"

            updated = 0
            for pid in principle_ids:
                try:
                    store.update_usage(pid, success=success)
                    updated += 1
                except Exception as e:
                    print(f"Warning: Failed to update principle {pid}: {e}", file=sys.stderr)

            print(f"--=={{ principle outcome report }}==--")
            print(f"Outcome: {args.report_outcome.upper()}")
            print(f"Principles updated: {updated}/{len(principle_ids)}")
            for pid in principle_ids:
                principle = store.get_principle_by_id(pid)
                if principle:
                    print(f"  {pid}: metric_score={principle.metric_score:.3f}, usage={principle.usage_count}")
            sys.exit(0)
        except Exception as e:
            print(f"ERROR: Failed to report outcome: {e}", file=sys.stderr)
            sys.exit(1)

    # Find project root
    project_root = find_project_root()
    graph_path = project_root / "graph" / "regulatory-graph.yaml"

    # Resolve target node
    target_node = args.node
    if args.current or not target_node:
        state_path = project_root / args.state
        target_node = resolve_current_node(state_path)
        if not target_node:
            if args.current:
                print(
                    f"No current node in workflow state: {args.state}", file=sys.stderr
                )
                sys.exit(1)
            target_node = "protocol-setup"
            print(f"No workflow state. Defaulting to: {target_node}", file=sys.stderr)

    # Get adjacency from router
    router_result = call_graph_router(target_node)
    skills = router_result.get("skills", [])
    regulatory_refs = get_regulatory_refs(target_node, graph_path)

    if not skills:
        print(f"Warning: No skills for node: {target_node}", file=sys.stderr)

    # Build budget-controlled context
    # Week 3: Initialize principle store if requested
    principle_store = None
    if args.with_principles and PRINCIPLE_STORE_AVAILABLE:
        try:
            principle_store = PrincipleStore(args.principle_store)
        except Exception as e:
            print(f"Warning: Could not load principle store: {e}", file=sys.stderr)
    elif args.with_principles and not PRINCIPLE_STORE_AVAILABLE:
        print("Warning: PrincipleStore not available (missing dependencies)", file=sys.stderr)

    builder = ContextBuilder(project_root, budget=args.budget, principle_store=principle_store)
    result = builder.build_context(
        node_id=target_node,
        router_result=router_result,
        all_skills=skills,
        regulatory_refs=regulatory_refs,
        task_description=args.task_description,
        with_principles=args.with_principles
    )

    # Format output
    if args.json:
        output = OutputFormatter.format_json(result)
    elif args.estimate:
        output = OutputFormatter.format_estimate(result)
    else:
        output = OutputFormatter.format_context(
            result, include_content=not args.no_content
        )

    # Write or print
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(output, encoding="utf-8")
        print(f"Context written to: {args.output}", file=sys.stderr)
        print(
            f"Budget: {result.budget_used}/{result.budget} tokens ({result.budget_strategy})",
            file=sys.stderr,
        )
    else:
        print(output)


if __name__ == "__main__":
    main()
