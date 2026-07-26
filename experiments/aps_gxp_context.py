"""Deterministic lexical relevance and provenance primitives for APS-GxP v6.

The relevance implementation is deliberately standard-library-only. Retrieval
text is the normalized skill name, frontmatter ``title`` and ``description``
scalars, and all Markdown headings. Both queries and documents are lowercased
and tokenized with ``[a-z0-9]+`` after hyphens/underscores are changed to spaces;
the frozen :data:`STOP_WORDS` are removed.

For query token ``t`` and skill document ``d``, the score is BM25:

``sum(IDF(t) * f(t,d)*(k1+1) /
      (f(t,d) + k1*(1-b+b*len(d)/avgdl)))``

where ``IDF(t)=ln(1+(N-df(t)+0.5)/(df(t)+0.5))``, ``k1=1.2``, and
``b=0.75``. Each distinct query token contributes once. Exact score ties are
resolved outside this module by priority band, hub degree, then normalized
skill name. No model, embedding, network, or task outcome enters the score.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from collections import Counter
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Mapping, Sequence


BM25_K1 = 1.2
BM25_B = 0.75
TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
HEADING_PATTERN = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$")
FRONTMATTER_SCALAR_PATTERN = re.compile(
    r"^(title|name|description|version)\s*:\s*(.*?)\s*$",
    re.IGNORECASE,
)
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
SECRET_FIELD_NAMES = {
    "api_key",
    "apikey",
    "authorization",
    "client_secret",
    "credential",
    "credentials",
    "password",
    "private_key",
    "secret",
    "access_token",
    "refresh_token",
}
STOP_WORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "can",
        "create",
        "data",
        "do",
        "for",
        "from",
        "how",
        "in",
        "is",
        "it",
        "of",
        "on",
        "or",
        "output",
        "produce",
        "provide",
        "that",
        "the",
        "this",
        "to",
        "use",
        "using",
        "with",
    }
)

REQUIRED_MANIFEST_FIELDS = (
    "schema_version",
    "task_id",
    "arm",
    "run_id",
    "seed",
    "budget",
    "budget_used",
    "scheduler_sha256",
    "graph_sha256",
    "task_sha256",
    "prompt_context_sha256",
    "candidates",
    "manifest_sha256",
)
REQUIRED_CANDIDATE_FIELDS = (
    "skill_name",
    "source_path",
    "source_sha256",
    "declared_version",
    "active_node_id",
    "skill_bound_node_ids",
    "graph_relation",
    "priority_band",
    "lexical_relevance_score",
    "hub_degree",
    "final_priority_score",
    "original_estimated_tokens",
    "injected_estimated_tokens",
    "status",
    "selection_reason",
    "injected_fragment_sha256",
)
ADMITTED_STATUSES = frozenset({"loaded", "truncated"})
ALL_STATUSES = frozenset({*ADMITTED_STATUSES, "dropped", "missing"})
GRAPH_RELATIONS = frozenset(
    {"CURRENT", "SUCCESSOR", "PREDECESSOR", "GLOBAL", "OUT_OF_SCOPE"}
)
PRIORITY_BANDS = frozenset(
    {"CURRENT", "SUCCESSOR", "PREDECESSOR", "GLOBAL", "UNIFORM"}
)


def sha256_text(text: str) -> str:
    """Return a lowercase SHA-256 hex digest for UTF-8 text."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    """Return a lowercase SHA-256 digest without loading the whole file."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _frontmatter_scalars(content: str) -> dict[str, str]:
    """Extract only stable single-line fields needed for retrieval/provenance."""
    if not content.startswith("---"):
        return {}
    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}
    values: dict[str, str] = {}
    for line in parts[1].splitlines():
        match = FRONTMATTER_SCALAR_PATTERN.match(line)
        if match:
            value = match.group(2).strip().strip("\"'")
            values[match.group(1).lower()] = value
    return values


def declared_version(content: str) -> str | None:
    """Return the declared frontmatter version, when one exists."""
    return _frontmatter_scalars(content).get("version") or None


def build_retrieval_text(skill_name: str, content: str) -> str:
    """Build frozen retrieval text from name, metadata, and Markdown headings."""
    metadata = _frontmatter_scalars(content)
    headings = [
        match.group(1)
        for line in content.splitlines()
        if (match := HEADING_PATTERN.match(line))
    ]
    title = metadata.get("title") or metadata.get("name")
    if title is None and headings:
        title = headings[0]
    pieces = [
        skill_name.lstrip("/").replace("-", " ").replace("_", " "),
        title or skill_name,
        metadata.get("description", ""),
        *headings,
    ]
    return "\n".join(piece for piece in pieces if piece)


def tokenize(text: str) -> tuple[str, ...]:
    """Tokenize text according to the frozen v6 lexical rule."""
    normalized = text.lower().replace("-", " ").replace("_", " ")
    return tuple(
        token
        for token in TOKEN_PATTERN.findall(normalized)
        if token not in STOP_WORDS
    )


