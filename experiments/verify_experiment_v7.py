#!/usr/bin/env python3
"""Independent, fail-closed verifier for frozen V7 artifacts.

This verifier intentionally does not import the V7 runner, router, evaluator, or
analyzer. It recomputes hashes and structural invariants from serialized files.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
V6_PATH = (
    PROJECT_ROOT
    / "experiments"
    / "results"
    / "experiment_v6_aps_gxp_formal_20260724_judged.json"
)
EXPECTED_V6_SHA256 = (
    "fb9f787a6e95e2bd0813c7f7b90fd986e64adeba09305645572a3875df927aa0"
)
ARMS = [
    "graph_bm25_chunk_optimized",
    "full_corpus_bm25_token_matched",
    "random_token_matched",
    "flat_8000",
]
USAGE_FIELDS = {
    "input_tokens",
    "output_tokens",
    "cache_read_tokens",
    "cache_creation_tokens",
    "raw_usage_sha256",
}
SHA256 = re.compile(r"^[0-9a-f]{64}$")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def secret_like_fields(value: Any, prefix: str = "root") -> list[str]:
    errors = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized = re.sub(r"[^a-z0-9]+", "_", str(key).lower())
            if normalized in {
                "api_key",
                "authorization",
                "password",
                "secret",
            } or normalized.endswith(
                ("_api_key", "_access_token", "_private_key")
            ):
                errors.append(f"secret-like field: {prefix}.{key}")
            errors.extend(secret_like_fields(item, f"{prefix}.{key}"))
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for index, item in enumerate(value):
            errors.extend(secret_like_fields(item, f"{prefix}[{index}]"))
    return errors


def verify_freeze(path: Path) -> list[str]:
    errors = []
    freeze = json.loads(path.read_text(encoding="utf-8"))
    content = dict(freeze)
    recorded_content_hash = content.pop("freeze_content_sha256", None)
    if recorded_content_hash != canonical_sha256(content):
        errors.append("freeze content hash mismatch")
    if freeze.get("v6_immutable_sha256") != EXPECTED_V6_SHA256:
        errors.append("freeze V6 hash declaration mismatch")
    if sha256_file(V6_PATH) != EXPECTED_V6_SHA256:
        errors.append("immutable V6 file hash mismatch")
    v6 = json.loads(V6_PATH.read_text(encoding="utf-8"))
    if len(v6.get("results", [])) != 120:
        errors.append("immutable V6 row count mismatch")
    if freeze.get("arms") != ARMS:
        errors.append("frozen arm order mismatch")
    if freeze.get("runs") != 3:
        errors.append("frozen run count mismatch")
    if freeze.get("heldout_count") != 24:
        errors.append("frozen held-out count mismatch")
    if len(freeze.get("heldout_task_ids", [])) != 24:
        errors.append("frozen held-out task ID count mismatch")
    if len(set(freeze.get("heldout_task_ids", []))) != 24:
        errors.append("frozen held-out task IDs are not unique")
    for field in ("stage0_path", "plan_path"):
        relative = freeze.get(field)
        if not isinstance(relative, str):
            errors.append(f"freeze missing {field}")
            continue
        actual = PROJECT_ROOT / relative
        recorded_field = f"{field.removesuffix('_path')}_sha256"
        if sha256_file(actual) != freeze.get(recorded_field):
            errors.append(f"{field} hash mismatch")
    task_path = (
        PROJECT_ROOT
        / "experiments"
        / "config"
        / "experiment_v7_routing_sensitive_tasks_20260725.yaml"
    )
    if sha256_file(task_path) != freeze.get("task_registry_sha256"):
        errors.append("task registry hash mismatch")
    registry = yaml.safe_load(task_path.read_text(encoding="utf-8"))
    if len(registry.get("development_tasks", [])) != 10:
        errors.append("development task count mismatch")
    if len(registry.get("heldout_tasks", [])) != 24:
        errors.append("held-out task count mismatch")
    for name, digest in freeze.get("source_hashes", {}).items():
        candidates = {
            "runner": "experiments/run_experiment_v7_routing_sensitive.py",
            "routing": "experiments/v7_routing.py",
            "deterministic_eval": "experiments/v7_deterministic_eval.py",
            "stage0": "experiments/v7_stage0.py",
            "task_registry": (
                "experiments/config/"
                "experiment_v7_routing_sensitive_tasks_20260725.yaml"
            ),
            "graph": "graph/regulatory-graph.yaml",
            "analyzer": "experiments/analyze_experiment_v7.py",
            "verifier": "experiments/verify_experiment_v7.py",
        }
        relative = candidates.get(name)
        if relative is None:
            errors.append(f"unknown frozen source hash key: {name}")
        elif sha256_file(PROJECT_ROOT / relative) != digest:
            errors.append(f"frozen source hash mismatch: {name}")
    corpus = freeze.get("corpus_files", [])
    if canonical_sha256(corpus) != freeze.get("corpus_tree_sha256"):
        errors.append("corpus tree hash mismatch")
    for row in corpus:
        if sha256_file(PROJECT_ROOT / row["path"]) != row.get("sha256"):
            errors.append(f"corpus source hash mismatch: {row.get('path')}")
    preflight = freeze.get("heldout_structural_preflight", {})
    if preflight.get("quality_scores_computed") is not False:
        errors.append("held-out structural preflight exposed quality scores")
    if preflight.get("generation_or_judge_scores_used") is not False:
        errors.append("held-out preflight used generation or judge scores")
    if preflight.get("cell_count") != 96:
        errors.append("held-out preflight cell count mismatch")
    if len(preflight.get("cells", [])) != 24:
        errors.append("held-out preflight task count mismatch")
    if freeze.get("manuscript_modified") is not False:
        errors.append("freeze claims a manuscript modification")
    if freeze.get("operational_gxp_compliance_claimed") is not False:
        errors.append("freeze claims operational GxP compliance")
    errors.extend(secret_like_fields(freeze, "freeze"))
    return errors


def verify_generation(path: Path) -> list[str]:
    errors = []
    payload = json.loads(path.read_text(encoding="utf-8"))
    metadata = payload.get("metadata", {})
    rows = payload.get("results", [])
    expected = (
        len(metadata.get("tasks", []))
        * len(metadata.get("arms", []))
        * int(metadata.get("runs", 0))
    )
    if len(rows) != expected:
        errors.append(f"generation row count {len(rows)} != {expected}")
    keys = [row.get("run_key") for row in rows]
    if len(keys) != len(set(keys)):
        errors.append("generation run keys are not unique")
    for row in rows:
        key = str(row.get("run_key"))
        if USAGE_FIELDS - set(row.get("provider_usage", {})):
            errors.append(f"{key}: incomplete provider usage")
        for field in (
            "serialized_prompt_characters",
            "serialized_prompt_bytes",
            "canonical_prompt_tokens",
        ):
            if not isinstance(row.get(field), int) or row[field] < 0:
                errors.append(f"{key}: invalid {field}")
        response = str(row.get("response", ""))
        if hashlib.sha256(response.encode("utf-8")).hexdigest() != row.get(
            "response_sha256"
        ):
            errors.append(f"{key}: response hash mismatch")
        if row.get("manifest_sha256") != row.get("manifest", {}).get(
            "manifest_sha256"
        ):
            errors.append(f"{key}: manifest linkage mismatch")
        if row.get("repeated_manifest_sha256") != row.get("manifest_sha256"):
            errors.append(f"{key}: repeated manifest mismatch")
        attempts = row.get("generation_attempts", [])
        if not attempts or attempts[-1].get("status") != "success":
            errors.append(f"{key}: final generation attempt is not successful")
        if "deterministic_evaluation" in row or "llm_judgment" in row:
            errors.append(f"{key}: generation checkpoint leaks quality scores")
    errors.extend(secret_like_fields(payload, "generation"))
    return errors


def verify_evaluated(path: Path) -> list[str]:
    errors = []
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("results", [])
    if len(rows) != 288:
        errors.append(f"evaluated row count {len(rows)} != 288")
    for row in rows:
        key = str(row.get("run_key"))
        deterministic = row.get("deterministic_evaluation")
        if not isinstance(deterministic, Mapping):
            errors.append(f"{key}: deterministic evaluation missing")
        elif not 0 <= float(deterministic.get("score", -1)) <= 1:
            errors.append(f"{key}: deterministic score invalid")
        judgment = row.get("llm_judgment")
        if not isinstance(judgment, Mapping):
            errors.append(f"{key}: LLM judgment missing")
        elif judgment.get("complete_response_sha256_judged") != row.get(
            "response_sha256"
        ):
            errors.append(f"{key}: judged response linkage mismatch")
        if not row.get("llm_judge_attempts"):
            errors.append(f"{key}: judge attempt history missing")
    errors.extend(secret_like_fields(payload, "evaluated"))
    return errors


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze", type=Path, required=True)
    parser.add_argument("--generation", type=Path)
    parser.add_argument("--evaluated", type=Path)
    args = parser.parse_args()
    errors = verify_freeze(args.freeze)
    if args.generation:
        errors.extend(verify_generation(args.generation))
    if args.evaluated:
        errors.extend(verify_evaluated(args.evaluated))
    if errors:
        raise SystemExit("\n".join(errors))
    print("V7_INDEPENDENT_VERIFICATION_OK")


if __name__ == "__main__":
    main()
