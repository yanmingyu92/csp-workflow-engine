#!/usr/bin/env python3
"""Demographics Table - Generate demographics summary table."""

import sys
from pathlib import Path
from typing import Dict, List, Any
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "_shared"))

from base_skill import (
    BaseCSPSkill,
    SkillConfig,
    SkillResult,
    SkillStatus,
    create_argument_parser,
)


class DemographicsTable(BaseCSPSkill):
    """Generate demographics summary table."""

    GRAPH_NODE_ID = "tfl-demographics"
    REQUIRED_INPUT_VARS = ["USUBJID", "TRT01P", "AGE", "SEX", "RACE"]
    OUTPUT_VARS = []
    SKILL_NAME = "demographics-table"
    SKILL_VERSION = "1.0.0"

    def run(self) -> SkillResult:
        """Execute demographics table generation."""
        self.log_info("Generating demographics table")

        if self.config.dry_run:
            return self._dry_run()

        # Read ADSL
        input_path = self.config.input_path or Path("output/adam/adsl.xpt")
        from io_handlers import DatasetReader

        reader = DatasetReader()
        adsl = reader.read(input_path)

        if not adsl:
            return self.create_result(SkillStatus.ERROR, "Could not read ADSL")

        # Filter to population
        population = self.config.population or "SAFFL"
        if population in adsl:
            keep = [i for i, f in enumerate(adsl[population]) if f == "Y"]
            adsl = {k: [v[i] for i in keep] for k, v in adsl.items()}

        n = len(adsl.get("USUBJID", []))
        if n == 0:
            return self.create_result(SkillStatus.ERROR, f"No subjects in {population}")

        # Group by treatment
        trt_groups = self._group_by_treatment(adsl)

        # Calculate statistics
        table_data = []

        # Age - continuous
        table_data.append({"row": "Age (years)", "indent": 0, "stat": ""})
        table_data.append(
            {"row": "  n", "stat": "n", **self._n_by_trt(trt_groups, "AGE")}
        )
        table_data.append(
            {
                "row": "  Mean (SD)",
                "stat": "mean_sd",
                **self._mean_sd_by_trt(trt_groups, "AGE"),
            }
        )
        table_data.append(
            {
                "row": "  Median",
                "stat": "median",
                **self._median_by_trt(trt_groups, "AGE"),
            }
        )
        table_data.append(
            {
                "row": "  Min, Max",
                "stat": "range",
                **self._range_by_trt(trt_groups, "AGE"),
            }
        )

        # Age group
        table_data.append({"row": "Age Group, n (%)", "indent": 0})
        for grp in ["<65", ">=65"]:
            counts = self._cat_counts_by_trt(trt_groups, "AGEGR1", grp)
            table_data.append({"row": f"  {grp}", **counts})

        # Sex
        table_data.append({"row": "Sex, n (%)", "indent": 0})
        for sex in ["M", "F"]:
            counts = self._cat_counts_by_trt(trt_groups, "SEX", sex)
            label = "Male" if sex == "M" else "Female"
            table_data.append({"row": f"  {label}", **counts})

        # Race
        table_data.append({"row": "Race, n (%)", "indent": 0})
        for race in ["WHITE", "BLACK OR AFRICAN AMERICAN", "ASIAN"]:
            counts = self._cat_counts_by_trt(trt_groups, "RACE", race)
            table_data.append({"row": f"  {race.title()}", **counts})

        # Write output
        output_path = self.config.output_path or Path("output/tfl/t_demographics.csv")
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Write CSV
        with open(output_path, "w", newline="", encoding="utf-8") as f:
            import csv

            trts = sorted(set(adsl.get("TRT01P", [])))
            fieldnames = ["Row"] + trts
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for row in table_data:
                csv_row = {"Row": row.get("row", "")}
                for trt in trts:
                    csv_row[trt] = row.get(trt, "")
                writer.writerow(csv_row)

        return self.create_result(
            SkillStatus.SUCCESS,
            f"Generated demographics table for {n} subjects",
            outputs={"output_file": str(output_path), "subjects": n},
        )

    def _group_by_treatment(self, data: Dict) -> Dict[str, Dict]:
        """Group data by treatment."""
        groups = defaultdict(lambda: defaultdict(list))
        n = len(data.get("USUBJID", []))
        for i in range(n):
            trt = (
                data.get("TRT01P", [""] * (i + 1))[i]
                if i < len(data.get("TRT01P", []))
                else "Unknown"
            )
            for var, values in data.items():
                groups[trt][var].append(values[i] if i < len(values) else "")
        return dict(groups)

    def _n_by_trt(self, groups: Dict, var: str) -> Dict:
        """Get non-missing n by treatment."""
        return {
            trt: str(len([v for v in g.get(var, []) if v not in [None, "", " "]]))
            for trt, g in groups.items()
        }

    def _mean_sd_by_trt(self, groups: Dict, var: str) -> Dict:
        """Calculate mean (SD) by treatment."""
        result = {}
        for trt, g in groups.items():
            vals = [float(v) for v in g.get(var, []) if v not in [None, "", " "]]
            if vals:
                import statistics

                mean = statistics.mean(vals)
                sd = statistics.stdev(vals) if len(vals) > 1 else 0
                result[trt] = f"{mean:.1f} ({sd:.1f})"
            else:
                result[trt] = ""
        return result

    def _median_by_trt(self, groups: Dict, var: str) -> Dict:
        """Calculate median by treatment."""
        result = {}
        for trt, g in groups.items():
            vals = [float(v) for v in g.get(var, []) if v not in [None, "", " "]]
            if vals:
                import statistics

                result[trt] = f"{statistics.median(vals):.1f}"
            else:
                result[trt] = ""
        return result

    def _range_by_trt(self, groups: Dict, var: str) -> Dict:
        """Calculate min, max by treatment."""
        result = {}
        for trt, g in groups.items():
            vals = [float(v) for v in g.get(var, []) if v not in [None, "", " "]]
            if vals:
                result[trt] = f"{min(vals):.0f}, {max(vals):.0f}"
            else:
                result[trt] = ""
        return result

    def _cat_counts_by_trt(self, groups: Dict, var: str, category: str) -> Dict:
        """Get counts and percentages by treatment for category."""
        result = {}
        for trt, g in groups.items():
            n_total = len(g.get(var, []))
            n_cat = sum(1 for v in g.get(var, []) if str(v).upper() == category.upper())
            pct = (n_cat / n_total * 100) if n_total > 0 else 0
            result[trt] = f"{n_cat} ({pct:.1f}%)"
        return result

    def _dry_run(self) -> SkillResult:
        return self.create_result(
            SkillStatus.DRY_RUN, "Would generate demographics table", outputs={}
        )


def main():
    parser = create_argument_parser(
        "demographics-table", "Generate demographics summary table"
    )
    parser.add_argument(
        "--population", "-p", default="SAFFL", help="Population flag to filter"
    )
    args = parser.parse_args()
    config = SkillConfig.from_args(args)
    config.population = args.population
    result = DemographicsTable(config).run()
    print(result.to_json())
    sys.exit(0 if result.status in [SkillStatus.SUCCESS, SkillStatus.WARNING] else 1)


if __name__ == "__main__":
    main()
