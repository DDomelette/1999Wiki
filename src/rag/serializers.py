from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .contracts import FrozenRetrievalPacket, ResponsePacket, SubtaskInfo, freeze_value

_SOURCE_FIELDS = (
    "citation_id",
    "name",
    "category",
    "source",
    "score",
    "heading_path",
    "chunk_index",
    "retrieval_stage",
    "child_id",
    "parent_id",
    "section_kind",
    "entity_type",
    "entity_id",
)
_MEDIA_FIELDS = (
    "binding_id",
    "resource_id",
    "media_id",
    "asset_id",
    "asset_type",
    "media_role",
    "mime",
    "url",
    "title",
    "alt",
    "role",
    "attach_policy",
    "child_id",
    "parent_id",
    "section",
    "source_binding_token",
    "owner_entity_id",
    "owner_page_id",
    "variant",
    "skin_id",
    "panel_group",
    "sort_order",
    "duration_ms",
    "language",
    "entity_type",
    "entity_id",
)
_ASSET_FIELDS = (
    "asset_id",
    "name",
    "category",
    "source",
    "heading_path",
    "role",
    "alt",
    "url",
)
_ACTION_FIELDS = (
    "subtask_id",
    "label",
    "query",
    "action_type",
    "entity",
    "entity_type",
    "entity_id",
    "semantic_intents",
    "intent",
    "packet_policy",
    "target_parent_id",
)
_ROUTE_FIELDS = (
    "name",
    "confidence",
    "intent",
    "entity",
    "requested_intents",
    "semantic_intents",
    "proposed_route",
    "effective_route",
    "retrieval_outcome",
    "route_reason",
    "retrieval_debug",
)
_LOCAL_PATH_RE = re.compile(r"(?:file://|(?<![a-z0-9])[a-z]:[\\/])", re.IGNORECASE)
_DEBUG_INT_FIELDS = (
    "candidate_k",
    "required_source_count",
    "chars_used",
    "max_sources",
    "owner_before",
    "owner_after",
    "owner_mismatch",
    "missing_owner_metadata",
    "owner_shortfall",
)
_DEBUG_COUNT_FIELDS = (
    "intent_candidates",
    "intent_targets",
    "intent_retained",
    "coverage_shortfall",
)


