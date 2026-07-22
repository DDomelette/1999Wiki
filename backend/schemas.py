"""后端请求/响应 Pydantic 模型。"""
from __future__ import annotations

import json
import math
import re
from pathlib import PurePath
from typing import Annotated, Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictInt, ValidationError, model_validator
from typing_extensions import TypedDict

from src.rag.query_plan import VALID_INTENTS
from src.rag.route_policy import normalize_action_type


class RouteOptions(BaseModel):
    expanded: bool = False
    free_supplement: bool = False


class ActionItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    label: str = Field(max_length=80)
    query: str = Field(max_length=2000)
    action_type: Literal[
        "",
        "expand_search",
        "force_free_supplement",
        "expand_parent",
    ] = ""
    entity: str = Field(default="", max_length=256)
    entity_type: str = Field(default="", max_length=64)
    entity_id: str = Field(default="", max_length=128)
    semantic_intents: list[str] = Field(default_factory=list, max_length=16)
    intent: str = Field(default="", max_length=64)
    packet_policy: str = Field(default="", max_length=64)
    target_parent_id: Optional[str] = Field(default=None, max_length=256)

    @model_validator(mode="after")
    def normalize_legacy_route_action(self) -> "ActionItem":
        normalized_type = normalize_action_type(self.model_dump())
        if normalized_type:
            self.action_type = normalized_type
        self.semantic_intents = list(dict.fromkeys(
            item for item in self.semantic_intents if item in VALID_INTENTS
        ))
        if self.intent in {"llm_general", "expanded_rag"}:
            self.intent = ""
        if self.packet_policy in {"free_supplement", "expanded"}:
            self.packet_policy = ""
        return self


class RetrievalDebug(TypedDict, total=False):
    candidate_k: StrictInt
    required_source_count: StrictInt
    intent_candidates: dict[str, StrictInt]
    intent_targets: dict[str, StrictInt]
    intent_retained: dict[str, StrictInt]
    coverage_shortfall: dict[str, StrictInt]
    chars_used: StrictInt
    max_sources: StrictInt
    owner_before: StrictInt
    owner_after: StrictInt
    owner_mismatch: StrictInt
    missing_owner_metadata: StrictInt
    owner_shortfall: StrictInt


class RouteInfo(BaseModel):
    name: str
    confidence: float = 0.0
    intent: str = ""
    entity: Optional[str] = None
    requested_intents: Optional[list[str]] = None
    semantic_intents: Optional[list[str]] = None
    proposed_route: Literal["rag_grounded", "expanded_rag", "llm_general"] = "rag_grounded"
    effective_route: Literal["rag_grounded", "expanded_rag", "llm_general"] = "rag_grounded"
    retrieval_outcome: Literal["sufficient", "partial", "empty", "failed"] = "empty"
    route_reason: Literal[
        "",
        "grounded_sufficient",
        "grounded_partial",
        "grounded_empty",
        "retrieval_failed",
        "explicit_recovery_action",
        "authorized_empty_fallback",
    ] = ""
    retrieval_debug: Optional[RetrievalDebug] = None


class MemoryInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["disabled", "new", "hit", "expired"]
    turns_used: int = Field(ge=0)
    rewrite_mode: Literal["none", "planner", "fallback"]


class TimingInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_first_token_ms: Optional[float] = None
    validated_ready_ms: Optional[float] = None
    visible_first_token_ms: Optional[float] = None
    completed_ms: Optional[float] = None
    stage_ms: dict[str, float] = Field(default_factory=dict)
    error_stages: list[str] = Field(default_factory=list)
    warning: str = ""


def normalize_memory_info(
    *,
    status: str,
    turns_used: int,
    rewrite_mode: str,
) -> MemoryInfo:
    return MemoryInfo(
        status=status,
        turns_used=turns_used,
        rewrite_mode=rewrite_mode,
    )


class AskRequest(BaseModel):
    question: str
    conversation_id: Optional[UUID] = None
    category: Optional[str] = None
    route_options: RouteOptions = Field(default_factory=RouteOptions)
    action_payload: Optional[ActionItem] = None


class SourceItem(BaseModel):
    citation_id: str = ""
    name: str
    category: str
    source: str
    score: float
    heading_path: Optional[str] = None
    chunk_index: Optional[int] = None
    retrieval_stage: Optional[str] = None
    child_id: Optional[str] = None
    parent_id: Optional[str] = None
    section_kind: Optional[str] = None
    entity_type: str = ""
    entity_id: str = ""


