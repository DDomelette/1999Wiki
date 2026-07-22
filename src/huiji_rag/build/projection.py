"""Deterministic crawler-only projection into canonical RAG semantics."""
from __future__ import annotations

import base64
import hashlib
import json
import re
from collections import Counter, OrderedDict
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Sequence

from src.huiji_rag.models import ChildBlock, ParentBlock, VoiceSourceRow
from src.huiji_rag.text import clean_huiji_text, compact_lines

from .contracts import canonical_json_bytes


_CHAR_TITLE_RE = re.compile(r"Data:Char/[^/]+\.json\Z")
_SAFE_TOKEN_RE = re.compile(r"[A-Za-z0-9_-]+\Z")
_PLACEHOLDER_NAMES = frozenset({"???", "？??", "？？？"})
_VOICE_FIELDS = (
    ("content", "zh", "中文"),
    ("encontent", "en", "EN"),
    ("twcontent", "zh-hant", "繁中"),
    ("jpcontent", "jp", "日"),
    ("kocontent", "kr", "韩"),
)
_SECTION_LABELS = {
    "profile": "基础资料",
    "dossier": "档案",
    "collection": "藏品",
    "skills": "技能",
    "culture_dossier": "文化档案",
    "udimo": "尤提姆",
    "voice": "语音",
    "media": "媒体",
}
_SECTION_ORDER = (
    "profile",
    "dossier",
    "collection",
    "skills",
    "culture_dossier",
    "udimo",
    "voice",
    "media",
)
_LEGACY_SECTION = {
    "collection": "culture",
    "culture_dossier": "items",
}
_GENERIC_MARKERS = ("psychube", "equip", "item", "episode", "story")


@dataclass(frozen=True)
class SemanticChild:
    """A child block plus source-stable business identity fields."""

    block: ChildBlock
    stable_source_token: str
    source_token_kind: str
    owner_entity_id: str
    owner_page_id: str
    ordinal: int = 0
    name_en: str = ""
    valuation: str = ""
    description: str = ""
    media_binding_tokens: tuple[str, ...] = ()
    source_fields: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "media_binding_tokens", tuple(self.media_binding_tokens))
        object.__setattr__(self, "source_fields", MappingProxyType(dict(self.source_fields)))

    def to_json(self) -> dict[str, Any]:
        row = self.block.to_json()
        row.update(
            {
                "stable_source_token": self.stable_source_token,
                "source_token_kind": self.source_token_kind,
                "owner_entity_id": self.owner_entity_id,
                "owner_page_id": self.owner_page_id,
                "ordinal": self.ordinal,
                "name_en": self.name_en,
                "valuation": self.valuation,
                "description": self.description,
                "media_binding_tokens": list(self.media_binding_tokens),
                "source_fields": dict(self.source_fields),
            }
        )
        return row


@dataclass(frozen=True)
class MediaBindingIntent:
    """A source-proven media relation awaiting resource resolution."""

    source_binding_token: str
    owner_entity_id: str
    owner_page_id: str
    parent_id: str
    child_id: str
    section: str
    media_role: str
    resource_stem: str
    title: str
    variant: str = ""
    skin_id: str = ""
    event_name: str = ""
    language: str = ""
    sort_order: int = 0
    source_refs: tuple[dict[str, Any], ...] = ()
    missing_policy: str = "text_only"

    def to_json(self) -> dict[str, Any]:
        return {
            "source_binding_token": self.source_binding_token,
            "owner_entity_id": self.owner_entity_id,
            "owner_page_id": self.owner_page_id,
            "parent_id": self.parent_id,
            "child_id": self.child_id,
            "section": self.section,
            "media_role": self.media_role,
            "resource_stem": self.resource_stem,
            "title": self.title,
            "variant": self.variant,
            "skin_id": self.skin_id,
            "event_name": self.event_name,
            "language": self.language,
            "sort_order": self.sort_order,
            "source_refs": [dict(item) for item in self.source_refs],
            "missing_policy": self.missing_policy,
        }


@dataclass(frozen=True)
class ProjectionExclusion:
    reason_code: str
    source_title: str
    source_identity: str
    source_content_sha256: str
    entity_id: str = ""
    entity_name: str = ""
    json_path: str = "$"
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "details", MappingProxyType(dict(self.details)))

    def to_json(self) -> dict[str, Any]:
        return {
            "reason_code": self.reason_code,
            "source_title": self.source_title,
            "source_identity": self.source_identity,
            "source_content_sha256": self.source_content_sha256,
            "entity_id": self.entity_id,
            "entity_name": self.entity_name,
            "json_path": self.json_path,
            "details": dict(self.details),
        }


@dataclass(frozen=True)
class IdentityFallback:
    owner_page_id: str
    canonical_section: str
    json_path: str
    source_identity_sha256: str
    stable_source_token: str
    reason_code: str = "stable_source_id_missing"

    def to_json(self) -> dict[str, str]:
        return {
            "owner_page_id": self.owner_page_id,
            "canonical_section": self.canonical_section,
            "json_path": self.json_path,
            "source_identity_sha256": self.source_identity_sha256,
            "stable_source_token": self.stable_source_token,
            "reason_code": self.reason_code,
        }


@dataclass(frozen=True)
class SemanticRecordLink:
    record_kind: str
    legacy_id: str
    candidate_id: str
    change_kind: str
    source_title: str
    source_content_sha256: str
    json_path: str
    legacy_section: str
    candidate_section: str

    def to_json(self) -> dict[str, str]:
        return {
            "record_kind": self.record_kind,
            "legacy_id": self.legacy_id,
            "candidate_id": self.candidate_id,
            "change_kind": self.change_kind,
            "source_title": self.source_title,
            "source_content_sha256": self.source_content_sha256,
            "json_path": self.json_path,
            "legacy_section": self.legacy_section,
            "candidate_section": self.candidate_section,
        }


@dataclass(frozen=True)
class CorpusProjection:
    parents: tuple[ParentBlock, ...]
    children: tuple[SemanticChild, ...]
    voice_sources: tuple[VoiceSourceRow, ...]
    media_intents: tuple[MediaBindingIntent, ...]
    exclusions: tuple[ProjectionExclusion, ...]
    identity_fallbacks: tuple[IdentityFallback, ...]
    record_links: tuple[SemanticRecordLink, ...]

    @property
    def parent_rows(self) -> tuple[dict[str, Any], ...]:
        return tuple(item.to_json() for item in self.parents)

    @property
    def child_rows(self) -> tuple[dict[str, Any], ...]:
        return tuple(item.to_json() for item in self.children)


