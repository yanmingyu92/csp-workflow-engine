from __future__ import annotations

import json
from pathlib import Path

import pytest

from experiments.v7_deterministic_eval import (
    DeterministicEvaluator,
    HoldoutLeakageError,
    extract_answer_json,
    validate_holdout_isolation,
)


def _task(criteria: list[dict]) -> dict:
    return {
        "task_id": "heldout-01",
        "node_id": "adam-adsl",
        "prompt": "Return the requested JSON object.",
        "criteria": criteria,
    }


def _manifest() -> dict:
    return {
        "selected_chunks": [
            {
                "chunk_id": "adam-adsl-builder::edge-cases::0::abcd1234",
                "skill_name": "adam-adsl-builder",
                "heading_path": "Edge Cases",
            },
            {
                "chunk_id": "adam-adsl-builder::constraints::0::efgh5678",
                "skill_name": "adam-adsl-builder",
                "heading_path": "Constraints",
            },
        ]
    }


def test_json_extraction_keeps_parse_attempt_history():
    response = (
        "Prose before.\n```json\n"
        '{"answer":{"SAFFL":"N","ITTFL":"Y"},"evidence_ids":["x"]}'
        "\n```\nProse after."
    )

    parsed, attempts = extract_answer_json(response)

    assert parsed["answer"]["SAFFL"] == "N"
    assert len(attempts) >= 2
    assert any(attempt["status"] == "success" for attempt in attempts)
    assert all("strategy" in attempt for attempt in attempts)


def test_exact_contains_set_forbidden_and_regex_validators():
    task = _task(
        [
            {
                "id": "saffl",
                "type": "json_exact",
                "path": "answer.SAFFL",
                "expected": "N",
                "weight": 1,
            },
            {
                "id": "notes",
                "type": "json_contains_all",
                "path": "answer.notes",
                "expected": ["prespecified SAP", "qualifying exposure"],
                "weight": 1,
            },
            {
                "id": "affected",
                "type": "json_set_equals",
                "path": "answer.affected",
                "expected": ["ADSL", "demographics"],
                "weight": 1,
            },
            {
                "id": "forbidden",
                "type": "forbidden_terms",
                "terms": ["TRTSDBJ", "always ITTFL=N"],
                "weight": 1,
            },
            {
                "id": "formula",
                "type": "regex",
                "path": "answer.formula",
                "pattern": r"TRTEDT\s*-\s*TRTSDT\s*\+\s*1",
                "weight": 1,
            },
        ]
    )
    response = json.dumps(
        {
            "answer": {
                "SAFFL": "N",
                "notes": "Use the prespecified SAP definition and qualifying exposure.",
                "affected": ["demographics", "ADSL"],
                "formula": "TRTEDT - TRTSDT + 1",
            },
            "evidence_ids": [],
        }
    )

    result = DeterministicEvaluator().evaluate(task, response, _manifest())

    assert result["score"] == 1.0
    assert all(item["passed"] for item in result["criteria"])


def test_provenance_citations_must_exist_in_manifest_and_match_required_section():
    task = _task(
        [
            {
                "id": "evidence",
                "type": "provenance_citation",
                "path": "evidence_ids",
                "required": [
                    {
                        "skill_name": "adam-adsl-builder",
                        "heading_contains": "Edge Cases",
                    }
                ],
                "weight": 2,
            }
        ]
    )
    valid = json.dumps(
        {
            "answer": {},
            "evidence_ids": [
                "adam-adsl-builder::edge-cases::0::abcd1234"
            ],
        }
    )
    hallucinated = json.dumps(
        {"answer": {}, "evidence_ids": ["made-up::chunk::id"]}
    )

    evaluator = DeterministicEvaluator()
    assert evaluator.evaluate(task, valid, _manifest())["score"] == 1.0
    failed = evaluator.evaluate(task, hallucinated, _manifest())
    assert failed["score"] == 0.0
    assert "not present in the context manifest" in failed["criteria"][0]["detail"]


