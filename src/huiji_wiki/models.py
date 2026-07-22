"""Serializable wiki view models."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


SAFE_MEDIA_FIELD_ORDER = (
    "bindingId",
    "resourceId",
    "mediaId",
    "assetId",
    "assetType",
    "mime",
    "url",
    "title",
    "alt",
    "role",
    "sectionKey",
    "displayOrder",
    "sha1",
    "width",
    "height",
    "variant",
    "attachPolicy",
    "childId",
    "parentId",
    "panelGroup",
    "sortOrder",
    "durationMs",
    "ownerEntityId",
    "ownerPageId",
    "skinId",
    "eventName",
    "language",
    "sourceBindingToken",
    "bindingStatus",
)


def _camel(row: dict[str, Any]) -> dict[str, Any]:
    mapping = {
        "page_id": "pageId",
        "page_type": "pageType",
        "source_pageid": "sourcePageid",
        "source_title": "sourceTitle",
        "content_json": "content",
        "template_group": "templateGroup",
        "animation_profile": "animationProfile",
        "theme_token": "themeToken",
        "section_key": "sectionKey",
        "media_id": "mediaId",
        "binding_id": "bindingId",
        "resource_id": "resourceId",
        "media_role": "mediaRole",
        "display_order": "displayOrder",
        "fallback_media_id": "fallbackMediaId",
        "object_key": "objectKey",
        "asset_type": "assetType",
        "from_page_id": "fromPageId",
        "to_page_id": "toPageId",
        "relation_type": "relationType",
        "alias_type": "aliasType",
        "target_route": "targetRoute",
        "asset_id": "assetId",
        "attach_policy": "attachPolicy",
        "child_id": "childId",
        "parent_id": "parentId",
        "panel_group": "panelGroup",
        "sort_order": "sortOrder",
        "duration_ms": "durationMs",
        "owner_entity_id": "ownerEntityId",
        "owner_page_id": "ownerPageId",
        "skin_id": "skinId",
        "event_name": "eventName",
        "source_binding_token": "sourceBindingToken",
        "binding_status": "bindingStatus",
    }
    return {mapping.get(key, key): value for key, value in row.items()}


def is_public_media_url(url: str) -> bool:
    return url.startswith(("http://", "https://"))


def _first_value(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return ""


def sanitize_media_item(row: dict[str, Any]) -> dict[str, Any] | None:
    url = str(_first_value(row, "url"))
    if not is_public_media_url(url):
        return None

    media_id = str(_first_value(row, "mediaId", "media_id", "assetId", "asset_id"))
    asset_id = str(_first_value(row, "assetId", "asset_id", "mediaId", "media_id"))
    asset_type = str(_first_value(row, "assetType", "asset_type", "role", "mediaRole", "media_role"))
    title = str(_first_value(row, "title", "alt"))
    role = str(_first_value(row, "role", "mediaRole", "media_role", "assetType", "asset_type"))
    alt = str(_first_value(row, "alt", "title"))

    payload: dict[str, Any] = {
        "bindingId": _first_value(row, "bindingId", "binding_id"),
        "resourceId": _first_value(row, "resourceId", "resource_id"),
        "mediaId": media_id,
        "assetId": asset_id,
        "assetType": asset_type,
        "mime": str(_first_value(row, "mime")),
        "url": url,
        "title": title,
        "alt": alt,
        "role": role,
        "sectionKey": _first_value(row, "sectionKey", "section_key"),
        "displayOrder": _first_value(row, "displayOrder", "display_order"),
        "sha1": _first_value(row, "sha1"),
        "width": _first_value(row, "width"),
        "height": _first_value(row, "height"),
        "variant": _first_value(row, "variant"),
        "attachPolicy": _first_value(row, "attachPolicy", "attach_policy"),
        "childId": _first_value(row, "childId", "child_id"),
        "parentId": _first_value(row, "parentId", "parent_id"),
        "panelGroup": _first_value(row, "panelGroup", "panel_group"),
        "sortOrder": _first_value(row, "sortOrder", "sort_order"),
        "durationMs": _first_value(row, "durationMs", "duration_ms"),
        "ownerEntityId": _first_value(row, "ownerEntityId", "owner_entity_id"),
        "ownerPageId": _first_value(row, "ownerPageId", "owner_page_id"),
        "skinId": _first_value(row, "skinId", "skin_id"),
        "eventName": _first_value(row, "eventName", "event_name"),
        "language": _first_value(row, "language"),
        "sourceBindingToken": _first_value(row, "sourceBindingToken", "source_binding_token"),
        "bindingStatus": _first_value(row, "bindingStatus", "binding_status"),
    }
    return {key: payload[key] for key in SAFE_MEDIA_FIELD_ORDER if payload.get(key) not in (None, "")}


@dataclass(frozen=True)
class WikiPage:
    page_id: str
    page_type: str
    title: str
    subtitle: str
    category: str
    route: str
    source_pageid: int | None = None
    source_title: str = ""
    content_json: dict[str, Any] | None = None
    updated_at: str = ""

    def to_json(self) -> dict[str, Any]:
        return asdict(self)

    def to_api(self) -> dict[str, Any]:
        return _camel(self.to_json())

    @classmethod
    def from_json(cls, row: dict[str, Any]) -> "WikiPage":
        return cls(
            page_id=str(row.get("page_id")),
            page_type=str(row.get("page_type", "generic")),
            title=str(row.get("title", "")),
            subtitle=str(row.get("subtitle", "")),
            category=str(row.get("category", "")),
            route=str(row.get("route", "")),
            source_pageid=row.get("source_pageid"),
            source_title=str(row.get("source_title", "")),
            content_json=dict(row.get("content_json") or {}),
            updated_at=str(row.get("updated_at", "")),
        )


@dataclass(frozen=True)
class WikiCategory:
    key: str
    label: str
    count: int
    template_group: str = ""
    animation_profile: str = ""
    theme_token: str = ""

    def to_json(self) -> dict[str, Any]:
        return _camel(asdict(self))


@dataclass(frozen=True)
class WikiMediaLink:
    page_id: str
    section_key: str
    media_id: str
    media_role: str
    display_order: int
    fallback_media_id: str = ""
    object_key: str = ""
    url: str = ""
    asset_type: str = ""
    mime: str = ""
    title: str = ""
    sha1: str = ""
    width: int = 0
    height: int = 0
    variant: str = ""
    binding_id: str = ""
    resource_id: str = ""
    attach_policy: str = ""
    child_id: str = ""
    parent_id: str = ""
    panel_group: str = ""
    sort_order: int = 0
    duration_ms: int = 0
    owner_entity_id: str = ""
    owner_page_id: str = ""
    skin_id: str = ""
    event_name: str = ""
    language: str = ""
    source_binding_token: str = ""
    binding_status: str = ""

    def to_json(self) -> dict[str, Any]:
        return asdict(self)

    def to_api(self) -> dict[str, Any]:
        payload = {
            "binding_id": self.binding_id,
            "resource_id": self.resource_id,
            "media_id": self.media_id,
            "asset_id": self.media_id,
            "asset_type": self.asset_type,
            "mime": self.mime,
            "url": self.url,
            "title": self.title,
            "alt": self.title,
            "role": self.media_role or self.asset_type,
            "section_key": self.section_key,
            "display_order": self.display_order,
            "sha1": self.sha1,
            "width": self.width,
            "height": self.height,
            "variant": self.variant,
            "attach_policy": self.attach_policy,
            "child_id": self.child_id,
            "parent_id": self.parent_id,
            "panel_group": self.panel_group,
            "sort_order": self.sort_order if self.sort_order > 0 else "",
            "duration_ms": self.duration_ms if self.duration_ms > 0 else "",
            "owner_entity_id": self.owner_entity_id,
            "owner_page_id": self.owner_page_id,
            "skin_id": self.skin_id,
            "event_name": self.event_name,
            "language": self.language,
            "source_binding_token": self.source_binding_token,
            "binding_status": self.binding_status,
        }
        return sanitize_media_item(payload) or {}

    @classmethod
    def from_json(cls, row: dict[str, Any]) -> "WikiMediaLink":
        return cls(
            page_id=str(row.get("page_id", "")),
            section_key=str(row.get("section_key", "")),
            media_id=str(row.get("media_id", "")),
            media_role=str(row.get("media_role", "")),
            display_order=int(row.get("display_order", 0) or 0),
            fallback_media_id=str(row.get("fallback_media_id", "")),
            object_key=str(row.get("object_key", "")),
            url=str(row.get("url", "")),
            asset_type=str(row.get("asset_type", "")),
            mime=str(row.get("mime", "")),
            title=str(row.get("title", "")),
            sha1=str(row.get("sha1", "")),
            width=int(row.get("width", 0) or 0),
            height=int(row.get("height", 0) or 0),
            variant=str(row.get("variant", "")),
            binding_id=str(row.get("binding_id", "")),
            resource_id=str(row.get("resource_id", "")),
            attach_policy=str(row.get("attach_policy", "")),
            child_id=str(row.get("child_id", "")),
            parent_id=str(row.get("parent_id", "")),
            panel_group=str(row.get("panel_group", "")),
            sort_order=int(row.get("sort_order", 0) or 0),
            duration_ms=int(row.get("duration_ms", 0) or 0),
            owner_entity_id=str(row.get("owner_entity_id", "")),
            owner_page_id=str(row.get("owner_page_id", "")),
            skin_id=str(row.get("skin_id", "")),
            event_name=str(row.get("event_name", "")),
            language=str(row.get("language", "")),
            source_binding_token=str(row.get("source_binding_token", "")),
            binding_status=str(row.get("binding_status", "")),
        )


@dataclass(frozen=True)
class WikiRelation:
    from_page_id: str
    to_page_id: str
    relation_type: str
    label: str
    confidence: float

    def to_json(self) -> dict[str, Any]:
        return _camel(asdict(self))


@dataclass(frozen=True)
class WikiAlias:
    page_id: str
    alias: str
    alias_type: str
    priority: int

    def to_json(self) -> dict[str, Any]:
        return _camel(asdict(self))


@dataclass(frozen=True)
class WikiLinkSpan:
    page_id: str
    section_key: str
    text: str
    target_route: str
    confidence: float

    def to_json(self) -> dict[str, Any]:
        return _camel(asdict(self))
