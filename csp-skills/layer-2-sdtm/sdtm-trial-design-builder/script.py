#!/usr/bin/env python3
"""SDTM Trial Design Builder - Create TS, TA, TI, TV datasets."""

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


class SDTMTrialDesignBuilder(BaseCSPSkill):
    """Create FDA-required trial design datasets (TS, TA, TI, TV)."""

    GRAPH_NODE_ID = "sdtm-trial-design"
    REQUIRED_INPUT_VARS = []
    OUTPUT_VARS = []
    SKILL_NAME = "sdtm-trial-design-builder"
    SKILL_VERSION = "1.0.0"

    # Standard TS parameters
    TS_PARAMETERS = [
        ("TSPARMCD", "TSPARM", "TSVAL"),
        ("TITLE", "Trial Title", ""),
        ("INDIC", "Indication", ""),
        ("PHASE", "Trial Phase", ""),
        ("STUDYTYP", "Study Type", ""),
        ("PLANSUB", "Planned Number of Subjects", ""),
        ("SPONSOR", "Sponsor", ""),
        ("TRTINDA", "Investigational Product A", ""),
        ("TRTINDA1", "Product A Description", ""),
    ]

    def run(self) -> SkillResult:
        """Execute trial design dataset creation."""
        self.log_info("Starting trial design dataset creation")

        if self.config.dry_run:
            return self._dry_run()

        # Read study configuration
        config_path = self.config.input_path or Path("specs/study-config.yaml")
        study_config = self._load_study_config(config_path)

        output_dir = self.config.output_path or Path("output/sdtm")
        output_dir.mkdir(parents=True, exist_ok=True)

        created_files = []

        # Build each trial design dataset
        ts_data = self._build_ts(study_config)
        ta_data = self._build_ta(study_config)
        ti_data = self._build_ti(study_config)
        tv_data = self._build_tv(study_config)

        # Write datasets
        from io_handlers import DatasetWriter

        writer = DatasetWriter()

        for data, domain, label in [
            (ts_data, "TS", "Trial Summary"),
            (ta_data, "TA", "Trial Arms"),
            (ti_data, "TI", "Trial Inclusion/Exclusion"),
            (tv_data, "TV", "Trial Visits"),
        ]:
            if data and any(data.values()):
                output_path = output_dir / f"{domain.lower()}.xpt"
                writer.write(
                    data, output_path, metadata={"domain": domain, "label": label}
                )
                created_files.append(str(output_path))

        self.metrics["datasets_created"] = len(created_files)

        return self.create_result(
            SkillStatus.SUCCESS,
            f"Created {len(created_files)} trial design datasets",
            outputs={"files": created_files},
        )

    def _load_study_config(self, config_path: Path) -> Dict:
        """Load study configuration from YAML."""
        if not config_path.exists():
            self.log_warning(f"Config file not found: {config_path}, using defaults")
            return self._default_study_config()

        import yaml

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            self.log_warning(f"Error loading config: {e}, using defaults")
            return self._default_study_config()

    def _default_study_config(self) -> Dict:
        """Return default study configuration."""
        return {
            "study": {
                "studyid": "STUDY001",
                "title": "Clinical Study",
                "phase": "Phase 2",
                "indication": "Indication",
                "sponsor": "Sponsor",
                "planned_enrollment": 100,
            },
            "arms": [
                {
                    "arm": "Treatment A",
                    "armcd": "TRTA",
                    "description": "Active treatment",
                }
            ],
            "visits": [
                {"visit": "Screening", "visitnum": 1, "visitdy": -14},
                {"visit": "Baseline", "visitnum": 2, "visitdy": 0},
                {"visit": "Week 4", "visitnum": 3, "visitdy": 28},
            ],
            "criteria": [
                {"ietest": "Informed consent", "iecat": "INCLUSION"},
                {"ietest": "Age >= 18", "iecat": "INCLUSION"},
            ],
        }

    def _build_ts(self, config: Dict) -> Dict:
        """Build Trial Summary dataset."""
        study = config.get("study", {})
        ts_data = {
            "STUDYID": [],
            "DOMAIN": [],
            "TSPARMCD": [],
            "TSPARM": [],
            "TSVAL": [],
        }

        params = [
            ("TITLE", "Trial Title", study.get("title", "")),
            ("INDIC", "Indication", study.get("indication", "")),
            ("PHASE", "Trial Phase", study.get("phase", "")),
            ("STUDYTYP", "Study Type", study.get("study_type", "INTERVENTIONAL")),
            (
                "PLANSUB",
                "Planned Number of Subjects",
                str(study.get("planned_enrollment", "")),
            ),
            ("SPONSOR", "Sponsor", study.get("sponsor", "")),
        ]

        for tsparmd, tsparm, tsval in params:
            if tsval:
                ts_data["STUDYID"].append(study.get("studyid", "STUDY001"))
                ts_data["DOMAIN"].append("TS")
                ts_data["TSPARMCD"].append(tsparmd)
                ts_data["TSPARM"].append(tsparm)
                ts_data["TSVAL"].append(str(tsval))

        return ts_data

    def _build_ta(self, config: Dict) -> Dict:
        """Build Trial Arms dataset."""
        ta_data = {
            "STUDYID": [],
            "DOMAIN": [],
            "ARM": [],
            "ARMCD": [],
            "TAETORD": [],
            "EPOCH": [],
        }

        arms = config.get("arms", [])
        studyid = config.get("study", {}).get("studyid", "STUDY001")

        for i, arm in enumerate(arms, 1):
            ta_data["STUDYID"].append(studyid)
            ta_data["DOMAIN"].append("TA")
            ta_data["ARM"].append(arm.get("arm", ""))
            ta_data["ARMCD"].append(arm.get("armcd", ""))
            ta_data["TAETORD"].append(i)
            ta_data["EPOCH"].append(arm.get("epoch", "TREATMENT"))

        return ta_data

    def _build_ti(self, config: Dict) -> Dict:
        """Build Trial Inclusion/Exclusion dataset."""
        ti_data = {
            "STUDYID": [],
            "DOMAIN": [],
            "IETEST": [],
            "IECAT": [],
            "IETESTCD": [],
        }

        criteria = config.get("criteria", [])
        studyid = config.get("study", {}).get("studyid", "STUDY001")

        for i, criterion in enumerate(criteria, 1):
            ti_data["STUDYID"].append(studyid)
            ti_data["DOMAIN"].append("TI")
            ti_data["IETEST"].append(criterion.get("ietest", ""))
            ti_data["IECAT"].append(criterion.get("iecat", "INCLUSION"))
            ti_data["IETESTCD"].append(f"I{i:03d}")

        return ti_data

    def _build_tv(self, config: Dict) -> Dict:
        """Build Trial Visits dataset."""
        tv_data = {
            "STUDYID": [],
            "DOMAIN": [],
            "VISIT": [],
            "VISITNUM": [],
            "VISITDY": [],
            "VISTYP": [],
        }

        visits = config.get("visits", [])
        studyid = config.get("study", {}).get("studyid", "STUDY001")

        for visit in visits:
            tv_data["STUDYID"].append(studyid)
            tv_data["DOMAIN"].append("TV")
            tv_data["VISIT"].append(visit.get("visit", ""))
            tv_data["VISITNUM"].append(visit.get("visitnum", 0))
            tv_data["VISITDY"].append(visit.get("visitdy", 0))
            tv_data["VISTYP"].append(visit.get("vistyp", "SCHEDULED"))

        return tv_data

    def _dry_run(self) -> SkillResult:
        return self.create_result(
            SkillStatus.DRY_RUN, "Would create trial design datasets", outputs={}
        )


def main():
    parser = create_argument_parser(
        "sdtm-trial-design-builder", "Create trial design datasets"
    )
    args = parser.parse_args()
    config = SkillConfig.from_args(args)
    result = SDTMTrialDesignBuilder(config).run()
    print(result.to_json())
    sys.exit(0 if result.status in [SkillStatus.SUCCESS, SkillStatus.WARNING] else 1)


if __name__ == "__main__":
    main()
