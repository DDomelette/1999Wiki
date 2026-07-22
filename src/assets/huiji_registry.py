"""Asset registry backed by Huiji RAG media assets."""
from __future__ import annotations

import hashlib
import json
import re
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Mapping

from src.assets.voice_pagination import (
    MAX_CURSOR_STATES,
    InvalidVoiceCursor,
    VoicePaginationIndex,
    derive_entity_scope,
    is_safe_browser_http_url,
)
from src.huiji_rag.build.contracts import validate_media_v3_row
from src.huiji_rag.io import iter_jsonl
from src.huiji_rag.runtime_artifacts import (
    RuntimeArtifactSnapshot,
    resolve_runtime_artifact_snapshot,
)
from src.rag.contracts import EntityRef
from src.rag.ownership import filter_owned_rows
from src.rag.packet_policy import compose_packet_policies
from src.rag.query_plan import requested_intents


MEDIA_INTENT_ASSET_TYPES = {
    "image": ("image", "psychube", "portrait", "skill", "ultimate"),
    "audio": ("voice",),
    "video": ("video",),
}

_INTENT_MEDIA_ROLES = {
    "item": frozenset(("collection_item",)),
    "udimo": frozenset(("udimo",)),
    "skill": frozenset(("skill",)),
    "voice": frozenset(("voice",)),
    "video": frozenset(("video",)),
}
_RELATION_SPECIFIC_INTENTS = frozenset(("item", "udimo"))
_COMPAT_MEDIA_ROLES = {
    "voice": "voice",
    "skill": "skill",
    "ultimate": "skill",
    "portrait": "portrait",
    "video": "video",
    "psychube": "psychube",
}
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")

VOICE_TEXT_LABELS = {
    "中文": "zh",
    "中": "zh",
    "EN": "en",
    "英文": "en",
    "日": "jp",
    "日文": "jp",
    "JP": "jp",
    "韩": "kr",
    "韓": "kr",
    "韩文": "kr",
    "韓文": "kr",
    "KR": "kr",
    "繁中": "zh-hant",
    "繁体": "zh-hant",
    "繁體": "zh-hant",
}

VOICE_TEXT_RE = re.compile(r"^\s*([^:：]{1,8})\s*[:：]\s*(.*)$")


@dataclass(frozen=True)
class MediaRetrievalBundle:
    items: tuple[dict[str, object], ...]
    panels: tuple[dict[str, object], ...]


@dataclass(frozen=True)
class _SourceBinding:
    entity_scope: str
    entity_type: str
    entity_id: str
    entity_name: str
    child_id: str
    parent_id: str


