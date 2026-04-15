#!/usr/bin/env python3
"""SDTM DS Mapper - Map disposition data to SDTM DS domain."""

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


class SDTMDSMapper(BaseCSPSkill):
    """Map disposition data to SDTM DS domain."""

    GRAPH_NODE_ID = "sdtm-ds-mapping"
    REQUIRED_INPUT_VARS = ["USUBJID", "DSTERM"]
    OUTPUT_VARS = ["STUDYID", "DOMAIN", "USUBJID", "DSSEQ", "DSTERM", "DSDECOD"]
    SKILL_NAME = "sdtm-ds-mapper"
    SKILL_VERSION = "1.0.0"

    # Standard disposition terms per CDISC
    STANDARD_DISPOSITION_TERMS = {
        "completed": "COMPLETED",
        "completed study": "COMPLETED",
        "discontinued": "DISCONTINUED",
        "screen failure": "SCREEN FAILURE",
        "screen failure - ineligible": "SCREEN FAILURE",
        "adverse event": "ADVERSE EVENT",
        "ae": "ADVERSE EVENT",
        "withdrawal by subject": "WITHDRAWAL BY SUBJECT",
        "subject withdrawal": "WITHDRAWAL BY SUBJECT",
        "protocol violation": "PROTOCOL VIOLATION",
        "lost to follow up": "LOST TO FOLLOW-UP",
        "ltfu": "LOST TO FOLLOW-UP",
        "death": "DEATH",
        "physician decision": "PHYSICIAN DECISION",
        "sponsor decision": "SPONSOR DECISION",
        "lack of efficacy": "LACK OF EFFICACY",
    }

    def run(self) -> SkillResult:
        """Execute DS domain mapping."""
        self.log_info(f"Starting DS domain mapping from {self.config.input_path}")

        if self.config.dry_run:
            return self._dry_run()

        # Read raw DS data
        from io_handlers import DatasetReader

        reader = DatasetReader()
        raw_data = reader.read(self.config.input_path)

        if not raw_data:
            return self.create_result(SkillStatus.ERROR, "Could not read raw DS data")

        n_records = len(list(raw_data.values())[0])

        # Initialize DS domain columns
        ds_data = {
            var: []
            for var in [
                "STUDYID",
                "DOMAIN",
                "USUBJID",
                "DSSEQ",
                "DSSPID",
                "DSTERM",
                "DSDECOD",
                "DSCAT",
                "DSSCAT",
                "DSSTDTC",
                "DSENDTC",
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

            dsterm = self._get_val(raw_data, "DSTERM", i, "")
            dsdecod = self._get_val(
                raw_data, "DSDECOD", i, self._standardize_term(dsterm)
            )

            ds_data["STUDYID"].append(studyid)
            ds_data["DOMAIN"].append("DS")
            ds_data["USUBJID"].append(usubjid)
            ds_data["DSSEQ"].append(i + 1)
            ds_data["DSSPID"].append(str(i + 1))
            ds_data["DSTERM"].append(dsterm)
            ds_data["DSDECOD"].append(dsdecod)
            ds_data["DSCAT"].append(self._get_val(raw_data, "DSCAT", i, "DISPOSITION"))
            ds_data["DSSCAT"].append(self._get_val(raw_data, "DSSCAT", i, ""))
            ds_data["DSSTDTC"].append(
                self._format_date(self._get_val(raw_data, "DSSTDTC", i, ""))
            )
            ds_data["DSENDTC"].append(
                self._format_date(self._get_val(raw_data, "DSENDTC", i, ""))
            )

        # Write output
        from io_handlers import DatasetWriter

        output_path = self.config.output_path or Path("output/sdtm/ds.xpt")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        writer = DatasetWriter()
        writer.write(
            ds_data, output_path, metadata={"domain": "DS", "label": "Disposition"}
        )

        self.metrics["ds_records"] = n_records
        self.metrics["subjects_with_disposition"] = len(set(ds_data["USUBJID"]))
        self.metrics["completed"] = sum(
            1 for d in ds_data["DSDECOD"] if d == "COMPLETED"
        )

        return self.create_result(
            SkillStatus.SUCCESS,
            f"Mapped {n_records} disposition records for {self.metrics['subjects_with_disposition']} subjects",
            outputs={"output_file": str(output_path), "records": n_records},
        )

    def _get_val(self, data: Dict, var: str, idx: int, default: Any) -> Any:
        if var in data and idx < len(data[var]):
            val = data[var][idx]
            return val if val is not None and val != "" else default
        return default

    def _standardize_term(self, term: str) -> str:
        """Map verbatim term to standard CDISC disposition term."""
        term_lower = str(term).lower().strip()
        return self.STANDARD_DISPOSITION_TERMS.get(
            term_lower, term.upper() if term else ""
        )

    def _format_date(self, val: str) -> str:
        return str(val).replace("/", "-") if val else ""

    def _dry_run(self) -> SkillResult:
        return self.create_result(
            SkillStatus.DRY_RUN, "Would map DS domain", outputs={}
        )


def main():
    parser = create_argument_parser(
        "sdtm-ds-mapper", "Map disposition to SDTM DS domain"
    )
    args = parser.parse_args()
    config = SkillConfig.from_args(args)
    result = SDTMDSMapper(config).run()
    print(result.to_json())
    sys.exit(0 if result.status in [SkillStatus.SUCCESS, SkillStatus.WARNING] else 1)


if __name__ == "__main__":
    main()
