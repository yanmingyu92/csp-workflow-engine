#!/usr/bin/env python3
"""
SAP Parser - Statistical Analysis Plan Parser

Parses SAP documents to extract:
- Primary and secondary endpoints
- Analysis populations (ITT, mITT, PP, Safety)
- Statistical methods and parameters
- TFL shell specifications

Usage:
    python script.py --input docs/sap.pdf --output specs/sap-parsed.yaml
"""

import sys
import json
import yaml
import argparse
import re
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime

# Add parent path for shared utilities
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "_shared"))

from base_skill import (
    BaseCSPSkill,
    SkillResult,
    SkillConfig,
    SkillStatus,
    create_argument_parser,
    main_wrapper,
)


@dataclass
class Endpoint:
    """Represents a clinical endpoint."""

    id: str
    name: str
    description: str = ""
    method: str = ""
    population: str = ""
    dataset: str = ""
    hypothesis: Dict[str, str] = field(default_factory=dict)
    multiplicity: str = ""
    subgroups: List[str] = field(default_factory=list)
    page_ref: str = ""


@dataclass
class Population:
    """Represents an analysis population."""

    id: str
    name: str
    description: str = ""
    derivation: Dict[str, str] = field(default_factory=dict)
    criteria: List[str] = field(default_factory=list)
    page_ref: str = ""


@dataclass
class StatisticalMethod:
    """Represents a statistical method."""

    id: str
    name: str
    description: str = ""
    parameters: Dict[str, Any] = field(default_factory=dict)
    assumptions: List[str] = field(default_factory=list)
    page_ref: str = ""


@dataclass
class TFLShell:
    """Represents a TFL shell specification."""

    id: str
    title: str
    type: str  # table, figure, listing
    population: str = ""
    purpose: str = ""
    page_ref: str = ""


@dataclass
class SAPExtraction:
    """Complete SAP extraction result."""

    metadata: Dict[str, Any] = field(default_factory=dict)
    primary_endpoints: List[Endpoint] = field(default_factory=list)
    secondary_endpoints: List[Endpoint] = field(default_factory=list)
    exploratory_endpoints: List[Endpoint] = field(default_factory=list)
    populations: List[Population] = field(default_factory=list)
    methods: List[StatisticalMethod] = field(default_factory=list)
    tfl_tables: List[TFLShell] = field(default_factory=list)
    tfl_figures: List[TFLShell] = field(default_factory=list)
    tfl_listings: List[TFLShell] = field(default_factory=list)
    issues: List[Dict[str, str]] = field(default_factory=list)


