"""Independent deterministic metrics for the V7 oracle decomposition."""

from __future__ import annotations

import ast
import hashlib
import json
import re
from collections import defaultdict, deque
from itertools import combinations
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import yaml  # type: ignore[import-untyped]


CANONICAL_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_]+|[^\w\s]", re.UNICODE)
WORD_PATTERN = re.compile(r"[a-z0-9]+")
HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
INTEGRATION_SKILL_PATTERN = re.compile(r"/([a-z0-9][a-z0-9-]*)", re.I)
EXCLUDED_HEADING_TERMS = (
    "runtime configuration",
    "execute now",
    "arguments",
    "script execution",
    "script",
    "basic usage",
    "examples",
    "example usage",
)
REQUIRED_PROVENANCE_FIELDS = (
    "chunk_id",
    "source_path",
    "source_sha256",
    "content_sha256",
    "injected_fragment_sha256",
)
SCHEMA_CRITERION_TYPES = {"object_schema", "define_xml", "yaml_exact"}
DERIVATION_CRITERION_TYPES = {"regex", "restricted_python"}
ERROR_CLASSES = (
    "retrieval_miss",
    "wrong_or_stale_evidence",
    "evidence_present_generator_omission",
    "derivation_error",
    "schema_or_serialization_error",
    "forbidden_hallucination",
    "citation_mismatch",
    "judge_only_disagreement",
    "unresolved_insufficient_artifact_evidence",
)


