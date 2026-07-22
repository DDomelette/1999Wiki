"""Voice-line grouping and stable in-memory pagination contracts."""
from __future__ import annotations

import base64
import json
import re
import secrets
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import Any, Iterable, Mapping
from urllib.parse import unquote, urlsplit

from src.huiji_rag.media import preferred_format_score


DEFAULT_VOICE_PAGE_SIZE = 8
MAX_VOICE_PAGE_SIZE = 20
MAX_CURSOR_STATES = 4096
MAX_URL_DECODE_DEPTH = 8

_LANGUAGE_PREFIXES = {
    "zh": ("zh", "cn", "ch"),
    "en": ("en",),
    "jp": ("jp", "ja"),
    "kr": ("kr", "ko"),
}
_LANGUAGE_ALIASES = {
    prefix: language
    for language, prefixes in _LANGUAGE_PREFIXES.items()
    for prefix in prefixes
}
_LANGUAGE_ORDER = {"zh": 0, "en": 1, "jp": 2, "kr": 3}
_LANGUAGE_LABELS = {
    "zh": "(中文)",
    "en": "(EN)",
    "jp": "(日)",
    "kr": "(韩)",
}
_AUDIO_EXTENSIONS = {".mp3", ".ogg", ".wav", ".m4a", ".aac", ".flac"}
_WINDOWS_DRIVE_PATH_RE = re.compile(r"(?<![a-z0-9])[a-z]:[\\/]", re.IGNORECASE)
_FILE_SCHEME_RE = re.compile(r"(?<![a-z0-9])file:", re.IGNORECASE)
_FORWARD_UNC_RE = re.compile(r"(?<!:)//")
_TRAVERSAL_SEGMENT_RE = re.compile(r"(?:^|[/=?#&])\.\.(?:/|$)")
_TYPED_ENTITY_SCOPE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*:(.+)$")


@dataclass(frozen=True)
class VoiceLineGroup:
    voice_line_id: str
    title: str
    variants: tuple[dict[str, object], ...]


@dataclass(frozen=True)
class VoicePanelPage:
    type: str
    grouping: str
    entity_id: str
    lines: tuple[VoiceLineGroup, ...]
    page_size: int
    total_lines: int
    has_more: bool
    next_cursor: str | None

    def to_dict(self) -> dict[str, object]:
        return {
            "type": self.type,
            "grouping": self.grouping,
            "entity_id": self.entity_id,
            "lines": [
                {
                    "voice_line_id": line.voice_line_id,
                    "title": line.title,
                    "variants": [dict(variant) for variant in line.variants],
                }
                for line in self.lines
            ],
            "page_size": self.page_size,
            "total_lines": self.total_lines,
            "has_more": self.has_more,
            "next_cursor": self.next_cursor,
        }


class InvalidVoiceCursor(ValueError):
    """Raised when a voice cursor cannot be validated in the current process."""


class VoiceCursorBuildMismatch(ValueError):
    """Raised when a voice cursor belongs to a different artifact build."""


@dataclass(frozen=True)
class _VoiceCursorState:
    entity_id: str
    parent_id: str
    last_voice_line_id: str
    page_size: int


@dataclass(frozen=True)
class _VoiceGroupEntry:
    entity_id: str
    parent_id: str
    sort_order: int
    group: VoiceLineGroup


def is_safe_browser_http_url(value: Any) -> bool:
    """Accept browser HTTP URLs only when their decoded payload has no local path marker."""
    url = str(value or "").strip()
    try:
        parsed = urlsplit(url)
    except ValueError:
        return False
    if parsed.scheme.casefold() not in {"http", "https"} or not parsed.netloc:
        return False
    payload = parsed.netloc + parsed.path
    if parsed.query:
        payload += "?" + parsed.query
    if parsed.fragment:
        payload += "#" + parsed.fragment
    for _attempt in range(MAX_URL_DECODE_DEPTH):
        decoded = unquote(payload)
        if decoded == payload:
            break
        payload = decoded
    else:
        return False
    lowered = payload.casefold()
    normalized = lowered.replace("\\", "/")
    return (
        _FILE_SCHEME_RE.search(lowered) is None
        and _WINDOWS_DRIVE_PATH_RE.search(lowered) is None
        and "\\" not in lowered
        and _FORWARD_UNC_RE.search(lowered) is None
        and _TRAVERSAL_SEGMENT_RE.search(normalized) is None
    )


