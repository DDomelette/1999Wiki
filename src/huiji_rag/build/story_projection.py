"""Source-backed Story relation indexing and deterministic text projection."""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Sequence

from src.huiji_rag.models import ChildBlock, ParentBlock

from .contracts import canonical_json_bytes


_STORY_TITLE_RE = re.compile(r"Data:Story/([^/]+?)(?:\.json)?\Z", re.IGNORECASE)
_RELATION_TITLE_RE = re.compile(
    r"Data:(ChapterElement|Chapter|Episode)/[^/]+(?:\.json)?\Z",
    re.IGNORECASE,
)
_PLACEHOLDER_NAMES = frozenset({"", "???", "null", "none", "unknown", "未命名"})
_STEP_CONTAINERS = ("steps", "stepList", "storySteps", "scenes", "dialogues")
_DIALOGUE_KEYS = frozenset({"dialogue", "text", "content"})
_SPEAKER_KEYS = frozenset({"speaker", "speakerName", "roleName", "name"})
_SCENE_KEYS = frozenset({"scene", "sceneId", "sceneName"})
_CHOICE_KEYS = frozenset({"choice", "choices", "options"})
_ROOT_METADATA_KEYS = frozenset({"info", "name", "title"})
_INFO_METADATA_KEYS = frozenset({"id", "name", "start", "title"})
_ROOT_SPEAKER_CONTEXT_KEYS = frozenset({"hide_name", "show_name"}).union(
    _DIALOGUE_KEYS,
    _SCENE_KEYS,
    _CHOICE_KEYS,
)
_STEP_CONTROL_KEYS = frozenset(
    {
        "action",
        "audio",
        "auto",
        "background",
        "bg",
        "bool_1",
        "branch",
        "camera",
        "condition",
        "duration",
        "effect",
        "expression",
        "head_icon",
        "hide_name",
        "id",
        "is_end",
        "jump",
        "live2d",
        "music",
        "next",
        "no_l2d",
        "pos",
        "position",
        "resource",
        "resource_path",
        "shake",
        "show_name",
        "show_name_en",
        "skin",
        "sound",
        "speed",
        "step",
        "stepId",
        "step_id",
        "trigger",
        "type",
        "uid",
        "voice",
        "wait",
    }
)
_SUPPORTED_STEP_KEYS = frozenset().union(
    _DIALOGUE_KEYS,
    _SPEAKER_KEYS,
    _SCENE_KEYS,
    _CHOICE_KEYS,
    _STEP_CONTROL_KEYS,
)


@dataclass(frozen=True)
class StoryDiagnostic:
    reason_code: str
    story_id: str
    source_title: str
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "details", MappingProxyType(dict(self.details)))


@dataclass(frozen=True)
class StoryIdentityFallback:
    story_id: str
    json_path: str
    stable_source_token: str
    source_identity_sha256: str
    reason_code: str = "stable_story_step_id_missing"


@dataclass(frozen=True)
class StoryChildProjection:
    block: ChildBlock
    stable_source_token: str
    source_token_kind: str
    owner_entity_id: str
    owner_page_id: str
    source_fields: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_fields", MappingProxyType(dict(self.source_fields)))


@dataclass(frozen=True)
class StoryProjection:
    parents: tuple[ParentBlock, ...]
    children: tuple[StoryChildProjection, ...]
    diagnostics: tuple[StoryDiagnostic, ...]
    blocked_story_ids: tuple[str, ...]
    identity_fallbacks: tuple[StoryIdentityFallback, ...]


@dataclass(frozen=True)
class _StoryRecord:
    story_id: str
    row: Mapping[str, Any]
    payload: Mapping[str, Any]


@dataclass(frozen=True)
class _NameEvidence:
    priority: int
    name: str
    relation_kind: str
    source_refs: tuple[Mapping[str, Any], ...]


@dataclass(frozen=True)
class _RelationEvidence:
    story_id: str
    name: str
    priority: int
    relation_kind: str
    route_tag: str
    source_refs: tuple[Mapping[str, Any], ...]


