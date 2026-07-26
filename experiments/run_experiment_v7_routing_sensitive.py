#!/usr/bin/env python3
"""Checkpoint-safe runner for the V7 routing-sensitive experiment.

This module deliberately keeps paid generation and paid judging behind explicit
subcommands. Offline diagnostics, validation, freeze creation, and checkpoint
inspection never invoke an external model.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import shutil
import subprocess
import tempfile
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from experiments.v7_deterministic_eval import (
    DeterministicEvaluator,
    extract_answer_json,
)
from experiments.v7_routing import (
    V7_ARMS,
    RoutingConfig,
    RoutingCorpus,
    TaskRoutingRequest,
    canonical_token_count,
    validate_context_manifest_v7,
)
from experiments.v7_stage0 import load_task_registry


SHA256_PATTERN = __import__("re").compile(r"^[0-9a-f]{64}$")
REQUIRED_USAGE_FIELDS = (
    "input_tokens",
    "output_tokens",
    "cache_read_tokens",
    "cache_creation_tokens",
    "raw_usage_sha256",
)
PROJECT_ROOT = Path(__file__).resolve().parents[1]
TASKS_PATH = (
    PROJECT_ROOT
    / "experiments"
    / "config"
    / "experiment_v7_routing_sensitive_tasks_20260725.yaml"
)
STAGE0_PATH = (
    PROJECT_ROOT
    / "experiments"
    / "results"
    / "experiment_v7_routing_sensitive_stage0_20260725.json"
)
FREEZE_PATH = (
    PROJECT_ROOT
    / "experiments"
    / "config"
    / "experiment_v7_routing_sensitive_freeze_20260725.json"
)
SMOKE_PATH = (
    PROJECT_ROOT
    / "experiments"
    / "results"
    / "experiment_v7_routing_sensitive_smoke_20260725.json"
)
FORMAL_GENERATION_PATH = (
    PROJECT_ROOT
    / "experiments"
    / "results"
    / "experiment_v7_routing_sensitive_formal_generation_20260725.json"
)
FORMAL_EVALUATED_PATH = (
    PROJECT_ROOT
    / "experiments"
    / "results"
    / "experiment_v7_routing_sensitive_formal_evaluated_20260725.json"
)
FAILURE_LOG_PATH = (
    PROJECT_ROOT
    / "experiments"
    / "results"
    / "experiment_v7_routing_sensitive_failure_log_20260725.json"
)
ENVIRONMENT_KEYS = {
    "GLM_API_KEY",
    "GLM_BASE_URL",
    "DEEPSEEK_API_KEY",
    "DEEPSEEK_BASE_URL",
    "AGENT_MODEL",
    "DEEPSEEK_MODEL",
}
GENERATION_MAX_TURNS = 1
GENERATION_TIMEOUT_SECONDS = 300
GENERATION_TRANSPORT_RETRIES = 2
JUDGE_MAX_ATTEMPTS = 6
JUDGE_MAX_TOKENS = 1200
SUPPORTED_JUDGE_MODELS = {"deepseek-v4-pro", "deepseek-v4-flash"}
ARM_DEFINITIONS = {
    "graph_bm25_chunk_optimized": (
        "Graph plus full-content BM25 chunk retrieval with dependency expansion, "
        "MMR, version conflict handling, and deterministic provenance."
    ),
    "full_corpus_bm25_token_matched": (
        "Full-corpus BM25 chunk retrieval without graph features, matched to the "
        "optimized arm's exact canonical context tokens."
    ),
    "random_token_matched": (
        "Seeded random chunk order matched to the optimized arm's exact "
        "canonical context tokens."
    ),
    "flat_8000": "Uniform alphabetical chunk loading at 8000 canonical tokens.",
}
NO_TOOLS_DIRECTIVE = """**CRITICAL: ANSWER DIRECTLY - DO NOT USE TOOLS**
All task evidence available to you is in the [Skills Context] section.
Do not call tools or inspect files. Treat only supplied evidence IDs as citable.
Return one valid JSON object and no markdown. The object must contain `answer`
and `evidence_ids`; cite exact EVIDENCE id values that support the answer.
If required evidence is absent, use null rather than inventing a rule.
"""
DOMAIN_INSTRUCTION = """You are completing a blinded clinical-data programming
task. Apply only the standards versions and constraints supported by the supplied
context. Accuracy, executable derivations, and traceable provenance matter more
than length or stylistic completeness."""
JUDGE_SYSTEM_PROMPT = """You are a blinded secondary reviewer. Score only
readability and actionability of the complete response. Do not score factual
correctness, regulatory compliance, evidence retrieval, or completeness; those
are measured by deterministic validators. Return JSON only."""


def stable_run_key(task_id: str, arm: str, run_id: int) -> str:
    return f"{task_id}::{arm}::{run_id}"


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_json_sha256(value: Any) -> str:
    return sha256_text(
        json.dumps(
            value,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )
    )


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def repository_relative_path(path: Path) -> str:
    return Path(path).resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()


def load_environment_file(path: Path = PROJECT_ROOT / ".env") -> list[str]:
    """Load only allowlisted experiment variables without logging values."""
    loaded: list[str] = []
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
        if key not in ENVIRONMENT_KEYS or key in os.environ:
            continue
        value = value.strip()
        if (
            len(value) >= 2
            and value[0] == value[-1]
            and value[0] in {"'", '"'}
        ):
            value = value[1:-1]
        os.environ[key] = value
        loaded.append(key)
    return loaded


def resolve_judge_model(configured: str | None = None) -> str:
    """Resolve legacy/unsupported aliases to the supported frozen default."""
    candidate = configured or os.getenv("DEEPSEEK_MODEL")
    if candidate in SUPPORTED_JUDGE_MODELS:
        return str(candidate)
    return "deepseek-v4-pro"


def build_transmitted_prompt(*, context: str, task_prompt: str) -> str:
    """Build the exact string serialized to the generation provider."""
    return (
        f"{NO_TOOLS_DIRECTIVE}\n"
        f"{DOMAIN_INSTRUCTION}\n\n"
        f"[Skills Context]\n{context}\n\n"
        f"[Task]\n{task_prompt.strip()}\n"
    )


def normalize_provider_usage(usage: Mapping[str, Any] | None) -> dict[str, Any]:
    raw = dict(usage or {})

    def integer(field: str) -> int:
        value = raw.get(field, 0)
        return (
            int(value)
            if isinstance(value, (int, float)) and not isinstance(value, bool)
            else 0
        )

    cache_read_source = next(
        (
            field
            for field in ("cache_read_tokens", "cache_read_input_tokens")
            if field in raw
        ),
        None,
    )
    cache_creation_source = next(
        (
            field
            for field in (
                "cache_creation_tokens",
                "cache_creation_input_tokens",
            )
            if field in raw
        ),
        None,
    )
    return {
        "input_tokens": integer("input_tokens"),
        "output_tokens": integer("output_tokens"),
        "cache_read_tokens": integer(cache_read_source)
        if cache_read_source
        else 0,
        "cache_creation_tokens": integer(cache_creation_source)
        if cache_creation_source
        else 0,
        "raw_usage_sha256": canonical_json_sha256(raw),
        "field_capture": {
            "input_tokens": (
                "input_tokens" if "input_tokens" in raw else "provider_field_absent"
            ),
            "output_tokens": (
                "output_tokens"
                if "output_tokens" in raw
                else "provider_field_absent"
            ),
            "cache_read_tokens": cache_read_source
            or "provider_field_absent_recorded_as_zero",
            "cache_creation_tokens": cache_creation_source
            or "provider_field_absent_recorded_as_zero",
        },
    }


def parse_claude_envelope(
    stdout: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Parse CLI JSON while retaining every parser strategy attempted."""
    attempts: list[dict[str, Any]] = []
    candidates = [("full_stdout", stdout.strip())]
    nonempty = [line.strip() for line in stdout.splitlines() if line.strip()]
    if nonempty and nonempty[-1] != stdout.strip():
        candidates.append(("last_nonempty_line", nonempty[-1]))
    for strategy, candidate in candidates:
        try:
            value = json.loads(candidate)
        except json.JSONDecodeError as error:
            attempts.append(
                {
                    "strategy": strategy,
                    "status": "failed",
                    "error": str(error)[:500],
                }
            )
            continue
        if not isinstance(value, Mapping):
            attempts.append(
                {
                    "strategy": strategy,
                    "status": "failed",
                    "error": "top-level CLI payload is not an object",
                }
            )
            continue
        attempts.append(
            {"strategy": strategy, "status": "success", "error": None}
        )
        return dict(value), attempts
    raise ValueError(f"Claude CLI envelope parse failed: {attempts}")


