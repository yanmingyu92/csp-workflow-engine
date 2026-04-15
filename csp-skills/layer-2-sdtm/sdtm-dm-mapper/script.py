#!/usr/bin/env python3
"""SDTM DM Mapper - Map raw demographics to SDTM DM domain."""

import sys
import yaml
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict, field

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "_shared"))

from base_skill import (
    BaseCSPSkill,
    SkillConfig,
    SkillResult,
    SkillStatus,
    create_argument_parser,
)
from io_handlers import CSVHandler, DatasetReader, DatasetWriter
from validators import CDISCTermValidator, VariableValidator, ValidationResult
from cdisc_utils import SDTMComplianceChecker, ComplianceIssue


@dataclass
class DMRecord:
    """SDTM DM domain record."""

    STUDYID: str
    DOMAIN: str = "DM"
    USUBJID: str = ""
    SUBJID: str = ""
    SITEID: str = ""
    AGE: int = None
    AGEU: str = "YEARS"
    SEX: str = ""
    RACE: str = ""
    ETHNIC: str = ""
    ARM: str = ""
    ARMCD: str = ""
    ACTARM: str = ""
    ACTARMCD: str = ""
    COUNTRY: str = ""
    RFSTDTC: str = ""
    RFENDTC: str = ""


class SDTMDMMapper(BaseCSPSkill):
    """Map raw demographics data to SDTM DM domain."""

    GRAPH_NODE_ID = "sdtm-dm-mapping"
    REQUIRED_INPUT_VARS = ["STUDYID", "SUBJID", "SITEID", "AGE", "SEX"]
    OUTPUT_VARS = [
        "STUDYID",
        "DOMAIN",
        "USUBJID",
        "SUBJID",
        "AGE",
        "SEX",
        "RACE",
        "ARM",
    ]
    SKILL_NAME = "sdtm-dm-mapper"
    SKILL_VERSION = "1.0.0"

    # CDISC CT mappings
    SEX_MAP = {
        "M": "M",
        "MALE": "M",
        "F": "F",
        "FEMALE": "F",
        "U": "U",
        "UNKNOWN": "U",
    }

    RACE_MAP = {
        "WHITE": "WHITE",
        "BLACK OR AFRICAN AMERICAN": "BLACK OR AFRICAN AMERICAN",
        "BLACK": "BLACK OR AFRICAN AMERICAN",
        "ASIAN": "ASIAN",
        "AMERICAN INDIAN": "AMERICAN INDIAN OR ALASKA NATIVE",
        "NATIVE HAWAIIAN": "NATIVE HAWAIIAN OR OTHER PACIFIC ISLANDER",
        "PACIFIC ISLANDER": "NATIVE HAWAIIAN OR OTHER PACIFIC ISLANDER",
        "MULTIPLE": "MULTIPLE",
        "OTHER": "OTHER",
    }

    def __init__(self, config: SkillConfig):
        super().__init__(config)
        self.ct_validator = CDISCTermValidator()
        self.sdtm_checker = SDTMComplianceChecker()
        self.validator = VariableValidator()

    def run(self) -> SkillResult:
        """Execute DM domain mapping."""
        self.log_info(f"Starting DM domain mapping from {self.config.input_path}")

        if self.config.dry_run:
            return self._dry_run()

        # Load mapping specification
        spec = self._load_spec()

        # Read raw demographics data
        raw_data = self._read_raw_data()
        if not raw_data:
            return self.create_result(
                SkillStatus.ERROR, "Could not read raw demographics data"
            )

        # Validate raw data
        validation_issues = self._validate_raw_data(raw_data)
        if validation_issues and self.config.strict_mode:
            return self.create_result(
                SkillStatus.ERROR,
                f"Raw data validation failed: {len(validation_issues)} issues",
                outputs={"issues": [asdict(i) for i in validation_issues]},
            )

        # Map to DM domain
        dm_data = self._map_to_dm(raw_data, spec)

        # Validate DM output
        dm_issues = self._validate_dm_output(dm_data)
        self.warnings.extend([i.message for i in dm_issues if i.severity == "WARNING"])

        # Write output
        output_path = self._write_dm_domain(dm_data)

        # Build result metrics
        self.metrics["subjects_mapped"] = len(dm_data.get("USUBJID", []))
        self.metrics["validation_issues"] = len(validation_issues) + len(dm_issues)
        self.metrics["unique_usubjids"] = len(set(dm_data.get("USUBJID", [])))

        status = SkillStatus.WARNING if dm_issues else SkillStatus.SUCCESS
        return self.create_result(
            status,
            f"Mapped {self.metrics['subjects_mapped']} subjects to DM domain",
            outputs={
                "output_file": str(output_path),
                "subjects": self.metrics["subjects_mapped"],
                "issues": len(dm_issues),
            },
        )

    def _load_spec(self) -> Dict:
        """Load mapping specification."""
        spec_path = self.config.spec_path or Path("specs/sdtm-mapping-spec.yaml")
        if spec_path.exists():
            with open(spec_path, "r") as f:
                return yaml.safe_load(f) or {}
        return {}

    def _read_raw_data(self) -> Optional[Dict[str, List]]:
        """Read raw demographics data."""
        reader = DatasetReader()
        try:
            return reader.read(self.config.input_path)
        except Exception as e:
            self.log_error(f"Failed to read input: {e}")
            return None

    def _validate_raw_data(self, data: Dict) -> List[ComplianceIssue]:
        """Validate raw demographics data."""
        issues = []

        # Check required variables
        for var in self.REQUIRED_INPUT_VARS:
            if var not in data:
                issues.append(
                    ComplianceIssue(
                        severity="ERROR",
                        category="Missing Variable",
                        message=f"Required variable '{var}' not found in raw data",
                        variable=var,
                    )
                )

        # Check for missing values in required fields
        n_records = len(list(data.values())[0]) if data else 0
        for var in self.REQUIRED_INPUT_VARS:
            if var in data:
                missing = sum(1 for v in data[var] if v is None or v == "")
                if missing > 0:
                    issues.append(
                        ComplianceIssue(
                            severity="WARNING",
                            category="Missing Values",
                            message=f"{missing} missing values in {var}",
                            variable=var,
                        )
                    )

        return issues

    def _map_to_dm(self, raw_data: Dict, spec: Dict) -> Dict[str, List]:
        """Map raw data to SDTM DM domain."""
        n_records = len(list(raw_data.values())[0]) if raw_data else 0

        # Initialize output columns
        dm_data = {
            var: []
            for var in [
                "STUDYID",
                "DOMAIN",
                "USUBJID",
                "SUBJID",
                "SITEID",
                "AGE",
                "AGEU",
                "SEX",
                "RACE",
                "ETHNIC",
                "ARM",
                "ARMCD",
                "ACTARM",
                "ACTARMCD",
                "COUNTRY",
                "RFSTDTC",
                "RFENDTC",
            ]
        }

        for i in range(n_records):
            # Get raw values
            studyid = self._get_value(raw_data, "STUDYID", i, "")
            siteid = self._get_value(raw_data, "SITEID", i, "")
            subjid = self._get_value(raw_data, "SUBJID", i, "")

            # Derive USUBJID
            usubjid = f"{studyid}-{siteid}-{subjid}"

            # Map SEX
            sex_raw = str(self._get_value(raw_data, "SEX", i, "")).upper()
            sex = self.SEX_MAP.get(sex_raw, "U")

            # Map RACE
            race_raw = str(self._get_value(raw_data, "RACE", i, "")).upper()
            race = self.RACE_MAP.get(race_raw, race_raw)

            # Get ARM and derive ARMCD
            arm = self._get_value(raw_data, "ARM", i, "")
            armcd = self._get_value(raw_data, "ARMCD", i, "")
            if not armcd and arm:
                armcd = arm[:8].upper()

            # Build DM record
            dm_data["STUDYID"].append(studyid)
            dm_data["DOMAIN"].append("DM")
            dm_data["USUBJID"].append(usubjid)
            dm_data["SUBJID"].append(subjid)
            dm_data["SITEID"].append(siteid)
            dm_data["AGE"].append(self._get_numeric(raw_data, "AGE", i))
            dm_data["AGEU"].append("YEARS")
            dm_data["SEX"].append(sex)
            dm_data["RACE"].append(race)
            dm_data["ETHNIC"].append(self._get_value(raw_data, "ETHNIC", i, ""))
            dm_data["ARM"].append(arm)
            dm_data["ARMCD"].append(armcd)
            dm_data["ACTARM"].append(self._get_value(raw_data, "ACTARM", i, arm))
            dm_data["ACTARMCD"].append(self._get_value(raw_data, "ACTARMCD", i, armcd))
            dm_data["COUNTRY"].append(self._get_value(raw_data, "COUNTRY", i, "USA"))
            dm_data["RFSTDTC"].append("")  # Populated from EX
            dm_data["RFENDTC"].append("")  # Populated from EX

        return dm_data

    def _get_value(self, data: Dict, var: str, idx: int, default: Any) -> Any:
        """Get value from data with default."""
        if var in data and idx < len(data[var]):
            val = data[var][idx]
            return val if val is not None and val != "" else default
        return default

    def _get_numeric(self, data: Dict, var: str, idx: int) -> Optional[int]:
        """Get numeric value from data."""
        val = self._get_value(data, var, idx, None)
        if val is None:
            return None
        try:
            return int(float(val))
        except (ValueError, TypeError):
            return None

    def _validate_dm_output(self, dm_data: Dict) -> List[ComplianceIssue]:
        """Validate DM domain output."""
        issues = self.sdtm_checker.check(dm_data, "DM")

        # Check USUBJID uniqueness
        usubjids = dm_data.get("USUBJID", [])
        if len(usubjids) != len(set(usubjids)):
            issues.append(
                ComplianceIssue(
                    severity="ERROR",
                    category="Duplicate Keys",
                    message="Duplicate USUBJIDs found",
                    variable="USUBJID",
                )
            )

        # Validate SEX against CDISC CT
        for i, sex in enumerate(dm_data.get("SEX", [])):
            if sex:
                result = self.ct_validator.validate(sex, "sex")
                if not result.is_valid:
                    issues.append(
                        ComplianceIssue(
                            severity="WARNING",
                            category="Controlled Terminology",
                            message=f"Invalid SEX value at record {i+1}: {sex}",
                            variable="SEX",
                            record=i + 1,
                        )
                    )

        return issues

    def _write_dm_domain(self, dm_data: Dict) -> Path:
        """Write DM domain to output file."""
        output_path = self.config.output_path or Path("output/sdtm/dm.xpt")
        output_path.parent.mkdir(parents=True, exist_ok=True)

        writer = DatasetWriter(output_format=self.config.output_format)
        writer.write(
            dm_data,
            output_path,
            metadata={
                "domain": "DM",
                "label": "Demographics",
            },
        )

        self.log_info(f"DM domain written to {output_path}")
        return output_path

    def _dry_run(self) -> SkillResult:
        """Show what would be done."""
        raw_data = self._read_raw_data()
        n_records = len(list(raw_data.values())[0]) if raw_data else 0

        return self.create_result(
            SkillStatus.DRY_RUN,
            f"Would map {n_records} records to DM domain",
            outputs={"input_records": n_records},
        )


def create_parser() -> argparse.ArgumentParser:
    """Create argument parser."""
    parser = create_argument_parser(
        "sdtm-dm-mapper", "Map raw demographics to SDTM DM domain"
    )
    parser.add_argument("--spec", "-s", help="Mapping specification file")
    return parser


def main():
    """Main entry point."""
    parser = create_parser()
    args = parser.parse_args()

    config = SkillConfig.from_args(args)
    skill = SDTMDMMapper(config)
    result = skill.run()

    print(result.to_json())
    sys.exit(
        0
        if result.status
        in [SkillStatus.SUCCESS, SkillStatus.WARNING, SkillStatus.DRY_RUN]
        else 1
    )


if __name__ == "__main__":
    main()
