#!/usr/bin/env python3
"""SDTM SUPP Builder - Create SUPPXX datasets for non-standard variables."""

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


class SDTMSuppBuilder(BaseCSPSkill):
    """Create SUPPXX datasets for non-standard variables."""

    GRAPH_NODE_ID = "sdtm-suppqual"
    REQUIRED_INPUT_VARS = []
    OUTPUT_VARS = ["RDOMAIN", "IDVAR", "IDVARVAL", "QNAM", "QLABEL", "QVAL"]
    SKILL_NAME = "sdtm-supp-builder"
    SKILL_VERSION = "1.0.0"

    def run(self) -> SkillResult:
        """Execute SUPP dataset creation."""
        self.log_info("Starting SUPP dataset creation")

        if self.config.dry_run:
            return self._dry_run()

        # Read spec for non-standard variables
        spec_path = self.config.input_path or Path("specs/sdtm-mapping-spec.yaml")
        supp_specs = self._load_supp_specs(spec_path)

        # Read parent domain data
        input_dir = Path("output/sdtm")
        output_dir = self.config.output_path or Path("output/sdtm")
        output_dir.mkdir(parents=True, exist_ok=True)

        created_files = []

        # Process each SUPP specification
        for rdomain, qualifiers in supp_specs.items():
            # Read parent domain
            parent_path = input_dir / f"{rdomain.lower()}.xpt"
            if not parent_path.exists():
                self.log_warning(f"Parent domain not found: {parent_path}")
                continue

            from io_handlers import DatasetReader

            reader = DatasetReader()
            parent_data = reader.read(parent_path)

            if not parent_data:
                continue

            # Build SUPP dataset
            supp_data = self._build_supp(rdomain, parent_data, qualifiers)

            if supp_data and any(supp_data.values()):
                from io_handlers import DatasetWriter

                writer = DatasetWriter()
                output_path = output_dir / f"supp{rdomain.lower()}.xpt"
                writer.write(
                    supp_data,
                    output_path,
                    metadata={
                        "domain": f"SUPP{rdomain}",
                        "label": f"Supplemental Qualifiers for {rdomain}",
                    },
                )
                created_files.append(str(output_path))

        self.metrics["supp_datasets"] = len(created_files)
        self.metrics["total_qualifiers"] = sum(len(q) for q in supp_specs.values())

        return self.create_result(
            SkillStatus.SUCCESS,
            f"Created {len(created_files)} SUPP datasets with {self.metrics['total_qualifiers']} qualifiers",
            outputs={"files": created_files},
        )

    def _load_supp_specs(self, spec_path: Path) -> Dict[str, List[Dict]]:
        """Load SUPP specifications from YAML."""
        if not spec_path.exists():
            self.log_warning(f"Spec file not found: {spec_path}, using defaults")
            return self._default_supp_specs()

        import yaml

        try:
            with open(spec_path, "r", encoding="utf-8") as f:
                spec = yaml.safe_load(f) or {}
                return spec.get("supplemental", {})
        except Exception as e:
            self.log_warning(f"Error loading spec: {e}, using defaults")
            return self._default_supp_specs()

    def _default_supp_specs(self) -> Dict[str, List[Dict]]:
        """Return default SUPP specifications."""
        return {
            "DM": [
                {
                    "qnam": "ETHNIC",
                    "qlabel": "Ethnicity Detail",
                    "source": "ETHNIC_DETAIL",
                },
                {"qnam": "CANCSTG", "qlabel": "Cancer Staging", "source": "STAGE"},
            ],
            "AE": [
                {"qnam": "AETRTEM", "qlabel": "Treatment Emergent", "source": "TRTEM"},
            ],
        }

    def _build_supp(
        self, rdomain: str, parent_data: Dict, qualifiers: List[Dict]
    ) -> Dict:
        """Build SUPP dataset for a domain."""
        supp_data = {
            "STUDYID": [],
            "RDOMAIN": [],
            "USUBJID": [],
            "IDVAR": [],
            "IDVARVAL": [],
            "QNAM": [],
            "QLABEL": [],
            "QVAL": [],
        }

        # Get ID variable for this domain
        idvar = self._get_idvar(rdomain)
        studyid = (
            parent_data.get("STUDYID", [""])[0] if parent_data.get("STUDYID") else ""
        )
        usubjids = parent_data.get("USUBJID", [])
        idvarvals = parent_data.get(idvar, []) if idvar else []

        n_records = len(usubjids)

        for i in range(n_records):
            usubjid = usubjids[i] if i < len(usubjids) else ""
            idvarval = str(idvarvals[i]) if idvarvals and i < len(idvarvals) else ""

            for qual in qualifiers:
                qnam = qual.get("qnam", "")
                qlabel = qual.get("qlabel", "")
                source = qual.get("source", "")

                # Get value from parent data
                qval = ""
                if source in parent_data and i < len(parent_data[source]):
                    qval = str(parent_data[source][i])

                if qval:  # Only add non-empty values
                    supp_data["STUDYID"].append(studyid)
                    supp_data["RDOMAIN"].append(rdomain)
                    supp_data["USUBJID"].append(usubjid)
                    supp_data["IDVAR"].append(idvar)
                    supp_data["IDVARVAL"].append(idvarval)
                    supp_data["QNAM"].append(qnam)
                    supp_data["QLABEL"].append(qlabel)
                    supp_data["QVAL"].append(qval)

        return supp_data

    def _get_idvar(self, rdomain: str) -> str:
        """Get the ID variable for a domain."""
        idvar_map = {
            "DM": "",
            "AE": "AESEQ",
            "EX": "EXSEQ",
            "DS": "DSSEQ",
            "LB": "LBSEQ",
            "VS": "VSSEQ",
            "CM": "CMSEQ",
            "MH": "MHSEQ",
        }
        return idvar_map.get(rdomain.upper(), f"{rdomain}SEQ")

    def _dry_run(self) -> SkillResult:
        return self.create_result(
            SkillStatus.DRY_RUN, "Would create SUPP datasets", outputs={}
        )


def main():
    parser = create_argument_parser("sdtm-supp-builder", "Create SUPPXX datasets")
    args = parser.parse_args()
    config = SkillConfig.from_args(args)
    result = SDTMSuppBuilder(config).run()
    print(result.to_json())
    sys.exit(0 if result.status in [SkillStatus.SUCCESS, SkillStatus.WARNING] else 1)


if __name__ == "__main__":
    main()
