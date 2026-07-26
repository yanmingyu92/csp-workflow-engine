#!/usr/bin/env python3
"""Re-judge the stored original experiment under the locked v5 protocol.

This script never calls the generation model. It preserves the original
first-4,000-character judgments, scores all 90 complete stored responses,
and evaluates the two original pairwise contrasts in both AB and BA order.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import sys
from typing import Any, Dict, Iterable, Mapping

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from experiments import rejudge_v5_full_outputs as full
from experiments import run_experiment_v4_claude as v4
from experiments import run_experiment_v5_corrected as v5


REJUDGE_VERSION = "original-full-response-bidirectional-1"
ORIGINAL_CONDITIONS: tuple[str, ...] = (
    "agent_only",
    "agent_framework",
    "agent_framework_distill",
)
ORIGINAL_PAIRWISE_CONTRASTS: tuple[tuple[str, str], ...] = (
    ("agent_framework", "agent_only"),
    ("agent_framework_distill", "agent_only"),
)
PRIMARY_DECISION_RULE = {
    "contrast": "agent_framework_minus_agent_only",
    "outcome": "quality_score",
    "inferential_unit": "task",
    "replicate_handling": "average_three_replicates_within_task_condition",
    "interval": "10000-resample paired task bootstrap 95% percentile CI",
    "test": "exact two-sided sign-flip over paired task differences",
    "retained_secondary_evidence": (
        "mean_difference > 0 AND CI lower bound > 0 AND exact P < .05"
    ),
    "directional_but_uncertain": (
        "mean_difference > 0 but either CI includes 0 or exact P >= .05"
    ),
    "not_retained": "mean_difference <= 0",
    "manuscript_policy": (
        "The corrective v5 experiment remains primary regardless of outcome."
    ),
}


def stable_run_key(task_id: str, condition: str, run_id: int) -> str:
    return f"{task_id}::{condition}::{run_id}"


def normalize_original_source(source: Mapping[str, Any]) -> Dict[str, Any]:
    """Return a detached copy with stable keys and explicit design metadata."""
    normalized = json.loads(json.dumps(source))
    rows = normalized.get("results", [])
    for row in rows:
        row["run_id"] = int(row.get("run_id", 0))
        row["run_key"] = stable_run_key(
            str(row["task_id"]), str(row["condition"]), row["run_id"]
        )
    tasks = sorted({str(row["task_id"]) for row in rows})
    conditions_present = {str(row["condition"]) for row in rows}
    normalized["metadata"] = {
        **normalized.get("metadata", {}),
        "tasks": tasks,
        "conditions": [
            condition
            for condition in ORIGINAL_CONDITIONS
            if condition in conditions_present
        ],
        "runs": len({int(row["run_id"]) for row in rows}),
    }
    return normalized


def validate_original_source(source: Mapping[str, Any]) -> list[str]:
    """Validate the immutable 10-task x 3-arm x 3-run source checkpoint."""
    errors: list[str] = []
    rows = list(source.get("results", []))
    metadata = source.get("metadata", {})
    tasks = list(metadata.get("tasks", []))
    conditions = list(metadata.get("conditions", []))
    runs = int(metadata.get("runs", 0))
    expected = len(tasks) * len(conditions) * runs
    if conditions != list(ORIGINAL_CONDITIONS):
        errors.append(f"unexpected conditions: {conditions}")
    if len(tasks) != 10 or runs != 3:
        errors.append(f"unexpected design: {len(tasks)} tasks x {runs} runs")
    if len(rows) != expected:
        errors.append(f"result cardinality {len(rows)} != {expected}")
    keys = [str(row.get("run_key")) for row in rows]
    if len(keys) != len(set(keys)):
        errors.append("duplicate run keys")
    index = {
        (
            str(row.get("task_id")),
            str(row.get("condition")),
            int(row.get("run_id", -1)),
        )
        for row in rows
    }
    expected_index = {
        (task, condition, run_id)
        for task in tasks
        for condition in conditions
        for run_id in range(runs)
    }
    if index != expected_index:
        errors.append("source does not contain every matched task-condition-run cell")
    if any(not str(row.get("response", "")).strip() for row in rows):
        errors.append("at least one stored response is empty")
    if any(bool(row.get("is_error_response")) for row in rows):
        errors.append("at least one original agent response is marked as an error")
    required_scores = (
        "quality_score",
        "dim_completeness",
        "dim_terminology",
        "dim_structure",
    )
    if any(row.get(field) is None for row in rows for field in required_scores):
        errors.append("at least one original prefix judgment is incomplete")
    return errors


def build_pairwise_jobs(
    rows: Iterable[Mapping[str, Any]],
) -> list[Dict[str, Any]]:
    return full.build_pairwise_jobs(rows, ORIGINAL_PAIRWISE_CONTRASTS)


def build_protocol(
    source: Mapping[str, Any],
    source_path: Path,
    criteria_by_node: Mapping[str, str],
) -> Dict[str, Any]:
    """Build the immutable protocol used for preflight, resume, and validation."""
    protocol = {
        "version": REJUDGE_VERSION,
        "script_sha256": full._sha256_file(Path(__file__)),
        "source_checkpoint_sha256": full._sha256_file(source_path),
        "dependency_sha256": {
            "run_experiment_v4_claude": full._sha256_file(Path(v4.__file__)),
            "run_experiment_v5_corrected": full._sha256_file(Path(v5.__file__)),
            "rejudge_v5_full_outputs": full._sha256_file(Path(full.__file__)),
        },
        "judge_model_requested": full.JUDGE_MODEL,
        "thinking_mode": full.THINKING_MODE,
        "temperature": 0.0,
        "response_format": "json_object",
        "scalar_max_tokens": full.SCALAR_MAX_TOKENS,
        "pairwise_max_tokens": full.PAIRWISE_MAX_TOKENS,
        "max_rendered_prompt_bytes": full.MAX_RENDERED_PROMPT_BYTES,
        "scalar_prompt_template_sha256": full._sha256_text(
            v4.MULTI_DIM_JUDGE_PROMPT
        ),
        "pairwise_prompt_template_sha256": full._sha256_text(
            v4.PAIRWISE_JUDGE_PROMPT
        ),
        "pairwise_contrasts": [list(item) for item in ORIGINAL_PAIRWISE_CONTRASTS],
        "domain_criteria_by_node": dict(sorted(criteria_by_node.items())),
        "task_prompt_sha256": {
            task_id: full._sha256_text(v4.TASK_PROMPTS[task_id])
            for task_id in source["metadata"]["tasks"]
        },
        "primary_decision_rule": PRIMARY_DECISION_RULE,
        "pricing_usd_per_million": full.PRICING_USD_PER_MILLION,
        "pricing_as_of": full.PRICING_AS_OF,
        "pricing_source": full.PRICING_SOURCE,
    }
    protocol["protocol_sha256"] = full._canonical_sha256(protocol)
    return protocol


def _prefix_judgment(
    row: Mapping[str, Any], judge_model_requested: str | None
) -> Dict[str, Any]:
    return {
        "policy": "first_4000_characters",
        "response_characters_judged": min(4000, len(str(row["response"]))),
        "dim_completeness": row.get("dim_completeness"),
        "dim_terminology": row.get("dim_terminology"),
        "dim_structure": row.get("dim_structure"),
        "dim_reasoning": row.get("dim_reasoning"),
        "quality_score": row.get("quality_score"),
        "judge_model_requested": judge_model_requested,
    }


def initialize_checkpoint(
    source: Mapping[str, Any],
    source_path: Path,
    protocol: Mapping[str, Any],
) -> Dict[str, Any]:
    checkpoint = json.loads(json.dumps(source))
    source_judge = source.get("metadata", {}).get("judge")
    for row in checkpoint["results"]:
        row["prefix_judgment"] = _prefix_judgment(row, source_judge)
    checkpoint["prefix_pairwise_results"] = checkpoint.get("pairwise_results", [])
    checkpoint["pairwise_results"] = []
    checkpoint["pairwise_presentations"] = []
    checkpoint["source_metadata"] = dict(source.get("metadata", {}))
    checkpoint["metadata"] = {
        **source.get("metadata", {}),
        "source_version": source.get("metadata", {}).get("version"),
        "version": REJUDGE_VERSION,
        "experiment_version": REJUDGE_VERSION,
        "rejudge_complete": False,
        "rejudge_started_at": full._utc_now(),
        "rejudge_completed_at": None,
        "source_checkpoint": str(source_path.resolve()),
        "source_checkpoint_sha256": full._sha256_file(source_path),
        "response_judging_policy": (
            "full_stored_response_no_character_truncation"
        ),
        "pairwise_presentation_policy": "both_ab_and_ba_orientations",
        "prefix_judgments_preserved": True,
        "rejudge_protocol": dict(protocol),
        "rejudge_protocol_sha256": protocol["protocol_sha256"],
        "rejudge_cost": {"scalar": 0.0, "pairwise": 0.0, "total": 0.0},
    }
    return checkpoint


def preflight_summary(
    source: Mapping[str, Any], criteria_by_node: Mapping[str, str]
) -> Dict[str, Any]:
    scalar_prompts = []
    for row in source["results"]:
        prompt = full.build_scalar_prompt(
            v4.TASK_PROMPTS[str(row["task_id"])],
            criteria_by_node[str(row["graph_node"])],
            str(row["response"]),
        )
        scalar_prompts.append(
            {
                "key": row["run_key"],
                "prompt_bytes": len(prompt.encode("utf-8")),
                "response_bytes": len(str(row["response"]).encode("utf-8")),
            }
        )
    pairwise_prompts = []
    for job in build_pairwise_jobs(source["results"]):
        prompt = v4.PAIRWISE_JUDGE_PROMPT.format(
            task_description=v4.TASK_PROMPTS[str(job["task_id"])],
            domain_criteria=criteria_by_node[str(job["graph_node"])],
            response_a=job["response_a"],
            response_b=job["response_b"],
        )
        pairwise_prompts.append(
            {
                "key": job["pairwise_key"],
                "prompt_bytes": len(prompt.encode("utf-8")),
                "response_bytes": len(job["response_a"].encode("utf-8"))
                + len(job["response_b"].encode("utf-8")),
            }
        )
    all_prompts = scalar_prompts + pairwise_prompts
    largest_scalar = max(scalar_prompts, key=lambda item: item["prompt_bytes"])
    largest_pairwise = max(
        pairwise_prompts, key=lambda item: item["prompt_bytes"]
    )
    return {
        "source_checkpoint_sha256": full._sha256_file(
            Path(source["metadata"]["source_path"])
        )
        if source["metadata"].get("source_path")
        else None,
        "scalar_calls": len(scalar_prompts),
        "logical_pairs": len(pairwise_prompts) // 2,
        "pairwise_presentation_calls": len(pairwise_prompts),
        "total_calls": len(all_prompts),
        "total_rendered_prompt_bytes": sum(
            item["prompt_bytes"] for item in all_prompts
        ),
        "maximum_scalar": largest_scalar,
        "maximum_pairwise": largest_pairwise,
        "fail_closed_prompt_byte_limit": full.MAX_RENDERED_PROMPT_BYTES,
        "all_prompts_within_limit": all(
            item["prompt_bytes"] <= full.MAX_RENDERED_PROMPT_BYTES
            for item in all_prompts
        ),
    }


def _refresh_metadata(checkpoint: Dict[str, Any]) -> None:
    full._refresh_metadata(checkpoint)


def validate_rejudged_checkpoint(
    checkpoint: Mapping[str, Any],
    source: Mapping[str, Any],
    protocol: Mapping[str, Any],
) -> list[str]:
    expected_pairs = len(build_pairwise_jobs(source["results"])) // 2
    errors = full.validate_rejudged_checkpoint(
        checkpoint,
        expected_pairs=expected_pairs,
        source=None,
        current_protocol=protocol,
    )
    if checkpoint.get("metadata", {}).get("source_checkpoint_sha256") != (
        protocol["source_checkpoint_sha256"]
    ):
        errors.append("source checkpoint hash mismatch")
    source_index = {
        str(row["run_key"]): row for row in source.get("results", [])
    }
    if {str(row.get("run_key")) for row in checkpoint.get("results", [])} != set(
        source_index
    ):
        errors.append("rejudged scalar run keys differ from source checkpoint")
    for row in checkpoint.get("results", []):
        original = source_index.get(str(row.get("run_key")))
        judgment = row.get("full_response_judgment", {})
        if original is None:
            errors.append(f"unexpected scalar row: {row.get('run_key')}")
            continue
        if not judgment:
            continue
        response = str(original["response"])
        if judgment.get("response_sha256") != full._sha256_text(response):
            errors.append(f"scalar response hash mismatch: {row.get('run_key')}")
        if judgment.get("response_characters_judged") != len(response):
            errors.append(f"scalar response length mismatch: {row.get('run_key')}")
        if judgment.get("response_bytes_judged") != len(response.encode("utf-8")):
            errors.append(f"scalar response byte count mismatch: {row.get('run_key')}")
        criteria = protocol["domain_criteria_by_node"][str(row["graph_node"])]
        prompt = full.build_scalar_prompt(
            v4.TASK_PROMPTS[str(row["task_id"])], criteria, response
        )
        if judgment.get("rendered_prompt_sha256") != full._sha256_text(prompt):
            errors.append(f"scalar prompt hash mismatch: {row.get('run_key')}")
    expected_pairwise = {
        str(job["pairwise_key"]): job
        for job in build_pairwise_jobs(source.get("results", []))
    }
    presentations = list(checkpoint.get("pairwise_presentations", []))
    unexpected_pairwise = {
        str(row.get("pairwise_key")) for row in presentations
    } - set(expected_pairwise)
    if unexpected_pairwise:
        errors.append(
            "pairwise presentations contain source-inconsistent keys: "
            f"{sorted(unexpected_pairwise)}"
        )
    for result in presentations:
        job = expected_pairwise.get(str(result.get("pairwise_key")))
        if job is None:
            continue
        response_a = str(job["response_a"])
        response_b = str(job["response_b"])
        for side, response in (("a", response_a), ("b", response_b)):
            if result.get(f"response_{side}_sha256") != full._sha256_text(response):
                errors.append(
                    f"pairwise response {side} hash mismatch: "
                    f"{result.get('pairwise_key')}"
                )
            if result.get(f"response_{side}_characters") != len(response):
                errors.append(
                    f"pairwise response {side} length mismatch: "
                    f"{result.get('pairwise_key')}"
                )
            if result.get(f"response_{side}_bytes") != len(
                response.encode("utf-8")
            ):
                errors.append(
                    f"pairwise response {side} byte mismatch: "
                    f"{result.get('pairwise_key')}"
                )
        criteria = protocol["domain_criteria_by_node"][str(job["graph_node"])]
        prompt = v4.PAIRWISE_JUDGE_PROMPT.format(
            task_description=v4.TASK_PROMPTS[str(job["task_id"])],
            domain_criteria=criteria,
            response_a=response_a,
            response_b=response_b,
        )
        if result.get("rendered_prompt_sha256") != full._sha256_text(prompt):
            errors.append(
                f"pairwise prompt hash mismatch: {result.get('pairwise_key')}"
            )
    return errors


async def run_rejudgment(args: argparse.Namespace) -> Path:
    raw_source = json.loads(args.input.read_text(encoding="utf-8"))
    source = normalize_original_source(raw_source)
    source_errors = validate_original_source(source)
    if source_errors:
        raise SystemExit("Source validation failed:\n- " + "\n- ".join(source_errors))
    rejudger = full.FullResponseRejudger(args.concurrency, args.retries)
    criteria = rejudger.criteria_by_node(source["results"])
    protocol = build_protocol(source, args.input, criteria)
    if args.output.exists():
        checkpoint = json.loads(args.output.read_text(encoding="utf-8"))
        if checkpoint.get("metadata", {}).get("rejudge_protocol") != protocol:
            raise SystemExit("Refusing resume: locked protocol has changed")
        print(f"Resuming checkpoint: {args.output}")
    else:
        checkpoint = initialize_checkpoint(source, args.input, protocol)
        full._atomic_write_json(args.output, checkpoint)
        print(f"Initialized checkpoint: {args.output}")

    pending_rows = [
        row
        for row in checkpoint["results"]
        if not row.get("full_response_judgment")
        or row["full_response_judgment"].get("judge_parse_error")
    ]
    if args.limit_scalar is not None:
        pending_rows = pending_rows[: args.limit_scalar]
    print(f"Scalar judgments pending this invocation: {len(pending_rows)}")
    scalar_tasks = [
        asyncio.create_task(full._scalar_job(rejudger, row))
        for row in pending_rows
    ]
    for completed in asyncio.as_completed(scalar_tasks):
        row, judgment = await completed
        full._apply_scalar(row, judgment)
        _refresh_metadata(checkpoint)
        full._atomic_write_json(args.output, checkpoint)
        full._assert_no_judge_drift(checkpoint)
        print(
            f"scalar {row['run_key']}: score={row.get('quality_score')} "
            f"chars={judgment['response_characters_judged']} "
            f"error={bool(judgment.get('judge_parse_error'))}"
        )

    jobs = build_pairwise_jobs(checkpoint["results"])
    presentations = checkpoint.setdefault("pairwise_presentations", [])
    completed_keys = {
        str(row["pairwise_key"])
        for row in presentations
        if not row.get("judge_parse_error")
    }
    pending_jobs = [
        job for job in jobs if job["pairwise_key"] not in completed_keys
    ]
    if args.limit_pairwise is not None:
        pending_jobs = pending_jobs[: args.limit_pairwise]
    print(f"Pairwise presentations pending this invocation: {len(pending_jobs)}")
    pairwise_tasks = [
        asyncio.create_task(full._pairwise_job(rejudger, job))
        for job in pending_jobs
    ]
    for completed in asyncio.as_completed(pairwise_tasks):
        job, judgment = await completed
        existing_index = next(
            (
                index
                for index, row in enumerate(presentations)
                if row.get("pairwise_key") == job["pairwise_key"]
            ),
            None,
        )
        if existing_index is None:
            presentations.append(judgment)
        else:
            presentations[existing_index] = full._merge_attempt_history(
                presentations[existing_index], judgment
            )
        checkpoint["pairwise_results"] = full.aggregate_pairwise_presentations(
            presentations
        )
        _refresh_metadata(checkpoint)
        full._atomic_write_json(args.output, checkpoint)
        full._assert_no_judge_drift(checkpoint)
        print(
            f"pairwise {job['pairwise_key']}: winner={judgment['winner']} "
            f"error={bool(judgment.get('judge_parse_error'))}"
        )

    checkpoint["pairwise_results"] = full.aggregate_pairwise_presentations(
        presentations
    )
    errors = validate_rejudged_checkpoint(
        checkpoint, source=source, protocol=protocol
    )
    checkpoint["metadata"]["rejudge_complete"] = not errors
    if not errors:
        checkpoint["metadata"]["rejudge_completed_at"] = full._utc_now()
    _refresh_metadata(checkpoint)
    full._atomic_write_json(args.output, checkpoint)
    if errors:
        print("Checkpoint remains incomplete:")
        for error in errors:
            print(f"- {error}")
    else:
        print(
            f"Validated: {len(checkpoint['results'])} full scalar judgments and "
            f"{len(checkpoint['pairwise_results'])} logical pairs / "
            f"{len(presentations)} presentations"
        )
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
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--validate", action="store_true")
    parser.add_argument(
        "--acknowledge-external-full-response-transfer",
        action="store_true",
    )
    args = parser.parse_args()
    raw_source = json.loads(args.input.read_text(encoding="utf-8"))
    source = normalize_original_source(raw_source)
    source["metadata"]["source_path"] = str(args.input)
    errors = validate_original_source(source)
    if errors:
        raise SystemExit("Source validation failed:\n- " + "\n- ".join(errors))
    rejudger = full.FullResponseRejudger(args.concurrency, args.retries)
    criteria = rejudger.criteria_by_node(source["results"])
    protocol = build_protocol(source, args.input, criteria)
    if args.preflight:
        print(json.dumps(preflight_summary(source, criteria), indent=2))
        print(json.dumps({"locked_decision_rule": PRIMARY_DECISION_RULE}, indent=2))
        return
    if args.output is None:
        parser.error("--output is required unless --preflight is used")
    if args.validate:
        checkpoint = json.loads(args.output.read_text(encoding="utf-8"))
        validation_errors = validate_rejudged_checkpoint(
            checkpoint, source, protocol
        )
        if validation_errors:
            raise SystemExit(
                "Validation failed:\n- " + "\n- ".join(validation_errors)
            )
        print(
            f"Validated: {len(checkpoint['results'])} full scalar judgments and "
            f"{len(checkpoint['pairwise_results'])} logical pairs / "
            f"{len(checkpoint['pairwise_presentations'])} presentations"
        )
        return
    if not args.acknowledge_external_full_response_transfer:
        parser.error(
            "--acknowledge-external-full-response-transfer is required because "
            "this command sends complete stored original outputs to DeepSeek"
        )
    asyncio.run(run_rejudgment(args))


if __name__ == "__main__":
    main()
