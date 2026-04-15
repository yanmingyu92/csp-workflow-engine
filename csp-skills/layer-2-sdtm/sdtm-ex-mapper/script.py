#!/usr/bin/env python3
"""SDTM EX Mapper - Map exposure/dosing data to SDTM EX domain."""

import sys
from pathlib import Path
from typing import Dict, List, Any

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "_shared"))

from base_skill import (
    BaseCSPSkill,
    SkillConfig,
    SkillResult,
    SkillStatus,
    create_argument_parser,
)


class SDTMEXMapper(BaseCSPSkill):
    """Map exposure/dosing data to SDTM EX domain."""

    GRAPH_NODE_ID = "sdtm-ex-mapping"
    REQUIRED_INPUT_VARS = ["USUBJID", "EXTRT", "EXDOSE"]
    OUTPUT_VARS = [
        "STUDYID",
        "DOMAIN",
        "USUBJID",
        "EXSEQ",
        "EXTRT",
        "EXDOSE",
        "EXDOSU",
        "EXROUTE",
    ]
    SKILL_NAME = "sdtm-ex-mapper"
    SKILL_VERSION = "1.0.0"

    def run(self) -> SkillResult:
        """Execute EX domain mapping."""
        self.log_info(f"Starting EX domain mapping from {self.config.input_path}")

        if self.config.dry_run:
            return self._dry_run()

        # Read raw EX data
        from io_handlers import DatasetReader

        reader = DatasetReader()
        raw_data = reader.read(self.config.input_path)

        if not raw_data:
            return self.create_result(SkillStatus.ERROR, "Could not read raw EX data")

        n_records = len(list(raw_data.values())[0])

        # Initialize EX domain columns
        ex_data = {
            var: []
            for var in [
                "STUDYID",
                "DOMAIN",
                "USUBJID",
                "EXSEQ",
                "EXSPID",
                "EXTRT",
                "EXDOSE",
                "EXDOSU",
                "EXROUTE",
                "EXLOT",
                "EXSTDTC",
                "EXENDTC",
                "EXDOSFRQ",
            ]
        }

        # Track first dose per subject for relative day calculation
        first_dose_dates: Dict[str, str] = {}

        # Map each record
        for i in range(n_records):
            studyid = self._get_val(raw_data, "STUDYID", i, "")
            siteid = self._get_val(raw_data, "SITEID", i, "")
            subjid = self._get_val(raw_data, "SUBJID", i, "")
            usubjid = self._get_val(
                raw_data, "USUBJID", i, f"{studyid}-{siteid}-{subjid}"
            )

            extrt = self._get_val(raw_data, "EXTRT", i, "")
            exdose = self._get_val(raw_data, "EXDOSE", i, 0)
            exstdtc = self._format_date(self._get_val(raw_data, "EXSTDTC", i, ""))

            # Track first dose
            if usubjid not in first_dose_dates and exstdtc:
                first_dose_dates[usubjid] = exstdtc

            ex_data["STUDYID"].append(studyid)
            ex_data["DOMAIN"].append("EX")
            ex_data["USUBJID"].append(usubjid)
            ex_data["EXSEQ"].append(i + 1)
            ex_data["EXSPID"].append(str(i + 1))
            ex_data["EXTRT"].append(extrt)
            ex_data["EXDOSE"].append(float(exdose) if exdose else 0)
            ex_data["EXDOSU"].append(self._get_val(raw_data, "EXDOSU", i, "mg"))
            ex_data["EXROUTE"].append(
                self._map_route(self._get_val(raw_data, "EXROUTE", i, ""))
            )
            ex_data["EXLOT"].append(self._get_val(raw_data, "EXLOT", i, ""))
            ex_data["EXSTDTC"].append(exstdtc)
            ex_data["EXENDTC"].append(
                self._format_date(self._get_val(raw_data, "EXENDTC", i, ""))
            )
            ex_data["EXDOSFRQ"].append(
                self._map_frequency(self._get_val(raw_data, "EXDOSFRQ", i, ""))
            )

        # Write output
        from io_handlers import DatasetWriter

        output_path = self.config.output_path or Path("output/sdtm/ex.xpt")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        writer = DatasetWriter()
        writer.write(
            ex_data, output_path, metadata={"domain": "EX", "label": "Exposure"}
        )

        self.metrics["ex_records"] = n_records
        self.metrics["subjects_dosed"] = len(first_dose_dates)

        return self.create_result(
            SkillStatus.SUCCESS,
            f"Mapped {n_records} exposure records for {self.metrics['subjects_dosed']} subjects",
            outputs={"output_file": str(output_path), "records": n_records},
        )

    def _get_val(self, data: Dict, var: str, idx: int, default: Any) -> Any:
        if var in data and idx < len(data[var]):
            val = data[var][idx]
            return val if val is not None and val != "" else default
        return default

    def _map_route(self, val: str) -> str:
        mapping = {
            "oral": "ORAL",
            "iv": "INTRAVENOUS",
            "intravenous": "INTRAVENOUS",
            "sc": "SUBCUTANEOUS",
            "subcutaneous": "SUBCUTANEOUS",
            "im": "INTRAMUSCULAR",
            "intramuscular": "INTRAMUSCULAR",
            "topical": "TOPICAL",
            "transdermal": "TRANSDERMAL",
        }
        return mapping.get(str(val).lower(), str(val).upper() if val else "")

    def _map_frequency(self, val: str) -> str:
        mapping = {
            "qd": "ONCE",
            "once daily": "ONCE",
            "bid": "TWICE",
            "twice daily": "TWICE",
            "tid": "3 TIMES",
            "three times daily": "3 TIMES",
            "qid": "4 TIMES",
            "q4h": "EVERY 4 HOURS",
            "q6h": "EVERY 6 HOURS",
            "q8h": "EVERY 8 HOURS",
            "qw": "ONCE WEEKLY",
            "weekly": "ONCE WEEKLY",
        }
        return mapping.get(str(val).lower(), str(val).upper() if val else "")

    def _format_date(self, val: str) -> str:
        return str(val).replace("/", "-") if val else ""

    def _dry_run(self) -> SkillResult:
        return self.create_result(
            SkillStatus.DRY_RUN, "Would map EX domain", outputs={}
        )


def main():
    parser = create_argument_parser(
        "sdtm-ex-mapper", "Map exposure/dosing to SDTM EX domain"
    )
    args = parser.parse_args()
    config = SkillConfig.from_args(args)
    result = SDTMEXMapper(config).run()
    print(result.to_json())
    sys.exit(0 if result.status in [SkillStatus.SUCCESS, SkillStatus.WARNING] else 1)


if __name__ == "__main__":
    main()