@dataclass
class _ProjectionAccumulator:
    parents: list[ParentBlock] = field(default_factory=list)
    children: list[SemanticChild] = field(default_factory=list)
    voice_sources: list[VoiceSourceRow] = field(default_factory=list)
    media_intents: list[MediaBindingIntent] = field(default_factory=list)
    exclusions: list[ProjectionExclusion] = field(default_factory=list)
    identity_fallbacks: list[IdentityFallback] = field(default_factory=list)
    record_links: list[SemanticRecordLink] = field(default_factory=list)


def project_crawler_semantics(rows: Iterable[Mapping[str, Any]]) -> CorpusProjection:
    """Project supported records without consulting active artifacts or business stores."""
    selected: list[dict[str, Any]] = []
    for candidate in rows:
        title = str(candidate.get("title") or "")
        is_character_source = title == "Data:Char/map.json" or bool(
            _CHAR_TITLE_RE.fullmatch(title)
        )
        is_supported_generic = not title.startswith("Data:Char/") and any(
            marker in title.casefold() for marker in _GENERIC_MARKERS
        )
        if is_character_source or is_supported_generic:
            selected.append(dict(candidate))
    source_rows = tuple(selected)
    aliases = _alias_map(source_rows)
    udimo = _udimo_owner_index(source_rows)
    result = _ProjectionAccumulator()

    for row in source_rows:
        title = str(row.get("title") or "")
        if not _CHAR_TITLE_RE.fullmatch(title) or title == "Data:Char/map.json":
            continue
        payload = _payload_object(row)
        if payload is None:
            result.exclusions.append(_exclusion(row, "invalid_character_json"))
            continue
        excluded = _character_exclusion(row, payload)
        if excluded is not None:
            result.exclusions.append(excluded)
            _extract_voice_sources(row, payload, result)
            continue
        entity_id = str(payload.get("id") or "").strip()
        _project_character(
            row,
            payload,
            aliases.get(entity_id, ()),
            udimo.get(_normal_name(payload.get("name"))),
            result,
        )

    for row in source_rows:
        title = str(row.get("title") or "")
        if title.startswith("Data:Char/"):
            continue
        if not any(marker in title.casefold() for marker in _GENERIC_MARKERS):
            continue
        _project_generic(row, result)

    _assert_unique_ids(result.parents, result.children)
    return CorpusProjection(
        parents=tuple(result.parents),
        children=tuple(result.children),
        voice_sources=tuple(sorted(result.voice_sources, key=lambda item: item.source_id)),
        media_intents=tuple(result.media_intents),
        exclusions=tuple(result.exclusions),
        identity_fallbacks=tuple(result.identity_fallbacks),
        record_links=tuple(result.record_links),
    )