def project_stories(rows: Iterable[Mapping[str, Any]]) -> StoryProjection:
    """Index minimal relation evidence and retain each Story payload only once."""
    stories: dict[str, _StoryRecord] = {}
    evidence: dict[str, list[_NameEvidence]] = {}
    relation_tags: dict[str, set[str]] = {}
    relation_evidence: list[_RelationEvidence] = []
    diagnostics: list[StoryDiagnostic] = []
    blocked: set[str] = set()

    for raw_row in rows:
        row = dict(raw_row)
        title = str(row.get("title") or "")
        payload = _payload_object(row)
        if payload is None:
            if _STORY_TITLE_RE.fullmatch(title):
                diagnostics.append(
                    StoryDiagnostic("invalid_story_json", _story_id(title), title)
                )
            continue
        story_match = _STORY_TITLE_RE.fullmatch(title)
        if story_match:
            story_id = story_match.group(1)
            previous = stories.get(story_id)
            record = _StoryRecord(story_id, row, payload)
            if previous is not None and previous.row != record.row:
                blocked.add(story_id)
                diagnostics.append(
                    StoryDiagnostic("story_source_conflict", story_id, title)
                )
                continue
            stories[story_id] = record
            for name, json_path in _direct_names(payload):
                evidence.setdefault(story_id, []).append(
                    _NameEvidence(
                        1,
                        name,
                        "story_payload",
                        (_source_ref(row, json_path),),
                    )
                )
            continue

        relation_match = _RELATION_TITLE_RE.fullmatch(title)
        if not relation_match:
            continue
        relation_type = relation_match.group(1).casefold()
        if relation_type != "episode":
            diagnostics.append(
                StoryDiagnostic(
                    "unsupported_story_relation",
                    "",
                    title,
                    {"container": relation_type},
                )
            )
            continue
        episode = payload.get("episode")
        if not isinstance(episode, dict):
            diagnostics.append(
                StoryDiagnostic(
                    "unsupported_story_relation",
                    "",
                    title,
                    {"container": "episode"},
                )
            )
            continue
        relation_name = _scalar_name(episode.get("name"))
        if not relation_name:
            continue
        for key, label in (
            ("beforeStory", "before"),
            ("story", "main"),
            ("afterStory", "after"),
        ):
            for story_id in _relation_ids(episode.get(key)):
                name = _episode_phase_name(relation_name, label)
                relation_evidence.append(
                    _RelationEvidence(
                        story_id,
                        name,
                        3,
                        f"episode_{label}",
                        "episode",
                        (
                            _source_ref(row, f"$.episode.{key}"),
                            _source_ref(row, "$.episode.name"),
                        ),
                    )
                )

    for relation in relation_evidence:
        evidence.setdefault(relation.story_id, []).append(
            _NameEvidence(
                relation.priority,
                relation.name,
                relation.relation_kind,
                relation.source_refs,
            )
        )
        relation_tags.setdefault(relation.story_id, set()).add(relation.route_tag)

    parents: list[ParentBlock] = []
    children: list[StoryChildProjection] = []
    identity_fallbacks: list[StoryIdentityFallback] = []
    for story_id, record in sorted(stories.items()):
        if story_id in blocked:
            continue
        resolved = _resolve_name(story_id, record, evidence.get(story_id, ()))
        if resolved is None:
            blocked.add(story_id)
            diagnostics.append(
                StoryDiagnostic("story_name_conflict", story_id, str(record.row["title"]))
            )
            continue
        entity_name, aliases, weak_name, name_source_refs = resolved
        story_children, fallbacks = _project_story_children(
            record,
            entity_name,
            aliases,
            weak_name,
            tuple(sorted(relation_tags.get(story_id, ()))),
        )
        structure_kind = _story_structure_kind(record.payload, story_children)
        diagnostic_details = {
            "revid": record.row.get("revid"),
            "story_structure_kind": structure_kind,
            "visible_story_atom_count": len(story_children),
        }
        if structure_kind == "unsupported_potentially_visible":
            blocked.add(story_id)
            diagnostics.append(
                StoryDiagnostic(
                    "unsupported_story_structure",
                    story_id,
                    str(record.row["title"]),
                    diagnostic_details,
                )
            )
            continue
        identity_fallbacks.extend(fallbacks)
        if not story_children:
            diagnostics.append(
                StoryDiagnostic(
                    (
                        "empty_story"
                        if structure_kind == "empty_object"
                        else "control_only_story"
                    ),
                    story_id,
                    str(record.row["title"]),
                    diagnostic_details,
                )
            )
            continue
        parent_id = f"story:{story_id}/story"
        parent_source_refs = (
            _source_ref(record.row, "$"),
            *_dedupe_source_refs(name_source_refs),
        )
        quality_flags = ("weak_entity_name",) if weak_name else ()
        parents.append(
            ParentBlock(
                parent_id=parent_id,
                entity_id=story_id,
                entity_name=entity_name,
                entity_aliases=aliases,
                category="story",
                section_kind="story",
                title=entity_name,
                summary_text=story_children[0].block.content[:1000],
                source_refs=parent_source_refs,
                child_ids=tuple(child.block.child_id for child in story_children),
                content_hash=hashlib.sha256(
                    "\n".join(
                        child.block.content_hash for child in story_children
                    ).encode("utf-8")
                ).hexdigest(),
                entity_type="story",
                quality_flags=quality_flags,
                omitted_action_label=entity_name,
            )
        )
        children.extend(story_children)

    diagnostics.sort(key=lambda item: (item.story_id, item.reason_code, item.source_title))
    return StoryProjection(
        parents=tuple(parents),
        children=tuple(children),
        diagnostics=tuple(diagnostics),
        blocked_story_ids=tuple(sorted(blocked)),
        identity_fallbacks=tuple(identity_fallbacks),
    )