class AssetItem(BaseModel):
    asset_id: str
    name: str = ""
    category: str = ""
    source: str = ""
    heading_path: Optional[str] = None
    role: str
    alt: str
    url: str


class MediaItem(BaseModel):
    binding_id: str = ""
    resource_id: str = ""
    media_id: str
    asset_id: str = ""
    asset_type: str = ""
    media_role: str = ""
    mime: str = ""
    url: str
    title: str = ""
    alt: str = ""
    role: str = ""
    attach_policy: str = ""
    child_id: Optional[str] = None
    parent_id: Optional[str] = None
    section: str = ""
    source_binding_token: str = ""
    owner_entity_id: str = ""
    owner_page_id: str = ""
    variant: str = ""
    skin_id: str = ""
    panel_group: Optional[str] = None
    sort_order: Optional[int] = None
    duration_ms: Optional[int] = None
    language: str = ""
    entity_type: str = ""
    entity_id: str = ""


def _media_item_matches_type(item: MediaItem, expected: str) -> bool:
    declared = [value for value in (item.asset_type, item.role) if value]
    return bool(declared) and all(value == expected for value in declared)


class VoiceLineGroup(BaseModel):
    model_config = ConfigDict(extra="forbid")

    voice_line_id: str
    title: str
    variants: list[MediaItem] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_voice_variants(self) -> "VoiceLineGroup":
        if not all(_media_item_matches_type(item, "voice") for item in self.variants):
            raise ValueError("voice panel variants must be voice media")
        return self


class VoicePanelPage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["voice"]
    grouping: Literal["voice_line"]
    entity_id: str
    entity_type: str = ""
    lines: list[VoiceLineGroup]
    page_size: int
    total_lines: int
    has_more: bool
    next_cursor: Optional[str] = None


class LegacyVideoPanel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["video"]
    items: list[MediaItem] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_video_items(self) -> "LegacyVideoPanel":
        if not all(_media_item_matches_type(item, "video") for item in self.items):
            raise ValueError("video panel items must be video media")
        return self


MediaPanel = Annotated[VoicePanelPage | LegacyVideoPanel, Field(discriminator="type")]


class AskResponse(BaseModel):
    answer: str
    grounding_mode: Literal["grounded", "ungrounded", "none"] = "none"
    sources: list[SourceItem]
    assets: list[AssetItem] = Field(default_factory=list)
    media: list[MediaItem] = Field(default_factory=list)
    route: Optional[RouteInfo] = None
    planning_status: str = ""
    planning_warning: str = ""
    planning_error: str = ""
    citation_warning: str = ""
    omitted_actions: list[ActionItem] = Field(default_factory=list)
    failure_actions: list[ActionItem] = Field(default_factory=list)
    media_panels: list[MediaPanel] = Field(default_factory=list)
    memory: MemoryInfo = Field(default_factory=lambda: MemoryInfo(
        status="disabled",
        turns_used=0,
        rewrite_mode="none",
    ))
    timing: Optional[TimingInfo] = None


class HealthResponse(BaseModel):
    status: str
    vectorstore_loaded: bool
    llm_ready: bool
    doc_count: int
    provenance_status: Literal["pending", "pass", "blocked", "error"] = "pending"
    provenance_errors: list[str] = Field(default_factory=list)
    provenance_evidence: str = ""


class CategoryMeta(BaseModel):
    key: str
    title: str
    subtitle: str
    description: str
    doc_count: int
    cover_prompt: str


class CategoriesResponse(BaseModel):
    categories: list[CategoryMeta]


class CategoryDoc(BaseModel):
    name: str
    source: str
    snippet: str


class CategoryDocsResponse(BaseModel):
    key: str
    docs: list[CategoryDoc]


