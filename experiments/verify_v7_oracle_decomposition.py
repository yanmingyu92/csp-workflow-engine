"""Independent verifier for the V7 oracle decomposition artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

from experiments.v7_oracle_metrics import (
    ERROR_CLASSES,
    canonical_json_bytes,
    sha256_file,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ANALYSIS = (
    ROOT / "experiments" / "results" / "experiment_v7_oracle_decomposition_20260725"
)
EXPECTED_V6_SHA256 = "fb9f787a6e95e2bd0813c7f7b90fd986e64adeba09305645572a3875df927aa0"
EXPECTED_ARMS = {
    "graph_bm25_chunk_optimized",
    "full_corpus_bm25_token_matched",
    "random_token_matched",
    "flat_8000",
}
METRIC_KEYS = {
    "required_section_recall",
    "required_section_precision",
    "required_token_precision",
    "dependency_coverage",
    "topology_alignment",
    "irrelevant_token_ratio",
    "redundancy",
    "version_selection_correctness",
    "version_conflict_output_correctness",
    "provenance_completeness",
    "correct_citation_rate",
}
REQUIRED_REPORTS = {
    "analysis-report.md",
    "stats-appendix.md",
    "figure-catalog.md",
    "regulatory-alignment-matrix.md",
    "failure_log.json",
    "input_hashes.json",
    "oracle_decomposition.json",
}


def verify_payload(
    payload: Mapping[str, Any],
    *,
    root: Path,
    verify_files: bool = True,
) -> list[str]:
    """Return deterministic verification errors for one payload."""
    errors: list[str] = []
    if payload.get("schema_version") != "v7-oracle-decomposition-1":
        errors.append("unexpected decomposition schema version")
    cells = list(payload.get("cells", []))
    if len(cells) != 288:
        errors.append(f"expected 288 cells, observed {len(cells)}")
    keys = [
        (str(row.get("task_id")), str(row.get("arm")), int(row.get("run_id", -1)))
        for row in cells
    ]
    if len(set(keys)) != len(keys):
        errors.append("duplicate task/arm/run cells detected")
    tasks = {task_id for task_id, _, _ in keys}
    arms = {arm for _, arm, _ in keys}
    runs = {run_id for _, _, run_id in keys}
    if len(tasks) != 24:
        errors.append(f"expected 24 tasks, observed {len(tasks)}")
    if arms != EXPECTED_ARMS:
        errors.append(f"unexpected arm set: {sorted(arms)}")
    if runs != {0, 1, 2}:
        errors.append(f"unexpected run IDs: {sorted(runs)}")
    for index, cell in enumerate(cells):
        metrics = cell.get("metrics", {})
        for key in METRIC_KEYS:
            value = metrics.get(key)
            if not isinstance(value, (int, float)):
                errors.append(f"cell {index} missing numeric metric {key}")
            elif not 0.0 <= float(value) <= 1.0:
                errors.append(f"cell {index} metric {key}={value} outside [0, 1]")
    boundaries = payload.get("claim_boundaries", {})
    prohibited = {
        "graph_superiority_established": "graph superiority",
        "cross_version_means_compared": "cross-version mean comparison",
        "operational_gxp_compliance_claimed": "operational GxP compliance",
        "paid_generation_started": "paid generation",
    }
    for key, label in prohibited.items():
        if boundaries.get(key) is not False:
            errors.append(f"prohibited or missing claim boundary: {label}")
    hashes = payload.get("input_hashes", {})
    baseline = hashes.get("v6_judged_baseline", {})
    if baseline.get("sha256") != EXPECTED_V6_SHA256:
        errors.append("V6 judged baseline hash is not the immutable expected SHA256")
    if verify_files:
        for role, record in sorted(hashes.items()):
            path = root / str(record.get("path", ""))
            if not path.is_file():
                errors.append(f"missing hashed input for {role}: {path}")
                continue
            observed = sha256_file(path)
            if observed != record.get("sha256"):
                errors.append(f"input hash mismatch for {role}")
    taxonomy = payload.get("error_taxonomy", {})
    if set(taxonomy.get("classes", [])) != set(ERROR_CLASSES):
        errors.append("error taxonomy classes do not match the frozen contract")
    failures = payload.get("failure_summary", {})
    if int(failures.get("error_count", 0)) != 0:
        errors.append(
            f"decomposition has {failures.get('error_count')} artifact errors"
        )
    freeze_audit = payload.get("freeze_contract_audit", {})
    if int(freeze_audit.get("mismatch_count", -1)) != 0:
        errors.append("V7 final-freeze contract has mismatches")
    if freeze_audit.get("verified_source_count") != freeze_audit.get(
        "frozen_source_count"
    ):
        errors.append("not all frozen V7 sources were independently verified")
    if freeze_audit.get("verified_corpus_file_count") != freeze_audit.get(
        "frozen_corpus_file_count"
    ):
        errors.append("not all frozen V7 corpus files were independently verified")
    linkage = payload.get("generation_evaluation_linkage_audit", {})
    if linkage.get("generation_record_count") != 288:
        errors.append("formal generation record count is not 288")
    if linkage.get("evaluation_record_count") != 288:
        errors.append("formal evaluation record count is not 288")
    if linkage.get("linked_record_count") != 288:
        errors.append("not all formal generation/evaluation records are linked")
    if int(linkage.get("mismatch_count", -1)) != 0:
        errors.append("formal generation/evaluation linkage has mismatches")
    future = payload.get("future_experiment_go_no_go", {})
    if future.get("decision") != "no_go_for_immediate_paid_generation":
        errors.append("future experiment go/no-go decision is not the required no-go")
    if (
        future.get("conditional_protocol", {}).get("automatic_start_authorized")
        is not False
    ):
        errors.append("future paid protocol is not explicitly non-automatic")
    return sorted(set(errors))


def verify_analysis_directory(
    *,
    root: Path,
    analysis_dir: Path,
) -> dict[str, Any]:
    errors: list[str] = []
    missing = sorted(
        filename
        for filename in REQUIRED_REPORTS
        if not (analysis_dir / filename).is_file()
    )
    errors.extend(f"missing required artifact: {filename}" for filename in missing)
    payload_path = analysis_dir / "oracle_decomposition.json"
    payload: Mapping[str, Any] = {}
    if payload_path.is_file():
        try:
            payload = json.loads(payload_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"decomposition JSON is invalid: {exc}")
    if payload:
        errors.extend(verify_payload(payload, root=root, verify_files=True))
    report_path = analysis_dir / "analysis-report.md"
    if report_path.is_file():
        report = report_path.read_text(encoding="utf-8").lower()
        required_boundaries = (
            "does not establish graph superiority",
            "not an operational gxp compliance",
            "human-overseen",
            "no cross-version mean comparison",
        )
        for phrase in required_boundaries:
            if phrase not in report:
                errors.append(f"analysis report lacks boundary phrase: {phrase}")
    matrix_path = analysis_dir / "regulatory-alignment-matrix.md"
    if matrix_path.is_file():
        matrix = matrix_path.read_text(encoding="utf-8").lower()
        for phrase in (
            "architecture property",
            "benchmark proxy",
            "validated operational control",
            "formal compliance",
            "remaining human responsibility",
        ):
            if phrase not in matrix:
                errors.append(f"regulatory matrix lacks distinction: {phrase}")
    artifact_hashes = {
        path.relative_to(analysis_dir).as_posix(): sha256_file(path)
        for path in sorted(analysis_dir.rglob("*"))
        if path.is_file()
        and path.name not in {"artifact_hashes.json", "verification-report.md"}
    }
    return {
        "schema_version": "v7-oracle-verification-1",
        "passed": not errors,
        "errors": sorted(set(errors)),
        "artifact_hashes": artifact_hashes,
    }


def main() -> int:  # pragma: no cover - thin CLI wrapper
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--analysis-dir", type=Path, default=DEFAULT_ANALYSIS)
    parser.add_argument("--write-report", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    analysis_dir = args.analysis_dir.resolve()
    result = verify_analysis_directory(root=root, analysis_dir=analysis_dir)
    if args.write_report:
        (analysis_dir / "artifact_hashes.json").write_bytes(
            canonical_json_bytes(result["artifact_hashes"])
        )
        lines = [
            "# V7 Oracle Decomposition Verification",
            "",
            f"- Passed: `{str(result['passed']).lower()}`",
            f"- Error count: `{len(result['errors'])}`",
            f"- Hashed deterministic artifacts: `{len(result['artifact_hashes'])}`",
            "",
            "## Errors",
            "",
        ]
        lines.extend(
            [f"- {error}" for error in result["errors"]]
            or ["- No verification errors."]
        )
        (analysis_dir / "verification-report.md").write_text(
            "\n".join(lines) + "\n", encoding="utf-8", newline="\n"
        )
    print(json.dumps(result, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
