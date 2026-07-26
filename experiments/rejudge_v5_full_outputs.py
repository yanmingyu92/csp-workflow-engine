#!/usr/bin/env python3
"""Re-judge stored v5 responses in full and balance pairwise presentation order.

This script never calls the generation model. It preserves the original
prefix-based judgments, scores each stored response without character
truncation, and evaluates every prespecified pair in both A/B orientations.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Sequence

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from experiments import run_experiment_v4_claude as v4  # noqa: E402
from experiments import run_experiment_v5_corrected as v5  # noqa: E402


REJUDGE_VERSION = "v5-full-response-bidirectional-1"
JUDGE_MODEL = "deepseek-v4-flash"
THINKING_MODE = "disabled"
SCALAR_MAX_TOKENS = 400
PAIRWISE_MAX_TOKENS = 300
MAX_RENDERED_PROMPT_BYTES = 2_000_000
PRICING_USD_PER_MILLION = {
    "prompt_cache_hit": 0.0028,
    "prompt_cache_miss": 0.14,
    "completion": 0.28,
}
PRICING_AS_OF = "2026-07-17"
PRICING_SOURCE = "https://api-docs.deepseek.com/quick_start/pricing"


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_sha256(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return _sha256_text(encoded)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_scalar_prompt(
    task_description: str, domain_criteria: str, response: str
) -> str:
    """Build a scalar judge prompt containing the complete stored response."""
    return v4.MULTI_DIM_JUDGE_PROMPT.format(
        task_description=task_description,
        domain_criteria=domain_criteria,
        response=response,
    )


def parse_pairwise_judgment(content: str) -> tuple[Dict[str, str] | None, str | None]:
    """Strictly parse all required pairwise JSON fields."""
    raw = (content or "").strip()
    if raw.startswith("```json") and raw.endswith("```"):
        raw = raw[7:-3].strip()
    elif raw.startswith("```") and raw.endswith("```"):
        raw = raw[3:-3].strip()
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError) as error:
        return None, f"invalid JSON: {error}"
    if not isinstance(parsed, dict):
        return None, "pairwise judgment must be a JSON object"
    winner = parsed.get("winner")
    reason = parsed.get("reason")
    confidence = parsed.get("confidence")
    if winner not in {"A", "B", "tie"}:
        return None, "winner must be A, B, or tie"
    if not isinstance(reason, str) or not reason.strip():
        return None, "reason must be a nonempty string"
    if confidence not in {"high", "medium", "low"}:
        return None, "confidence must be high, medium, or low"
    return {
        "winner": winner,
        "reason": reason.strip()[:500],
        "confidence": confidence,
    }, None


def _usage_snapshot(response: Any) -> Dict[str, int]:
    usage = getattr(response, "usage", None)
    prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
    completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
    cache_hit = int(getattr(usage, "prompt_cache_hit_tokens", 0) or 0)
    raw_miss = getattr(usage, "prompt_cache_miss_tokens", None)
    cache_miss = (
        int(raw_miss)
        if raw_miss is not None
        else max(0, prompt_tokens - cache_hit)
    )
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": int(
            getattr(usage, "total_tokens", prompt_tokens + completion_tokens)
            or 0
        ),
        "prompt_cache_hit_tokens": cache_hit,
        "prompt_cache_miss_tokens": cache_miss,
    }


def _current_judge_cost(usage: Mapping[str, int]) -> float:
    return (
        usage["prompt_cache_hit_tokens"]
        * PRICING_USD_PER_MILLION["prompt_cache_hit"]
        + usage["prompt_cache_miss_tokens"]
        * PRICING_USD_PER_MILLION["prompt_cache_miss"]
        + usage["completion_tokens"]
        * PRICING_USD_PER_MILLION["completion"]
    ) / 1_000_000


def build_rejudge_protocol(
    source: Mapping[str, Any], criteria_by_node: Mapping[str, str]
) -> Dict[str, Any]:
    """Return the complete fail-closed protocol description used for resume."""
    protocol = {
        "version": REJUDGE_VERSION,
        "script_sha256": _sha256_file(Path(__file__)),
        "dependency_sha256": {
            "run_experiment_v4_claude": _sha256_file(Path(v4.__file__)),
            "run_experiment_v5_corrected": _sha256_file(Path(v5.__file__)),
        },
        "judge_model_requested": JUDGE_MODEL,
        "thinking_mode": THINKING_MODE,
        "temperature": 0.0,
        "response_format": "json_object",
        "scalar_max_tokens": SCALAR_MAX_TOKENS,
        "pairwise_max_tokens": PAIRWISE_MAX_TOKENS,
        "max_rendered_prompt_bytes": MAX_RENDERED_PROMPT_BYTES,
        "scalar_prompt_template_sha256": _sha256_text(v4.MULTI_DIM_JUDGE_PROMPT),
        "pairwise_prompt_template_sha256": _sha256_text(v4.PAIRWISE_JUDGE_PROMPT),
        "pairwise_contrasts": [list(item) for item in v5.PAIRWISE_CONTRASTS],
        "domain_criteria_by_node": dict(sorted(criteria_by_node.items())),
        "task_prompt_sha256": {
            task_id: _sha256_text(v4.TASK_PROMPTS[task_id])
            for task_id in source.get("metadata", {}).get("tasks", [])
        },
        "pricing_usd_per_million": PRICING_USD_PER_MILLION,
        "pricing_as_of": PRICING_AS_OF,
        "pricing_source": PRICING_SOURCE,
    }
    protocol["protocol_sha256"] = _canonical_sha256(protocol)
    return protocol


def preflight_summary(
    source: Mapping[str, Any], criteria_by_node: Mapping[str, str]
) -> Dict[str, Any]:
    """Measure the exact external payload scope without making API calls."""
    scalar = []
    for row in source.get("results", []):
        prompt = build_scalar_prompt(
            v4.TASK_PROMPTS[str(row["task_id"])],
            criteria_by_node[str(row["graph_node"])],
            str(row["response"]),
        )
        scalar.append(
            {
                "key": row["run_key"],
                "prompt_bytes": len(prompt.encode("utf-8")),
                "response_bytes": len(str(row["response"]).encode("utf-8")),
            }
        )
    pairwise = []
    for job in build_pairwise_jobs(source.get("results", [])):
        prompt = v4.PAIRWISE_JUDGE_PROMPT.format(
            task_description=v4.TASK_PROMPTS[str(job["task_id"])],
            domain_criteria=criteria_by_node[str(job["graph_node"])],
            response_a=job["response_a"],
            response_b=job["response_b"],
        )
        pairwise.append(
            {
                "key": job["pairwise_key"],
                "prompt_bytes": len(prompt.encode("utf-8")),
                "response_bytes": len(job["response_a"].encode("utf-8"))
                + len(job["response_b"].encode("utf-8")),
            }
        )
    largest_scalar = max(scalar, key=lambda item: item["prompt_bytes"])
    largest_pairwise = max(pairwise, key=lambda item: item["prompt_bytes"])
    return {
        "scalar_calls": len(scalar),
        "pairwise_presentation_calls": len(pairwise),
        "logical_pairs": len(pairwise) // 2,
        "total_calls": len(scalar) + len(pairwise),
        "total_rendered_prompt_bytes": sum(
            item["prompt_bytes"] for item in scalar + pairwise
        ),
        "maximum_scalar": largest_scalar,
        "maximum_pairwise": largest_pairwise,
        "fail_closed_prompt_byte_limit": MAX_RENDERED_PROMPT_BYTES,
        "all_prompts_within_limit": all(
            item["prompt_bytes"] <= MAX_RENDERED_PROMPT_BYTES
            for item in scalar + pairwise
        ),
    }


def normalize_pairwise_winner(
    raw_winner: str,
    orientation: str,
    condition_a: str,
    condition_b: str,
) -> str:
    """Map a presented A/B winner back to the logical condition identity."""
    normalized = raw_winner.strip().lower()
    if normalized == "tie":
        return "tie"
    if normalized not in {"a", "b"}:
        return "error"
    if orientation == "ab":
        return condition_a if normalized == "a" else condition_b
    if orientation == "ba":
        return condition_b if normalized == "a" else condition_a
    raise ValueError(f"Unknown orientation: {orientation}")


def build_pairwise_jobs(
    rows: Iterable[Mapping[str, Any]],
    contrasts: Sequence[tuple[str, str]] = v5.PAIRWISE_CONTRASTS,
) -> list[Dict[str, Any]]:
    """Create two full-response presentation jobs for each matched pair."""
    row_list = list(rows)
    index = {
        (str(row["task_id"]), int(row["run_id"]), str(row["condition"])): row
        for row in row_list
    }
    if len(index) != len(row_list):
        raise ValueError("Duplicate task-run-condition rows in source checkpoint")
    task_runs = sorted({(task, run_id) for task, run_id, _ in index})
    jobs: list[Dict[str, Any]] = []
    for task_id, run_id in task_runs:
        for condition_a, condition_b in contrasts:
            row_a = index.get((task_id, run_id, condition_a))
            row_b = index.get((task_id, run_id, condition_b))
            if row_a is None or row_b is None:
                raise ValueError(
                    f"Missing matched pair for {task_id} run {run_id}: "
                    f"{condition_a} vs {condition_b}"
                )
            logical_key = v5.stable_pairwise_key(
                task_id, run_id, condition_a, condition_b
            )
            for orientation in ("ab", "ba"):
                if orientation == "ab":
                    presented_a, presented_b = row_a, row_b
                else:
                    presented_a, presented_b = row_b, row_a
                jobs.append(
                    {
                        "pairwise_key": f"{logical_key}::orientation_{orientation}",
                        "logical_pair_key": logical_key,
                        "task_id": task_id,
                        "run_id": run_id,
                        "condition_a": condition_a,
                        "condition_b": condition_b,
                        "orientation": orientation,
                        "presented_condition_a": str(presented_a["condition"]),
                        "presented_condition_b": str(presented_b["condition"]),
                        "graph_node": str(row_a["graph_node"]),
                        "response_a": str(presented_a["response"]),
                        "response_b": str(presented_b["response"]),
                    }
                )
    return jobs


def aggregate_pairwise_presentations(
    presentations: Iterable[Mapping[str, Any]],
) -> list[Dict[str, Any]]:
    """Collapse AB/BA calls into one conservative logical-pair result."""
    grouped: Dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for presentation in presentations:
        grouped[str(presentation["logical_pair_key"])].append(presentation)
    output: list[Dict[str, Any]] = []
    for logical_key in sorted(grouped):
        rows = sorted(grouped[logical_key], key=lambda item: item["orientation"])
        first = rows[0]
        orientations = {str(row["orientation"]) for row in rows}
        valid = (
            len(rows) == 2
            and orientations == {"ab", "ba"}
            and not any(row.get("judge_parse_error") for row in rows)
        )
        winners = [str(row.get("winner")) for row in rows]
        agreement = valid and winners[0] == winners[1]
        if not valid:
            consensus = "error"
        elif agreement:
            consensus = winners[0]
        else:
            consensus = "discordant"
        output.append(
            {
                "pairwise_key": logical_key,
                "logical_pair_key": logical_key,
                "task_id": first.get("task_id"),
                "run_id": first.get("run_id"),
                "condition_a": first.get("condition_a"),
                "condition_b": first.get("condition_b"),
                "winner": consensus,
                "orientation_agreement": bool(agreement),
                "orientation_winners": {
                    str(row["orientation"]): row.get("winner") for row in rows
                },
                "presentation_keys": [row["pairwise_key"] for row in rows],
                "judge_parse_error": (
                    None if valid else "missing or invalid orientation judgment"
                ),
            }
        )
    return output


def validate_rejudged_checkpoint(
    checkpoint: Mapping[str, Any],
    expected_pairs: int | None = None,
    source: Mapping[str, Any] | None = None,
    current_protocol: Mapping[str, Any] | None = None,
) -> list[str]:
    """Validate completion, full-response provenance, and paired orientations."""
    errors: list[str] = []
    rows = list(checkpoint.get("results", []))
    presentations = list(checkpoint.get("pairwise_presentations", []))
    logical_results = list(checkpoint.get("pairwise_results", []))
    metadata = checkpoint.get("metadata", {})
    if checkpoint.get("metadata", {}).get("response_judging_policy") != (
        "full_stored_response_no_character_truncation"
    ):
        errors.append("metadata does not declare full-response scalar judging")
    if checkpoint.get("metadata", {}).get("pairwise_presentation_policy") != (
        "both_ab_and_ba_orientations"
    ):
        errors.append("metadata does not declare bidirectional pairwise judging")
    stored_protocol = metadata.get("rejudge_protocol", {})
    if not stored_protocol or metadata.get("rejudge_protocol_sha256") != (
        stored_protocol.get("protocol_sha256")
    ):
        errors.append("rejudge protocol or protocol hash is missing")
    if current_protocol is not None and stored_protocol != current_protocol:
        errors.append("current rejudge protocol does not match checkpoint protocol")
    incomplete_scalar = [
        row.get("run_key")
        for row in rows
        if not row.get("full_response_judgment")
        or row["full_response_judgment"].get("judge_parse_error")
        or not row["full_response_judgment"].get("judge_model_returned")
        or row.get("quality_score") is None
    ]
    if incomplete_scalar:
        errors.append(f"scalar judgments incomplete or invalid: {len(incomplete_scalar)}")
    truncated_scalar = [
        row.get("run_key")
        for row in rows
        if row.get("full_response_judgment", {}).get("truncated") is not False
    ]
    if truncated_scalar:
        errors.append(f"scalar judgments lack full-response proof: {len(truncated_scalar)}")

    source_index: Dict[str, Mapping[str, Any]] = {}
    if source is not None:
        source_errors = v5.validate_checkpoint(source)
        if source_errors:
            errors.append(f"source checkpoint invalid: {source_errors}")
        source_index = {
            str(row["run_key"]): row for row in source.get("results", [])
        }
        if len(source_index) != len(source.get("results", [])):
            errors.append("source checkpoint has duplicate run keys")
        if {str(row.get("run_key")) for row in rows} != set(source_index):
            errors.append("rejudged scalar run keys differ from source checkpoint")
        criteria_by_node = stored_protocol.get("domain_criteria_by_node", {})
        for row in rows:
            source_row = source_index.get(str(row.get("run_key")))
            judgment = row.get("full_response_judgment", {})
            if source_row is None or not judgment:
                continue
            response_text = str(source_row["response"])
            if judgment.get("response_sha256") != _sha256_text(response_text):
                errors.append(f"scalar response hash mismatch: {row.get('run_key')}")
            if judgment.get("response_characters_judged") != len(response_text):
                errors.append(f"scalar response length mismatch: {row.get('run_key')}")
            if judgment.get("response_bytes_judged") != len(
                response_text.encode("utf-8")
            ):
                errors.append(f"scalar response byte count mismatch: {row.get('run_key')}")
            task_id = str(row["task_id"])
            criteria = criteria_by_node.get(str(row["graph_node"]))
            if criteria is not None:
                prompt = build_scalar_prompt(
                    v4.TASK_PROMPTS[task_id], criteria, response_text
                )
                if judgment.get("rendered_prompt_sha256") != _sha256_text(prompt):
                    errors.append(f"scalar prompt hash mismatch: {row.get('run_key')}")

    grouped: Dict[str, set[str]] = defaultdict(set)
    for result in presentations:
        grouped[str(result.get("logical_pair_key"))].add(
            str(result.get("orientation"))
        )
        if result.get("judge_parse_error"):
            errors.append(
                f"pairwise judgment unparseable: {result.get('pairwise_key')}"
            )
        elif not result.get("judge_model_returned"):
            errors.append(
                f"pairwise returned model missing: {result.get('pairwise_key')}"
            )
        if result.get("truncated") is not False:
            errors.append(
                f"pairwise judgment lacks full-response proof: {result.get('pairwise_key')}"
            )
    missing_orientation = [
        key for key, orientations in grouped.items() if orientations != {"ab", "ba"}
    ]
    if missing_orientation:
        errors.append(
            f"pairwise orientation incomplete for {len(missing_orientation)} logical pairs"
        )
    if expected_pairs is not None:
        if len(grouped) != expected_pairs:
            errors.append(
                f"logical pairwise cardinality {len(grouped)} != {expected_pairs}"
            )
        if len(presentations) != expected_pairs * 2:
            errors.append(
                f"pairwise presentation cardinality {len(presentations)} != {expected_pairs * 2}"
            )
        if len(logical_results) != expected_pairs:
            errors.append(
                f"logical result cardinality {len(logical_results)} != {expected_pairs}"
            )
    if len({row.get("pairwise_key") for row in presentations}) != len(presentations):
        errors.append("duplicate pairwise presentation keys")
    expected_logical = aggregate_pairwise_presentations(presentations)
    if logical_results != expected_logical:
        errors.append("stored logical pairwise results do not match presentations")

    if source_index:
        criteria_by_node = stored_protocol.get("domain_criteria_by_node", {})
        for result in presentations:
            task_id = str(result["task_id"])
            run_id = int(result["run_id"])
            condition_a = str(result["presented_condition_a"])
            condition_b = str(result["presented_condition_b"])
            source_a = source_index.get(v5.stable_run_key(task_id, condition_a, run_id))
            source_b = source_index.get(v5.stable_run_key(task_id, condition_b, run_id))
            if source_a is None or source_b is None:
                errors.append(f"pairwise source row missing: {result.get('pairwise_key')}")
                continue
            response_a = str(source_a["response"])
            response_b = str(source_b["response"])
            for side, response_text in (("a", response_a), ("b", response_b)):
                if result.get(f"response_{side}_sha256") != _sha256_text(response_text):
                    errors.append(
                        f"pairwise response {side} hash mismatch: {result.get('pairwise_key')}"
                    )
                if result.get(f"response_{side}_characters") != len(response_text):
                    errors.append(
                        f"pairwise response {side} length mismatch: {result.get('pairwise_key')}"
                    )
                if result.get(f"response_{side}_bytes") != len(response_text.encode("utf-8")):
                    errors.append(
                        f"pairwise response {side} byte mismatch: {result.get('pairwise_key')}"
                    )
            criteria = criteria_by_node.get(str(source_a["graph_node"]))
            if criteria is not None:
                prompt = v4.PAIRWISE_JUDGE_PROMPT.format(
                    task_description=v4.TASK_PROMPTS[task_id],
                    domain_criteria=criteria,
                    response_a=response_a,
                    response_b=response_b,
                )
                if result.get("rendered_prompt_sha256") != _sha256_text(prompt):
                    errors.append(
                        f"pairwise prompt hash mismatch: {result.get('pairwise_key')}"
                    )
    returned_models = {
        str(model)
        for model in [
            *(
                row.get("full_response_judgment", {}).get("judge_model_returned")
                for row in rows
            ),
            *(row.get("judge_model_returned") for row in presentations),
        ]
        if model
    }
    if returned_models and returned_models != {JUDGE_MODEL}:
        errors.append(f"unexpected returned judge models: {sorted(returned_models)}")
    fingerprints = {
        str(fingerprint)
        for fingerprint in [
            *(
                row.get("full_response_judgment", {}).get("system_fingerprint")
                for row in rows
            ),
            *(row.get("system_fingerprint") for row in presentations),
        ]
        if fingerprint
    }
    if len(fingerprints) > 1:
        errors.append(f"mixed judge system fingerprints: {sorted(fingerprints)}")
    return errors


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def _prefix_judgment(row: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "policy": "first_4000_characters",
        "dim_completeness": row.get("dim_completeness"),
        "dim_terminology": row.get("dim_terminology"),
        "dim_structure": row.get("dim_structure"),
        "dim_reasoning": row.get("dim_reasoning"),
        "quality_score": row.get("quality_score"),
        "judge_cost_usd": row.get("judge_cost_usd"),
        "judge_model_requested": row.get("judge_model_requested"),
        "judge_model_returned": row.get("judge_model_returned"),
        "judge_response_id": row.get("judge_response_id"),
        "judge_input_tokens": row.get("judge_input_tokens"),
        "judge_output_tokens": row.get("judge_output_tokens"),
        "judge_parse_error": row.get("judge_parse_error"),
    }


def initialize_checkpoint(
    source: Mapping[str, Any],
    source_path: Path,
    protocol: Mapping[str, Any],
) -> Dict[str, Any]:
    """Copy the source checkpoint and preserve all prefix judgments explicitly."""
    output = json.loads(json.dumps(source))
    source_hash = _sha256_file(source_path)
    source_metadata = dict(source.get("metadata", {}))
    for row in output.get("results", []):
        row.setdefault("prefix_judgment", _prefix_judgment(row))
    output["prefix_pairwise_results"] = output.get("pairwise_results", [])
    output["pairwise_results"] = []
    output["pairwise_presentations"] = []
    output["source_metadata"] = source_metadata
    output["metadata"] = {
        **source_metadata,
        "source_version": source_metadata.get("version"),
        "version": REJUDGE_VERSION,
        "experiment_version": REJUDGE_VERSION,
        "rejudge_complete": False,
        "rejudge_started_at": _utc_now(),
        "rejudge_completed_at": None,
        "source_checkpoint": str(source_path.resolve()),
        "source_checkpoint_sha256": source_hash,
        "response_judging_policy": "full_stored_response_no_character_truncation",
        "pairwise_presentation_policy": "both_ab_and_ba_orientations",
        "prefix_judgments_preserved": True,
        "rejudge_protocol": dict(protocol),
        "rejudge_protocol_sha256": protocol["protocol_sha256"],
        "rejudge_cost": {"scalar": 0.0, "pairwise": 0.0, "total": 0.0},
    }
    return output


def _refresh_metadata(checkpoint: Dict[str, Any]) -> None:
    scalar_cost = sum(
        float(row.get("full_response_judgment", {}).get("judge_cost_usd", 0))
        for row in checkpoint.get("results", [])
    )
    pairwise_cost = sum(
        float(row.get("judge_cost_usd", 0))
        for row in checkpoint.get("pairwise_presentations", [])
    )
    source_cost = float(
        checkpoint.get("source_metadata", {}).get("total_cost", 0)
    )
    models = sorted(
        {
            str(model)
            for model in [
                *(
                    row.get("full_response_judgment", {}).get(
                        "judge_model_returned"
                    )
                    for row in checkpoint.get("results", [])
                ),
                *(
                    row.get("judge_model_returned")
                    for row in checkpoint.get("pairwise_presentations", [])
                ),
            ]
            if model
        }
    )
    checkpoint["metadata"]["rejudge_cost"] = {
        "scalar": round(scalar_cost, 9),
        "pairwise": round(pairwise_cost, 9),
        "total": round(scalar_cost + pairwise_cost, 9),
    }
    checkpoint["metadata"]["cumulative_cost_usd"] = round(
        source_cost + scalar_cost + pairwise_cost, 9
    )
    checkpoint["metadata"]["rejudge_models_returned"] = models
    fingerprints = sorted(
        {
            str(fingerprint)
            for fingerprint in [
                *(
                    row.get("full_response_judgment", {}).get(
                        "system_fingerprint"
                    )
                    for row in checkpoint.get("results", [])
                ),
                *(
                    row.get("system_fingerprint")
                    for row in checkpoint.get("pairwise_presentations", [])
                ),
            ]
            if fingerprint
        }
    )
    checkpoint["metadata"]["judge_system_fingerprints"] = fingerprints


class FullResponseRejudger:
    """DeepSeek-only re-judger for immutable stored agent responses."""

    def __init__(self, concurrency: int = 4, retries: int = 2):
        v5.load_environment_file()
        self.runner = v5.CorrectedExperimentRunner(dry_run=True)
        self.client = self.runner.judge_client
        self.model = JUDGE_MODEL
        self.semaphore = asyncio.Semaphore(concurrency)
        self.retries = retries

    def criteria_by_node(self, rows: Iterable[Mapping[str, Any]]) -> Dict[str, str]:
        nodes = sorted({str(row["graph_node"]) for row in rows})
        return {node: self.runner._get_judge_criteria(node) for node in nodes}

    async def _request(self, prompt: str, max_tokens: int) -> Any:
        prompt_bytes = len(prompt.encode("utf-8"))
        if prompt_bytes > MAX_RENDERED_PROMPT_BYTES:
            raise ValueError(
                f"Rendered prompt is {prompt_bytes} bytes, above the fail-closed "
                f"limit of {MAX_RENDERED_PROMPT_BYTES}; no truncation permitted"
            )
        async with self.semaphore:
            return await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                max_tokens=max_tokens,
                response_format={"type": "json_object"},
                extra_body={"thinking": {"type": THINKING_MODE}},
            )

    @staticmethod
    def _attempt_record(
        response: Any,
        content: str,
        parse_error: str | None,
        attempt_number: int,
    ) -> Dict[str, Any]:
        usage = _usage_snapshot(response)
        choice = response.choices[0]
        return {
            "attempt": attempt_number,
            "request_error": None,
            "judge_parse_error": parse_error,
            "judge_model_returned": getattr(response, "model", None),
            "judge_response_id": getattr(response, "id", None),
            "system_fingerprint": getattr(response, "system_fingerprint", None),
            "created": getattr(response, "created", None),
            "finish_reason": getattr(choice, "finish_reason", None),
            "usage": usage,
            "cost_usd": _current_judge_cost(usage),
            "raw_content": content,
            "raw_content_sha256": _sha256_text(content),
            "completed_at": _utc_now(),
        }

    @staticmethod
    def _error_attempt(error: Exception, attempt_number: int) -> Dict[str, Any]:
        return {
            "attempt": attempt_number,
            "request_error": str(error),
            "judge_parse_error": None,
            "judge_model_returned": None,
            "judge_response_id": None,
            "system_fingerprint": None,
            "created": None,
            "finish_reason": None,
            "usage": {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "prompt_cache_hit_tokens": 0,
                "prompt_cache_miss_tokens": 0,
            },
            "cost_usd": 0.0,
            "raw_content": "",
            "raw_content_sha256": _sha256_text(""),
            "completed_at": _utc_now(),
        }

    @staticmethod
    def _attempt_totals(attempts: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
        prompt_tokens = sum(
            int(attempt["usage"]["prompt_tokens"]) for attempt in attempts
        )
        completion_tokens = sum(
            int(attempt["usage"]["completion_tokens"]) for attempt in attempts
        )
        return {
            "judge_input_tokens": prompt_tokens,
            "judge_output_tokens": completion_tokens,
            "judge_cost_usd": sum(float(attempt["cost_usd"]) for attempt in attempts),
        }

    async def scalar(self, row: Mapping[str, Any]) -> Dict[str, Any]:
        task_id = str(row["task_id"])
        response_text = str(row["response"])
        prompt = build_scalar_prompt(
            v4.TASK_PROMPTS[task_id],
            self.runner._get_judge_criteria(str(row["graph_node"])),
            response_text,
        )
        attempts: list[Dict[str, Any]] = []
        parsed = v5.JudgmentParse(None, "", "no successful attempt")
        for attempt_number in range(1, self.retries + 2):
            try:
                response = await self._request(prompt, SCALAR_MAX_TOKENS)
                content = response.choices[0].message.content or ""
                parsed = v5.parse_multidim_judgment(content)
                attempts.append(
                    self._attempt_record(
                        response, content, parsed.parse_error, attempt_number
                    )
                )
                if parsed.parse_error is None:
                    break
            except Exception as error:  # pragma: no cover - network behavior
                attempts.append(self._error_attempt(error, attempt_number))
                parsed = v5.JudgmentParse(None, "", str(error))
            if attempt_number <= self.retries:
                await asyncio.sleep(2 ** (attempt_number - 1))
        final = attempts[-1]
        totals = self._attempt_totals(attempts)
        return {
            "policy": "full_stored_response_no_character_truncation",
            "truncated": False,
            "response_characters_judged": len(response_text),
            "response_bytes_judged": len(response_text.encode("utf-8")),
            "response_sha256": _sha256_text(response_text),
            "rendered_prompt_characters": len(prompt),
            "rendered_prompt_bytes": len(prompt.encode("utf-8")),
            "rendered_prompt_sha256": _sha256_text(prompt),
            "scores": parsed.scores,
            "reasoning": parsed.reasoning,
            "judge_model_requested": self.model,
            "judge_model_returned": final["judge_model_returned"],
            "judge_response_id": final["judge_response_id"],
            "system_fingerprint": final["system_fingerprint"],
            "created": final["created"],
            "finish_reason": final["finish_reason"],
            **totals,
            "judge_parse_error": parsed.parse_error,
            "attempts": attempts,
            "judged_at": _utc_now(),
        }

    async def pairwise(self, job: Mapping[str, Any]) -> Dict[str, Any]:
        response_a = str(job["response_a"])
        response_b = str(job["response_b"])
        prompt = v4.PAIRWISE_JUDGE_PROMPT.format(
            task_description=v4.TASK_PROMPTS[str(job["task_id"])],
            domain_criteria=self.runner._get_judge_criteria(
                str(job["graph_node"])
            ),
            response_a=response_a,
            response_b=response_b,
        )
        attempts: list[Dict[str, Any]] = []
        parsed: Dict[str, str] | None = None
        parse_error: str | None = "no successful attempt"
        for attempt_number in range(1, self.retries + 2):
            try:
                response = await self._request(prompt, PAIRWISE_MAX_TOKENS)
                content = response.choices[0].message.content or ""
                parsed, parse_error = parse_pairwise_judgment(content)
                attempts.append(
                    self._attempt_record(
                        response, content, parse_error, attempt_number
                    )
                )
                if parse_error is None:
                    break
            except Exception as error:  # pragma: no cover - network behavior
                attempts.append(self._error_attempt(error, attempt_number))
                parsed, parse_error = None, str(error)
            if attempt_number <= self.retries:
                await asyncio.sleep(2 ** (attempt_number - 1))
        final = attempts[-1]
        totals = self._attempt_totals(attempts)
        raw_winner = parsed["winner"] if parsed else "error"
        winner = normalize_pairwise_winner(
            raw_winner,
            str(job["orientation"]),
            str(job["condition_a"]),
            str(job["condition_b"]),
        )
        identity = {
            key: job[key]
            for key in (
                "pairwise_key",
                "logical_pair_key",
                "task_id",
                "run_id",
                "condition_a",
                "condition_b",
                "orientation",
                "presented_condition_a",
                "presented_condition_b",
            )
        }
        return identity | {
            "winner": winner,
            "raw_winner": raw_winner,
            "reason": parsed["reason"] if parsed else "",
            "confidence": parsed["confidence"] if parsed else None,
            "policy": "full_stored_response_no_character_truncation",
            "truncated": False,
            "response_a_characters": len(response_a),
            "response_b_characters": len(response_b),
            "response_a_bytes": len(response_a.encode("utf-8")),
            "response_b_bytes": len(response_b.encode("utf-8")),
            "response_a_sha256": _sha256_text(response_a),
            "response_b_sha256": _sha256_text(response_b),
            "rendered_prompt_characters": len(prompt),
            "rendered_prompt_bytes": len(prompt.encode("utf-8")),
            "rendered_prompt_sha256": _sha256_text(prompt),
            "judge_model_requested": self.model,
            "judge_model_returned": final["judge_model_returned"],
            "judge_response_id": final["judge_response_id"],
            "system_fingerprint": final["system_fingerprint"],
            "created": final["created"],
            "finish_reason": final["finish_reason"],
            **totals,
            "judge_parse_error": parse_error,
            "attempts": attempts,
            "judged_at": _utc_now(),
        }


def _apply_scalar(row: Dict[str, Any], judgment: Mapping[str, Any]) -> None:
    merged = _merge_attempt_history(row.get("full_response_judgment"), judgment)
    row["full_response_judgment"] = merged
    scores = merged.get("scores")
    if scores is None:
        row["dim_completeness"] = None
        row["dim_terminology"] = None
        row["dim_structure"] = None
        row["quality_score"] = None
    else:
        row["dim_completeness"] = scores["completeness"]
        row["dim_terminology"] = scores["terminology"]
        row["dim_structure"] = scores["structure"]
        row["quality_score"] = round(
            sum(float(scores[name]) for name in ("completeness", "terminology", "structure"))
            / 3.0,
            2,
        )
    row["dim_reasoning"] = merged.get("reasoning", "")
    for field in (
        "judge_model_requested",
        "judge_model_returned",
        "judge_response_id",
        "judge_input_tokens",
        "judge_output_tokens",
        "judge_cost_usd",
        "judge_parse_error",
    ):
        row[field] = merged.get(field)
    row["cost_usd"] = float(row.get("agent_cost_usd", 0)) + float(
        merged.get("judge_cost_usd", 0)
    )


def _merge_attempt_history(
    existing: Mapping[str, Any] | None,
    new_result: Mapping[str, Any],
) -> Dict[str, Any]:
    merged = dict(new_result)
    attempts = [
        dict(attempt) for attempt in (existing or {}).get("attempts", [])
    ] + [dict(attempt) for attempt in new_result.get("attempts", [])]
    for number, attempt in enumerate(attempts, start=1):
        attempt["attempt"] = number
    merged["attempts"] = attempts
    if attempts:
        totals = FullResponseRejudger._attempt_totals(attempts)
        merged.update(totals)
    return merged


def _assert_no_judge_drift(checkpoint: Mapping[str, Any]) -> None:
    rows = list(checkpoint.get("results", []))
    presentations = list(checkpoint.get("pairwise_presentations", []))
    models = {
        str(model)
        for model in [
            *(
                row.get("full_response_judgment", {}).get("judge_model_returned")
                for row in rows
            ),
            *(row.get("judge_model_returned") for row in presentations),
        ]
        if model
    }
    if models and models != {JUDGE_MODEL}:
        raise RuntimeError(f"Judge model drift detected: {sorted(models)}")
    fingerprints = {
        str(fingerprint)
        for fingerprint in [
            *(
                row.get("full_response_judgment", {}).get("system_fingerprint")
                for row in rows
            ),
            *(row.get("system_fingerprint") for row in presentations),
        ]
        if fingerprint
    }
    if len(fingerprints) > 1:
        raise RuntimeError(
            f"Judge system-fingerprint drift detected: {sorted(fingerprints)}"
        )


async def _scalar_job(
    rejudger: FullResponseRejudger, row: Dict[str, Any]
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    return row, await rejudger.scalar(row)


async def _pairwise_job(
    rejudger: FullResponseRejudger, job: Mapping[str, Any]
) -> tuple[Mapping[str, Any], Dict[str, Any]]:
    return job, await rejudger.pairwise(job)


async def run_rejudgment(args: argparse.Namespace) -> Path:
    source_hash = _sha256_file(args.input)
    source = json.loads(args.input.read_text(encoding="utf-8"))
    source_errors = v5.validate_checkpoint(source)
    if source_errors:
        raise SystemExit("Source checkpoint failed validation:\n- " + "\n- ".join(source_errors))
    if len(source.get("results", [])) != 180 or len(source.get("pairwise_results", [])) != 90:
        raise SystemExit("Source checkpoint must contain exactly 180 agent and 90 pairwise rows")
    rejudger = FullResponseRejudger(args.concurrency, args.retries)
    criteria_by_node = rejudger.criteria_by_node(source["results"])
    protocol = build_rejudge_protocol(source, criteria_by_node)
    if args.output.exists():
        checkpoint = json.loads(args.output.read_text(encoding="utf-8"))
        if checkpoint.get("metadata", {}).get("source_checkpoint_sha256") != source_hash:
            raise SystemExit("Refusing resume: output source hash differs from input")
        if checkpoint.get("metadata", {}).get("rejudge_protocol") != protocol:
            raise SystemExit("Refusing resume: rejudge protocol or script has changed")
        print(f"Resuming checkpoint: {args.output}")
    else:
        checkpoint = initialize_checkpoint(source, args.input, protocol)
        _atomic_write_json(args.output, checkpoint)
        print(f"Initialized checkpoint: {args.output}")

    rows = list(checkpoint["results"])
    pending_rows = [
        row
        for row in rows
        if not row.get("full_response_judgment")
        or row["full_response_judgment"].get("judge_parse_error")
    ]
    if args.limit_scalar is not None:
        pending_rows = pending_rows[: args.limit_scalar]
    print(f"Scalar judgments pending this invocation: {len(pending_rows)}")
    scalar_tasks = [
        asyncio.create_task(_scalar_job(rejudger, row)) for row in pending_rows
    ]
    for completed in asyncio.as_completed(scalar_tasks):
        row, judgment = await completed
        _apply_scalar(row, judgment)
        _refresh_metadata(checkpoint)
        _atomic_write_json(args.output, checkpoint)
        _assert_no_judge_drift(checkpoint)
        print(
            f"scalar {row['run_key']}: score={row.get('quality_score')} "
            f"chars={judgment['response_characters_judged']} "
            f"error={bool(judgment.get('judge_parse_error'))}"
        )

    all_jobs = build_pairwise_jobs(rows)
    presentations = checkpoint.setdefault("pairwise_presentations", [])
    completed_keys = {
        str(result.get("pairwise_key"))
        for result in presentations
        if not result.get("judge_parse_error")
    }
    pending_jobs = [
        job for job in all_jobs if job["pairwise_key"] not in completed_keys
    ]
    if args.limit_pairwise is not None:
        pending_jobs = pending_jobs[: args.limit_pairwise]
    print(f"Pairwise presentations pending this invocation: {len(pending_jobs)}")
    pairwise_tasks = [
        asyncio.create_task(_pairwise_job(rejudger, job)) for job in pending_jobs
    ]
    for completed in asyncio.as_completed(pairwise_tasks):
        job, judgment = await completed
        existing_index = next(
            (
                index
                for index, result in enumerate(presentations)
                if result.get("pairwise_key") == job["pairwise_key"]
            ),
            None,
        )
        if existing_index is None:
            presentations.append(judgment)
        else:
            presentations[existing_index] = _merge_attempt_history(
                presentations[existing_index], judgment
            )
        checkpoint["pairwise_results"] = aggregate_pairwise_presentations(
            presentations
        )
        _refresh_metadata(checkpoint)
        _atomic_write_json(args.output, checkpoint)
        _assert_no_judge_drift(checkpoint)
        print(
            f"pairwise {judgment['pairwise_key']}: "
            f"winner={judgment['winner']} "
            f"error={bool(judgment.get('judge_parse_error'))}"
        )

    expected_pairs = len(all_jobs) // 2
    checkpoint["pairwise_results"] = aggregate_pairwise_presentations(
        presentations
    )
    errors = validate_rejudged_checkpoint(
        checkpoint, expected_pairs, source=source, current_protocol=protocol
    )
    if not errors:
        checkpoint["metadata"]["rejudge_complete"] = True
        checkpoint["metadata"]["rejudge_completed_at"] = _utc_now()
        _refresh_metadata(checkpoint)
        _atomic_write_json(args.output, checkpoint)
        print(
            f"Validated: {len(rows)}/{len(rows)} full scalar judgments and "
            f"{len(presentations)}/{len(all_jobs)} pairwise presentations"
        )
    else:
        checkpoint["metadata"]["rejudge_complete"] = False
        _refresh_metadata(checkpoint)
        _atomic_write_json(args.output, checkpoint)
        print("Checkpoint remains incomplete:")
        for error in errors:
            print(f"- {error}")
    costs = checkpoint["metadata"]["rejudge_cost"]
    print(
        f"Rejudge cost: ${costs['total']:.6f} "
        f"(scalar ${costs['scalar']:.6f}; pairwise ${costs['pairwise']:.6f})"
    )
    return args.output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--limit-scalar", type=int)
    parser.add_argument("--limit-pairwise", type=int)
    parser.add_argument("--validate", action="store_true")
    parser.add_argument(
        "--preflight",
        action="store_true",
        help="Report exact full-response payload sizes without making API calls.",
    )
    parser.add_argument(
        "--acknowledge-external-full-response-transfer",
        action="store_true",
        help=(
            "Required for API calls: confirms that complete stored outputs, not "
            "4,000-character prefixes, may be sent to DeepSeek."
        ),
    )
    args = parser.parse_args()
    if args.concurrency < 1:
        parser.error("--concurrency must be at least 1")
    if args.preflight:
        source = json.loads(args.input.read_text(encoding="utf-8"))
        source_errors = v5.validate_checkpoint(source)
        if source_errors:
            raise SystemExit(
                "Source checkpoint failed validation:\n- "
                + "\n- ".join(source_errors)
            )
        rejudger = FullResponseRejudger(args.concurrency, args.retries)
        summary = preflight_summary(
            source, rejudger.criteria_by_node(source["results"])
        )
        print(json.dumps(summary, indent=2))
        return
    if args.output is None:
        parser.error("--output is required unless --preflight is used")
    if args.validate:
        checkpoint = json.loads(args.output.read_text(encoding="utf-8"))
        source = json.loads(args.input.read_text(encoding="utf-8"))
        rejudger = FullResponseRejudger(args.concurrency, args.retries)
        protocol = build_rejudge_protocol(
            source, rejudger.criteria_by_node(source["results"])
        )
        expected_pairs = len(build_pairwise_jobs(source.get("results", []))) // 2
        errors = validate_rejudged_checkpoint(
            checkpoint,
            expected_pairs,
            source=source,
            current_protocol=protocol,
        )
        if errors:
            raise SystemExit("Validation failed:\n- " + "\n- ".join(errors))
        if checkpoint.get("metadata", {}).get("source_checkpoint_sha256") != _sha256_file(args.input):
            raise SystemExit("Validation failed: source checkpoint hash mismatch")
        print(
            f"Validated: {len(checkpoint['results'])} full scalar judgments and "
            f"{len(checkpoint['pairwise_results'])} logical pairs / "
            f"{len(checkpoint['pairwise_presentations'])} presentations"
        )
        return
    if not args.acknowledge_external_full_response_transfer:
        parser.error(
            "--acknowledge-external-full-response-transfer is required because "
            "this command sends complete stored outputs to DeepSeek"
        )
    asyncio.run(run_rejudgment(args))


if __name__ == "__main__":
    main()