class Bm25RelevanceIndex:
    """Deterministic BM25 index over stable skill retrieval texts."""

    def __init__(self, skill_documents: Mapping[str, str]):
        if not skill_documents:
            raise ValueError("At least one skill document is required")
        self.retrieval_text = {
            name.lstrip("/"): build_retrieval_text(name, content)
            for name, content in sorted(skill_documents.items())
        }
        self.document_tokens = {
            name: tokenize(text) for name, text in self.retrieval_text.items()
        }
        self.term_frequencies = {
            name: Counter(tokens) for name, tokens in self.document_tokens.items()
        }
        self.document_frequency: Counter[str] = Counter()
        for tokens in self.document_tokens.values():
            self.document_frequency.update(set(tokens))
        self.document_count = len(self.document_tokens)
        self.average_document_length = (
            sum(len(tokens) for tokens in self.document_tokens.values())
            / self.document_count
        )

    def score(self, query: str, skill_name: str) -> float:
        """Return a stable BM25 score rounded for portable JSON serialization."""
        normalized_name = skill_name.lstrip("/")
        if normalized_name not in self.term_frequencies:
            raise KeyError(f"Unknown skill: {normalized_name}")
        frequencies = self.term_frequencies[normalized_name]
        document_length = len(self.document_tokens[normalized_name])
        length_ratio = (
            document_length / self.average_document_length
            if self.average_document_length
            else 1.0
        )
        score = 0.0
        for term in sorted(set(tokenize(query))):
            frequency = frequencies.get(term, 0)
            if not frequency:
                continue
            document_frequency = self.document_frequency[term]
            inverse_document_frequency = math.log(
                1.0
                + (
                    self.document_count
                    - document_frequency
                    + 0.5
                )
                / (document_frequency + 0.5)
            )
            denominator = frequency + BM25_K1 * (
                1.0 - BM25_B + BM25_B * length_ratio
            )
            score += (
                inverse_document_frequency
                * frequency
                * (BM25_K1 + 1.0)
                / denominator
            )
        return round(score, 12)


def canonical_manifest_sha256(manifest: Mapping[str, Any]) -> str:
    """Hash a canonical manifest while excluding its self-referential hash."""
    payload = dict(manifest)
    payload.pop("manifest_sha256", None)
    serialized = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    return sha256_text(serialized)


def _is_absolute_path(value: str) -> bool:
    return PurePosixPath(value).is_absolute() or PureWindowsPath(value).is_absolute()


def _secret_field_errors(value: Any, prefix: str = "manifest") -> list[str]:
    errors: list[str] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            snake_key = re.sub(
                r"([a-z0-9])([A-Z])", r"\1_\2", str(key)
            ).lower()
            normalized_key = re.sub(r"[^a-z0-9]+", "_", snake_key).strip("_")
            secret_component = any(
                component in normalized_key.split("_")
                for component in (
                    "authorization",
                    "credential",
                    "credentials",
                    "password",
                    "secret",
                )
            )
            secret_suffix = normalized_key.endswith(
                (
                    "_api_key",
                    "_access_key",
                    "_private_key",
                    "_access_token",
                    "_refresh_token",
                )
            )
            if (
                normalized_key in SECRET_FIELD_NAMES
                or secret_component
                or secret_suffix
            ):
                errors.append(f"secret-like field at {prefix}.{key}")
            errors.extend(_secret_field_errors(item, f"{prefix}.{key}"))
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for index, item in enumerate(value):
            errors.extend(_secret_field_errors(item, f"{prefix}[{index}]"))
    return errors


