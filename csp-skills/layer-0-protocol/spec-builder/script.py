#!/usr/bin/env python3
"""Spec Builder - Create SDTM, ADaM, and TFL specifications"""

import sys
import yaml
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field, asdict

# Add parent path for shared utilities
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "_shared"))

from base_skill import (
    BaseCSPSkill,
    SkillConfig,
    SkillResult,
    SkillStatus,
    create_argument_parser,
)


@dataclass
class VariableMapping:
    """SDTM variable mapping specification."""

    domain: str
    variable: str
    source_dataset: str
    source_variable: str
    derivation: str = ""
    required: bool = True
    controlled_terminology: str = ""
    comment: str = ""


@dataclass
class ADaMDerivation:
    """ADaM variable derivation specification."""

    dataset: str
    variable: str
    derivation_type: str  # merge, derived, flag, computed
    source_variables: List[str] = field(default_factory=list)
    derivation_logic: str = ""
    data_type: str = ""
    label: str = ""


class SpecBuilderSkill(BaseCSPSkill):
    """Build specifications for SDTM, ADaM, and TFL."""

    GRAPH_NODE_ID = "spec-creation"
    REQUIRED_INPUT_VARS = []
    OUTPUT_VARS = ["specifications"]
    SKILL_NAME = "spec-builder"
    SKILL_VERSION = "1.0.0"

    def run(self) -> SkillResult:
        """Execute specification building."""
        self.log_info(f"Building {self.config.spec_type} specifications")

        if self.config.dry_run:
            return self._dry_run()

        # Load inputs
        sap_data = self._load_yaml(self.config.input_path)
        study_config = self._load_yaml(self.config.study_config_path)

        if not sap_data:
            return self.create_result(
                SkillStatus.ERROR, "Could not load SAP specifications"
            )

        # Build specifications based on type
        outputs = {}

        if self.config.spec_type in ["sdtm", "all"]:
            outputs["sdtm"] = self._build_sdtm_spec(sap_data, study_config)

        if self.config.spec_type in ["adam", "all"]:
            outputs["adam"] = self._build_adam_spec(sap_data, study_config)

        if self.config.spec_type in ["tfl", "all"]:
            outputs["tfl"] = self._build_tfl_spec(sap_data, study_config)

        # Write outputs
        output_files = self._write_specs(outputs)

        self.metrics["output_files"] = output_files
        self.metrics["spec_type"] = self.config.spec_type

        return self.create_result(
            SkillStatus.SUCCESS,
            f"Built {self.config.spec_type} specifications",
            outputs={"files": output_files},
        )

    def _build_sdtm_spec(self, sap_data: Dict, study_config: Dict) -> Dict[str, Any]:
        """Build SDTM mapping specification."""
        domains = []

        # DM domain (always required)
        dm_vars = [
            VariableMapping(
                "DM", "STUDYID", "RAW.DM", "STUDYID", "Study identifier", True
            ),
            VariableMapping("DM", "DOMAIN", "", "", "DM", True),
            VariableMapping(
                "DM",
                "USUBJID",
                "RAW.DM",
                "SUBJID",
                "Concatenate STUDYID-SITEID-SUBJID",
                True,
            ),
            VariableMapping(
                "DM", "SUBJID", "RAW.DM", "SUBJID", "Subject identifier", True
            ),
            VariableMapping(
                "DM", "SITEID", "RAW.DM", "SITEID", "Site identifier", True
            ),
            VariableMapping("DM", "AGE", "RAW.DM", "AGE", "Age in years", True),
            VariableMapping("DM", "AGEU", "", "", "YEARS", True),
            VariableMapping("DM", "SEX", "RAW.DM", "SEX", "Sex", True, "C66731"),
            VariableMapping("DM", "RACE", "RAW.DM", "RACE", "Race", True, "C74457"),
            VariableMapping(
                "DM", "ARM", "RAW.DM", "ARM", "Assigned treatment arm", True
            ),
            VariableMapping("DM", "ARMCD", "RAW.DM", "ARMCD", "Arm code", True),
        ]

        domains.append(
            {
                "domain": "DM",
                "name": "Demographics",
                "structure": "One record per subject",
                "key_variables": ["STUDYID", "USUBJID"],
                "variables": [asdict(v) for v in dm_vars],
            }
        )

        # Add more domains based on SAP endpoints
        endpoints = sap_data.get("endpoints", {})
        if endpoints.get("primary") or endpoints.get("secondary"):
            # AE domain for safety
            domains.append(self._get_ae_domain_template())
            # LB domain for lab data
            domains.append(self._get_lb_domain_template())
            # VS domain for vitals
            domains.append(self._get_vs_domain_template())
            # EX domain for exposure
            domains.append(self._get_ex_domain_template())

        return {
            "schema_version": 1,
            "spec_type": "sdtm",
            "created": datetime.utcnow().isoformat(),
            "domains": domains,
        }

    def _get_ae_domain_template(self) -> Dict:
        """Get AE domain template."""
        ae_vars = [
            {
                "domain": "AE",
                "variable": "STUDYID",
                "source": "RAW.AE",
                "required": True,
            },
            {
                "domain": "AE",
                "variable": "DOMAIN",
                "source": "",
                "derivation": "AE",
                "required": True,
            },
            {
                "domain": "AE",
                "variable": "USUBJID",
                "source": "RAW.AE",
                "required": True,
            },
            {
                "domain": "AE",
                "variable": "AESEQ",
                "source": "",
                "derivation": "Sequence number",
                "required": True,
            },
            {
                "domain": "AE",
                "variable": "AETERM",
                "source": "RAW.AE.AETERM",
                "required": True,
            },
            {
                "domain": "AE",
                "variable": "AEDECOD",
                "source": "MedDRA coding",
                "required": True,
                "ct": "MedDRA",
            },
            {
                "domain": "AE",
                "variable": "AEBODSYS",
                "source": "MedDRA coding",
                "required": True,
            },
            {
                "domain": "AE",
                "variable": "AESEV",
                "source": "RAW.AE.AESEV",
                "required": True,
                "ct": "C66769",
            },
            {
                "domain": "AE",
                "variable": "AESER",
                "source": "RAW.AE.AESER",
                "required": True,
                "ct": "C66770",
            },
            {
                "domain": "AE",
                "variable": "AESTDTC",
                "source": "RAW.AE.AESTDTC",
                "required": False,
            },
            {
                "domain": "AE",
                "variable": "AEENDTC",
                "source": "RAW.AE.AEENDTC",
                "required": False,
            },
        ]
        return {"domain": "AE", "name": "Adverse Events", "variables": ae_vars}

    def _get_lb_domain_template(self) -> Dict:
        """Get LB domain template."""
        return {
            "domain": "LB",
            "name": "Laboratory Tests",
            "structure": "One record per lab test per visit per subject",
            "key_variables": ["STUDYID", "USUBJID", "LBSEQ"],
            "variables": [
                {
                    "domain": "LB",
                    "variable": "LBTESTCD",
                    "source": "RAW.LB.LBTESTCD",
                    "ct": "LBTESTCD",
                },
                {"domain": "LB", "variable": "LBTEST", "source": "RAW.LB.LBTEST"},
                {"domain": "LB", "variable": "LBORRES", "source": "RAW.LB.LBORRES"},
                {"domain": "LB", "variable": "LBORRESU", "source": "RAW.LB.LBORRESU"},
                {
                    "domain": "LB",
                    "variable": "LBSTRESN",
                    "source": "Derived",
                    "derivation": "Standardized result",
                },
                {
                    "domain": "LB",
                    "variable": "LBSTRESU",
                    "source": "Derived",
                    "derivation": "Standardized unit",
                },
            ],
        }

    def _get_vs_domain_template(self) -> Dict:
        """Get VS domain template."""
        return {
            "domain": "VS",
            "name": "Vital Signs",
            "variables": [
                {
                    "domain": "VS",
                    "variable": "VSTESTCD",
                    "source": "RAW.VS.VSTESTCD",
                    "ct": "VSTESTCD",
                },
                {"domain": "VS", "variable": "VSTEST", "source": "RAW.VS.VSTEST"},
                {"domain": "VS", "variable": "VSORRES", "source": "RAW.VS.VSORRES"},
                {"domain": "VS", "variable": "VSORRESU", "source": "RAW.VS.VSORRESU"},
                {"domain": "VS", "variable": "VSSTRESN", "source": "Derived"},
            ],
        }

    def _get_ex_domain_template(self) -> Dict:
        """Get EX domain template."""
        return {
            "domain": "EX",
            "name": "Exposure",
            "variables": [
                {"domain": "EX", "variable": "EXTRT", "source": "RAW.EX.EXTRT"},
                {"domain": "EX", "variable": "EXDOSE", "source": "RAW.EX.EXDOSE"},
                {"domain": "EX", "variable": "EXDOSU", "source": "RAW.EX.EXDOSU"},
                {"domain": "EX", "variable": "EXSTDTC", "source": "RAW.EX.EXSTDTC"},
                {"domain": "EX", "variable": "EXENDTC", "source": "RAW.EX.EXENDTC"},
            ],
        }

    def _build_adam_spec(self, sap_data: Dict, study_config: Dict) -> Dict[str, Any]:
        """Build ADaM derivation specification."""
        datasets = []

        # ADSL (always required)
        adsl_vars = [
            {
                "dataset": "ADSL",
                "variable": "USUBJID",
                "type": "merge",
                "source": "DM.USUBJID",
            },
            {
                "dataset": "ADSL",
                "variable": "TRT01P",
                "type": "merge",
                "source": "DM.ARM",
                "label": "Planned Treatment Arm",
            },
            {
                "dataset": "ADSL",
                "variable": "TRT01A",
                "type": "merge",
                "source": "DM.ACTARM",
                "label": "Actual Treatment Arm",
            },
            {
                "dataset": "ADSL",
                "variable": "SAFFL",
                "type": "flag",
                "logic": "Received any study drug",
                "label": "Safety Flag",
            },
            {
                "dataset": "ADSL",
                "variable": "ITTFL",
                "type": "flag",
                "logic": "Randomized",
                "label": "ITT Flag",
            },
            {
                "dataset": "ADSL",
                "variable": "TRTSDT",
                "type": "derived",
                "source": "EX.EXSTDTC",
                "logic": "First exposure date",
            },
            {
                "dataset": "ADSL",
                "variable": "TRTEDT",
                "type": "derived",
                "source": "EX.EXENDTC",
                "logic": "Last exposure date",
            },
        ]

        datasets.append(
            {
                "dataset": "ADSL",
                "name": "Subject-Level Analysis Dataset",
                "structure": "One record per subject",
                "key_variables": ["STUDYID", "USUBJID"],
                "variables": adsl_vars,
            }
        )

        # Add ADAE if AE endpoint exists
        endpoints = sap_data.get("endpoints", {})
        if endpoints.get("primary") or endpoints.get("secondary"):
            datasets.append(
                {
                    "dataset": "ADAE",
                    "name": "Adverse Event Analysis Dataset",
                    "structure": "One record per AE per subject",
                    "variables": [
                        {
                            "dataset": "ADAE",
                            "variable": "TRTEMFL",
                            "type": "flag",
                            "logic": "AE started on or after first dose",
                        },
                        {
                            "dataset": "ADAE",
                            "variable": "AOCCFL",
                            "type": "flag",
                            "logic": "First occurrence of preferred term",
                        },
                        {
                            "dataset": "ADAE",
                            "variable": "ASTDT",
                            "type": "derived",
                            "source": "AE.AESTDTC",
                        },
                        {
                            "dataset": "ADAE",
                            "variable": "AENDT",
                            "type": "derived",
                            "source": "AE.AEENDTC",
                        },
                    ],
                }
            )

        return {
            "schema_version": 1,
            "spec_type": "adam",
            "created": datetime.utcnow().isoformat(),
            "datasets": datasets,
        }

    def _build_tfl_spec(self, sap_data: Dict, study_config: Dict) -> Dict[str, Any]:
        """Build TFL shell specification."""
        shells = sap_data.get("tfl_shells", {})

        tables = []
        for i, table in enumerate(shells.get("tables", [])):
            tables.append(
                {
                    "id": table.get("id", f"Table {i+1}"),
                    "title": table.get("title", ""),
                    "population": table.get("population", "ITT"),
                    "purpose": table.get("purpose", "efficacy"),
                    "template": (
                        "standard_demographics"
                        if "demographic" in table.get("title", "").lower()
                        else "standard_analysis"
                    ),
                }
            )

        figures = []
        for i, fig in enumerate(shells.get("figures", [])):
            figures.append(
                {
                    "id": fig.get("id", f"Figure {i+1}"),
                    "title": fig.get("title", ""),
                    "population": fig.get("population", "ITT"),
                    "type": self._infer_figure_type(fig.get("title", "")),
                }
            )

        return {
            "schema_version": 1,
            "spec_type": "tfl",
            "created": datetime.utcnow().isoformat(),
            "tables": tables,
            "figures": figures,
            "listings": shells.get("listings", []),
        }

    def _infer_figure_type(self, title: str) -> str:
        """Infer figure type from title."""
        title_lower = title.lower()
        if "km" in title_lower or "kaplan" in title_lower or "survival" in title_lower:
            return "km_curve"
        elif "forest" in title_lower:
            return "forest_plot"
        elif "waterfall" in title_lower:
            return "waterfall_plot"
        elif "spaghetti" in title_lower or "over time" in title_lower:
            return "spaghetti_plot"
        return "standard"

    def _load_yaml(self, path: Optional[Path]) -> Optional[Dict]:
        """Load YAML file."""
        if not path or not path.exists():
            return None
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def _write_specs(self, outputs: Dict[str, Dict]) -> List[str]:
        """Write specification files."""
        output_files = []
        output_dir = (
            self.config.output_path.parent if self.config.output_path else Path("specs")
        )

        for spec_type, spec_data in outputs.items():
            if spec_type == "sdtm":
                path = output_dir / "sdtm-mapping-spec.yaml"
            elif spec_type == "adam":
                path = output_dir / "adam-derivation-spec.yaml"
            elif spec_type == "tfl":
                path = output_dir / "tfl-shells.yaml"
            else:
                continue

            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                yaml.dump(spec_data, f, default_flow_style=False, sort_keys=False)
            output_files.append(str(path))

        return output_files

    def _dry_run(self) -> SkillResult:
        """Show what would be done."""
        return self.create_result(
            SkillStatus.DRY_RUN,
            f"Would build {self.config.spec_type} specifications",
            outputs={"spec_type": self.config.spec_type},
        )


def create_parser() -> argparse.ArgumentParser:
    """Create argument parser."""
    parser = create_argument_parser(
        "spec-builder", "Build SDTM/ADaM/TFL specifications"
    )
    parser.add_argument(
        "--type",
        dest="spec_type",
        choices=["sdtm", "adam", "tfl", "all"],
        default="all",
        help="Type of specification to build",
    )
    return parser


def main():
    parser = create_parser()
    args = parser.parse_args()

    config = SkillConfig.from_args(args)
    config.spec_type = args.spec_type
    skill = SpecBuilderSkill(config)
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