def _project_character(
    row: Mapping[str, Any],
    payload: Mapping[str, Any],
    aliases: tuple[str, ...],
    udimo: tuple[Mapping[str, Any], Mapping[str, Any]] | None,
    result: _ProjectionAccumulator,
) -> None:
    entity_id = str(payload.get("id") or "").strip()
    entity_name = clean_huiji_text(payload.get("name"))
    owner_page_id = f"char:{entity_id}"
    source_ref = _source_ref(row, "$")
    alias_text = " ".join(aliases)
    children_by_section: dict[str, list[SemanticChild]] = {
        section: [] for section in _SECTION_ORDER
    }
    ordered_children: list[SemanticChild] = []

    profile_parent = f"{owner_page_id}/profile"
    profile_child_id = f"{profile_parent}/root"
    profile_text = "\n".join(
        part
        for part in (
            f"{entity_name} 角色资料",
            f"稀有度: {payload.get('rare', '')}",
            f"职业: {payload.get('career', '')}",
            f"伤害类型: {payload.get('dmgType', '')}",
            f"别名: {alias_text}" if alias_text else "",
        )
        if part
    )
    profile_title = f"{entity_name} / 基础资料"
    profile = _semantic_child(
        child_id=profile_child_id,
        parent_id=profile_parent,
        entity_id=entity_id,
        entity_name=entity_name,
        section_kind="profile",
        title=profile_title,
        text=profile_text,
        search_parts=(entity_name, alias_text, "基础资料", profile_title, profile_text, profile_child_id),
        chunk_index=0,
        source_refs=(source_ref,),
        route_tags=("intro", "profile_fact", "media"),
        stable_source_token="root",
        source_token_kind="canonical_singleton",
        owner_page_id=owner_page_id,
    )
    children_by_section["profile"].append(profile)
    ordered_children.append(profile)
    result.record_links.append(
        _record_link(row, "child", f"{owner_page_id}/profile:0000", profile_child_id, "profile", "profile")
    )

    section_indexes = {"dossier": 0, "collection": 0, "culture_dossier": 0}
    for raw_index, item in enumerate(_dict_rows(payload.get("character_data"))):
        raw_type = str(item.get("type") or "")
        section = {"1": "dossier", "2": "collection", "3": "culture_dossier"}.get(raw_type)
        json_path = f"$.character_data.{raw_index}"
        if section is None:
            result.exclusions.append(
                _exclusion(
                    row,
                    "unsupported_character_data_type",
                    entity_id=entity_id,
                    entity_name=entity_name,
                    json_path=json_path,
                    details={"type": raw_type},
                )
            )
            continue
        title = clean_huiji_text(item.get("title"))
        body = clean_huiji_text(item.get("text") or item.get("content") or item.get("desc"))
        text = "\n".join(part for part in (title, body) if part)
        if not text:
            result.exclusions.append(
                _exclusion(
                    row,
                    "empty_section_text",
                    entity_id=entity_id,
                    entity_name=entity_name,
                    json_path=json_path,
                    details={"section": section},
                )
            )
            continue
        token, token_kind = _stable_source_token(
            item.get("id"), row, owner_page_id, section, json_path, item, result
        )
        parent_id = f"{owner_page_id}/{section}"
        child_id = f"{parent_id}/{token}"
        display_title = title or "条目"
        raw_section_index = section_indexes[section]
        section_indexes[section] += 1
        keyword = {
            "dossier": "档案",
            "collection": "藏品 单品 收藏品",
            "culture_dossier": "文化 文化档案",
        }[section]
        route_tags = {
            "dossier": ("intro", "dossier"),
            "collection": ("intro", "item", "collection"),
            "culture_dossier": ("intro", "culture", "culture_dossier"),
        }[section]
        binding_tokens: tuple[str, ...] = ()
        if section == "collection":
            binding_token = f"collection:{token}:{str(item.get('icon') or '')}"
            binding_tokens = (binding_token,)
            result.media_intents.append(
                MediaBindingIntent(
                    source_binding_token=binding_token,
                    owner_entity_id=f"character:{entity_id}",
                    owner_page_id=owner_page_id,
                    parent_id=parent_id,
                    child_id=child_id,
                    section=section,
                    media_role="collection_item",
                    resource_stem=(
                        f"Belonging-{item.get('icon')}" if str(item.get("icon") or "") else ""
                    ),
                    title=display_title,
                    variant=str(item.get("skinId") or ""),
                    skin_id=str(item.get("skinId") or ""),
                    sort_order=raw_index,
                    source_refs=(_source_ref(row, json_path),),
                )
            )
        child = _semantic_child(
            child_id=child_id,
            parent_id=parent_id,
            entity_id=entity_id,
            entity_name=entity_name,
            section_kind=section,
            title=display_title,
            text=text,
            search_parts=(entity_name, alias_text, keyword, display_title, text, child_id),
            chunk_index=raw_section_index,
            source_refs=(_source_ref(row, json_path),),
            route_tags=route_tags,
            stable_source_token=token,
            source_token_kind=token_kind,
            owner_page_id=owner_page_id,
            ordinal=_as_nonnegative_int(item.get("number") or item.get("id")),
            name_en=clean_huiji_text(item.get("titleEn")),
            valuation=clean_huiji_text(item.get("estimate")),
            description=body,
            media_binding_tokens=binding_tokens,
            source_fields={
                "raw_type": raw_type,
                "raw_id": str(item.get("id") or ""),
                "icon": str(item.get("icon") or ""),
                "skin_id": str(item.get("skinId") or ""),
            },
        )
        children_by_section[section].append(child)
        ordered_children.append(child)
        legacy_section = {"dossier": "dossier", "collection": "culture", "culture_dossier": "item"}[section]
        legacy_parent = {
            "dossier": f"{owner_page_id}/dossier",
            "collection": f"{owner_page_id}/culture",
            "culture_dossier": f"{owner_page_id}/items",
        }[section]
        legacy_child = f"{owner_page_id}/{legacy_section}:{raw_index:04d}"
        result.record_links.append(
            _record_link(row, "child", legacy_child, child_id, legacy_section, section, json_path=json_path)
        )

    if udimo is not None:
        item_row, item = udimo
        _project_udimo(
            item_row,
            item,
            entity_id=entity_id,
            entity_name=entity_name,
            owner_page_id=owner_page_id,
            alias_text=alias_text,
            children_by_section=children_by_section,
            ordered_children=ordered_children,
            result=result,
        )

    _project_voices(
        row,
        _dict_rows(payload.get("character_voice")),
        entity_id=entity_id,
        entity_name=entity_name,
        alias_text=alias_text,
        owner_page_id=owner_page_id,
        children_by_section=children_by_section,
        ordered_children=ordered_children,
        result=result,
    )

    _project_skills(
        row,
        payload,
        entity_id=entity_id,
        entity_name=entity_name,
        alias_text=alias_text,
        owner_page_id=owner_page_id,
        children_by_section=children_by_section,
        ordered_children=ordered_children,
        result=result,
    )
    _project_skin_media_intents(
        row,
        payload,
        entity_id=entity_id,
        entity_name=entity_name,
        owner_page_id=owner_page_id,
        profile_child_id=profile_child_id,
        result=result,
    )

    section_parents: dict[str, ParentBlock] = {}
    for section in _SECTION_ORDER:
        members = children_by_section[section]
        if not members:
            continue
        summary = _legacy_short_summary(
            "\n".join(item.block.text for item in members), max_chars=800
        )
        parent_id = f"{owner_page_id}/{section}"
        label = _SECTION_LABELS[section]
        parent = ParentBlock(
            parent_id=parent_id,
            entity_id=entity_id,
            entity_name=entity_name,
            entity_aliases=aliases,
            category="character",
            section_kind=section,
            title=f"{entity_name} / {label}",
            summary_text=summary,
            source_refs=_merged_source_refs(members),
            child_ids=tuple(item.block.child_id for item in members),
            content_hash=_parent_hash(summary, tuple(item.block.child_id for item in members)),
            entity_type="character",
            depth_level=1,
            ancestor_ids=(owner_page_id,),
            quality_flags=quality_flags_for_text(summary, entity_name),
            omitted_action_label=label,
        )
        section_parents[section] = parent
        legacy_section = _LEGACY_SECTION.get(section, section)
        legacy_parent_id = "" if section == "udimo" else f"{owner_page_id}/{legacy_section}"
        result.record_links.append(
            _record_link(
                row,
                "parent",
                legacy_parent_id,
                parent_id,
                legacy_section if legacy_parent_id else "",
                section,
                change_kind="new_source_record" if not legacy_parent_id else None,
            )
        )

    summary_parts = [
        f"{_SECTION_LABELS[section]}: {section_parents[section].summary_text}"
        for section in _SECTION_ORDER
        if section in section_parents
    ]
    root_summary = _legacy_short_summary("\n".join(summary_parts), max_chars=1200)
    root_child_ids = tuple(item.block.child_id for item in ordered_children)
    root = ParentBlock(
        parent_id=owner_page_id,
        entity_id=entity_id,
        entity_name=entity_name,
        entity_aliases=aliases,
        category="character",
        section_kind="entity",
        title=entity_name,
        summary_text=root_summary,
        source_refs=_merged_source_refs(ordered_children),
        child_ids=root_child_ids,
        content_hash=_parent_hash(root_summary, root_child_ids),
        entity_type="character",
        depth_level=1,
        ancestor_ids=(),
        quality_flags=quality_flags_for_text(root_summary, entity_name),
        omitted_action_label="entity",
    )
    result.parents.append(root)
    result.parents.extend(section_parents[section] for section in _SECTION_ORDER if section in section_parents)
    result.children.extend(ordered_children)
    result.record_links.append(
        _record_link(row, "parent", owner_page_id, owner_page_id, "entity", "entity")
    )


def _project_udimo(
    row: Mapping[str, Any],
    item: Mapping[str, Any],
    *,
    entity_id: str,
    entity_name: str,
    owner_page_id: str,
    alias_text: str,
    children_by_section: dict[str, list[SemanticChild]],
    ordered_children: list[SemanticChild],
    result: _ProjectionAccumulator,
) -> None:
    section = "udimo"
    json_path = "$"
    token, token_kind = _stable_source_token(
        item.get("id"), row, owner_page_id, section, json_path, item, result
    )
    parent_id = f"{owner_page_id}/{section}"
    child_id = f"{parent_id}/{token}"
    title = clean_huiji_text(item.get("name")) or "尤提姆"
    description = clean_huiji_text(
        item.get("desc") or item.get("description") or item.get("useDesc")
    )
    text = "\n".join(part for part in (title, description) if part)
    binding_token = f"udimo:{token}:{str(item.get('icon') or '')}"
    child = _semantic_child(
        child_id=child_id,
        parent_id=parent_id,
        entity_id=entity_id,
        entity_name=entity_name,
        section_kind=section,
        title=title,
        text=text,
        search_parts=(entity_name, alias_text, "尤提姆 Udimo", title, text, child_id),
        chunk_index=0,
        source_refs=(_source_ref(row, "$"),),
        route_tags=("udimo",),
        stable_source_token=token,
        source_token_kind=token_kind,
        owner_page_id=owner_page_id,
        description=description,
        media_binding_tokens=(binding_token,),
        source_fields={
            "relation_kind": "structured_item_name_owner",
            "raw_id": str(item.get("id") or ""),
            "icon": str(item.get("icon") or ""),
        },
    )
    children_by_section[section].append(child)
    ordered_children.append(child)
    result.media_intents.append(
        MediaBindingIntent(
            source_binding_token=binding_token,
            owner_entity_id=f"character:{entity_id}",
            owner_page_id=owner_page_id,
            parent_id=parent_id,
            child_id=child_id,
            section=section,
            media_role="udimo",
            resource_stem=(f"Item-{item.get('icon')}" if str(item.get("icon") or "") else ""),
            title=title,
            source_refs=(_source_ref(row, "$"),),
        )
    )
    result.record_links.append(
        _record_link(row, "child", "", child_id, "", section, change_kind="new_source_record")
    )