def validate_context_manifest(manifest: Mapping[str, Any]) -> list[str]:
    """Return deterministic provenance/safety violations for a manifest."""
    errors = _secret_field_errors(manifest)
    for field in REQUIRED_MANIFEST_FIELDS:
        if field not in manifest:
            errors.append(f"missing manifest field: {field}")

    budget = manifest.get("budget")
    budget_used = manifest.get("budget_used")
    if not isinstance(budget, int) or not isinstance(budget_used, int):
        errors.append("budget and budget_used must be integers")
    elif budget_used < 0 or budget_used > budget:
        errors.append(f"budget violation: {budget_used}/{budget}")

    for field in (
        "scheduler_sha256",
        "graph_sha256",
        "task_sha256",
        "prompt_context_sha256",
    ):
        value = manifest.get(field)
        if not isinstance(value, str) or not SHA256_PATTERN.fullmatch(value):
            errors.append(f"invalid or missing {field}")

    candidates = manifest.get("candidates")
    if not isinstance(candidates, list):
        errors.append("candidates must be a list")
        candidates = []
    seen_names: set[str] = set()
    for index, candidate in enumerate(candidates):
        prefix = f"candidate[{index}]"
        if not isinstance(candidate, Mapping):
            errors.append(f"{prefix} must be an object")
            continue
        for field in REQUIRED_CANDIDATE_FIELDS:
            if field not in candidate:
                errors.append(f"{prefix} missing {field}")
        name = candidate.get("skill_name")
        if not isinstance(name, str) or not name:
            errors.append(f"{prefix} missing skill_name")
        elif name in seen_names:
            errors.append(f"duplicate candidate skill_name: {name}")
        else:
            seen_names.add(name)
        source_path = candidate.get("source_path")
        if not isinstance(source_path, str) or not source_path:
            errors.append(f"{prefix} missing source_path")
        elif _is_absolute_path(source_path):
            errors.append(f"{prefix} contains absolute path")
        elif "\\" in source_path or ".." in PurePosixPath(source_path).parts:
            errors.append(f"{prefix} source_path is not repository-relative POSIX")
        source_hash = candidate.get("source_sha256")
        if not isinstance(source_hash, str) or not SHA256_PATTERN.fullmatch(
            source_hash
        ):
            errors.append(f"{prefix} invalid or missing source_sha256")
        reason = candidate.get("selection_reason")
        if not isinstance(reason, str) or not reason:
            errors.append(f"{prefix} missing selection_reason")
        status = candidate.get("status")
        active_node_id = candidate.get("active_node_id")
        if not isinstance(active_node_id, str) or not active_node_id:
            errors.append(f"{prefix} invalid active_node_id")
        bound_node_ids = candidate.get("skill_bound_node_ids")
        if not isinstance(bound_node_ids, list) or any(
            not isinstance(node_id, str) or not node_id
            for node_id in bound_node_ids
        ):
            errors.append(f"{prefix} invalid skill_bound_node_ids")
        graph_relation = candidate.get("graph_relation")
        if graph_relation not in GRAPH_RELATIONS:
            errors.append(f"{prefix} invalid graph_relation")
        priority_band = candidate.get("priority_band")
        if priority_band not in PRIORITY_BANDS:
            errors.append(f"{prefix} invalid priority_band")
        for field in ("lexical_relevance_score", "final_priority_score"):
            numeric = candidate.get(field)
            if (
                isinstance(numeric, bool)
                or not isinstance(numeric, (int, float))
                or not math.isfinite(float(numeric))
            ):
                errors.append(f"{prefix} invalid {field}")
        hub_degree = candidate.get("hub_degree")
        if (
            isinstance(hub_degree, bool)
            or not isinstance(hub_degree, int)
            or hub_degree < 0
        ):
            errors.append(f"{prefix} invalid hub_degree")
        original_tokens = candidate.get("original_estimated_tokens")
        if (
            isinstance(original_tokens, bool)
            or not isinstance(original_tokens, int)
            or original_tokens < 0
        ):
            errors.append(f"{prefix} invalid original_estimated_tokens")
        if status not in ALL_STATUSES:
            errors.append(f"{prefix} invalid status")
        fragment_hash = candidate.get("injected_fragment_sha256")
        if status in ADMITTED_STATUSES:
            if not isinstance(fragment_hash, str) or not SHA256_PATTERN.fullmatch(
                fragment_hash
            ):
                errors.append(
                    f"{prefix} admitted fragment missing injected_fragment_sha256"
                )
        elif fragment_hash is not None:
            errors.append(
                f"{prefix} non-admitted fragment has injected_fragment_sha256"
            )
        injected_tokens = candidate.get("injected_estimated_tokens")
        if not isinstance(injected_tokens, int) or injected_tokens < 0:
            errors.append(f"{prefix} invalid injected_estimated_tokens")

    try:
        expected_hash = canonical_manifest_sha256(manifest)
    except (TypeError, ValueError):
        errors.append("manifest contains non-canonical values")
    else:
        if manifest.get("manifest_sha256") != expected_hash:
            errors.append("manifest hash is missing or unstable")
    return errors


def simulate_skill_change(
    manifest: Mapping[str, Any],
    skill_name: str,
) -> dict[str, Any]:
    """Apply an in-memory one-skill hash/version perturbation and rehash."""
    changed = copy.deepcopy(dict(manifest))
    normalized_name = skill_name.lstrip("/")
    matched = False
    for candidate in changed.get("candidates", []):
        if candidate.get("skill_name") != normalized_name:
            continue
        matched = True
        candidate["source_sha256"] = sha256_text(
            f"aps-gxp-v6-simulated-change:{candidate['source_sha256']}"
        )
        version = candidate.get("declared_version")
        candidate["declared_version"] = (
            f"{version}+simulated" if version else "simulated"
        )
    if not matched:
        return copy.deepcopy(dict(manifest))
    changed["manifest_sha256"] = canonical_manifest_sha256(changed)
    return changed
