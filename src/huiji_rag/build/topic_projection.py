"""Versioned selector catalog and source-backed Topic projection."""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Iterable, Mapping

from src.huiji_rag.models import ChildBlock, ParentBlock

from .contracts import canonical_json_bytes


DEFAULT_TOPIC_CATALOG_PATH = (
    Path(__file__).resolve().parents[1] / "resources" / "topic_catalog.v1.json"
)
_CATALOG_SCHEMA_VERSION = "huiji.topic-catalog/v1"
_ROOT_FIELDS = frozenset({"schema_version", "topics"})
_TOPIC_FIELDS = frozenset(
    {
        "topic_id",
        "name",
        "aliases",
        "exact_page_titles",
        "exact_heading_titles",
        "required_route_tags",
        "definition_patterns",
        "structured_relations",
    }
)
_RELATION_FIELDS = frozenset({"field", "value"})
_SAFE_TOPIC_ID_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
_SAFE_RELATION_FIELD_RE = re.compile(r"[a-z][a-z0-9_]*\Z")


class TopicCatalogError(ValueError):
    """Raised when selector catalog identity or behavior is ambiguous."""


@dataclass(frozen=True)
class TopicRelationSelector:
    field: str
    value: str


@dataclass(frozen=True)
class TopicCatalogItem:
    topic_id: str
    name: str
    aliases: tuple[str, ...]
    exact_page_titles: tuple[str, ...]
    exact_heading_titles: tuple[str, ...]
    required_route_tags: tuple[str, ...]
    definition_patterns: tuple[str, ...]
    structured_relations: tuple[TopicRelationSelector, ...]

    @property
    def selector_count(self) -> int:
        return (
            len(self.exact_page_titles)
            + len(self.exact_heading_titles)
            + len(self.definition_patterns)
            + len(self.structured_relations)
        )


@dataclass(frozen=True)
class TopicCatalog:
    schema_version: str
    topics: tuple[TopicCatalogItem, ...]
    fingerprint_sha256: str


@dataclass(frozen=True)
class TopicDiagnostic:
    reason_code: str
    topic_id: str
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "details", MappingProxyType(dict(self.details)))


@dataclass(frozen=True)
class TopicChildProjection:
    block: ChildBlock
    owner_entity_id: str
    owner_page_id: str
    source_fields: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_fields", MappingProxyType(dict(self.source_fields)))

    def to_json(self) -> dict[str, Any]:
        row = self.block.to_json()
        row.update(
            {
                "owner_entity_id": self.owner_entity_id,
                "owner_page_id": self.owner_page_id,
                "source_fields": dict(self.source_fields),
            }
        )
        return row


@dataclass(frozen=True)
class TopicProjection:
    parents: tuple[ParentBlock, ...]
    children: tuple[TopicChildProjection, ...]
    diagnostics: tuple[TopicDiagnostic, ...]
    catalog_fingerprint_sha256: str


@dataclass(frozen=True)
class _SourceChild:
    category: str
    entity_type: str
    entity_id: str
    entity_name: str
    entity_aliases: tuple[str, ...]
    owner_entity_id: str
    owner_page_id: str
    route_tags: tuple[str, ...]
    parent_id: str
    child_id: str
    heading_path: tuple[str, ...]
    section_kind: str
    content: str
    source_refs: tuple[dict[str, Any], ...]
    source_fields: Mapping[str, Any]