def derive_entity_scope(
    entity_id: Any,
    child_id: Any,
    parent_id: Any,
    entity_name: Any = "",
) -> str | None:
    """Resolve one stable entity scope, returning None for conflicting identifiers."""
    explicit = str(entity_id or "").strip()
    prefixes = {
        text.split("/", 1)[0]
        for value in (child_id, parent_id)
        if (text := str(value or "").strip()) and "/" in text
    }
    if len(prefixes) > 1:
        return None
    inferred = next(iter(prefixes), "")
    if explicit and inferred and explicit != inferred:
        typed_scope = _TYPED_ENTITY_SCOPE_RE.fullmatch(inferred)
        if ":" in explicit or typed_scope is None or typed_scope.group(1) != explicit:
            return None
        return inferred
    return explicit or inferred or str(entity_name or "").strip()


def _is_playable_voice(row: Mapping[str, Any]) -> bool:
    if str(row.get("asset_type") or "") != "voice":
        return False
    if not row.get("is_available") or row.get("is_common"):
        return False
    if not is_safe_browser_http_url(row.get("url")):
        return False
    mime = str(row.get("mime") or "").casefold()
    if mime:
        return mime.startswith("audio/")
    return Path(str(row.get("filename") or "")).suffix.casefold() in _AUDIO_EXTENSIONS


def _voice_language(row: Mapping[str, Any]) -> str:
    explicit = str(row.get("language") or "").strip().casefold()
    if explicit:
        return _LANGUAGE_ALIASES.get(explicit, explicit)
    stem = Path(str(row.get("filename") or "")).stem.casefold()
    first = re.split(r"[\s_-]+", stem, maxsplit=1)[0]
    return _LANGUAGE_ALIASES.get(first, first or "other")


def _language_sort_key(language: str) -> tuple[int, str]:
    base = re.split(r"[-_]", language, maxsplit=1)[0]
    canonical = _LANGUAGE_ALIASES.get(base, base)
    return _LANGUAGE_ORDER.get(canonical, 4), language


def _line_number(child_id: str) -> int:
    match = re.search(r"(\d+)$", child_id)
    return int(match.group(1)) if match else 2**63 - 1


def _stable_row_key(row: Mapping[str, Any]) -> tuple[int, str]:
    return (
        int(row.get("sort_order", 0) or 0),
        str(row.get("binding_id") or row.get("media_id") or ""),
    )


def _preferred_variant(
    current: Mapping[str, Any] | None,
    candidate: Mapping[str, Any],
) -> Mapping[str, Any]:
    if current is None:
        return candidate
    current_score = preferred_format_score(str(current.get("filename") or ""))
    candidate_score = preferred_format_score(str(candidate.get("filename") or ""))
    if candidate_score != current_score:
        return candidate if candidate_score > current_score else current
    return candidate if _stable_row_key(candidate) < _stable_row_key(current) else current


def _variant_title(
    row: Mapping[str, Any],
    language: str,
    transcripts: Mapping[str, str],
) -> str:
    transcript = str(transcripts.get(language) or "").strip()
    if transcript:
        return f"{_LANGUAGE_LABELS.get(language, f'({language})')} {transcript}"
    return str(row.get("title") or row.get("filename") or row.get("media_id") or "")


def _serialize_variant(
    row: Mapping[str, Any],
    language: str,
    transcripts: Mapping[str, str],
    entity_scope: str,
) -> dict[str, object]:
    title = _variant_title(row, language, transcripts)
    binding_id = str(row.get("binding_id") or "")
    media_id = str(row.get("media_id") or "")
    return {
        "binding_id": binding_id,
        "resource_id": str(row.get("resource_id") or ""),
        "media_id": media_id,
        "asset_id": binding_id or media_id,
        "asset_type": "voice",
        "media_role": str(row.get("media_role") or "voice"),
        "mime": str(row.get("mime") or ""),
        "url": str(row.get("url") or ""),
        "child_id": str(row.get("child_id") or ""),
        "parent_id": str(row.get("parent_id") or ""),
        "section": str(row.get("section") or ""),
        "source_binding_token": str(row.get("source_binding_token") or ""),
        "owner_entity_id": str(row.get("owner_entity_id") or ""),
        "owner_page_id": str(row.get("owner_page_id") or ""),
        "variant": str(row.get("variant") or ""),
        "skin_id": str(row.get("skin_id") or ""),
        "entity_id": entity_scope,
        "entity_name": str(row.get("entity_name") or ""),
        "title": title,
        "alt": title,
        "role": "voice",
        "attach_policy": str(row.get("attach_policy") or ""),
        "panel_group": str(row.get("panel_group") or ""),
        "sort_order": int(row.get("sort_order", 0) or 0),
        "duration_ms": int(row.get("duration_ms", 0) or 0),
        "language": language,
    }


