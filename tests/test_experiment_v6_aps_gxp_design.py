"""Design, regression, and Stage-0 invariants for APS-GxP v6."""

from __future__ import annotations

import asyncio
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from experiments import run_experiment_v4_claude as v4
from experiments.run_experiment_v6_aps_gxp import (
    FOUR_ARM_CONDITIONS,
    V5_PARITY_CHECKPOINT,
    ApsGxpExperimentRunner,
    build_complete_response_judge_prompt,
    build_stage0_report,
    judge_checkpoint,
    run_generation,
    stable_run_key,
    validate_random_token_matching,
    validate_resume_configuration,
    validate_v6_checkpoint,
)
from experiments.aps_gxp_context import (
    canonical_manifest_sha256,
    sha256_text,
)


PROJECT_ROOT = Path(__file__).parents[1]
EXPECTED_V5_CHECKPOINT_SHA256 = (
    "e337862a974fd2bb5cd1bd691875f1e6483b8acca5687cbe4e758f5fcb587ed8"
)


@pytest.fixture(scope="module")
def runner():
    return ApsGxpExperimentRunner(seed=42, budget=8000)


def _signature_from_stored(row: dict) -> tuple[tuple[str, str, str, int], ...]:
    return tuple(
        (
            skill["name"],
            skill["band"],
            skill["status"],
            int(skill["tokens"]),
        )
        for skill in row["context_audit"]["skills"]
    )


def _signature_from_cell(cell) -> tuple[tuple[str, str, str, int], ...]:
    return tuple(
        (
            skill.name,
            skill.band.name,
            skill.status,
            int(skill.token_estimate),
        )
        for skill in cell.context_result.skills
    )


def test_four_arm_order_is_locked():
    assert FOUR_ARM_CONDITIONS == (
        "aps_v5_frozen",
        "aps_gxp_optimized",
        "flat_8000",
        "random_token_matched",
    )


def test_run_key_is_task_arm_run():
    assert stable_run_key("task-a", "aps_gxp_optimized", 2) == (
        "task-a::aps_gxp_optimized::2"
    )