def atomic_json_write(path: Path, payload: Mapping[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(
            payload,
            indent=2,
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def validate_resume_configuration(
    checkpoint: Mapping[str, Any],
    *,
    expected_metadata: Mapping[str, Any],
) -> list[str]:
    errors: list[str] = []
    metadata = checkpoint.get("metadata")
    if not isinstance(metadata, Mapping):
        return ["checkpoint metadata must be an object"]
    immutable_fields = (
        "version",
        "seed",
        "tasks",
        "arms",
        "runs",
        "source_hashes",
        "freeze_sha256",
        "sealed_quality_until_formal_complete",
    )
    for field in immutable_fields:
        if metadata.get(field) != expected_metadata.get(field):
            errors.append(
                f"resume {field} mismatch: "
                f"{metadata.get(field)!r} != {expected_metadata.get(field)!r}"
            )
    return errors


def _finite_nonnegative_integer(value: Any) -> bool:
    return (
        isinstance(value, int)
        and not isinstance(value, bool)
        and value >= 0
    )


def validate_generation_checkpoint(
    checkpoint: Mapping[str, Any],
    *,
    allow_partial: bool = False,
) -> list[str]:
    errors: list[str] = []
    metadata = checkpoint.get("metadata")
    if not isinstance(metadata, Mapping):
        return ["metadata must be an object"]
    tasks = metadata.get("tasks")
    arms = metadata.get("arms")
    runs = metadata.get("runs")
    if not isinstance(tasks, list) or not all(isinstance(item, str) for item in tasks):
        errors.append("metadata tasks must be a string list")
        tasks = []
    if arms != list(V7_ARMS):
        errors.append("metadata arms do not match the frozen V7 arm order")
        arms = list(V7_ARMS)
    if not isinstance(runs, int) or isinstance(runs, bool) or runs <= 0:
        errors.append("metadata runs must be a positive integer")
        runs = 0
    for field in ("freeze_sha256",):
        value = metadata.get(field)
        if not isinstance(value, str) or not SHA256_PATTERN.fullmatch(value):
            errors.append(f"metadata {field} must be SHA-256")
    source_hashes = metadata.get("source_hashes")
    if not isinstance(source_hashes, Mapping) or not source_hashes:
        errors.append("metadata source_hashes must be non-empty")
    else:
        for key, value in source_hashes.items():
            if not isinstance(value, str) or not SHA256_PATTERN.fullmatch(value):
                errors.append(f"source hash {key} is invalid")

    results = checkpoint.get("results")
    if not isinstance(results, list):
        return [*errors, "results must be a list"]
    expected_keys = {
        stable_run_key(task_id, arm, run_id)
        for task_id in tasks
        for arm in V7_ARMS
        for run_id in range(runs)
    }
    seen: set[str] = set()
    for index, row in enumerate(results):
        prefix = f"results[{index}]"
        if not isinstance(row, Mapping):
            errors.append(f"{prefix} must be an object")
            continue
        key = row.get("run_key")
        if key in seen:
            errors.append(f"duplicate run_key: {key}")
        elif isinstance(key, str):
            seen.add(key)
        if key not in expected_keys:
            errors.append(f"{prefix} contains out-of-panel run_key: {key}")
        expected_key = stable_run_key(
            str(row.get("task_id")),
            str(row.get("arm")),
            int(row.get("run_id", -1)),
        )
        if key != expected_key:
            errors.append(f"{prefix} run_key linkage mismatch")
        response = row.get("response")
        if not isinstance(response, str):
            errors.append(f"{prefix} response must be a string")
            response = ""
        if row.get("response_sha256") != sha256_text(response):
            errors.append(f"{prefix} response_sha256 mismatch")
        manifest_sha = row.get("manifest_sha256")
        if not isinstance(manifest_sha, str) or not SHA256_PATTERN.fullmatch(
            manifest_sha
        ):
            errors.append(f"{prefix} manifest_sha256 is invalid")
        for field in (
            "serialized_prompt_characters",
            "serialized_prompt_bytes",
            "canonical_prompt_tokens",
        ):
            if not _finite_nonnegative_integer(row.get(field)):
                errors.append(f"{prefix} invalid or missing {field}")
        usage = row.get("provider_usage")
        if not isinstance(usage, Mapping):
            errors.append(f"{prefix} provider_usage must be an object")
        else:
            for field in REQUIRED_USAGE_FIELDS:
                if field not in usage:
                    errors.append(f"{prefix} provider_usage missing {field}")
                elif field == "raw_usage_sha256":
                    if not isinstance(
                        usage[field], str
                    ) or not SHA256_PATTERN.fullmatch(usage[field]):
                        errors.append(
                            f"{prefix} provider_usage invalid {field}"
                        )
                elif not _finite_nonnegative_integer(usage[field]):
                    errors.append(
                        f"{prefix} provider_usage invalid {field}"
                    )
        attempts = row.get("generation_attempts")
        if not isinstance(attempts, list) or not attempts:
            errors.append(f"{prefix} generation attempt history is missing")
        else:
            numbers = [attempt.get("attempt") for attempt in attempts]
            if numbers != list(range(1, len(attempts) + 1)):
                errors.append(f"{prefix} generation attempt history is not contiguous")
            if attempts[-1].get("status") != "success":
                errors.append(f"{prefix} final generation attempt is not success")
            if attempts[-1].get("response_sha256") != row.get(
                "response_sha256"
            ):
                errors.append(f"{prefix} final attempt response linkage mismatch")
        if row.get("is_error_response") is not False:
            errors.append(f"{prefix} contains an error response")
        if "deterministic_evaluation" in row and metadata.get(
            "sealed_quality_until_formal_complete"
        ):
            errors.append(
                f"{prefix} exposes deterministic score while quality seal is active"
            )
        if "llm_judgment" in row and metadata.get(
            "sealed_quality_until_formal_complete"
        ):
            errors.append(
                f"{prefix} exposes LLM score while quality seal is active"
            )
    if not allow_partial and expected_keys != seen:
        missing = sorted(expected_keys - seen)
        errors.append(f"formal panel is incomplete: {len(missing)} cells missing")
    return errors


def _source_hashes() -> dict[str, str]:
    sources = {
        "runner": Path(__file__),
        "routing": PROJECT_ROOT / "experiments" / "v7_routing.py",
        "deterministic_eval": (
            PROJECT_ROOT / "experiments" / "v7_deterministic_eval.py"
        ),
        "stage0": PROJECT_ROOT / "experiments" / "v7_stage0.py",
        "task_registry": TASKS_PATH,
        "graph": PROJECT_ROOT / "graph" / "regulatory-graph.yaml",
    }
    analyzer = PROJECT_ROOT / "experiments" / "analyze_experiment_v7.py"
    if analyzer.exists():
        sources["analyzer"] = analyzer
    verifier = PROJECT_ROOT / "experiments" / "verify_experiment_v7.py"
    if verifier.exists():
        sources["verifier"] = verifier
    return {
        name: sha256_file(path)
        for name, path in sources.items()
        if path.exists()
    }


def _corpus_hashes() -> list[dict[str, str]]:
    rows = []
    for path in sorted((PROJECT_ROOT / "csp-skills").rglob("SKILL.md")):
        rows.append(
            {
                "path": path.relative_to(PROJECT_ROOT).as_posix(),
                "sha256": sha256_file(path),
            }
        )
    return rows


def create_freeze(
    *,
    stage0_path: Path = STAGE0_PATH,
    output_path: Path = FREEZE_PATH,
    supersedes: str | None = None,
) -> dict[str, Any]:
    """Freeze V7 sources after offline diagnostics and before paid calls."""
    stage0 = json.loads(stage0_path.read_text(encoding="utf-8"))
    if stage0.get("task_registry", {}).get("sha256") != sha256_file(
        TASKS_PATH
    ):
        raise ValueError(
            "Stage 0 task-registry hash is stale; rerun offline diagnostics"
        )
    aggregate = stage0["selected_diagnostics"]["aggregate"]
    if aggregate["recall_at_k"] != 1.0:
        raise ValueError("Cannot freeze V7 with development recall@k below 1")
    if aggregate["dependency_coverage"] != 1.0:
        raise ValueError("Cannot freeze V7 with incomplete dependency coverage")
    if aggregate["provenance_completeness"] != 1.0:
        raise ValueError("Cannot freeze V7 with incomplete provenance")
    if not stage0["selected_diagnostics"]["change_impact"]["passed"]:
        raise ValueError("Cannot freeze V7 with failed change-impact partition")
    registry = load_task_registry(TASKS_PATH)
    source_hashes = _source_hashes()
    corpus_hashes = _corpus_hashes()
    config = RoutingConfig(**stage0["selected_config"])
    corpus = RoutingCorpus.from_paths(
        PROJECT_ROOT / "csp-skills",
        PROJECT_ROOT / "graph" / "regulatory-graph.yaml",
        config,
    )
    if corpus.config_sha256 != stage0["selected_config_sha256"]:
        raise ValueError("Reconstructed routing config hash differs from Stage 0")

    structural_cells: list[dict[str, Any]] = []
    for task in registry["heldout_tasks"]:
        request = TaskRoutingRequest(
            task_id=str(task["task_id"]),
            node_id=str(task["node_id"]),
            query=str(task["prompt"]),
            version_pins=dict(task.get("version_pins", {})),
        )
        optimized = corpus.build_context(
            request, V7_ARMS[0], run_id=0
        )
        targets = {V7_ARMS[0]: optimized}
        for arm in V7_ARMS[1:]:
            targets[arm] = corpus.build_context(
                request,
                arm,
                run_id=0,
                target_tokens=(
                    optimized.canonical_tokens
                    if arm in V7_ARMS[1:3]
                    else None
                ),
            )
        if not (
            targets[V7_ARMS[0]].canonical_tokens
            == targets[V7_ARMS[1]].canonical_tokens
            == targets[V7_ARMS[2]].canonical_tokens
        ):
            raise ValueError(
                f"Structural token matching failed for {task['task_id']}"
            )
        structural_cells.append(
            {
                "task_id": task["task_id"],
                "optimized_tokens": optimized.canonical_tokens,
                "manifest_sha256": {
                    arm: built.manifest["manifest_sha256"]
                    for arm, built in targets.items()
                },
            }
        )
    freeze = {
        "schema_version": "v7-routing-sensitive-freeze-1",
        "frozen_at": utc_now(),
        "supersedes_freeze_sha256": supersedes,
        "v6_immutable_sha256": (
            "fb9f787a6e95e2bd0813c7f7b90fd986e64adeba09305645572a3875df927aa0"
        ),
        "stage0_path": stage0_path.relative_to(PROJECT_ROOT).as_posix(),
        "stage0_sha256": sha256_file(stage0_path),
        "plan_path": (
            "plan/jmir_aps_gxp_v7_routing_sensitive_experiment_20260725.md"
        ),
        "plan_sha256": sha256_file(
            PROJECT_ROOT
            / "plan"
            / "jmir_aps_gxp_v7_routing_sensitive_experiment_20260725.md"
        ),
        "task_registry_sha256": sha256_file(TASKS_PATH),
        "source_hashes": source_hashes,
        "corpus_files": corpus_hashes,
        "corpus_tree_sha256": canonical_json_sha256(corpus_hashes),
        "routing_config": asdict(config),
        "routing_config_sha256": corpus.config_sha256,
        "arms": list(V7_ARMS),
        "arm_definitions": ARM_DEFINITIONS,
        "heldout_task_ids": [
            task["task_id"] for task in registry["heldout_tasks"]
        ],
        "heldout_count": len(registry["heldout_tasks"]),
        "runs": 3,
        "generation_model_requested": os.getenv("AGENT_MODEL", "glm-5"),
        "judge_model_requested": resolve_judge_model(),
        "judge_model_configuration": {
            "environment_value_supported": (
                os.getenv("DEEPSEEK_MODEL") in SUPPORTED_JUDGE_MODELS
            ),
            "unsupported_alias_policy": (
                "resolve_to_deepseek-v4-pro_before_freeze"
            ),
        },
        "generation_configuration": {
            "max_turns": GENERATION_MAX_TURNS,
            "timeout_seconds": GENERATION_TIMEOUT_SECONDS,
            "transport_retries": GENERATION_TRANSPORT_RETRIES,
            "no_tools_directive_sha256": sha256_text(NO_TOOLS_DIRECTIVE),
            "domain_instruction_sha256": sha256_text(DOMAIN_INSTRUCTION),
        },
        "judge_configuration": {
            "temperature": 0.0,
            "max_tokens": JUDGE_MAX_TOKENS,
            "maximum_attempts": JUDGE_MAX_ATTEMPTS,
            "endpoint": "readability_actionability_secondary_only",
            "system_prompt_sha256": sha256_text(JUDGE_SYSTEM_PROMPT),
        },
        "statistics": {
            "independent_unit": "task",
            "primary": "mean deterministic atomic-criterion score over 3 reps",
            "primary_contrasts": [
                [
                    "graph_bm25_chunk_optimized",
                    "full_corpus_bm25_token_matched",
                ],
                [
                    "graph_bm25_chunk_optimized",
                    "random_token_matched",
                ],
            ],
            "multiplicity": "Holm correction across two primary contrasts",
            "paired_test": "exact sign-flip permutation at task level",
            "bootstrap": "paired task bootstrap with fixed seed",
            "effect_size": "paired Cohen dz",
            "missing_policy": "generation failure aborts; invalid answer scores zero",
            "retention_margin": -0.05,
        },
        "decision_rule": (
            "Routing superiority requires positive optimized differences and "
            "Holm-adjusted p<0.05 against both BM25-only and random on the "
            "deterministic primary. Otherwise report null or efficiency/"
            "governance only."
        ),
        "heldout_structural_preflight": {
            "quality_scores_computed": False,
            "generation_or_judge_scores_used": False,
            "cell_count": len(structural_cells) * len(V7_ARMS),
            "cells": structural_cells,
        },
        "manuscript_modified": False,
        "operational_gxp_compliance_claimed": False,
    }
    freeze["freeze_content_sha256"] = canonical_json_sha256(freeze)
    atomic_json_write(output_path, freeze)
    return freeze


def _agent_environment() -> dict[str, str]:
    environment = dict(os.environ)
    for variable in (
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_AUTH_TOKEN",
        "ANTHROPIC_BASE_URL",
        "ANTHROPIC_DEFAULT_SONNET_MODEL",
        "ANTHROPIC_DEFAULT_OPUS_MODEL",
        "ANTHROPIC_DEFAULT_HAIKU_MODEL",
        "ANTHROPIC_MODEL",
    ):
        environment.pop(variable, None)
    glm_key = os.getenv("GLM_API_KEY")
    if glm_key:
        environment["ANTHROPIC_BASE_URL"] = os.getenv(
            "GLM_BASE_URL", "https://api.z.ai/api/anthropic"
        )
        environment["ANTHROPIC_AUTH_TOKEN"] = glm_key
    return environment


def _attempt_cli_generation(
    transmitted_prompt: str,
    *,
    attempt_number: int,
) -> dict[str, Any]:
    temp_root = PROJECT_ROOT / "temp"
    temp_root.mkdir(parents=True, exist_ok=True)
    run_directory = Path(
        tempfile.mkdtemp(prefix="v7_generation_", dir=temp_root)
    )
    prompt_path = run_directory / "prompt.txt"
    settings_path = run_directory / "settings.json"
    prompt_path.write_text(transmitted_prompt, encoding="utf-8")
    settings_path.write_text(
        json.dumps({"disableAllHooks": True}),
        encoding="utf-8",
    )
    model = os.getenv("AGENT_MODEL", "glm-5")
    command = (
        f'type "{prompt_path}" | claude -p --output-format json '
        f"--max-turns {GENERATION_MAX_TURNS} --model {model} "
        f'--settings "{settings_path}"'
    )
    started = time.monotonic()
    record: dict[str, Any] = {
        "attempt": attempt_number,
        "attempted_at": utc_now(),
        "status": "transport_error",
        "response_sha256": None,
    }
    try:
        process = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=GENERATION_TIMEOUT_SECONDS,
            cwd=str(run_directory),
            encoding="utf-8",
            errors="replace",
            shell=True,
            env=_agent_environment(),
        )
        duration_ms = int((time.monotonic() - started) * 1000)
        record.update(
            {
                "return_code": process.returncode,
                "duration_ms": duration_ms,
                "stdout_sha256": sha256_text(process.stdout),
                "stderr_sha256": sha256_text(process.stderr),
                "stderr_tail": process.stderr[-1000:],
            }
        )
        if process.returncode != 0 or not process.stdout.strip():
            record["error"] = "nonzero return code or empty stdout"
            return record
        try:
            envelope, parse_attempts = parse_claude_envelope(process.stdout)
        except ValueError as error:
            record["error"] = str(error)
            record["envelope_parse_attempts"] = (
                str(error)[:2000]
            )
            return record
        record["envelope_parse_attempts"] = parse_attempts
        response = envelope.get("result", "")
        if not isinstance(response, str) or not response.strip():
            record["error"] = "provider envelope contains no response text"
            return record
        if envelope.get("is_error") or str(envelope.get("subtype", "")).startswith(
            "error"
        ):
            record["error"] = "provider envelope indicates an error"
            record["provider_envelope_sha256"] = canonical_json_sha256(envelope)
            record["provider_usage"] = normalize_provider_usage(
                envelope.get("usage")
            )
            return record
        model_usage = envelope.get("modelUsage", {})
        model_returned = (
            next(iter(model_usage))
            if isinstance(model_usage, Mapping) and model_usage
            else "unknown"
        )
        record.update(
            {
                "status": "success",
                "response": response,
                "response_sha256": sha256_text(response),
                "provider_usage": normalize_provider_usage(
                    envelope.get("usage")
                ),
                "provider_envelope_sha256": canonical_json_sha256(envelope),
                "model_returned": model_returned,
                "response_id": envelope.get("session_id"),
                "finish_reason": envelope.get("stop_reason"),
                "num_turns": int(envelope.get("num_turns", 0) or 0),
                "cost_usd": float(envelope.get("total_cost_usd", 0.0) or 0.0),
            }
        )
        return record
    except subprocess.TimeoutExpired:
        record.update(
            {
                "duration_ms": GENERATION_TIMEOUT_SECONDS * 1000,
                "error": "generation transport timeout",
            }
        )
        return record
    except Exception as error:
        record.update(
            {
                "duration_ms": int((time.monotonic() - started) * 1000),
                "error": f"{type(error).__name__}: {error}"[:1000],
            }
        )
        return record
    finally:
        shutil.rmtree(run_directory, ignore_errors=True)


class V7ExperimentRunner:
    """Frozen-context builder and checkpoint-safe provider orchestrator."""

    def __init__(self, freeze_path: Path = FREEZE_PATH):
        self.freeze_path = Path(freeze_path)
        self.freeze = json.loads(self.freeze_path.read_text(encoding="utf-8"))
        if self.freeze.get("source_hashes") != _source_hashes():
            raise ValueError("Current V7 sources do not match the freeze")
        if self.freeze.get("task_registry_sha256") != sha256_file(TASKS_PATH):
            raise ValueError("Task registry differs from the freeze")
        if self.freeze.get("corpus_files") != _corpus_hashes():
            raise ValueError("Skill corpus differs from the freeze")
        self.registry = load_task_registry(TASKS_PATH)
        self.config = RoutingConfig(**self.freeze["routing_config"])
        self.corpus = RoutingCorpus.from_paths(
            PROJECT_ROOT / "csp-skills",
            PROJECT_ROOT / "graph" / "regulatory-graph.yaml",
            self.config,
        )
        if self.corpus.config_sha256 != self.freeze["routing_config_sha256"]:
            raise ValueError("Runtime routing config differs from the freeze")

    def panel(self, name: str) -> list[dict[str, Any]]:
        if name == "formal":
            return list(self.registry["heldout_tasks"])
        if name == "smoke":
            return list(self.registry["smoke_tasks"])
        raise ValueError(f"Unknown V7 panel: {name}")

    def build_contexts(
        self, task: Mapping[str, Any], run_id: int
    ) -> dict[str, Any]:
        request = TaskRoutingRequest(
            task_id=str(task["task_id"]),
            node_id=str(task["node_id"]),
            query=str(task["prompt"]),
            version_pins=dict(task.get("version_pins", {})),
        )
        optimized = self.corpus.build_context(
            request, V7_ARMS[0], run_id
        )
        contexts = {V7_ARMS[0]: optimized}
        contexts[V7_ARMS[1]] = self.corpus.build_context(
            request,
            V7_ARMS[1],
            run_id,
            target_tokens=optimized.canonical_tokens,
        )
        contexts[V7_ARMS[2]] = self.corpus.build_context(
            request,
            V7_ARMS[2],
            run_id,
            target_tokens=optimized.canonical_tokens,
        )
        contexts[V7_ARMS[3]] = self.corpus.build_context(
            request,
            V7_ARMS[3],
            run_id,
        )
        if not (
            contexts[V7_ARMS[0]].canonical_tokens
            == contexts[V7_ARMS[1]].canonical_tokens
            == contexts[V7_ARMS[2]].canonical_tokens
        ):
            raise ValueError("Canonical token matching failed")
        return contexts

    def metadata(
        self,
        tasks: Sequence[Mapping[str, Any]],
        *,
        runs: int,
        panel: str,
    ) -> dict[str, Any]:
        return {
            "version": "v7-routing-sensitive-generation-1",
            "panel": panel,
            "seed": self.config.seed,
            "tasks": [str(task["task_id"]) for task in tasks],
            "arms": list(V7_ARMS),
            "runs": runs,
            "source_hashes": self.freeze["source_hashes"],
            "freeze_sha256": sha256_file(self.freeze_path),
            "freeze_content_sha256": self.freeze["freeze_content_sha256"],
            "routing_config_sha256": self.corpus.config_sha256,
            "task_registry_sha256": sha256_file(TASKS_PATH),
            "agent_model_requested": self.freeze[
                "generation_model_requested"
            ],
            "sealed_quality_until_formal_complete": panel == "formal",
            "full_usage_accounting_required": True,
            "created_at": utc_now(),
        }


def _checkpoint_payload(
    metadata: Mapping[str, Any],
    results: Sequence[Mapping[str, Any]],
    failures: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    return {
        "metadata": dict(metadata),
        "results": list(results),
        "failed_generation_attempts": list(failures),
    }


def run_generation(
    runner: V7ExperimentRunner,
    *,
    panel: str,
    runs: int,
    output_path: Path,
) -> dict[str, Any]:
    """Run generation only; deterministic and LLM scores remain sealed."""
    tasks = runner.panel(panel)
    expected_metadata = runner.metadata(tasks, runs=runs, panel=panel)
    results: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    if output_path.exists():
        checkpoint = json.loads(output_path.read_text(encoding="utf-8"))
        errors = validate_resume_configuration(
            checkpoint,
            expected_metadata=expected_metadata,
        )
        if errors:
            raise ValueError(f"Generation resume mismatch: {errors}")
        checkpoint_errors = validate_generation_checkpoint(
            checkpoint,
            allow_partial=True,
        )
        if checkpoint_errors:
            raise ValueError(
                f"Generation resume checkpoint invalid: {checkpoint_errors}"
            )
        results = list(checkpoint.get("results", []))
        failures = list(checkpoint.get("failed_generation_attempts", []))
        metadata = dict(checkpoint["metadata"])
    else:
        metadata = expected_metadata
    completed = {str(row["run_key"]) for row in results}
    jobs = [
        (task, arm, run_id)
        for task in tasks
        for arm in V7_ARMS
        for run_id in range(runs)
    ]
    random.Random(runner.config.seed + (1 if panel == "smoke" else 0)).shuffle(
        jobs
    )
    context_cache: dict[tuple[str, int], dict[str, Any]] = {}
    for task, arm, run_id in jobs:
        key = stable_run_key(str(task["task_id"]), arm, run_id)
        if key in completed:
            continue
        cache_key = (str(task["task_id"]), run_id)
        if cache_key not in context_cache:
            context_cache[cache_key] = runner.build_contexts(task, run_id)
        built = context_cache[cache_key][arm]
        repeated = runner.build_contexts(task, run_id)[arm]
        if (
            repeated.manifest["manifest_sha256"]
            != built.manifest["manifest_sha256"]
        ):
            raise ValueError(f"Nondeterministic context manifest for {key}")
        transmitted = build_transmitted_prompt(
            context=built.context_text,
            task_prompt=str(task["prompt"]),
        )
        attempts: list[dict[str, Any]] = []
        success: dict[str, Any] | None = None
        for attempt_number in range(1, GENERATION_TRANSPORT_RETRIES + 2):
            attempt = _attempt_cli_generation(
                transmitted,
                attempt_number=attempt_number,
            )
            attempts.append(attempt)
            if attempt["status"] == "success":
                success = attempt
                break
            failures.append({"run_key": key, **attempt})
            atomic_json_write(
                output_path,
                _checkpoint_payload(metadata, results, failures),
            )
        if success is None:
            raise RuntimeError(
                f"Generation transport failed closed for {key}; "
                "no later paid job was started"
            )
        response = str(success.pop("response"))
        row = {
            "run_key": key,
            "task_id": task["task_id"],
            "node_id": task["node_id"],
            "arm": arm,
            "run_id": run_id,
            "arm_definition": ARM_DEFINITIONS[arm],
            "response": response,
            "response_sha256": sha256_text(response),
            "manifest": built.manifest,
            "manifest_sha256": built.manifest["manifest_sha256"],
            "repeated_manifest_sha256": repeated.manifest["manifest_sha256"],
            "context_canonical_tokens": built.canonical_tokens,
            "context_characters": len(built.context_text),
            "context_bytes": len(built.context_text.encode("utf-8")),
            "serialized_prompt_sha256": sha256_text(transmitted),
            "serialized_prompt_characters": len(transmitted),
            "serialized_prompt_bytes": len(transmitted.encode("utf-8")),
            "canonical_prompt_tokens": canonical_token_count(transmitted),
            "provider_canonical_tokenizer_count": None,
            "provider_canonical_tokenizer_capture": "not_exposed_by_cli",
            "provider_usage": success["provider_usage"],
            "generation_model_requested": runner.freeze[
                "generation_model_requested"
            ],
            "generation_model_returned": success["model_returned"],
            "generation_response_id": success.get("response_id"),
            "generation_finish_reason": success.get("finish_reason"),
            "generation_duration_ms": success["duration_ms"],
            "generation_num_turns": success["num_turns"],
            "generation_cost_usd": success["cost_usd"],
            "generation_attempts": attempts,
            "is_error_response": False,
            "isolated_working_directory": True,
            "created_at": utc_now(),
        }
        results.append(row)
        completed.add(key)
        atomic_json_write(
            output_path,
            _checkpoint_payload(metadata, results, failures),
        )
        print(
            f"V7_GENERATED {len(results)}/{len(jobs)} {key}",
            flush=True,
        )
    checkpoint = _checkpoint_payload(metadata, results, failures)
    errors = validate_generation_checkpoint(checkpoint, allow_partial=False)
    if errors:
        raise ValueError(f"Completed generation checkpoint invalid: {errors}")
    atomic_json_write(output_path, checkpoint)
    return checkpoint


def build_secondary_judge_prompt(
    task_prompt: str,
    response: str,
) -> str:
    return f"""Evaluate the complete blinded response below.

TASK:
{task_prompt}

COMPLETE RESPONSE:
{response}

Return only:
{{"readability": <integer 1-5>, "actionability": <integer 1-5>,
"reasoning": "<brief secondary-quality explanation>"}}
"""


def _judge_attempt(
    *,
    client: Any,
    model: str,
    prompt: str,
    attempt_number: int,
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "attempt": attempt_number,
        "attempted_at": utc_now(),
        "status": "transport_error",
        "rendered_prompt_sha256": sha256_text(prompt),
        "rendered_prompt_characters": len(prompt),
        "rendered_prompt_bytes": len(prompt.encode("utf-8")),
    }
    started = time.monotonic()
    try:
        completion = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
            max_tokens=JUDGE_MAX_TOKENS,
        )
        duration_ms = int((time.monotonic() - started) * 1000)
        choice = completion.choices[0]
        raw_response = choice.message.content or ""
        usage_raw = (
            completion.usage.model_dump()
            if completion.usage is not None
            and hasattr(completion.usage, "model_dump")
            else {}
        )
        parsed, parse_attempts = extract_answer_json(raw_response)
        record.update(
            {
                "duration_ms": duration_ms,
                "raw_response": raw_response,
                "raw_response_sha256": sha256_text(raw_response),
                "parse_attempts": parse_attempts,
                "provider_usage": normalize_provider_usage(usage_raw),
                "judge_model_requested": model,
                "judge_model_returned": str(
                    getattr(completion, "model", "unknown")
                ),
                "judge_response_id": str(
                    getattr(completion, "id", "") or ""
                ),
                "finish_reason": str(
                    getattr(choice, "finish_reason", "") or ""
                ),
                "system_fingerprint": getattr(
                    completion, "system_fingerprint", None
                ),
            }
        )
        if parsed is None:
            record["status"] = "parser_error"
            record["error"] = "judge response is not a JSON object"
            return record
        readability = parsed.get("readability")
        actionability = parsed.get("actionability")
        if not (
            isinstance(readability, int)
            and not isinstance(readability, bool)
            and 1 <= readability <= 5
            and isinstance(actionability, int)
            and not isinstance(actionability, bool)
            and 1 <= actionability <= 5
            and isinstance(parsed.get("reasoning"), str)
            and parsed["reasoning"].strip()
        ):
            record["status"] = "parser_error"
            record["error"] = "judge JSON violates the frozen scalar schema"
            return record
        record["status"] = "success"
        record["judgment"] = {
            "readability": readability,
            "actionability": actionability,
            "secondary_mean": round(
                (readability + actionability) / 2.0, 12
            ),
            "reasoning": parsed["reasoning"],
        }
        return record
    except Exception as error:
        record.update(
            {
                "duration_ms": int((time.monotonic() - started) * 1000),
                "error": f"{type(error).__name__}: {error}"[:2000],
            }
        )
        return record


def _new_judge_client() -> tuple[Any, str]:
    from openai import OpenAI

    load_environment_file()
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise PermissionError("DEEPSEEK_API_KEY is required for V7 judging")
    client = OpenAI(
        api_key=api_key,
        base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
    )
    return client, resolve_judge_model()


def run_smoke(
    runner: V7ExperimentRunner,
    *,
    output_path: Path = SMOKE_PATH,
) -> dict[str, Any]:
    """Exercise transport/parser/checkpoint/full-response judging without scores."""
    checkpoint = run_generation(
        runner,
        panel="smoke",
        runs=1,
        output_path=output_path,
    )
    if checkpoint.get("smoke_transport_audit", {}).get("passed"):
        return checkpoint
    checkpoint.setdefault(
        "pre_fix_judge_failure_record",
        {
            "frozen_smoke_attempt_count": 6,
            "diagnostic_attempt_count": 1,
            "status": "transport_error",
            "root_cause": (
                "configured legacy model alias deepseek-chat rejected with "
                "HTTP 400; provider supports deepseek-v4-pro or "
                "deepseek-v4-flash"
            ),
            "response_or_score_produced": False,
            "attempt_payloads_unavailable": (
                "pre-fix smoke path raised before checkpointing judge attempts"
            ),
            "remediation_scope": "transport_parser_configuration_only",
        },
    )
    checkpoint.setdefault("smoke_judge_attempts", [])
    atomic_json_write(output_path, checkpoint)
    task = runner.panel("smoke")[0]
    client, model = _new_judge_client()
    judge_audit = []
    for row in checkpoint["results"]:
        parsed, parse_attempts = extract_answer_json(row["response"])
        if parsed is None:
            raise RuntimeError(
                f"Smoke generation response parser failed for {row['run_key']}"
            )
        prompt = build_secondary_judge_prompt(
            str(task["prompt"]), row["response"]
        )
        attempts = []
        success = None
        for attempt_number in range(1, JUDGE_MAX_ATTEMPTS + 1):
            attempt = _judge_attempt(
                client=client,
                model=model,
                prompt=prompt,
                attempt_number=attempt_number,
            )
            attempts.append(attempt)
            sanitized_attempt = {
                key: value
                for key, value in attempt.items()
                if key not in {"judgment", "raw_response"}
            }
            sanitized_attempt["score_values_exposed"] = False
            checkpoint["smoke_judge_attempts"].append(
                {"run_key": row["run_key"], **sanitized_attempt}
            )
            atomic_json_write(output_path, checkpoint)
            if attempt["status"] == "success":
                success = attempt
                break
            time.sleep(min(2 * attempt_number, 10))
        if success is None:
            raise RuntimeError(
                f"Smoke judge transport/parser failed for {row['run_key']}"
            )
        judge_audit.append(
            {
                "run_key": row["run_key"],
                "generation_json_parse_status": "success",
                "generation_parse_attempts": parse_attempts,
                "complete_response_sha256_judged": row["response_sha256"],
                "complete_response_characters_judged": len(row["response"]),
                "complete_response_bytes_judged": len(
                    row["response"].encode("utf-8")
                ),
                "judge_attempt_count": len(attempts),
                "judge_status": "success",
                "judge_raw_response_sha256": success[
                    "raw_response_sha256"
                ],
                "judge_provider_usage": success["provider_usage"],
                "judge_identity": {
                    "requested": success["judge_model_requested"],
                    "returned": success["judge_model_returned"],
                    "response_id": success["judge_response_id"],
                    "finish_reason": success["finish_reason"],
                },
                "score_values_exposed": False,
                "router_parameters_changed": False,
            }
        )
    checkpoint["smoke_transport_audit"] = {
        "schema_version": "v7-smoke-transport-audit-1",
        "passed": True,
        "completed_at": utc_now(),
        "arm_scores_aggregated_or_inspected": False,
        "router_parameters_changed": False,
        "allowed_fix_scope": "transport_parser_or_configuration_only",
        "cells": judge_audit,
    }
    atomic_json_write(output_path, checkpoint)
    return checkpoint


def _task_map(registry: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(task["task_id"]): dict(task)
        for task in registry["heldout_tasks"]
    }


def run_formal_evaluation(
    runner: V7ExperimentRunner,
    *,
    generation_path: Path = FORMAL_GENERATION_PATH,
    output_path: Path = FORMAL_EVALUATED_PATH,
) -> dict[str, Any]:
    """Score stored formal responses locally, then run blinded secondary judging."""
    generation = json.loads(generation_path.read_text(encoding="utf-8"))
    generation_errors = validate_generation_checkpoint(
        generation, allow_partial=False
    )
    if generation_errors:
        raise ValueError(
            f"Formal generation checkpoint invalid: {generation_errors}"
        )
    if generation["metadata"].get("panel") != "formal":
        raise ValueError("Evaluation source is not the formal panel")
    generation_sha256 = sha256_file(generation_path)
    tasks = _task_map(runner.registry)
    if output_path.exists():
        evaluated = json.loads(output_path.read_text(encoding="utf-8"))
        if (
            evaluated.get("metadata", {}).get("source_generation_sha256")
            != generation_sha256
        ):
            raise ValueError("Evaluated resume source generation mismatch")
        rows = list(evaluated.get("results", []))
        if [row.get("run_key") for row in rows] != [
            row.get("run_key") for row in generation["results"]
        ]:
            raise ValueError("Evaluated resume row linkage mismatch")
    else:
        evaluator = DeterministicEvaluator()
        rows = []
        for source_row in generation["results"]:
            row = dict(source_row)
            task = tasks[str(row["task_id"])]
            row["deterministic_evaluation"] = evaluator.evaluate(
                task,
                str(row["response"]),
                row["manifest"],
            )
            row["llm_judge_attempts"] = []
            row["llm_judgment"] = None
            rows.append(row)
        metadata = dict(generation["metadata"])
        metadata.update(
            {
                "version": "v7-routing-sensitive-evaluated-1",
                "source_generation_path": repository_relative_path(
                    generation_path
                ),
                "source_generation_sha256": generation_sha256,
                "sealed_quality_until_formal_complete": False,
                "deterministic_primary_complete": True,
                "secondary_judging_complete": False,
                "evaluated_at": utc_now(),
            }
        )
        evaluated = {
            "metadata": metadata,
            "results": rows,
            "failed_generation_attempts": generation.get(
                "failed_generation_attempts", []
            ),
            "judge_failure_log": [],
        }
        atomic_json_write(output_path, evaluated)

    client, model = _new_judge_client()
    jobs = [
        row for row in rows if not isinstance(row.get("llm_judgment"), Mapping)
    ]
    random.Random(runner.config.seed + 77).shuffle(jobs)
    completed = sum(
        isinstance(row.get("llm_judgment"), Mapping) for row in rows
    )
    for row in jobs:
        task = tasks[str(row["task_id"])]
        prompt = build_secondary_judge_prompt(
            str(task["prompt"]), str(row["response"])
        )
        prior_attempts = list(row.get("llm_judge_attempts", []))
        success = None
        start_attempt = len(prior_attempts) + 1
        for attempt_number in range(
            start_attempt, start_attempt + JUDGE_MAX_ATTEMPTS
        ):
            attempt = _judge_attempt(
                client=client,
                model=model,
                prompt=prompt,
                attempt_number=attempt_number,
            )
            prior_attempts.append(attempt)
            row["llm_judge_attempts"] = prior_attempts
            if attempt["status"] == "success":
                success = attempt
                break
            evaluated["judge_failure_log"].append(
                {
                    "run_key": row["run_key"],
                    "attempt": attempt_number,
                    "status": attempt["status"],
                    "error": attempt.get("error"),
                    "raw_response_sha256": attempt.get(
                        "raw_response_sha256"
                    ),
                }
            )
            atomic_json_write(output_path, evaluated)
            time.sleep(min(2 * attempt_number, 15))
        if success is None:
            atomic_json_write(output_path, evaluated)
            raise RuntimeError(
                f"Judge failed closed for {row['run_key']}; "
                "all attempts are preserved and no score was substituted"
            )
        row["llm_judgment"] = {
            **success["judgment"],
            "complete_response_sha256_judged": row["response_sha256"],
            "complete_response_characters_judged": len(row["response"]),
            "complete_response_bytes_judged": len(
                row["response"].encode("utf-8")
            ),
            "rendered_prompt_sha256": success[
                "rendered_prompt_sha256"
            ],
            "rendered_prompt_characters": success[
                "rendered_prompt_characters"
            ],
            "rendered_prompt_bytes": success["rendered_prompt_bytes"],
            "judge_model_requested": success["judge_model_requested"],
            "judge_model_returned": success["judge_model_returned"],
            "judge_response_id": success["judge_response_id"],
            "finish_reason": success["finish_reason"],
            "system_fingerprint": success["system_fingerprint"],
            "provider_usage": success["provider_usage"],
            "blinded_arm_identity": True,
            "secondary_only": True,
        }
        completed += 1
        atomic_json_write(output_path, evaluated)
        print(
            f"V7_JUDGED {completed}/{len(rows)} {row['run_key']}",
            flush=True,
        )
    evaluated["metadata"]["secondary_judging_complete"] = True
    evaluated["metadata"]["completed_at"] = utc_now()
    atomic_json_write(output_path, evaluated)
    return evaluated


def write_failure_log(
    *,
    generation_path: Path = FORMAL_GENERATION_PATH,
    evaluated_path: Path = FORMAL_EVALUATED_PATH,
    output_path: Path = FAILURE_LOG_PATH,
) -> dict[str, Any]:
    generation = json.loads(generation_path.read_text(encoding="utf-8"))
    evaluated = (
        json.loads(evaluated_path.read_text(encoding="utf-8"))
        if evaluated_path.exists()
        else {}
    )
    log = {
        "schema_version": "v7-failure-log-1",
        "created_at": utc_now(),
        "generation_checkpoint_sha256": sha256_file(generation_path),
        "evaluated_checkpoint_sha256": (
            sha256_file(evaluated_path) if evaluated_path.exists() else None
        ),
        "generation_attempt_failures": generation.get(
            "failed_generation_attempts", []
        ),
        "judge_attempt_failures": evaluated.get("judge_failure_log", []),
        "silent_score_substitutions": 0,
    }
    atomic_json_write(output_path, log)
    return log


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    freeze_parser = subparsers.add_parser(
        "freeze", help="Freeze sources and configuration after offline tests."
    )
    freeze_parser.add_argument("--stage0", type=Path, default=STAGE0_PATH)
    freeze_parser.add_argument("--output", type=Path, default=FREEZE_PATH)
    freeze_parser.add_argument("--supersedes")

    smoke_parser = subparsers.add_parser(
        "smoke", help="Run the fixed four-cell transport/parser smoke."
    )
    smoke_parser.add_argument("--freeze", type=Path, default=FREEZE_PATH)
    smoke_parser.add_argument("--output", type=Path, default=SMOKE_PATH)

    generate_parser = subparsers.add_parser(
        "generate", help="Run or resume the complete formal generation panel."
    )
    generate_parser.add_argument("--freeze", type=Path, default=FREEZE_PATH)
    generate_parser.add_argument(
        "--output", type=Path, default=FORMAL_GENERATION_PATH
    )

    evaluate_parser = subparsers.add_parser(
        "evaluate",
        help="Deterministically score and secondarily judge stored responses.",
    )
    evaluate_parser.add_argument("--freeze", type=Path, default=FREEZE_PATH)
    evaluate_parser.add_argument(
        "--generation", type=Path, default=FORMAL_GENERATION_PATH
    )
    evaluate_parser.add_argument(
        "--output", type=Path, default=FORMAL_EVALUATED_PATH
    )

    validate_parser = subparsers.add_parser(
        "validate-checkpoint",
        help="Validate an existing generation checkpoint offline.",
    )
    validate_parser.add_argument("path", type=Path)
    validate_parser.add_argument("--allow-partial", action="store_true")

    subparsers.add_parser(
        "failure-log", help="Consolidate preserved failed attempts."
    )
    args = parser.parse_args()
    if args.command == "freeze":
        load_environment_file()
        freeze = create_freeze(
            stage0_path=args.stage0,
            output_path=args.output,
            supersedes=args.supersedes,
        )
        print(
            json.dumps(
                {
                    "freeze": str(args.output),
                    "freeze_sha256": sha256_file(args.output),
                    "freeze_content_sha256": freeze[
                        "freeze_content_sha256"
                    ],
                },
                sort_keys=True,
            )
        )
        return
    if args.command == "validate-checkpoint":
        checkpoint = json.loads(
            args.path.read_text(encoding="utf-8")
        )
        errors = validate_generation_checkpoint(
            checkpoint, allow_partial=args.allow_partial
        )
        if errors:
            raise SystemExit("\n".join(errors))
        print("V7_CHECKPOINT_VALID")
        return
    if args.command == "failure-log":
        log = write_failure_log()
        print(
            json.dumps(
                {
                    "generation_failures": len(
                        log["generation_attempt_failures"]
                    ),
                    "judge_failures": len(log["judge_attempt_failures"]),
                },
                sort_keys=True,
            )
        )
        return
    load_environment_file()
    runner = V7ExperimentRunner(args.freeze)
    if args.command == "smoke":
        run_smoke(runner, output_path=args.output)
        print(f"V7_SMOKE_COMPLETE {args.output}")
        return
    if args.command == "generate":
        run_generation(
            runner,
            panel="formal",
            runs=3,
            output_path=args.output,
        )
        print(f"V7_FORMAL_GENERATION_COMPLETE {args.output}")
        return
    if args.command == "evaluate":
        run_formal_evaluation(
            runner,
            generation_path=args.generation,
            output_path=args.output,
        )
        print(f"V7_FORMAL_EVALUATION_COMPLETE {args.output}")
        return
    parser.error(f"Unknown command: {args.command}")


if __name__ == "__main__":
    main()