def test_xml_cross_reference_validator_accepts_methoddef_and_rejects_computationalmethod():
    task = _task(
        [
            {
                "id": "define",
                "type": "define_xml",
                "path": "answer.xml",
                "required_item_oids": ["IT.DM.SEX"],
                "required_method_oids": ["MT.DM.USUBJID"],
                "weight": 1,
            }
        ]
    )
    valid_xml = """<ODM xmlns="http://www.cdisc.org/ns/odm/v1.3"
 xmlns:def="http://www.cdisc.org/ns/def/v2.1">
 <Study OID="S"><MetaDataVersion OID="MDV"
 def:DefineVersion="2.1.0" def:StandardName="SDTM-IG"
 def:StandardVersion="3.4">
 <ItemGroupDef OID="IG.DM" Name="DM" Repeating="No"
 IsReferenceData="No" Domain="DM">
 <ItemRef ItemOID="IT.DM.SEX" Mandatory="Yes"
 MethodOID="MT.DM.USUBJID"/>
 </ItemGroupDef>
 <ItemDef OID="IT.DM.SEX" Name="SEX" DataType="text" Length="1">
 <Description><TranslatedText xml:lang="en">Sex</TranslatedText></Description>
 </ItemDef>
 <MethodDef OID="MT.DM.USUBJID" Name="USUBJID" Type="Computation">
 <Description><TranslatedText xml:lang="en">Assigned consistently.</TranslatedText></Description>
 </MethodDef>
 </MetaDataVersion></Study></ODM>"""
    bad_xml = valid_xml.replace("MethodDef", "def:ComputationalMethod")

    evaluator = DeterministicEvaluator()
    valid = evaluator.evaluate(
        task, json.dumps({"answer": {"xml": valid_xml}}), _manifest()
    )
    invalid = evaluator.evaluate(
        task, json.dumps({"answer": {"xml": bad_xml}}), _manifest()
    )

    assert valid["score"] == 1.0
    assert invalid["score"] == 0.0


def test_json_and_yaml_schema_validators():
    task = _task(
        [
            {
                "id": "json-schema",
                "type": "object_schema",
                "path": "answer.manifest",
                "required": {
                    "task_id": "string",
                    "affected_nodes": "array",
                    "reproducible": "boolean",
                },
                "weight": 1,
            },
            {
                "id": "yaml",
                "type": "yaml_exact",
                "path": "answer.yaml",
                "expected_paths": {
                    "change.source": "adam-adsl-builder",
                    "change.version": "3.1",
                },
                "weight": 1,
            },
        ]
    )
    response = json.dumps(
        {
            "answer": {
                "manifest": {
                    "task_id": "heldout-01",
                    "affected_nodes": ["adam-adsl", "tfl-table-generation"],
                    "reproducible": True,
                },
                "yaml": (
                    "change:\n"
                    "  source: adam-adsl-builder\n"
                    '  version: "3.1"\n'
                ),
            }
        }
    )

    result = DeterministicEvaluator().evaluate(task, response, _manifest())

    assert result["score"] == 1.0


def test_restricted_python_validator_executes_safe_function_and_rejects_import():
    task = _task(
        [
            {
                "id": "study-day",
                "type": "restricted_python",
                "path": "answer.code",
                "function": "study_day",
                "cases": [
                    {"args": ["2026-01-10", "2026-01-10"], "expected": 1},
                    {"args": ["2026-01-09", "2026-01-10"], "expected": -1},
                    {"args": ["2026-01-12", "2026-01-10"], "expected": 3},
                ],
                "weight": 1,
            }
        ]
    )
    safe = """
def study_day(event_date, reference_date):
    from_date = lambda value: tuple(int(x) for x in value.split("-"))
    def ordinal(parts):
        y, m, d = parts
        return y * 372 + m * 31 + d
    difference = ordinal(from_date(event_date)) - ordinal(from_date(reference_date))
    return difference + 1 if difference >= 0 else difference
"""
    unsafe = "import os\ndef study_day(a, b):\n    return os.system('echo unsafe')\n"

    evaluator = DeterministicEvaluator()
    assert evaluator.evaluate(
        task, json.dumps({"answer": {"code": safe}}), _manifest()
    )["score"] == 1.0
    failed = evaluator.evaluate(
        task, json.dumps({"answer": {"code": unsafe}}), _manifest()
    )
    assert failed["score"] == 0.0
    assert "Import" in failed["criteria"][0]["detail"]


def test_parse_failure_and_validator_exception_score_zero_fail_closed():
    task = _task(
        [
            {
                "id": "missing",
                "type": "json_exact",
                "path": "answer.value",
                "expected": "x",
                "weight": 1,
            }
        ]
    )

    result = DeterministicEvaluator().evaluate(task, "not json", _manifest())

    assert result["score"] == 0.0
    assert result["parse_status"] == "failed"
    assert result["parse_attempts"]
    assert result["criteria"][0]["passed"] is False


def test_holdout_leakage_guard_rejects_ids_prompt_overlap_and_answer_leakage(
    tmp_path: Path,
):
    development = [
        {
            "task_id": "dev-01",
            "prompt": "Derive SAFFL for randomized never dosed subjects.",
        }
    ]
    heldout = [
        {
            "task_id": "dev-01",
            "prompt": "Derive SAFFL for randomized never dosed subjects.",
            "criteria": [{"expected": "SAFFL=N"}],
        }
    ]

    with pytest.raises(HoldoutLeakageError):
        validate_holdout_isolation(development, heldout)

    clean = [
        {
            "task_id": "heldout-unique",
            "prompt": "Resolve a Define-XML MethodOID cross-reference.",
            "criteria": [{"expected": "MethodDef"}],
        }
    ]
    report = validate_holdout_isolation(development, clean)
    assert report["passed"] is True
    assert report["heldout_count"] == 1