def is_story_source_title(title: str) -> bool:
    return bool(
        _STORY_TITLE_RE.fullmatch(str(title))
        or _RELATION_TITLE_RE.fullmatch(str(title))
    )


def _resolve_name(
    story_id: str,
    record: _StoryRecord,
    values: Sequence[_NameEvidence],
) -> tuple[str, tuple[str, ...], bool, tuple[Mapping[str, Any], ...]] | None:
    grouped: dict[int, set[str]] = {}
    for item in values:
        grouped.setdefault(item.priority, set()).add(item.name)
    if not grouped:
        return f"Data:Story/{story_id}", (), True, ()
    winning_priority = min(grouped)
    winning_names = grouped[winning_priority]
    if len(winning_names) != 1:
        return None
    entity_name = next(iter(winning_names))
    retained_priorities = {
        priority
        for priority, names in grouped.items()
        if priority == winning_priority or len(names) == 1
    }
    aliases = tuple(
        sorted(
            {
                name
                for priority, names in grouped.items()
                if priority in retained_priorities and priority > winning_priority
                for name in names
                if name != entity_name
            },
            key=lambda value: (value.casefold(), value),
        )
    )
    source_refs = tuple(
        source_ref
        for item in values
        if item.priority in retained_priorities
        and (item.name == entity_name or item.name in aliases)
        for source_ref in item.source_refs
    )
    return entity_name, aliases, False, source_refs


def _project_story_children(
    record: _StoryRecord,
    entity_name: str,
    aliases: tuple[str, ...],
    weak_name: bool,
    relation_tags: tuple[str, ...],
) -> tuple[list[StoryChildProjection], list[StoryIdentityFallback]]:
    children: list[StoryChildProjection] = []
    fallbacks: list[StoryIdentityFallback] = []
    occurrences: dict[str, int] = {}
    for json_path, step, source_step_token in _iter_steps(record.payload):
        content, scene_value = _visible_step_content(step)
        if not content:
            continue
        stable_value = source_step_token or scene_value or _stable_step_value(step)
        if stable_value:
            prefix = "scene" if scene_value and not source_step_token else "step"
            base_token = f"{prefix}-{_safe_token(stable_value)}"
            token_kind = f"stable_{prefix}_id"
        else:
            fingerprint = canonical_json_bytes(
                [
                    str(record.row.get("title") or ""),
                    json_path,
                    str(record.row.get("content_sha256") or ""),
                ],
                trailing_newline=False,
            )
            digest = hashlib.sha256(fingerprint).hexdigest()
            base_token = f"hash-{digest[:20]}"
            token_kind = "source_identity_hash"
            fallbacks.append(
                StoryIdentityFallback(
                    story_id=record.story_id,
                    json_path=json_path,
                    stable_source_token=base_token,
                    source_identity_sha256=digest,
                )
            )
        occurrences[base_token] = occurrences.get(base_token, 0) + 1
        occurrence = occurrences[base_token]
        token = base_token if occurrence == 1 else f"{base_token}-occurrence-{occurrence:02d}"
        parent_id = f"story:{record.story_id}/story"
        child_id = f"{parent_id}/{token}"
        quality_flags = ("weak_entity_name",) if weak_name else ()
        route_tags = ("story", *relation_tags)
        source_ref = _source_ref(record.row, json_path)
        search_text = " ".join(
            (
                entity_name,
                " ".join(aliases),
                str(record.row.get("title") or ""),
                record.story_id,
                content,
            )
        )
        block = ChildBlock(
            child_id=child_id,
            parent_id=parent_id,
            entity_id=record.story_id,
            entity_name=entity_name,
            category="story",
            section_kind="story",
            title=entity_name,
            text=content,
            search_text=search_text,
            chunk_index=len(children),
            media_ids=(),
            media_policy="text_only",
            source_refs=(source_ref,),
            content_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
            entity_type="story",
            ancestor_ids=(f"story:{record.story_id}", parent_id),
            quality_flags=quality_flags,
            route_tags=route_tags,
            omitted_action_label=entity_name,
            heading_path=(f"story:{record.story_id}", token),
            entity_aliases=aliases,
        )
        children.append(
            StoryChildProjection(
                block=block,
                stable_source_token=token,
                source_token_kind=token_kind,
                owner_entity_id=f"story:{record.story_id}",
                owner_page_id=f"story:{record.story_id}",
                source_fields={"json_path": json_path},
            )
        )
    return children, fallbacks


