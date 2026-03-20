#!/usr/bin/env python3
"""SDTM Validator - Validate SDTM domains against CDISC standards."""

import sys
import yaml
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "_shared"))

from base_skill import (
    BaseCSPSkill,
    SkillConfig,
    SkillResult,
    SkillStatus,
    create_argument_parser,
)
from io_handlers import DatasetReader
from cdisc_utils import SDTMComplianceChecker, ComplianceIssue


class SDTMValidator(BaseCSPSkill):
    """Validate SDTM domain datasets."""

    GRAPH_NODE_ID = "sdtm-dm-mapping"
    REQUIRED_INPUT_VARS = []
    OUTPUT_VARS = ["validation_report"]
    SKILL_NAME = "sdtm-validator"
    SKILL_VERSION = "1.0.0"

    def __init__(self, config: SkillConfig):
        super().__init__(config)
        self.compliance_checker = SDTMComplianceChecker(strict=config.strict_mode)
        self.all_issues: List[ComplianceIssue] = []

    def run(self) -> SkillResult:
        """Execute SDTM validation."""
        self.log_info(f"Starting SDTM validation of {self.config.input_path}")

        if self.config.dry_run:
            return self._dry_run()

        # Find all SDTM datasets
        datasets = self._find_datasets()
        if not datasets:
            return self.create_result(SkillStatus.ERROR, "No SDTM datasets found")

        # Validate each dataset
        validation_results = {}
        for dataset_path, domain in datasets:
            result = self._validate_domain(dataset_path, domain)
            validation_results[domain] = result

        # Cross-domain validation
        cross_issues = self._cross_domain_validation(datasets)
        validation_results["CROSS_DOMAIN"] = {
            "issues": [asdict(i) for i in cross_issues]
        }

        # Generate report
        report = self._generate_report(validation_results)
        self._write_report(report)

        # Count issues by severity
        error_count = sum(1 for i in self.all_issues if i.severity == "ERROR")
        warning_count = sum(1 for i in self.all_issues if i.severity == "WARNING")

        self.metrics["datasets_validated"] = len(datasets)
        self.metrics["total_errors"] = error_count
        self.metrics["total_warnings"] = warning_count

        if error_count > 0:
            status = SkillStatus.ERROR
            message = (
                f"Validation failed: {error_count} errors, {warning_count} warnings"
            )
        elif warning_count > 0:
            status = SkillStatus.WARNING
            message = f"Validation passed with {warning_count} warnings"
        else:
            status = SkillStatus.SUCCESS
            message = f"All {len(datasets)} domains validated successfully"

        return self.create_result(
            status,
            message,
            outputs={
                "errors": error_count,
                "warnings": warning_count,
                "report": str(self.config.output_path),
            },
        )

    def _find_datasets(self) -> List[tuple]:
        """Find all SDTM datasets."""
        input_dir = self.config.input_path
        if not input_dir or not input_dir.exists():
            return []

        datasets = []
        for ext in [".xpt", ".csv", ".XPT", ".CSV"]:
            for path in input_dir.glob(f"*{ext}"):
                domain = path.stem.upper()
                if domain.startswith("SUPP"):
                    domain = "SUPPQUAL"
                datasets.append((path, domain))

        return sorted(datasets, key=lambda x: x[1])

    def _validate_domain(self, path: Path, domain: str) -> Dict[str, Any]:
        """Validate a single domain."""
        self.log_info(f"Validating {domain}...")

        try:
            reader = DatasetReader()
            data = reader.read(path)

            issues = self.compliance_checker.check(data, domain)
            self.all_issues.extend(issues)

            return {
                "file": str(path),
                "n_records": len(list(data.values())[0]) if data else 0,
                "n_variables": len(data),
                "issues": [asdict(i) for i in issues],
                "issue_count": {
                    "error": sum(1 for i in issues if i.severity == "ERROR"),
                    "warning": sum(1 for i in issues if i.severity == "WARNING"),
                    "info": sum(1 for i in issues if i.severity == "INFO"),
                },
            }

        except Exception as e:
            issue = ComplianceIssue(
                severity="ERROR",
                category="File Read",
                message=f"Could not read dataset: {e}",
            )
            self.all_issues.append(issue)
            return {"file": str(path), "issues": [asdict(issue)], "error": str(e)}

    def _cross_domain_validation(self, datasets: List[tuple]) -> List[ComplianceIssue]:
        """Perform cross-domain validation."""
        issues = []

        # Load DM for USUBJID reference
        dm_data = None
        for path, domain in datasets:
            if domain == "DM":
                reader = DatasetReader()
                dm_data = reader.read(path)
                break

        if not dm_data:
            issues.append(
                ComplianceIssue(
                    severity="WARNING",
                    category="Cross-Domain",
                    message="DM domain not found - cannot perform USUBJID reference validation",
                )
            )
            return issues

        dm_usubjids = set(dm_data.get("USUBJID", []))

        # Check all domains have USUBJIDs in DM
        for path, domain in datasets:
            if domain in ["DM", "TS", "TA", "TI", "TV"]:
                continue

            try:
                reader = DatasetReader()
                data = reader.read(path)
                domain_usubjids = set(data.get("USUBJID", []))
                missing_in_dm = domain_usubjids - dm_usubjids

                if missing_in_dm:
                    issues.append(
                        ComplianceIssue(
                            severity="ERROR",
                            category="Cross-Domain",
                            message=f"{domain}: {len(missing_in_dm)} USUBJIDs not found in DM",
                            details=list(missing_in_dm)[:10],
                        )
                    )
            except Exception:
                pass

        return issues

    def _generate_report(self, results: Dict) -> Dict[str, Any]:
        """Generate validation report."""
        return {
            "schema_version": 1,
            "validation_date": datetime.utcnow().isoformat(),
            "input_path": str(self.config.input_path),
            "summary": {
                "datasets_validated": len(results) - 1,  # Exclude CROSS_DOMAIN
                "total_errors": sum(
                    1 for i in self.all_issues if i.severity == "ERROR"
                ),
                "total_warnings": sum(
                    1 for i in self.all_issues if i.severity == "WARNING"
                ),
                "status": (
                    "PASS"
                    if not any(i.severity == "ERROR" for i in self.all_issues)
                    else "FAIL"
                ),
            },
            "domains": results,
        }

    def _write_report(self, report: Dict):
        """Write validation report."""
        output_path = self.config.output_path or Path("reports/sdtm-validation.yaml")
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
            yaml.dump(report, f, default_flow_style=False, sort_keys=False)

        self.log_info(f"Validation report written to {output_path}")

    def _dry_run(self) -> SkillResult:
        """Show what would be done."""
        datasets = self._find_datasets()
        return self.create_result(
            SkillStatus.DRY_RUN,
            f"Would validate {len(datasets)} SDTM domains",
            outputs={"datasets": [d[1] for d in datasets]},
        )


def main():
    parser = create_argument_parser("sdtm-validator", "Validate SDTM domains")
    parser.add_argument("--domain", "-d", help="Validate specific domain only")
    args = parser.parse_args()

    config = SkillConfig.from_args(args)
    skill = SDTMValidator(config)
    result = skill.run()

    print(result.to_json())
    sys.exit(0 if result.status in [SkillStatus.SUCCESS, SkillStatus.WARNING] else 1)


if __name__ == "__main__":
    main()
