#!/usr/bin/env python3
"""ADaM Validation - Validate ADaM datasets."""

import sys
from pathlib import Path
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "_shared"))

from base_skill import (
    BaseCSPSkill,
    SkillConfig,
    SkillResult,
    SkillStatus,
    create_argument_parser,
)


class ADAMValidation(BaseCSPSkill):
    """Validate ADaM datasets."""

    GRAPH_NODE_ID = "adam-validation"
    REQUIRED_INPUT_VARS = []
    OUTPUT_VARS = []
    SKILL_NAME = "adam-validation"
    SKILL_VERSION = "1.0.0"

    # Required ADSL variables per ADaM IG
    REQUIRED_ADSL_VARS = [
        "STUDYID",
        "USUBJID",
        "SUBJID",
        "SITEID",
        "TRT01P",
        "TRT01PN",
        "SAFFL",
    ]

    # Required ADAE variables
    REQUIRED_ADAE_VARS = ["STUDYID", "USUBJID", "AETERM", "AEDECOD", "TRTA", "SAFFL"]

    def run(self) -> SkillResult:
        """Execute ADaM validation."""
        self.log_info("Starting ADaM validation")

        if self.config.dry_run:
            return self._dry_run()

        input_dir = self.config.input_path or Path("output/adam")

        # Find ADaM datasets
        adam_files = list(input_dir.glob("*.xpt")) if input_dir.exists() else []

        if not adam_files:
            return self.create_result(SkillStatus.WARNING, "No ADaM datasets found")

        issues = []
        warnings = []
        validated = []

        for dataset_path in adam_files:
            domain = dataset_path.stem.upper()
            self.log_info(f"Validating {domain}")

            from io_handlers import DatasetReader

            reader = DatasetReader()
            data = reader.read(dataset_path)

            if not data:
                issues.append(f"{domain}: Could not read dataset")
                continue

            # Check required variables
            if domain == "ADSL":
                missing = [v for v in self.REQUIRED_ADSL_VARS if v not in data]
                if missing:
                    issues.append(f"ADSL missing required vars: {', '.join(missing)}")

                # Check one record per subject
                usubjids = data.get("USUBJID", [])
                if len(usubjids) != len(set(usubjids)):
                    issues.append("ADSL: Duplicate USUBJID found")

                # Check population flags
                if "SAFFL" in data:
                    saffl_y = sum(1 for f in data["SAFFL"] if f == "Y")
                    self.metrics["safety_pop"] = saffl_y

            elif domain == "ADAE":
                missing = [v for v in self.REQUIRED_ADAE_VARS if v not in data]
                if missing:
                    issues.append(f"ADAE missing required vars: {', '.join(missing)}")

            # Check variable types
            for var, values in data.items():
                if values and not isinstance(values, list):
                    warnings.append(
                        f"{domain}.{var}: Expected list, got {type(values).__name__}"
                    )

            validated.append(domain)

        # Write report
        report_path = Path("reports/adam-validation-report.txt")
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with open(report_path, "w") as f:
            f.write("ADaM VALIDATION REPORT\n")
            f.write("=" * 60 + "\n\n")
            f.write(f"Datasets validated: {len(validated)}\n")
            for d in validated:
                f.write(f"  - {d}\n")
            f.write(f"\nIssues: {len(issues)}\n")
            for issue in issues:
                f.write(f"  ERROR: {issue}\n")
            f.write(f"\nWarnings: {len(warnings)}\n")
            for warning in warnings:
                f.write(f"  WARNING: {warning}\n")

        status = (
            SkillStatus.ERROR
            if issues
            else SkillStatus.SUCCESS if validated else SkillStatus.WARNING
        )

        return self.create_result(
            status,
            f"Validated {len(validated)} ADaM datasets. Issues: {len(issues)}, Warnings: {len(warnings)}",
            outputs={
                "report": str(report_path),
                "issues": len(issues),
                "warnings": len(warnings),
            },
        )

    def _dry_run(self) -> SkillResult:
        return self.create_result(
            SkillStatus.DRY_RUN, "Would validate ADaM datasets", outputs={}
        )


def main():
    parser = create_argument_parser("adam-validation", "Validate ADaM datasets")
    args = parser.parse_args()
    config = SkillConfig.from_args(args)
    result = ADAMValidation(config).run()
    print(result.to_json())
    sys.exit(0 if result.status in [SkillStatus.SUCCESS, SkillStatus.WARNING] else 1)


if __name__ == "__main__":
    main()
