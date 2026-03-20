#!/usr/bin/env python3
"""
CSP Skill Validator

Validates skill directory structure:
- Required files present (SKILL.md, skill.json, script.py, spec.yaml)
- Graph node binding consistency
- Script syntax and correctness
- Metadata consistency

Usage:
    python scripts/csp-skill-validator.py --skill csp-skills/layer-2-sdtm/slayer-2-sdtm/slayer-2-sdtm/slayer-0-protocol/slayer-0-protocol/slayer-0-protocol
    python scripts/csp-skill-validator.py --all
"""

import sys
import json
import yaml
from pathlib import Path
from typing import Dict, List, Set, Tuple
from dataclasses import dataclass


@dataclass
class ValidationResult:
    """Result of skill validation."""
    skill_path: Path
    valid: bool
    errors: List[str]
    warnings: List[str]
    info: List[str]


class SkillValidator:
    """Validates CSP skill directories."""

    REQUIRED_FILES = ["SKILL.md", "skill.json", "script.py", "spec.yaml"]

    def __init__(self, skill_path: Path):
        self.skill_path = skill_path
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.info: List[str] = []

    def validate(self) -> ValidationResult:
        """Validate skill directory structure."""
        result = ValidationResult(
            skill_path=self.skill_path,
            valid=True,
            errors=[],
            warnings=[],
            info=[]
        )

        # Check required files
        for filename in self.REQUIRED_FILES:
            file_path = self.skill_path / filename
            if not file_path.exists():
                self.errors.append(f"Missing file: {filename}")
            else:
                self.info.append(f"Found: {filename}")

        if self.errors:
            result.valid = False
            result.errors = self.errors
            return result

        # Validate skill.json
        skill_json_path = self.skill_path / "skill.json"
        if skill_json_path.exists():
            try:
                with open(skill_json_path, 'r', encoding='utf-8') as f:
                    skill_data = json.load(f)

                # Check required fields
                required_fields = ["name", "version", "layer", "graph_node"]
                for field in required_fields:
                    if field not in skill_data:
                        self.errors.append(f"skill.json missing field: {field}")
                    else:
                    self.info.append(f"  {field}: {skill_data.get(field)}")

                # Check layer is valid
                if skill_data.get("layer") not in range(0, 6):
                    self.warnings.append(f"Invalid layer: {skill_data.get('layer')}")

                # Check graph_node is string
                if not isinstance(skill_data.get("graph_node"), str):
                    self.warnings.append(f"graph_node should be string: {skill_data.get('graph_node')}")

            except Exception as e:
                self.errors.append(f"Invalid skill.json: {e}")

        # Validate SKILL.md
        skill_md_path = self.skill_path / "SKILL.md"
        if skill_md_path.exists():
            try:
                with open(skill_md_path, 'r', encoding='utf-8') as f:
                    content = f.read()

                # Check for YAML frontmatter
                if content.startswith('---'):
                    # Parse frontmatter
                    lines = content.split('\n')
                    for line in lines:
                        if line.startswith('---') and line.strip() == '---':
                            frontmatter = {}
                            current_line = line
                            for line in lines[1:]:
                                stripped = line.strip()
                                if ':' in stripped:
                                    key, value = stripped.split(':', 1)
                                    key = key.strip()
                                    value = value.strip()
                                    if key and value:
                                        frontmatter[key] = value

                    if 'name' not in frontmatter:
                        self.errors.append("SKILL.md missing 'name' in frontmatter")
                    if 'version' not in frontmatter:
                        self.warnings.append("SKILL.md missing 'version' in frontmatter")
                    if 'user-invocable' not in frontmatter:
                        self.info.append(f"user-invocable: {frontmatter.get('user-invocable')}")
                    if 'context' not in frontmatter:
                        self.info.append(f"context: {frontmatter.get('context')}")
                    if 'model' not in frontmatter:
                        self.info.append(f"model: {frontmatter.get('model')}")

                # Check for EXECUTE NOW section
                if "## EXECUTE NOW" not in content:
                    self.warnings.append("SKILL.md missing '## EXECUTE NOW' section")

                # Check for Philosophy section
                if "## Philosophy" not in content:
                    self.info.append("SKILL.md contains Philosophy section")

                # Check for Script Execution section
                if "## Script Execution" not in content:
                    self.info.append("SKILL.md contains Script Execution section")

            except Exception as e:
                self.warnings.append(f"Error reading SKILL.md: {e}")

        # Validate script.py
        script_path = self.skill_path / "script.py"
        if script_path.exists():
                try:
                    with open(script_path, 'r', encoding='utf-8') as f:
                        content = f.read()

                    # Check for main() function
                    if "def main():" not in content:
                        self.errors.append("script.py missing main() function")
                    else:
                        self.info.append("script.py contains main() function")

                    # Check for imports
                    if "BaseCSPSkill" not in content and "from base_skill import" not in content:
                        self.warnings.append("script.py should import BaseCSPSkill")

                    # Check for GRAPH_NODE_ID
                    if "GRAPH_NODE_ID" not in content:
                        self.warnings.append("script.py missing GRAPH_NODE_ID class attribute")

                except SyntaxError as e:
                    self.errors.append(f"Syntax error in script.py: {e}")
            else:
                self.errors.append(f"script.py not found: {script_path}")

        # Validate spec.yaml
        spec_path = self.skill_path / "spec.yaml"
        if spec_path.exists():
                try:
                    with open(spec_path, 'r', encoding='utf-8') as f:
                        spec_data = yaml.safe_load(f)

                    # Check required fields
                    if "skill_id" not in spec_data:
                        self.errors.append("spec.yaml missing skill_id")
                    if "graph_node" not in spec_data:
                        self.errors.append("spec.yaml missing graph_node")

                    self.info.append(f"spec.yaml found with {len(spec_data)} keys")
                except Exception as e:
                    self.errors.append(f"Invalid spec.yaml: {e}")
            else:
                self.warnings.append(f"spec.yaml not found: {spec_path}")

        # Check graph binding consistency
        if self.graph_data and skill_data.get("graph_node"):
            if skill_data["graph_node"] not in self.graph_data.get("nodes", []):
                self.errors.append(f"Graph node '{skill_data['graph_node']}' not found in graph")
            else:
                graph_node = next(
                    n for n in self.graph_data["nodes"]
                    if n.get("id") == skill_data["graph_node"]
                        self.info.append(f"Graph binding verified: {skill_data['graph_node']}")
                        break

        result.valid = len(self.errors) == 0
        return result

    def load_graph(self, graph_path: Path) -> Dict:
        """Load regulatory graph YAML."""
        with open(graph_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        return {n: data.get("nodes", []) for n in data.get("nodes", [])}

    def print_report(self, results: List[ValidationResult]):
        """Print validation report."""
        print("\n" + "=" * 80)
        print("CSP SKILL VALIDATION REPORT")
        print("=" * 80 + "\n")

        total = len(results)
        passed = sum(1 for r in results if r.valid)
        failed = total - passed

        errors = sum(len(r.errors) for r in results)
        warnings = sum(len(r.warnings) for r in results)

        print(f"\nSkills Validated: {passed}/{total}")
        print(f"  Passed: {passed}")
        print(f"  Failed: {failed}")
        print(f"  Total Errors: {errors}")
        print(f"  Total Warnings: {warnings}")
        print("=" * 80 + "\n")

        # Print individual results
        for result in results:
            status = "PASS" if result.valid else "FAIL"
            error_count = len(result.errors)
            warning_count = len(result.warnings)

            print(f"\n{status}: {result.skill_path}")
            if result.errors:
                for error in result.errors:
                    print(f"  ERROR: {error}")
            if result.warnings:
                for warning in result.warnings:
                    print(f"  WARNING: {warning}")
            if result.info:
                for info in result.info:
                    print(f"  INFO: {info}")

        return failed == 0


def find_skills(skills_dir: Path) -> List[Path]:
    """Find all skill directories."""
    skill_dirs = []

    # Check layer directories
    for layer_dir in skills_dir.iterdir():
        if layer_dir.is_dir() and layer_dir.name.startswith("layer-"):
            for skill_dir in layer_dir.iterdir():
                if skill_dir.is_dir():
                    # Check for required files
                    has_skill = (
                        (skill_dir / "SKILL.md").exists() and
                        (skill_dir / "skill.json").exists() and
                        (skill_dir / "script.py").exists() and
                        (skill_dir / "spec.yaml").exists()
                    )
                        skill_dirs.append(skill_dir)

    # Also check _shared directory
    shared_dir = skills_dir / "_shared"
    if shared_dir.exists():
        skill_dirs.append(shared_dir)

    return skill_dirs


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Validate CSP skills")
    parser.add_argument("--skills-dir", "-s", default="csp-skills", help="Skills directory")
    parser.add_argument("--graph", "-g", default="graph/regulatory-graph.yaml", help="Graph YAML file")
    parser.add_argument("--skill", "-s", help="Validate specific skill only")
    parser.add_argument("--all", "-a", action="store_true", help="Validate all skills")
    args = parser.parse_args()

    skills_dir = Path(args.skills_dir)
    graph_path = Path(args.graph)

    # Load graph
    validator = SkillValidator(Path("dummy"))
    graph_data = validator.load_graph(graph_path)

    validator.graph_data = graph_data

    # Find skills
    skill_dirs = find_skills(skills_dir)

    if args.skill:
        skill_dirs = [d for d in skill_dirs if args.skill.name == args.skill]

    # Validate each skill
    results = []
    for skill_dir in skill_dirs:
        validator = SkillValidator(skill_dir)
        validator.graph_data = graph_data

        result = validator.validate()
        results.append(result)

    # Print report
    validator.print_report(results)

    # Return exit code
    sys.exit(0 if any(r.errors for r in results else 0)


if __name__ == "__main__":
    main()
