"""Primary deterministic graders for the V7 routing-sensitive experiment."""

from __future__ import annotations

import ast
import json
import math
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import yaml


class HoldoutLeakageError(ValueError):
    """Raised when development and held-out panels are not isolated."""


def _attempt(
    attempts: list[dict[str, Any]],
    strategy: str,
    payload: str,
) -> Any | None:
    try:
        parsed = json.loads(payload)
    except (json.JSONDecodeError, TypeError) as error:
        attempts.append(
            {
                "strategy": strategy,
                "status": "failed",
                "error": str(error)[:300],
            }
        )
        return None
    if not isinstance(parsed, Mapping):
        attempts.append(
            {
                "strategy": strategy,
                "status": "failed",
                "error": "top-level JSON value is not an object",
            }
        )
        return None
    attempts.append({"strategy": strategy, "status": "success", "error": None})
    return dict(parsed)


def extract_answer_json(response: str) -> tuple[dict[str, Any] | None, list[dict]]:
    """Extract an answer object while preserving every parse attempt."""
    attempts: list[dict[str, Any]] = []
    parsed = _attempt(attempts, "full_response_json", response.strip())
    if parsed is not None:
        return parsed, attempts

    for index, match in enumerate(
        re.finditer(r"```(?:json)?\s*(.*?)```", response, re.I | re.S)
    ):
        parsed = _attempt(
            attempts, f"fenced_json_{index}", match.group(1).strip()
        )
        if parsed is not None:
            return parsed, attempts

    decoder = json.JSONDecoder()
    for index, character in enumerate(response):
        if character != "{":
            continue
        try:
            candidate, end = decoder.raw_decode(response[index:])
        except json.JSONDecodeError as error:
            attempts.append(
                {
                    "strategy": f"raw_decode_at_{index}",
                    "status": "failed",
                    "error": str(error)[:300],
                }
            )
            continue
        if isinstance(candidate, Mapping):
            attempts.append(
                {
                    "strategy": f"raw_decode_at_{index}",
                    "status": "success",
                    "error": None,
                    "consumed_characters": end,
                }
            )
            return dict(candidate), attempts
    return None, attempts


def _path_get(value: Any, path: str) -> Any:
    current = value
    if not path:
        return current
    for component in path.split("."):
        if isinstance(current, Mapping) and component in current:
            current = current[component]
            continue
        if isinstance(current, Sequence) and not isinstance(current, (str, bytes)):
            try:
                current = current[int(component)]
            except (ValueError, IndexError):
                raise KeyError(path) from None
            continue
        raise KeyError(path)
    return current


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _validate_define_xml(value: Any, criterion: Mapping[str, Any]) -> tuple[bool, str]:
    if not isinstance(value, str):
        return False, "XML value is not a string"
    try:
        root = ET.fromstring(value)
    except ET.ParseError as error:
        return False, f"XML parse failed: {error}"
    if _local_name(root.tag) != "ODM":
        return False, "root element must be ODM"
    tags = [_local_name(element.tag) for element in root.iter()]
    if "ComputationalMethod" in tags:
        return False, "ComputationalMethod is not admitted; use ODM MethodDef"
    methods = {
        element.attrib.get("OID")
        for element in root.iter()
        if _local_name(element.tag) == "MethodDef"
    }
    items = {
        element.attrib.get("OID")
        for element in root.iter()
        if _local_name(element.tag) == "ItemDef"
    }
    item_refs = [
        element
        for element in root.iter()
        if _local_name(element.tag) == "ItemRef"
    ]
    for expected in criterion.get("required_item_oids", []):
        if expected not in items:
            return False, f"missing ItemDef {expected}"
        if not any(row.attrib.get("ItemOID") == expected for row in item_refs):
            return False, f"missing ItemRef for {expected}"
    for expected in criterion.get("required_method_oids", []):
        if expected not in methods:
            return False, f"missing MethodDef {expected}"
        if not any(row.attrib.get("MethodOID") == expected for row in item_refs):
            return False, f"missing MethodOID reference for {expected}"
    metadata = next(
        (
            element
            for element in root.iter()
            if _local_name(element.tag) == "MetaDataVersion"
        ),
        None,
    )
    if metadata is None:
        return False, "missing MetaDataVersion"
    define_attributes = {
        _local_name(key): item for key, item in metadata.attrib.items()
    }
    for attribute in ("DefineVersion", "StandardName", "StandardVersion"):
        if not define_attributes.get(attribute):
            return False, f"missing def:{attribute}"
    return True, "schema/cross-reference checks passed"


