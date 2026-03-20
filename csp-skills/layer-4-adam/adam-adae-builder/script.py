#!/usr/bin/env python3
"""ADAE Builder - Build ADAE adverse events analysis dataset."""

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


class ADAEBuilder(BaseCSPSkill):
    """Build ADAE adverse events analysis dataset."""

    GRAPH_NODE_ID = "adam-adae-build"
    REQUIRED_INPUT_VARS = ["USUBJID", "AETERM"]
    OUTPUT_VARS = ["USUBJID", "AETERM", "AEDECOD", "TRTA", "SAFFL", "TRTEMFL"]
    SKILL_NAME = "adae-builder"
    SKILL_VERSION = "1.0.0"

    def run(self) -> SkillResult:
        """Execute ADAE building."""
        self.log_info("Starting ADAE build")

        if self.config.dry_run:
            return self._dry_run()

        # Read source data
        input_dir = self.config.input_path or Path("output")
        ae_data = self._read_dataset(input_dir / "sdtm" / "ae.xpt")
        adsl_data = self._read_dataset(input_dir / "adam" / "adsl.xpt")

        if not ae_data:
            return self.create_result(SkillStatus.ERROR, "Could not read AE domain")
        if not adsl_data:
            return self.create_result(SkillStatus.ERROR, "Could not read ADSL")

        # Build ADSL lookup
        adsl_lookup = self._build_adsl_lookup(adsl_data)

        n_records = len(ae_data.get("USUBJID", []))

        # Initialize ADAE with AE variables
        adae_data = {}
        for var in ae_data:
            adae_data[var] = list(ae_data[var])

        # Add ADAE-specific variables
        adae_vars = [
            "TRTA",
            "TRTAN",
            "TRTP",
            "TRTPN",
            "SAFFL",
            "ITTFL",
            "ASTDT",
            "ASTDTF",
            "ASTDY",
            "AENDT",
            "AENDY",
            "TRTEMFL",
            "AOCCFL",
            "AESEVN",
            "AESER",
        ]
        for var in adae_vars:
            adae_data[var] = [""] * n_records

        # Merge ADSL and derive variables
        for i in range(n_records):
            usubjid = ae_data["USUBJID"][i] if i < len(ae_data["USUBJID"]) else ""

            # Get ADSL values
            if usubjid in adsl_lookup:
                sl = adsl_lookup[usubjid]
                adae_data["TRTA"][i] = sl.get("TRT01A", "")
                adae_data["TRTAN"][i] = sl.get("TRT01AN", "")
                adae_data["TRTP"][i] = sl.get("TRT01P", "")
                adae_data["TRTPN"][i] = sl.get("TRT01PN", "")
                adae_data["SAFFL"][i] = sl.get("SAFFL", "")
                adae_data["ITTFL"][i] = sl.get("ITTFL", "")
                trtsdt = sl.get("TRTSDT", "")
                trtedt = sl.get("TRTEDT", "")
            else:
                trtsdt = ""
                trtedt = ""

            # Analysis dates
            aestdtc = (
                ae_data.get("AESTDTC", [""] * (i + 1))[i]
                if i < len(ae_data.get("AESTDTC", []))
                else ""
            )
            aendtc = (
                ae_data.get("AEENDTC", [""] * (i + 1))[i]
                if i < len(ae_data.get("AEENDTC", []))
                else ""
            )

            adae_data["ASTDT"][i] = self._parse_date(aestdtc)
            adae_data["AENDT"][i] = self._parse_date(aendtc)

            # Treatment-emergent flag
            adae_data["TRTEMFL"][i] = self._derive_trtemfl(aestdtc, trtsdt, trtedt)

            # Severity numeric
            aesev = (
                ae_data.get("AESEV", [""] * (i + 1))[i]
                if i < len(ae_data.get("AESEV", []))
                else ""
            )
            adae_data["AESEVN"][i] = {"MILD": 1, "MODERATE": 2, "SEVERE": 3}.get(
                str(aesev).upper(), ""
            )

        # Write output
        output_path = self.config.output_path or Path("output/adam/adae.xpt")
        output_path.parent.mkdir(parents=True, exist_ok=True)

        from io_handlers import DatasetWriter

        writer = DatasetWriter()
        writer.write(
            adae_data,
            output_path,
            metadata={"domain": "ADAE", "label": "Adverse Events Analysis"},
        )

        self.metrics["ae_records"] = n_records
        self.metrics["treatment_emergent"] = sum(
            1 for f in adae_data["TRTEMFL"] if f == "Y"
        )

        return self.create_result(
            SkillStatus.SUCCESS,
            f"Built ADAE with {n_records} records, {self.metrics['treatment_emergent']} treatment-emergent",
            outputs={"output_file": str(output_path), "records": n_records},
        )

    def _read_dataset(self, path: Path) -> Dict:
        """Read dataset."""
        if not path.exists():
            return {}
        from io_handlers import DatasetReader

        reader = DatasetReader()
        return reader.read(path) or {}

    def _build_adsl_lookup(self, adsl: Dict) -> Dict[str, Dict]:
        """Build lookup dictionary from ADSL."""
        lookup = {}
        n = len(adsl.get("USUBJID", []))
        for i in range(n):
            usubjid = adsl["USUBJID"][i]
            lookup[usubjid] = {
                var: adsl[var][i] if i < len(adsl[var]) else "" for var in adsl
            }
        return lookup

    def _parse_date(self, date_str: str) -> str:
        """Parse date string."""
        if not date_str:
            return ""
        return str(date_str).replace("/", "-")[:10]

    def _derive_trtemfl(self, aestdtc: str, trtsdt: str, trtedt: str) -> str:
        """Derive treatment-emergent flag."""
        if not aestdtc or not trtsdt:
            return ""
        # Simplified: AE start >= first dose
        try:
            ae_date = aestdtc[:10]
            trt_date = trtsdt[:10]
            return "Y" if ae_date >= trt_date else "N"
        except:
            return ""

    def _dry_run(self) -> SkillResult:
        return self.create_result(SkillStatus.DRY_RUN, "Would build ADAE", outputs={})


def main():
    parser = create_argument_parser("adae-builder", "Build ADAE adverse events dataset")
    args = parser.parse_args()
    config = SkillConfig.from_args(args)
    result = ADAEBuilder(config).run()
    print(result.to_json())
    sys.exit(0 if result.status in [SkillStatus.SUCCESS, SkillStatus.WARNING] else 1)


if __name__ == "__main__":
    main()
