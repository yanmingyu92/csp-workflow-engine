"""Deterministic chunk retrieval and provenance for the V7 experiment.

The V7 router indexes complete evidence-bearing Markdown sections rather than
skill metadata alone. Its canonical budget unit is the count produced by
``CANONICAL_TOKEN_PATTERN``. This declared tokenizer is provider-independent and
is therefore suitable for exact arm matching. Provider token usage and any
available model-tokenizer count are recorded separately by the runner.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
import re
from collections import Counter, defaultdict, deque
from dataclasses import asdict, dataclass, field
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Iterable, Mapping, Sequence

import yaml


CANONICAL_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_]+|[^\w\s]", re.UNICODE)
WORD_PATTERN = re.compile(r"[a-z0-9]+")
HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
INTEGRATION_SKILL_PATTERN = re.compile(r"/([a-z0-9][a-z0-9-]*)", re.I)
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
VERSION_PATTERNS = {
    "SDTM IG": re.compile(r"\bSDTM(?:-?IG|\s+IG)\s+v?(\d+\.\d+)\b", re.I),
    "ADaM IG": re.compile(r"\bADaM(?:-?IG|\s+IG)\s+v?(\d+\.\d+)\b", re.I),
    "Define-XML": re.compile(
        r"\bDefine-?XML\s+v?(\d+\.\d+(?:\.\d+)?)\b", re.I
    ),
}
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
PRIORITY_SECTION_KINDS = {
    "derivation": 2.4,
    "constraints": 2.2,
    "edge_cases": 2.3,
    "validation": 2.0,
    "output_schema": 1.8,
    "integration": 1.1,
    "overview": 0.2,
    "other": 0.6,
}
V7_ARMS = (
    "graph_bm25_chunk_optimized",
    "full_corpus_bm25_token_matched",
    "random_token_matched",
    "flat_8000",
)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_tokens(text: str) -> tuple[str, ...]:
    """Return the exact tokens used for V7 cross-arm context matching."""
    return tuple(match.group(0) for match in CANONICAL_TOKEN_PATTERN.finditer(text))


def canonical_token_count(text: str) -> int:
    return len(canonical_tokens(text))


def _truncate_to_canonical_tokens(text: str, target: int) -> str:
    if target <= 0:
        return ""
    matches = list(CANONICAL_TOKEN_PATTERN.finditer(text))
    if len(matches) <= target:
        return text
    return text[: matches[target - 1].end()]


def _canonical_json_hash(value: Any) -> str:
    return sha256_text(
        json.dumps(
            value,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )
    )


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
    return dict(metadata) if isinstance(metadata, Mapping) else {}, parts[2].lstrip()


def _slug(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return normalized or "overview"


def _section_kind(heading: str) -> str:
    lowered = heading.lower()
    if "derivation" in lowered or "formula" in lowered:
        return "derivation"
    if "constraint" in lowered or "never" in lowered or "always" in lowered:
        return "constraints"
    if "edge case" in lowered or "partial" in lowered or "conflict" in lowered:
        return "edge_cases"
    if "validation" in lowered or "check" in lowered or "quality" in lowered:
        return "validation"
    if "output schema" in lowered or "structure" in lowered:
        return "output_schema"
    if "integration" in lowered or "upstream" in lowered or "downstream" in lowered:
        return "integration"
    if heading == "Overview":
        return "overview"
    return "other"


def _excluded_heading(heading: str) -> bool:
    lowered = heading.lower().strip()
    return any(
        lowered == term or lowered.startswith(f"{term} ")
        for term in EXCLUDED_HEADING_TERMS
    )


def _split_text(text: str, max_tokens: int) -> list[str]:
    """Split a section without dropping content, preferring paragraph boundaries."""
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    if not paragraphs:
        return []
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


@dataclass(frozen=True)
class SkillChunk:
    chunk_id: str
    skill_name: str
    source_path: str
    source_sha256: str
    declared_version: str | None
    heading_path: str
    section_kind: str
    content: str
    content_sha256: str
    canonical_tokens: int
    dependency_skills: tuple[str, ...] = ()
    document_order: int = 0


@dataclass(frozen=True)
class TaskRoutingRequest:
    task_id: str
    node_id: str
    query: str
    version_pins: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class RoutingConfig:
    seed: int = 20260725
    context_budget: int = 4000
    flat_budget: int = 8000
    max_chunk_tokens: int = 360
    top_k: int = 14
    score_gap_ratio: float = 1.0
    current_service_floor_tokens: int = 320
    bm25_k1: float = 1.2
    bm25_b: float = 0.75
    mmr_lambda: float = 0.78
    graph_current_boost: float = 1.25
    dependency_boost: float = 3.0
    two_hop_penalty: float = 0.5
    pinned_versions: Mapping[str, str] = field(
        default_factory=lambda: {
            "SDTM IG": "3.4",
            "ADaM IG": "1.3",
            "Define-XML": "2.1.0",
        }
    )

    def __post_init__(self) -> None:
        if self.context_budget <= 0 or self.flat_budget <= 0:
            raise ValueError("Context budgets must be positive")
        if self.max_chunk_tokens <= 0 or self.top_k <= 0:
            raise ValueError("Chunk and top-k values must be positive")
        if not 0.0 <= self.score_gap_ratio <= 1.0:
            raise ValueError("score_gap_ratio must be within [0, 1]")
        if not 0.0 < self.mmr_lambda <= 1.0:
            raise ValueError("mmr_lambda must be within (0, 1]")
        if not 0.0 < self.two_hop_penalty < 1.0:
            raise ValueError("two_hop_penalty must be within (0, 1)")


@dataclass(frozen=True)
class ContextBuild:
    context_text: str
    canonical_tokens: int
    manifest: dict[str, Any]


def chunk_skill_document(
    skill_name: str,
    source_path: Path,
    content: str,
    *,
    max_chunk_tokens: int = 360,
) -> list[SkillChunk]:
    """Parse one SKILL.md into stable, evidence-bearing section chunks."""
    metadata, body = _frontmatter(content)
    source_sha = sha256_text(content)
    declared = metadata.get("version")
    declared_version = str(declared) if declared is not None else None
    dependencies: set[str] = set()
    integration_match = re.search(
        r"(?ims)^#{1,6}\s+Integration\b(.*?)(?=^#{1,6}\s+|\Z)",
        body,
    )
    if integration_match:
        dependencies.update(
            value.lower()
            for value in INTEGRATION_SKILL_PATTERN.findall(
                integration_match.group(1)
            )
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

    chunks: list[SkillChunk] = []
    order = 0
    for heading_path, section_text in sections:
        for part_index, part in enumerate(
            _split_text(section_text, max_chunk_tokens)
        ):
            content_sha = sha256_text(part)
            chunk_id = (
                f"{skill_name}::{_slug(heading_path)}::{part_index}::"
                f"{content_sha[:8]}"
            )
            chunks.append(
                SkillChunk(
                    chunk_id=chunk_id,
                    skill_name=skill_name,
                    source_path=source_path.as_posix(),
                    source_sha256=source_sha,
                    declared_version=declared_version,
                    heading_path=heading_path,
                    section_kind=_section_kind(heading_path),
                    content=part,
                    content_sha256=content_sha,
                    canonical_tokens=canonical_token_count(part),
                    dependency_skills=tuple(sorted(dependencies)),
                    document_order=order,
                )
            )
            order += 1
    return chunks


class _Bm25Index:
    def __init__(self, chunks: Sequence[SkillChunk], config: RoutingConfig):
        self.config = config
        self.chunks = {chunk.chunk_id: chunk for chunk in chunks}
        self.tokens = {
            chunk.chunk_id: tuple(
                WORD_PATTERN.findall(
                    (
                        f"{chunk.skill_name} {chunk.heading_path} {chunk.content}"
                    ).lower()
                )
            )
            for chunk in chunks
        }
        self.frequencies = {
            chunk_id: Counter(tokens) for chunk_id, tokens in self.tokens.items()
        }
        self.document_frequency: Counter[str] = Counter()
        for tokens in self.tokens.values():
            self.document_frequency.update(set(tokens))
        self.document_count = len(chunks)
        self.average_length = (
            sum(len(tokens) for tokens in self.tokens.values()) / len(chunks)
            if chunks
            else 1.0
        )

    def score(self, query: str, chunk_id: str) -> float:
        query_terms = sorted(set(WORD_PATTERN.findall(query.lower())))
        frequencies = self.frequencies[chunk_id]
        length_ratio = len(self.tokens[chunk_id]) / self.average_length
        score = 0.0
        for term in query_terms:
            frequency = frequencies.get(term, 0)
            if not frequency:
                continue
            df = self.document_frequency[term]
            idf = math.log(
                1.0 + (self.document_count - df + 0.5) / (df + 0.5)
            )
            denominator = frequency + self.config.bm25_k1 * (
                1.0
                - self.config.bm25_b
                + self.config.bm25_b * length_ratio
            )
            score += (
                idf
                * frequency
                * (self.config.bm25_k1 + 1.0)
                / denominator
            )
        return round(score, 12)


class RoutingCorpus:
    """Immutable V7 chunk corpus with graph and integration dependencies."""

    def __init__(
        self,
        *,
        chunks: Sequence[SkillChunk],
        graph_data: Mapping[str, Any],
        graph_sha256: str,
        config: RoutingConfig,
    ):
        if not chunks:
            raise ValueError("V7 corpus must contain at least one chunk")
        self.chunks = tuple(chunks)
        self.chunk_by_id = {chunk.chunk_id: chunk for chunk in self.chunks}
        self.graph_data = dict(graph_data)
        self.graph_sha256 = graph_sha256
        self.config = config
        self.config_sha256 = _canonical_json_hash(asdict(config))
        self.index = _Bm25Index(self.chunks, config)
        self.nodes = {
            str(node["id"]): dict(node)
            for node in self.graph_data.get("nodes", [])
            if isinstance(node, Mapping) and node.get("id")
        }
        self.skill_chunks: dict[str, list[SkillChunk]] = defaultdict(list)
        for chunk in self.chunks:
            self.skill_chunks[chunk.skill_name].append(chunk)
        self.skill_dependencies: dict[str, set[str]] = defaultdict(set)
        for chunk in self.chunks:
            self.skill_dependencies[chunk.skill_name].update(
                dependency
                for dependency in chunk.dependency_skills
                if dependency in self.skill_chunks
            )
        self.predecessors: dict[str, set[str]] = defaultdict(set)
        self.successors: dict[str, set[str]] = defaultdict(set)
        for node_id, node in self.nodes.items():
            for dependency in node.get("dependencies", []):
                dependency_id = (
                    dependency.get("node")
                    if isinstance(dependency, Mapping)
                    else dependency
                )
                if dependency_id and str(dependency_id) in self.nodes:
                    dependency_id = str(dependency_id)
                    self.predecessors[node_id].add(dependency_id)
                    self.successors[dependency_id].add(node_id)

    @classmethod
    def from_paths(
        cls,
        skill_root: Path,
        graph_path: Path,
        config: RoutingConfig,
    ) -> "RoutingCorpus":
        skill_root = Path(skill_root)
        graph_path = Path(graph_path)
        graph_text = graph_path.read_text(encoding="utf-8")
        graph_data = yaml.safe_load(graph_text) or {}
        chunks: list[SkillChunk] = []
        for skill_path in sorted(skill_root.rglob("SKILL.md")):
            skill_name = skill_path.parent.name.lstrip("/")
            source_path = skill_path
            try:
                source_path = skill_path.resolve().relative_to(
                    skill_root.parent.resolve()
                )
            except ValueError:
                source_path = Path(skill_path.name)
            chunks.extend(
                chunk_skill_document(
                    skill_name,
                    source_path,
                    skill_path.read_text(encoding="utf-8"),
                    max_chunk_tokens=config.max_chunk_tokens,
                )
            )
        return cls(
            chunks=chunks,
            graph_data=graph_data,
            graph_sha256=sha256_text(graph_text),
            config=config,
        )

    def _bound_skills(self, node_id: str) -> set[str]:
        return {
            str(skill).lstrip("/")
            for skill in self.nodes.get(node_id, {}).get("skills_bound", [])
        }

    def dependency_distances(
        self, node_id: str, *, max_hops: int = 2
    ) -> dict[str, int]:
        """Return minimum graph/integration distance from the active node."""
        distances: dict[str, int] = {
            skill: 0 for skill in sorted(self._bound_skills(node_id))
        }
        node_queue: deque[tuple[str, int]] = deque([(node_id, 0)])
        seen_nodes = {node_id}
        while node_queue:
            current_node, distance = node_queue.popleft()
            if distance >= max_hops:
                continue
            adjacent = sorted(
                self.predecessors.get(current_node, set())
                | self.successors.get(current_node, set())
            )
            for adjacent_node in adjacent:
                new_distance = distance + 1
                for skill in self._bound_skills(adjacent_node):
                    distances[skill] = min(
                        distances.get(skill, max_hops + 1), new_distance
                    )
                if adjacent_node not in seen_nodes:
                    seen_nodes.add(adjacent_node)
                    node_queue.append((adjacent_node, new_distance))

        skill_queue: deque[tuple[str, int]] = deque(
            sorted(distances.items(), key=lambda item: (item[1], item[0]))
        )
        while skill_queue:
            skill, distance = skill_queue.popleft()
            if distance >= max_hops:
                continue
            related = set(self.skill_dependencies.get(skill, set()))
            related.update(
                owner
                for owner, dependencies in self.skill_dependencies.items()
                if skill in dependencies
            )
            for neighbor in sorted(related):
                new_distance = distance + 1
                if new_distance < distances.get(neighbor, max_hops + 1):
                    distances[neighbor] = new_distance
                    skill_queue.append((neighbor, new_distance))
        return distances

    def dependency_multiplier(self, hops: int) -> float:
        if hops <= 0:
            return 1.0
        if hops == 1:
            return 1.0
        if hops == 2:
            return self.config.two_hop_penalty
        return 0.0

    @staticmethod
    def _jaccard(first: SkillChunk, second: SkillChunk) -> float:
        left = set(WORD_PATTERN.findall(first.content.lower()))
        right = set(WORD_PATTERN.findall(second.content.lower()))
        if not left and not right:
            return 1.0
        return len(left & right) / max(1, len(left | right))

    def _version_state(
        self,
        chunk: SkillChunk,
        pins: Mapping[str, str],
    ) -> tuple[bool, list[dict[str, str]]]:
        conflicts: list[dict[str, str]] = []
        for standard, pattern in VERSION_PATTERNS.items():
            pinned = pins.get(standard)
            if not pinned:
                continue
            for version in sorted(set(pattern.findall(chunk.content))):
                normalized = version
                if standard == "Define-XML" and normalized.count(".") == 1:
                    normalized = f"{normalized}.0"
                if normalized != pinned:
                    conflicts.append(
                        {
                            "chunk_id": chunk.chunk_id,
                            "standard": standard,
                            "observed_version": version,
                            "pinned_version": pinned,
                            "resolution": "excluded_stale_version",
                        }
                    )
        return bool(conflicts), conflicts

    def _rank(
        self,
        request: TaskRoutingRequest,
        *,
        graph_enabled: bool,
        apply_score_gap: bool = True,
    ) -> tuple[list[SkillChunk], dict[str, dict[str, Any]], list[dict[str, str]]]:
        pins = {**dict(self.config.pinned_versions), **dict(request.version_pins)}
        distances = (
            self.dependency_distances(request.node_id, max_hops=2)
            if graph_enabled
            else {}
        )
        scores: dict[str, dict[str, Any]] = {}
        conflicts: list[dict[str, str]] = []
        eligible: list[SkillChunk] = []
        for chunk in self.chunks:
            stale, chunk_conflicts = self._version_state(chunk, pins)
            conflicts.extend(chunk_conflicts)
            relevance = self.index.score(request.query, chunk.chunk_id)
            section_boost = PRIORITY_SECTION_KINDS[chunk.section_kind]
            hop = distances.get(chunk.skill_name)
            graph_boost = 0.0
            if graph_enabled and hop is not None:
                graph_boost = (
                    self.config.graph_current_boost
                    if hop == 0
                    else self.config.dependency_boost
                    * self.dependency_multiplier(hop)
                )
            final_score = round(relevance + section_boost + graph_boost, 12)
            scores[chunk.chunk_id] = {
                "lexical_relevance_score": relevance,
                "section_priority_score": section_boost,
                "dependency_hops": hop,
                "graph_dependency_score": graph_boost,
                "final_score": final_score,
                "stale_version": stale,
            }
            if not stale:
                eligible.append(chunk)
        eligible.sort(
            key=lambda chunk: (
                -scores[chunk.chunk_id]["final_score"],
                chunk.source_path,
                chunk.document_order,
                chunk.chunk_id,
            )
        )
        if eligible and apply_score_gap:
            best = scores[eligible[0].chunk_id]["final_score"]
            cutoff = best - abs(best) * self.config.score_gap_ratio
            eligible = [
                chunk
                for chunk in eligible
                if scores[chunk.chunk_id]["final_score"] >= cutoff
            ]
        return eligible, scores, sorted(
            conflicts,
            key=lambda row: (
                row["standard"],
                row["observed_version"],
                row["chunk_id"],
            ),
        )

    def _mmr_select(
        self,
        ranked: Sequence[SkillChunk],
        scores: Mapping[str, Mapping[str, Any]],
        *,
        request: TaskRoutingRequest,
        graph_enabled: bool,
    ) -> list[SkillChunk]:
        selected: list[SkillChunk] = []
        remaining = list(ranked)
        if graph_enabled:
            current_skills = self._bound_skills(request.node_id)
            current = [
                chunk for chunk in remaining if chunk.skill_name in current_skills
            ]
            floor_used = 0
            for chunk in current:
                if selected and floor_used >= self.config.current_service_floor_tokens:
                    break
                selected.append(chunk)
                remaining.remove(chunk)
                floor_used += chunk.canonical_tokens
                if len(selected) >= self.config.top_k:
                    return selected

        maximum = max(
            (float(scores[chunk.chunk_id]["final_score"]) for chunk in remaining),
            default=1.0,
        )
        maximum = maximum or 1.0
        while remaining and len(selected) < self.config.top_k:
            def mmr_key(chunk: SkillChunk) -> tuple[float, str]:
                normalized = float(scores[chunk.chunk_id]["final_score"]) / maximum
                redundancy = max(
                    (self._jaccard(chunk, prior) for prior in selected),
                    default=0.0,
                )
                mmr = (
                    self.config.mmr_lambda * normalized
                    - (1.0 - self.config.mmr_lambda) * redundancy
                )
                return (round(mmr, 12), chunk.chunk_id)

            best = max(remaining, key=mmr_key)
            selected.append(best)
            remaining.remove(best)
        return selected

    @staticmethod
    def _header(chunk: SkillChunk) -> str:
        version = chunk.declared_version or "unversioned"
        return (
            f'[EVIDENCE id="{chunk.chunk_id}" source="{chunk.source_path}" '
            f'section="{chunk.heading_path}" version="{version}"]\n'
        )

    @staticmethod
    def _compact_header(chunk: SkillChunk) -> str:
        return f'[EVIDENCE id="{chunk.chunk_id}"]\n'

    def _render_exact(
        self,
        chunks: Sequence[SkillChunk],
        target_tokens: int,
    ) -> tuple[str, list[tuple[SkillChunk, str, int]]]:
        if target_tokens <= 0:
            raise ValueError("target_tokens must be positive")
        rendered = ""
        admitted: list[tuple[SkillChunk, str, int]] = []
        for chunk in chunks:
            separator = "\n\n" if rendered else ""
            header = self._header(chunk)
            full_fragment = header + chunk.content
            full_candidate = rendered + separator + full_fragment
            if canonical_token_count(full_candidate) <= target_tokens:
                rendered = full_candidate
                admitted.append(
                    (chunk, chunk.content, canonical_token_count(separator + full_fragment))
                )
                continue
            selected_header = header
            used = canonical_token_count(
                rendered + separator + selected_header
            )
            content_budget = target_tokens - used
            if content_budget <= 0:
                selected_header = self._compact_header(chunk)
                used = canonical_token_count(
                    rendered + separator + selected_header
                )
                content_budget = target_tokens - used
                if content_budget <= 0:
                    continue
            fragment = _truncate_to_canonical_tokens(chunk.content, content_budget)
            candidate = rendered + separator + selected_header + fragment
            actual = canonical_token_count(candidate)
            if actual > target_tokens:
                fragment = _truncate_to_canonical_tokens(
                    fragment, max(0, content_budget - (actual - target_tokens))
                )
                candidate = (
                    rendered + separator + selected_header + fragment
                )
            rendered = candidate
            admitted.append(
                (
                    chunk,
                    fragment,
                    canonical_token_count(
                        separator + selected_header + fragment
                    ),
                )
            )
            break
        padding_tokens = target_tokens - canonical_token_count(rendered)
        if padding_tokens > 0:
            rendered += " PAD" * padding_tokens
        return rendered, admitted

    def build_context(
        self,
        request: TaskRoutingRequest,
        arm: str,
        run_id: int,
        *,
        target_tokens: int | None = None,
    ) -> ContextBuild:
        if arm not in V7_ARMS:
            raise ValueError(f"Unknown V7 arm: {arm}")
        if arm in {
            "full_corpus_bm25_token_matched",
            "random_token_matched",
        } and target_tokens is None:
            raise ValueError(f"target_tokens is required for {arm}")

        conflicts: list[dict[str, str]] = []
        scores: dict[str, dict[str, Any]] = {}
        budget_fill_ids: set[str] = set()
        if arm == "graph_bm25_chunk_optimized":
            ranked, scores, conflicts = self._rank(request, graph_enabled=True)
            selected = self._mmr_select(
                ranked,
                scores,
                request=request,
                graph_enabled=True,
            )
            requested_budget = self.config.context_budget
        elif arm == "full_corpus_bm25_token_matched":
            ranked, scores, conflicts = self._rank(
                request,
                graph_enabled=False,
                apply_score_gap=False,
            )
            selected = self._mmr_select(
                ranked,
                scores,
                request=request,
                graph_enabled=False,
            )
            requested_budget = int(target_tokens)
            core_ids = {chunk.chunk_id for chunk in selected}
            for chunk in ranked:
                current_tokens = canonical_token_count(
                    "\n\n".join(
                        self._header(item) + item.content
                        for item in selected
                    )
                )
                if current_tokens >= requested_budget:
                    break
                if chunk.chunk_id in core_ids:
                    continue
                selected.append(chunk)
                budget_fill_ids.add(chunk.chunk_id)
        elif arm == "random_token_matched":
            selected = list(self.chunks)
            random.Random(
                f"{self.config.seed}:{request.task_id}:{run_id}:{arm}"
            ).shuffle(selected)
            scores = {
                chunk.chunk_id: {
                    "lexical_relevance_score": self.index.score(
                        request.query, chunk.chunk_id
                    ),
                    "section_priority_score": PRIORITY_SECTION_KINDS[
                        chunk.section_kind
                    ],
                    "dependency_hops": None,
                    "graph_dependency_score": 0.0,
                    "final_score": 0.0,
                    "stale_version": False,
                }
                for chunk in selected
            }
            requested_budget = int(target_tokens)
        else:
            selected = sorted(
                self.chunks,
                key=lambda chunk: (
                    chunk.source_path,
                    chunk.document_order,
                    chunk.chunk_id,
                ),
            )
            scores = {
                chunk.chunk_id: {
                    "lexical_relevance_score": self.index.score(
                        request.query, chunk.chunk_id
                    ),
                    "section_priority_score": PRIORITY_SECTION_KINDS[
                        chunk.section_kind
                    ],
                    "dependency_hops": None,
                    "graph_dependency_score": 0.0,
                    "final_score": 0.0,
                    "stale_version": False,
                }
                for chunk in selected
            }
            requested_budget = self.config.flat_budget

        full_tokens = canonical_token_count(
            "\n\n".join(self._header(chunk) + chunk.content for chunk in selected)
        )
        actual_target = min(requested_budget, full_tokens)
        context_text, admitted = self._render_exact(selected, actual_target)
        actual_tokens = canonical_token_count(context_text)
        evidence_tokens = sum(item[2] for item in admitted)
        budget_padding_tokens = actual_tokens - evidence_tokens
        if arm in {
            "full_corpus_bm25_token_matched",
            "random_token_matched",
        } and actual_tokens != requested_budget:
            raise ValueError(
                f"Exact canonical token matching failed for {arm}: "
                f"{actual_tokens} != {requested_budget}"
            )
        selected_rows = []
        for rank, (chunk, fragment, rendered_tokens) in enumerate(admitted, start=1):
            score = scores[chunk.chunk_id]
            selected_rows.append(
                {
                    "rank": rank,
                    "chunk_id": chunk.chunk_id,
                    "skill_name": chunk.skill_name,
                    "source_path": chunk.source_path,
                    "source_sha256": chunk.source_sha256,
                    "declared_version": chunk.declared_version,
                    "heading_path": chunk.heading_path,
                    "section_kind": chunk.section_kind,
                    "content_sha256": chunk.content_sha256,
                    "injected_fragment_sha256": sha256_text(fragment),
                    "injected_canonical_tokens_with_header": rendered_tokens,
                    "lexical_relevance_score": score[
                        "lexical_relevance_score"
                    ],
                    "section_priority_score": score["section_priority_score"],
                    "dependency_hops": score["dependency_hops"],
                    "graph_dependency_score": score[
                        "graph_dependency_score"
                    ],
                    "final_score": score["final_score"],
                    "selection_reason": (
                        "current_service_floor_or_graph_mmr"
                        if arm == "graph_bm25_chunk_optimized"
                        else "full_corpus_bm25_budget_fill"
                        if chunk.chunk_id in budget_fill_ids
                        else "full_corpus_bm25_mmr"
                        if arm == "full_corpus_bm25_token_matched"
                        else "seeded_random_order"
                        if arm == "random_token_matched"
                        else "stable_flat_corpus_order"
                    ),
                    "truncated": fragment != chunk.content,
                }
            )
        manifest: dict[str, Any] = {
            "schema_version": "v7-context-manifest-1",
            "task_id": request.task_id,
            "node_id": request.node_id,
            "arm": arm,
            "run_id": run_id,
            "seed": self.config.seed,
            "requested_canonical_tokens": requested_budget,
            "actual_canonical_tokens": actual_tokens,
            "context_characters": len(context_text),
            "context_bytes": len(context_text.encode("utf-8")),
            "context_sha256": sha256_text(context_text),
            "budget_padding_canonical_tokens": budget_padding_tokens,
            "budget_padding_policy": (
                "explicit_neutral_pad_after_all_provenance_fragments"
                if budget_padding_tokens
                else "none"
            ),
            "query_sha256": sha256_text(request.query),
            "graph_sha256": self.graph_sha256,
            "routing_config_sha256": self.config_sha256,
            "selected_chunks": selected_rows,
            "version_conflicts": conflicts,
            "candidate_ranking_sha256": _canonical_json_hash(
                [
                    {
                        "chunk_id": chunk.chunk_id,
                        **scores[chunk.chunk_id],
                    }
                    for chunk in selected
                ]
            ),
        }
        manifest["manifest_sha256"] = canonical_manifest_sha256_v7(manifest)
        errors = validate_context_manifest_v7(manifest)
        if errors:
            raise ValueError(f"Invalid V7 context manifest: {errors}")
        return ContextBuild(
            context_text=context_text,
            canonical_tokens=actual_tokens,
            manifest=manifest,
        )

    @staticmethod
    def change_impact_scope(
        manifests: Sequence[Mapping[str, Any]],
        *,
        changed_skill: str,
    ) -> dict[str, Any]:
        task_impact: dict[str, bool] = {}
        for manifest in manifests:
            task_id = str(manifest.get("task_id"))
            selected_skills = {
                row.get("skill_name")
                for row in manifest.get("selected_chunks", [])
            }
            task_impact[task_id] = (
                task_impact.get(task_id, False)
                or changed_skill in selected_skills
            )
        affected = sorted(
            task_id for task_id, is_affected in task_impact.items()
            if is_affected
        )
        unaffected = sorted(
            task_id for task_id, is_affected in task_impact.items()
            if not is_affected
        )
        return {
            "changed_skill": changed_skill,
            "affected_task_ids": affected,
            "unaffected_task_ids": unaffected,
            "affected_count": len(affected),
            "total_count": len(task_impact),
        }


def canonical_manifest_sha256_v7(manifest: Mapping[str, Any]) -> str:
    payload = dict(manifest)
    payload.pop("manifest_sha256", None)
    return _canonical_json_hash(payload)


def _secret_field_errors(value: Any, prefix: str = "manifest") -> list[str]:
    errors: list[str] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized = re.sub(r"[^a-z0-9]+", "_", str(key).lower())
            if (
                normalized in {"api_key", "authorization", "password", "secret"}
                or normalized.endswith(("_api_key", "_access_token", "_private_key"))
            ):
                errors.append(f"secret-like field at {prefix}.{key}")
            errors.extend(_secret_field_errors(item, f"{prefix}.{key}"))
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for index, item in enumerate(value):
            errors.extend(_secret_field_errors(item, f"{prefix}[{index}]"))
    return errors


def validate_context_manifest_v7(manifest: Mapping[str, Any]) -> list[str]:
    errors = _secret_field_errors(manifest)
    required = (
        "schema_version",
        "task_id",
        "node_id",
        "arm",
        "run_id",
        "requested_canonical_tokens",
        "actual_canonical_tokens",
        "context_characters",
        "context_bytes",
        "context_sha256",
        "budget_padding_canonical_tokens",
        "budget_padding_policy",
        "query_sha256",
        "graph_sha256",
        "routing_config_sha256",
        "selected_chunks",
        "version_conflicts",
        "candidate_ranking_sha256",
        "manifest_sha256",
    )
    for field_name in required:
        if field_name not in manifest:
            errors.append(f"missing manifest field: {field_name}")
    if manifest.get("arm") not in V7_ARMS:
        errors.append("invalid V7 arm")
    padding = manifest.get("budget_padding_canonical_tokens")
    if (
        isinstance(padding, bool)
        or not isinstance(padding, int)
        or padding < 0
    ):
        errors.append("invalid budget_padding_canonical_tokens")
    if manifest.get("budget_padding_policy") not in {
        "none",
        "explicit_neutral_pad_after_all_provenance_fragments",
    }:
        errors.append("invalid budget_padding_policy")
    for field_name in (
        "context_sha256",
        "query_sha256",
        "graph_sha256",
        "routing_config_sha256",
        "candidate_ranking_sha256",
    ):
        value = manifest.get(field_name)
        if not isinstance(value, str) or not SHA256_PATTERN.fullmatch(value):
            errors.append(f"invalid {field_name}")
    selected = manifest.get("selected_chunks")
    if not isinstance(selected, list) or not selected:
        errors.append("selected_chunks must be a non-empty list")
        selected = []
    seen: set[str] = set()
    for index, row in enumerate(selected):
        prefix = f"selected_chunks[{index}]"
        chunk_id = row.get("chunk_id") if isinstance(row, Mapping) else None
        if not isinstance(chunk_id, str) or not chunk_id:
            errors.append(f"{prefix} missing chunk_id")
        elif chunk_id in seen:
            errors.append(f"duplicate chunk_id: {chunk_id}")
        else:
            seen.add(chunk_id)
        source_path = row.get("source_path") if isinstance(row, Mapping) else None
        if (
            not isinstance(source_path, str)
            or not source_path
            or PurePosixPath(source_path).is_absolute()
            or PureWindowsPath(source_path).is_absolute()
            or "\\" in source_path
            or ".." in PurePosixPath(source_path).parts
        ):
            errors.append(f"{prefix} invalid repository-relative source_path")
        for hash_field in (
            "source_sha256",
            "content_sha256",
            "injected_fragment_sha256",
        ):
            value = row.get(hash_field) if isinstance(row, Mapping) else None
            if not isinstance(value, str) or not SHA256_PATTERN.fullmatch(value):
                errors.append(f"{prefix} invalid {hash_field}")
        score = row.get("final_score") if isinstance(row, Mapping) else None
        if (
            isinstance(score, bool)
            or not isinstance(score, (int, float))
            or not math.isfinite(float(score))
        ):
            errors.append(f"{prefix} invalid final_score")
    try:
        expected = canonical_manifest_sha256_v7(manifest)
    except (TypeError, ValueError):
        errors.append("manifest is not canonical JSON")
    else:
        if manifest.get("manifest_sha256") != expected:
            errors.append("manifest hash mismatch")
    return errors