def _iter_steps(payload: Mapping[str, Any]):
    found_container = False
    for key, value in payload.items():
        if key.isdigit() and isinstance(value, dict):
            yield f"$.{key}", value, key
            continue
        if key not in _STEP_CONTAINERS:
            continue
        found_container = True
        if isinstance(value, list):
            for index, item in enumerate(value):
                if isinstance(item, dict):
                    yield f"$.{key}.{index}", item, ""
        elif isinstance(value, dict):
            for child_key, item in value.items():
                if isinstance(item, dict):
                    yield f"$.{key}.{child_key}", item, ""
    if not found_container and any(key in payload for key in _DIALOGUE_KEYS):
        yield "$", payload, ""


def _visible_step_content(step: Mapping[str, Any]) -> tuple[str, str]:
    lines: list[str] = []
    speaker = ""
    scene_value = ""
    for key, value in step.items():
        if key in _SCENE_KEYS:
            scene_value = _visible_value(value)
            if scene_value:
                lines.append(f"Scene: {scene_value}")
        elif key in _SPEAKER_KEYS:
            speaker = _visible_value(value)
        elif key in _DIALOGUE_KEYS:
            dialogue = _visible_value(value)
            if dialogue:
                lines.append(f"{speaker}: {dialogue}" if speaker else dialogue)
        elif key in _CHOICE_KEYS:
            for choice in _choice_texts(value):
                lines.append(f"Choice: {choice}")
    return "\n".join(lines), scene_value


def _story_structure_kind(
    payload: Mapping[str, Any],
    children: Sequence[StoryChildProjection],
) -> str:
    if not payload:
        return "empty_object"
    if children:
        return "visible_story"
    if _has_unsupported_story_structure(payload):
        return "unsupported_potentially_visible"
    return "control_only"


def _has_unsupported_story_structure(payload: Mapping[str, Any]) -> bool:
    root_name_is_speaker_state = "name" in payload and any(
        key in payload for key in _ROOT_SPEAKER_CONTEXT_KEYS
    )
    direct_step = {
        key: value
        for key, value in payload.items()
        if key in _SUPPORTED_STEP_KEYS
        and (
            key not in _ROOT_METADATA_KEYS
            or (key == "name" and root_name_is_speaker_state)
        )
    }
    if direct_step and _step_has_unsupported_structure(direct_step):
        return True
    for key, value in payload.items():
        if key == "info":
            if _info_has_unsupported_structure(value):
                return True
            continue
        if key in _ROOT_METADATA_KEYS or key in _SUPPORTED_STEP_KEYS:
            continue
        if key.isdigit():
            if not isinstance(value, Mapping):
                return _has_value(value)
            if _step_has_unsupported_structure(value):
                return True
            continue
        if key not in _STEP_CONTAINERS:
            return _has_value(value)
        if isinstance(value, list):
            for item in value:
                if not isinstance(item, Mapping):
                    if _has_value(item):
                        return True
                    continue
                if _step_has_unsupported_structure(item):
                    return True
        elif isinstance(value, Mapping):
            for item in value.values():
                if not isinstance(item, Mapping):
                    if _has_value(item):
                        return True
                    continue
                if _step_has_unsupported_structure(item):
                    return True
        elif _has_value(value):
            return True
    return False