def _project_voices(
    row: Mapping[str, Any],
    voices: Sequence[Mapping[str, Any]],
    *,
    entity_id: str,
    entity_name: str,
    alias_text: str,
    owner_page_id: str,
    children_by_section: dict[str, list[SemanticChild]],
    ordered_children: list[SemanticChild],
    result: _ProjectionAccumulator,
) -> None:
    grouped: "OrderedDict[str, list[tuple[int, Mapping[str, Any]]]]" = OrderedDict()
    for voice_index, voice in enumerate(voices):
        event_name = str(voice.get("eventName") or "").strip()
        if not event_name:
            _project_voice(
                row,
                voice,
                voice_index=voice_index,
                entity_id=entity_id,
                entity_name=entity_name,
                alias_text=alias_text,
                owner_page_id=owner_page_id,
                children_by_section=children_by_section,
                ordered_children=ordered_children,
                result=result,
            )
            continue
        grouped.setdefault(event_name, []).append((voice_index, voice))

    parent_id = f"{owner_page_id}/voice"
    source_title = str(row.get("title") or "")
    for event_name, occurrences in grouped.items():
        first_index, first_voice = occurrences[0]
        first_path = f"$.character_voice.{first_index}"
        token, token_kind = _stable_source_token(
            event_name,
            row,
            owner_page_id,
            "voice",
            first_path,
            {"eventName": event_name},
            result,
        )
        child_id = f"{parent_id}/{token}"
        titles = tuple(
            dict.fromkeys(
                title
                for _index, voice in occurrences
                if (title := clean_huiji_text(voice.get("name")))
            )
        )
        title = titles[0] if titles else f"voice {token}"
        source_refs = tuple(
            _source_ref(row, f"$.character_voice.{voice_index}")
            for voice_index, _voice in occurrences
        )
        audio_ids = tuple(
            dict.fromkeys(
                str(voice.get("audio") or "").strip()
                for _index, voice in occurrences
                if str(voice.get("audio") or "").strip()
            )
        )
        skin_scopes = tuple(
            dict.fromkeys(
                str(voice.get("skins") or "").strip()
                for _index, voice in occurrences
                if str(voice.get("skins") or "").strip()
            )
        )

        lines = [title]
        source_rows: list[VoiceSourceRow] = []
        transcript_evidence: dict[str, Any] = {}
        binding_tokens: list[str] = []
        has_variants = False
        for field_name, language, label in _VOICE_FIELDS:
            candidates = [
                (voice_index, voice, str(voice.get(field_name) or ""))
                for voice_index, voice in occurrences
                if isinstance(voice.get(field_name), str)
                and str(voice.get(field_name)).strip()
            ]
            if not candidates:
                continue
            selected, evidence = _select_voice_transcript(candidates)
            if not selected:
                continue
            selected_index, selected_voice, selected_transcript = selected
            lines.append(f"{label}: {selected_transcript}")
            transcript_evidence[language] = evidence
            has_variants = has_variants or len(evidence["variants"]) > 1
            binding_tokens.append(f"voice:{token}:{language}")
            source_rows.append(
                VoiceSourceRow(
                    source_id=f"{child_id}:{language}",
                    entity_id=owner_page_id,
                    parent_id=parent_id,
                    child_id=child_id,
                    audio_id=str(selected_voice.get("audio") or ""),
                    event_name=event_name,
                    language=language,
                    transcript=selected_transcript,
                )
            )
            if not str(selected_voice.get("audio") or "").strip():
                result.exclusions.append(
                    _exclusion(
                        row,
                        "voice_binding_audio_id_missing",
                        entity_id=entity_id,
                        entity_name=entity_name,
                        json_path=f"$.character_voice.{selected_index}",
                        details={"event_name": event_name, "language": language},
                    )
                )

        text = "\n".join(lines)
        child = _semantic_child(
            child_id=child_id,
            parent_id=parent_id,
            entity_id=entity_id,
            entity_name=entity_name,
            section_kind="voice",
            title=title,
            text=text,
            search_parts=(entity_name, alias_text, "voice", title, text, event_name, child_id),
            chunk_index=len(children_by_section["voice"]),
            source_refs=source_refs,
            route_tags=("voice",),
            stable_source_token=token,
            source_token_kind=token_kind,
            owner_page_id=owner_page_id,
            media_policy="on_intent",
            media_binding_tokens=tuple(binding_tokens),
            source_fields={
                "event_name": event_name,
                "audio_ids": list(audio_ids),
                "skin_scopes": list(skin_scopes),
                "titles": list(titles),
                "occurrences": [
                    {
                        "json_path": f"$.character_voice.{voice_index}",
                        "audio_id": str(voice.get("audio") or ""),
                        "skin_scope": str(voice.get("skins") or ""),
                    }
                    for voice_index, voice in occurrences
                ],
                "transcript_evidence": transcript_evidence,
            },
            additional_quality_flags=(
                ("source_transcript_variant_resolved",) if has_variants else ()
            ),
        )
        children_by_section["voice"].append(child)
        ordered_children.append(child)
        result.voice_sources.extend(source_rows)

        linked_legacy_ids: set[str] = set()
        for voice_index, voice in occurrences:
            audio_id = str(voice.get("audio") or "").strip()
            if not audio_id:
                continue
            legacy_id = f"{owner_page_id}/voice:{audio_id}"
            if legacy_id in linked_legacy_ids:
                continue
            linked_legacy_ids.add(legacy_id)
            result.record_links.append(
                _record_link(
                    row,
                    "child",
                    legacy_id,
                    child_id,
                    "voice",
                    "voice",
                    json_path=f"$.character_voice.{voice_index}",
                )
            )