def sha256_file(path: Path) -> str:
    """Return a streaming SHA256 for a file."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def canonical_json_bytes(value: Any) -> bytes:
    """Serialize JSON deterministically with a final newline."""
    return (
        json.dumps(
            value,
            sort_keys=True,
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def canonical_token_count(text: str) -> int:
    return sum(1 for _ in CANONICAL_TOKEN_PATTERN.finditer(text))


def _truncate_to_canonical_tokens(text: str, target: int) -> str:
    if target <= 0:
        return ""
    matches = list(CANONICAL_TOKEN_PATTERN.finditer(text))
    if len(matches) <= target:
        return text
    return text[: matches[target - 1].end()]


def _frontmatter(content: str) -> tuple[dict[str, Any], str]:
    if not content.startswith("---"):
        return {}, content
    parts = content.split("---", 2)
    if len(parts) != 3:
        return {}, content
    try:
        metadata = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        metadata = {}
    return (
        dict(metadata) if isinstance(metadata, Mapping) else {},
        parts[2].lstrip(),
    )


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "overview"


def _excluded_heading(heading: str) -> bool:
    lowered = heading.lower().strip()
    return any(
        lowered == term or lowered.startswith(f"{term} ")
        for term in EXCLUDED_HEADING_TERMS
    )


def _split_text(text: str, max_tokens: int) -> list[str]:
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        proposed = f"{current}\n\n{paragraph}".strip() if current else paragraph
        if canonical_token_count(proposed) <= max_tokens:
            current = proposed
            continue
        if current:
            chunks.append(current)
            current = ""
        remaining = paragraph
        while canonical_token_count(remaining) > max_tokens:
            piece = _truncate_to_canonical_tokens(remaining, max_tokens)
            chunks.append(piece)
            remaining = remaining[len(piece) :].lstrip()
        current = remaining
    if current:
        chunks.append(current)
    return chunks


def parse_skill_document(
    *,
    skill_name: str,
    source_path: str,
    content: str,
    max_chunk_tokens: int = 360,
) -> list[dict[str, Any]]:
    """Reconstruct V7 chunks without importing the frozen router."""
    metadata, body = _frontmatter(content)
    declared = metadata.get("version")
    integration_match = re.search(
        r"(?ims)^#{1,6}\s+Integration\b(.*?)(?=^#{1,6}\s+|\Z)",
        body,
    )
    dependencies = (
        sorted(
            {
                value.lower()
                for value in INTEGRATION_SKILL_PATTERN.findall(
                    integration_match.group(1)
                )
            }
        )
        if integration_match
        else []
    )
    sections: list[tuple[str, str]] = []
    heading_stack: list[tuple[int, str]] = []
    current_heading = "Overview"
    current_lines: list[str] = []

    def flush() -> None:
        text = "\n".join(current_lines).strip()
        if text and not _excluded_heading(current_heading):
            sections.append((current_heading, text))

    for line in body.splitlines():
        match = HEADING_PATTERN.match(line)
        if not match:
            current_lines.append(line)
            continue
        flush()
        current_lines = []
        level = len(match.group(1))
        heading = match.group(2).strip()
        while heading_stack and heading_stack[-1][0] >= level:
            heading_stack.pop()
        heading_stack.append((level, heading))
        current_heading = " > ".join(value for _, value in heading_stack)
    flush()

    chunks: list[dict[str, Any]] = []
    document_order = 0
    for heading_path, section_text in sections:
        for part_index, part in enumerate(_split_text(section_text, max_chunk_tokens)):
            content_sha = sha256_text(part)
            chunks.append(
                {
                    "chunk_id": (
                        f"{skill_name}::{_slug(heading_path)}::{part_index}::"
                        f"{content_sha[:8]}"
                    ),
                    "skill_name": skill_name,
                    "source_path": source_path,
                    "source_sha256": sha256_text(content),
                    "declared_version": (
                        str(declared) if declared is not None else None
                    ),
                    "heading_path": heading_path,
                    "content": part,
                    "content_sha256": content_sha,
                    "canonical_tokens": canonical_token_count(part),
                    "dependency_skills": dependencies,
                    "document_order": document_order,
                }
            )
            document_order += 1
    return chunks


def build_chunk_corpus(root: Path) -> dict[str, dict[str, Any]]:
    """Build the frozen skill corpus and fail on duplicate chunk IDs."""
    corpus: dict[str, dict[str, Any]] = {}
    skill_root = root / "csp-skills"
    for path in sorted(skill_root.rglob("SKILL.md")):
        source_path = path.relative_to(root).as_posix()
        chunks = parse_skill_document(
            skill_name=path.parent.name,
            source_path=source_path,
            content=path.read_text(encoding="utf-8"),
        )
        for chunk in chunks:
            chunk_id = str(chunk["chunk_id"])
            if chunk_id in corpus:
                raise ValueError(f"Duplicate reconstructed chunk ID: {chunk_id}")
            corpus[chunk_id] = chunk
    return corpus


def reconstruct_fragment(
    row: Mapping[str, Any],
    corpus: Mapping[str, Mapping[str, Any]],
) -> str | None:
    """Recover the exact injected fragment by its recorded SHA256."""
    chunk = corpus.get(str(row.get("chunk_id")))
    if not chunk:
        return None
    content = str(chunk["content"])
    expected = str(row.get("injected_fragment_sha256", ""))
    if sha256_text(content) == expected:
        return content
    for match in CANONICAL_TOKEN_PATTERN.finditer(content):
        candidate = content[: match.end()]
        if sha256_text(candidate) == expected:
            return candidate
    if expected == sha256_text(""):
        return ""
    return None


def extract_task_requirements(task: Mapping[str, Any]) -> dict[str, Any]:
    """Map task and atomic criteria to registry-declared evidence sections."""
    requirements: list[dict[str, str]] = []
    for criterion in task.get("criteria", []):
        if criterion.get("type") != "provenance_citation":
            continue
        for requirement in criterion.get("required", []):
            normalized = {
                "skill_name": str(requirement["skill_name"]),
                **(
                    {"heading_contains": str(requirement["heading_contains"])}
                    if requirement.get("heading_contains")
                    else {}
                ),
            }
            if normalized not in requirements:
                requirements.append(normalized)
    criterion_map = {
        str(criterion["id"]): [dict(item) for item in requirements]
        for criterion in task.get("criteria", [])
    }
    return {
        "task_requirements": requirements,
        "criteria": criterion_map,
        "mapping_basis": "registry_provenance_requirement_union",
    }


def requirement_matches_chunk(
    requirement: Mapping[str, Any],
    chunk: Mapping[str, Any],
) -> bool:
    if (
        str(chunk.get("skill_name", "")).casefold()
        != str(requirement.get("skill_name", "")).casefold()
    ):
        return False
    heading = requirement.get("heading_contains")
    return (
        not heading
        or str(heading).casefold() in str(chunk.get("heading_path", "")).casefold()
    )


def parse_response_json(response: str) -> tuple[Any | None, str]:
    """Parse stored responses using deterministic, non-repairing strategies."""
    try:
        return json.loads(response), "full_response_json"
    except (json.JSONDecodeError, TypeError):
        pass
    fenced = re.search(r"```(?:json)?\s*(.*?)```", response, re.I | re.S)
    if fenced:
        try:
            return json.loads(fenced.group(1)), "fenced_json"
        except json.JSONDecodeError:
            pass
    start, end = response.find("{"), response.rfind("}")
    if 0 <= start < end:
        try:
            return json.loads(response[start : end + 1]), "object_substring_json"
        except json.JSONDecodeError:
            pass
    return None, "unparseable"


def response_evidence_ids(parsed: Any) -> list[str]:
    if not isinstance(parsed, Mapping):
        return []
    value = parsed.get("evidence_ids")
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, str)]


def _jaccard_text(left: str, right: str) -> float:
    first = set(WORD_PATTERN.findall(left.lower()))
    second = set(WORD_PATTERN.findall(right.lower()))
    if not first and not second:
        return 1.0
    return len(first & second) / max(1, len(first | second))


def lexical_overlap(prompt: str, evidence_text: str) -> dict[str, float]:
    query = set(WORD_PATTERN.findall(prompt.lower()))
    evidence = set(WORD_PATTERN.findall(evidence_text.lower()))
    intersection = query & evidence
    return {
        "jaccard": len(intersection) / max(1, len(query | evidence)),
        "query_term_coverage": len(intersection) / max(1, len(query)),
    }


def build_graph_index(
    graph_data: Mapping[str, Any],
    corpus: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Index graph nodes, typed undirected adjacency, and skill integrations."""
    nodes = {
        str(node["id"]): dict(node)
        for node in graph_data.get("nodes", [])
        if isinstance(node, Mapping) and node.get("id")
    }
    neighbors: dict[str, list[tuple[str, str]]] = defaultdict(list)
    bound_skills: dict[str, set[str]] = defaultdict(set)
    for node_id, node in nodes.items():
        for skill in node.get("skills_bound", []):
            bound_skills[node_id].add(str(skill).lstrip("/"))
        for dependency in node.get("dependencies", []):
            if isinstance(dependency, Mapping):
                predecessor = str(dependency.get("node", ""))
                edge_type = str(dependency.get("edge_type", "untyped"))
            else:
                predecessor = str(dependency)
                edge_type = "untyped"
            if predecessor in nodes:
                neighbors[node_id].append((predecessor, edge_type))
                neighbors[predecessor].append((node_id, edge_type))
    skill_dependencies: dict[str, set[str]] = defaultdict(set)
    for chunk in corpus.values():
        skill = str(chunk["skill_name"])
        skill_dependencies[skill].update(
            str(item) for item in chunk.get("dependency_skills", [])
        )
    return {
        "nodes": nodes,
        "neighbors": {key: sorted(value) for key, value in sorted(neighbors.items())},
        "bound_skills": {
            key: sorted(value) for key, value in sorted(bound_skills.items())
        },
        "skill_dependencies": {
            key: sorted(value) for key, value in sorted(skill_dependencies.items())
        },
    }