def _info_has_unsupported_structure(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return _has_value(value)
    for key, item in value.items():
        if key not in _INFO_METADATA_KEYS:
            if _has_value(item):
                return True
            continue
        if not _is_supported_metadata_value(item):
            return True
    return False


def _is_supported_metadata_value(value: Any) -> bool:
    if value is None or isinstance(value, (bool, int, float, str)):
        return True
    return isinstance(value, list) and all(
        item is None or isinstance(item, (bool, int, float, str))
        for item in value
    )


def _step_has_unsupported_structure(step: Mapping[str, Any]) -> bool:
    if any(
        key not in _SUPPORTED_STEP_KEYS and _has_value(value)
        for key, value in step.items()
    ):
        return True
    content, _scene_value = _visible_step_content(step)
    if content:
        return False
    has_speaker_state = any(
        _visible_value(step.get(key)) for key in _SPEAKER_KEYS if key in step
    )
    return has_speaker_state and step.get("show_name") is not False


def _has_value(value: Any) -> bool:
    if value is None or value is False or value == "":
        return False
    if isinstance(value, (list, tuple, Mapping)):
        return bool(value)
    return True


def _choice_texts(value: Any) -> tuple[str, ...]:
    rows = value if isinstance(value, list) else [value]
    result: list[str] = []
    for item in rows:
        if isinstance(item, dict):
            for key in ("text", "content", "title", "name"):
                text = _visible_value(item.get(key))
                if text:
                    result.append(text)
                    break
        elif isinstance(item, list):
            text = (
                _visible_value(item[4])
                if len(item) > 4 and isinstance(item[4], list)
                else ""
            )
            if text:
                result.append(text)
        else:
            text = _visible_value(item)
            if text:
                result.append(text)
    return tuple(result)


def _direct_names(payload: Mapping[str, Any]) -> tuple[tuple[str, str], ...]:
    info = payload.get("info")
    info_title = (
        _scalar_name(info.get("title"))
        if isinstance(info, dict)
        else ""
    )
    return tuple(
        dict.fromkeys(
            item
            for item in (
                (info_title, "$.info.title"),
                (_scalar_name(payload.get("name")), "$.name"),
                (_scalar_name(payload.get("title")), "$.title"),
            )
            if item[0]
        )
    )


def _relation_ids(value: Any) -> tuple[str, ...]:
    if isinstance(value, bool) or value is None:
        return ()
    if isinstance(value, (str, int)):
        text = str(value).strip()
        return (text,) if text and text != "0" else ()
    if isinstance(value, list):
        return tuple(
            dict.fromkeys(
                story_id
                for item in value
                for story_id in _relation_ids(item)
            )
        )
    return ()


def _dedupe_source_refs(
    refs: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], ...]:
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


def _episode_phase_name(name: str, phase: str) -> str:
    if phase == "before":
        return f"{name} (before)"
    if phase == "after":
        return f"{name} (after)"
    return name


def _stable_step_value(step: Mapping[str, Any]) -> str:
    for key in ("stepId", "step_id", "id", "uid"):
        value = _scalar_text(step.get(key))
        if value:
            return value
    return ""


def _safe_token(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).strip().casefold()
    token = re.sub(r"[^\w-]+", "-", normalized, flags=re.UNICODE).strip("-_")
    return token or hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:20]


def _payload_object(row: Mapping[str, Any]) -> Mapping[str, Any] | None:
    try:
        payload = json.loads(str(row.get("content") or ""))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _story_id(title: str) -> str:
    match = _STORY_TITLE_RE.fullmatch(title)
    return match.group(1) if match else ""


def _scalar_name(value: Any) -> str:
    text = _visible_value(value)
    return "" if text.casefold() in _PLACEHOLDER_NAMES else text


def _scalar_text(value: Any) -> str:
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return ""
    return str(value).strip()


def _visible_value(value: Any) -> str:
    if isinstance(value, list):
        return _scalar_text(value[0]) if value else ""
    return _scalar_text(value)


def _source_ref(row: Mapping[str, Any], json_path: str) -> dict[str, Any]:
    title = str(row.get("title") or "")
    revid = str(row.get("revid") or "")
    content_sha256 = str(row.get("content_sha256") or "")
    return {
        "source_kind": "crawler_data_page",
        "source_title": title,
        "source_row_id": f"{title}:{revid}:{json_path}",
        "source_content_sha256": content_sha256,
        "revid": row.get("revid"),
        "json_path": json_path,
    }
