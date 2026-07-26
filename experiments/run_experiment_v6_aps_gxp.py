#!/usr/bin/env python3
"""Prepare and execute the locked four-arm APS-GxP v6 experiment.

Stage 0 is entirely local and deterministic. Generation and scalar judging are
separate commands with separate affirmative flags so a context dry run cannot
accidentally make a paid call or transmit a stored response. The optimized arm
uses BM25 relevance only for non-CURRENT admission/ranking; the v5 scheduler and
runner remain unchanged and are delegated to directly by ``aps_v5_frozen``.
The optimized arm additionally enforces a deterministic 84% soft context cap
with an override for the full CURRENT demand.
"""

from __future__ import annotations

import argparse
import ast
import asyncio
import copy
import hashlib
import inspect
import json
import os
import random
import shutil
import statistics
import sys
import tempfile
import textwrap
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from experiments import run_experiment_v4_claude as v4  # noqa: E402
from experiments import run_experiment_v5_corrected as v5  # noqa: E402
from experiments.aps_gxp_context import (  # noqa: E402
    ADMITTED_STATUSES,
    Bm25RelevanceIndex,
    canonical_manifest_sha256,
    declared_version,
    sha256_file,
    sha256_text,
    simulate_skill_change,
    validate_context_manifest,
)


V5_PARITY_CHECKPOINT = (
    PROJECT_ROOT
    / "experiments"
    / "results"
    / "experiment_v5_rejudged_full_outputs.json"
)
V6_DESIGN_PATH = (
    PROJECT_ROOT / "plan" / "jmir_aps_gxp_optimization_experiment_20260724.md"
)
DEFAULT_STAGE0_JSON = (
    PROJECT_ROOT
    / "experiments"
    / "results"
    / "experiment_v6_aps_gxp_stage0.json"
)
DEFAULT_STAGE0_MARKDOWN = (
    PROJECT_ROOT
    / "paper"
    / "jmir_ai"
    / "analysis_v6_aps_gxp"
    / "stage0_report.md"
)
DEFAULT_SMOKE_OUTPUT = (
    PROJECT_ROOT
    / "experiments"
    / "results"
    / "experiment_v6_aps_gxp_smoke.json"
)

FOUR_ARM_CONDITIONS = (
    "aps_v5_frozen",
    "aps_gxp_optimized",
    "flat_8000",
    "random_token_matched",
)
ARM_DEFINITIONS = {
    "aps_v5_frozen": "Exact corrected-v5 APS selection with v6 provenance only.",
    "aps_gxp_optimized": (
        "Corrected APS with deterministic non-CURRENT BM25 relevance admission "
        "and an 84% soft context cap with full CURRENT override."
    ),
    "flat_8000": "Uniform alphabetical full-corpus loading at 8000 tokens.",
    "random_token_matched": (
        "Seeded corpus order matched to optimized task/run context tokens."
    ),
}
RELEVANCE_ABSOLUTE_THRESHOLD = 10.0
RELEVANCE_RULE_VERSION = "bm25-k1-1.2-b-0.75-absolute-10.0"
OPTIMIZED_CONTEXT_BUDGET_PERCENT = 84
OPTIMIZATION_POLICY_VERSION = (
    "optimized-soft-cap-0.84-full-current-override-v1"
)
OPTIMIZED_CONTEXT_BUDGET_POLICY = (
    "optimized_84_percent_soft_cap_with_full_current_override"
)
EXPECTED_V5_CHECKPOINT_SHA256 = (
    "e337862a974fd2bb5cd1bd691875f1e6483b8acca5687cbe4e758f5fcb587ed8"
)
SMOKE_TASK_ID = "task-20-tfl-ae"
SCALAR_POLICY = "full_stored_response_no_character_truncation"
AGENT_MAX_TURNS = 6
AGENT_TIMEOUT_SECONDS = 420
AGENT_MAX_RETRIES = 1
AGENT_RETRY_DELAY_SECONDS = 5
JUDGE_MAX_TOKENS = 2000