def test_direct_v6_cli_entrypoint_can_import_experiments_package():
    script = (
        PROJECT_ROOT / "experiments" / "run_experiment_v6_aps_gxp.py"
    )
    completed = subprocess.run(
        [sys.executable, str(script), "--help"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr


def test_frozen_v5_matches_full_response_checkpoint_for_all_ten_tasks(runner):
    checkpoint_bytes = V5_PARITY_CHECKPOINT.read_bytes()
    assert hashlib.sha256(checkpoint_bytes).hexdigest() == (
        EXPECTED_V5_CHECKPOINT_SHA256
    )
    data = json.loads(checkpoint_bytes)
    stored = [
        row for row in data["results"] if row["condition"] == "agent_framework"
    ]
    assert len(stored) == 30

    for task_id in v4.QUICK_10_TASKS:
        task_rows = [row for row in stored if row["task_id"] == task_id]
        expected_signatures = {_signature_from_stored(row) for row in task_rows}
        assert len(expected_signatures) == 1
        cell = runner.build_context_cell(task_id, "aps_v5_frozen", run_id=0)
        assert _signature_from_cell(cell) == next(iter(expected_signatures))


def test_optimized_relevance_varies_and_changes_tfl_noncurrent_selection(runner):
    demographics = runner.build_context_cell(
        "task-17-tfl-demographics", "aps_gxp_optimized", run_id=0
    )
    adverse_events = runner.build_context_cell(
        "task-20-tfl-ae", "aps_gxp_optimized", run_id=0
    )
    demographic_records = {
        row["skill_name"]: row for row in demographics.manifest["candidates"]
    }
    adverse_event_records = {
        row["skill_name"]: row for row in adverse_events.manifest["candidates"]
    }
    common_noncurrent = sorted(
        {
            name
            for name, row in demographic_records.items()
            if row["priority_band"] != "CURRENT"
        }
        & {
            name
            for name, row in adverse_event_records.items()
            if row["priority_band"] != "CURRENT"
        }
    )

    assert any(
        demographic_records[name]["lexical_relevance_score"]
        != adverse_event_records[name]["lexical_relevance_score"]
        for name in common_noncurrent
    )
    demographic_selected = {
        row["skill_name"]
        for row in demographic_records.values()
        if row["priority_band"] != "CURRENT"
        and row["status"] in {"loaded", "truncated"}
    }
    adverse_event_selected = {
        row["skill_name"]
        for row in adverse_event_records.values()
        if row["priority_band"] != "CURRENT"
        and row["status"] in {"loaded", "truncated"}
    }
    assert demographic_selected != adverse_event_selected


def test_optimized_protects_current_and_can_stop_below_budget(runner):
    below_budget = False
    for task_id in v4.QUICK_10_TASKS:
        frozen = runner.build_context_cell(task_id, "aps_v5_frozen", run_id=0)
        optimized = runner.build_context_cell(
            task_id, "aps_gxp_optimized", run_id=0
        )
        frozen_current = {
            skill.name
            for skill in frozen.context_result.skills
            if skill.band.name == "CURRENT"
            and skill.status in {"loaded", "truncated"}
        }
        optimized_current = {
            skill.name
            for skill in optimized.context_result.skills
            if skill.band.name == "CURRENT"
            and skill.status in {"loaded", "truncated"}
        }
        assert optimized_current == frozen_current
        assert optimized.context_result.budget_used <= 8000
        below_budget |= optimized.context_result.budget_used < 8000
        assert all(
            row["selection_reason"]
            for row in optimized.manifest["candidates"]
        )
    assert below_budget


def test_optimized_soft_cap_preserves_full_current_and_limits_noncurrent(runner):
    common_budget = 8000
    expected_soft_cap = 6720
    override_observed = False
    for task_id in v4.QUICK_10_TASKS:
        optimized = runner.build_context_cell(
            task_id, "aps_gxp_optimized", run_id=0
        )
        current = [
            candidate
            for candidate in optimized.manifest["candidates"]
            if candidate["graph_relation"] == "CURRENT"
        ]
        full_current_demand = sum(
            candidate["original_estimated_tokens"]
            for candidate in current
        )
        effective_cap = min(
            common_budget,
            max(expected_soft_cap, full_current_demand),
        )
        override_observed |= full_current_demand > expected_soft_cap

        assert optimized.manifest["context_budget_policy"] == (
            "optimized_84_percent_soft_cap_with_full_current_override"
        )
        assert optimized.manifest["optimized_soft_cap_tokens"] == (
            expected_soft_cap
        )
        assert optimized.manifest["effective_context_cap_tokens"] == (
            effective_cap
        )
        assert optimized.context_result.skill_tokens <= effective_cap
        assert all(
            candidate["status"] == "loaded"
            and candidate["injected_estimated_tokens"]
            == candidate["original_estimated_tokens"]
            for candidate in current
        )
    assert override_observed


def test_manifest_is_complete_and_reproducible(runner):
    first = runner.build_context_cell(
        "task-07-sdtm-ae", "aps_gxp_optimized", run_id=1
    )
    runner.build_context_cell("task-01-sap-parse", "flat_8000", run_id=0)
    again = runner.build_context_cell(
        "task-07-sdtm-ae", "aps_gxp_optimized", run_id=1
    )

    assert first.manifest == again.manifest
    assert first.manifest["manifest_sha256"] == again.manifest["manifest_sha256"]
    assert first.validation_errors == ()


def test_random_is_call_order_independent_and_token_matched(runner):
    for task_id in v4.QUICK_10_TASKS:
        optimized = runner.build_context_cell(
            task_id, "aps_gxp_optimized", run_id=2
        )
        random_first = runner.build_context_cell(
            task_id, "random_token_matched", run_id=2
        )
        runner.build_context_cell(task_id, "flat_8000", run_id=0)
        random_again = runner.build_context_cell(
            task_id, "random_token_matched", run_id=2
        )

        assert random_first.manifest == random_again.manifest
        assert (
            abs(
                random_first.context_result.skill_tokens
                - optimized.context_result.skill_tokens
            )
            <= 1
        )
        assert {
            skill.band.name
            for skill in random_first.context_result.skills
        } == {"GLOBAL"}


def test_checkpoint_random_token_matching_is_independently_validated(runner):
    cells = [
        runner.build_context_cell(
            "task-20-tfl-ae", arm, run_id=0
        )
        for arm in FOUR_ARM_CONDITIONS
    ]
    checkpoint = runner.context_checkpoint(cells)

    assert validate_random_token_matching(checkpoint) == []

    random_row = next(
        row
        for row in checkpoint["contexts"]
        if row["arm"] == "random_token_matched"
    )
    random_row["skills_tokens"] += 2
    assert any(
        "random token match" in error
        for error in validate_random_token_matching(checkpoint)
    )


def test_returned_manifest_cannot_mutate_runner_binding_state(runner):
    first = runner.build_context_cell(
        "task-20-tfl-ae", "aps_gxp_optimized", run_id=0
    )
    candidate = first.manifest["candidates"][0]
    candidate["skill_bound_node_ids"].append("tampered-node")

    again = runner.build_context_cell(
        "task-20-tfl-ae", "aps_gxp_optimized", run_id=0
    )

    assert "tampered-node" not in again.manifest["candidates"][0][
        "skill_bound_node_ids"
    ]


def test_source_hashes_freeze_corpus_and_invocation_wrapper(runner):
    hashes = runner.source_hashes_v6()

    assert len(hashes["skill_manifest"]) == 64
    assert len(hashes["invocation"]) == 64
    assert len(hashes["regulatory_patterns"]) == 64
    assert len(hashes["optimization_policy"]) == 64


def test_complete_response_judge_prompt_has_no_prefix_path():
    response = "A" * 5000 + "UNIQUE_COMPLETE_RESPONSE_TAIL"

    prompt = build_complete_response_judge_prompt(
        task_id="task-20-tfl-ae",
        response=response,
        domain_criteria="criteria",
    )

    assert response in prompt
    assert "UNIQUE_COMPLETE_RESPONSE_TAIL" in prompt
    assert len(response) > 4000


def test_scalar_checkpoint_proves_the_complete_response_and_prompt(runner):
    task_id = "task-20-tfl-ae"
    arm = "aps_gxp_optimized"
    response = "A" * 5000 + "UNIQUE_COMPLETE_RESPONSE_TAIL"
    cell = runner.build_context_cell(task_id, arm, run_id=0)
    domain_criteria = runner._get_judge_criteria(v4.TASK_NODES[task_id][0])
    judge_prompt = build_complete_response_judge_prompt(
        task_id, response, domain_criteria
    )
    result = {
        "run_key": stable_run_key(task_id, arm, 0),
        "task_id": task_id,
        "graph_node": v4.TASK_NODES[task_id][0],
        "arm": arm,
        "run_id": 0,
        "response": response,
        "response_sha256": sha256_text(response),
        "skills_tokens": cell.context_result.skill_tokens,
        "budget_used": cell.context_result.budget_used,
        "manifest_sha256": cell.manifest["manifest_sha256"],
        "manifest": cell.manifest,
        "repeated_manifest_sha256": [cell.manifest["manifest_sha256"]] * 3,
        "agent_model_requested": runner.agent_model_requested,
        "agent_model_returned": "fake-agent-returned",
        "is_error_response": False,
        "judge_domain_criteria": domain_criteria,
        "judge_domain_criteria_sha256": sha256_text(domain_criteria),
        "scalar_judgment": {
            "policy": "full_stored_response_no_character_truncation",
            "truncated": False,
            "response_characters_judged": len(response),
            "response_bytes_judged": len(response.encode("utf-8")),
            "response_sha256": sha256_text(response),
            "rendered_prompt_characters": len(judge_prompt),
            "rendered_prompt_bytes": len(judge_prompt.encode("utf-8")),
            "rendered_prompt_sha256": sha256_text(judge_prompt),
            "scores": {
                "completeness": 4.0,
                "terminology": 4.0,
                "structure": 4.0,
            },
            "judge_model_requested": runner.judge_model,
            "judge_model_returned": "judge-model-returned",
            "judge_response_id": "response-id",
            "system_fingerprint": "fingerprint",
            "system_fingerprint_capture": "available",
            "judge_input_tokens": 100,
            "judge_output_tokens": 20,
            "finish_reason": "stop",
            "judge_parse_error": None,
        },
    }
    checkpoint = runner.generation_checkpoint([result], [task_id], runs=1)
    checkpoint["metadata"]["arms"] = [arm]
    assert validate_v6_checkpoint(
        checkpoint, require_judgments=True
    ) == []

    corrupted_prompt = copy.deepcopy(checkpoint)
    corrupted_prompt["results"][0]["scalar_judgment"][
        "rendered_prompt_sha256"
    ] = "0" * 64
    assert any(
        "scalar prompt hash mismatch" in error
        for error in validate_v6_checkpoint(
            corrupted_prompt, require_judgments=True
        )
    )

    missing_identity = copy.deepcopy(checkpoint)
    missing_identity["results"][0]["scalar_judgment"][
        "judge_model_returned"
    ] = None
    assert any(
        "judge identity" in error
        for error in validate_v6_checkpoint(
            missing_identity, require_judgments=True
        )
    )


def test_checkpoint_validator_rejects_duplicates_budget_and_manifest_errors(runner):
    cell = runner.build_context_cell(
        "task-06-sdtm-dm", "aps_gxp_optimized", run_id=0
    )
    checkpoint = runner.context_checkpoint([cell])
    assert validate_v6_checkpoint(checkpoint, context_only=True) == []

    duplicate = copy.deepcopy(checkpoint)
    duplicate["contexts"].append(copy.deepcopy(duplicate["contexts"][0]))
    assert any(
        "duplicate" in error
        for error in validate_v6_checkpoint(duplicate, context_only=True)
    )

    over_budget = copy.deepcopy(checkpoint)
    over_budget["contexts"][0]["manifest"]["budget_used"] = 8001
    assert any(
        "budget" in error
        for error in validate_v6_checkpoint(over_budget, context_only=True)
    )

    unstable = copy.deepcopy(checkpoint)
    unstable["contexts"][0]["manifest"]["manifest_sha256"] = "0" * 64
    assert any(
        "manifest hash" in error
        for error in validate_v6_checkpoint(unstable, context_only=True)
    )

    row_identity = copy.deepcopy(checkpoint)
    row_identity["contexts"][0]["task_id"] = "task-20-tfl-ae"
    assert any(
        "row identity" in error
        for error in validate_v6_checkpoint(row_identity, context_only=True)
    )

    manifest_identity = copy.deepcopy(checkpoint)
    manifest_identity["contexts"][0]["manifest"]["arm"] = "flat_8000"
    manifest_identity["contexts"][0]["manifest"]["manifest_sha256"] = (
        canonical_manifest_sha256(
            manifest_identity["contexts"][0]["manifest"]
        )
    )
    manifest_identity["contexts"][0]["manifest_sha256"] = (
        manifest_identity["contexts"][0]["manifest"]["manifest_sha256"]
    )
    assert any(
        "manifest identity" in error
        for error in validate_v6_checkpoint(
            manifest_identity, context_only=True
        )
    )

    invalid_soft_cap = copy.deepcopy(checkpoint)
    invalid_soft_cap["contexts"][0]["manifest"][
        "effective_context_cap_tokens"
    ] += 1
    invalid_soft_cap["contexts"][0]["manifest"]["manifest_sha256"] = (
        canonical_manifest_sha256(
            invalid_soft_cap["contexts"][0]["manifest"]
        )
    )
    invalid_soft_cap["contexts"][0]["manifest_sha256"] = (
        invalid_soft_cap["contexts"][0]["manifest"]["manifest_sha256"]
    )
    assert any(
        "optimized context policy" in error
        for error in validate_v6_checkpoint(
            invalid_soft_cap, context_only=True
        )
    )

    impossible_current = copy.deepcopy(checkpoint)
    optimized_row = next(
        row
        for row in impossible_current["contexts"]
        if row["arm"] == "aps_gxp_optimized"
    )
    current_candidate = next(
        candidate
        for candidate in optimized_row["manifest"]["candidates"]
        if candidate["graph_relation"] == "CURRENT"
    )
    current_candidate["original_estimated_tokens"] = 8001
    optimized_row["manifest"]["manifest_sha256"] = canonical_manifest_sha256(
        optimized_row["manifest"]
    )
    optimized_row["manifest_sha256"] = optimized_row["manifest"][
        "manifest_sha256"
    ]
    assert any(
        "CURRENT demand exceeds" in error
        for error in validate_v6_checkpoint(
            impossible_current, context_only=True
        )
    )


def test_resume_requires_the_same_immutable_v6_configuration(runner):
    task_ids = ["task-20-tfl-ae"]
    checkpoint = runner.generation_checkpoint([], task_ids, runs=1)
    assert checkpoint["metadata"]["judge_configuration"] == {
        "temperature": 0.0,
        "max_tokens": 2000,
        "complete_response_policy": (
            "full_stored_response_no_character_truncation"
        ),
    }
    assert validate_resume_configuration(
        checkpoint, runner, task_ids, runs=1
    ) == []

    wrong_seed = copy.deepcopy(checkpoint)
    wrong_seed["metadata"]["seed"] = 7
    assert any(
        "seed" in error
        for error in validate_resume_configuration(
            wrong_seed, runner, task_ids, runs=1
        )
    )

    wrong_hash = copy.deepcopy(checkpoint)
    wrong_hash["metadata"]["source_hashes"]["runner"] = "0" * 64
    assert any(
        "source hashes" in error
        for error in validate_resume_configuration(
            wrong_hash, runner, task_ids, runs=1
        )
    )


def test_judge_checkpoint_handles_unjudged_rows_and_sends_complete_responses(
    runner, tmp_path
):
    task_id = "task-20-tfl-ae"
    response_tail = "UNIQUE_COMPLETE_RESPONSE_TAIL"
    rows = []
    for arm in FOUR_ARM_CONDITIONS:
        cell = runner.build_context_cell(task_id, arm, run_id=0)
        response = "A" * 5000 + response_tail
        domain_criteria = runner._get_judge_criteria(
            v4.TASK_NODES[task_id][0]
        )
        rows.append(
            {
                "run_key": stable_run_key(task_id, arm, 0),
                "task_id": task_id,
                "graph_node": v4.TASK_NODES[task_id][0],
                    "judge_domain_criteria": domain_criteria,
                    "judge_domain_criteria_sha256": sha256_text(
                        domain_criteria
                    ),
                "arm": arm,
                "run_id": 0,
                    "response": response,
                    "response_sha256": sha256_text(response),
                    "skills_tokens": cell.context_result.skill_tokens,
                "budget_used": cell.context_result.budget_used,
                "manifest_sha256": cell.manifest["manifest_sha256"],
                "manifest": cell.manifest,
                "repeated_manifest_sha256": [
                    cell.manifest["manifest_sha256"]
                ]
                * 3,
                "agent_model_requested": runner.agent_model_requested,
                "agent_model_returned": "fake-agent-returned",
                "is_error_response": False,
                "isolated_working_directory": True,
                "scalar_judgment": None,
            }
        )
    checkpoint = runner.generation_checkpoint(rows, [task_id], runs=1)
    source_path = tmp_path / "generated.json"
    output_path = tmp_path / "judged.json"
    source_path.write_text(json.dumps(checkpoint), encoding="utf-8")

    prompts = []

    class FakeCompletions:
        async def create(self, **kwargs):
            prompts.append(kwargs["messages"][0]["content"])
            assert kwargs["max_tokens"] == 2000
            return SimpleNamespace(
                model="fake-judge-returned",
                id=f"response-{len(prompts)}",
                system_fingerprint="fake-fingerprint",
                usage=SimpleNamespace(
                    prompt_tokens=100,
                    completion_tokens=20,
                ),
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content=(
                                '{"completeness": 4, "terminology": 4, '
                                '"structure": 4, "reasoning": "complete"}'
                            )
                        ),
                        finish_reason="stop",
                    )
                ],
            )

    original_network = runner.network_enabled
    original_client = runner.judge_client
    runner.network_enabled = True
    runner.judge_client = SimpleNamespace(
        chat=SimpleNamespace(completions=FakeCompletions())
    )
    try:
        invalid_checkpoint = copy.deepcopy(checkpoint)
        invalid_checkpoint["results"][0]["response_sha256"] = "0" * 64
        invalid_source_path = tmp_path / "invalid-generated.json"
        invalid_source_path.write_text(
            json.dumps(invalid_checkpoint), encoding="utf-8"
        )
        with pytest.raises(ValueError, match="source checkpoint invalid"):
            asyncio.run(
                judge_checkpoint(
                    runner, invalid_source_path, tmp_path / "invalid-judged.json"
                )
            )
        assert prompts == []

        parse_error_resume = copy.deepcopy(checkpoint)
        parse_error_resume["results"][0]["scalar_judgment"] = {
            "judge_parse_error": "invalid JSON",
            "response_sha256": parse_error_resume["results"][0][
                "response_sha256"
            ],
        }
        output_path.write_text(
            json.dumps(parse_error_resume), encoding="utf-8"
        )
        judged = asyncio.run(
            judge_checkpoint(runner, source_path, output_path)
        )
    finally:
        runner.network_enabled = original_network
        runner.judge_client = original_client

    assert len(prompts) == len(FOUR_ARM_CONDITIONS)
    assert all(response_tail in prompt for prompt in prompts)
    assert len(
        judged["results"][0]["prior_scalar_judgment_attempts"]
    ) == 1
    assert validate_v6_checkpoint(judged, require_judgments=True) == []

    formal_partial = copy.deepcopy(judged["results"][0])
    formal_partial["run_id"] = 2
    formal_partial["run_key"] = stable_run_key(
        task_id, formal_partial["arm"], 2
    )
    formal_cell = runner.build_context_cell(
        task_id, formal_partial["arm"], run_id=2
    )
    formal_partial["manifest"] = formal_cell.manifest
    formal_partial["manifest_sha256"] = formal_cell.manifest[
        "manifest_sha256"
    ]
    formal_partial["budget_used"] = formal_cell.context_result.budget_used
    formal_partial["repeated_manifest_sha256"] = [
        formal_cell.manifest["manifest_sha256"]
    ] * 3
    formal_metadata = runner.generation_checkpoint(
        [], [task_id], runs=3
    )["metadata"]
    assert validate_v6_checkpoint(
        {"metadata": formal_metadata, "results": [formal_partial]},
        require_judgments=True,
        allow_partial=True,
    ) == []


