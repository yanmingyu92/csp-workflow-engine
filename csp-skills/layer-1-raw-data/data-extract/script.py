#!/usr/bin/env python3
"""Data Extract - Extract raw clinical data from EDC source."""

import sys
import yaml
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "_shared"))

from base_skill import (
    BaseCSPSkill,
    SkillConfig,
    SkillResult,
    SkillStatus,
    create_argument_parser,
    main_wrapper,
)
from io_handlers import CSVHandler, DatasetReader


class DataExtractSkill(BaseCSPSkill):
    """Extract raw clinical data from EDC system."""

    GRAPH_NODE_ID = "edc-extract"
    REQUIRED_INPUT_VARS = []
    OUTPUT_VARS = ["raw_datasets", "manifest"]
    SKILL_NAME = "data-extract"
    SKILL_VERSION = "1.0.0"

    def run(self) -> SkillResult:
        """Execute data extraction."""
        self.log_info(f"Starting data extraction from {self.config.input_path}")

        if self.config.dry_run:
            return self._dry_run()

        # Load study config
        study_config = self._load_study_config()

        # Find all data files
        source_files = self._find_source_files()
        if not source_files:
            return self.create_result(
                SkillStatus.ERROR, "No data files found in source directory"
            )

        # Extract each dataset
        extracted_datasets = []
        for source_file in source_files:
            result = self._extract_dataset(source_file)
            if result:
                extracted_datasets.append(result)

        # Create extraction manifest
        manifest = self._create_manifest(extracted_datasets, study_config)
        self._write_manifest(manifest)

        self.metrics["datasets_extracted"] = len(extracted_datasets)
        self.metrics["total_records"] = sum(
            d.get("row_count", 0) for d in extracted_datasets
        )

        return self.create_result(
            SkillStatus.SUCCESS,
            f"Extracted {len(extracted_datasets)} datasets",
            outputs={
                "datasets": extracted_datasets,
                "manifest": str(self.config.output_path / "extraction-manifest.yaml"),
            },
        )

    def _load_study_config(self) -> Dict:
        """Load study configuration."""
        config_path = self.config.study_config_path or Path("specs/study-config.yaml")
        if config_path.exists():
            with open(config_path, "r") as f:
                return yaml.safe_load(f) or {}
        return {}

    def _find_source_files(self) -> List[Path]:
        """Find all data files in source directory."""
        source_dir = self.config.input_path
        if not source_dir or not source_dir.exists():
            return []

        files = []
        for ext in [".csv", ".sas7bdat", ".xpt", ".CSV", ".XPT"]:
            files.extend(source_dir.glob(f"*{ext}"))

        return sorted(files)

    def _extract_dataset(self, source_file: Path) -> Optional[Dict[str, Any]]:
        """Extract a single dataset."""
        try:
            reader = DatasetReader()
            data = reader.read(source_file)

            # Get dataset name from filename
            dataset_name = source_file.stem.upper()

            # Write to output
            output_file = self.config.output_path / f"{dataset_name.lower()}.csv"
            output_file.parent.mkdir(parents=True, exist_ok=True)

            handler = CSVHandler()
            handler.write(data, output_file)

            row_count = len(list(data.values())[0]) if data else 0
            var_count = len(data)

            self.log_info(
                f"Extracted {dataset_name}: {row_count} records, {var_count} variables"
            )

            return {
                "name": dataset_name,
                "source_file": str(source_file),
                "output_file": str(output_file),
                "row_count": row_count,
                "variable_count": var_count,
                "variables": list(data.keys()),
            }

        except Exception as e:
            self.log_error(f"Failed to extract {source_file}: {e}")
            return None

    def _create_manifest(
        self, datasets: List[Dict], study_config: Dict
    ) -> Dict[str, Any]:
        """Create extraction manifest."""
        return {
            "schema_version": 1,
            "extraction": {
                "timestamp": datetime.utcnow().isoformat(),
                "source_path": str(self.config.input_path),
                "output_path": str(self.config.output_path),
                "tool": self.SKILL_NAME,
                "version": self.SKILL_VERSION,
            },
            "study": {
                "id": study_config.get("study", {}).get("id", "UNKNOWN"),
                "name": study_config.get("study", {}).get("name", ""),
            },
            "data_cut": {
                "date": datetime.utcnow().strftime("%Y-%m-%d"),
                "description": "Full data extraction",
            },
            "datasets": datasets,
            "summary": {
                "total_datasets": len(datasets),
                "total_records": sum(d.get("row_count", 0) for d in datasets),
            },
        }

    def _write_manifest(self, manifest: Dict):
        """Write extraction manifest."""
        manifest_path = self.config.output_path / "extraction-manifest.yaml"
        manifest_path.parent.mkdir(parents=True, exist_ok=True)

        with open(manifest_path, "w", encoding="utf-8") as f:
            yaml.dump(manifest, f, default_flow_style=False, sort_keys=False)

        self.log_info(f"Manifest written to {manifest_path}")

    def _dry_run(self) -> SkillResult:
        """Show what would be done."""
        source_files = self._find_source_files()
        return self.create_result(
            SkillStatus.DRY_RUN,
            f"Would extract {len(source_files)} datasets",
            outputs={"source_files": [str(f) for f in source_files]},
        )


def main():
    parser = create_argument_parser(
        "data-extract", "Extract raw clinical data from EDC"
    )
    parser.add_argument("--study-config", help="Study configuration file")
    args = parser.parse_args()

    config = SkillConfig.from_args(args)
    config.study_config_path = Path(args.study_config) if args.study_config else None

    skill = DataExtractSkill(config)
    result = skill.run()

    print(result.to_json())
    sys.exit(0 if result.status in [SkillStatus.SUCCESS, SkillStatus.WARNING] else 1)


if __name__ == "__main__":
    main()
