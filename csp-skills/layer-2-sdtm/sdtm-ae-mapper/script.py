#!/usr/bin/env python3
"""SDTM AE Mapper - Map adverse events to SDTM AE domain."""

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


class SDTMAEMapper(BaseCSPSkill):
    """Map adverse event data to SDTM AE domain."""

    GRAPH_NODE_ID = "sdtm-ae-mapping"
    REQUIRED_INPUT_VARS = ["USUBJID", "AETERM"]
    OUTPUT_VARS = ["STUDYID", "DOMAIN", "USUBJID", "AESEQ", "AETERM", "AEDECOD"]
    SKILL_NAME = "sdtm-ae-mapper"
    SKILL_VERSION = "1.0.0"

    def run(self) -> SkillResult:
        """Execute AE domain mapping."""
        self.log_info(f"Starting AE domain mapping from {self.config.input_path}")

        if self.config.dry_run:
            return self._dry_run()

        # Read raw AE data
        from io_handlers import DatasetReader

        reader = DatasetReader()
        raw_data = reader.read(self.config.input_path)

        if not raw_data:
            return self.create_result(SkillStatus.ERROR, "Could not read raw AE data")

        n_records = len(list(raw_data.values())[0])

        # Initialize AE domain columns
        ae_data = {
            var: []
            for var in [
                "STUDYID",
                "DOMAIN",
                "USUBJID",
                "AESEQ",
                "AESPID",
                "AETERM",
                "AEDECOD",
                "AEBODSYS",
                "AESEV",
                "AESER",
                "AEREL",
                "AEOUT",
                "AESTDTC",
                "AEENDTC",
            ]
        }

        # Map each record
        for i in range(n_records):
            studyid = self._get_val(raw_data, "STUDYID", i, "")
            siteid = self._get_val(raw_data, "SITEID", i, "")
            subjid = self._get_val(raw_data, "SUBJID", i, "")
            usubjid = self._get_val(
                raw_data, "USUBJID", i, f"{studyid}-{siteid}-{subjid}"
            )

            aeterm = self._get_val(raw_data, "AETERM", i, "")

            # MedDRA coding (mock - would use actual MedDRA in production)
            aedecod = self._get_val(
                raw_data, "AEDECOD", i, self._mock_meddra_pt(aeterm)
            )
            aebodsys = self._get_val(
                raw_data, "AEBODSYS", i, self._mock_meddra_soc(aeterm)
            )

            ae_data["STUDYID"].append(studyid)
            ae_data["DOMAIN"].append("AE")
            ae_data["USUBJID"].append(usubjid)
            ae_data["AESEQ"].append(i + 1)
            ae_data["AESPID"].append(str(i + 1))
            ae_data["AETERM"].append(aeterm)
            ae_data["AEDECOD"].append(aedecod)
            ae_data["AEBODSYS"].append(aebodsys)
            ae_data["AESEV"].append(
                self._map_severity(self._get_val(raw_data, "AESEV", i, "MILD"))
            )
            ae_data["AESER"].append(
                self._map_yn(self._get_val(raw_data, "AESER", i, "N"))
            )
            ae_data["AEREL"].append(
                self._map_relationship(
                    self._get_val(raw_data, "AEREL", i, "NOT RELATED")
                )
            )
            ae_data["AEOUT"].append(self._get_val(raw_data, "AEOUT", i, ""))
            ae_data["AESTDTC"].append(
                self._format_date(self._get_val(raw_data, "AESTDTC", i, ""))
            )
            ae_data["AEENDTC"].append(
                self._format_date(self._get_val(raw_data, "AEENDTC", i, ""))
            )

        # Write output
        from io_handlers import DatasetWriter

        output_path = self.config.output_path or Path("output/sdtm/ae.xpt")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        writer = DatasetWriter()
        writer.write(
            ae_data, output_path, metadata={"domain": "AE", "label": "Adverse Events"}
        )

        self.metrics["ae_records"] = n_records
        self.metrics["subjects_with_ae"] = len(set(ae_data["USUBJID"]))

        return self.create_result(
            SkillStatus.SUCCESS,
            f"Mapped {n_records} adverse events for {self.metrics['subjects_with_ae']} subjects",
            outputs={"output_file": str(output_path), "records": n_records},
        )

    def _get_val(self, data: Dict, var: str, idx: int, default: Any) -> Any:
        if var in data and idx < len(data[var]):
            val = data[var][idx]
            return val if val is not None and val != "" else default
        return default

    def _map_severity(self, val: str) -> str:
        mapping = {"mild": "MILD", "moderate": "MODERATE", "severe": "SEVERE"}
        return mapping.get(str(val).upper(), "MILD")

    def _map_yn(self, val: str) -> str:
        return "Y" if str(val).upper() in ["Y", "YES", "1", "TRUE"] else "N"

    def _map_relationship(self, val: str) -> str:
        mapping = {
            "related": "RELATED",
            "not related": "NOT RELATED",
            "unknown": "UNKNOWN",
        }
        return mapping.get(str(val).upper(), "NOT RELATED")

    def _format_date(self, val: str) -> str:
        # Basic ISO 8601 formatting
        return str(val).replace("/", "-") if val else ""

    def _mock_meddra_pt(self, term: str) -> str:
        # Mock MedDRA coding - production would use actual MedDRA dictionary
        return term.upper()[:50] if term else ""

    def _mock_meddra_soc(self, term: str) -> str:
        # Mock SOC - production would use actual MedDRA
        return "GENERAL DISORDERS" if term else ""

    def _dry_run(self) -> SkillResult:
        return self.create_result(
            SkillStatus.DRY_RUN, "Would map AE domain", outputs={}
        )


def main():
    parser = create_argument_parser(
        "sdtm-ae-mapper", "Map adverse events to SDTM AE domain"
    )
    args = parser.parse_args()
    config = SkillConfig.from_args(args)
    result = SDTMAEMapper(config).run()
    print(result.to_json())
    sys.exit(0 if result.status in [SkillStatus.SUCCESS, SkillStatus.WARNING] else 1)


if __name__ == "__main__":
    main()
