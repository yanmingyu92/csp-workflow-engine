#!/usr/bin/env python3
"""ADSL Builder - Build ADSL subject-level dataset."""

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


class ADSLBuilder(BaseCSPSkill):
    """Build ADSL subject-level dataset with derived flags and populations."""

    GRAPH_NODE_ID = "adam-adsl-build"
    REQUIRED_INPUT_VARS = ["USUBJID"]
    OUTPUT_VARS = ["USUBJID", "TRT01P", "TRT01A", "SAFFL", "ITTFL"]
    SKILL_NAME = "adsl-builder"
    SKILL_VERSION = "1.0.0"

    def run(self) -> SkillResult:
        """Execute ADSL building."""
        self.log_info("Starting ADSL build")

        if self.config.dry_run:
            return self._dry_run()

        # Read SDTM domains
        input_dir = self.config.input_path or Path("output/sdtm")
        dm_data = self._read_sdtm_domain(input_dir / "dm.xpt")
        ds_data = self._read_sdtm_domain(input_dir / "ds.xpt")
        ex_data = self._read_sdtm_domain(input_dir / "ex.xpt")

        if not dm_data:
            return self.create_result(SkillStatus.ERROR, "Could not read DM domain")

        n_subjects = len(dm_data.get("USUBJID", []))

        # Initialize ADSL with DM variables
        adsl_data = {}
        for var in dm_data:
            adsl_data[var] = list(dm_data[var])

        # Add ADSL-specific variables
        adsl_vars = [
            "TRT01P",
            "TRT01PN",
            "TRT01A",
            "TRT01AN",
            "SAFFL",
            "ITTFL",
            "PPROTFL",
            "EFFFL",
            "COMPLTFL",
            "DISCONFL",
            "DCTREASN",
            "TRTSDT",
            "TRTEDT",
            "TRTDURD",
            "AGEGR1",
            "AGEGR1N",
            "RACEGR1",
            "RACEGR1N",
        ]
        for var in adsl_vars:
            adsl_data[var] = [""] * n_subjects

        # Derive treatment variables
        self._derive_treatment(adsl_data, dm_data, ex_data)

        # Derive population flags
        self._derive_populations(adsl_data, dm_data, ex_data)

        # Derive disposition
        self._derive_disposition(adsl_data, ds_data)

        # Derive baseline characteristics
        self._derive_baseline(adsl_data)

        # Write output
        output_path = self.config.output_path or Path("output/adam/adsl.xpt")
        output_path.parent.mkdir(parents=True, exist_ok=True)

        from io_handlers import DatasetWriter

        writer = DatasetWriter()
        writer.write(
            adsl_data,
            output_path,
            metadata={"domain": "ADSL", "label": "Subject-Level Analysis"},
        )

        self.metrics["subjects"] = n_subjects
        self.metrics["safety_pop"] = sum(1 for f in adsl_data["SAFFL"] if f == "Y")
        self.metrics["itt_pop"] = sum(1 for f in adsl_data["ITTFL"] if f == "Y")

        return self.create_result(
            SkillStatus.SUCCESS,
            f"Built ADSL for {n_subjects} subjects (SAFFL={self.metrics['safety_pop']}, ITTFL={self.metrics['itt_pop']})",
            outputs={"output_file": str(output_path), "subjects": n_subjects},
        )

    def _read_sdtm_domain(self, path: Path) -> Dict:
        """Read SDTM domain dataset."""
        if not path.exists():
            return {}
        from io_handlers import DatasetReader

        reader = DatasetReader()
        return reader.read(path) or {}

    def _derive_treatment(self, adsl: Dict, dm: Dict, ex: Dict):
        """Derive treatment variables."""
        trt_map = {
            "PLACEBO": 1,
            "LOW DOSE": 2,
            "HIGH DOSE": 3,
            "XANOMELINE LOW DOSE": 2,
            "XANOMELINE HIGH DOSE": 3,
        }

        for i, usubjid in enumerate(adsl["USUBJID"]):
            # Planned treatment from DM
            arm = dm.get("ARM", [""] * (i + 1))[i] if i < len(dm.get("ARM", [])) else ""
            adsl["TRT01P"][i] = arm
            adsl["TRT01PN"][i] = trt_map.get(arm.upper(), 99)

            # Actual treatment from EX
            if ex and "USUBJID" in ex:
                ex_idx = (
                    ex["USUBJID"].index(usubjid) if usubjid in ex["USUBJID"] else -1
                )
                if ex_idx >= 0:
                    extrt = (
                        ex.get("EXTRT", [""] * (ex_idx + 1))[ex_idx]
                        if ex_idx < len(ex.get("EXTRT", []))
                        else ""
                    )
                    adsl["TRT01A"][i] = extrt
                    adsl["TRT01AN"][i] = trt_map.get(extrt.upper(), 99)

                    # Treatment dates
                    exstdtc = (
                        ex.get("EXSTDTC", [""] * (ex_idx + 1))[ex_idx]
                        if ex_idx < len(ex.get("EXSTDTC", []))
                        else ""
                    )
                    adsl["TRTSDT"][i] = self._parse_date(exstdtc)

    def _derive_populations(self, adsl: Dict, dm: Dict, ex: Dict):
        """Derive population flags."""
        ex_subjects = set(ex.get("USUBJID", [])) if ex else set()

        for i, usubjid in enumerate(adsl["USUBJID"]):
            # Safety: received at least one dose
            adsl["SAFFL"][i] = "Y" if usubjid in ex_subjects else "N"

            # ITT: randomized (has ARM assignment)
            arm = dm.get("ARM", [""] * (i + 1))[i] if i < len(dm.get("ARM", [])) else ""
            adsl["ITTFL"][i] = "Y" if arm and arm != "Screen Failure" else "N"

            # Per-protocol (default to ITT for now)
            adsl["PPROTFL"][i] = adsl["ITTFL"][i]

    def _derive_disposition(self, adsl: Dict, ds: Dict):
        """Derive disposition flags."""
        if not ds or "USUBJID" not in ds:
            return

        for i, usubjid in enumerate(adsl["USUBJID"]):
            # Find DS records for this subject
            ds_indices = [j for j, u in enumerate(ds["USUBJID"]) if u == usubjid]

            for j in ds_indices:
                dsdecod = (
                    ds.get("DSDECOD", [""] * (j + 1))[j]
                    if j < len(ds.get("DSDECOD", []))
                    else ""
                )

                if dsdecod == "COMPLETED":
                    adsl["COMPLTFL"][i] = "Y"
                elif dsdecod and dsdecod not in ["COMPLETED", "SCREEN FAILURE"]:
                    adsl["DISCONFL"][i] = "Y"
                    adsl["DCTREASN"][i] = dsdecod

    def _derive_baseline(self, adsl: Dict):
        """Derive baseline characteristics."""
        for i, age in enumerate(adsl.get("AGE", [])):
            try:
                age_val = int(age) if age else 0
                if age_val < 65:
                    adsl["AGEGR1"][i] = "<65"
                    adsl["AGEGR1N"][i] = 1
                else:
                    adsl["AGEGR1"][i] = ">=65"
                    adsl["AGEGR1N"][i] = 2
            except (ValueError, TypeError):
                pass

        for i, race in enumerate(adsl.get("RACE", [])):
            adsl["RACEGR1"][i] = (
                "WHITE" if str(race).upper() == "WHITE" else "NON-WHITE"
            )
            adsl["RACEGR1N"][i] = 1 if str(race).upper() == "WHITE" else 2

    def _parse_date(self, date_str: str) -> str:
        """Parse date string to ISO format."""
        if not date_str:
            return ""
        return str(date_str).replace("/", "-")[:10]

    def _dry_run(self) -> SkillResult:
        return self.create_result(SkillStatus.DRY_RUN, "Would build ADSL", outputs={})


def main():
    parser = create_argument_parser("adsl-builder", "Build ADSL subject-level dataset")
    args = parser.parse_args()
    config = SkillConfig.from_args(args)
    result = ADSLBuilder(config).run()
    print(result.to_json())
    sys.exit(0 if result.status in [SkillStatus.SUCCESS, SkillStatus.WARNING] else 1)


if __name__ == "__main__":
    main()