def dependency_routes(
    graph_index: Mapping[str, Any],
    node_id: str,
    *,
    max_hops: int = 2,
) -> tuple[dict[str, int], dict[str, str]]:
    """Return router-equivalent skill distances and typed route labels."""
    bound = graph_index["bound_skills"]
    neighbors = graph_index["neighbors"]
    distances: dict[str, int] = {skill: 0 for skill in bound.get(node_id, [])}
    labels: dict[str, str] = {skill: "current_node" for skill in distances}
    queue: deque[tuple[str, int, tuple[str, ...]]] = deque([(node_id, 0, ())])
    seen_node_distance = {node_id: 0}
    while queue:
        current, distance, edge_path = queue.popleft()
        if distance >= max_hops:
            continue
        for neighbor, edge_type in neighbors.get(current, []):
            new_distance = distance + 1
            new_path = (*edge_path, edge_type)
            route_label = "+".join(new_path)
            for skill in bound.get(neighbor, []):
                prior = distances.get(skill, max_hops + 1)
                if new_distance < prior or (
                    new_distance == prior and route_label < labels.get(skill, "\uffff")
                ):
                    distances[skill] = new_distance
                    labels[skill] = route_label
            if new_distance < seen_node_distance.get(neighbor, max_hops + 1):
                seen_node_distance[neighbor] = new_distance
                queue.append((neighbor, new_distance, new_path))

    skill_dependencies = graph_index["skill_dependencies"]
    skill_queue: deque[tuple[str, int]] = deque(
        sorted(distances.items(), key=lambda item: (item[1], item[0]))
    )
    while skill_queue:
        skill, distance = skill_queue.popleft()
        if distance >= max_hops:
            continue
        related = set(skill_dependencies.get(skill, []))
        related.update(
            owner
            for owner, dependencies in skill_dependencies.items()
            if skill in dependencies
        )
        for neighbor in sorted(related):
            new_distance = distance + 1
            if new_distance < distances.get(neighbor, max_hops + 1):
                distances[neighbor] = new_distance
                labels[neighbor] = "integration"
                skill_queue.append((neighbor, new_distance))
    return distances, labels