def _group_title(
    variants: tuple[dict[str, object], ...],
    transcripts: Mapping[str, str],
    child_id: str,
) -> str:
    zh = str(transcripts.get("zh") or "").strip()
    if zh:
        return zh
    for language in sorted(transcripts, key=_language_sort_key):
        transcript = str(transcripts.get(language) or "").strip()
        if transcript:
            return transcript
    first = variants[0] if variants else {}
    stable = str(first.get("title") or "").strip()
    if stable:
        return stable
    return child_id


def _build_group_entries(
    records: Iterable[Mapping[str, Any]],
    transcripts_by_child: Mapping[str, Mapping[str, str]],
) -> tuple[_VoiceGroupEntry, ...]:
    grouped: dict[tuple[str, str, str], dict[str, Mapping[str, Any]]] = {}
    for row in records:
        if not _is_playable_voice(row):
            continue
        entity_id = derive_entity_scope(
            row.get("entity_id"),
            row.get("child_id"),
            row.get("parent_id"),
            row.get("entity_name"),
        )
        parent_id = str(row.get("parent_id") or "")
        child_id = str(row.get("child_id") or "")
        if not entity_id or not parent_id or not child_id:
            continue
        language = _voice_language(row)
        language_rows = grouped.setdefault((entity_id, parent_id, child_id), {})
        language_rows[language] = _preferred_variant(language_rows.get(language), row)

    entries: list[_VoiceGroupEntry] = []
    for (entity_id, parent_id, child_id), language_rows in grouped.items():
        transcripts = transcripts_by_child.get(child_id, {})
        variants = tuple(
            _serialize_variant(language_rows[language], language, transcripts, entity_id)
            for language in sorted(language_rows, key=_language_sort_key)
        )
        sort_order = min(int(row.get("sort_order", 0) or 0) for row in language_rows.values())
        entries.append(
            _VoiceGroupEntry(
                entity_id=entity_id,
                parent_id=parent_id,
                sort_order=sort_order,
                group=VoiceLineGroup(
                    voice_line_id=child_id,
                    title=_group_title(variants, transcripts, child_id),
                    variants=variants,
                ),
            )
        )
    entries.sort(
        key=lambda entry: (
            entry.parent_id,
            _line_number(entry.group.voice_line_id),
            entry.sort_order,
            entry.group.voice_line_id,
        )
    )
    # A physical resource or compatibility media ID may have many bindings.
    # Pagination is line-based and therefore keeps every child association.
    return tuple(entries)


def build_voice_line_groups(
    records: Iterable[Mapping[str, Any]],
    transcripts_by_child: Mapping[str, Mapping[str, str]],
) -> tuple[VoiceLineGroup, ...]:
    """Build playable voice lines from already-loaded artifact records."""
    return tuple(entry.group for entry in _build_group_entries(records, transcripts_by_child))


