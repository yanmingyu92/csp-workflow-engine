#!/usr/bin/env python3
"""Corrected six-arm experiment for the JMIR AI major revision.

This v5 runner preserves the v4 runner as a historical artifact while fixing
the APS candidate/band defects and separating domain-prompt priming from skill
corpus access. Results are checkpointed after every external call.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import os
import random
import re
import shutil
import sys
import tempfile
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from experiments import run_experiment_v4_claude as v4  # noqa: E402


DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "experiments" / "results"

ENVIRONMENT_KEYS = {
    "GLM_API_KEY",
    "GLM_BASE_URL",
    "DEEPSEEK_API_KEY",
    "DEEPSEEK_BASE_URL",
    "AGENT_MODEL",
    "DEEPSEEK_MODEL",
}

SIX_ARM_CONDITIONS: Tuple[str, ...] = (
    "agent_only",
    "agent_domain_prompt_only",
    "agent_framework",
    "agent_framework_distill",
    "agent_skills_flat",
    "agent_skills_random",
)

DOMAIN_SYSTEM_PROMPT = """You are an AI programming assistant with expertise in FDA clinical trial submissions and CDISC standards.
Apply SDTM IG v3.4 and ADaM IG v1.3 terminology accurately. Produce precise, actionable outputs with correct variable names, controlled terminology, ISO 8601 dates, and complete derivation logic when relevant.
If domain context is supplied in the task, use it as evidence; do not assume that unsupplied framework content exists."""

ARM_DEFINITIONS = {
    "agent_only": "Bare task; no CDISC system prompt; no skill corpus.",
    "agent_domain_prompt_only": "CDISC system prompt; no skill corpus.",
    "agent_framework": "CDISC system prompt plus corrected APS context.",
    "agent_framework_distill": (
        "CDISC system prompt plus corrected APS context and distilled principles."
    ),
    "agent_skills_flat": (
        "CDISC system prompt plus budget-capped corpus loading with uniform "
        "alphabetical priority."
    ),
    "agent_skills_random": (
        "CDISC system prompt plus five reproducibly sampled corpus skills."
    ),
}

RANDOM_K_SKILLS = 5
PAIRWISE_CONTRASTS: Tuple[Tuple[str, str], ...] = (
    ("agent_framework", "agent_domain_prompt_only"),
    ("agent_framework", "agent_skills_flat"),
    ("agent_framework", "agent_skills_random"),
)


def load_environment_file(
    path: Path = PROJECT_ROOT / ".env",
    environment: Optional[Any] = None,
) -> List[str]:
    """Load only experiment allowlisted keys without overwriting the process.

    This intentionally avoids a new python-dotenv dependency and never logs
    values. Existing process configuration always wins over the local file.
    """
    target = os.environ if environment is None else environment
    loaded: List[str] = []
    path = Path(path)
    if not path.exists():
        return loaded
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key not in ENVIRONMENT_KEYS or key in target:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        target[key] = value
        loaded.append(key)
    return loaded


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_run_key(task_id: str, condition: str, run_id: int) -> str:
    return f"{task_id}::{condition}::{run_id}"


def stable_pairwise_key(
    task_id: str,
    run_id: int,
    condition_a: str,
    condition_b: str,
) -> str:
    return f"{task_id}::{run_id}::{condition_a}::{condition_b}"


@dataclass(frozen=True)
class ConditionPayload:
    prompt: str
    system_prompt: Optional[str]
    skills: Tuple[str, ...]
    context_result: Optional[Any]
    arm_definition: str


@dataclass(frozen=True)
class JudgmentParse:
    scores: Optional[Dict[str, float]]
    reasoning: str
    parse_error: Optional[str]


def parse_multidim_judgment(content: str) -> JudgmentParse:
    """Parse a complete three-score judgment; partial output remains missing."""
    raw = (content or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.I)
    match = re.search(r"\{[\s\S]*\}", raw)
    candidate = match.group(0) if match else raw
    try:
        parsed = json.loads(candidate)
    except (TypeError, ValueError) as error:
        return JudgmentParse(None, "", f"invalid JSON: {error}")

    required = ("completeness", "terminology", "structure")
    try:
        raw_scores = {name: parsed[name] for name in required}
        if any(
            isinstance(value, bool) or not isinstance(value, (int, float))
            for value in raw_scores.values()
        ):
            raise TypeError("scores must be finite JSON numbers, not booleans or strings")
        scores = {name: float(value) for name, value in raw_scores.items()}
    except (KeyError, TypeError, ValueError) as error:
        return JudgmentParse(None, str(parsed.get("reasoning", "")), str(error))
    if any(not math.isfinite(value) for value in scores.values()):
        return JudgmentParse(None, str(parsed.get("reasoning", "")), "score is not finite")
    if any(value < 1 or value > 5 for value in scores.values()):
        return JudgmentParse(None, str(parsed.get("reasoning", "")), "score outside 1-5")
    return JudgmentParse(scores, str(parsed.get("reasoning", ""))[:500], None)


@dataclass
class CorrectedExperimentResult:
    run_key: str
    experiment_id: str
    timestamp: str
    task_id: str
    graph_node: str
    layer: int
    condition: str
    run_id: int
    arm_definition: str
    prompt_sha256: str
    prompt_preview: str
    system_prompt_used: bool
    system_prompt_sha256: Optional[str]
    response: str
    skills_loaded: List[str]
    skills_count: int
    skills_tokens: int
    context_strategy: str
    context_audit: Dict[str, Any]
    principles_used: List[str]
    principles_count: int
    tokens_in: int
    tokens_out: int
    dim_completeness: Optional[float]
    dim_terminology: Optional[float]
    dim_structure: Optional[float]
    dim_reasoning: str
    quality_score: Optional[float]
    auto_metrics: Dict[str, Any]
    cost_usd: float
    agent_cost_usd: float
    judge_cost_usd: float
    agent_model_requested: str
    agent_model_returned: str
    agent_duration_ms: int
    agent_num_turns: int
    agent_retries: int
    is_error_response: bool
    judge_model_requested: str
    judge_model_returned: Optional[str]
    judge_response_id: Optional[str]
    judge_input_tokens: int
    judge_output_tokens: int
    judge_parse_error: Optional[str]
    isolated_working_directory: bool


class CorrectedExperimentRunner(v4.ExperimentRunner):
    """v5 runner with corrected condition construction and provenance."""

    def __init__(self, dry_run: bool = False, seed: int = 42, budget: int = 8000):
        load_environment_file()
        super().__init__(dry_run=dry_run, seed=seed, budget=budget)
        self.results: List[CorrectedExperimentResult] = []
        self.pairwise_results: List[Dict[str, Any]] = []
        self.completed_run_keys = set()
        self.completed_pairwise_keys = set()
        self.domain_system_prompt = DOMAIN_SYSTEM_PROMPT
        self.run_config: Dict[str, Any] = {
            "tasks": list(v4.QUICK_10_TASKS),
            "conditions": list(SIX_ARM_CONDITIONS),
            "runs": 0,
        }
        self._loaded_metadata: Dict[str, Any] = {}

    def source_hashes(self) -> Dict[str, str]:
        task_panel = {
            task: {
                "prompt": v4.TASK_PROMPTS[task],
                "node": v4.TASK_NODES[task],
            }
            for task in v4.QUICK_10_TASKS
        }
        return {
            "runner": _sha256_file(Path(__file__)),
            "scheduler": _sha256_file(PROJECT_ROOT / "scripts" / "context-loader.py"),
            "graph": _sha256_file(v4.GRAPH_PATH),
            "system_prompt": _sha256_text(DOMAIN_SYSTEM_PROMPT),
            "task_panel": _sha256_text(
                json.dumps(task_panel, sort_keys=True, ensure_ascii=False)
            ),
            "judge_prompt": _sha256_text(
                v4.MULTI_DIM_JUDGE_PROMPT + "\n" + v4.PAIRWISE_JUDGE_PROMPT
            ),
        }

    def _build_routed_context(
        self, task_id: str, node_id: str, with_principles: bool
    ) -> Any:
        return self.context_builder.build_context(
            node_id=node_id,
            router_result=self._get_router_result(node_id),
            all_skills=None,
            regulatory_refs=[],
            task_description=v4.TASK_PROMPTS[task_id],
            with_principles=with_principles,
        )

    def build_condition_payload(
        self, task_id: str, condition: str, run_id: int
    ) -> ConditionPayload:
        if condition not in SIX_ARM_CONDITIONS:
            raise ValueError(f"Unknown v5 condition: {condition}")
        if task_id not in v4.TASK_PROMPTS:
            raise ValueError(f"Unknown task: {task_id}")

        base_prompt = v4.TASK_PROMPTS[task_id]
        node_id, _ = v4.TASK_NODES[task_id]
        if condition == "agent_only":
            return ConditionPayload(
                base_prompt, None, (), None, ARM_DEFINITIONS[condition]
            )
        if condition == "agent_domain_prompt_only":
            return ConditionPayload(
                base_prompt,
                DOMAIN_SYSTEM_PROMPT,
                (),
                None,
                ARM_DEFINITIONS[condition],
            )

        if condition in ("agent_framework", "agent_framework_distill"):
            context = self._build_routed_context(
                task_id,
                node_id,
                with_principles=condition == "agent_framework_distill",
            )
        elif condition == "agent_skills_flat":
            context = self._build_uniform_context(
                node_id, self._all_corpus_skills(), "FLAT"
            )
        else:
            corpus = self._all_corpus_skills()
            rng = random.Random(f"{self.seed}:{task_id}:{run_id}")
            sampled = sorted(rng.sample(corpus, min(RANDOM_K_SKILLS, len(corpus))))
            context = self._build_uniform_context(node_id, sampled, "RANDOM")

        context_text = self.cl_module.OutputFormatter.format_context(
            context, include_content=True
        )
        skills = tuple(
            skill.name
            for skill in context.skills
            if skill.status in ("loaded", "truncated")
        )
        return ConditionPayload(
            prompt=f"{context_text}\n\n## Task\n{base_prompt}",
            system_prompt=DOMAIN_SYSTEM_PROMPT,
            skills=skills,
            context_result=context,
            arm_definition=ARM_DEFINITIONS[condition],
        )

    @staticmethod
    def _context_audit(context: Optional[Any]) -> Dict[str, Any]:
        if context is None:
            return {
                "budget": 0,
                "budget_used": 0,
                "band_summary": {},
                "current_floor_tokens": 0,
                "current_tokens_used": 0,
                "skills": [],
            }
        return {
            "budget": context.budget,
            "budget_used": context.budget_used,
            "band_summary": getattr(context, "band_summary", {}),
            "current_floor_tokens": getattr(context, "current_floor_tokens", 0),
            "current_tokens_used": getattr(context, "current_tokens_used", 0),
            "skills": [
                {
                    "name": skill.name,
                    "band": skill.band.name,
                    "hub_degree": getattr(skill, "hub_degree", 0),
                    "priority_score": skill.priority_score,
                    "status": skill.status,
                    "tokens": skill.token_estimate,
                }
                for skill in context.skills
            ],
        }

    @staticmethod
    def _usage_tokens(response: Any) -> Tuple[int, int]:
        usage = getattr(response, "usage", None)
        if usage is None:
            return 0, 0
        input_tokens = getattr(usage, "prompt_tokens", None)
        if input_tokens is None:
            input_tokens = getattr(usage, "input_tokens", 0)
        output_tokens = getattr(usage, "completion_tokens", None)
        if output_tokens is None:
            output_tokens = getattr(usage, "output_tokens", 0)
        return int(input_tokens or 0), int(output_tokens or 0)

    async def run_task(
        self, task_id: str, condition: str, run_id: int = 0
    ) -> CorrectedExperimentResult:
        key = stable_run_key(task_id, condition, run_id)
        if key in self.completed_run_keys:
            raise ValueError(f"Duplicate run key: {key}")

        node_id, layer = v4.TASK_NODES[task_id]
        base_prompt = v4.TASK_PROMPTS[task_id]
        payload = self.build_condition_payload(task_id, condition, run_id)
        context = payload.context_result
        context_audit = self._context_audit(context)
        skills_tokens = int(getattr(context, "skill_tokens", 0))
        principles_used = list(
            getattr(context, "principles_retrieved_ids", []) if context else []
        )
        principles_count = len(getattr(context, "principles", []) if context else [])
        context_strategy = getattr(context, "budget_strategy", "none")

        requested_agent_model = os.getenv("AGENT_MODEL", "glm-5")
        requested_judge_model = self.judge_model
        retries = 0
        isolated = True
        judge_model_returned = None
        judge_response_id = None
        judge_input_tokens = 0
        judge_output_tokens = 0
        judge_parse_error = None

        if self.dry_run:
            response = "[DRY RUN]"
            agent_result = {
                "input_tokens": 100,
                "output_tokens": 200,
                "total_cost_usd": 0.0,
                "model": "dry-run",
                "duration_ms": 0,
                "num_turns": 0,
                "is_error": False,
            }
            scores = {"completeness": 4.0, "terminology": 4.0, "structure": 4.0}
            reasoning = "Dry run"
            judge_cost = 0.0
        else:
            run_cwd = tempfile.mkdtemp(prefix="csp_v5_isolated_")
            try:
                agent_result = v4.invoke_claude_code(
                    prompt=payload.prompt,
                    system_prompt=payload.system_prompt,
                    max_turns=6,
                    timeout=420,
                    cwd=run_cwd,
                )
                if agent_result["is_error"] and agent_result["input_tokens"] == 0:
                    retries = 1
                    time.sleep(5)
                    agent_result = v4.invoke_claude_code(
                        prompt=payload.prompt,
                        system_prompt=payload.system_prompt,
                        max_turns=6,
                        timeout=420,
                        cwd=run_cwd,
                    )
            finally:
                shutil.rmtree(run_cwd, ignore_errors=True)

            response = agent_result["result"]
            agent_failed = agent_result["is_error"] or v4.is_error_response(response)
            if agent_failed:
                scores = {
                    "completeness": 1.0,
                    "terminology": 1.0,
                    "structure": 1.0,
                }
                reasoning = f"Agent error: {response[:200]}"
                judge_cost = 0.0
            else:
                try:
                    judge_content = v4.MULTI_DIM_JUDGE_PROMPT.format(
                        task_description=base_prompt,
                        response=response,
                        domain_criteria=self._get_judge_criteria(node_id),
                    )
                    judge_response = await self.judge_client.chat.completions.create(
                        model=requested_judge_model,
                        messages=[{"role": "user", "content": judge_content}],
                        temperature=0.0,
                        max_tokens=300,
                    )
                    judge_model_returned = getattr(judge_response, "model", None)
                    judge_response_id = getattr(judge_response, "id", None)
                    judge_input_tokens, judge_output_tokens = self._usage_tokens(
                        judge_response
                    )
                    parsed = parse_multidim_judgment(
                        judge_response.choices[0].message.content
                    )
                    scores = parsed.scores
                    reasoning = parsed.reasoning
                    judge_parse_error = parsed.parse_error
                    judge_cost = self._judge_cost(
                        judge_input_tokens, judge_output_tokens
                    )
                except Exception as error:
                    scores = None
                    reasoning = ""
                    judge_parse_error = f"judge request failed: {error}"
                    judge_cost = 0.0

        agent_failed = bool(
            agent_result.get("is_error") or v4.is_error_response(response)
        )
        if scores is None:
            dim_completeness = None
            dim_terminology = None
            dim_structure = None
            quality_score = None
        else:
            dim_completeness = scores["completeness"]
            dim_terminology = scores["terminology"]
            dim_structure = scores["structure"]
            quality_score = round(
                (dim_completeness + dim_terminology + dim_structure) / 3.0, 2
            )

        agent_cost = float(agent_result.get("total_cost_usd", 0.0))
        total_cost = agent_cost + judge_cost
        self.total_agent_cost += agent_cost
        self.total_judge_cost += judge_cost
        self.total_cost += total_cost

        return CorrectedExperimentResult(
            run_key=key,
            experiment_id=(
                f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{task_id}_"
                f"{condition}_{run_id}"
            ),
            timestamp=datetime.now().isoformat(),
            task_id=task_id,
            graph_node=node_id,
            layer=layer,
            condition=condition,
            run_id=run_id,
            arm_definition=payload.arm_definition,
            prompt_sha256=_sha256_text(payload.prompt),
            prompt_preview=payload.prompt[:500],
            system_prompt_used=payload.system_prompt is not None,
            system_prompt_sha256=(
                _sha256_text(payload.system_prompt) if payload.system_prompt else None
            ),
            response=response,
            skills_loaded=list(payload.skills),
            skills_count=len(payload.skills),
            skills_tokens=skills_tokens,
            context_strategy=context_strategy,
            context_audit=context_audit,
            principles_used=principles_used,
            principles_count=principles_count,
            tokens_in=int(agent_result.get("input_tokens", 0)),
            tokens_out=int(agent_result.get("output_tokens", 0)),
            dim_completeness=dim_completeness,
            dim_terminology=dim_terminology,
            dim_structure=dim_structure,
            dim_reasoning=reasoning,
            quality_score=quality_score,
            auto_metrics=v4.compute_auto_metrics(response),
            cost_usd=total_cost,
            agent_cost_usd=agent_cost,
            judge_cost_usd=judge_cost,
            agent_model_requested=requested_agent_model,
            agent_model_returned=str(agent_result.get("model", "unknown")),
            agent_duration_ms=int(agent_result.get("duration_ms", 0)),
            agent_num_turns=int(agent_result.get("num_turns", 0)),
            agent_retries=retries,
            is_error_response=agent_failed,
            judge_model_requested=requested_judge_model,
            judge_model_returned=judge_model_returned,
            judge_response_id=judge_response_id,
            judge_input_tokens=judge_input_tokens,
            judge_output_tokens=judge_output_tokens,
            judge_parse_error=judge_parse_error,
            isolated_working_directory=isolated,
        )

    async def run_pairwise_replicate(
        self,
        task_id: str,
        run_id: int,
        condition_a: str,
        condition_b: str,
    ) -> Dict[str, Any]:
        pair_key = stable_pairwise_key(
            task_id, run_id, condition_a, condition_b
        )
        result_a = next(
            (
                result
                for result in self.results
                if result.run_key == stable_run_key(task_id, condition_a, run_id)
            ),
            None,
        )
        result_b = next(
            (
                result
                for result in self.results
                if result.run_key == stable_run_key(task_id, condition_b, run_id)
            ),
            None,
        )
        if result_a is None or result_b is None:
            raise ValueError(f"Missing results for pairwise key {pair_key}")

        if result_a.is_error_response or result_b.is_error_response:
            if result_a.is_error_response and result_b.is_error_response:
                winner = "tie"
            elif result_a.is_error_response:
                winner = condition_b
            else:
                winner = condition_a
            return {
                "pairwise_key": pair_key,
                "task_id": task_id,
                "run_id": run_id,
                "condition_a": condition_a,
                "condition_b": condition_b,
                "winner": winner,
                "raw_winner": "automatic",
                "reason": "Automatic result because at least one agent call failed",
                "confidence": "high",
                "flipped": False,
                "judge_model_requested": self.judge_model,
                "judge_model_returned": None,
                "judge_response_id": None,
                "judge_input_tokens": 0,
                "judge_output_tokens": 0,
                "judge_parse_error": None,
            }

        rng = random.Random(
            f"{self.seed}:{task_id}:{run_id}:{condition_a}:{condition_b}"
        )
        flipped = rng.random() < 0.5
        if flipped:
            response_a, response_b = result_b.response, result_a.response
        else:
            response_a, response_b = result_a.response, result_b.response

        judge_content = v4.PAIRWISE_JUDGE_PROMPT.format(
            task_description=v4.TASK_PROMPTS[task_id],
            domain_criteria=self._get_judge_criteria(result_a.graph_node),
            response_a=response_a,
            response_b=response_b,
        )
        try:
            response = await self.judge_client.chat.completions.create(
                model=self.judge_model,
                messages=[{"role": "user", "content": judge_content}],
                temperature=0.0,
                max_tokens=200,
            )
            content = response.choices[0].message.content or ""
            winner_match = re.search(
                r'"winner"\s*:\s*"(A|B|tie)"', content, re.I
            )
            reason_match = re.search(r'"reason"\s*:\s*"([^"]+)"', content)
            confidence_match = re.search(
                r'"confidence"\s*:\s*"(high|medium|low)"', content, re.I
            )
            raw_winner = winner_match.group(1) if winner_match else "parse_error"
            parse_error = None if winner_match else "winner not parseable"
            if raw_winner.lower() == "tie":
                winner = "tie"
            elif raw_winner == "parse_error":
                winner = "error"
            elif flipped:
                winner = condition_a if raw_winner.upper() == "B" else condition_b
            else:
                winner = condition_a if raw_winner.upper() == "A" else condition_b
            input_tokens, output_tokens = self._usage_tokens(response)
            judge_cost = self._judge_cost(input_tokens, output_tokens)
            self.total_judge_cost += judge_cost
            self.total_cost += judge_cost
            return {
                "pairwise_key": pair_key,
                "task_id": task_id,
                "run_id": run_id,
                "condition_a": condition_a,
                "condition_b": condition_b,
                "winner": winner,
                "raw_winner": raw_winner,
                "reason": (
                    reason_match.group(1)[:300]
                    if reason_match
                    else content[:300]
                ),
                "confidence": (
                    confidence_match.group(1).lower()
                    if confidence_match
                    else "low"
                ),
                "flipped": flipped,
                "judge_model_requested": self.judge_model,
                "judge_model_returned": getattr(response, "model", None),
                "judge_response_id": getattr(response, "id", None),
                "judge_input_tokens": input_tokens,
                "judge_output_tokens": output_tokens,
                "judge_parse_error": parse_error,
            }
        except Exception as error:
            return {
                "pairwise_key": pair_key,
                "task_id": task_id,
                "run_id": run_id,
                "condition_a": condition_a,
                "condition_b": condition_b,
                "winner": "error",
                "raw_winner": "error",
                "reason": str(error)[:300],
                "confidence": "low",
                "flipped": flipped,
                "judge_model_requested": self.judge_model,
                "judge_model_returned": None,
                "judge_response_id": None,
                "judge_input_tokens": 0,
                "judge_output_tokens": 0,
                "judge_parse_error": f"judge request failed: {error}",
            }

    def _checkpoint_payload(self) -> Dict[str, Any]:
        agent_models = sorted(
            {
                result.agent_model_returned
                for result in self.results
                if result.agent_model_returned != "dry-run"
            }
        )
        judge_models = sorted(
            {
                model
                for model in [
                    *(result.judge_model_returned for result in self.results),
                    *(
                        result.get("judge_model_returned")
                        for result in self.pairwise_results
                    ),
                ]
                if model
            }
        )
        return {
            "metadata": {
                "version": "v5-corrected-six-arm",
                "timestamp": datetime.now().isoformat(),
                "dry_run": self.dry_run,
                "seed": self.seed,
                "budget": self.budget,
                "agent": "Claude Code (claude -p)",
                "agent_model_requested": os.getenv("AGENT_MODEL", "glm-5"),
                "agent_models_returned": agent_models,
                "judge_model_requested": self.judge_model,
                "judge_models_returned": judge_models,
                "conditions": list(self.run_config.get("conditions", [])),
                "tasks": list(self.run_config.get("tasks", [])),
                "runs": int(self.run_config.get("runs", 0)),
                "arm_definitions": ARM_DEFINITIONS,
                "isolated_working_directory_all_arms": True,
                "scheduler_version": "APS-v5-graph-proximity-hub",
                "source_hashes": self.source_hashes(),
                "argv": sys.argv,
                "total_cost": round(self.total_cost, 6),
                "agent_cost": round(self.total_agent_cost, 6),
                "judge_cost": round(self.total_judge_cost, 6),
            },
            "results": [asdict(result) for result in self.results],
            "pairwise_results": self.pairwise_results,
        }

    def save_checkpoint(self, path: Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = path.with_suffix(path.suffix + ".tmp")
        temporary_path.write_text(
            json.dumps(self._checkpoint_payload(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        temporary_path.replace(path)

    def load_checkpoint(self, path: Path) -> None:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        metadata = data.get("metadata", {})
        if metadata.get("version") != "v5-corrected-six-arm":
            raise ValueError("Not a v5 corrected-experiment checkpoint")
        if int(metadata.get("seed", self.seed)) != self.seed:
            raise ValueError("Resume seed does not match checkpoint")
        if int(metadata.get("budget", self.budget)) != self.budget:
            raise ValueError("Resume budget does not match checkpoint")
        self._loaded_metadata = metadata
        self.run_config = {
            "tasks": metadata.get("tasks", []),
            "conditions": metadata.get("conditions", []),
            "runs": metadata.get("runs", 0),
        }
        self.results = [
            CorrectedExperimentResult(**row) for row in data.get("results", [])
        ]
        self.pairwise_results = list(data.get("pairwise_results", []))
        self.completed_run_keys = {result.run_key for result in self.results}
        self.completed_pairwise_keys = {
            row["pairwise_key"] for row in self.pairwise_results
        }
        self.total_cost = float(metadata.get("total_cost", 0.0))
        self.total_agent_cost = float(metadata.get("agent_cost", 0.0))
        self.total_judge_cost = float(metadata.get("judge_cost", 0.0))


def validate_checkpoint(data: Mapping[str, Any]) -> List[str]:
    """Return invariant violations; an empty list means the checkpoint is valid."""
    errors: List[str] = []
    metadata = data.get("metadata", {})
    results = data.get("results", [])
    pairwise = data.get("pairwise_results", [])
    tasks = metadata.get("tasks", [])
    conditions = metadata.get("conditions", [])
    runs = int(metadata.get("runs", 0))
    expected_agents = len(tasks) * len(conditions) * runs

    run_keys = [row.get("run_key") for row in results]
    if len(results) != expected_agents:
        errors.append(f"agent cardinality {len(results)} != {expected_agents}")
    if len(run_keys) != len(set(run_keys)):
        errors.append("duplicate agent run keys")
    expected_keys = {
        stable_run_key(task_id, condition, run_id)
        for run_id in range(runs)
        for task_id in tasks
        for condition in conditions
    }
    if set(run_keys) != expected_keys:
        errors.append("agent run-key set does not match the configured panel")
    if any(not row.get("isolated_working_directory") for row in results):
        errors.append("at least one arm was not recorded as isolated")
    if any(row.get("system_prompt_used") for row in results if row.get("condition") == "agent_only"):
        errors.append("agent_only unexpectedly used the domain system prompt")
    if any(
        not row.get("system_prompt_used")
        for row in results
        if row.get("condition") != "agent_only"
    ):
        errors.append("at least one non-bare arm omitted the domain system prompt")
    if any(
        row.get("context_audit", {}).get("budget_used", 0)
        > row.get("context_audit", {}).get("budget", 0)
        for row in results
        if row.get("condition") not in ("agent_only", "agent_domain_prompt_only")
    ):
        errors.append("at least one context exceeded its token budget")
    routed_rows = [
        row
        for row in results
        if row.get("condition") in ("agent_framework", "agent_framework_distill")
    ]
    if any(
        not any(
            skill.get("status") in ("loaded", "truncated")
            and skill.get("band") != "GLOBAL"
            for skill in row.get("context_audit", {}).get("skills", [])
        )
        for row in routed_rows
    ):
        errors.append("at least one routed context loaded only GLOBAL skills")
    if any(
        row.get("context_audit", {}).get("current_tokens_used", 0)
        < row.get("context_audit", {}).get("current_floor_tokens", 0)
        for row in routed_rows
    ):
        errors.append("at least one routed context failed its CURRENT-band floor")
    if any(
        skill.get("name", "").startswith("/")
        for row in results
        for skill in row.get("context_audit", {}).get("skills", [])
    ):
        errors.append("at least one context retained a non-normalized skill identifier")
    source_hashes = metadata.get("source_hashes", {})
    if len(source_hashes) < 6 or any(
        len(value) != 64 for value in source_hashes.values()
    ):
        errors.append("source hashes missing")

    if not metadata.get("dry_run"):
        if any(row.get("judge_parse_error") for row in results):
            errors.append("at least one multi-dimensional judgment is missing or unparseable")
        if any(row.get("judge_parse_error") for row in pairwise):
            errors.append("at least one pairwise judgment is missing or unparseable")
        if not metadata.get("agent_models_returned"):
            errors.append("returned agent model identifier missing")
        if not metadata.get("judge_models_returned"):
            errors.append("returned judge model identifier missing")

    selected_pairwise = sum(
        condition_a in conditions and condition_b in conditions
        for condition_a, condition_b in PAIRWISE_CONTRASTS
    )
    expected_pairwise = (
        0 if metadata.get("dry_run") else len(tasks) * runs * selected_pairwise
    )
    pairwise_keys = [row.get("pairwise_key") for row in pairwise]
    if len(pairwise) != expected_pairwise:
        errors.append(f"pairwise cardinality {len(pairwise)} != {expected_pairwise}")
    if len(pairwise_keys) != len(set(pairwise_keys)):
        errors.append("duplicate pairwise keys")
    return errors


def _default_output() -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return DEFAULT_OUTPUT_DIR / f"experiment_v5_corrected_{timestamp}.json"


async def _run(args: argparse.Namespace) -> Path:
    if args.resume:
        output_path = args.resume
    else:
        output_path = args.output or _default_output()

    conditions = (
        tuple(item.strip() for item in args.condition_list.split(",") if item.strip())
        if args.condition_list
        else SIX_ARM_CONDITIONS
    )
    unknown = sorted(set(conditions) - set(SIX_ARM_CONDITIONS))
    if unknown:
        raise ValueError(f"Unknown conditions: {unknown}")
    tasks = tuple(v4.QUICK_10_TASKS[: args.tasks])

    runner = CorrectedExperimentRunner(
        dry_run=args.dry_run, seed=args.seed, budget=args.budget
    )
    if args.resume:
        runner.load_checkpoint(args.resume)
        expected_config = {
            "tasks": list(tasks),
            "conditions": list(conditions),
            "runs": args.runs,
        }
        if runner.run_config != expected_config:
            raise ValueError(
                f"Resume configuration mismatch: {runner.run_config} != {expected_config}"
            )
    else:
        runner.run_config = {
            "tasks": list(tasks),
            "conditions": list(conditions),
            "runs": args.runs,
        }

    triples = [
        (task_id, condition, run_id)
        for run_id in range(args.runs)
        for task_id in tasks
        for condition in conditions
    ]
    random.Random(args.seed).shuffle(triples)
    print(
        f"v5 corrected experiment: {len(tasks)} tasks × {len(conditions)} arms × "
        f"{args.runs} runs = {len(triples)} agent calls"
    )
    print(f"Checkpoint: {output_path}")

    for index, (task_id, condition, run_id) in enumerate(triples, 1):
        key = stable_run_key(task_id, condition, run_id)
        if key in runner.completed_run_keys:
            print(f"[{index}/{len(triples)}] skip {key}")
            continue
        print(f"[{index}/{len(triples)}] {key}")
        result = await runner.run_task(task_id, condition, run_id)
        runner.results.append(result)
        runner.completed_run_keys.add(key)
        runner.save_checkpoint(output_path)
        print(
            f"  score={result.quality_score} skills={result.skills_count} "
            f"tokens={result.skills_tokens} model={result.agent_model_returned} "
            f"error={result.is_error_response}"
        )

    if not args.dry_run and not args.skip_pairwise:
        pairs = [
            (task_id, run_id, condition_a, condition_b)
            for run_id in range(args.runs)
            for task_id in tasks
            for condition_a, condition_b in PAIRWISE_CONTRASTS
            if condition_a in conditions and condition_b in conditions
        ]
        for index, (task_id, run_id, condition_a, condition_b) in enumerate(
            pairs, 1
        ):
            key = stable_pairwise_key(
                task_id, run_id, condition_a, condition_b
            )
            if key in runner.completed_pairwise_keys:
                print(f"[pair {index}/{len(pairs)}] skip {key}")
                continue
            print(f"[pair {index}/{len(pairs)}] {key}")
            result = await runner.run_pairwise_replicate(
                task_id, run_id, condition_a, condition_b
            )
            runner.pairwise_results.append(result)
            runner.completed_pairwise_keys.add(key)
            runner.save_checkpoint(output_path)

    runner.save_checkpoint(output_path)
    data = json.loads(output_path.read_text(encoding="utf-8"))
    errors = validate_checkpoint(data)
    if errors:
        print("Validation errors:")
        for error in errors:
            print(f"  - {error}")
        if not args.skip_pairwise:
            raise SystemExit(1)
    else:
        print(
            f"Validated: {len(data['results'])}/{len(triples)} agent results, "
            f"{len(data['pairwise_results'])} pairwise results"
        )
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--tasks", type=int, default=10)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--budget", type=int, default=8000)
    parser.add_argument("--condition-list")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--resume", type=Path)
    parser.add_argument("--skip-pairwise", action="store_true")
    parser.add_argument("--validate", type=Path)
    parser.add_argument("--check-env", action="store_true")
    args = parser.parse_args()

    if args.check_env:
        load_environment_file()
        required = ("GLM_API_KEY", "DEEPSEEK_API_KEY")
        for key in required:
            print(f"{key}={'configured' if os.getenv(key) else 'missing'}")
        if any(not os.getenv(key) for key in required):
            raise SystemExit(1)
        return

    if args.validate:
        data = json.loads(args.validate.read_text(encoding="utf-8"))
        errors = validate_checkpoint(data)
        if errors:
            for error in errors:
                print(f"ERROR: {error}")
            raise SystemExit(1)
        metadata = data["metadata"]
        print(
            f"Validated {len(data['results'])}/{len(metadata['tasks']) * len(metadata['conditions']) * metadata['runs']} "
            f"agent results and {len(data['pairwise_results'])} pairwise results"
        )
        return

    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
