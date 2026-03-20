#!/usr/bin/env python3
"""ADTTE Builder - Build ADTTE time-to-event analysis dataset."""

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


class ADTTEBuilder(BaseCSPSkill):
    """Build ADTTE time-to-event analysis dataset."""

    GRAPH_NODE_ID = "adam-adtte-build"
    REQUIRED_INPUT_VARS = ["USUBJID"]
    OUTPUT_VARS = ["USUBJID", "PARAM", "PARAMCD", "AVAL", "CNSR", "ADT"]
    SKILL_NAME = "adtte-builder"
    SKILL_VERSION = "1.0.0"

    # Standard TTE parameters
    TTE_PARAMS = [
        {
            "paramcd": "TTDEATH",
            "param": "Time to Death (Days)",
            "event_source": "DS",
            "event_decod": "DEATH",
        },
        {
            "paramcd": "TTDISC",
            "param": "Time to Discontinuation (Days)",
            "event_source": "DS",
            "event_decod": "DISCONTINUED",
        },
        {
            "paramcd": "TTFSAE",
            "param": "Time to First SAE (Days)",
            "event_source": "AE",
            "event_flag": "AESER",
        },
    ]

    def run(self) -> SkillResult:
        """Execute ADTTE building."""
        self.log_info("Starting ADTTE build")

        if self.config.dry_run:
            return self._dry_run()

        # Read source data
        input_dir = self.config.input_path or Path("output")
        adsl_data = self._read_dataset(input_dir / "adam" / "adsl.xpt")
        ds_data = self._read_dataset(input_dir / "sdtm" / "ds.xpt")
        ae_data = self._read_dataset(input_dir / "sdtm" / "ae.xpt")

        if not adsl_data:
            return self.create_result(SkillStatus.ERROR, "Could not read ADSL")

        # Initialize ADTTE
        adtte_data = {
            "STUDYID": [],
            "USUBJID": [],
            "SUBJID": [],
            "PARAM": [],
            "PARAMCD": [],
            "PARAMN": [],
            "AVAL": [],
            "AVALU": [],
            "CNSR": [],
            "ADT": [],
            "ADTF": [],
            "EVNTDESC": [],
            "CNSDTDSC": [],
            "TRTP": [],
            "TRTPN": [],
            "TRTA": [],
            "TRTAN": [],
            "SAFFL": [],
            "ITTFL": [],
        }

        # Build ADSL lookup
        adsl_lookup = self._build_lookup(adsl_data)
        ds_lookup = self._build_event_lookup(ds_data, "DSDECOD") if ds_data else {}
        ae_lookup = self._build_ae_lookup(ae_data) if ae_data else {}

        # Process each subject and parameter
        for i, usubjid in enumerate(adsl_data.get("USUBJID", [])):
            sl = adsl_lookup.get(usubjid, {})
            trtsdt = sl.get("TRTSDT", "")
            saffl = sl.get("SAFFL", "")

            if saffl != "Y":
                continue  # Skip non-safety subjects

            for pnum, param in enumerate(self.TTE_PARAMS, 1):
                adtte_data["STUDYID"].append(adsl_data.get("STUDYID", [""])[0])
                adtte_data["USUBJID"].append(usubjid)
                adtte_data["SUBJID"].append(sl.get("SUBJID", ""))
                adtte_data["PARAM"].append(param["param"])
                adtte_data["PARAMCD"].append(param["paramcd"])
                adtte_data["PARAMN"].append(pnum)
                adtte_data["AVALU"].append("DAYS")
                adtte_data["TRTP"].append(sl.get("TRT01P", ""))
                adtte_data["TRTPN"].append(sl.get("TRT01PN", ""))
                adtte_data["TRTA"].append(sl.get("TRT01A", ""))
                adtte_data["TRTAN"].append(sl.get("TRT01AN", ""))
                adtte_data["SAFFL"].append(saffl)
                adtte_data["ITTFL"].append(sl.get("ITTFL", ""))

                # Calculate time-to-event
                event_date, event_desc = self._find_event(
                    usubjid, param, ds_lookup, ae_lookup, sl
                )

                if event_date and trtsdt:
                    adtte_data["AVAL"].append(self._calc_days(trtsdt, event_date))
                    adtte_data["CNSR"].append(0)
                    adtte_data["ADT"].append(event_date)
                    adtte_data["EVNTDESC"].append(event_desc)
                    adtte_data["CNSDTDSC"].append("")
                else:
                    # Censored
                    eosdt = sl.get("EOSDT", "") or self._get_cutoff_date()
                    adtte_data["AVAL"].append(
                        self._calc_days(trtsdt, eosdt) if trtsdt else 0
                    )
                    adtte_data["CNSR"].append(1)
                    adtte_data["ADT"].append(eosdt)
                    adtte_data["EVNTDESC"].append("")
                    adtte_data["CNSDTDSC"].append(
                        "Study Completion" if sl.get("COMPLTFL") == "Y" else "Censored"
                    )

        # Write output
        output_path = self.config.output_path or Path("output/adam/adtte.xpt")
        output_path.parent.mkdir(parents=True, exist_ok=True)

        from io_handlers import DatasetWriter

        writer = DatasetWriter()
        writer.write(
            adtte_data,
            output_path,
            metadata={"domain": "ADTTE", "label": "Time-to-Event Analysis"},
        )

        n_records = len(adtte_data["USUBJID"])
        self.metrics["tte_records"] = n_records
        self.metrics["events"] = sum(1 for c in adtte_data["CNSR"] if c == 0)
        self.metrics["censored"] = sum(1 for c in adtte_data["CNSR"] if c == 1)

        return self.create_result(
            SkillStatus.SUCCESS,
            f"Built ADTTE with {n_records} records ({self.metrics['events']} events, {self.metrics['censored']} censored)",
            outputs={"output_file": str(output_path), "records": n_records},
        )

    def _read_dataset(self, path: Path) -> Dict:
        """Read dataset."""
        if not path.exists():
            return {}
        from io_handlers import DatasetReader

        reader = DatasetReader()
        return reader.read(path) or {}

    def _build_lookup(self, data: Dict) -> Dict[str, Dict]:
        """Build lookup dictionary."""
        lookup = {}
        n = len(data.get("USUBJID", []))
        for i in range(n):
            usubjid = data["USUBJID"][i]
            lookup[usubjid] = {
                var: data[var][i] if i < len(data[var]) else "" for var in data
            }
        return lookup

    def _build_event_lookup(self, data: Dict, event_var: str) -> Dict[str, List[Dict]]:
        """Build event lookup by subject."""
        lookup = {}
        n = len(data.get("USUBJID", []))
        for i in range(n):
            usubjid = data["USUBJID"][i]
            if usubjid not in lookup:
                lookup[usubjid] = []
            lookup[usubjid].append(
                {
                    "date": (
                        data.get("DSSTDTC", [""] * (i + 1))[i]
                        if i < len(data.get("DSSTDTC", []))
                        else ""
                    ),
                    "event": (
                        data.get(event_var, [""] * (i + 1))[i]
                        if i < len(data.get(event_var, []))
                        else ""
                    ),
                }
            )
        return lookup

    def _build_ae_lookup(self, data: Dict) -> Dict[str, List[Dict]]:
        """Build AE lookup by subject."""
        lookup = {}
        n = len(data.get("USUBJID", []))
        for i in range(n):
            usubjid = data["USUBJID"][i]
            if usubjid not in lookup:
                lookup[usubjid] = []
            lookup[usubjid].append(
                {
                    "date": (
                        data.get("AESTDTC", [""] * (i + 1))[i]
                        if i < len(data.get("AESTDTC", []))
                        else ""
                    ),
                    "term": (
                        data.get("AETERM", [""] * (i + 1))[i]
                        if i < len(data.get("AETERM", []))
                        else ""
                    ),
                    "serious": (
                        data.get("AESER", [""] * (i + 1))[i]
                        if i < len(data.get("AESER", []))
                        else ""
                    ),
                }
            )
        return lookup

    def _find_event(
        self, usubjid: str, param: Dict, ds_lookup: Dict, ae_lookup: Dict, sl: Dict
    ) -> tuple:
        """Find first event date for parameter."""
        if param["event_source"] == "DS" and usubjid in ds_lookup:
            for event in ds_lookup[usubjid]:
                if event["event"] == param.get("event_decod", ""):
                    return self._parse_date(event["date"]), event["event"]
        elif param["event_source"] == "AE" and usubjid in ae_lookup:
            for event in ae_lookup[usubjid]:
                if event["serious"] == "Y":
                    return self._parse_date(event["date"]), f"SAE: {event['term']}"
        return "", ""

    def _parse_date(self, date_str: str) -> str:
        if not date_str:
            return ""
        return str(date_str).replace("/", "-")[:10]

    def _calc_days(self, start: str, end: str) -> int:
        """Calculate days between dates."""
        try:
            from datetime import datetime

            d1 = datetime.strptime(start[:10], "%Y-%m-%d")
            d2 = datetime.strptime(end[:10], "%Y-%m-%d")
            return (d2 - d1).days
        except:
            return 0

    def _get_cutoff_date(self) -> str:
        """Get analysis cutoff date."""
        return "2024-12-31"  # Default cutoff

    def _dry_run(self) -> SkillResult:
        return self.create_result(SkillStatus.DRY_RUN, "Would build ADTTE", outputs={})


def main():
    parser = create_argument_parser(
        "adtte-builder", "Build ADTTE time-to-event dataset"
    )
    args = parser.parse_args()
    config = SkillConfig.from_args(args)
    result = ADTTEBuilder(config).run()
    print(result.to_json())
    sys.exit(0 if result.status in [SkillStatus.SUCCESS, SkillStatus.WARNING] else 1)


if __name__ == "__main__":
    main()
