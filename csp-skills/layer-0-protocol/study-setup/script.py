#!/usr/bin/env python3
"""Study Setup - Configure study-level metadata"""

import sys
import json
import yaml
import argparse
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Any, Optional
from datetime import datetime

# Add parent path for shared utilities
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "_shared"))

from base_skill import (
    BaseCSPSkill,
    SkillResult,
    SkillStatus,
    SkillConfig,
    create_argument_parser,
    main_wrapper,
)


@dataclass
class TreatmentArm:
    """Treatment arm definition."""

    id: str
    name: str
    armcd: str
    description: str = ""
    dose: str = ""
    frequency: str = ""


@dataclass
class Visit:
    """Visit definition."""

    id: str
    name: str
    visitnum: int
    window_days: int = 0
    description: str = ""
    visit_type: str = "SCHEDULED"


@dataclass
class StudyConfig:
    """Complete study configuration."""

    study_id: str
    study_name: str
    phase: str
    therapeutic_area: str = ""
    indication: str = ""
    design_type: str = ""
    blinding: str = ""
    randomization: str = ""
    stratification_factors: List[str] = field(default_factory=list)
    arms: List[TreatmentArm] = field(default_factory=list)
    visits: List[Visit] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class StudySetupSkill(BaseCSPSkill):
    """Configure study-level metadata from protocol."""

    GRAPH_NODE_ID = "protocol-setup"
    REQUIRED_INPUT_VARS = []
    OUTPUT_VARS = ["study_id", "arms", "visits"]
    SKILL_NAME = "study-setup"
    SKILL_VERSION = "1.0.0"

    def run(self) -> SkillResult:
        """Execute study setup configuration."""
        self.log_info(f"Starting study setup for {self.config.input_path}")

        if self.config.dry_run:
            return self._dry_run()

        # Read protocol document
        content = self._read_document()
        if not content:
            return self.create_result(
                SkillStatus.ERROR, "Could not read protocol document"
            )

        # Extract study configuration
        study_config = self._extract_config(content)

        # Validate configuration
        validation_issues = self._validate_config(study_config)
        if validation_issues and self.config.strict_mode:
            return self.create_result(
                SkillStatus.ERROR,
                f"Validation failed: {len(validation_issues)} issues",
                outputs={"issues": validation_issues},
            )

        # Write output
        self._write_config(study_config)

        result_data = {
            "study_id": study_config.study_id,
            "phase": study_config.phase,
            "n_arms": len(study_config.arms),
            "n_visits": len(study_config.visits),
            "output_file": str(self.config.output_path),
        }

        self.metrics.update(result_data)

        status = SkillStatus.WARNING if validation_issues else SkillStatus.SUCCESS
        return self.create_result(
            status,
            f"Study configuration created for {study_config.study_id}",
            outputs=result_data,
        )

    def _read_document(self) -> Optional[str]:
        """Read content from protocol document."""
        path = self.config.input_path
        if not path or not path.exists():
            return None

        suffix = path.suffix.lower()
        if suffix == ".txt":
            return path.read_text(encoding="utf-8")
        elif suffix == ".pdf":
            try:
                import pdfplumber

                text_parts = []
                with pdfplumber.open(path) as pdf:
                    for page in pdf.pages[:10]:  # First 10 pages
                        text = page.extract_text()
                        if text:
                            text_parts.append(text)
                return "\n".join(text_parts)
            except ImportError:
                self.log_warning("pdfplumber not installed")
                return None
        return None

    def _extract_config(self, content: str) -> StudyConfig:
        """Extract study configuration from protocol content."""
        import re

        # Extract study ID
        study_id = self._extract_pattern(
            content,
            [r"study\s*(?:id|number|code)[:\s]*([A-Z0-9\-]+)", r"([A-Z]{2,4}\d{4,})"],
            "UNKNOWN",
        )

        # Extract phase
        phase = self._extract_pattern(
            content, [r"phase\s*(\d[a-z]?)", r"(phase\s*[iI]{1,3})"], "Unknown"
        )

        # Extract treatment arms
        arms = self._extract_arms(content)

        # Extract visits
        visits = self._extract_visits(content)

        return StudyConfig(
            study_id=study_id,
            study_name=f"Clinical Study {study_id}",
            phase=phase,
            arms=arms,
            visits=visits,
            metadata={
                "extraction_date": datetime.utcnow().isoformat(),
                "source_file": str(self.config.input_path),
            },
        )

    def _extract_pattern(self, content: str, patterns: List[str], default: str) -> str:
        """Extract first matching pattern from content."""
        import re

        for pattern in patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return default

    def _extract_arms(self, content: str) -> List[TreatmentArm]:
        """Extract treatment arms from content."""
        import re

        arms = []

        # Common patterns for treatment arms
        arm_patterns = [
            r"(treatment|arm)\s*([A-Z])\s*[:\-]?\s*([^\n]+)",
            r"arm\s*(\d+)\s*[:\-]?\s*([^\n]+)",
        ]

        arm_map = {}
        for pattern in arm_patterns:
            for match in re.finditer(pattern, content, re.IGNORECASE):
                groups = match.groups()
                if len(groups) >= 2:
                    arm_id = groups[1] if len(groups) > 1 else groups[0]
                    arm_name = (
                        groups[-1].strip() if len(groups) > 1 else groups[1].strip()
                    )
                    if arm_id not in arm_map and len(arm_name) < 100:
                        arm_map[arm_id] = arm_name

        # Create TreatmentArm objects
        for i, (arm_id, arm_name) in enumerate(arm_map.items()):
            arms.append(
                TreatmentArm(
                    id=arm_id,
                    name=arm_name[:50],
                    armcd=f"ARM{i+1:02d}"[:8],
                    description=arm_name,
                )
            )

        # Default arms if none found
        if not arms:
            arms = [
                TreatmentArm(id="A", name="Placebo", armcd="PLACEBO"),
                TreatmentArm(id="B", name="Active", armcd="ACTIVE"),
            ]
            self.warnings.append("No treatment arms found, using defaults")

        return arms

    def _extract_visits(self, content: str) -> List[Visit]:
        """Extract visit schedule from content."""
        import re

        visits = []

        # Common visit patterns
        visit_patterns = [
            r"(screening|baseline|day\s*\d+|week\s*\d+|end\s*of\s*(?:treatment|study)|follow[\s-]?up)",
        ]

        visit_set = set()
        for pattern in visit_patterns:
            for match in re.finditer(pattern, content, re.IGNORECASE):
                visit_name = match.group(1).title()
                if visit_name not in visit_set:
                    visit_set.add(visit_name)

        # Create Visit objects
        visit_num = 1
        for visit_name in sorted(visit_set):
            visits.append(
                Visit(
                    id=visit_name.upper().replace(" ", "")[:8],
                    name=visit_name,
                    visitnum=visit_num,
                )
            )
            visit_num += 1

        # Default visits if none found
        if not visits:
            visits = [
                Visit(id="SCREEN", name="Screening", visitnum=1),
                Visit(id="BASELINE", name="Baseline", visitnum=2),
                Visit(id="WEEK1", name="Week 1", visitnum=3),
                Visit(id="EOS", name="End of Study", visitnum=99),
            ]

        return visits

    def _validate_config(self, config: StudyConfig) -> List[Dict[str, str]]:
        """Validate study configuration."""
        issues = []

        if config.study_id == "UNKNOWN":
            issues.append({"type": "error", "message": "Study ID not found"})

        if not config.arms:
            issues.append({"type": "error", "message": "No treatment arms defined"})

        if not config.visits:
            issues.append({"type": "warning", "message": "No visits defined"})

        return issues

    def _write_config(self, config: StudyConfig):
        """Write configuration to output file."""
        if self.config.output_path:
            self.config.output_path.parent.mkdir(parents=True, exist_ok=True)

            output = {
                "schema_version": 1,
                "study": {
                    "id": config.study_id,
                    "name": config.study_name,
                    "phase": config.phase,
                    "therapeutic_area": config.therapeutic_area,
                    "indication": config.indication,
                },
                "design": {
                    "type": config.design_type,
                    "blinding": config.blinding,
                    "randomization": config.randomization,
                    "stratification_factors": config.stratification_factors,
                },
                "arms": [asdict(arm) for arm in config.arms],
                "visits": [asdict(visit) for visit in config.visits],
                "metadata": config.metadata,
            }

            with open(self.config.output_path, "w", encoding="utf-8") as f:
                yaml.dump(output, f, default_flow_style=False, sort_keys=False)

    def _dry_run(self) -> SkillResult:
        """Show what would be done without making changes."""
        return self.create_result(
            SkillStatus.DRY_RUN,
            f"Would create study configuration at {self.config.output_path}",
            outputs={
                "input": str(self.config.input_path),
                "output": str(self.config.output_path),
            },
        )


def main():
    parser = create_argument_parser("study-setup", "Configure study-level metadata")
    args = parser.parse_args()

    config = SkillConfig.from_args(args)
    skill = StudySetupSkill(config)
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