def load_topic_catalog(
    path: Path = DEFAULT_TOPIC_CATALOG_PATH,
) -> TopicCatalog:
    """Load and validate exact UTF-8 catalog bytes."""
    catalog_path = Path(path)
    raw_bytes = catalog_path.read_bytes()
    try:
        raw = json.loads(raw_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise TopicCatalogError("topic catalog is not valid UTF-8 JSON") from error
    return validate_topic_catalog(
        raw,
        fingerprint_sha256=hashlib.sha256(raw_bytes).hexdigest(),
    )


def validate_topic_catalog(
    raw: Any,
    *,
    fingerprint_sha256: str | None = None,
) -> TopicCatalog:
    """Validate selector identity, schema, and deterministic source ordering."""
    if not isinstance(raw, dict) or set(raw) != _ROOT_FIELDS:
        raise TopicCatalogError("topic catalog root fields are invalid")
    if raw.get("schema_version") != _CATALOG_SCHEMA_VERSION:
        raise TopicCatalogError("topic catalog schema version is invalid")
    topic_rows = raw.get("topics")
    if not isinstance(topic_rows, list) or not topic_rows:
        raise TopicCatalogError("topic catalog topics must be a non-empty list")

    items = tuple(_validate_topic_row(row) for row in topic_rows)
    topic_ids = tuple(item.topic_id for item in items)
    if topic_ids != tuple(sorted(topic_ids, key=_sort_key)):
        raise TopicCatalogError("topic catalog topics are not deterministically ordered")
    if len(set(topic_ids)) != len(topic_ids):
        raise TopicCatalogError("topic catalog contains duplicate topic IDs")

    identity_owner: dict[str, str] = {}
    for item in items:
        for identity in (item.name, *item.aliases):
            normalized = _normalize(identity)
            previous = identity_owner.get(normalized)
            if previous is not None and previous != item.topic_id:
                raise TopicCatalogError("topic catalog contains ambiguous aliases")
            identity_owner[normalized] = item.topic_id

    fingerprint = fingerprint_sha256 or hashlib.sha256(
        canonical_json_bytes(raw, trailing_newline=False)
    ).hexdigest()
    return TopicCatalog(_CATALOG_SCHEMA_VERSION, items, fingerprint)


def project_topics(
    source_children: Iterable[Any],
    *,
    catalog: TopicCatalog | None = None,
) -> TopicProjection:
    """Copy eligible source children into deterministic Topic ownership."""
    selected_catalog = catalog or load_topic_catalog()
    sources = tuple(_source_child(item) for item in source_children)
    parents: list[ParentBlock] = []
    children: list[TopicChildProjection] = []
    diagnostics: list[TopicDiagnostic] = []

    for topic in selected_catalog.topics:
        topic_children: list[TopicChildProjection] = []
        for source in sources:
            evidence_kind = _eligible_evidence(topic, source)
            if evidence_kind is None:
                continue
            topic_children.append(_topic_child(topic, source, evidence_kind))
        if not topic_children:
            diagnostics.append(
                TopicDiagnostic(
                    "topic_evidence_shortfall",
                    topic.topic_id,
                    {"selector_count": topic.selector_count},
                )
            )
            continue
        parent_id = f"topic:{topic.topic_id}/topic"
        parents.append(
            ParentBlock(
                parent_id=parent_id,
                entity_id=topic.topic_id,
                entity_name=topic.name,
                entity_aliases=topic.aliases,
                category="topic",
                section_kind="topic",
                title=topic.name,
                summary_text=topic_children[0].block.content,
                source_refs=_dedupe_refs(
                    ref
                    for child in topic_children
                    for ref in child.block.source_refs
                ),
                child_ids=tuple(child.block.child_id for child in topic_children),
                content_hash=hashlib.sha256(
                    "\n".join(
                        child.block.content_hash for child in topic_children
                    ).encode("utf-8")
                ).hexdigest(),
                entity_type="topic",
                depth_level=1,
                ancestor_ids=(f"topic:{topic.topic_id}",),
            )
        )
        children.extend(topic_children)

    return TopicProjection(
        parents=tuple(parents),
        children=tuple(children),
        diagnostics=tuple(diagnostics),
        catalog_fingerprint_sha256=selected_catalog.fingerprint_sha256,
    )


def _validate_topic_row(raw: Any) -> TopicCatalogItem:
    if not isinstance(raw, dict) or set(raw) != _TOPIC_FIELDS:
        raise TopicCatalogError("topic catalog item fields are invalid")
    topic_id = _required_string(raw.get("topic_id"), "topic_id")
    if not _SAFE_TOPIC_ID_RE.fullmatch(topic_id):
        raise TopicCatalogError("topic ID is invalid")
    name = _required_string(raw.get("name"), "name")
    aliases = _ordered_strings(raw.get("aliases"), "aliases")
    exact_page_titles = _ordered_strings(
        raw.get("exact_page_titles"), "exact_page_titles"
    )
    exact_heading_titles = _ordered_strings(
        raw.get("exact_heading_titles"), "exact_heading_titles"
    )
    required_route_tags = _ordered_strings(
        raw.get("required_route_tags"), "required_route_tags"
    )
    definition_patterns = _ordered_strings(
        raw.get("definition_patterns"), "definition_patterns"
    )
    for pattern in definition_patterns:
        try:
            re.compile(pattern)
        except re.error as error:
            raise TopicCatalogError("definition pattern is invalid") from error

    relation_rows = raw.get("structured_relations")
    if not isinstance(relation_rows, list):
        raise TopicCatalogError("structured_relations must be a list")
    structured_relations = tuple(_relation_selector(item) for item in relation_rows)
    relation_order = tuple(
        (item.field, item.value) for item in structured_relations
    )
    if relation_order != tuple(
        sorted(relation_order, key=lambda item: (_sort_key(item[0]), _sort_key(item[1])))
    ):
        raise TopicCatalogError("structured_relations are not deterministically ordered")
    if len(set(relation_order)) != len(relation_order):
        raise TopicCatalogError("structured_relations contain duplicates")

    item = TopicCatalogItem(
        topic_id=topic_id,
        name=name,
        aliases=aliases,
        exact_page_titles=exact_page_titles,
        exact_heading_titles=exact_heading_titles,
        required_route_tags=required_route_tags,
        definition_patterns=definition_patterns,
        structured_relations=structured_relations,
    )
    if item.selector_count == 0:
        raise TopicCatalogError("topic catalog item has no selectors")
    if _normalize(name) in {_normalize(alias) for alias in aliases}:
        raise TopicCatalogError("topic name is duplicated in aliases")
    return item


def _relation_selector(raw: Any) -> TopicRelationSelector:
    if not isinstance(raw, dict) or set(raw) != _RELATION_FIELDS:
        raise TopicCatalogError("structured relation fields are invalid")
    field_name = _required_string(raw.get("field"), "structured relation field")
    value = _required_string(raw.get("value"), "structured relation value")
    if not _SAFE_RELATION_FIELD_RE.fullmatch(field_name):
        raise TopicCatalogError("structured relation field is invalid")
    return TopicRelationSelector(field_name, value)


def _ordered_strings(raw: Any, field_name: str) -> tuple[str, ...]:
    if not isinstance(raw, list):
        raise TopicCatalogError(f"{field_name} must be a list")
    values = tuple(_required_string(item, field_name) for item in raw)
    if values != tuple(sorted(values, key=_sort_key)):
        raise TopicCatalogError(f"{field_name} is not deterministically ordered")
    normalized = tuple(_normalize(item) for item in values)
    if len(set(normalized)) != len(normalized):
        raise TopicCatalogError(f"{field_name} contains duplicates")
    return values


def _required_string(raw: Any, field_name: str) -> str:
    if not isinstance(raw, str) or not raw.strip():
        raise TopicCatalogError(f"{field_name} must be a non-empty string")
    if raw != raw.strip():
        raise TopicCatalogError(f"{field_name} contains surrounding whitespace")
    return raw


def _source_child(raw: Any) -> _SourceChild:
    block = getattr(raw, "block", None)
    public = block if isinstance(block, ChildBlock) else raw
    content = str(getattr(public, "content", getattr(public, "text", "")))
    source_refs = tuple(dict(item) for item in getattr(public, "source_refs", ()))
    if not content or not source_refs:
        raise ValueError("Topic source child must have content and source refs")
    heading_path = tuple(str(item) for item in getattr(public, "heading_path", ()))
    if not heading_path or any(not item for item in heading_path):
        raise ValueError("Topic source child must have a non-empty heading path")
    return _SourceChild(
        category=str(getattr(public, "category", "")),
        entity_type=str(getattr(public, "entity_type", "")),
        entity_id=str(getattr(public, "entity_id", "")),
        entity_name=str(getattr(public, "entity_name", "")),
        entity_aliases=tuple(getattr(public, "entity_aliases", ())),
        owner_entity_id=str(getattr(raw, "owner_entity_id", "")),
        owner_page_id=str(getattr(raw, "owner_page_id", "")),
        route_tags=tuple(getattr(public, "route_tags", ())),
        parent_id=str(getattr(public, "parent_id", "")),
        child_id=str(getattr(public, "child_id", "")),
        heading_path=heading_path,
        section_kind=str(getattr(public, "section_kind", "")),
        content=content,
        source_refs=source_refs,
        source_fields=MappingProxyType(dict(getattr(raw, "source_fields", {}))),
    )


def _eligible_evidence(
    topic: TopicCatalogItem,
    source: _SourceChild,
) -> str | None:
    if not set(topic.required_route_tags).issubset(source.route_tags):
        return None
    page_titles = {_normalize(item) for item in topic.exact_page_titles}
    if source.entity_type == "page" and _normalize(source.entity_name) in page_titles:
        return "exact_page_title"
    if source.entity_type == "page" and any(
        _normalize(alias) in page_titles for alias in source.entity_aliases
    ):
        return "redirect_alias"
    heading_titles = {_normalize(item) for item in topic.exact_heading_titles}
    if any(_normalize(item) in heading_titles for item in source.heading_path):
        return "exact_heading"
    for relation in topic.structured_relations:
        if _relation_matches(source.source_fields.get(relation.field), relation.value):
            return "structured_relation"
    if _definition_eligible(source) and any(
        re.search(pattern, source.content) for pattern in topic.definition_patterns
    ):
        return "controlled_definition"
    return None


def _definition_eligible(source: _SourceChild) -> bool:
    if "voice" in source.route_tags:
        return False
    return bool(
        {"page", "definition", "worldview"}.intersection(source.route_tags)
    )


def _relation_matches(raw: Any, expected: str) -> bool:
    if isinstance(raw, bool) or raw is None:
        return False
    if isinstance(raw, (str, int)):
        return str(raw) == expected
    if isinstance(raw, (list, tuple)):
        return any(_relation_matches(item, expected) for item in raw)
    return False


def _topic_child(
    topic: TopicCatalogItem,
    source: _SourceChild,
    evidence_kind: str,
) -> TopicChildProjection:
    owner_id = f"topic:{topic.topic_id}"
    parent_id = f"{owner_id}/topic"
    relation_digest = hashlib.sha256(
        f"{topic.topic_id}\0{source.child_id}".encode("utf-8")
    ).hexdigest()[:20]
    route_tags = ["topic"]
    if evidence_kind == "controlled_definition":
        route_tags.extend(("definition", "worldview"))
    source_title = " ".join(
        str(ref.get("source_title") or "")
        for ref in source.source_refs
        if ref.get("source_title")
    )
    search_text = " ".join(
        value
        for value in (
            topic.name,
            " ".join(topic.aliases),
            source_title,
            " ".join(source.heading_path),
            source.content,
        )
        if value
    )
    block = ChildBlock(
        child_id=f"{parent_id}/source:{relation_digest}",
        parent_id=parent_id,
        entity_id=topic.topic_id,
        entity_name=topic.name,
        category="topic",
        section_kind="topic",
        title=topic.name,
        text=source.content,
        search_text=search_text,
        chunk_index=0,
        media_ids=(),
        media_policy="text_only",
        source_refs=source.source_refs,
        content_hash=hashlib.sha256(source.content.encode("utf-8")).hexdigest(),
        entity_type="topic",
        depth_level=3,
        ancestor_ids=(owner_id, parent_id),
        route_tags=tuple(route_tags),
        content=source.content,
        heading_path=source.heading_path,
        entity_aliases=topic.aliases,
    )
    return TopicChildProjection(
        block=block,
        owner_entity_id=owner_id,
        owner_page_id=owner_id,
        source_fields={
            "evidence_kind": evidence_kind,
            "source_child_id": source.child_id,
            "source_parent_id": source.parent_id,
            "source_owner_entity_id": source.owner_entity_id,
            "source_owner_page_id": source.owner_page_id,
            "source_entity_type": source.entity_type,
        },
    )


def _dedupe_refs(refs: Iterable[Mapping[str, Any]]) -> tuple[dict[str, Any], ...]:
    seen: set[bytes] = set()
    result: list[dict[str, Any]] = []
    for ref in refs:
        row = dict(ref)
        fingerprint = canonical_json_bytes(row, trailing_newline=False)
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        result.append(row)
    return tuple(result)


def _normalize(value: str) -> str:
    return unicodedata.normalize("NFKC", value).strip().casefold()


def _sort_key(value: str) -> tuple[str, str]:
    return (_normalize(value), value)