_LOCAL_PATH_RE = re.compile(r"(?:file://|(?<![a-z0-9])[a-z]:[\\/])", re.IGNORECASE)
_SENSITIVE_KEYS = {
    "api_key",
    "access_key",
    "secret",
    "secret_key",
    "password",
    "prompt",
    "content",
    "plan",
    "query_plan",
    "local_path",
    "local_relpath",
    "authorization",
    "credentials",
}
_SENSITIVE_KEY_MARKERS = (
    "prompt",
    "content",
    "secret",
    "token",
    "password",
    "credential",
    "authorization",
    "api_key",
    "access_key",
    "relpath",
)
_ALLOWED_PATH_KEYS = {"heading_path"}
_ALLOWED_TIMING_KEYS = {
    "model_first_token_ms",
    "validated_ready_ms",
    "visible_first_token_ms",
    "completed_ms",
    "stage_ms",
    "error_stages",
}
_ALLOWED_STAGE_NAMES = frozenset({
    "memory.acquire",
    "planner.llm",
    "planner.normalize",
    "entity.resolve",
    "route.resolve",
    "retrieval.structured",
    "retrieval.bm25",
    "retrieval.dense",
    "retrieval.fusion",
    "retrieval.rerank",
    "retrieval.expand",
    "retrieval.allocate",
    "media.attach",
    "source_map.build",
    "answer.llm",
    "citation.validate",
    "citation.repair",
    "response.serialize",
})
_DROP = object()
_SAFE_ROUTE_INTENTS = frozenset(VALID_INTENTS)
_ACRONYM_KEY_BOUNDARY_RE = re.compile(r"([A-Z]+)([A-Z][a-z])")
_CAMEL_KEY_BOUNDARY_RE = re.compile(r"([a-z0-9])([A-Z])")
_KEY_DELIMITER_RE = re.compile(r"[^A-Za-z0-9]+")


def _normalize_transport_key(value: str) -> tuple[str, set[str]]:
    split = _ACRONYM_KEY_BOUNDARY_RE.sub(r"\1_\2", value)
    split = _CAMEL_KEY_BOUNDARY_RE.sub(r"\1_\2", split)
    parts = {
        part.lower()
        for part in _KEY_DELIMITER_RE.split(split)
        if part
    }
    return "_".join(part.lower() for part in _KEY_DELIMITER_RE.split(split) if part), parts


def _is_sensitive_key(value: Any) -> bool:
    if type(value) is not str:
        return True
    key, key_parts = _normalize_transport_key(value)
    if key in _ALLOWED_TIMING_KEYS or key == "source_binding_token":
        return False
    return (
        key in _SENSITIVE_KEYS
        or any(marker in key for marker in _SENSITIVE_KEY_MARKERS)
        or bool({"plan", "planner"} & key_parts)
        or (key not in _ALLOWED_PATH_KEYS and (key == "path" or key.endswith("_path")))
        or key.endswith("_api_key")
        or key.endswith("_access_key")
        or key.endswith("_secret")
        or key.endswith("_secret_key")
        or key.endswith("_password")
    )