def _project_voice(
    row: Mapping[str, Any],
    voice: Mapping[str, Any],
    *,
    voice_index: int,
    entity_id: str,
    entity_name: str,
    alias_text: str,
    owner_page_id: str,
    children_by_section: dict[str, list[SemanticChild]],
    ordered_children: list[SemanticChild],
    result: _ProjectionAccumulator,
) -> None:
    json_path = f"$.character_voice.{voice_index}"
    token, token_kind = _stable_source_token(
        voice.get("audio"), row, owner_page_id, "voice", json_path, voice, result
    )
    parent_id = f"{owner_page_id}/voice"
    child_id = f"{parent_id}/{token}"
    title = clean_huiji_text(voice.get("name")) or f"语音 {token}"
    lines = [title]
    for field_name, _language, label in _VOICE_FIELDS:
        transcript = _display_voice_transcript(voice.get(field_name))
        if transcript:
            lines.append(f"{label}: {transcript}")
    text = "\n".join(lines)
    child = _semantic_child(
        child_id=child_id,
        parent_id=parent_id,
        entity_id=entity_id,
        entity_name=entity_name,
        section_kind="voice",
        title=title,
        text=text,
        search_parts=(entity_name, alias_text, "语音", title, text, child_id),
        chunk_index=len(children_by_section["voice"]),
        source_refs=(_source_ref(row, json_path),),
        route_tags=("voice",),
        stable_source_token=token,
        source_token_kind=token_kind,
        owner_page_id=owner_page_id,
        media_policy="on_intent",
        source_fields={
            "audio_id": str(voice.get("audio") or ""),
            "event_name": str(voice.get("eventName") or ""),
            "skin_scope": str(voice.get("skins") or ""),
        },
    )
    children_by_section["voice"].append(child)
    ordered_children.append(child)
    legacy_id = f"{owner_page_id}/voice:{str(voice.get('audio') or token)}"
    result.record_links.append(
        _record_link(row, "child", legacy_id, child_id, "voice", "voice", json_path=json_path)
    )

    event_name = voice.get("eventName")
    audio_id = str(voice.get("audio") or "")
    if not isinstance(event_name, str) or not event_name.strip() or not audio_id:
        result.exclusions.append(
            _exclusion(
                row,
                "voice_binding_identity_missing",
                entity_id=entity_id,
                entity_name=entity_name,
                json_path=json_path,
            )
        )
        return
    source_title = str(row.get("title") or "")
    for field_name, language, _label in _VOICE_FIELDS:
        transcript = voice.get(field_name)
        if not isinstance(transcript, str) or not transcript.strip():
            continue
        result.voice_sources.append(
            VoiceSourceRow(
                source_id=f"{source_title}:{audio_id}:{language}",
                entity_id=owner_page_id,
                parent_id=parent_id,
                child_id=child_id,
                audio_id=audio_id,
                event_name=event_name,
                language=language,
                transcript=transcript,
            )
        )


def _extract_voice_sources(
    row: Mapping[str, Any],
    payload: Mapping[str, Any],
    result: _ProjectionAccumulator,
) -> None:
    """Keep EVB diagnostics complete even when the owning entity is excluded."""
    source_title = str(row.get("title") or "")
    grouped: "OrderedDict[tuple[str, str], list[tuple[int, Mapping[str, Any]]]]" = OrderedDict()
    for voice_index, voice in enumerate(_dict_rows(payload.get("character_voice"))):
        event_name = str(voice.get("eventName") or "").strip()
        hero_id = str(voice.get("heroId") or payload.get("id") or "").strip()
        if event_name and hero_id:
            grouped.setdefault((hero_id, event_name), []).append((voice_index, voice))

    for (hero_id, event_name), occurrences in grouped.items():
        owner_page_id = f"char:{hero_id}"
        parent_id = f"{owner_page_id}/voice"
        first_index, _first_voice = occurrences[0]
        token, _token_kind = _stable_source_token(
            event_name,
            row,
            owner_page_id,
            "voice",
            f"$.character_voice.{first_index}",
            {"eventName": event_name},
            result,
        )
        child_id = f"{parent_id}/{token}"
        for field_name, language, _label in _VOICE_FIELDS:
            candidates = [
                (voice_index, voice, str(voice.get(field_name) or ""))
                for voice_index, voice in occurrences
                if isinstance(voice.get(field_name), str)
                and str(voice.get(field_name)).strip()
            ]
            selected, _evidence = _select_voice_transcript(candidates)
            if not selected:
                continue
            _selected_index, selected_voice, selected_transcript = selected
            result.voice_sources.append(
                VoiceSourceRow(
                    source_id=f"{child_id}:{language}",
                    entity_id=owner_page_id,
                    parent_id=parent_id,
                    child_id=child_id,
                    audio_id=str(selected_voice.get("audio") or ""),
                    event_name=event_name,
                    language=language,
                    transcript=selected_transcript,
                )
            )