@dataclass(frozen=True)
class SSEEvent:
    event: str
    data: Mapping[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(self, "data", freeze_value(self.data))

    def to_dict(self) -> dict[str, Any]:
        return _plain(self.data)


def response_packet_to_public_dict(packet: ResponsePacket) -> dict[str, Any]:
    public = retrieval_packet_to_public_dict(
        packet.retrieval_packet,
        grounding_mode=packet.grounding_mode,
        citation_warning=",".join(packet.citation_validation.warnings),
        memory_info=packet.memory_info,
    )
    public["subtasks"] = [
        _branch_to_public(branch) for branch in packet.branch_results
    ]
    return {"answer": packet.answer, **public}


def retrieval_packet_to_public_dict(
    retrieval: FrozenRetrievalPacket,
    *,
    grounding_mode: str,
    citation_warning: str,
    memory_info: Mapping[str, object],
) -> dict[str, Any]:
    route = retrieval.diagnostics.get("route", {})
    return {
        "grounding_mode": grounding_mode,
        "sources": [_source_to_public(row) for row in retrieval.sources],
        "assets": [
            item for row in retrieval.assets if (item := _asset_to_public(row)) is not None
        ],
        "media": [
            item for row in retrieval.media if (item := _media_to_public(row)) is not None
        ],
        "media_panels": [
            panel
            for row in retrieval.media_panels
            if (panel := _panel_to_public(row)) is not None
        ],
        "route": _route_to_public(route) if isinstance(route, Mapping) else None,
        "planning_status": retrieval.planning_status,
        "planning_warning": retrieval.planning_warning,
        "planning_error": retrieval.planning_error,
        "citation_warning": citation_warning,
        "omitted_actions": [_action_to_public(row) for row in retrieval.omitted_actions],
        "failure_actions": [_action_to_public(row) for row in retrieval.failure_actions],
        "subtasks": [],
        "memory": dict(memory_info),
    }


def _branch_to_public(branch: Any) -> dict[str, Any]:
    subtask = SubtaskInfo.from_branch(branch)
    return {
        "subtask_id": subtask.subtask_id,
        "order": subtask.order,
        "task_type": subtask.task_type,
        "query": subtask.query,
        "effective_route": subtask.effective_route,
        "retrieval_outcome": subtask.retrieval_outcome,
        "grounding_mode": subtask.grounding_mode,
        "status": subtask.status,
        "citation_ids": list(subtask.citation_ids),
    }


def response_packet_to_sse_events(
    packet: ResponsePacket,
    *,
    token_chunk_size: int = 32,
) -> tuple[SSEEvent, ...]:
    if token_chunk_size <= 0:
        raise ValueError("token_chunk_size must be positive")
    public = response_packet_to_public_dict(packet)
    sources_data = {key: value for key, value in public.items() if key != "answer"}
    events = [SSEEvent("sources", sources_data)]
    events.extend(
        SSEEvent("token", {"token": packet.answer[offset: offset + token_chunk_size]})
        for offset in range(0, len(packet.answer), token_chunk_size)
    )
    events.append(SSEEvent("done", public))
    return tuple(events)


def response_packet_to_sse_strings(
    packet: ResponsePacket,
    *,
    token_chunk_size: int = 32,
) -> tuple[str, ...]:
    return tuple(
        f"event: {event.event}\ndata: {json.dumps(_plain(event.data), ensure_ascii=False)}\n\n"
        for event in response_packet_to_sse_events(packet, token_chunk_size=token_chunk_size)
    )


def _select(value: Mapping[str, Any], fields: Sequence[str]) -> dict[str, Any]:
    return {
        field: _plain(value[field])
        for field in fields
        if field in value
    }


def _source_to_public(source: Mapping[str, Any]) -> dict[str, Any]:
    result = {
        "citation_id": "",
        "name": "",
        "category": "",
        "source": "",
        "score": 0.0,
        "heading_path": None,
        "chunk_index": None,
        "retrieval_stage": None,
        "child_id": None,
        "parent_id": None,
        "section_kind": None,
        "entity_type": "",
        "entity_id": "",
    }
    result.update(_select(source, _SOURCE_FIELDS))
    source_path = result.get("source")
    if isinstance(source_path, str) and _LOCAL_PATH_RE.search(source_path):
        result["source"] = ""
    return result


def _asset_to_public(asset: Mapping[str, Any]) -> dict[str, Any] | None:
    url = str(asset.get("url") or "")
    if not url or _LOCAL_PATH_RE.search(url):
        return None
    result = {
        "asset_id": str(
            asset.get("binding_id")
            or asset.get("asset_id")
            or asset.get("media_id")
            or ""
        ),
        "name": "",
        "category": "",
        "source": "",
        "heading_path": None,
        "role": str(asset.get("asset_type") or ""),
        "alt": str(asset.get("title") or ""),
        "url": url,
    }
    result.update(_select(asset, _ASSET_FIELDS))
    result["url"] = url
    return result


def _media_to_public(media: Mapping[str, Any]) -> dict[str, Any] | None:
    url = str(media.get("url") or "")
    if not url or _LOCAL_PATH_RE.search(url):
        return None
    result = {
        "binding_id": str(media.get("binding_id") or ""),
        "resource_id": str(media.get("resource_id") or ""),
        "media_id": str(media.get("media_id") or media.get("asset_id") or ""),
        "asset_id": str(
            media.get("binding_id")
            or media.get("asset_id")
            or media.get("media_id")
            or ""
        ),
        "asset_type": str(media.get("role") or ""),
        "media_role": str(media.get("media_role") or media.get("role") or ""),
        "mime": "",
        "url": url,
        "title": "",
        "alt": "",
        "role": str(media.get("asset_type") or ""),
        "attach_policy": "",
        "child_id": None,
        "parent_id": None,
        "section": "",
        "source_binding_token": "",
        "owner_entity_id": "",
        "owner_page_id": "",
        "variant": "",
        "skin_id": "",
        "panel_group": None,
        "sort_order": None,
        "duration_ms": None,
        "language": "",
        "entity_type": "",
        "entity_id": "",
    }
    result.update(_select(media, _MEDIA_FIELDS))
    result["url"] = url
    return result


def _route_to_public(route: Mapping[str, Any]) -> dict[str, Any]:
    result = {
        "name": "rag_grounded",
        "confidence": 0.0,
        "intent": "",
        "entity": None,
        "requested_intents": None,
        "semantic_intents": None,
        "proposed_route": "rag_grounded",
        "effective_route": "rag_grounded",
        "retrieval_outcome": "empty",
        "route_reason": "",
        "retrieval_debug": None,
    }
    result.update(_select(route, _ROUTE_FIELDS))
    debug = route.get("retrieval_debug")
    if isinstance(debug, Mapping):
        strict: dict[str, Any] = {}
        for field in _DEBUG_INT_FIELDS:
            value = debug.get(field)
            if type(value) is int:
                strict[field] = value
        for field in _DEBUG_COUNT_FIELDS:
            value = debug.get(field)
            if isinstance(value, Mapping):
                counts = {
                    str(key): count
                    for key, count in value.items()
                    if type(key) is str and type(count) is int
                }
                strict[field] = counts
        result["retrieval_debug"] = strict
    return result


def _action_to_public(action: Mapping[str, Any]) -> dict[str, Any]:
    result = {
        "label": "",
        "query": "",
        "action_type": "",
        "entity": "",
        "entity_type": "",
        "entity_id": "",
        "semantic_intents": [],
        "intent": "",
        "packet_policy": "",
        "target_parent_id": None,
    }
    result.update(_select(action, _ACTION_FIELDS))
    return result


def _panel_to_public(panel: Mapping[str, Any]) -> dict[str, Any] | None:
    panel_type = str(panel.get("type") or "")
    if panel_type == "voice":
        lines = []
        for line in panel.get("lines", ()):
            if not isinstance(line, Mapping):
                continue
            variants = [
                public_item
                for item in line.get("variants", ())
                if isinstance(item, Mapping)
                if (public_item := _media_to_public(item)) is not None
            ]
            if not variants:
                continue
            lines.append({
                "voice_line_id": line.get("voice_line_id", ""),
                "title": line.get("title", ""),
                "variants": variants,
            })
        if not lines:
            return None
        result = {
            "type": "voice",
            "grouping": "voice_line",
            "entity_id": "",
            "entity_type": "",
            "page_size": 0,
            "total_lines": 0,
            "has_more": False,
            "next_cursor": None,
        }
        result.update({
            key: _plain(value)
            for key, value in panel.items()
            if key in {
                "type", "grouping", "entity_id", "entity_type", "page_size",
                "total_lines", "has_more", "next_cursor",
            }
        })
        result["lines"] = lines
        return result
    if panel_type == "video":
        items = [
            public_item
            for item in panel.get("items", ())
            if isinstance(item, Mapping)
            if (public_item := _media_to_public(item)) is not None
        ]
        if not items:
            return None
        return {
            "type": "video",
            "items": items,
        }
    return None


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


__all__ = [
    "SSEEvent",
    "response_packet_to_public_dict",
    "retrieval_packet_to_public_dict",
    "response_packet_to_sse_events",
    "response_packet_to_sse_strings",
]