def stable_run_key(task_id: str, arm: str, run_id: int) -> str:
    """Return the immutable task-arm-run key."""
    return f"{task_id}::{arm}::{run_id}"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_json_write(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    temporary.replace(path)


def build_complete_response_judge_prompt(
    task_id: str,
    response: str,
    domain_criteria: str,
) -> str:
    """Render the scalar rubric with the complete, unsliced stored response."""
    return v4.MULTI_DIM_JUDGE_PROMPT.format(
        task_description=v4.TASK_PROMPTS[task_id],
        domain_criteria=domain_criteria,
        response=response,
    )


def _complete_transmitted_agent_prompt(prompt: str) -> str:
    """Mirror the exact wrapper prepended inside the frozen v4 invocation."""
    source = textwrap.dedent(inspect.getsource(v4.invoke_claude_code))
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if not any(
            isinstance(target, ast.Name)
            and target.id == "no_tools_directive"
            for target in targets
        ):
            continue
        value = node.value
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            return value.value + prompt
    raise RuntimeError("Frozen v4 no-tools directive could not be resolved")


@dataclass(frozen=True)
class V6ContextCell:
    """One deterministic task-arm-run context construction."""

    task_id: str
    arm: str
    run_id: int
    context_result: Any
    prompt_context: str
    manifest: dict[str, Any]
    validation_errors: tuple[str, ...]

    @property
    def run_key(self) -> str:
        return stable_run_key(self.task_id, self.arm, self.run_id)


class ApsGxpExperimentRunner(v5.CorrectedExperimentRunner):
    """v6-only context composition over the unchanged v5 implementation."""

    def __init__(
        self,
        seed: int = 42,
        budget: int = 8000,
        network_enabled: bool = False,
    ):
        super().__init__(dry_run=not network_enabled, seed=seed, budget=budget)
        self.network_enabled = network_enabled
        self.agent_model_requested = os.getenv("AGENT_MODEL", "glm-5")
        self._corpus_names = tuple(self._all_corpus_skills())
        self._skill_documents = {
            name: self.context_builder.load_skill(name).content
            for name in self._corpus_names
        }
        self._corpus_manifest = [
            {
                "skill_name": name,
                "source_path": (
                    Path(self.context_builder.load_skill(name).path)
                    .resolve()
                    .relative_to(PROJECT_ROOT.resolve())
                    .as_posix()
                ),
                "source_sha256": sha256_file(
                    Path(self.context_builder.load_skill(name).path)
                ),
                "declared_version": declared_version(
                    self._skill_documents[name]
                ),
            }
            for name in sorted(self._corpus_names)
        ]
        self.relevance_index = Bm25RelevanceIndex(self._skill_documents)
        self._source_hashes_cache: dict[str, str] | None = None
        self._binding_nodes: dict[str, list[str]] = {
            name: sorted(
                node_id
                for node_id, node in self.nodes.items()
                if name
                in {
                    str(skill).lstrip("/")
                    for skill in node.get("skills_bound", [])
                }
            )
            for name in self._corpus_names
        }
        successor_counts = {node_id: 0 for node_id in self.nodes}
        for node in self.nodes.values():
            for dependency in node.get("dependencies", []):
                dependency_id = (
                    dependency.get("node", "")
                    if isinstance(dependency, dict)
                    else str(dependency)
                )
                if dependency_id in successor_counts:
                    successor_counts[dependency_id] += 1
        self._hub_degrees = {
            name: max(
                (
                    len(node.get("dependencies", []))
                    + successor_counts[node_id]
                    for node_id, node in self.nodes.items()
                    if name
                    in {
                        str(skill).lstrip("/")
                        for skill in node.get("skills_bound", [])
                    }
                ),
                default=0,
            )
            for name in self._corpus_names
        }

    def _fresh_builder(self) -> Any:
        return self.cl_module.ContextBuilder(
            project_root=PROJECT_ROOT,
            budget=self.budget,
            principle_store=None,
        )

    def source_hashes_v6(self) -> dict[str, str]:
        if self._source_hashes_cache is not None:
            return dict(self._source_hashes_cache)
        task_panel = {
            task_id: {
                "prompt": v4.TASK_PROMPTS[task_id],
                "node": v4.TASK_NODES[task_id],
            }
            for task_id in v4.QUICK_10_TASKS
        }
        paths = {
            "runner": Path(__file__),
            "v6_context": PROJECT_ROOT / "experiments" / "aps_gxp_context.py",
            "v5_runner": PROJECT_ROOT
            / "experiments"
            / "run_experiment_v5_corrected.py",
            "analyzer": PROJECT_ROOT
            / "experiments"
            / "analyze_aps_gxp_experiment.py",
            "scheduler": PROJECT_ROOT / "scripts" / "context-loader.py",
            "invocation": PROJECT_ROOT
            / "experiments"
            / "run_experiment_v4_claude.py",
            "graph": v4.GRAPH_PATH,
            "regulatory_patterns": v4.REGULATORY_PATTERNS_PATH,
            "design": V6_DESIGN_PATH,
        }
        hashes = {name: sha256_file(path) for name, path in paths.items()}
        hashes.update(
            {
                "system_prompt": sha256_text(v5.DOMAIN_SYSTEM_PROMPT),
                "task_panel": sha256_text(
                    json.dumps(task_panel, sort_keys=True, ensure_ascii=False)
                ),
                "judge_prompt": sha256_text(v4.MULTI_DIM_JUDGE_PROMPT),
                "relevance_rule": sha256_text(RELEVANCE_RULE_VERSION),
                "optimization_policy": sha256_text(
                    OPTIMIZATION_POLICY_VERSION
                ),
                "skill_manifest": sha256_text(
                    json.dumps(
                        self._corpus_manifest,
                        sort_keys=True,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    )
                ),
            }
        )
        self._source_hashes_cache = hashes
        return dict(hashes)

    def _relation_by_skill(
        self, node_id: str, router_result: Mapping[str, Any]
    ) -> dict[str, str]:
        current = [
            str(skill).lstrip("/")
            for skill in self.nodes.get(node_id, {}).get("skills_bound", [])
        ]
        successor = [
            str(skill).lstrip("/")
            for successor_id in router_result.get("successors", [])
            for skill in self.nodes.get(successor_id, {}).get("skills_bound", [])
        ]
        predecessor = [
            str(skill).lstrip("/")
            for predecessor_id in router_result.get("predecessors", [])
            for skill in self.nodes.get(predecessor_id, {}).get("skills_bound", [])
        ]
        globals_ = [
            str(skill).lstrip("/")
            for skill in self.graph_data.get("global_skills", [])
        ]
        relation: dict[str, str] = {}
        for label, names in (
            ("CURRENT", current),
            ("SUCCESSOR", successor),
            ("PREDECESSOR", predecessor),
            ("GLOBAL", globals_),
        ):
            for name in names:
                relation.setdefault(name, label)
        return relation

    def _new_context_result(self, node_id: str, router_result: Mapping[str, Any]) -> Any:
        return self.cl_module.ContextResult(
            node_id=node_id,
            layer=int(router_result.get("layer", 0)),
            layer_name=str(router_result.get("layer_name", "Unknown")),
            budget=self.budget,
        )

    def _summarize_context(
        self,
        result: Any,
        skills: Sequence[Any],
        strategy: str,
        scheduler: Any | None = None,
    ) -> Any:
        result.skills = list(skills)
        result.skills_loaded = sum(skill.status == "loaded" for skill in skills)
        result.skills_truncated = sum(
            skill.status == "truncated" for skill in skills
        )
        result.skills_dropped = sum(skill.status == "dropped" for skill in skills)
        result.skills_missing = sum(skill.status == "missing" for skill in skills)
        result.skill_tokens = sum(
            int(skill.token_estimate)
            for skill in skills
            if skill.status in ADMITTED_STATUSES
        )
        result.total_tokens = result.skill_tokens
        result.budget_used = result.total_tokens
        if scheduler is not None:
            result.current_floor_tokens = int(
                getattr(scheduler, "last_current_floor_tokens", 0)
            )
            result.current_tokens_used = int(
                getattr(scheduler, "last_current_tokens_used", 0)
            )
        result.band_summary = {}
        for band in self.cl_module.PriorityBand:
            band_skills = [skill for skill in skills if skill.band == band]
            result.band_summary[band.name] = {
                "candidates": len(band_skills),
                "loaded": sum(s.status == "loaded" for s in band_skills),
                "truncated": sum(s.status == "truncated" for s in band_skills),
                "dropped": sum(s.status == "dropped" for s in band_skills),
                "missing": sum(s.status == "missing" for s in band_skills),
                "tokens": sum(
                    int(s.token_estimate)
                    for s in band_skills
                    if s.status in ADMITTED_STATUSES
                ),
            }
        result.budget_strategy = (
            f"{strategy}: {result.skills_loaded} loaded | "
            f"{result.skills_truncated} truncated | "
            f"{result.skills_dropped} dropped | "
            f"{result.budget_used}/{self.budget} tokens"
        )
        return result

    def _build_optimized(
        self, task_id: str, node_id: str, router_result: Mapping[str, Any]
    ) -> tuple[Any, dict[str, int], dict[str, str]]:
        builder = self.context_builder
        scheduler = self.cl_module.AdaptivePriorityScheduler(self.budget)
        candidate_names = builder.collect_candidate_skills(
            node_id, dict(router_result)
        )
        skill_infos = [builder.load_skill(name) for name in candidate_names]
        original_tokens = {
            info.name: int(info.token_estimate) for info in skill_infos
        }
        current, successor, predecessor, globals_ = builder._band_skill_sets(
            node_id, dict(router_result)
        )
        classification = scheduler.classify_skills(
            candidate_names, current, successor, predecessor, globals_
        )
        relevance = {
            info.name: self.relevance_index.score(
                v4.TASK_PROMPTS[task_id], info.name
            )
            for info in skill_infos
        }
        v5_priority: dict[str, float] = {}
        for info in skill_infos:
            info.band = classification[info.name]
            info.hub_degree = self._hub_degrees.get(info.name, 0)
            v5_priority[info.name] = scheduler.compute_priority(
                info.band, info.name, info.hub_degree
            )
            # The 100-point band gaps make graph band lexicographically primary.
            # Relevance then ranks within a non-CURRENT band; hub score breaks
            # exact relevance ties. CURRENT ordering is the frozen v5 ordering.
            if info.band == self.cl_module.PriorityBand.CURRENT:
                info.priority_score = 1000.0 + v5_priority[info.name]
            else:
                bounded_relevance = min(99.0, relevance[info.name])
                info.priority_score = round(
                    1000.0
                    - 100.0 * int(info.band)
                    + bounded_relevance
                    + v5_priority[info.name] / 100.0,
                    12,
                )

        noncurrent = [
            info
            for info in skill_infos
            if info.band != self.cl_module.PriorityBand.CURRENT
            and info.exists
            and not info.error
        ]
        qualified_names = {
            info.name
            for info in noncurrent
            if relevance[info.name] >= RELEVANCE_ABSOLUTE_THRESHOLD
        }
        fallback_name: str | None = None
        if noncurrent and all(relevance[info.name] == 0.0 for info in noncurrent):
            fallback_name = sorted(
                noncurrent,
                key=lambda info: (
                    int(info.band),
                    -v5_priority[info.name],
                    info.name,
                ),
            )[0].name
            qualified_names.add(fallback_name)

        eligible: list[Any] = []
        excluded: list[Any] = []
        reason_basis: dict[str, str] = {}
        for info in skill_infos:
            if not info.exists or info.error:
                info.status = "missing"
                reason_basis[info.name] = "source_missing"
                excluded.append(info)
            elif info.band == self.cl_module.PriorityBand.CURRENT:
                reason_basis[info.name] = "current_protected"
                eligible.append(info)
            elif info.name == fallback_name:
                reason_basis[info.name] = "all_zero_single_best_fallback"
                eligible.append(info)
            elif info.name in qualified_names:
                reason_basis[info.name] = "relevance_qualified"
                eligible.append(info)
            else:
                info.status = "dropped"
                reason_basis[info.name] = "below_relevance_threshold"
                excluded.append(info)

        optimized_soft_cap = (
            self.budget * OPTIMIZED_CONTEXT_BUDGET_PERCENT
        ) // 100
        full_current_demand = sum(
            int(info.token_estimate)
            for info in eligible
            if info.band == self.cl_module.PriorityBand.CURRENT
            and info.exists
            and not info.error
        )
        if full_current_demand > self.budget:
            raise ValueError(
                "Full CURRENT demand exceeds the common context budget: "
                f"{full_current_demand}/{self.budget}"
            )
        effective_context_cap = min(
            self.budget,
            max(optimized_soft_cap, full_current_demand),
        )
        scheduler = self.cl_module.AdaptivePriorityScheduler(
            effective_context_cap
        )
        scheduled = scheduler.schedule(eligible, ref_tokens=0)
        for info in scheduled:
            if info.status == "dropped":
                reason_basis[info.name] = (
                    f"{reason_basis[info.name]}_budget_drop"
                )
            elif info.status == "truncated":
                reason_basis[info.name] = (
                    f"{reason_basis[info.name]}_truncated"
                )
            elif info.status == "loaded":
                reason_basis[info.name] = f"{reason_basis[info.name]}_loaded"
        result = self._new_context_result(node_id, router_result)
        result.context_budget_policy = OPTIMIZED_CONTEXT_BUDGET_POLICY
        result.optimized_soft_cap_tokens = optimized_soft_cap
        result.effective_context_cap_tokens = effective_context_cap
        result = self._summarize_context(
            result,
            [*scheduled, *sorted(excluded, key=lambda info: info.name)],
            "APS-GxP optimized",
            scheduler=scheduler,
        )
        return result, original_tokens, reason_basis

    def _exact_fragment(self, content: str, target_tokens: int) -> str:
        if target_tokens <= 0:
            return ""
        target_chars = target_tokens * self.cl_module.TokenEstimator.CHARS_PER_TOKEN
        if len(content) <= target_chars:
            return content
        marker = "\n[...token-matched truncation]"
        if len(marker) >= target_chars:
            return content[:target_chars]
        return content[: target_chars - len(marker)] + marker

    def _build_random_matched(
        self,
        task_id: str,
        node_id: str,
        run_id: int,
        router_result: Mapping[str, Any],
        target_tokens: int,
    ) -> tuple[Any, dict[str, int], dict[str, str]]:
        builder = self.context_builder
        ordered_names = list(self._corpus_names)
        random.Random(f"{self.seed}:{task_id}:{run_id}").shuffle(ordered_names)
        skill_infos = [builder.load_skill(name) for name in ordered_names]
        original_tokens = {
            info.name: int(info.token_estimate) for info in skill_infos
        }
        reasons: dict[str, str] = {}
        remaining = target_tokens
        for info in skill_infos:
            info.band = self.cl_module.PriorityBand.GLOBAL
            info.hub_degree = self._hub_degrees.get(info.name, 0)
            info.priority_score = 0.0
            if not info.exists or info.error:
                info.status = "missing"
                reasons[info.name] = "source_missing"
                continue
            if remaining <= 0:
                info.status = "dropped"
                reasons[info.name] = "random_target_reached"
                continue
            original = original_tokens[info.name]
            if original <= remaining:
                info.truncated_content = info.content
                info.status = "loaded"
                reasons[info.name] = "random_order_loaded"
                remaining -= original
                continue
            fragment = self._exact_fragment(info.content, remaining)
            actual = self.cl_module.TokenEstimator.estimate(fragment)
            info.truncated_content = fragment
            info.token_estimate = actual
            info.status = "truncated"
            reasons[info.name] = "random_final_fragment_truncated"
            remaining -= actual
        result = self._new_context_result(node_id, router_result)
        result = self._summarize_context(
            result, skill_infos, "Random token matched"
        )
        if abs(result.skill_tokens - target_tokens) > 1:
            raise ValueError(
                f"Random token match failed: {result.skill_tokens} vs {target_tokens}"
            )
        return result, original_tokens, reasons

    @staticmethod
    def _injected_fragment(skill: Any) -> str:
        content = skill.truncated_content or skill.content
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                content = parts[2].strip()
        return content

    def _manifest(
        self,
        task_id: str,
        arm: str,
        run_id: int,
        context_result: Any,
        prompt_context: str,
        original_tokens: Mapping[str, int],
        reasons: Mapping[str, str],
    ) -> dict[str, Any]:
        node_id, _ = v4.TASK_NODES[task_id]
        router_result = self._get_router_result(node_id)
        relation = self._relation_by_skill(node_id, router_result)
        candidates: list[dict[str, Any]] = []
        for skill in context_result.skills:
            path = Path(skill.path)
            relative_path = path.resolve().relative_to(
                PROJECT_ROOT.resolve()
            ).as_posix()
            fragment = (
                self._injected_fragment(skill)
                if skill.status in ADMITTED_STATUSES
                else ""
            )
            if arm in {"flat_8000", "random_token_matched"}:
                priority_band = "UNIFORM"
            else:
                priority_band = skill.band.name
            candidates.append(
                {
                    "skill_name": skill.name,
                    "source_path": relative_path,
                    "source_sha256": sha256_file(path),
                    "declared_version": declared_version(skill.content),
                    "active_node_id": node_id,
                    "skill_bound_node_ids": self._binding_nodes.get(
                        skill.name, []
                    ).copy(),
                    "graph_relation": relation.get(
                        skill.name, "OUT_OF_SCOPE"
                    ),
                    "priority_band": priority_band,
                    "lexical_relevance_score": self.relevance_index.score(
                        v4.TASK_PROMPTS[task_id], skill.name
                    ),
                    "hub_degree": int(getattr(skill, "hub_degree", 0)),
                    "final_priority_score": round(
                        float(skill.priority_score), 12
                    ),
                    "original_estimated_tokens": int(
                        original_tokens[skill.name]
                    ),
                    "injected_estimated_tokens": (
                        int(skill.token_estimate)
                        if skill.status in ADMITTED_STATUSES
                        else 0
                    ),
                    "status": skill.status,
                    "selection_reason": reasons[skill.name],
                    "injected_fragment_sha256": (
                        sha256_text(fragment)
                        if skill.status in ADMITTED_STATUSES
                        else None
                    ),
                }
            )
        source_hashes = self.source_hashes_v6()
        manifest: dict[str, Any] = {
            "schema_version": "aps-gxp-v6-context-manifest-1",
            "task_id": task_id,
            "arm": arm,
            "run_id": run_id,
            "seed": self.seed,
            "budget": self.budget,
            "budget_used": int(context_result.budget_used),
            "scheduler_sha256": source_hashes["scheduler"],
            "graph_sha256": source_hashes["graph"],
            "task_sha256": sha256_text(v4.TASK_PROMPTS[task_id]),
            "prompt_context_sha256": sha256_text(prompt_context),
            "candidates": candidates,
        }
        if arm == "aps_gxp_optimized":
            manifest.update(
                {
                    "context_budget_policy": getattr(
                        context_result, "context_budget_policy"
                    ),
                    "optimized_soft_cap_tokens": int(
                        getattr(
                            context_result, "optimized_soft_cap_tokens"
                        )
                    ),
                    "effective_context_cap_tokens": int(
                        getattr(
                            context_result, "effective_context_cap_tokens"
                        )
                    ),
                }
            )
        manifest["manifest_sha256"] = canonical_manifest_sha256(manifest)
        return manifest

    def build_context_cell(
        self, task_id: str, arm: str, run_id: int = 0
    ) -> V6ContextCell:
        if task_id not in v4.QUICK_10_TASKS:
            raise ValueError(f"Unknown v6 task: {task_id}")
        if arm not in FOUR_ARM_CONDITIONS:
            raise ValueError(f"Unknown v6 arm: {arm}")
        node_id, _ = v4.TASK_NODES[task_id]
        router_result = self._get_router_result(node_id)

        if arm == "aps_v5_frozen":
            context = self._build_routed_context(
                task_id, node_id, with_principles=False
            )
            original_tokens = {
                skill.name: self.cl_module.TokenEstimator.estimate(
                    self._skill_documents[skill.name]
                )
                for skill in context.skills
            }
            reasons = {
                skill.name: (
                    "frozen_v5_loaded"
                    if skill.status == "loaded"
                    else "frozen_v5_truncated"
                    if skill.status == "truncated"
                    else "frozen_v5_budget_drop"
                    if skill.status == "dropped"
                    else "source_missing"
                )
                for skill in context.skills
            }
        elif arm == "aps_gxp_optimized":
            context, original_tokens, reasons = self._build_optimized(
                task_id, node_id, router_result
            )
        elif arm == "flat_8000":
            context = self._build_uniform_context(
                node_id, list(self._corpus_names), "FLAT-8000"
            )
            original_tokens = {
                skill.name: self.cl_module.TokenEstimator.estimate(
                    self._skill_documents[skill.name]
                )
                for skill in context.skills
            }
            reasons = {
                skill.name: (
                    "uniform_loaded"
                    if skill.status == "loaded"
                    else "uniform_truncated"
                    if skill.status == "truncated"
                    else "uniform_budget_drop"
                    if skill.status == "dropped"
                    else "source_missing"
                )
                for skill in context.skills
            }
        else:
            optimized = self.build_context_cell(
                task_id, "aps_gxp_optimized", run_id
            )
            context, original_tokens, reasons = self._build_random_matched(
                task_id,
                node_id,
                run_id,
                router_result,
                target_tokens=int(optimized.context_result.skill_tokens),
            )

        prompt_context = self.cl_module.OutputFormatter.format_context(
            context, include_content=True
        )
        manifest = self._manifest(
            task_id,
            arm,
            run_id,
            context,
            prompt_context,
            original_tokens,
            reasons,
        )
        return V6ContextCell(
            task_id=task_id,
            arm=arm,
            run_id=run_id,
            context_result=context,
            prompt_context=prompt_context,
            manifest=manifest,
            validation_errors=tuple(
                [
                    *validate_context_manifest(manifest),
                    *validate_optimized_context_policy(manifest),
                ]
            ),
        )

    def context_checkpoint(
        self, cells: Iterable[V6ContextCell]
    ) -> dict[str, Any]:
        cell_list = list(cells)
        tasks = list(dict.fromkeys(cell.task_id for cell in cell_list))
        arms = list(dict.fromkeys(cell.arm for cell in cell_list))
        runs = sorted({cell.run_id for cell in cell_list})
        return {
            "metadata": {
                "version": "aps-gxp-v6-context-only-1",
                "dry_run": True,
                "seed": self.seed,
                "budget": self.budget,
                "tasks": tasks,
                "arms": arms,
                "runs": len(runs),
                "source_hashes": self.source_hashes_v6(),
            },
            "contexts": [
                {
                    "run_key": cell.run_key,
                    "task_id": cell.task_id,
                    "arm": cell.arm,
                    "run_id": cell.run_id,
                    "skills_tokens": int(cell.context_result.skill_tokens),
                    "budget_used": int(cell.context_result.budget_used),
                    "manifest_sha256": cell.manifest["manifest_sha256"],
                    "manifest": copy.deepcopy(cell.manifest),
                }
                for cell in cell_list
            ],
        }

    def generation_checkpoint(
        self,
        results: Sequence[Mapping[str, Any]],
        task_ids: Sequence[str],
        runs: int,
        failed_generation_attempts: Sequence[Mapping[str, Any]] = (),
    ) -> dict[str, Any]:
        return {
            "metadata": {
                "version": "aps-gxp-v6-generation-1",
                "dry_run": False,
                "seed": self.seed,
                "budget": self.budget,
                "tasks": list(task_ids),
                "arms": list(FOUR_ARM_CONDITIONS),
                "runs": runs,
                "agent": "Claude Code (claude -p)",
                "agent_model_requested": self.agent_model_requested,
                "agent_configuration": {
                    "max_turns": AGENT_MAX_TURNS,
                    "timeout_seconds": AGENT_TIMEOUT_SECONDS,
                    "max_retries": AGENT_MAX_RETRIES,
                    "retry_delay_seconds": AGENT_RETRY_DELAY_SECONDS,
                    "no_tools_directive_sha256": sha256_text(
                        _complete_transmitted_agent_prompt("")
                    ),
                },
                "domain_system_prompt_sha256": sha256_text(
                    v5.DOMAIN_SYSTEM_PROMPT
                ),
                "source_hashes": self.source_hashes_v6(),
                "arm_definitions": ARM_DEFINITIONS,
                "isolated_working_directory_all_calls": True,
                "judging_policy": SCALAR_POLICY,
                "judge_model_requested": self.judge_model,
                "judge_configuration": {
                    "temperature": 0.0,
                    "max_tokens": JUDGE_MAX_TOKENS,
                    "complete_response_policy": SCALAR_POLICY,
                },
                "pairwise_judging": "omitted",
                "updated_at": _utc_now(),
            },
            "results": list(results),
            "failed_generation_attempts": list(
                failed_generation_attempts
            ),
        }


def _manifest_scope(manifest: Mapping[str, Any]) -> dict[str, dict[str, int]]:
    scope = {
        "current": {"skills": 0, "tokens": 0},
        "relevance_qualified_adjacent": {"skills": 0, "tokens": 0},
        "global": {"skills": 0, "tokens": 0},
        "out_of_scope": {"skills": 0, "tokens": 0},
    }
    for candidate in manifest.get("candidates", []):
        if candidate.get("status") not in ADMITTED_STATUSES:
            continue
        relation = candidate.get("graph_relation")
        if relation == "CURRENT":
            category = "current"
        elif relation in {"SUCCESSOR", "PREDECESSOR"}:
            category = "relevance_qualified_adjacent"
        elif relation == "GLOBAL":
            category = "global"
        else:
            category = "out_of_scope"
        scope[category]["skills"] += 1
        scope[category]["tokens"] += int(
            candidate.get("injected_estimated_tokens", 0)
        )
    return scope


def validate_optimized_context_policy(
    manifest: Mapping[str, Any],
) -> list[str]:
    """Validate the deterministic optimized soft cap and CURRENT override."""
    if manifest.get("arm") != "aps_gxp_optimized":
        return []

    errors: list[str] = []
    budget = manifest.get("budget")
    budget_used = manifest.get("budget_used")
    candidates = manifest.get("candidates")
    if (
        isinstance(budget, bool)
        or not isinstance(budget, int)
        or isinstance(budget_used, bool)
        or not isinstance(budget_used, int)
        or not isinstance(candidates, list)
    ):
        return ["optimized context policy inputs are invalid"]

    current_candidates = [
        candidate
        for candidate in candidates
        if isinstance(candidate, Mapping)
        and candidate.get("graph_relation") == "CURRENT"
    ]
    current_token_values: list[int] = []
    for candidate in current_candidates:
        value = candidate.get("original_estimated_tokens")
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            return [
                "optimized context policy CURRENT token demand is invalid"
            ]
        current_token_values.append(value)

    optimized_soft_cap = (
        budget * OPTIMIZED_CONTEXT_BUDGET_PERCENT
    ) // 100
    full_current_demand = sum(current_token_values)
    if full_current_demand > budget:
        errors.append(
            "optimized context policy full CURRENT demand exceeds "
            f"the common budget: {full_current_demand}/{budget}"
        )
    effective_context_cap = min(
        budget,
        max(optimized_soft_cap, full_current_demand),
    )
    expected_fields = {
        "context_budget_policy": OPTIMIZED_CONTEXT_BUDGET_POLICY,
        "optimized_soft_cap_tokens": optimized_soft_cap,
        "effective_context_cap_tokens": effective_context_cap,
    }
    for field, expected in expected_fields.items():
        if manifest.get(field) != expected:
            errors.append(
                "optimized context policy "
                f"{field} mismatch: {manifest.get(field)!r} != {expected!r}"
            )
    if budget_used > effective_context_cap:
        errors.append(
            "optimized context policy effective cap violation: "
            f"{budget_used}/{effective_context_cap}"
        )
    for candidate in current_candidates:
        if (
            candidate.get("status") != "loaded"
            or candidate.get("injected_estimated_tokens")
            != candidate.get("original_estimated_tokens")
        ):
            errors.append(
                "optimized context policy failed to load full CURRENT skill: "
                f"{candidate.get('skill_name')}"
            )
    return errors


def _v5_signature_from_row(
    row: Mapping[str, Any],
) -> tuple[tuple[str, str, str, int], ...]:
    return tuple(
        (
            str(skill["name"]),
            str(skill["band"]),
            str(skill["status"]),
            int(skill["tokens"]),
        )
        for skill in row["context_audit"]["skills"]
    )


def _v5_signature_from_cell(
    cell: V6ContextCell,
) -> tuple[tuple[str, str, str, int], ...]:
    return tuple(
        (
            skill.name,
            skill.band.name,
            skill.status,
            int(skill.token_estimate),
        )
        for skill in cell.context_result.skills
    )


def _frozen_parity(
    cells: Mapping[tuple[str, str], V6ContextCell]
) -> tuple[bool, dict[str, Any]]:
    checkpoint_bytes = V5_PARITY_CHECKPOINT.read_bytes()
    checkpoint_hash = hashlib.sha256(checkpoint_bytes).hexdigest()
    data = json.loads(checkpoint_bytes)
    rows = [
        row
        for row in data["results"]
        if row["condition"] == "agent_framework"
    ]
    task_results: dict[str, bool] = {}
    for task_id in v4.QUICK_10_TASKS:
        stored = {
            _v5_signature_from_row(row)
            for row in rows
            if row["task_id"] == task_id
        }
        actual = _v5_signature_from_cell(
            cells[(task_id, "aps_v5_frozen")]
        )
        task_results[task_id] = len(stored) == 1 and actual in stored
    passed = (
        checkpoint_hash == EXPECTED_V5_CHECKPOINT_SHA256
        and len(rows) == 30
        and all(task_results.values())
    )
    return passed, {
        "checkpoint_sha256": checkpoint_hash,
        "expected_checkpoint_sha256": EXPECTED_V5_CHECKPOINT_SHA256,
        "stored_framework_rows": len(rows),
        "task_parity": task_results,
    }


def _change_impact(
    cells: Mapping[tuple[str, str], V6ContextCell],
    task_ids: Sequence[str],
    skill_names: Sequence[str],
) -> dict[str, Any]:
    per_arm: dict[str, Any] = {}
    for arm in FOUR_ARM_CONDITIONS:
        counts: dict[str, int] = {}
        for skill_name in skill_names:
            changed_count = 0
            for task_id in task_ids:
                manifest = cells[(task_id, arm)].manifest
                perturbed = simulate_skill_change(manifest, skill_name)
                changed_count += (
                    perturbed["manifest_sha256"]
                    != manifest["manifest_sha256"]
                )
            counts[skill_name] = changed_count
        values = list(counts.values())
        proportions = {
            skill_name: (
                affected / len(task_ids) if task_ids else 0.0
            )
            for skill_name, affected in counts.items()
        }
        proportion_values = list(proportions.values())
        per_arm[arm] = {
            "per_skill_affected_tasks": counts,
            "per_skill_affected_task_proportion": proportions,
            "mean_affected_tasks": statistics.mean(values) if values else 0.0,
            "median_affected_tasks": statistics.median(values) if values else 0.0,
            "range_affected_tasks": (
                [min(values), max(values)] if values else [0, 0]
            ),
            "mean_affected_task_proportion": (
                statistics.mean(proportion_values)
                if proportion_values
                else 0.0
            ),
            "median_affected_task_proportion": (
                statistics.median(proportion_values)
                if proportion_values
                else 0.0
            ),
            "range_affected_task_proportion": (
                [min(proportion_values), max(proportion_values)]
                if proportion_values
                else [0.0, 0.0]
            ),
        }
    optimized = per_arm["aps_gxp_optimized"]["per_skill_affected_tasks"]
    flat = per_arm["flat_8000"]["per_skill_affected_tasks"]
    paired = {
        skill_name: optimized[skill_name] - flat[skill_name]
        for skill_name in skill_names
    }
    return {
        "per_arm": per_arm,
        "paired_optimized_minus_flat": paired,
    }


def build_stage0_report(
    runner: ApsGxpExperimentRunner,
    task_ids: Sequence[str] = tuple(v4.QUICK_10_TASKS),
    repeats: int = 3,
) -> dict[str, Any]:
    """Build repeated no-network contexts and evaluate every Stage-0 gate."""
    if repeats != 3:
        # Tests may pass a task subset, but the reproducibility rule remains fixed.
        raise ValueError("Stage 0 requires exactly three repeated builds")
    repeated: dict[tuple[str, str], list[V6ContextCell]] = {}
    for task_id in task_ids:
        for arm in FOUR_ARM_CONDITIONS:
            repeated[(task_id, arm)] = [
                runner.build_context_cell(task_id, arm, run_id=0)
                for _ in range(repeats)
            ]
    first = {key: builds[0] for key, builds in repeated.items()}

    cell_rows: list[dict[str, Any]] = []
    admitted_fragments = 0
    complete_fragments = 0
    for (task_id, arm), builds in repeated.items():
        manifest = builds[0].manifest
        admitted = [
            candidate
            for candidate in manifest["candidates"]
            if candidate["status"] in ADMITTED_STATUSES
        ]
        admitted_fragments += len(admitted)
        complete_fragments += (
            len(admitted) if not builds[0].validation_errors else 0
        )
        cell_rows.append(
            {
                "task_id": task_id,
                "arm": arm,
                "run_id": 0,
                "skills_tokens": int(builds[0].context_result.skill_tokens),
                "budget_used": int(builds[0].context_result.budget_used),
                "candidate_count": len(manifest["candidates"]),
                "admitted_skills": [
                    candidate["skill_name"] for candidate in admitted
                ],
                "manifest_sha256": manifest["manifest_sha256"],
                "repeated_manifest_sha256": [
                    build.manifest["manifest_sha256"] for build in builds
                ],
                "provenance_complete": not builds[0].validation_errors,
                "validation_errors": list(builds[0].validation_errors),
                "scope": _manifest_scope(manifest),
            }
        )

    all_validation_errors = [
        error
        for builds in repeated.values()
        for build in builds
        for error in build.validation_errors
    ]
    reproducible_cells = sum(
        len({build.manifest["manifest_sha256"] for build in builds}) == 1
        for builds in repeated.values()
    )
    total_cells = len(repeated)
    optimized_tokens = [
        int(first[(task_id, "aps_gxp_optimized")].context_result.skill_tokens)
        for task_id in task_ids
    ]
    flat_tokens = [
        int(first[(task_id, "flat_8000")].context_result.skill_tokens)
        for task_id in task_ids
    ]
    random_differences = [
        abs(
            int(
                first[
                    (task_id, "random_token_matched")
                ].context_result.skill_tokens
            )
            - int(
                first[(task_id, "aps_gxp_optimized")].context_result.skill_tokens
            )
        )
        for task_id in task_ids
    ]
    reductions = sum(
        optimized <= 0.85 * flat
        for optimized, flat in zip(optimized_tokens, flat_tokens)
    )
    current_parity: dict[str, bool] = {}
    for task_id in task_ids:
        frozen_current = {
            (
                candidate["skill_name"],
                candidate["status"],
                candidate["injected_estimated_tokens"],
            )
            for candidate in first[
                (task_id, "aps_v5_frozen")
            ].manifest["candidates"]
            if candidate["graph_relation"] == "CURRENT"
        }
        optimized_current = {
            (
                candidate["skill_name"],
                candidate["status"],
                candidate["injected_estimated_tokens"],
            )
            for candidate in first[
                (task_id, "aps_gxp_optimized")
            ].manifest["candidates"]
            if candidate["graph_relation"] == "CURRENT"
        }
        current_parity[task_id] = frozen_current == optimized_current

    relevance_varies = False
    grouped_nodes: dict[str, list[str]] = {}
    for task_id in task_ids:
        grouped_nodes.setdefault(v4.TASK_NODES[task_id][0], []).append(task_id)
    for same_node_tasks in grouped_nodes.values():
        if len(same_node_tasks) < 2:
            continue
        task_a, task_b = same_node_tasks[:2]
        scores_a = {
            row["skill_name"]: row["lexical_relevance_score"]
            for row in first[
                (task_a, "aps_gxp_optimized")
            ].manifest["candidates"]
            if row["priority_band"] != "CURRENT"
        }
        scores_b = {
            row["skill_name"]: row["lexical_relevance_score"]
            for row in first[
                (task_b, "aps_gxp_optimized")
            ].manifest["candidates"]
            if row["priority_band"] != "CURRENT"
        }
        relevance_varies |= any(
            scores_a[name] != scores_b[name]
            for name in set(scores_a) & set(scores_b)
        )

    tfl_difference: bool | None = None
    tfl_tasks = {"task-17-tfl-demographics", "task-20-tfl-ae"}
    if tfl_tasks <= set(task_ids):
        selections = []
        for task_id in sorted(tfl_tasks):
            selections.append(
                {
                    row["skill_name"]
                    for row in first[
                        (task_id, "aps_gxp_optimized")
                    ].manifest["candidates"]
                    if row["priority_band"] != "CURRENT"
                    and row["status"] in ADMITTED_STATUSES
                }
            )
        tfl_difference = selections[0] != selections[1]

    full_panel = tuple(task_ids) == tuple(v4.QUICK_10_TASKS)
    frozen_pass, frozen_actual = (
        _frozen_parity(first)
        if full_panel
        else (True, {"not_evaluated_for_task_subset": True})
    )
    change_impact = _change_impact(
        first, task_ids, runner._corpus_names
    )
    change_impact_again = _change_impact(
        first, task_ids, runner._corpus_names
    )
    median_optimized = statistics.median(optimized_tokens)

    gates: dict[str, dict[str, Any]] = {
        "frozen_v5_parity": {
            "pass": frozen_pass,
            "actual": frozen_actual,
            "expected": "all 10 task projections match the hashed v5 checkpoint",
        },
        "context_cardinality": {
            "pass": total_cells == len(task_ids) * 4,
            "actual": total_cells,
            "expected": len(task_ids) * 4,
        },
        "budgets": {
            "pass": all(row["budget_used"] <= runner.budget for row in cell_rows),
            "actual": max(row["budget_used"] for row in cell_rows),
            "expected": f"maximum <= {runner.budget}",
        },
        "relevance_score_variation": {
            "pass": relevance_varies,
            "actual": relevance_varies,
            "expected": "at least one same-node task pair varies",
        },
        "current_protection": {
            "pass": all(current_parity.values()),
            "actual": current_parity,
            "expected": (
                "optimized CURRENT names/statuses/tokens equal frozen CURRENT"
            ),
        },
        "optimized_median_context": {
            "pass": 4000 <= median_optimized <= 7200,
            "actual": median_optimized,
            "expected": "[4000, 7200]",
        },
        "optimized_max_context": {
            "pass": max(optimized_tokens) <= 8000,
            "actual": max(optimized_tokens),
            "expected": "<= 8000",
        },
        "optimized_15_percent_reduction": {
            "pass": reductions >= (6 if full_panel else 0),
            "actual": reductions,
            "expected": "at least 6 of 10 tasks" if full_panel else "descriptive subset",
        },
        "tfl_noncurrent_selection_difference": {
            "pass": tfl_difference is True if tfl_difference is not None else True,
            "actual": tfl_difference,
            "expected": "the two fixed TFL tasks differ",
        },
        "provenance_completeness": {
            "pass": not all_validation_errors
            and admitted_fragments == complete_fragments,
            "actual": (
                100.0
                if not admitted_fragments
                else 100.0 * complete_fragments / admitted_fragments
            ),
            "expected": "100%",
        },
        "manifest_reproducibility": {
            "pass": reproducible_cells == total_cells,
            "actual": (
                100.0 if not total_cells else 100.0 * reproducible_cells / total_cells
            ),
            "expected": "100% across three builds",
        },
        "random_token_matching": {
            "pass": max(random_differences) <= 1,
            "actual": max(random_differences),
            "expected": "<= 1 estimated token",
        },
        "change_impact_determinism": {
            "pass": change_impact == change_impact_again,
            "actual": change_impact == change_impact_again,
            "expected": True,
        },
        "no_secrets_or_absolute_paths": {
            "pass": not all_validation_errors,
            "actual": all_validation_errors,
            "expected": [],
        },
    }
    return {
        "report_version": "aps-gxp-v6-stage0-1",
        "generated_at": _utc_now(),
        "network_calls": 0,
        "seed": runner.seed,
        "budget": runner.budget,
        "task_ids": list(task_ids),
        "task_count": len(task_ids),
        "arms": list(FOUR_ARM_CONDITIONS),
        "repeats": repeats,
        "relevance_rule": {
            "version": RELEVANCE_RULE_VERSION,
            "absolute_threshold": RELEVANCE_ABSOLUTE_THRESHOLD,
        },
            "optimization_policy": {
                "version": OPTIMIZATION_POLICY_VERSION,
                "soft_cap_ratio": (
                    OPTIMIZED_CONTEXT_BUDGET_PERCENT / 100
                ),
                "full_current_override": True,
            },
        "source_hashes": runner.source_hashes_v6(),
        "actuals": {
            "context_cells": total_cells,
            "context_builds": total_cells * repeats,
            "optimized_tokens": dict(zip(task_ids, optimized_tokens)),
            "flat_tokens": dict(zip(task_ids, flat_tokens)),
            "random_token_differences": dict(zip(task_ids, random_differences)),
            "change_impact": change_impact,
        },
        "gates": gates,
        "all_gates_pass": all(gate["pass"] for gate in gates.values()),
        "cells": cell_rows,
    }


def render_stage0_markdown(report: Mapping[str, Any]) -> str:
    lines = [
        "# APS-GxP v6 Stage-0 Report",
        "",
        f"Network calls: **{report['network_calls']}**",
        f"Context cells/builds: **{report['actuals']['context_cells']} / "
        f"{report['actuals']['context_builds']}**",
        f"Overall: **{'PASS' if report['all_gates_pass'] else 'FAIL'}**",
        "",
        "## Gates",
        "",
        "| Gate | Result | Actual | Expected |",
        "|---|---|---|---|",
    ]
    for name, gate in report["gates"].items():
        actual = json.dumps(gate["actual"], sort_keys=True, ensure_ascii=False)
        expected = str(gate["expected"])
        lines.append(
            f"| `{name}` | {'PASS' if gate['pass'] else 'FAIL'} | "
            f"`{actual}` | {expected} |"
        )
    lines.extend(
        [
            "",
            "## Source Hashes",
            "",
            *[
                f"- `{name}`: `{digest}`"
                for name, digest in report["source_hashes"].items()
            ],
            "",
            "These are deterministic GxP-oriented governance proxies; they do not "
            "establish operational GxP compliance.",
            "",
        ]
    )
    return "\n".join(lines)


def _validate_row_linkage(
    row: Mapping[str, Any],
    metadata: Mapping[str, Any],
    context_only: bool,
) -> list[str]:
    """Link the public row identity to its manifest and frozen configuration."""
    errors: list[str] = []
    task_id = row.get("task_id")
    arm = row.get("arm")
    run_id = row.get("run_id")
    key = row.get("run_key")
    if (
        not isinstance(task_id, str)
        or not isinstance(arm, str)
        or isinstance(run_id, bool)
        or not isinstance(run_id, int)
        or key != stable_run_key(task_id, arm, run_id)
    ):
        errors.append(f"{key}: row identity does not match run key")
        return errors
    manifest = row.get("manifest", {})
    if any(
        manifest.get(field) != value
        for field, value in (
            ("task_id", task_id),
            ("arm", arm),
            ("run_id", run_id),
            ("seed", metadata.get("seed")),
            ("budget", metadata.get("budget")),
        )
    ):
        errors.append(f"{key}: manifest identity/configuration mismatch")
    if task_id not in v4.TASK_PROMPTS:
        errors.append(f"{key}: unknown task")
    else:
        if manifest.get("task_sha256") != sha256_text(v4.TASK_PROMPTS[task_id]):
            errors.append(f"{key}: manifest task hash mismatch")
        if not context_only and row.get("graph_node") != v4.TASK_NODES[task_id][0]:
            errors.append(f"{key}: graph node does not match task")
    if row.get("budget_used") != manifest.get("budget_used"):
        errors.append(f"{key}: row/manifest budget linkage mismatch")
    admitted_tokens = sum(
        int(candidate.get("injected_estimated_tokens", 0))
        for candidate in manifest.get("candidates", [])
        if isinstance(candidate, Mapping)
        and candidate.get("status") in ADMITTED_STATUSES
    )
    if row.get("skills_tokens") != admitted_tokens:
        errors.append(f"{key}: row/manifest skill-token linkage mismatch")
    if not context_only:
        criteria = row.get("judge_domain_criteria")
        if (
            not isinstance(criteria, str)
            or not criteria
            or row.get("judge_domain_criteria_sha256")
            != sha256_text(criteria)
        ):
            errors.append(f"{key}: judge criteria hash linkage mismatch")
    return errors


def validate_random_token_matching(
    checkpoint: Mapping[str, Any],
) -> list[str]:
    """Verify each random context matches its optimized task/run target."""
    rows = checkpoint.get("results", checkpoint.get("contexts", []))
    if not isinstance(rows, list):
        return ["random token matching rows must be a list"]
    by_cell = {
        (
            row.get("task_id"),
            row.get("arm"),
            row.get("run_id"),
        ): row
        for row in rows
        if isinstance(row, Mapping)
    }
    errors: list[str] = []
    task_runs = {
        (task_id, run_id)
        for task_id, arm, run_id in by_cell
        if arm in {"aps_gxp_optimized", "random_token_matched"}
    }
    for task_id, run_id in sorted(task_runs):
        optimized = by_cell.get(
            (task_id, "aps_gxp_optimized", run_id)
        )
        random_row = by_cell.get(
            (task_id, "random_token_matched", run_id)
        )
        if optimized is None or random_row is None:
            continue
        optimized_tokens = optimized.get("skills_tokens")
        random_tokens = random_row.get("skills_tokens")
        if (
            isinstance(optimized_tokens, bool)
            or not isinstance(optimized_tokens, int)
            or isinstance(random_tokens, bool)
            or not isinstance(random_tokens, int)
            or abs(random_tokens - optimized_tokens) > 1
        ):
            errors.append(
                "random token match failed for "
                f"{task_id} run {run_id}: "
                f"{random_tokens!r} vs {optimized_tokens!r}"
            )
    return errors


def validate_v6_checkpoint(
    checkpoint: Mapping[str, Any],
    context_only: bool = False,
    require_judgments: bool = False,
    allow_partial: bool = False,
) -> list[str]:
    """Validate cardinality, keys, budgets, manifests, and scalar proof."""
    errors: list[str] = []
    metadata = checkpoint.get("metadata", {})
    rows_key = "contexts" if context_only else "results"
    rows = checkpoint.get(rows_key, [])
    if not isinstance(rows, list):
        return [f"{rows_key} must be a list"]
    errors.extend(validate_random_token_matching(checkpoint))
    keys = [row.get("run_key") for row in rows]
    if len(keys) != len(set(keys)):
        errors.append(f"duplicate {rows_key} run keys")
    for row in rows:
        errors.extend(_validate_row_linkage(row, metadata, context_only))
        manifest = row.get("manifest", {})
        errors.extend(
            f"{row.get('run_key')}: {error}"
            for error in (
                *validate_context_manifest(manifest),
                *validate_optimized_context_policy(manifest),
            )
        )
        if row.get("manifest_sha256") != manifest.get("manifest_sha256"):
            errors.append(f"{row.get('run_key')}: manifest hash linkage mismatch")
        if row.get("budget_used", manifest.get("budget_used", 0)) > metadata.get(
            "budget", 0
        ):
            errors.append(f"{row.get('run_key')}: budget violation")
        if not context_only:
            response = str(row.get("response", ""))
            if row.get("response_sha256") != sha256_text(response):
                errors.append(f"{row.get('run_key')}: response hash mismatch")
            if row.get("is_error_response") is not False:
                errors.append(f"{row.get('run_key')}: agent generation failed")
            if any(
                not row.get(field)
                for field in (
                    "agent_model_requested",
                    "agent_model_returned",
                )
            ):
                errors.append(
                    f"{row.get('run_key')}: agent model identity missing"
                )
            if row.get("agent_model_requested") != metadata.get(
                "agent_model_requested"
            ):
                errors.append(
                    f"{row.get('run_key')}: requested agent model mismatch"
                )
            repeated_hashes = row.get("repeated_manifest_sha256")
            if (
                not isinstance(repeated_hashes, list)
                or len(repeated_hashes) != 3
                or set(repeated_hashes) != {manifest.get("manifest_sha256")}
            ):
                errors.append(
                    f"{row.get('run_key')}: repeated manifest proof invalid"
                )
            if require_judgments:
                judgment = row.get("scalar_judgment", {})
                if judgment.get("policy") != SCALAR_POLICY:
                    errors.append(
                        f"{row.get('run_key')}: scalar judgment policy missing"
                    )
                if judgment.get("truncated") is not False:
                    errors.append(
                        f"{row.get('run_key')}: scalar response was truncated"
                    )
                if judgment.get("response_sha256") != sha256_text(response):
                    errors.append(
                        f"{row.get('run_key')}: scalar response hash mismatch"
                    )
                if judgment.get("response_characters_judged") != len(response):
                    errors.append(
                        f"{row.get('run_key')}: scalar response length mismatch"
                    )
                if judgment.get("response_bytes_judged") != len(
                    response.encode("utf-8")
                ):
                    errors.append(
                        f"{row.get('run_key')}: scalar response byte mismatch"
                    )
                domain_criteria = row.get("judge_domain_criteria")
                if not isinstance(domain_criteria, str):
                    errors.append(
                        f"{row.get('run_key')}: judge domain criteria missing"
                    )
                elif row.get("task_id") in v4.TASK_PROMPTS:
                    rendered_prompt = build_complete_response_judge_prompt(
                        str(row["task_id"]), response, domain_criteria
                    )
                    if judgment.get(
                        "rendered_prompt_sha256"
                    ) != sha256_text(rendered_prompt):
                        errors.append(
                            f"{row.get('run_key')}: scalar prompt hash mismatch"
                        )
                    if judgment.get(
                        "rendered_prompt_characters"
                    ) != len(rendered_prompt) or judgment.get(
                        "rendered_prompt_bytes"
                    ) != len(
                        rendered_prompt.encode("utf-8")
                    ):
                        errors.append(
                            f"{row.get('run_key')}: scalar prompt length mismatch"
                        )
                if any(
                    not judgment.get(field)
                    for field in (
                        "judge_model_requested",
                        "judge_model_returned",
                        "judge_response_id",
                        "finish_reason",
                    )
                ):
                    errors.append(
                        f"{row.get('run_key')}: judge identity or finish reason missing"
                    )
                if judgment.get("judge_model_requested") != metadata.get(
                    "judge_model_requested"
                ):
                    errors.append(
                        f"{row.get('run_key')}: requested judge model mismatch"
                    )
                if "system_fingerprint" not in judgment:
                    errors.append(
                        f"{row.get('run_key')}: system fingerprint field missing"
                    )
                expected_fingerprint_capture = (
                    "available"
                    if judgment.get("system_fingerprint")
                    else "provider_returned_null"
                )
                if (
                    judgment.get("system_fingerprint_capture")
                    != expected_fingerprint_capture
                ):
                    errors.append(
                        f"{row.get('run_key')}: system fingerprint capture "
                        "status invalid"
                    )
                if any(
                    not isinstance(judgment.get(field), int)
                    or judgment[field] < 0
                    for field in ("judge_input_tokens", "judge_output_tokens")
                ):
                    errors.append(
                        f"{row.get('run_key')}: judge token usage invalid"
                    )
                if judgment.get("judge_parse_error"):
                    errors.append(
                        f"{row.get('run_key')}: scalar parse error"
                    )

    if not context_only and not allow_partial:
        tasks = metadata.get("tasks", [])
        arms = metadata.get("arms", [])
        runs = int(metadata.get("runs", 0))
        expected = len(tasks) * len(arms) * runs
        if len(rows) != expected:
            errors.append(f"generation cardinality {len(rows)} != {expected}")
        expected_keys = {
            stable_run_key(task_id, arm, run_id)
            for task_id in tasks
            for arm in arms
            for run_id in range(runs)
        }
        if set(keys) != expected_keys:
            errors.append("generation run-key set does not match configured panel")
    return errors


def validate_resume_configuration(
    checkpoint: Mapping[str, Any],
    runner: ApsGxpExperimentRunner,
    task_ids: Sequence[str],
    runs: int,
) -> list[str]:
    """Fail closed unless a partial checkpoint has the immutable run config."""
    errors: list[str] = []
    metadata = checkpoint.get("metadata", {})
    expected = {
        "version": "aps-gxp-v6-generation-1",
        "seed": runner.seed,
        "budget": runner.budget,
        "tasks": list(task_ids),
        "arms": list(FOUR_ARM_CONDITIONS),
        "runs": runs,
        "domain_system_prompt_sha256": sha256_text(
            v5.DOMAIN_SYSTEM_PROMPT
        ),
        "agent_model_requested": runner.agent_model_requested,
        "agent_configuration": {
            "max_turns": AGENT_MAX_TURNS,
            "timeout_seconds": AGENT_TIMEOUT_SECONDS,
            "max_retries": AGENT_MAX_RETRIES,
            "retry_delay_seconds": AGENT_RETRY_DELAY_SECONDS,
            "no_tools_directive_sha256": sha256_text(
                _complete_transmitted_agent_prompt("")
            ),
        },
        "judge_model_requested": runner.judge_model,
        "judge_configuration": {
            "temperature": 0.0,
            "max_tokens": JUDGE_MAX_TOKENS,
            "complete_response_policy": SCALAR_POLICY,
        },
    }
    for field, expected_value in expected.items():
        if metadata.get(field) != expected_value:
            errors.append(
                f"resume {field} mismatch: "
                f"{metadata.get(field)!r} != {expected_value!r}"
            )
    if metadata.get("source_hashes") != runner.source_hashes_v6():
        errors.append("resume source hashes do not match current v6 sources")

    rows = checkpoint.get("results", [])
    if not isinstance(rows, list):
        return [*errors, "resume results must be a list"]
    keys = [row.get("run_key") for row in rows]
    if len(keys) != len(set(keys)):
        errors.append("resume checkpoint has duplicate run keys")
    expected_keys = {
        stable_run_key(task_id, arm, run_id)
        for task_id in task_ids
        for arm in FOUR_ARM_CONDITIONS
        for run_id in range(runs)
    }
    if not set(keys) <= expected_keys:
        errors.append("resume checkpoint contains out-of-panel run keys")
    for row in rows:
        key = row.get("run_key")
        errors.extend(_validate_row_linkage(row, metadata, context_only=False))
        manifest = row.get("manifest", {})
        errors.extend(
            f"{key}: {error}"
            for error in (
                *validate_context_manifest(manifest),
                *validate_optimized_context_policy(manifest),
            )
        )
        if row.get("manifest_sha256") != manifest.get("manifest_sha256"):
            errors.append(f"{key}: resume manifest linkage mismatch")
        response = str(row.get("response", ""))
        if row.get("response_sha256") != sha256_text(response):
            errors.append(f"{key}: resume response hash mismatch")
        if not row.get("isolated_working_directory"):
            errors.append(f"{key}: resume isolation flag missing")
        if row.get("agent_model_requested") != runner.agent_model_requested:
            errors.append(f"{key}: resume requested agent model mismatch")
        if not row.get("agent_model_returned"):
            errors.append(f"{key}: resume returned agent model missing")
        graph_node = row.get("graph_node")
        expected_criteria = (
            runner._get_judge_criteria(str(graph_node))
            if isinstance(graph_node, str)
            else None
        )
        if (
            expected_criteria is None
            or row.get("judge_domain_criteria") != expected_criteria
            or row.get("judge_domain_criteria_sha256")
            != sha256_text(expected_criteria)
        ):
            errors.append(f"{key}: resume judge criteria mismatch")
        if row.get("is_error_response") is not False:
            errors.append(f"{key}: resume contains a failed generation")
        repeated_hashes = row.get("repeated_manifest_sha256")
        if (
            not isinstance(repeated_hashes, list)
            or len(repeated_hashes) != 3
            or set(repeated_hashes) != {manifest.get("manifest_sha256")}
        ):
            errors.append(f"{key}: resume repeated manifest proof invalid")
    return errors


def run_generation(
    runner: ApsGxpExperimentRunner,
    task_ids: Sequence[str],
    runs: int,
    output_path: Path,
) -> dict[str, Any]:
    """Generate responses only; this function never calls the judge."""
    if not runner.network_enabled:
        raise PermissionError("Paid generation is not enabled")
    results: list[dict[str, Any]] = []
    failed_generation_attempts: list[dict[str, Any]] = []
    if output_path.exists():
        existing = json.loads(output_path.read_text(encoding="utf-8"))
        resume_errors = validate_resume_configuration(
            existing, runner, task_ids, runs
        )
        if resume_errors:
            raise ValueError(
                f"Resume checkpoint configuration mismatch: {resume_errors}"
            )
        results = list(existing.get("results", []))
        failed_generation_attempts = list(
            existing.get("failed_generation_attempts", [])
        )
    completed = {row["run_key"] for row in results}
    jobs = [
        (task_id, arm, run_id)
        for task_id in task_ids
        for arm in FOUR_ARM_CONDITIONS
        for run_id in range(runs)
    ]
    random.Random(runner.seed).shuffle(jobs)
    for task_id, arm, run_id in jobs:
        key = stable_run_key(task_id, arm, run_id)
        if key in completed:
            continue
        cell = runner.build_context_cell(task_id, arm, run_id)
        if cell.validation_errors:
            raise ValueError(f"Invalid context for {key}: {cell.validation_errors}")
        prompt = f"{cell.prompt_context}\n\n## Task\n{v4.TASK_PROMPTS[task_id]}"
        repeated_manifest_sha256 = [cell.manifest["manifest_sha256"]]
        for _ in range(2):
            repeated = runner.build_context_cell(task_id, arm, run_id)
            repeated_manifest_sha256.append(
                repeated.manifest["manifest_sha256"]
            )
        agent_retries = 0

        def invoke_isolated() -> dict[str, Any]:
            run_cwd = tempfile.mkdtemp(prefix="csp_v6_isolated_")
            try:
                return v4.invoke_claude_code(
                    prompt=prompt,
                    system_prompt=v5.DOMAIN_SYSTEM_PROMPT,
                    max_turns=AGENT_MAX_TURNS,
                    timeout=AGENT_TIMEOUT_SECONDS,
                    cwd=run_cwd,
                )
            finally:
                shutil.rmtree(run_cwd, ignore_errors=True)

        def agent_call_failed(result: Mapping[str, Any]) -> bool:
            response_text = str(result.get("result", ""))
            return bool(
                result.get("is_error")
                or v4.is_error_response(response_text)
            )

        agent_result = invoke_isolated()
        while agent_call_failed(agent_result):
            failed_generation_attempts.append(
                {
                    "run_key": key,
                    "attempt": agent_retries + 1,
                    "attempted_at": _utc_now(),
                    "model_returned": str(
                        agent_result.get("model", "unknown")
                    ),
                    "input_tokens": int(
                        agent_result.get("input_tokens", 0)
                    ),
                    "output_tokens": int(
                        agent_result.get("output_tokens", 0)
                    ),
                    "duration_ms": int(
                        agent_result.get("duration_ms", 0)
                    ),
                    "cost_usd": float(
                        agent_result.get("total_cost_usd", 0.0)
                    ),
                    "result_sha256": sha256_text(
                        str(agent_result.get("result", ""))
                    ),
                    "transport_error_flag": bool(
                        agent_result.get("is_error")
                    ),
                    "content_error_sentinel": v4.is_error_response(
                        str(agent_result.get("result", ""))
                    ),
                }
            )
            _atomic_json_write(
                output_path,
                runner.generation_checkpoint(
                    results,
                    task_ids,
                    runs,
                    failed_generation_attempts,
                ),
            )
            zero_input_failure = (
                int(agent_result.get("input_tokens", 0)) == 0
            )
            if (
                not zero_input_failure
                or agent_retries >= AGENT_MAX_RETRIES
            ):
                raise RuntimeError(
                    "Generation aborted after failed agent call "
                    f"for {key}; no later paid job was started"
                )
            agent_retries += 1
            time.sleep(AGENT_RETRY_DELAY_SECONDS)
            agent_result = invoke_isolated()
        response = str(agent_result.get("result", ""))
        domain_criteria = runner._get_judge_criteria(
            v4.TASK_NODES[task_id][0]
        )
        row = {
            "run_key": key,
            "task_id": task_id,
            "graph_node": v4.TASK_NODES[task_id][0],
            "judge_domain_criteria": domain_criteria,
            "judge_domain_criteria_sha256": sha256_text(
                domain_criteria
            ),
            "arm": arm,
            "run_id": run_id,
            "arm_definition": ARM_DEFINITIONS[arm],
            "agent_payload_sha256": sha256_text(prompt),
            "prompt_sha256": sha256_text(
                _complete_transmitted_agent_prompt(prompt)
            ),
            "response": response,
            "response_sha256": sha256_text(response),
            "skills_loaded": [
                candidate["skill_name"]
                for candidate in cell.manifest["candidates"]
                if candidate["status"] in ADMITTED_STATUSES
            ],
            "skills_tokens": int(cell.context_result.skill_tokens),
            "budget_used": int(cell.context_result.budget_used),
            "manifest_sha256": cell.manifest["manifest_sha256"],
            "manifest": cell.manifest,
            "repeated_manifest_sha256": repeated_manifest_sha256,
            "agent_model_requested": runner.agent_model_requested,
            "agent_model_returned": str(agent_result.get("model", "unknown")),
            "agent_response_id": agent_result.get("session_id"),
            "agent_response_id_capture": (
                "available"
                if agent_result.get("session_id")
                else "not_exposed_by_frozen_v4_wrapper"
            ),
            "agent_input_tokens": int(agent_result.get("input_tokens", 0)),
            "agent_output_tokens": int(agent_result.get("output_tokens", 0)),
            "agent_finish_reason": agent_result.get("stop_reason"),
            "agent_finish_reason_capture": (
                "available"
                if agent_result.get("stop_reason")
                else "not_exposed_by_frozen_v4_wrapper"
            ),
            "agent_duration_ms": int(agent_result.get("duration_ms", 0)),
            "agent_num_turns": int(agent_result.get("num_turns", 0)),
            "agent_retries": agent_retries,
            "agent_cost_usd": float(agent_result.get("total_cost_usd", 0.0)),
            "is_error_response": bool(
                agent_result.get("is_error") or v4.is_error_response(response)
            ),
            "isolated_working_directory": True,
            "scalar_judgment": None,
            "quality_score": None,
            "created_at": _utc_now(),
        }
        results.append(row)
        completed.add(key)
        _atomic_json_write(
            output_path,
            runner.generation_checkpoint(
                results,
                task_ids,
                runs,
                failed_generation_attempts,
            ),
        )
    checkpoint = runner.generation_checkpoint(
        results,
        task_ids,
        runs,
        failed_generation_attempts,
    )
    errors = validate_v6_checkpoint(checkpoint)
    if errors:
        raise ValueError(f"Generation checkpoint invalid: {errors}")
    _atomic_json_write(output_path, checkpoint)
    return checkpoint


async def judge_checkpoint(
    runner: ApsGxpExperimentRunner,
    source_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    """Judge complete stored responses only; no pairwise path exists in v6."""
    if not runner.network_enabled:
        raise PermissionError("External judging is not enabled")
    source_checkpoint = json.loads(source_path.read_text(encoding="utf-8"))
    source_metadata = source_checkpoint.get("metadata", {})
    source_tasks = source_metadata.get("tasks", [])
    source_runs = int(source_metadata.get("runs", 0))
    source_errors = [
        *validate_resume_configuration(
            source_checkpoint, runner, source_tasks, source_runs
        ),
        *validate_v6_checkpoint(source_checkpoint),
    ]
    if source_errors:
        raise ValueError(f"Judge source checkpoint invalid: {source_errors}")

    checkpoint = source_checkpoint
    if output_path.exists() and output_path.resolve() != source_path.resolve():
        resumed = json.loads(output_path.read_text(encoding="utf-8"))
        resume_errors = [
            *validate_resume_configuration(
                resumed, runner, source_tasks, source_runs
            ),
            *validate_v6_checkpoint(resumed),
        ]
        source_by_key = {
            row["run_key"]: (
                row["response_sha256"],
                row["manifest_sha256"],
            )
            for row in source_checkpoint["results"]
        }
        resumed_by_key = {
            row["run_key"]: (
                row["response_sha256"],
                row["manifest_sha256"],
            )
            for row in resumed.get("results", [])
        }
        if resumed_by_key != source_by_key:
            resume_errors.append(
                "judge resume response/manifest panel differs from source"
            )
        for row in resumed.get("results", []):
            existing = row.get("scalar_judgment") or {}
            if not existing or existing.get("judge_parse_error") is not None:
                continue
            resume_errors.extend(
                validate_v6_checkpoint(
                    {"metadata": resumed["metadata"], "results": [row]},
                    require_judgments=True,
                    allow_partial=True,
                )
            )
        if resume_errors:
            raise ValueError(f"Judge resume checkpoint invalid: {resume_errors}")
        checkpoint = resumed

    for row in checkpoint.get("results", []):
        existing_judgment = row.get("scalar_judgment") or {}
        if existing_judgment and existing_judgment.get(
            "judge_parse_error"
        ) is None:
            continue
        if existing_judgment:
            row.setdefault("prior_scalar_judgment_attempts", []).append(
                copy.deepcopy(existing_judgment)
            )
        response_text = str(row["response"])
        prompt = build_complete_response_judge_prompt(
            str(row["task_id"]),
            response_text,
            str(row["judge_domain_criteria"]),
        )
        response = await runner.judge_client.chat.completions.create(
            model=runner.judge_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=JUDGE_MAX_TOKENS,
        )
        choice = response.choices[0]
        content = choice.message.content or ""
        reasoning_content = (
            getattr(choice.message, "reasoning_content", None) or ""
        )
        parsed = v5.parse_multidim_judgment(content)
        usage = getattr(response, "usage", None)
        system_fingerprint = getattr(
            response, "system_fingerprint", None
        )
        judgment = {
            "policy": SCALAR_POLICY,
            "truncated": False,
            "response_characters_judged": len(response_text),
            "response_bytes_judged": len(response_text.encode("utf-8")),
            "response_sha256": sha256_text(response_text),
            "rendered_prompt_characters": len(prompt),
            "rendered_prompt_bytes": len(prompt.encode("utf-8")),
            "rendered_prompt_sha256": sha256_text(prompt),
            "scores": parsed.scores,
            "reasoning": parsed.reasoning,
            "judge_model_requested": runner.judge_model,
            "judge_model_returned": getattr(response, "model", None),
            "judge_response_id": getattr(response, "id", None),
            "system_fingerprint": system_fingerprint,
            "system_fingerprint_capture": (
                "available"
                if system_fingerprint
                else "provider_returned_null"
            ),
            "judge_input_tokens": int(
                getattr(usage, "prompt_tokens", 0) or 0
            ),
            "judge_output_tokens": int(
                getattr(usage, "completion_tokens", 0) or 0
            ),
            "finish_reason": getattr(choice, "finish_reason", None),
            "judge_parse_error": parsed.parse_error,
            "raw_content_sha256": sha256_text(content),
            "reasoning_content_characters": len(reasoning_content),
            "reasoning_content_sha256": sha256_text(reasoning_content),
            "judged_at": _utc_now(),
        }
        row["scalar_judgment"] = judgment
        if parsed.scores:
            row["dim_completeness"] = parsed.scores["completeness"]
            row["dim_terminology"] = parsed.scores["terminology"]
            row["dim_structure"] = parsed.scores["structure"]
            row["quality_score"] = round(
                sum(parsed.scores.values()) / 3.0, 2
            )
        _atomic_json_write(output_path, checkpoint)
    checkpoint["metadata"]["judge_model_requested"] = runner.judge_model
    checkpoint["metadata"]["judged_at"] = _utc_now()
    errors = validate_v6_checkpoint(checkpoint, require_judgments=True)
    if errors:
        raise ValueError(f"Judged checkpoint invalid: {errors}")
    _atomic_json_write(output_path, checkpoint)
    return checkpoint


def validate_stage0_prerequisite(
    runner: ApsGxpExperimentRunner,
    report_path: Path = DEFAULT_STAGE0_JSON,
) -> list[str]:
    """Require a passing Stage-0 report tied to the exact current sources."""
    if not report_path.exists():
        return [f"Stage-0 report does not exist: {report_path}"]
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        return [f"Stage-0 report is unreadable: {error}"]
    errors: list[str] = []
    if report.get("network_calls") != 0:
        errors.append("Stage-0 report is not a no-network run")
    if (
        report.get("task_count") != 10
        or report.get("task_ids") != list(v4.QUICK_10_TASKS)
        or report.get("arms") != list(FOUR_ARM_CONDITIONS)
        or report.get("repeats") != 3
    ):
        errors.append("Stage-0 report does not cover the locked 10x4x3 panel")
    if report.get("source_hashes") != runner.source_hashes_v6():
        errors.append("Stage-0 source hashes do not match current v6 sources")
    gates = report.get("gates", {})
    if (
        report.get("all_gates_pass") is not True
        or not isinstance(gates, Mapping)
        or not gates
        or not all(
            isinstance(gate, Mapping) and gate.get("pass") is True
            for gate in gates.values()
        )
    ):
        errors.append("Stage-0 gates have not all passed")
    return errors


def validate_smoke_prerequisite(
    runner: ApsGxpExperimentRunner,
    checkpoint_path: Path | None,
) -> list[str]:
    """Require a fully judged, source-matched fixed smoke before formal work."""
    if checkpoint_path is None:
        return ["a validated smoke checkpoint path is required"]
    if not checkpoint_path.exists():
        return [f"smoke checkpoint does not exist: {checkpoint_path}"]
    try:
        checkpoint = json.loads(
            checkpoint_path.read_text(encoding="utf-8")
        )
    except (OSError, ValueError) as error:
        return [f"smoke checkpoint is unreadable: {error}"]
    metadata = checkpoint.get("metadata", {})
    if (
        metadata.get("tasks") != [SMOKE_TASK_ID]
        or metadata.get("arms") != list(FOUR_ARM_CONDITIONS)
        or metadata.get("runs") != 1
    ):
        return ["smoke checkpoint does not contain the fixed four-call panel"]
    return [
        *validate_resume_configuration(
            checkpoint, runner, [SMOKE_TASK_ID], runs=1
        ),
        *validate_v6_checkpoint(checkpoint, require_judgments=True),
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--stage0", action="store_true")
    mode.add_argument("--smoke-generate", action="store_true")
    mode.add_argument("--formal-generate", action="store_true")
    mode.add_argument("--judge-checkpoint", type=Path)
    parser.add_argument("--smoke-generation-approved", action="store_true")
    parser.add_argument("--smoke-judge-approved", action="store_true")
    parser.add_argument("--formal-generation-approved", action="store_true")
    parser.add_argument("--formal-judge-approved", action="store_true")
    parser.add_argument("--validated-smoke-checkpoint", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    if args.stage0:
        runner = ApsGxpExperimentRunner(seed=42, budget=8000)
        report = build_stage0_report(runner)
        json_path = args.output or DEFAULT_STAGE0_JSON
        _atomic_json_write(json_path, report)
        DEFAULT_STAGE0_MARKDOWN.parent.mkdir(parents=True, exist_ok=True)
        DEFAULT_STAGE0_MARKDOWN.write_text(
            render_stage0_markdown(report), encoding="utf-8"
        )
        print(f"Stage 0: {'PASS' if report['all_gates_pass'] else 'FAIL'}")
        print(f"JSON: {json_path}")
        print(f"Markdown: {DEFAULT_STAGE0_MARKDOWN}")
        if not report["all_gates_pass"]:
            raise SystemExit(1)
        return

    if args.smoke_generate or args.formal_generate:
        required_approval = (
            args.smoke_generation_approved
            if args.smoke_generate
            else args.formal_generation_approved
        )
        approval_name = (
            "--smoke-generation-approved"
            if args.smoke_generate
            else "--formal-generation-approved"
        )
        if not required_approval:
            raise SystemExit(
                f"Paid generation blocked: {approval_name} is required"
            )
        task_ids = (
            [SMOKE_TASK_ID]
            if args.smoke_generate
            else list(v4.QUICK_10_TASKS)
        )
        runs = 1 if args.smoke_generate else 3
        output = args.output or (
            DEFAULT_SMOKE_OUTPUT
            if args.smoke_generate
            else PROJECT_ROOT
            / "experiments"
            / "results"
            / "experiment_v6_aps_gxp_formal.json"
        )
        runner = ApsGxpExperimentRunner(
            seed=42, budget=8000, network_enabled=True
        )
        stage0_errors = validate_stage0_prerequisite(runner)
        if stage0_errors:
            raise SystemExit(f"Paid generation blocked: {stage0_errors}")
        if args.formal_generate:
            smoke_errors = validate_smoke_prerequisite(
                runner, args.validated_smoke_checkpoint
            )
            if smoke_errors:
                raise SystemExit(
                    f"Formal generation blocked: {smoke_errors}"
                )
        run_generation(runner, task_ids, runs, output)
        print(f"Generation checkpoint: {output}")
        return

    if args.output is None:
        raise SystemExit("--output is required for judged checkpoints")
    runner = ApsGxpExperimentRunner(
        seed=42, budget=8000, network_enabled=True
    )
    stage0_errors = validate_stage0_prerequisite(runner)
    if stage0_errors:
        raise SystemExit(f"External judging blocked: {stage0_errors}")
    judge_source = json.loads(
        args.judge_checkpoint.read_text(encoding="utf-8")
    )
    source_metadata = judge_source.get("metadata", {})
    is_smoke = (
        source_metadata.get("tasks") == [SMOKE_TASK_ID]
        and source_metadata.get("runs") == 1
    )
    is_formal = (
        source_metadata.get("tasks") == list(v4.QUICK_10_TASKS)
        and source_metadata.get("runs") == 3
    )
    if not is_smoke and not is_formal:
        raise SystemExit("External judging blocked: source panel is not fixed")
    required_judge_approval = (
        args.smoke_judge_approved if is_smoke else args.formal_judge_approved
    )
    approval_name = (
        "--smoke-judge-approved"
        if is_smoke
        else "--formal-judge-approved"
    )
    if not required_judge_approval:
        raise SystemExit(
            f"External judging blocked: {approval_name} is required"
        )
    if is_formal:
        smoke_errors = validate_smoke_prerequisite(
            runner, args.validated_smoke_checkpoint
        )
        if smoke_errors:
            raise SystemExit(f"Formal judging blocked: {smoke_errors}")
    asyncio.run(judge_checkpoint(runner, args.judge_checkpoint, args.output))
    print(f"Judged checkpoint: {args.output}")


if __name__ == "__main__":
    main()