def test_stage0_cardinality_and_repeated_hash_schema(runner):
    report = build_stage0_report(
        runner,
        task_ids=("task-17-tfl-demographics", "task-20-tfl-ae"),
        repeats=3,
    )

    assert report["actuals"]["context_cells"] == 2 * 4
    assert report["actuals"]["context_builds"] == 2 * 4 * 3
    assert report["task_count"] == 2
    assert all(
        len(cell["repeated_manifest_sha256"]) == 3
        for cell in report["cells"]
    )
    assert "composite_gxp_score" not in report


def test_generation_retry_uses_a_fresh_directory_for_every_agent_call(
    runner, tmp_path, monkeypatch
):
    calls = []

    def fake_invoke_claude_code(**kwargs):
        calls.append(kwargs["cwd"])
        if len(calls) == 1:
            return {
                "result": "[TIMEOUT]",
                "total_cost_usd": 0.0,
                "input_tokens": 0,
                "output_tokens": 0,
                "duration_ms": 1,
                "num_turns": 0,
                "model": "timeout",
                "is_error": True,
            }
        return {
            "result": "complete response",
            "total_cost_usd": 0.0,
            "input_tokens": 10,
            "output_tokens": 5,
            "duration_ms": 1,
            "num_turns": 1,
            "model": "fake-agent-returned",
            "is_error": False,
        }

    monkeypatch.setattr(v4, "invoke_claude_code", fake_invoke_claude_code)
    monkeypatch.setattr(
        "experiments.run_experiment_v6_aps_gxp."
        "_complete_transmitted_agent_prompt",
        lambda prompt: "no-tools\n" + prompt,
    )
    monkeypatch.setattr(
        "experiments.run_experiment_v6_aps_gxp.time.sleep",
        lambda _seconds: None,
    )
    original_network = runner.network_enabled
    runner.network_enabled = True
    try:
        checkpoint = run_generation(
            runner,
            ["task-20-tfl-ae"],
            runs=1,
            output_path=tmp_path / "generation.json",
        )
    finally:
        runner.network_enabled = original_network

    assert len(checkpoint["results"]) == 4
    assert len(calls) == 5
    assert len(set(calls)) == len(calls)
    assert all(not Path(path).exists() for path in calls)


