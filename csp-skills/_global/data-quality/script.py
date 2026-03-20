#!/usr/bin/env python3
"""Data Quality Checker - Universal data quality checking at any pipeline stage."""

import sys
from pathlib import Path
from typing import Dict, List, Any, Optional

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "_shared"))

from base_skill import (
    BaseCSPSkill,
    SkillConfig,
    SkillResult,
    SkillStatus,
    create_argument_parser,
)


class DataQualityChecker(BaseCSPSkill):
    """Universal data quality checking — adapts to current graph layer."""

    GRAPH_NODE_ID = "_global_data_quality"
    REQUIRED_INPUT_VARS = ["INPUT_PATH"]
    OUTPUT_VARS = ["QUALITY_SCORE", "ISSUES", "STATUS"]
    SKILL_NAME = "data-quality"
    SKILL_VERSION = "1.0.0"

    def run(self) -> SkillResult:
        """Execute data quality checks."""
        self.log_info(f"Running data quality checks on {self.config.input_path}")

        if self.config.dry_run:
            return self.create_result(SkillStatus.DRY_RUN, "Would run quality checks")

        input_path = self.config.input_path
        if not input_path or not Path(input_path).exists():
            return self.create_result(
                SkillStatus.ERROR, f"Input not found: {input_path}"
            )

        # Load data
        from io_handlers import DatasetReader

        reader = DatasetReader()

        if Path(input_path).is_file():
            data = reader.read(Path(input_path))
            if not data:
                return self.create_result(SkillStatus.ERROR, "Could not read dataset")
            results = self._check_dataset(data, Path(input_path).name)
        else:
            # Directory: check all datasets
            results = {"datasets": [], "overall_score": 0, "total_issues": 0}
            files = list(Path(input_path).glob("*.xpt")) + list(
                Path(input_path).glob("*.csv")
            )
            for f in files:
                data = reader.read(f)
                if data:
                    ds_result = self._check_dataset(data, f.name)
                    results["datasets"].append(ds_result)
                    results["total_issues"] += ds_result.get("issue_count", 0)
            if results["datasets"]:
                results["overall_score"] = sum(
                    d.get("quality_score", 0) for d in results["datasets"]
                ) / len(results["datasets"])

        score = results.get("overall_score", results.get("quality_score", 0))
        issue_count = results.get("total_issues", results.get("issue_count", 0))
        status = SkillStatus.SUCCESS if score >= 80 else SkillStatus.WARNING

        return self.create_result(
            status,
            f"Quality score: {score:.0f}/100 | Issues: {issue_count}",
            outputs=results,
        )

    def _check_dataset(self, data: Dict, name: str) -> Dict[str, Any]:
        """Run quality checks on a single dataset."""
        issues = []
        n_vars = len(data)
        n_records = len(list(data.values())[0]) if data else 0

        # 1. Completeness checks
        for var_name, values in data.items():
            total = len(values)
            missing = sum(1 for v in values if v is None or str(v).strip() == "")
            if total > 0:
                miss_pct = missing / total * 100
                if miss_pct > 50:
                    issues.append(
                        {
                            "check": "completeness",
                            "severity": "ERROR",
                            "variable": var_name,
                            "detail": f"{miss_pct:.1f}% missing",
                        }
                    )
                elif miss_pct > 10:
                    issues.append(
                        {
                            "check": "completeness",
                            "severity": "WARNING",
                            "variable": var_name,
                            "detail": f"{miss_pct:.1f}% missing",
                        }
                    )

        # 2. Consistency checks
        if "USUBJID" in data:
            # Check for duplicate records
            ids = data["USUBJID"]
            unique_ids = set(ids)
            if len(ids) != len(unique_ids):
                dup_count = len(ids) - len(unique_ids)
                issues.append(
                    {
                        "check": "consistency",
                        "severity": "WARNING",
                        "variable": "USUBJID",
                        "detail": f"{dup_count} duplicate subject IDs",
                    }
                )

        # 3. Date conformance
        date_vars = [v for v in data.keys() if v.endswith("DTC") or v.endswith("DT")]
        for dv in date_vars:
            for val in data[dv]:
                if val and str(val).strip():
                    # Basic ISO 8601 check
                    s = str(val).strip()
                    if len(s) >= 10 and s[4] != "-":
                        issues.append(
                            {
                                "check": "conformance",
                                "severity": "ERROR",
                                "variable": dv,
                                "detail": f"Non-ISO date: {s[:20]}",
                            }
                        )
                        break

        # Compute score
        error_count = sum(1 for i in issues if i["severity"] == "ERROR")
        warn_count = sum(1 for i in issues if i["severity"] == "WARNING")
        score = max(0, 100 - error_count * 15 - warn_count * 5)

        return {
            "dataset": name,
            "records": n_records,
            "variables": n_vars,
            "quality_score": score,
            "issue_count": len(issues),
            "errors": error_count,
            "warnings": warn_count,
            "issues": issues[:20],  # Cap reported issues
        }


def main():
    parser = create_argument_parser("data-quality", "Universal data quality checker")
    args = parser.parse_args()
    config = SkillConfig.from_args(args)
    result = DataQualityChecker(config).run()
    print(result.to_json())
    sys.exit(0 if result.status in [SkillStatus.SUCCESS, SkillStatus.WARNING] else 1)


if __name__ == "__main__":
    main()