def _project_skills(
    row: Mapping[str, Any],
    payload: Mapping[str, Any],
    *,
    entity_id: str,
    entity_name: str,
    alias_text: str,
    owner_page_id: str,
    children_by_section: dict[str, list[SemanticChild]],
    ordered_children: list[SemanticChild],
    result: _ProjectionAccumulator,
) -> None:
    grouped: "OrderedDict[tuple[str, str], list[tuple[str, Mapping[str, Any]]]]" = (
        OrderedDict()
    )
    for source_path, skill in sorted(
        _skill_rows(payload.get("skill")), key=lambda item: item[0]
    ):
        rank = _rank_value(skill.get("skillRank"))
        token_prefix = "ultimate" if rank <= 0 else "skill"
        stable_id = str(
            (skill.get("id") or source_path)
            if rank <= 0
            else (skill.get("icon") or skill.get("id") or source_path)
        )
        grouped.setdefault((token_prefix, stable_id), []).append((source_path, skill))
    parent_id = f"{owner_page_id}/skills"
    for group_index, ((token_prefix, stable_id), entries) in enumerate(grouped.items()):
        ultimate = token_prefix == "ultimate"
        resource_icon_id = str(entries[0][1].get("icon") or stable_id)
        token, token_kind = _stable_source_token(
            f"{token_prefix}-{stable_id}",
            row,
            owner_page_id,
            "skills",
            f"$.skill.{entries[0][0]}",
            entries[0][1],
            result,
        )
        child_id = f"{parent_id}/{token}"
        title = clean_huiji_text(entries[0][1].get("name")) or f"技能 {stable_id}"
        lines = [title]
        source_refs: list[dict[str, Any]] = []
        source_ids: list[str] = []
        rendered_variants: set[tuple[int, str]] = set()
        for source_path, skill in entries:
            rank = _rank_value(skill.get("skillRank"))
            details = " ".join(
                part
                for part in (
                    clean_huiji_text(skill.get("desc_art")),
                    clean_huiji_text(skill.get("eff_desc")),
                )
                if part
            )
            label = "至终的仪式" if rank <= 0 else f"星级 {rank} / Rank {rank}"
            variant = (rank, details)
            if variant not in rendered_variants:
                lines.append(f"{label}: {details}" if details else label)
                rendered_variants.add(variant)
            source_refs.append(_source_ref(row, f"$.skill.{source_path}"))
            source_ids.append(str(skill.get("id") or source_path))
        text = "\n".join(lines)
        child = _semantic_child(
            child_id=child_id,
            parent_id=parent_id,
            entity_id=entity_id,
            entity_name=entity_name,
            section_kind="skill",
            title=title,
            text=text,
            search_parts=(
                entity_name,
                alias_text,
                "技能",
                title,
                text,
                child_id,
                f"Skill-{resource_icon_id}",
                *source_ids,
            ),
            chunk_index=group_index,
            source_refs=tuple(source_refs),
            route_tags=("intro", "skill"),
            stable_source_token=token,
            source_token_kind=token_kind,
            owner_page_id=owner_page_id,
            media_binding_tokens=(f"{token_prefix}:{stable_id}:{resource_icon_id}",),
            source_fields={
                "icon_id": resource_icon_id,
                "skill_ids": source_ids,
                "ultimate": ultimate,
            },
        )
        children_by_section["skills"].append(child)
        ordered_children.append(child)
        legacy_leaf = "ultimate" if ultimate else "skill"
        legacy_id = f"{owner_page_id}/{legacy_leaf}:{stable_id}"
        result.record_links.append(
            _record_link(
                row,
                "child",
                legacy_id,
                child_id,
                "skill",
                "skill",
                json_path=f"$.skill.{entries[0][0]}",
            )
        )
        result.media_intents.append(
            MediaBindingIntent(
                source_binding_token=f"{token_prefix}:{stable_id}:{resource_icon_id}",
                owner_entity_id=f"character:{entity_id}",
                owner_page_id=owner_page_id,
                parent_id=parent_id,
                child_id=child_id,
                section="skills",
                media_role="skill",
                resource_stem=f"Skill-{resource_icon_id}",
                title=title,
                sort_order=group_index,
                source_refs=tuple(source_refs),
            )
        )


def _project_skin_media_intents(
    row: Mapping[str, Any],
    payload: Mapping[str, Any],
    *,
    entity_id: str,
    entity_name: str,
    owner_page_id: str,
    profile_child_id: str,
    result: _ProjectionAccumulator,
) -> None:
    default_skin_id = str(payload.get("skinId") or "")
    order = 0
    for skin_index, skin in enumerate(_dict_rows(payload.get("skin")), start=1):
        skin_id = str(skin.get("id") or skin_index)
        variant = clean_huiji_text(
            skin.get("characterSkin") or skin.get("des") or ""
        )
        resources = (
            ("roster_avatar", "largeIcon", "Headicon_large-"),
            ("stage_live2d", "live2d", "L2d_static-"),
            ("stage_portrait", "verticalDrawing", "L2d_static-"),
            ("stage_portrait", "drawing", "Portrait-"),
            ("character_chibi", "spine", "Spine_static-"),
            (
                "character_chibi_variant",
                "alternateSpine",
                "Spine_static-",
            ),
            ("skin_background", "live2dbg", "Skin_bg-"),
        )
        for role, source_field, prefix in resources:
            raw_resource = str(skin.get(source_field) or "").replace("\\", "/")
            resource_token = raw_resource.rsplit("/", 1)[-1]
            if not resource_token or (
                role == "roster_avatar"
                and default_skin_id
                and skin_id != default_skin_id
            ):
                continue
            stem = f"{prefix}{resource_token}"
            token = f"skin:{skin_id}:{source_field}"
            result.media_intents.append(
                MediaBindingIntent(
                    source_binding_token=token,
                    owner_entity_id=f"character:{entity_id}",
                    owner_page_id=owner_page_id,
                    parent_id=f"{owner_page_id}/profile",
                    child_id=profile_child_id,
                    section="profile",
                    media_role=role,
                    resource_stem=stem,
                    title=(
                        clean_huiji_text(skin.get("characterSkin"))
                        or clean_huiji_text(skin.get("name"))
                        or entity_name
                    ),
                    variant=variant,
                    skin_id=skin_id,
                    sort_order=order,
                    source_refs=(
                        _source_ref(
                            row,
                            f"$.skin.{skin_index - 1}.{source_field}",
                        ),
                    ),
                )
            )
            order += 1