class SAPParser(BaseCSPSkill):
    """
    Parser for Statistical Analysis Plans.

    Extracts structured information from SAP documents for
    downstream specification generation and programming.
    """

    GRAPH_NODE_ID = "sap-review"
    REQUIRED_INPUT_VARS = []
    OUTPUT_VARS = ["endpoints", "populations", "methods", "tfl_shells"]
    SKILL_NAME = "sap-parser"
    SKILL_VERSION = "1.0.0"

    # Common population patterns
    POPULATION_PATTERNS = {
        "ITT": [
            r"intent[- ]to[- ]treat",
            r"ITT",
            r"full analysis set",
            r"FAS",
        ],
        "mITT": [
            r"modified intent[- ]to[- ]treat",
            r"mITT",
            r"modified ITT",
        ],
        "PP": [
            r"per[- ]protocol",
            r"PP\s*(?:population|set)?",
        ],
        "SAF": [
            r"safety\s*(?:population|set)?",
            r"SAF",
            r"as[- ]treated",
        ],
    }

    # Common statistical method patterns
    METHOD_PATTERNS = {
        "CMH": r"cochran[- ]mantel[- ]haenszel|CMH",
        "Chi-square": r"chi[- ]square|χ²|chi squared",
        "Fisher": r"fisher'?s? (?:exact )?test",
        "t-test": r"t[- ]test|student'?s? t",
        "ANOVA": r"analysis of variance|ANOVA",
        "ANCOVA": r"analysis of covariance|ANCOVA",
        "Log-rank": r"log[- ]rank|mantel[- ]cox",
        "Cox": r"cox (?:proportional hazards|regression|model)",
        "Kaplan-Meier": r"kaplan[- ]meier|KM",
        "Mixed Model": r"mixed (?:effects? )?model|MMRM",
        "Wilcoxon": r"wilcoxon (?:rank[- ]sum|signed[- ]rank)",
        "Descriptive": r"descriptive (?:statistics|analysis)",
    }

    def run(self) -> SkillResult:
        """Execute SAP parsing."""
        self.log_info(f"Starting SAP parsing for {self.config.input_path}")

        # Load study config if available
        if self.config.study_config_path:
            self.load_study_config()
            self.log_info(f"Loaded study config from {self.config.study_config_path}")

        # Extract content from SAP document
        if self.config.dry_run:
            return self._dry_run()

        # Parse SAP document
        extraction = self._extract_sap()

        if not extraction:
            return self.create_result(
                SkillStatus.ERROR,
                "Failed to extract content from SAP document",
            )

        # Validate extraction
        validation_issues = self._validate_extraction(extraction)

        if validation_issues and self.config.strict_mode:
            return self.create_result(
                SkillStatus.ERROR,
                f"Validation failed: {len(validation_issues)} issues found",
                outputs={"issues": validation_issues},
            )

        # Write outputs
        output_paths = self._write_outputs(extraction)

        # Build result
        result_data = {
            "primary_endpoints": len(extraction.primary_endpoints),
            "secondary_endpoints": len(extraction.secondary_endpoints),
            "populations": len(extraction.populations),
            "methods": len(extraction.methods),
            "tfl_tables": len(extraction.tfl_tables),
            "tfl_figures": len(extraction.tfl_figures),
            "tfl_listings": len(extraction.tfl_listings),
            "issues": len(extraction.issues),
            "output_files": list(output_paths.keys()),
        }

        self.metrics.update(result_data)

        status = SkillStatus.WARNING if extraction.issues else SkillStatus.SUCCESS
        message = f"SAP parsed: {len(extraction.primary_endpoints)} primary endpoints, {len(extraction.populations)} populations"

        return self.create_result(status, message, outputs=result_data)

    def _extract_sap(self) -> Optional[SAPExtraction]:
        """Extract structured content from SAP document."""
        extraction = SAPExtraction()

        # Set metadata
        extraction.metadata = {
            "extraction_date": datetime.utcnow().isoformat(),
            "source_file": str(self.config.input_path),
            "study_id": self.study_config.get("study", {}).get("id", "UNKNOWN"),
            "parser_version": self.SKILL_VERSION,
        }

        # Read SAP content
        content = self._read_document()
        if not content:
            self.log_error("Could not read SAP document")
            return None

        # Extract sections
        self._extract_endpoints(content, extraction)
        self._extract_populations(content, extraction)
        self._extract_methods(content, extraction)
        self._extract_tfl_shells(content, extraction)

        return extraction

    def _read_document(self) -> Optional[str]:
        """Read content from document."""
        path = self.config.input_path

        if not path.exists():
            self.log_error(f"Input file not found: {path}")
            return None

        suffix = path.suffix.lower()

        if suffix == ".pdf":
            return self._read_pdf(path)
        elif suffix in [".docx", ".doc"]:
            return self._read_docx(path)
        elif suffix == ".txt":
            return path.read_text(encoding="utf-8")
        else:
            self.log_error(f"Unsupported format: {suffix}")
            return None

    def _read_pdf(self, path: Path) -> Optional[str]:
        """Read PDF content."""
        try:
            import pdfplumber

            text_parts = []
            with pdfplumber.open(path) as pdf:
                for page in pdf.pages:
                    text = page.extract_text()
                    if text:
                        text_parts.append(text)
            return "\n\n".join(text_parts)
        except ImportError:
            self.log_warning("pdfplumber not installed, trying PyPDF2")
            try:
                import PyPDF2

                text_parts = []
                with open(path, "rb") as f:
                    reader = PyPDF2.PdfReader(f)
                    for page in reader.pages:
                        text = page.extract_text()
                        if text:
                            text_parts.append(text)
                return "\n\n".join(text_parts)
            except ImportError:
                self.log_error("No PDF library available. Install pdfplumber or PyPDF2")
                return None

    def _read_docx(self, path: Path) -> Optional[str]:
        """Read DOCX content."""
        try:
            import docx

            doc = docx.Document(path)
            return "\n\n".join(para.text for para in doc.paragraphs)
        except ImportError:
            self.log_error(
                "python-docx not installed. Install with: pip install python-docx"
            )
            return None

    def _extract_endpoints(self, content: str, extraction: SAPExtraction):
        """Extract endpoints from SAP content."""
        # Pattern for primary endpoint sections
        primary_patterns = [
            r"primary\s*(?:efficacy\s*)?endpoint[s]?(.*?)(?=secondary|exploratory|objective|$)",
            r"primary\s*objective[s]?(.*?)(?=secondary|exploratory|$)",
        ]

        # Pattern for secondary endpoint sections
        secondary_patterns = [
            r"secondary\s*(?:efficacy\s*)?endpoint[s]?(.*?)(?=exploratory|safety|statistical|$)",
            r"secondary\s*objective[s]?(.*?)(?=exploratory|$)",
        ]

        # Extract primary endpoints
        for pattern in primary_patterns:
            matches = re.findall(pattern, content, re.IGNORECASE | re.DOTALL)
            for match in matches:
                endpoints = self._parse_endpoint_list(match, "primary")
                extraction.primary_endpoints.extend(endpoints)

        # Extract secondary endpoints
        for pattern in secondary_patterns:
            matches = re.findall(pattern, content, re.IGNORECASE | re.DOTALL)
            for match in matches:
                endpoints = self._parse_endpoint_list(match, "secondary")
                extraction.secondary_endpoints.extend(endpoints)

        # Validate we found at least one primary
        if not extraction.primary_endpoints:
            extraction.issues.append(
                {
                    "type": "error",
                    "message": "No primary endpoints found in SAP",
                    "section": "endpoints",
                }
            )
            # Create a placeholder
            extraction.primary_endpoints.append(
                Endpoint(
                    id="EP001",
                    name="[MANUAL REVIEW REQUIRED - Primary endpoint not extracted]",
                    method="Unknown",
                    population="ITT",
                )
            )

    def _parse_endpoint_list(self, text: str, endpoint_type: str) -> List[Endpoint]:
        """Parse a list of endpoints from text."""
        endpoints = []

        # Split by common list markers
        items = re.split(r"\n\s*(?:\d+\.?|[a-z]\)|•|-)\s*", text)

        for i, item in enumerate(items):
            item = item.strip()
            if not item or len(item) < 10:
                continue

            # Create endpoint
            ep_id = f"EP{len(endpoints) + 1:03d}"
            if endpoint_type == "secondary":
                ep_id = f"EP_S{len(endpoints) + 1:02d}"

            endpoint = Endpoint(
                id=ep_id,
                name=self._extract_endpoint_name(item),
                description=item[:500],  # Truncate long descriptions
                method=self._extract_method(item),
                population=self._extract_population(item),
            )

            endpoints.append(endpoint)

        return endpoints

    def _extract_endpoint_name(self, text: str) -> str:
        """Extract endpoint name from text."""
        # Take first sentence or up to newline
        first_line = text.split("\n")[0].strip()
        if "." in first_line:
            return first_line.split(".")[0].strip()
        return first_line[:100]

    def _extract_method(self, text: str) -> str:
        """Extract statistical method from text."""
        for method_name, pattern in self.METHOD_PATTERNS.items():
            if re.search(pattern, text, re.IGNORECASE):
                return method_name
        return "Descriptive"

    def _extract_population(self, text: str) -> str:
        """Extract analysis population from text."""
        for pop_name, patterns in self.POPULATION_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, text, re.IGNORECASE):
                    return pop_name
        return "ITT"  # Default

    def _extract_populations(self, content: str, extraction: SAPExtraction):
        """Extract analysis populations from SAP content."""
        pop_patterns = [
            (r"analysis\s*population[s]?(.*?)(?=statistical|endpoint|method|$)", "all"),
            (r"patient\s*population[s]?(.*?)(?=statistical|endpoint|$)", "all"),
        ]

        defined_pops = set()

        for pattern, _ in pop_patterns:
            matches = re.findall(pattern, content, re.IGNORECASE | re.DOTALL)
            for match in matches:
                for pop_id, patterns in self.POPULATION_PATTERNS.items():
                    for p in patterns:
                        if (
                            re.search(p, match, re.IGNORECASE)
                            and pop_id not in defined_pops
                        ):
                            population = Population(
                                id=pop_id,
                                name=self._get_population_name(pop_id),
                                description=self._extract_population_description(
                                    match, pop_id
                                ),
                                derivation={
                                    "dataset": "ADSL",
                                    "flag_variable": f"{pop_id}FL",
                                },
                            )
                            extraction.populations.append(population)
                            defined_pops.add(pop_id)

        # Ensure at least ITT and Safety are defined
        if "ITT" not in defined_pops:
            extraction.populations.insert(
                0,
                Population(
                    id="ITT",
                    name="Intent-to-Treat",
                    description="All randomized subjects",
                    derivation={"dataset": "ADSL", "flag_variable": "ITTFL"},
                ),
            )
            extraction.issues.append(
                {
                    "type": "warning",
                    "message": "ITT population not explicitly defined, using default",
                    "section": "populations",
                }
            )

        if "SAF" not in defined_pops:
            extraction.populations.append(
                Population(
                    id="SAF",
                    name="Safety",
                    description="All subjects who received at least one dose of study drug",
                    derivation={"dataset": "ADSL", "flag_variable": "SAFFL"},
                )
            )

    def _get_population_name(self, pop_id: str) -> str:
        """Get full population name."""
        names = {
            "ITT": "Intent-to-Treat",
            "mITT": "Modified Intent-to-Treat",
            "PP": "Per-Protocol",
            "SAF": "Safety",
        }
        return names.get(pop_id, pop_id)

    def _extract_population_description(self, text: str, pop_id: str) -> str:
        """Extract population description from text."""
        # Find sentences mentioning the population
        sentences = re.split(r"[.!?]\s+", text)
        relevant = []
        for sentence in sentences:
            for pattern in self.POPULATION_PATTERNS.get(pop_id, []):
                if re.search(pattern, sentence, re.IGNORECASE):
                    relevant.append(sentence)
                    break
        return " ".join(relevant[:2])[:300]  # Limit length

    def _extract_methods(self, content: str, extraction: SAPExtraction):
        """Extract statistical methods from SAP content."""
        method_patterns = [
            r"statistical\s*method[s]?(.*?)(?=analysis\s*population|missing|interim|$)",
            r"analysis\s*method[s]?(.*?)(?=population|missing|$)",
        ]

        defined_methods = set()

        for pattern in method_patterns:
            matches = re.findall(pattern, content, re.IGNORECASE | re.DOTALL)
            for match in matches:
                for method_name, method_pattern in self.METHOD_PATTERNS.items():
                    if re.search(method_pattern, match, re.IGNORECASE):
                        if method_name not in defined_methods:
                            method = StatisticalMethod(
                                id=f"M{len(extraction.methods) + 1:03d}",
                                name=method_name,
                                description=f"Statistical method: {method_name}",
                                parameters={"alpha": 0.05},
                            )
                            extraction.methods.append(method)
                            defined_methods.add(method_name)

        # Add descriptive as fallback
        if "Descriptive" not in defined_methods:
            extraction.methods.append(
                StatisticalMethod(
                    id="M000",
                    name="Descriptive",
                    description="Descriptive statistics (n, mean, SD, median, range)",
                    parameters={},
                )
            )

    def _extract_tfl_shells(self, content: str, extraction: SAPExtraction):
        """Extract TFL shell specifications from SAP content."""
        # Pattern for table shells
        table_pattern = r"(?:table|tbl)\s*(\d+\.?\d*[- ]?\d*)\s*[:\-–]?\s*([^\n]+)"
        figure_pattern = r"(?:figure|fig)\s*(\d+\.?\d*[- ]?\d*)\s*[:\-–]?\s*([^\n]+)"
        listing_pattern = r"(?:listing|lst)\s*(\d+\.?\d*[- ]?\d*)\s*[:\-–]?\s*([^\n]+)"

        # Extract tables
        for match in re.finditer(table_pattern, content, re.IGNORECASE):
            extraction.tfl_tables.append(
                TFLShell(
                    id=f"Table {match.group(1)}",
                    title=match.group(2).strip(),
                    type="table",
                    population="ITT",  # Default
                )
            )

        # Extract figures
        for match in re.finditer(figure_pattern, content, re.IGNORECASE):
            extraction.tfl_figures.append(
                TFLShell(
                    id=f"Figure {match.group(1)}",
                    title=match.group(2).strip(),
                    type="figure",
                    population="ITT",
                )
            )

        # Extract listings
        for match in re.finditer(listing_pattern, content, re.IGNORECASE):
            extraction.tfl_listings.append(
                TFLShell(
                    id=f"Listing {match.group(1)}",
                    title=match.group(2).strip(),
                    type="listing",
                )
            )

    def _validate_extraction(self, extraction: SAPExtraction) -> List[Dict[str, str]]:
        """Validate extraction completeness."""
        issues = list(extraction.issues)

        # Check primary endpoint
        if not extraction.primary_endpoints:
            issues.append(
                {
                    "type": "error",
                    "message": "No primary endpoints extracted",
                }
            )

        # Check populations
        pop_ids = {p.id for p in extraction.populations}
        if "ITT" not in pop_ids:
            issues.append(
                {
                    "type": "warning",
                    "message": "ITT population not defined",
                }
            )
        if "SAF" not in pop_ids:
            issues.append(
                {
                    "type": "warning",
                    "message": "Safety population not defined",
                }
            )

        # Check methods
        if not extraction.methods:
            issues.append(
                {
                    "type": "warning",
                    "message": "No statistical methods extracted",
                }
            )

        return issues

    def _write_outputs(self, extraction: SAPExtraction) -> Dict[str, Path]:
        """Write extraction outputs to files."""
        output_paths = {}

        # Main parsed SAP output
        if self.config.output_path:
            sap_output = self._build_sap_yaml(extraction)
            self.config.output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config.output_path, "w", encoding="utf-8") as f:
                yaml.dump(sap_output, f, default_flow_style=False, sort_keys=False)
            output_paths["sap_parsed"] = self.config.output_path

        # TFL shells output
        tfl_path = (
            self.config.output_path.parent / "tfl-shells.yaml"
            if self.config.output_path
            else None
        )
        if tfl_path:
            tfl_output = self._build_tfl_yaml(extraction)
            with open(tfl_path, "w", encoding="utf-8") as f:
                yaml.dump(tfl_output, f, default_flow_style=False, sort_keys=False)
            output_paths["tfl_shells"] = tfl_path

        return output_paths

    def _build_sap_yaml(self, extraction: SAPExtraction) -> Dict[str, Any]:
        """Build YAML structure for SAP output."""
        return {
            "schema_version": 1,
            "sap_metadata": extraction.metadata,
            "endpoints": {
                "primary": [asdict(ep) for ep in extraction.primary_endpoints],
                "secondary": [asdict(ep) for ep in extraction.secondary_endpoints],
                "exploratory": [asdict(ep) for ep in extraction.exploratory_endpoints],
            },
            "populations": [asdict(p) for p in extraction.populations],
            "methods": [asdict(m) for m in extraction.methods],
            "issues": extraction.issues,
        }

    def _build_tfl_yaml(self, extraction: SAPExtraction) -> Dict[str, Any]:
        """Build YAML structure for TFL shells output."""
        return {
            "schema_version": 1,
            "source": str(self.config.input_path),
            "extraction_date": datetime.utcnow().isoformat(),
            "tables": [asdict(t) for t in extraction.tfl_tables],
            "figures": [asdict(f) for f in extraction.tfl_figures],
            "listings": [asdict(l) for l in extraction.tfl_listings],
        }

    def _dry_run(self) -> SkillResult:
        """Perform dry run without writing output."""
        return self.create_result(
            SkillStatus.DRY_RUN,
            f"Would parse SAP from {self.config.input_path}",
            outputs={
                "input": str(self.config.input_path),
                "output": str(self.config.output_path),
            },
        )


def main():
    """Main entry point."""
    parser = create_argument_parser(
        "sap-parser",
        "Parse Statistical Analysis Plan (SAP) to extract endpoints, populations, and methods",
    )
    args = parser.parse_args()

    config = SkillConfig.from_args(args)
    skill = SAPParser(config)
    result = skill.run()

    print(result.to_json())
    sys.exit(0 if result.status in [SkillStatus.SUCCESS, SkillStatus.WARNING] else 1)


if __name__ == "__main__":
    main()