def _validate_object_schema(
    value: Any, required: Mapping[str, str]
) -> tuple[bool, str]:
    if not isinstance(value, Mapping):
        return False, "value is not an object"
    expected_types = {
        "string": str,
        "array": list,
        "object": dict,
        "boolean": bool,
        "number": (int, float),
        "integer": int,
    }
    for key, type_name in required.items():
        if key not in value:
            return False, f"missing required property {key}"
        expected_type = expected_types.get(str(type_name))
        if expected_type is None:
            return False, f"unsupported schema type {type_name}"
        actual = value[key]
        if type_name in {"number", "integer"} and isinstance(actual, bool):
            return False, f"property {key} has boolean, not {type_name}"
        if not isinstance(actual, expected_type):
            return False, f"property {key} is not {type_name}"
    return True, "object schema passed"


ALLOWED_BUILTINS = {
    "abs": abs,
    "all": all,
    "any": any,
    "bool": bool,
    "float": float,
    "int": int,
    "len": len,
    "max": max,
    "min": min,
    "round": round,
    "str": str,
    "sum": sum,
    "tuple": tuple,
}
ALLOWED_ATTRIBUTES = {
    "endswith",
    "lower",
    "replace",
    "split",
    "startswith",
    "strip",
    "upper",
}
FORBIDDEN_AST = (
    ast.AsyncFunctionDef,
    ast.Await,
    ast.ClassDef,
    ast.Delete,
    ast.Global,
    ast.Import,
    ast.ImportFrom,
    ast.Nonlocal,
    ast.Raise,
    ast.Try,
    ast.While,
    ast.With,
)


def _validate_restricted_python(
    code: Any,
    function_name: str,
    cases: Sequence[Mapping[str, Any]],
) -> tuple[bool, str]:
    if not isinstance(code, str):
        return False, "code is not a string"
    try:
        tree = ast.parse(code)
    except SyntaxError as error:
        return False, f"Python syntax error: {error}"
    for node in ast.walk(tree):
        if isinstance(node, FORBIDDEN_AST):
            return False, f"forbidden AST node: {type(node).__name__}"
        if isinstance(node, ast.Name) and node.id.startswith("__"):
            return False, "dunder names are forbidden"
        if isinstance(node, ast.Attribute):
            if node.attr.startswith("__") or node.attr not in ALLOWED_ATTRIBUTES:
                return False, f"forbidden attribute: {node.attr}"
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in {"eval", "exec", "open", "compile", "__import__"}:
                return False, f"forbidden call: {node.func.id}"
    namespace: dict[str, Any] = {}
    try:
        exec(
            compile(tree, "<restricted-v7-answer>", "exec"),
            {"__builtins__": ALLOWED_BUILTINS},
            namespace,
        )
    except Exception as error:
        return False, f"restricted execution failed: {error}"
    function = namespace.get(function_name)
    if not callable(function):
        return False, f"missing function {function_name}"
    for index, case in enumerate(cases):
        try:
            actual = function(*case.get("args", []))
        except Exception as error:
            return False, f"case {index} raised: {error}"
        expected = case.get("expected")
        tolerance = float(case.get("tolerance", 0.0))
        if (
            isinstance(actual, (int, float))
            and not isinstance(actual, bool)
            and isinstance(expected, (int, float))
            and not isinstance(expected, bool)
            and tolerance > 0
        ):
            passed = math.isclose(
                float(actual), float(expected), abs_tol=tolerance, rel_tol=0.0
            )
        else:
            passed = actual == expected
        if not passed:
            return False, f"case {index}: {actual!r} != {expected!r}"
    return True, f"{len(cases)} restricted execution cases passed"


@dataclass(frozen=True)
class _CriterionResult:
    criterion_id: str
    criterion_type: str
    weight: float
    passed: bool
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.criterion_id,
            "type": self.criterion_type,
            "weight": self.weight,
            "passed": self.passed,
            "earned_weight": self.weight if self.passed else 0.0,
            "detail": self.detail,
        }