def _project_generic(row: Mapping[str, Any], result: _ProjectionAccumulator) -> None:
    title = str(row.get("title") or "")
    raw_content = str(row.get("content") or "")
    try:
        payload = json.loads(raw_content)
    except json.JSONDecodeError:
        payload = {"name": title, "text": raw_content}
    if not isinstance(payload, dict):
        payload = {"name": title, "text": raw_content}
    category = _category_from_title(title)
    raw_id = payload.get("id")
    entity_id = (
        str(raw_id)
        if isinstance(raw_id, (str, int, float)) and not isinstance(raw_id, bool)
        else hashlib.sha1(title.encode("utf-8")).hexdigest()[:12]
    )
    raw_name = payload.get("name")
    raw_title = payload.get("title")
    scalar_name = (
        str(raw_name).strip()
        if isinstance(raw_name, (str, int, float)) and not isinstance(raw_name, bool)
        else ""
    )
    scalar_title = (
        str(raw_title).strip()
        if isinstance(raw_title, (str, int, float)) and not isinstance(raw_title, bool)
        else ""
    )
    entity_name = scalar_name or scalar_title or title.removesuffix(".json")
    parent_id = f"{category}:{entity_id}/profile"
    child_id = f"{parent_id}/root"
    text_parts = [entity_name]
    for key in ("desc", "description", "story", "content", "text"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            text_parts.append(clean_huiji_text(value))
    if len(text_parts) == 1:
        text_parts.append(clean_huiji_text(raw_content[:1200]))
    text = "\n".join(text_parts)
    source_refs = (_source_ref(row, "$"),)
    block = ChildBlock(
        child_id=child_id,
        parent_id=parent_id,
        entity_id=entity_id,
        entity_name=entity_name,
        category=category,
        section_kind="profile",
        title=entity_name,
        text=text,
        search_text=_search_text((category, entity_name, title, text)),
        chunk_index=0,
        media_ids=(),
        media_policy="auto",
        source_refs=source_refs,
        content_hash=_hash_text(text),
        entity_type=category,
        depth_level=3,
        ancestor_ids=(parent_id,),
        quality_flags=quality_flags_for_text(text, entity_name),
        route_tags=("profile",),
        omitted_action_label=entity_name,
    )
    result.children.append(
        SemanticChild(
            block=block,
            stable_source_token="root",
            source_token_kind="canonical_singleton",
            owner_entity_id=f"{category}:{entity_id}",
            owner_page_id=f"{category}:{entity_id}",
            description=text_parts[-1] if len(text_parts) > 1 else "",
        )
    )
    result.parents.append(
        ParentBlock(
            parent_id=parent_id,
            entity_id=entity_id,
            entity_name=entity_name,
            entity_aliases=(),
            category=category,
            section_kind="profile",
            title=entity_name,
            summary_text=_legacy_short_summary(text, max_chars=1000),
            source_refs=source_refs,
            child_ids=(child_id,),
            content_hash=_hash_text(text),
            entity_type=category,
            depth_level=1,
            ancestor_ids=(),
            quality_flags=quality_flags_for_text(text, entity_name),
            omitted_action_label=entity_name,
        )
    )
    legacy_id = f"{category}:{entity_id}:0000"
    result.record_links.extend(
        (
            _record_link(row, "parent", parent_id, parent_id, "profile", "profile"),
            _record_link(row, "child", legacy_id, child_id, "profile", "profile"),
        )
    )


def _semantic_child(
    *,
    child_id: str,
    parent_id: str,
    entity_id: str,
    entity_name: str,
    section_kind: str,
    title: str,
    text: str,
    search_parts: Sequence[object],
    chunk_index: int,
    source_refs: tuple[dict[str, Any], ...],
    route_tags: tuple[str, ...],
    stable_source_token: str,
    source_token_kind: str,
    owner_page_id: str,
    media_policy: str = "auto",
    ordinal: int = 0,
    name_en: str = "",
    valuation: str = "",
    description: str = "",
    media_binding_tokens: tuple[str, ...] = (),
    source_fields: Mapping[str, Any] | None = None,
    additional_quality_flags: tuple[str, ...] = (),
) -> SemanticChild:
    block = ChildBlock(
        child_id=child_id,
        parent_id=parent_id,
        entity_id=entity_id,
        entity_name=entity_name,
        category="character",
        section_kind=section_kind,
        title=title,
        text=text,
        search_text=_search_text(search_parts),
        chunk_index=chunk_index,
        media_ids=(),
        media_policy=media_policy,
        source_refs=source_refs,
        content_hash=_hash_text(text),
        entity_type="character",
        depth_level=3,
        ancestor_ids=(owner_page_id, parent_id),
        quality_flags=tuple(
            dict.fromkeys(
                (*quality_flags_for_text(text, entity_name), *additional_quality_flags)
            )
        ),
        route_tags=route_tags,
        omitted_action_label=title,
    )
    return SemanticChild(
        block=block,
        stable_source_token=stable_source_token,
        source_token_kind=source_token_kind,
        owner_entity_id=f"character:{entity_id}",
        owner_page_id=owner_page_id,
        ordinal=ordinal,
        name_en=name_en,
        valuation=valuation,
        description=description,
        media_binding_tokens=media_binding_tokens,
        source_fields=source_fields or {},
    )


def quality_flags_for_text(text: str, entity_name: str) -> tuple[str, ...]:
    flags: list[str] = []
    stripped = text.strip()
    if len(stripped) < 24:
        flags.append("short_text")
    if "<" in stripped and ">" in stripped:
        flags.append("raw_html_noise")
    if not entity_name or entity_name in _PLACEHOLDER_NAMES:
        flags.append("weak_entity_name")
    return tuple(flags)


def _merged_source_refs(children: Sequence[SemanticChild]) -> tuple[dict[str, Any], ...]:
    refs: list[dict[str, Any]] = []
    seen: set[bytes] = set()
    for child in children:
        for source_ref in child.block.source_refs:
            fingerprint = canonical_json_bytes(source_ref)
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            refs.append(dict(source_ref))
    return tuple(refs)


def _alias_map(rows: Sequence[Mapping[str, Any]]) -> dict[str, tuple[str, ...]]:
    aliases: dict[str, list[str]] = {}
    for row in rows:
        if str(row.get("title") or "") != "Data:Char/map.json":
            continue
        payload = _payload_object(row)
        if payload is None:
            continue
        values = payload.get("name")
        if not isinstance(values, dict):
            continue
        for name, raw_entity_id in values.items():
            entity_id = str(raw_entity_id)
            clean_name = clean_huiji_text(name)
            if clean_name and clean_name not in aliases.setdefault(entity_id, []):
                aliases[entity_id].append(clean_name)
    return {key: tuple(value) for key, value in aliases.items()}


def _udimo_owner_index(
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, tuple[Mapping[str, Any], Mapping[str, Any]]]:
    result: dict[str, tuple[Mapping[str, Any], Mapping[str, Any]]] = {}
    for row in rows:
        if not str(row.get("title") or "").startswith("Data:Item/"):
            continue
        payload = _payload_object(row)
        if payload is None:
            continue
        name = clean_huiji_text(payload.get("name"))
        owner = ""
        for prefix in ("尤提姆贴纸·", "尤提姆·"):
            if name.startswith(prefix):
                owner = _normal_name(name[len(prefix) :])
                break
        if not owner:
            continue
        current = result.get(owner)
        if current is None or (not current[1].get("icon") and payload.get("icon")):
            result[owner] = (row, payload)
    return result


def _character_exclusion(
    row: Mapping[str, Any], payload: Mapping[str, Any]
) -> ProjectionExclusion | None:
    entity_id = str(payload.get("id") or "").strip()
    entity_name = str(payload.get("name") or "").strip()
    if not entity_id:
        return _exclusion(
            row,
            "missing_entity_id",
            entity_name=entity_name,
        )
    if not entity_name:
        return _exclusion(row, "empty_entity_name", entity_id=entity_id)
    if entity_name in _PLACEHOLDER_NAMES:
        return _exclusion(
            row,
            "placeholder_name",
            entity_id=entity_id,
            entity_name=entity_name,
        )
    return None


def _exclusion(
    row: Mapping[str, Any],
    reason_code: str,
    *,
    entity_id: str = "",
    entity_name: str = "",
    json_path: str = "$",
    details: Mapping[str, Any] | None = None,
) -> ProjectionExclusion:
    title = str(row.get("title") or "")
    content_sha256 = str(row.get("content_sha256") or "")
    identity = hashlib.sha256(
        canonical_json_bytes([title, json_path, content_sha256], trailing_newline=False)
    ).hexdigest()
    return ProjectionExclusion(
        reason_code=reason_code,
        source_title=title,
        source_identity=identity,
        source_content_sha256=content_sha256,
        entity_id=entity_id,
        entity_name=entity_name,
        json_path=json_path,
        details=details or {},
    )


def _stable_source_token(
    raw_value: object,
    row: Mapping[str, Any],
    owner_page_id: str,
    section: str,
    json_path: str,
    source_payload: Mapping[str, Any],
    result: _ProjectionAccumulator,
) -> tuple[str, str]:
    value = str(raw_value or "").strip()
    if value and _SAFE_TOKEN_RE.fullmatch(value):
        return value, "crawler_stable_id"
    if value:
        encoded = base64.urlsafe_b64encode(value.encode("utf-8")).decode("ascii").rstrip("=")
        return f"id-{encoded}", "crawler_stable_id_encoded"
    identity = {
        "source_title": str(row.get("title") or ""),
        "section": section,
        "payload": dict(source_payload),
    }
    digest = hashlib.sha256(canonical_json_bytes(identity, trailing_newline=False)).hexdigest()
    token = f"source-{digest[:20]}"
    result.identity_fallbacks.append(
        IdentityFallback(
            owner_page_id=owner_page_id,
            canonical_section=section,
            json_path=json_path,
            source_identity_sha256=digest,
            stable_source_token=token,
            reason_code="stable_source_id_missing" if not value else "stable_source_id_unsafe",
        )
    )
    return token, "source_identity_sha256"


def _record_link(
    row: Mapping[str, Any],
    record_kind: str,
    legacy_id: str,
    candidate_id: str,
    legacy_section: str,
    candidate_section: str,
    *,
    json_path: str = "$",
    change_kind: str | None = None,
) -> SemanticRecordLink:
    if change_kind is None:
        if legacy_section != candidate_section:
            change_kind = "corrected_semantics"
        elif legacy_id != candidate_id:
            change_kind = "preserved_rekeyed"
        else:
            change_kind = "preserved_exact"
    return SemanticRecordLink(
        record_kind=record_kind,
        legacy_id=legacy_id,
        candidate_id=candidate_id,
        change_kind=change_kind,
        source_title=str(row.get("title") or ""),
        source_content_sha256=str(row.get("content_sha256") or ""),
        json_path=json_path,
        legacy_section=legacy_section,
        candidate_section=candidate_section,
    )


def _source_ref(row: Mapping[str, Any], json_path: str) -> dict[str, Any]:
    return {
        "kind": "data_page",
        "title": str(row.get("title") or ""),
        "revid": row.get("revid"),
        "content_sha256": str(row.get("content_sha256") or ""),
        "json_path": json_path,
    }


def _payload_object(row: Mapping[str, Any]) -> dict[str, Any] | None:
    value = row.get("content")
    if isinstance(value, dict):
        return dict(value)
    if not isinstance(value, str):
        return None
    try:
        payload = json.loads(value)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _skill_rows(value: Any) -> list[tuple[str, Mapping[str, Any]]]:
    if isinstance(value, dict):
        return [(str(key), item) for key, item in value.items() if isinstance(item, dict)]
    if isinstance(value, list):
        flattened: list[tuple[str, Mapping[str, Any]]] = []

        def visit(items: list[Any], prefix: tuple[int, ...] = ()) -> None:
            for index, item in enumerate(items):
                path = (*prefix, index)
                if isinstance(item, dict):
                    flattened.append((".".join(str(part) for part in path), item))
                elif isinstance(item, list):
                    visit(item, path)

        visit(value)
        return flattened
    return []


def _dict_rows(value: Any) -> list[Mapping[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _category_from_title(title: str) -> str:
    lowered = title.casefold()
    if "psychube" in lowered or "equip" in lowered or "心相" in title:
        return "psychube"
    if "item" in lowered or "物品" in title:
        return "item"
    if "episode" in lowered or "story" in lowered or "剧情" in title:
        return "story"
    return "generic"


def _display_voice_transcript(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        return ""
    lines: list[str] = []
    for part in value.split("|"):
        cleaned = re.sub(r"#-?\d+(?:\.\d+)?", "", part).strip()
        cleaned = clean_huiji_text(cleaned)
        if cleaned:
            lines.append(cleaned)
    return "\n".join(lines)


def _select_voice_transcript(
    candidates: Sequence[tuple[int, Mapping[str, Any], str]],
) -> tuple[
    tuple[int, Mapping[str, Any], str] | None,
    dict[str, Any],
]:
    prepared: list[tuple[int, Mapping[str, Any], str, str]] = []
    for voice_index, voice, raw_transcript in candidates:
        display = _display_voice_transcript(raw_transcript)
        if display:
            prepared.append((voice_index, voice, raw_transcript, display))
    if not prepared:
        return None, {"selected_sha256": "", "variants": []}

    display_counts = Counter(item[3] for item in prepared)
    best_count = max(display_counts.values())
    selected = next(item for item in prepared if display_counts[item[3]] == best_count)
    raw_groups: "OrderedDict[str, list[tuple[int, Mapping[str, Any], str, str]]]" = OrderedDict()
    for item in prepared:
        raw_groups.setdefault(item[2], []).append(item)
    variants = []
    for raw_transcript, rows in raw_groups.items():
        variants.append(
            {
                "raw_sha256": _hash_text(raw_transcript),
                "display_sha256": _hash_text(rows[0][3]),
                "occurrence_count": len(rows),
                "audio_ids": list(
                    dict.fromkeys(str(row[1].get("audio") or "") for row in rows)
                ),
                "json_paths": [f"$.character_voice.{row[0]}" for row in rows],
            }
        )
    return (
        (selected[0], selected[1], selected[3]),
        {
            "selected_sha256": _hash_text(selected[3]),
            "selection_rule": "display_consensus_then_source_order",
            "variants": variants,
        },
    )


def _normal_name(value: Any) -> str:
    return re.sub(r"\s+", "", clean_huiji_text(value)).casefold()


def _legacy_short_summary(value: str, max_chars: int = 240) -> str:
    text = compact_lines(value)
    if len(text) <= max_chars:
        return text
    match = re.search(r"[。！？.!?]", text[: max_chars + 20])
    if match:
        return text[: match.end()]
    return text[:max_chars].rstrip()


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _parent_hash(summary: str, child_ids: Sequence[str]) -> str:
    return _hash_text("\n".join((summary, *child_ids)))


def _search_text(parts: Sequence[object]) -> str:
    return " ".join(str(part) for part in parts if str(part).strip())


def _rank_value(value: object) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _as_nonnegative_int(value: object) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _assert_unique_ids(
    parents: Sequence[ParentBlock], children: Sequence[SemanticChild]
) -> None:
    parent_ids = [item.parent_id for item in parents]
    child_ids = [item.block.child_id for item in children]
    if len(parent_ids) != len(set(parent_ids)):
        raise ValueError("crawler projection produced duplicate parent IDs")
    if len(child_ids) != len(set(child_ids)):
        raise ValueError("crawler projection produced duplicate child IDs")