def _sanitize_transport_value(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized = {}
        for key, item in value.items():
            if _is_sensitive_key(key):
                continue
            child = (
                _sanitize_stage_ms(item)
                if key == "stage_ms"
                else _sanitize_transport_value(item)
            )
            if child is not _DROP:
                sanitized[key] = child
        return sanitized
    if isinstance(value, (list, tuple)):
        sanitized = [_sanitize_transport_value(item) for item in value]
        return [item for item in sanitized if item is not _DROP]
    if isinstance(value, (set, frozenset)):
        sanitized = [_sanitize_transport_value(item) for item in value]
        safe = [item for item in sanitized if item is not _DROP]
        return sorted(
            safe,
            key=lambda item: json.dumps(
                item,
                ensure_ascii=True,
                sort_keys=True,
                separators=(",", ":"),
            ),
        )
    if isinstance(value, (PurePath, bytes, bytearray, memoryview)):
        return _DROP
    if isinstance(value, str):
        return _DROP if _LOCAL_PATH_RE.search(value) else value
    if value is None or type(value) in (bool, int):
        return value
    if type(value) is float:
        return value if math.isfinite(value) else _DROP
    return _DROP


def _sanitize_stage_ms(value: Any) -> dict[str, float]:
    if not isinstance(value, dict):
        return {}
    return {
        key: float(duration)
        for key, duration in value.items()
        if key in _ALLOWED_STAGE_NAMES
        and isinstance(duration, (int, float))
        and not isinstance(duration, bool)
        and math.isfinite(float(duration))
        and float(duration) >= 0
    }
def sanitize_transport_value(value: Any) -> Any:
    sanitized = _sanitize_transport_value(value)
    return None if sanitized is _DROP else sanitized


def _strict_ordered_strings(value: Any) -> list[str] | None:
    if not isinstance(value, (list, tuple)):
        return None
    return list(dict.fromkeys(
        item for item in value if _is_safe_intent_identifier(item)
    ))


def _is_safe_intent_identifier(value: Any) -> bool:
    return type(value) is str and value in _SAFE_ROUTE_INTENTS


def _strict_retrieval_debug(value: Any) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None
    result: dict[str, object] = {}
    for field in (
        "candidate_k",
        "required_source_count",
        "chars_used",
        "max_sources",
        "owner_before",
        "owner_after",
        "owner_mismatch",
        "missing_owner_metadata",
        "owner_shortfall",
    ):
        item = value.get(field)
        if type(item) is int:
            result[field] = item
    for field in (
        "intent_candidates",
        "intent_targets",
        "intent_retained",
        "coverage_shortfall",
    ):
        item = value.get(field)
        if isinstance(item, dict):
            result[field] = {
                key: count
                for key, count in item.items()
                if _is_safe_intent_identifier(key) and type(count) is int
            }
    return result


def normalize_route(route: Any) -> dict[str, Any] | None:
    if not isinstance(route, dict):
        return None
    requested_intents = _strict_ordered_strings(route.get("requested_intents"))
    semantic_intents = _strict_ordered_strings(route.get("semantic_intents"))
    retrieval_debug = _strict_retrieval_debug(route.get("retrieval_debug"))
    route = sanitize_transport_value(route)
    if not isinstance(route, dict):
        return None
    candidate = {
        key: route[key]
        for key in (
            "name",
            "confidence",
            "intent",
            "entity",
            "proposed_route",
            "effective_route",
            "retrieval_outcome",
            "route_reason",
        )
        if key in route
    }
    if requested_intents is not None:
        candidate["requested_intents"] = requested_intents
    if semantic_intents is not None:
        candidate["semantic_intents"] = semantic_intents
    if retrieval_debug is not None:
        candidate["retrieval_debug"] = retrieval_debug
    try:
        return RouteInfo.model_validate(candidate).model_dump()
    except ValidationError:
        return None


def normalize_asset_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = []
    items = sanitize_transport_value(items)
    if not isinstance(items, list):
        return normalized
    for item in items:
        if not isinstance(item, dict) or not item.get("url"):
            continue
        normalized.append(
            AssetItem(
                asset_id=item.get("asset_id", item.get("media_id", "")),
                name=item.get("name", ""),
                category=item.get("category", ""),
                source=item.get("source", ""),
                heading_path=item.get("heading_path"),
                role=item.get("role", item.get("asset_type", "")),
                alt=item.get("alt", item.get("title", "")),
                url=item.get("url", ""),
            ).model_dump()
        )
    return normalized


def normalize_media_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = []
    items = sanitize_transport_value(items)
    if not isinstance(items, list):
        return normalized
    for item in items:
        if not isinstance(item, dict) or not item.get("url"):
            continue
        normalized.append(
            MediaItem(
                binding_id=item.get("binding_id", ""),
                resource_id=item.get("resource_id", ""),
                media_id=item.get("media_id", item.get("asset_id", "")),
                asset_id=item.get(
                    "binding_id",
                    item.get("asset_id", item.get("media_id", "")),
                ),
                asset_type=item.get("asset_type", item.get("role", "")),
                media_role=item.get("media_role", item.get("role", "")),
                mime=item.get("mime", ""),
                url=item.get("url", ""),
                title=item.get("title", item.get("alt", "")),
                alt=item.get("alt", ""),
                role=item.get("role", item.get("asset_type", "")),
                attach_policy=item.get("attach_policy", ""),
                child_id=item.get("child_id"),
                parent_id=item.get("parent_id"),
                section=item.get("section", ""),
                source_binding_token=item.get("source_binding_token", ""),
                owner_entity_id=item.get("owner_entity_id", ""),
                owner_page_id=item.get("owner_page_id", ""),
                variant=item.get("variant", ""),
                skin_id=item.get("skin_id", ""),
                panel_group=item.get("panel_group"),
                sort_order=item.get("sort_order"),
                duration_ms=item.get("duration_ms"),
                language=item.get("language", ""),
                entity_type=item.get("entity_type", ""),
                entity_id=item.get("entity_id", ""),
            ).model_dump()
        )
    return normalized


def normalize_media_panels(panels: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    panels = sanitize_transport_value(panels)
    if not isinstance(panels, list):
        return normalized
    for panel in panels:
        if not isinstance(panel, dict):
            continue
        panel_type = panel.get("type")
        model = VoicePanelPage if panel_type == "voice" else LegacyVideoPanel if panel_type == "video" else None
        if model is None:
            continue
        try:
            normalized.append(model.model_validate(panel).model_dump())
        except ValidationError:
            continue
    return normalized
