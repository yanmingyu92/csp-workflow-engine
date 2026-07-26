#!/usr/bin/env python3
"""Verify the allowlisted JMIR revision-1 reproducibility release.

The verifier is standard-library only and makes no network calls. It checks the
manifest hashes, the explicit publication allowlist, JSON parseability, absence
of common secret/token forms, and absence of local-workspace or assistant-tool
traces in released data and documentation. With ``--staged``, it reads files
from the Git index and rejects staged paths outside the allowlist.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path, PurePosixPath
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = PurePosixPath("experiments/jmir_rev1_manifest.json")
ALLOWLIST_PATH = PurePosixPath("experiments/jmir_rev1_release_files.txt")
HASH_GROUPS = (
    "designs",
    "scripts",
    "checkpoints",
    "tests",
    "analysis_artifacts",
    "release_metadata",
)
CORE_RELEASE_PATHS = {
    ".gitattributes",
    ".gitignore",
    "README.md",
    "pyproject.toml",
    "uv.lock",
    "scripts/context-loader.py",
    str(MANIFEST_PATH),
    str(ALLOWLIST_PATH),
    "experiments/README_JMIR_REV1.md",
    "experiments/verify_jmir_release.py",
}
DENIED_RELEASE_PATH_PATTERNS = (
    re.compile(r"(?:^|/)\.env(?:$|\.)", re.IGNORECASE),
    re.compile(r"(?:^|/)(?:temp|tmp)(?:/|$)", re.IGNORECASE),
    re.compile(r"(?:^|/)submission_upload_", re.IGNORECASE),
    re.compile(r"(?:^|/)archive(?:/|$)", re.IGNORECASE),
    re.compile(r"(?:^|/)experiment_v6_aps_gxp_smoke", re.IGNORECASE),
    re.compile(r"(?:^|/)jmir_aps_gxp_v6_execution_prompt_", re.IGNORECASE),
    re.compile(r"(?:^|/)(?:response_to_reviewers|manuscript_rev)", re.IGNORECASE),
    re.compile(r"(?:^|/)\.codex(?:/|$)", re.IGNORECASE),
)
SECRET_VALUE_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bapi[-_][A-Za-z0-9_-]{20,}\b", re.IGNORECASE),
    re.compile(r"Authorization\s*:\s*Bearer\s+\S+", re.IGNORECASE),
    re.compile(
        r"(?:api[_ -]?key|access[_ -]?token|secret[_ -]?key|password)"
        r"\s*[:=]\s*['\"]?[A-Za-z0-9_./+=-]{12,}",
        re.IGNORECASE,
    ),
)
LOCAL_TRACE_PATTERNS = (
    re.compile(
        r"[A-Za-z]:[/\\]Users[/\\][^/\\\r\n]+(?:[/\\]|$)",
        re.IGNORECASE,
    ),
    re.compile(r"/(?:home|Users)/[^/\r\n]+(?:/|$)"),
    re.compile(r"(?:^|[/\\])\.codex(?:[/\\]|$)", re.IGNORECASE),
    re.compile(
        r"\bOpenAI\s+" + r"Codex\b|\bChat" + r"GPT\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"csp-workflow-engine[/\\](?:temp|tmp)(?:[/\\]|$)",
        re.IGNORECASE,
    ),
)
SENSITIVE_JSON_KEYS = re.compile(
    r"^(?:api[_-]?key|access[_-]?token|secret[_-]?key|authorization|"
    r"password|credential)$",
    re.IGNORECASE,
)


def _git(*args: str) -> bytes:
    completed = subprocess.run(
        ["git", "-c", f"safe.directory={ROOT.as_posix()}", *args],
        cwd=ROOT,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return completed.stdout


def _read(path: PurePosixPath, staged: bool) -> bytes:
    if staged:
        return _git("show", f":{path}")
    return (ROOT / Path(path)).read_bytes()


def _load_json(path: PurePosixPath, staged: bool) -> Any:
    return json.loads(_read(path, staged).decode("utf-8"))


def _load_allowlist(staged: bool) -> list[str]:
    lines = _read(ALLOWLIST_PATH, staged).decode("utf-8").splitlines()
    paths = [line.strip() for line in lines if line.strip()]
    if len(paths) != len(set(paths)):
        raise ValueError("Release allowlist contains duplicate paths")
    for value in paths:
        path = PurePosixPath(value)
        if path.is_absolute() or ".." in path.parts or "\\" in value:
            raise ValueError(f"Unsafe release allowlist path: {value}")
        if any(pattern.search(value) for pattern in DENIED_RELEASE_PATH_PATTERNS):
            raise ValueError(f"Intermediate/sensitive path is denied: {value}")
    return paths


def _manifest_hashes(manifest: Mapping[str, Any]) -> dict[str, str]:
    hashes: dict[str, str] = {}
    scheduler = manifest.get("scheduler")
    if not isinstance(scheduler, Mapping):
        raise ValueError("Manifest scheduler block is missing")
    scheduler_path = str(scheduler["path"])
    scheduler_sha256 = str(scheduler["sha256"])
    if not re.fullmatch(r"[0-9a-f]{64}", scheduler_sha256):
        raise ValueError(
            f"Manifest SHA-256 is invalid for {scheduler_path}: "
            f"{scheduler_sha256}"
        )
    hashes[scheduler_path] = scheduler_sha256
    for group in HASH_GROUPS:
        values = manifest.get(group, {})
        if not isinstance(values, Mapping):
            raise ValueError(f"Manifest {group} block is not a mapping")
        for path, expected in values.items():
            if path in hashes:
                raise ValueError(f"Manifest path occurs more than once: {path}")
            expected_text = str(expected)
            if not re.fullmatch(r"[0-9a-f]{64}", expected_text):
                raise ValueError(
                    f"Manifest SHA-256 is invalid for {path}: {expected_text}"
                )
            hashes[str(path)] = expected_text
    return hashes


def _walk_json_keys(value: Any, location: str = "$") -> list[str]:
    findings: list[str] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            key_text = str(key)
            if SENSITIVE_JSON_KEYS.fullmatch(key_text):
                findings.append(f"{location}.{key_text}")
            findings.extend(_walk_json_keys(item, f"{location}.{key_text}"))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            findings.extend(_walk_json_keys(item, f"{location}[{index}]"))
    return findings


def verify(staged: bool) -> list[str]:
    failures: list[str] = []
    try:
        allowlist = _load_allowlist(staged)
        manifest = _load_json(MANIFEST_PATH, staged)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        return [f"Release metadata could not be loaded: {error}"]

    if manifest.get("release") != "jmir-100769-rev1":
        failures.append("Unexpected release identifier in manifest")
    try:
        manifest_hashes = _manifest_hashes(manifest)
    except (KeyError, ValueError) as error:
        return [f"Release manifest is invalid: {error}"]
    allowset = set(allowlist)
    required = set(manifest_hashes) | CORE_RELEASE_PATHS
    missing_from_allowlist = sorted(required - allowset)
    if missing_from_allowlist:
        failures.append(
            f"Manifest/core paths missing from allowlist: {missing_from_allowlist}"
        )
    unexpected_allowlist = sorted(allowset - required)
    if unexpected_allowlist:
        failures.append(
            f"Allowlist paths lack manifest/core coverage: {unexpected_allowlist}"
        )

    total_bytes = 0
    for value in allowlist:
        path = PurePosixPath(value)
        try:
            data = _read(path, staged)
        except (OSError, subprocess.CalledProcessError) as error:
            failures.append(f"Release file is missing/unreadable: {value}: {error}")
            continue
        total_bytes += len(data)
        expected = manifest_hashes.get(value)
        if expected is not None:
            actual = hashlib.sha256(data).hexdigest()
            if actual != expected:
                failures.append(
                    f"SHA-256 mismatch for {value}: expected {expected}, got {actual}"
                )

        text = data.decode("utf-8", errors="replace")
        for pattern in SECRET_VALUE_PATTERNS:
            if pattern.search(text):
                failures.append(
                    f"Potential secret/token pattern in released file: {value}"
                )
                break
        for pattern in LOCAL_TRACE_PATTERNS:
            if pattern.search(text):
                failures.append(
                    f"Local workspace or AI-assistance trace in released file: {value}"
                )
                break
        if path.suffix.lower() == ".json":
            try:
                parsed = json.loads(text)
            except ValueError as error:
                failures.append(f"Invalid JSON in {value}: {error}")
            else:
                sensitive_keys = _walk_json_keys(parsed)
                if sensitive_keys:
                    failures.append(
                        f"Sensitive JSON key(s) in {value}: "
                        f"{sensitive_keys[:5]}"
                    )

    if staged:
        staged_paths = set(
            _git(
                "diff",
                "--cached",
                "--name-only",
            )
            .decode("utf-8")
            .splitlines()
        )
        unexpected_staged = sorted(staged_paths - allowset)
        if unexpected_staged:
            failures.append(
                f"Staged paths outside release allowlist: {unexpected_staged}"
            )
        tracked_paths = set(
            _git("ls-files", "--", *allowlist).decode("utf-8").splitlines()
        )
        missing_from_index = sorted(allowset - tracked_paths)
        if missing_from_index:
            failures.append(
                f"Allowlisted files missing from Git index: {missing_from_index}"
            )

    print(
        f"release={manifest.get('release')} files={len(allowlist)} "
        f"bytes={total_bytes} staged={str(staged).lower()}"
    )
    v6_checkpoint_hash = manifest.get("checkpoints", {}).get(
        "experiments/results/experiment_v6_aps_gxp_formal_20260724_judged.json"
    )
    print(f"v6_checkpoint_sha256={v6_checkpoint_hash}")
    print(
        "interpretation="
        f"{manifest.get('interpretation_boundary', {}).get('outcome')}"
    )
    return failures


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--staged",
        action="store_true",
        help="Read release files from the Git index and reject staged extras.",
    )
    args = parser.parse_args()
    failures = verify(args.staged)
    if failures:
        print("RELEASE_AUDIT_FAILED")
        for failure in failures:
            print(f"- {failure}")
        raise SystemExit(1)
    print("RELEASE_AUDIT_OK")


if __name__ == "__main__":
    main()