def test_generation_failure_is_checkpointed_and_aborts_remaining_calls(
    runner, tmp_path, monkeypatch
):
    calls = []

    def fake_invoke_claude_code(**kwargs):
        calls.append(kwargs["cwd"])
        return {
            "result": "[UPSTREAM ERROR]",
            "total_cost_usd": 0.25,
            "input_tokens": 100,
            "output_tokens": 0,
            "duration_ms": 1,
            "num_turns": 1,
            "model": "fake-agent-returned",
            "is_error": True,
        }

    monkeypatch.setattr(v4, "invoke_claude_code", fake_invoke_claude_code)
    monkeypatch.setattr(
        "experiments.run_experiment_v6_aps_gxp."
        "_complete_transmitted_agent_prompt",
        lambda prompt: "no-tools\n" + prompt,
    )
    output_path = tmp_path / "generation.json"
    original_network = runner.network_enabled
    runner.network_enabled = True
    try:
        with pytest.raises(RuntimeError, match="aborted after failed"):
            run_generation(
                runner,
                ["task-20-tfl-ae"],
                runs=1,
                output_path=output_path,
            )
    finally:
        runner.network_enabled = original_network

    checkpoint = json.loads(output_path.read_text(encoding="utf-8"))
    assert checkpoint["results"] == []
    assert len(checkpoint["failed_generation_attempts"]) == 1
    assert checkpoint["failed_generation_attempts"][0]["input_tokens"] == 100
    assert len(calls) == 1