def _parse_voice_transcripts(text: str) -> dict[str, str]:
    transcripts: dict[str, list[str]] = {}
    current_language = ""
    for raw_line in str(text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = VOICE_TEXT_RE.match(line)
        if match:
            label = match.group(1).strip()
            language = VOICE_TEXT_LABELS.get(label)
            if language:
                current_language = language
                value = match.group(2).strip()
                transcripts.setdefault(language, [])
                if value:
                    transcripts[language].append(value)
                continue
        if current_language:
            transcripts.setdefault(current_language, []).append(line)
    return {
        language: re.sub(r"\s+", " ", " ".join(parts)).strip()
        for language, parts in transcripts.items()
        if parts
    }


def _owner_from_plan(plan: Any) -> EntityRef | None:
    entity_type = str(getattr(plan, "entity_type", None) or "").strip()
    entity_id = str(getattr(plan, "entity_id", None) or "").strip()
    entity_name = str(getattr(plan, "entity", None) or "").strip()
    if not (entity_type and entity_id and entity_name):
        return None
    return EntityRef(
        entity_type=entity_type,
        entity_id=entity_id,
        entity_name=entity_name,
        aliases=tuple(getattr(plan, "aliases", ()) or ()),
        resolution_mode=str(getattr(plan, "resolution_mode", "unresolved") or "unresolved"),
    )


def _canonical_owner_type(value: object) -> str:
    owner_type = str(value or "").strip().casefold()
    return {"char": "character", "role": "character"}.get(owner_type, owner_type)


def _owner_identity(value: object) -> tuple[str, str] | None:
    text = str(value or "").strip()
    if not text or ":" not in text:
        return None
    owner_type, owner_id = text.split(":", 1)
    if not owner_type or not owner_id:
        return None
    return _canonical_owner_type(owner_type), owner_id


def _row_matches_owner(row: Mapping[str, Any], owner: EntityRef) -> bool:
    """Match both scoped v3 ownership and the installed unscoped legacy ID."""
    expected = (_canonical_owner_type(owner.entity_type), str(owner.entity_id))
    scoped = _owner_identity(row.get("owner_entity_id"))
    if scoped is not None and scoped != expected:
        return False

    entity_id = str(row.get("entity_id") or "").strip()
    if not entity_id:
        return scoped == expected
    entity_scope = _owner_identity(entity_id)
    if entity_scope is not None:
        return entity_scope == expected
    return entity_id == expected[1]


def _compat_hash(parts: list[object]) -> str:
    payload = json.dumps(
        parts,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _compat_resource_id(row: Mapping[str, Any]) -> str:
    for field in ("content_sha256", "content_hash"):
        digest = str(row.get(field) or "").strip().casefold()
        if _SHA256_RE.fullmatch(digest):
            return f"resource:sha256:{digest}"
    digest = _compat_hash(
        [
            "evb.legacy-media-resource/v1",
            str(row.get("object_key") or ""),
            str(row.get("url") or ""),
            str(row.get("media_id") or ""),
            str(row.get("filename") or ""),
        ]
    )
    return f"resource:compat-sha256:{digest}"


def _compat_owner_entity_id(row: Mapping[str, Any]) -> str:
    current = str(row.get("owner_entity_id") or "").strip()
    if current:
        return current
    entity_id = str(row.get("entity_id") or "").strip()
    scoped = _owner_identity(entity_id)
    if scoped is not None:
        return f"{scoped[0]}:{scoped[1]}"
    declared_type = _canonical_owner_type(
        row.get("entity_type") or row.get("category") or "character"
    )
    return f"{declared_type}:{entity_id}" if entity_id else "legacy:unknown"


def _compat_section(row: Mapping[str, Any]) -> str:
    section = str(row.get("section") or row.get("section_kind") or "").strip()
    if section:
        return section
    parent_id = str(row.get("parent_id") or "")
    return parent_id.rsplit("/", 1)[-1] if "/" in parent_id else "media"


def _normalize_compat_media_row(
    source: Mapping[str, Any],
    capability: str,
) -> dict[str, Any]:
    row = dict(source)
    asset_type = str(row.get("asset_type") or "").strip()
    media_role = str(row.get("media_role") or "").strip()
    if not media_role:
        media_role = _COMPAT_MEDIA_ROLES.get(asset_type, asset_type or "media")

    resource_id = str(row.get("resource_id") or "").strip() or _compat_resource_id(row)
    owner_entity_id = _compat_owner_entity_id(row)
    owner_page_id = str(row.get("owner_page_id") or "").strip()
    if not owner_page_id:
        owner_page_id = str(row.get("parent_id") or owner_entity_id).split("/", 1)[0]
    section = _compat_section(row)
    source_binding_token = str(
        row.get("source_binding_token")
        or row.get("binding_key")
        or row.get("media_id")
        or row.get("object_key")
        or row.get("url")
        or row.get("filename")
        or "legacy-media"
    )
    binding_digest = _compat_hash(
        [
            "evb.legacy-media-binding/v1",
            capability,
            owner_entity_id,
            owner_page_id,
            str(row.get("parent_id") or ""),
            str(row.get("child_id") or ""),
            section,
            media_role,
            str(row.get("variant") or ""),
            str(row.get("skin_id") or ""),
            str(row.get("event_name") or ""),
            str(row.get("language") or ""),
            source_binding_token,
            resource_id,
        ]
    )
    row.update(
        {
            "binding_id": str(row.get("binding_id") or "")
            or f"binding:compat-sha256:{binding_digest}",
            "resource_id": resource_id,
            "owner_entity_id": owner_entity_id,
            "owner_page_id": owner_page_id,
            "section": section,
            "media_role": media_role,
            "source_binding_token": source_binding_token,
            "variant": str(row.get("variant") or ""),
            "skin_id": str(row.get("skin_id") or ""),
        }
    )
    return row


def _normalize_media_records(
    rows: list[dict[str, Any]],
    capability: str,
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    seen: dict[str, dict[str, Any]] = {}
    for source in rows:
        row = (
            validate_media_v3_row(dict(source))
            if capability == "v3"
            else _normalize_compat_media_row(source, capability)
        )
        binding_id = str(row.get("binding_id") or "")
        if not binding_id:
            raise ValueError("media binding identity is empty")
        previous = seen.get(binding_id)
        if previous is not None:
            if previous != row:
                raise ValueError(f"conflicting media binding payload: {binding_id}")
            continue
        seen[binding_id] = row
        normalized.append(row)
    return normalized


def _row_matches_media_semantics(
    row: Mapping[str, Any],
    intents: tuple[str, ...],
) -> bool:
    requested = {str(intent or "").strip() for intent in intents}
    desired_roles = {
        role
        for intent in requested
        for role in _INTENT_MEDIA_ROLES.get(intent, ())
    }
    role = str(row.get("media_role") or "").strip()

    # Collection and Udimo are explicit relationships. A generic portrait/image
    # is never an acceptable fallback when the installed schema lacks that link.
    if requested & _RELATION_SPECIFIC_INTENTS:
        return role in desired_roles
    if desired_roles and "media" not in requested:
        return role in desired_roles
    return True


class HuijiMediaRegistry:
    def __init__(
        self,
        cfg: Any,
        artifact_snapshot: RuntimeArtifactSnapshot | None = None,
    ) -> None:
        self.artifact_snapshot = artifact_snapshot or resolve_runtime_artifact_snapshot(cfg)
        raw_records = (
            list(iter_jsonl(self.artifact_snapshot.media_assets))
            if self.artifact_snapshot.media_assets.exists()
            else []
        )
        self._records = _normalize_media_records(
            raw_records,
            self.artifact_snapshot.capability,
        )
        self._voice_transcripts = self._load_voice_transcripts(
            self.artifact_snapshot.child_blocks
        )
        build_version = self.artifact_snapshot.build_version
        self._voice_index = VoicePaginationIndex(
            self._records,
            self._voice_transcripts,
            build_version=build_version,
        )
        self._voice_cursor_owners: OrderedDict[str, EntityRef] = OrderedDict()

    def _load_voice_transcripts(self, child_path: Any) -> dict[str, dict[str, str]]:
        if child_path is None or not child_path.exists():
            return {}
        transcripts: dict[str, dict[str, str]] = {}
        for row in iter_jsonl(child_path):
            if str(row.get("section_kind") or "") != "voice" and "/voice" not in str(row.get("parent_id") or ""):
                continue
            child_id = str(row.get("child_id") or "")
            if not child_id:
                continue
            parsed = _parse_voice_transcripts(str(row.get("text") or ""))
            if parsed:
                transcripts[child_id] = parsed
        return transcripts

    def find_for_retrieval(
        self,
        plan: Any,
        sources: list[dict[str, Any]],
        limit: int = 8,
    ) -> list[dict[str, Any]]:
        return list(self.find_bundle_for_retrieval(plan, sources, limit=limit).items)

    def find_bundle_for_retrieval(
        self,
        plan: Any,
        sources: list[dict[str, Any]],
        limit: int = 8,
        voice_page_size: int = 8,
    ) -> MediaRetrievalBundle:
        entity = getattr(plan, "entity", None)
        owner = _owner_from_plan(plan)
        media_intent = getattr(plan, "media_intent", "none")
        owned_sources, _ = filter_owned_rows(sources, owner, "media.sources")
        bindings = self._source_bindings(owned_sources, str(entity or ""), owner)
        bound_children = {binding.child_id for binding in bindings if binding.child_id}
        intents = self._requested_intents(plan)
        entity_type = owner.entity_type if owner else getattr(plan, "entity_type", None)
        policy_bundle = compose_packet_policies(
            entity_type,
            intents,
            self.artifact_snapshot.capability,
        )
        allowed_types = set(policy_bundle.media_types)
        allowed_types.update(MEDIA_INTENT_ASSET_TYPES.get(str(media_intent), ()))
        if "skill" in allowed_types:
            allowed_types.add("ultimate")

        scored: list[tuple[float, dict[str, Any]]] = []
        for row in self._records:
            if not row.get("is_available") or row.get("is_common"):
                continue
            if not is_safe_browser_http_url(row.get("url", "")):
                continue
            if entity and row.get("entity_name") != entity:
                continue
            if owner is not None and not _row_matches_owner(row, owner):
                continue
            asset_type = str(row.get("asset_type", ""))
            if asset_type not in allowed_types:
                continue
            if not _row_matches_media_semantics(row, intents):
                continue
            match = self._match_source_binding(row, bindings, bound_children, owner)
            if match is None:
                continue
            child_match, parent_match = match
            score = 0.0
            if child_match:
                score += 2.0
            if parent_match:
                score += 1.0
            if row.get("attach_policy") == "auto":
                score += 0.5
            scored.append((score, row))

        nonvoice = [item for item in scored if str(item[1].get("asset_type") or "") != "voice"]
        voice = [item for item in scored if str(item[1].get("asset_type") or "") == "voice"]
        nonvoice.sort(
            key=lambda item: (
                -item[0],
                int(item[1].get("sort_order", 0) or 0),
                str(item[1].get("binding_id") or ""),
            )
        )
        nonvoice_items = self._select_nonvoice_bindings(
            nonvoice,
            max(0, int(limit)),
            owner,
        )

        panels: list[dict[str, object]] = []
        voice_items: list[dict[str, object]] = []
        scopes = sorted(
            {
                (
                    scope,
                    str(row.get("parent_id") or ""),
                )
                for _score, row in voice
                if row.get("parent_id")
                and (
                    scope := derive_entity_scope(
                        row.get("entity_id"),
                        row.get("child_id"),
                        row.get("parent_id"),
                        row.get("entity_name"),
                    )
                )
            }
        )
        for entity_id, parent_id in scopes:
            page = self._voice_index.first_page(
                entity_id,
                parent_id,
                page_size=voice_page_size,
            )
            if not page.lines:
                continue
            panel = page.to_dict()
            if owner is not None:
                panel = self._normalize_voice_page(panel, owner)
            panels.append(panel)
            for line in panel["lines"]:
                voice_items.extend(dict(variant) for variant in line["variants"])

        items = self._dedupe_binding_ids([*nonvoice_items, *voice_items])
        return MediaRetrievalBundle(items=tuple(items), panels=tuple(panels))

    def get_voice_page(self, cursor: str) -> dict[str, object]:
        page = self._voice_index.get_page(cursor).to_dict()
        owner = self._voice_cursor_owners.get(str(cursor))
        if owner is None:
            return page
        self._voice_cursor_owners.move_to_end(str(cursor))
        for line in page.get("lines", []):
            for variant in line.get("variants", []):
                expected_scope = derive_entity_scope(
                    owner.entity_id,
                    variant.get("child_id"),
                    variant.get("parent_id"),
                    owner.entity_name,
                )
                if expected_scope != page.get("entity_id"):
                    raise InvalidVoiceCursor("voice cursor owner no longer matches the page scope")
        return self._normalize_voice_page(page, owner)

    def _normalize_voice_page(
        self,
        page: dict[str, object],
        owner: EntityRef,
    ) -> dict[str, object]:
        normalized = dict(page)
        normalized["entity_type"] = owner.entity_type
        normalized["entity_id"] = owner.entity_id
        normalized_lines: list[dict[str, object]] = []
        for raw_line in page.get("lines", []):
            line = dict(raw_line)
            variants: list[dict[str, object]] = []
            for raw_variant in raw_line.get("variants", []):
                variant = dict(raw_variant)
                variant["entity_type"] = owner.entity_type
                variant["entity_id"] = owner.entity_id
                variant["entity_name"] = owner.entity_name
                variants.append(variant)
            line["variants"] = variants
            normalized_lines.append(line)
        normalized["lines"] = normalized_lines
        cursor = str(normalized.get("next_cursor") or "")
        if cursor:
            self._voice_cursor_owners[cursor] = owner
            self._voice_cursor_owners.move_to_end(cursor)
            while len(self._voice_cursor_owners) > MAX_CURSOR_STATES:
                self._voice_cursor_owners.popitem(last=False)
        return normalized

    @staticmethod
    def _requested_intents(plan: Any) -> tuple[str, ...]:
        if hasattr(plan, "secondary_intents"):
            return requested_intents(plan)
        intent = str(getattr(plan, "intent", "intro") or "intro")
        return (intent,)

    @staticmethod
    def _source_bindings(
        sources: list[dict[str, Any]],
        plan_entity: str,
        owner: EntityRef | None = None,
    ) -> tuple[_SourceBinding, ...]:
        bindings: list[_SourceBinding] = []
        for source in sources:
            entity_name = str(source.get("entity_name") or plan_entity or "")
            scope = derive_entity_scope(
                source.get("entity_id"),
                source.get("child_id"),
                source.get("parent_id"),
                entity_name,
            )
            if scope is None:
                continue
            bindings.append(
                _SourceBinding(
                    entity_scope=scope,
                    entity_type=(
                        owner.entity_type
                        if owner
                        else str(source.get("entity_type") or "")
                    ),
                    entity_id=(
                        owner.entity_id
                        if owner
                        else str(source.get("entity_id") or "")
                    ),
                    entity_name=entity_name,
                    child_id=str(source.get("child_id") or ""),
                    parent_id=str(source.get("parent_id") or ""),
                )
            )
        return tuple(bindings)

    @staticmethod
    def _match_source_binding(
        row: dict[str, Any],
        bindings: tuple[_SourceBinding, ...],
        bound_children: set[str],
        owner: EntityRef | None = None,
    ) -> tuple[bool, bool] | None:
        row_child = str(row.get("child_id") or "")
        row_parent = str(row.get("parent_id") or "")
        row_name = str(row.get("entity_name") or "")
        row_scope = derive_entity_scope(
            row.get("entity_id"),
            row_child,
            row_parent,
        )
        if row_scope is None:
            return None
        if owner is not None and not _row_matches_owner(row, owner):
            return None

        if row_child in bound_children:
            candidates = tuple(
                binding
                for binding in bindings
                if binding.child_id == row_child
                and (not binding.parent_id or binding.parent_id == row_parent)
            )
        else:
            candidates = tuple(
                binding
                for binding in bindings
                if binding.parent_id and binding.parent_id == row_parent
            )

        for binding in candidates:
            if row_scope and binding.entity_scope and row_scope != binding.entity_scope:
                continue
            if owner is not None and (
                binding.entity_type != owner.entity_type
                or binding.entity_id != owner.entity_id
            ):
                continue
            if row_name and binding.entity_name and row_name != binding.entity_name:
                continue
            return binding.child_id == row_child, binding.parent_id == row_parent
        return None

    @staticmethod
    def _select_nonvoice_bindings(
        scored: list[tuple[float, dict[str, Any]]],
        limit: int,
        owner: EntityRef | None = None,
    ) -> list[dict[str, object]]:
        if limit <= 0:
            return []
        selected: list[dict[str, Any]] = []
        seen_binding_ids: set[str] = set()
        for _score, row in scored:
            binding_id = str(row.get("binding_id") or "")
            if not binding_id or binding_id in seen_binding_ids:
                continue
            seen_binding_ids.add(binding_id)
            title = str(row.get("title") or row.get("filename") or "")
            selected.append(
                {
                    "binding_id": binding_id,
                    "resource_id": str(row.get("resource_id", "")),
                    "media_id": str(row.get("media_id", "")),
                    "asset_id": binding_id,
                    "asset_type": str(row.get("asset_type", "")),
                    "media_role": str(row.get("media_role", "")),
                    "mime": str(row.get("mime", "")),
                    "url": str(row.get("url", "")),
                    "child_id": str(row.get("child_id", "")),
                    "parent_id": str(row.get("parent_id", "")),
                    "section": str(row.get("section", "")),
                    "source_binding_token": str(row.get("source_binding_token", "")),
                    "owner_entity_id": str(row.get("owner_entity_id", "")),
                    "owner_page_id": str(row.get("owner_page_id", "")),
                    "variant": str(row.get("variant", "")),
                    "skin_id": str(row.get("skin_id", "")),
                    "entity_id": owner.entity_id if owner else str(row.get("entity_id", "")),
                    "entity_type": owner.entity_type if owner else str(row.get("entity_type", "")),
                    "entity_name": str(row.get("entity_name", "")),
                    "title": title,
                    "alt": title,
                    "role": str(row.get("asset_type", "")),
                    "attach_policy": str(row.get("attach_policy", "")),
                    "panel_group": str(row.get("panel_group", "")),
                    "sort_order": int(row.get("sort_order", 0) or 0),
                    "duration_ms": int(row.get("duration_ms", 0) or 0),
                    "language": str(row.get("language") or ""),
                }
            )
            if len(selected) >= limit:
                break
        return selected

    @staticmethod
    def _dedupe_binding_ids(items: list[dict[str, object]]) -> list[dict[str, object]]:
        deduped: list[dict[str, object]] = []
        seen: set[str] = set()
        for item in items:
            binding_id = str(item.get("binding_id") or item.get("asset_id") or "")
            if not binding_id or binding_id in seen:
                continue
            seen.add(binding_id)
            deduped.append(item)
        return deduped
