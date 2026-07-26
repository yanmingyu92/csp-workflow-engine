from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from experiments.run_experiment_v7_routing_sensitive import (
    V7_ARMS,
    atomic_json_write,
    build_transmitted_prompt,
    normalize_provider_usage,
    parse_claude_envelope,
    repository_relative_path,
    resolve_judge_model,
    stable_run_key,
    validate_generation_checkpoint,
    validate_resume_configuration,
)
from experiments.v7_routing import canonical_token_count


def _metadata() -> dict:
    return {
        "version": "v7-routing-sensitive-generation-1",
        "seed": 20260725,
        "tasks": ["heldout-01"],
        "arms": list(V7_ARMS),
        "runs": 3,
        "source_hashes": {"runner": "a" * 64},
        "freeze_sha256": "b" * 64,
        "sealed_quality_until_formal_complete": True,
    }


def _row(arm: str, run_id: int) -> dict:
    response = '{"answer":{"value":"x"},"evidence_ids":[]}'
    return {
        "run_key": stable_run_key("heldout-01", arm, run_id),
        "task_id": "heldout-01",
        "arm": arm,
        "run_id": run_id,
        "response": response,
        "response_sha256": __import__("hashlib").sha256(
            response.encode("utf-8")
        ).hexdigest(),
        "manifest_sha256": "c" * 64,
        "serialized_prompt_characters": 100,
        "serialized_prompt_bytes": 100,
        "canonical_prompt_tokens": 25,
        "provider_usage": {
            "input_tokens": 25,
            "output_tokens": 10,
            "cache_read_tokens": 0,
            "cache_creation_tokens": 0,
            "raw_usage_sha256": "d" * 64,
        },
        "generation_attempts": [
            {
                "attempt": 1,
                "status": "success",
                "response_sha256": __import__("hashlib").sha256(
                    response.encode("utf-8")
                ).hexdigest(),
            }
        ],
        "is_error_response": False,
    }


def test_run_key_and_arm_order_are_locked():
    assert V7_ARMS == (
        "graph_bm25_chunk_optimized",
        "full_corpus_bm25_token_matched",
        "random_token_matched",
        "flat_8000",
    )
    assert stable_run_key("heldout-01", V7_ARMS[0], 2) == (
        "heldout-01::graph_bm25_chunk_optimized::2"
    )


def test_checkpoint_requires_complete_usage_and_prompt_accounting():
    checkpoint = {"metadata": _metadata(), "results": [_row(V7_ARMS[0], 0)]}
    assert validate_generation_checkpoint(
        checkpoint, allow_partial=True
    ) == []

    for field in (
        "input_tokens",
        "output_tokens",
        "cache_read_tokens",
        "cache_creation_tokens",
    ):
        broken = copy.deepcopy(checkpoint)
        del broken["results"][0]["provider_usage"][field]
        assert any(
            field in error
            for error in validate_generation_checkpoint(
                broken, allow_partial=True
            )
        )

    broken = copy.deepcopy(checkpoint)
    del broken["results"][0]["serialized_prompt_bytes"]
    assert any(
        "serialized_prompt_bytes" in error
        for error in validate_generation_checkpoint(
            broken, allow_partial=True
        )
    )


def test_checkpoint_retains_all_attempts_and_never_silently_substitutes_scores():
    row = _row(V7_ARMS[0], 0)
    row["generation_attempts"].insert(
        0,
        {
            "attempt": 1,
            "status": "transport_error",
            "response_sha256": None,
        },
    )
    row["generation_attempts"][1]["attempt"] = 2
    checkpoint = {"metadata": _metadata(), "results": [row]}

    assert validate_generation_checkpoint(
        checkpoint, allow_partial=True
    ) == []

    row["generation_attempts"] = [row["generation_attempts"][-1]]
    row["generation_attempts"][0]["attempt"] = 2
    errors = validate_generation_checkpoint(checkpoint, allow_partial=True)
    assert any("attempt history" in error for error in errors)


def test_resume_fails_closed_on_freeze_or_source_hash_mismatch():
    checkpoint = {"metadata": _metadata(), "results": []}
    assert validate_resume_configuration(
        checkpoint,
        expected_metadata=_metadata(),
    ) == []

    changed = copy.deepcopy(_metadata())
    changed["freeze_sha256"] = "e" * 64
    errors = validate_resume_configuration(
        checkpoint,
        expected_metadata=changed,
    )
    assert any("freeze_sha256" in error for error in errors)


def test_atomic_checkpoint_write_is_parseable(tmp_path: Path):
    path = tmp_path / "checkpoint.json"
    payload = {"metadata": _metadata(), "results": []}

    atomic_json_write(path, payload)

    assert json.loads(path.read_text(encoding="utf-8")) == payload
    assert not path.with_suffix(".json.tmp").exists()


def test_duplicate_or_out_of_panel_cells_fail_closed():
    row = _row(V7_ARMS[0], 0)
    checkpoint = {"metadata": _metadata(), "results": [row, copy.deepcopy(row)]}
    errors = validate_generation_checkpoint(checkpoint, allow_partial=True)
    assert any("duplicate run_key" in error for error in errors)

    checkpoint = {"metadata": _metadata(), "results": [_row("unknown", 0)]}
    errors = validate_generation_checkpoint(checkpoint, allow_partial=True)
    assert any("out-of-panel" in error for error in errors)


def test_transmitted_prompt_accounting_uses_exact_serialized_payload():
    transmitted = build_transmitted_prompt(
        context="evidence context",
        task_prompt="Return JSON.",
    )

    assert transmitted.startswith("**CRITICAL: ANSWER DIRECTLY")
    assert "[Skills Context]" in transmitted
    assert "[Task]" in transmitted
    assert len(transmitted.encode("utf-8")) >= len(transmitted)
    assert canonical_token_count(transmitted) > 0


def test_provider_usage_normalization_preserves_cache_fields_and_raw_hash():
    usage = {
        "input_tokens": 100,
        "output_tokens": 20,
        "cache_read_input_tokens": 60,
        "cache_creation_input_tokens": 5,
    }

    normalized = normalize_provider_usage(usage)

    assert normalized["input_tokens"] == 100
    assert normalized["output_tokens"] == 20
    assert normalized["cache_read_tokens"] == 60
    assert normalized["cache_creation_tokens"] == 5
    assert len(normalized["raw_usage_sha256"]) == 64
    assert normalized["field_capture"]["cache_read_tokens"] == (
        "cache_read_input_tokens"
    )


def test_claude_envelope_parser_retains_attempt_history():
    stdout = (
        "warning line\n"
        '{"result":"{\\"answer\\":{}}","usage":{"input_tokens":4,'
        '"output_tokens":2},"modelUsage":{"glm-5":{}}}'
    )

    envelope, attempts = parse_claude_envelope(stdout)

    assert envelope["result"] == '{"answer":{}}'
    assert attempts[0]["status"] == "failed"
    assert attempts[-1]["status"] == "success"


def test_legacy_deepseek_alias_fails_over_to_supported_frozen_model():
    assert resolve_judge_model("deepseek-chat") == "deepseek-v4-pro"
    assert resolve_judge_model("deepseek-v4-flash") == "deepseek-v4-flash"


def test_repository_relative_path_accepts_relative_cli_arguments():
    assert repository_relative_path(
        Path("experiments/results/example.json")
    ) == "experiments/results/example.json"