def test_content_level_agent_error_aborts_before_later_paid_calls(
    runner, tmp_path, monkeypatch
):
    calls = []

    def fake_invoke_claude_code(**kwargs):
        calls.append(kwargs["cwd"])
        return {
            "result": "[EMPTY OUTPUT] upstream returned no response",
            "total_cost_usd": 0.25,
            "input_tokens": 100,
            "output_tokens": 0,
            "duration_ms": 1,
            "num_turns": 1,
            "model": "fake-agent-returned",
            "is_error": False,
        }

    monkeypatch.setattr(v4, "invoke_claude_code", fake_invoke_claude_code)
    monkeypatch.setattr(
        "experiments.run_experiment_v6_aps_gxp."
        "_complete_transmitted_agent_prompt",
        lambda prompt: "no-tools\n" + prompt,
    )
    output_path = tmp_path / "content-error-generation.json"
    original_network = runner.network_enabled
    runner.network_enabled = True
    try:
        with pytest.raises(RuntimeError, match="aborted after failed"):
            run_generation(
                runner,
                ["task-20-tfl-ae"],
                runs=1,
                output_path=output_path,
            )
    finally:
        runner.network_enabled = original_network

    checkpoint = json.loads(output_path.read_text(encoding="utf-8"))
    assert checkpoint["results"] == []
    assert len(checkpoint["failed_generation_attempts"]) == 1
    assert len(calls) == 1