class DeterministicEvaluator:
    """Evaluate machine-verifiable atomic criteria with a fail-closed policy."""

    def _evaluate_one(
        self,
        criterion: Mapping[str, Any],
        answer: Mapping[str, Any],
        response: str,
        manifest: Mapping[str, Any],
    ) -> _CriterionResult:
        criterion_id = str(criterion.get("id", "unnamed"))
        criterion_type = str(criterion.get("type", "unknown"))
        weight = float(criterion.get("weight", 1.0))
        try:
            value = _path_get(answer, str(criterion.get("path", "")))
        except KeyError:
            value = None
            path_missing = True
        else:
            path_missing = False
        passed = False
        detail = ""
        try:
            if criterion_type == "json_exact":
                passed = not path_missing and value == criterion.get("expected")
                detail = f"observed={value!r}; expected={criterion.get('expected')!r}"
            elif criterion_type == "json_contains_all":
                expected = list(criterion.get("expected", []))
                if isinstance(value, str):
                    lowered = value.lower()
                    missing = [
                        item for item in expected if str(item).lower() not in lowered
                    ]
                elif isinstance(value, Sequence):
                    missing = [item for item in expected if item not in value]
                else:
                    missing = expected
                passed = not missing
                detail = f"missing={missing!r}"
            elif criterion_type == "json_set_equals":
                expected_set = set(criterion.get("expected", []))
                actual_set = set(value) if isinstance(value, list) else set()
                passed = actual_set == expected_set
                detail = (
                    f"observed={sorted(actual_set)!r}; "
                    f"expected={sorted(expected_set)!r}"
                )
            elif criterion_type == "forbidden_terms":
                found = [
                    term
                    for term in criterion.get("terms", [])
                    if str(term).lower() in response.lower()
                ]
                passed = not found
                detail = f"forbidden terms found={found!r}"
            elif criterion_type == "regex":
                passed = isinstance(value, str) and bool(
                    re.search(str(criterion.get("pattern", "")), value)
                )
                detail = f"regex matched={passed}"
            elif criterion_type == "provenance_citation":
                selected = {
                    row.get("chunk_id"): row
                    for row in manifest.get("selected_chunks", [])
                    if isinstance(row, Mapping)
                }
                citations = value if isinstance(value, list) else []
                unknown = [item for item in citations if item not in selected]
                if unknown:
                    passed = False
                    detail = (
                        f"citation IDs not present in the context manifest: {unknown}"
                    )
                else:
                    missing_requirements: list[dict[str, Any]] = []
                    cited_rows = [selected[item] for item in citations]
                    for requirement in criterion.get("required", []):
                        if not any(
                            row.get("skill_name") == requirement.get("skill_name")
                            and str(requirement.get("heading_contains", "")).lower()
                            in str(row.get("heading_path", "")).lower()
                            for row in cited_rows
                        ):
                            missing_requirements.append(dict(requirement))
                    passed = not missing_requirements and bool(citations)
                    detail = f"missing required provenance={missing_requirements!r}"
            elif criterion_type == "define_xml":
                passed, detail = _validate_define_xml(value, criterion)
            elif criterion_type == "object_schema":
                passed, detail = _validate_object_schema(
                    value, criterion.get("required", {})
                )
            elif criterion_type == "yaml_exact":
                if not isinstance(value, str):
                    passed, detail = False, "YAML value is not a string"
                else:
                    try:
                        yaml_value = yaml.safe_load(value)
                    except yaml.YAMLError as error:
                        passed, detail = False, f"YAML parse failed: {error}"
                    else:
                        mismatches = {}
                        for path, expected in criterion.get(
                            "expected_paths", {}
                        ).items():
                            try:
                                observed = _path_get(yaml_value, path)
                            except KeyError:
                                observed = None
                            if observed != expected:
                                mismatches[path] = {
                                    "observed": observed,
                                    "expected": expected,
                                }
                        passed = not mismatches
                        detail = f"mismatches={mismatches!r}"
            elif criterion_type == "restricted_python":
                passed, detail = _validate_restricted_python(
                    value,
                    str(criterion.get("function")),
                    criterion.get("cases", []),
                )
            else:
                passed = False
                detail = f"unsupported criterion type: {criterion_type}"
        except Exception as error:
            passed = False
            detail = (
                f"validator failed closed with {type(error).__name__}: {error}"
            )
        return _CriterionResult(
            criterion_id=criterion_id,
            criterion_type=criterion_type,
            weight=weight,
            passed=passed,
            detail=detail,
        )

    def evaluate(
        self,
        task: Mapping[str, Any],
        response: str,
        manifest: Mapping[str, Any],
    ) -> dict[str, Any]:
        answer, attempts = extract_answer_json(response)
        criteria = list(task.get("criteria", []))
        if answer is None:
            results = [
                _CriterionResult(
                    criterion_id=str(criterion.get("id", "unnamed")),
                    criterion_type=str(criterion.get("type", "unknown")),
                    weight=float(criterion.get("weight", 1.0)),
                    passed=False,
                    detail="answer JSON could not be parsed; fail-closed zero",
                )
                for criterion in criteria
            ]
            parse_status = "failed"
        else:
            results = [
                self._evaluate_one(
                    criterion, answer, response, manifest
                )
                for criterion in criteria
            ]
            parse_status = "success"
        total_weight = sum(result.weight for result in results)
        earned_weight = sum(
            result.weight for result in results if result.passed
        )
        return {
            "task_id": task.get("task_id"),
            "parse_status": parse_status,
            "parse_attempts": attempts,
            "criteria": [result.to_dict() for result in results],
            "earned_weight": earned_weight,
            "available_weight": total_weight,
            "score": (
                round(earned_weight / total_weight, 12)
                if total_weight > 0
                else 0.0
            ),
            "missing_failure_policy": (
                "unparseable_or_validator_failure_scores_zero"
            ),
        }