def compute_cell_metrics(
    *,
    requirements: Sequence[Mapping[str, Any]],
    manifest: Mapping[str, Any],
    chunk_content: Mapping[str, str],
    dependency_reachable_skills: Mapping[str, int],
    response_evidence_ids: Sequence[str],
) -> dict[str, Any]:
    """Compute retrieval and evidence-control metrics for one stored cell."""
    selected = list(manifest.get("selected_chunks", []))
    hits = [
        any(requirement_matches_chunk(requirement, row) for row in selected)
        for requirement in requirements
    ]
    relevant_rows = [
        row
        for row in selected
        if any(
            requirement_matches_chunk(requirement, row) for requirement in requirements
        )
    ]
    selected_tokens = sum(
        int(row.get("injected_canonical_tokens_with_header", 0)) for row in selected
    )
    total_tokens = int(
        manifest.get(
            "actual_canonical_tokens",
            selected_tokens + int(manifest.get("budget_padding_canonical_tokens", 0)),
        )
    )
    relevant_tokens = sum(
        int(row.get("injected_canonical_tokens_with_header", 0))
        for row in relevant_rows
    )
    topology_hits = [
        str(requirement.get("skill_name")) in dependency_reachable_skills
        for requirement in requirements
    ]
    dependency_hits = [
        topology_hit and retrieval_hit
        for topology_hit, retrieval_hit in zip(topology_hits, hits)
    ]
    content_pairs = [
        _jaccard_text(
            chunk_content.get(str(left.get("chunk_id")), ""),
            chunk_content.get(str(right.get("chunk_id")), ""),
        )
        for left, right in combinations(selected, 2)
    ]
    cited = set(response_evidence_ids)
    selected_ids = {str(row.get("chunk_id")) for row in selected}
    correct_citation_hits = [
        any(
            str(row.get("chunk_id")) in cited
            and requirement_matches_chunk(requirement, row)
            for row in selected
        )
        for requirement in requirements
    ]
    complete_rows = [
        all(row.get(field) for field in REQUIRED_PROVENANCE_FIELDS) for row in selected
    ]
    conflict_ids = {
        str(item.get("chunk_id"))
        for item in manifest.get("version_conflicts", [])
        if isinstance(item, Mapping)
    }
    selected_stale_ids = sorted(selected_ids & conflict_ids)
    conflict_resolution_correct = all(
        item.get("resolution") == "excluded_stale_version"
        for item in manifest.get("version_conflicts", [])
        if isinstance(item, Mapping)
    )
    requirement_count = len(requirements)
    return {
        "required_section_count": requirement_count,
        "retrieved_required_section_count": sum(hits),
        "required_section_recall": (
            sum(hits) / requirement_count if requirement_count else 1.0
        ),
        "required_section_precision": (
            len(relevant_rows) / len(selected) if selected else 0.0
        ),
        "required_token_precision": (
            relevant_tokens / total_tokens if total_tokens else 0.0
        ),
        "dependency_coverage": (
            sum(dependency_hits) / requirement_count if requirement_count else 1.0
        ),
        "topology_alignment": (
            sum(topology_hits) / requirement_count if requirement_count else 1.0
        ),
        "irrelevant_token_ratio": (
            1.0 - relevant_tokens / total_tokens if total_tokens else 1.0
        ),
        "redundancy": (
            sum(content_pairs) / len(content_pairs) if content_pairs else 0.0
        ),
        "version_conflict_count": len(list(manifest.get("version_conflicts", []))),
        "stale_selected_count": len(selected_stale_ids),
        "stale_selected_chunk_ids": selected_stale_ids,
        "version_selection_correctness": float(
            not selected_stale_ids and conflict_resolution_correct
        ),
        "provenance_completeness": (
            sum(complete_rows) / len(complete_rows) if complete_rows else 1.0
        ),
        "citation_manifest_alignment": (
            len(cited & selected_ids) / len(cited) if cited else 0.0
        ),
        "correct_citation_rate": (
            sum(correct_citation_hits) / requirement_count if requirement_count else 1.0
        ),
        "selected_chunk_count": len(selected),
        "selected_context_tokens": total_tokens,
        "required_context_tokens": relevant_tokens,
        "budget_padding_tokens": int(
            manifest.get("budget_padding_canonical_tokens", 0)
        ),
    }