class VoiceCursorStore:
    """Bounded process-local cursor state with opaque public wrappers."""

    def __init__(self, build_version: str, max_states: int = MAX_CURSOR_STATES) -> None:
        self.build_version = str(build_version)
        self.max_states = min(MAX_CURSOR_STATES, max(1, int(max_states)))
        self._states: OrderedDict[str, _VoiceCursorState] = OrderedDict()
        self._tokens: dict[_VoiceCursorState, str] = {}
        self._lock = RLock()

    def __len__(self) -> int:
        with self._lock:
            return len(self._states)

    def issue(
        self,
        entity_id: str,
        parent_id: str,
        last_voice_line_id: str,
        page_size: int,
    ) -> str:
        state = _VoiceCursorState(
            entity_id=str(entity_id),
            parent_id=str(parent_id),
            last_voice_line_id=str(last_voice_line_id),
            page_size=_clamp_page_size(page_size),
        )
        with self._lock:
            existing = self._tokens.get(state)
            if existing is not None and existing in self._states:
                self._states.move_to_end(existing)
                return self._wrap(existing)
            token = secrets.token_urlsafe(24)
            while token in self._states:
                token = secrets.token_urlsafe(24)
            self._states[token] = state
            self._tokens[state] = token
            while len(self._states) > self.max_states:
                stale_token, stale_state = self._states.popitem(last=False)
                if self._tokens.get(stale_state) == stale_token:
                    del self._tokens[stale_state]
            return self._wrap(token)

    def decode(self, cursor: str) -> _VoiceCursorState:
        wrapper = self._unwrap(cursor)
        if wrapper["b"] != self.build_version:
            raise VoiceCursorBuildMismatch("voice cursor belongs to another build")
        with self._lock:
            state = self._states.get(wrapper["t"])
            if state is None:
                raise InvalidVoiceCursor("voice cursor is unknown or expired")
            self._states.move_to_end(wrapper["t"])
            return state

    def _wrap(self, token: str) -> str:
        payload = json.dumps(
            {"b": self.build_version, "t": token},
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")

    @staticmethod
    def _unwrap(cursor: str) -> dict[str, str]:
        try:
            raw = str(cursor).encode("ascii")
            padding = b"=" * (-len(raw) % 4)
            payload = base64.b64decode(raw + padding, altchars=b"-_", validate=True)
            wrapper = json.loads(payload.decode("utf-8"))
        except (UnicodeError, ValueError, TypeError, json.JSONDecodeError) as exc:
            raise InvalidVoiceCursor("voice cursor wrapper is invalid") from exc
        if (
            not isinstance(wrapper, dict)
            or set(wrapper) != {"b", "t"}
            or not isinstance(wrapper.get("b"), str)
            or not isinstance(wrapper.get("t"), str)
            or not wrapper["t"]
        ):
            raise InvalidVoiceCursor("voice cursor wrapper is invalid")
        return wrapper


def _clamp_page_size(page_size: int) -> int:
    return min(MAX_VOICE_PAGE_SIZE, max(1, int(page_size)))


class VoicePaginationIndex:
    """Read-only voice index over the registry records loaded at startup."""

    def __init__(
        self,
        records: Iterable[Mapping[str, Any]],
        transcripts_by_child: Mapping[str, Mapping[str, str]],
        *,
        build_version: str,
        cursor_store: VoiceCursorStore | None = None,
    ) -> None:
        entries = _build_group_entries(records, transcripts_by_child)
        scopes: dict[tuple[str, str], list[VoiceLineGroup]] = {}
        for entry in entries:
            scopes.setdefault((entry.entity_id, entry.parent_id), []).append(entry.group)
        self._scopes = {scope: tuple(groups) for scope, groups in scopes.items()}
        self._cursor_store = cursor_store or VoiceCursorStore(build_version)

    def first_page(
        self,
        entity_id: str,
        parent_id: str,
        page_size: int = DEFAULT_VOICE_PAGE_SIZE,
    ) -> VoicePanelPage:
        size = _clamp_page_size(page_size)
        groups = self._scopes.get((str(entity_id), str(parent_id)), ())
        return self._page(str(entity_id), str(parent_id), groups, 0, size)

    def get_page(self, cursor: str) -> VoicePanelPage:
        state = self._cursor_store.decode(cursor)
        groups = self._scopes.get((state.entity_id, state.parent_id))
        if groups is None:
            raise InvalidVoiceCursor("voice cursor scope is no longer available")
        matching_indexes = [
            index
            for index, group in enumerate(groups)
            if group.voice_line_id == state.last_voice_line_id
        ]
        if len(matching_indexes) != 1:
            raise InvalidVoiceCursor("voice cursor line is no longer available")
        return self._page(
            state.entity_id,
            state.parent_id,
            groups,
            matching_indexes[0] + 1,
            state.page_size,
        )

    def _page(
        self,
        entity_id: str,
        parent_id: str,
        groups: tuple[VoiceLineGroup, ...],
        start: int,
        page_size: int,
    ) -> VoicePanelPage:
        lines = groups[start : start + page_size]
        has_more = start + len(lines) < len(groups)
        next_cursor = None
        if has_more and lines:
            next_cursor = self._cursor_store.issue(
                entity_id,
                parent_id,
                lines[-1].voice_line_id,
                page_size,
            )
        return VoicePanelPage(
            type="voice",
            grouping="voice_line",
            entity_id=entity_id,
            lines=lines,
            page_size=page_size,
            total_lines=len(groups),
            has_more=has_more,
            next_cursor=next_cursor,
        )