def _prompt_similarity(first: str, second: str) -> float:
    left = set(re.findall(r"[a-z0-9]+", first.lower()))
    right = set(re.findall(r"[a-z0-9]+", second.lower()))
    if not left and not right:
        return 1.0
    return len(left & right) / max(1, len(left | right))


def _flatten_expected(value: Any) -> list[str]:
    flattened: list[str] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            if key in {"expected", "terms", "pattern"}:
                flattened.extend(_flatten_expected(item))
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for item in value:
            flattened.extend(_flatten_expected(item))
    elif isinstance(value, (str, int, float, bool)):
        flattened.append(str(value))
    return flattened


def validate_holdout_isolation(
    development_tasks: Sequence[Mapping[str, Any]],
    heldout_tasks: Sequence[Mapping[str, Any]],
    *,
    maximum_prompt_similarity: float = 0.75,
) -> dict[str, Any]:
    errors: list[str] = []
    development_ids = {str(task.get("task_id")) for task in development_tasks}
    heldout_ids = [str(task.get("task_id")) for task in heldout_tasks]
    duplicate_ids = sorted(development_ids & set(heldout_ids))
    if duplicate_ids:
        errors.append(f"task IDs appear in both panels: {duplicate_ids}")
    if len(heldout_ids) != len(set(heldout_ids)):
        errors.append("held-out task IDs are not unique")

    maximum_observed = 0.0
    maximum_pair: tuple[str, str] | None = None
    for development in development_tasks:
        for heldout in heldout_tasks:
            similarity = _prompt_similarity(
                str(development.get("prompt", "")),
                str(heldout.get("prompt", "")),
            )
            if similarity > maximum_observed:
                maximum_observed = similarity
                maximum_pair = (
                    str(development.get("task_id")),
                    str(heldout.get("task_id")),
                )
            if similarity > maximum_prompt_similarity:
                errors.append(
                    "prompt overlap exceeds threshold for "
                    f"{development.get('task_id')} and {heldout.get('task_id')}: "
                    f"{similarity:.3f}"
                )
    for heldout in heldout_tasks:
        prompt = str(heldout.get("prompt", "")).lower()
        leaked = [
            expected
            for expected in _flatten_expected(heldout.get("criteria", []))
            if len(expected) >= 16 and expected.lower() in prompt
        ]
        if leaked:
            errors.append(
                f"held-out prompt {heldout.get('task_id')} contains long "
                f"expected-answer text: {leaked[:3]}"
            )
    if errors:
        raise HoldoutLeakageError("; ".join(errors))
    return {
        "passed": True,
        "development_count": len(development_tasks),
        "heldout_count": len(heldout_tasks),
        "maximum_prompt_similarity": round(maximum_observed, 6),
        "maximum_similarity_pair": maximum_pair,
        "answer_leakage_detected": False,
    }