def compare_graph_to_bm25(
    *,
    requirements: Sequence[Mapping[str, Any]],
    graph_chunks: Sequence[Mapping[str, Any]],
    bm25_chunks: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Compute oracle evidence set deltas without consulting arm scores."""
    graph_ids = {str(row.get("chunk_id")) for row in graph_chunks}
    bm25_ids = {str(row.get("chunk_id")) for row in bm25_chunks}
    added = [row for row in graph_chunks if str(row.get("chunk_id")) not in bm25_ids]
    removed = [row for row in bm25_chunks if str(row.get("chunk_id")) not in graph_ids]
    graph_hits = [
        any(requirement_matches_chunk(req, row) for row in graph_chunks)
        for req in requirements
    ]
    bm25_hits = [
        any(requirement_matches_chunk(req, row) for row in bm25_chunks)
        for req in requirements
    ]
    unique_gains = [
        graph_hit and not bm25_hit for graph_hit, bm25_hit in zip(graph_hits, bm25_hits)
    ]
    losses = [
        bm25_hit and not graph_hit for graph_hit, bm25_hit in zip(graph_hits, bm25_hits)
    ]
    added_required = [
        row
        for row in added
        if any(requirement_matches_chunk(req, row) for req in requirements)
    ]
    denominator = len(requirements)
    return {
        "graph_added_chunk_count": len(added),
        "graph_removed_bm25_chunk_count": len(removed),
        "graph_added_required_chunk_count": len(added_required),
        "graph_added_required_fraction": (
            len(added_required) / len(added) if added else 0.0
        ),
        "graph_unique_requirement_count": sum(unique_gains),
        "graph_unique_requirement_gain": (
            sum(unique_gains) / denominator if denominator else 0.0
        ),
        "graph_requirement_loss_count": sum(losses),
        "graph_requirement_loss": (sum(losses) / denominator if denominator else 0.0),
        "graph_added_necessary": any(unique_gains),
        "graph_added_chunk_ids": sorted(str(row.get("chunk_id")) for row in added),
        "graph_added_required_chunk_ids": sorted(
            str(row.get("chunk_id")) for row in added_required
        ),
    }


def _detail_values(detail: str) -> tuple[Any, Any]:
    match = re.search(r"observed=(.*?); expected=(.*)$", detail)
    if not match:
        return object(), object()
    try:
        observed = ast.literal_eval(match.group(1))
    except (ValueError, SyntaxError):
        observed = match.group(1)
    try:
        expected = ast.literal_eval(match.group(2))
    except (ValueError, SyntaxError):
        expected = match.group(2)
    return observed, expected


def _looks_like_omission(criterion: Mapping[str, Any]) -> bool:
    detail = str(criterion.get("detail", ""))
    observed, expected = _detail_values(detail)
    if observed is None or observed == "" or observed == [] or observed == {}:
        return expected not in (None, "", [], {})
    if isinstance(observed, (list, set, tuple)) and isinstance(
        expected, (list, set, tuple)
    ):
        return set(observed) < set(expected)
    return "missing" in detail.lower() and "required" not in detail.lower()


def classify_criterion_failure(
    *,
    parse_status: str,
    criterion: Mapping[str, Any],
    context: Mapping[str, Any],
) -> str:
    """Assign one primary error class with retrieval/output precedence."""
    if parse_status != "success":
        return "schema_or_serialization_error"
    criterion_type = str(criterion.get("type", ""))
    if criterion_type == "forbidden_terms":
        return "forbidden_hallucination"
    if not context.get("required_evidence_present", False):
        return "retrieval_miss"
    if context.get("stale_or_conflicting_chunk_selected", False):
        return "wrong_or_stale_evidence"
    if criterion_type == "provenance_citation":
        return "citation_mismatch"
    if criterion_type in SCHEMA_CRITERION_TYPES:
        return "schema_or_serialization_error"
    if criterion_type in DERIVATION_CRITERION_TYPES:
        return "derivation_error"
    if _looks_like_omission(criterion):
        return "evidence_present_generator_omission"
    detail = str(criterion.get("detail", ""))
    if "expected=None" in detail and "observed=None" not in detail:
        return "forbidden_hallucination"
    if criterion_type in {
        "json_exact",
        "json_contains_all",
        "json_set_equals",
    }:
        return "derivation_error"
    return "unresolved_insufficient_artifact_evidence"


def build_error_decomposition(
    *,
    deterministic_evaluation: Mapping[str, Any],
    criterion_requirements: Mapping[str, Sequence[Mapping[str, Any]]],
    context_by_criterion: Mapping[str, Mapping[str, Any]],
    judge: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    """Create criterion failures plus conservative judge-only discordance."""
    parse_status = str(deterministic_evaluation.get("parse_status", "unavailable"))
    rows: list[dict[str, Any]] = []
    for criterion in deterministic_evaluation.get("criteria", []):
        if criterion.get("passed"):
            continue
        criterion_id = str(criterion.get("id"))
        context = dict(context_by_criterion.get(criterion_id, {}))
        rows.append(
            {
                "criterion_id": criterion_id,
                "criterion_type": str(criterion.get("type", "")),
                "criterion_weight": float(criterion.get("weight", 0.0)),
                "error_class": classify_criterion_failure(
                    parse_status=parse_status,
                    criterion=criterion,
                    context=context,
                ),
                "required_evidence_present": bool(
                    context.get("required_evidence_present", False)
                ),
                "required_evidence_count": len(
                    criterion_requirements.get(criterion_id, [])
                ),
                "detail": str(criterion.get("detail", "")),
            }
        )
    score = float(deterministic_evaluation.get("score", 0.0))
    if judge:
        judge_mean = float(judge.get("secondary_mean", 0.0))
        discordant = (score == 1.0 and judge_mean < 3.0) or (
            score == 0.0 and judge_mean >= 4.0
        )
        if discordant:
            rows.append(
                {
                    "criterion_id": "__secondary_judge__",
                    "criterion_type": "secondary_judge_discordance",
                    "criterion_weight": 0.0,
                    "error_class": "judge_only_disagreement",
                    "required_evidence_present": True,
                    "required_evidence_count": 0,
                    "detail": (
                        f"deterministic_score={score}; "
                        f"secondary_judge_mean={judge_mean}"
                    ),
                }
            )
    return rows


def confusion_counts(
    rows: Iterable[Mapping[str, Any]],
    *,
    present_key: str = "required_evidence_present",
    passed_key: str = "criterion_passed",
) -> dict[str, int]:
    counts = {
        "evidence_present__criterion_pass": 0,
        "evidence_present__criterion_fail": 0,
        "evidence_absent__criterion_pass": 0,
        "evidence_absent__criterion_fail": 0,
    }
    for row in rows:
        present = bool(row.get(present_key))
        passed = bool(row.get(passed_key))
        key = (
            f"evidence_{'present' if present else 'absent'}__"
            f"criterion_{'pass' if passed else 'fail'}"
        )
        counts[key] += 1
    return counts


def mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def quantile(values: Sequence[float], probability: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction
