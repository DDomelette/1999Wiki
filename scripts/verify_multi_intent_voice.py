"""Read-only artifact inventory and Milvus snapshot for P0 evaluation."""
from __future__ import annotations

import argparse
import codecs
import json
import math
import re
import socket
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, unquote, urlsplit
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pymilvus import MilvusClient

from config.config import get_config
from src.assets.voice_pagination import derive_entity_scope
from src.huiji_rag.io import iter_jsonl
from src.huiji_rag.runtime_artifacts import resolve_runtime_artifact_snapshot
from src.huiji_rag.media import preferred_format_score


VOICE_LANGUAGE_PREFIXES = {
    "zh": ("zh", "cn", "ch"),
    "en": ("en",),
    "jp": ("jp", "ja"),
    "kr": ("kr", "ko"),
}
VOICE_AUDIO_EXTENSIONS = {".mp3", ".ogg", ".wav", ".m4a", ".aac", ".flac"}
FILE_SCHEME_RE = re.compile(r"(?<![a-z0-9])file:", re.IGNORECASE)
FORBIDDEN_TRANSPORT_KEYS = {
    "absolute_path",
    "file_path",
    "filesystem_path",
    "local_path",
    "local_relpath",
}
QUERY_TEMPLATE = "{entity_name}的技能和语音"
DEFAULT_HTTP_TIMEOUT = 15.0
MAX_SSE_BYTES = 16 * 1024 * 1024
MAX_JSON_BYTES = 4 * 1024 * 1024
REQUIRED_ELIGIBLE_SAMPLE_LIMIT = 8
MAX_VOICE_PAGES = 512


@dataclass(frozen=True)
class CharacterInventory:
    entity_id: str
    entity_name: str
    skill_child_ids: tuple[str, ...]
    voice_text_child_ids: tuple[str, ...]
    playable_voice_line_ids: tuple[str, ...]
    playable_media_ids: tuple[str, ...]
    languages: tuple[str, ...]
    child_char_lengths: tuple[tuple[str, int], ...] = ()
    playable_media_by_line: tuple[tuple[str, tuple[str, ...]], ...] = ()
    media_languages: tuple[tuple[str, str], ...] = ()
    skill_media_ids: tuple[str, ...] = ()
    entity_scope: str = ""
    entity_scope_valid: bool = True
    media_id_line_conflicts: tuple[tuple[str, tuple[str, ...]], ...] = ()


def _is_voice_child(row: dict[str, Any]) -> bool:
    return str(row.get("section_kind") or "") == "voice" or "/voice" in str(row.get("parent_id") or "")


def _is_http_url(value: Any) -> bool:
    raw = str(value or "").strip()
    try:
        parsed = urlsplit(raw)
    except ValueError:
        return False
    if parsed.scheme.casefold() not in {"http", "https"} or not parsed.netloc:
        return False
    decoded = parsed.netloc + parsed.path
    if parsed.query:
        decoded += "?" + parsed.query
    if parsed.fragment:
        decoded += "#" + parsed.fragment
    for _attempt in range(8):
        next_value = unquote(decoded)
        if next_value == decoded:
            break
        decoded = next_value
    else:
        return False
    lowered = decoded.casefold()
    normalized = lowered.replace("\\", "/")
    return not (
        FILE_SCHEME_RE.search(lowered) is not None
        or re.search(r"(?:^|[^a-z0-9])[a-z]:/", normalized)
        or "\\" in lowered
        or "//" in lowered
        or "/../" in normalized
        or normalized.endswith("/..")
    )


def _is_playable_voice_media(row: dict[str, Any]) -> bool:
    asset_type = row.get("asset_type")
    mime = str(row.get("mime") or "").casefold()
    if asset_type != "voice":
        return False
    if not bool(row.get("is_available")) or bool(row.get("is_common")) or not _is_http_url(row.get("url")):
        return False
    if mime:
        return mime.startswith("audio/")
    return Path(str(row.get("filename") or "")).suffix.casefold() in VOICE_AUDIO_EXTENSIONS


def _infer_language(filename: Any) -> str:
    first_token = re.split(r"[\s_-]+", Path(str(filename or "")).stem.casefold(), maxsplit=1)[0]
    for language, prefixes in VOICE_LANGUAGE_PREFIXES.items():
        if first_token in prefixes:
            return language
    return ""


def _media_language(row: Mapping[str, Any]) -> str:
    explicit = str(row.get("language") or "").strip().casefold()
    aliases = {prefix: language for language, prefixes in VOICE_LANGUAGE_PREFIXES.items() for prefix in prefixes}
    if explicit:
        return aliases.get(explicit, explicit)
    return _infer_language(row.get("filename")) or "other"


def _binding_identity(row: Mapping[str, Any]) -> str:
    return str(
        row.get("binding_id")
        or row.get("asset_id")
        or row.get("media_id")
        or ""
    )


def _line_number(child_id: str) -> int:
    match = re.search(r"(\d+)$", child_id)
    return int(match.group(1)) if match else 2**63 - 1


def _preferred_voice_row(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    return min(
        rows,
        key=lambda row: (
            -preferred_format_score(str(row.get("filename") or "")),
            int(row.get("sort_order", 0) or 0),
            str(row.get("media_id") or ""),
        ),
    )


def _duplicates(values: Iterable[str]) -> list[str]:
    return sorted(value for value, count in Counter(values).items() if value and count > 1)


def _canonical_entity_scope(inventory: CharacterInventory) -> str:
    if not inventory.entity_scope_valid:
        return ""
    return inventory.entity_scope or inventory.entity_id


def _contains_local_path(value: Any) -> bool:
    if isinstance(value, str):
        decoded = value
        for _attempt in range(8):
            next_value = unquote(decoded)
            if next_value == decoded:
                break
            decoded = next_value
        else:
            return True
        lowered = decoded.casefold()
        normalized = lowered.replace("\\", "/")
        try:
            parsed = urlsplit(decoded)
        except ValueError:
            parsed = None
        url_payload = ""
        if parsed is not None and parsed.scheme.casefold() in {"http", "https"}:
            url_payload = parsed.netloc + parsed.path
        return bool(
            FILE_SCHEME_RE.search(lowered) is not None
            or re.search(r"(?:^|[^a-z0-9])[a-z]:/", normalized)
            or "\\\\" in lowered
            or "\\" in url_payload
            or "//" in url_payload
            or "/../" in normalized
            or normalized.endswith("/..")
        )
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized_key = str(key).casefold()
            if normalized_key in FORBIDDEN_TRANSPORT_KEYS:
                return True
            if (normalized_key == "url" or normalized_key.endswith("_url")) and not _is_http_url(item):
                return True
            if _contains_local_path(item):
                return True
        return False
    if isinstance(value, (list, tuple)):
        return any(_contains_local_path(item) for item in value)
    return False


def build_character_inventory(
    child_rows: Iterable[dict[str, Any]], media_rows: Iterable[dict[str, Any]]
) -> list[CharacterInventory]:
    entities: dict[str, dict[str, Any]] = {}
    for row in child_rows:
        entity_id = str(row.get("entity_id") or "")
        child_id = str(row.get("child_id") or "")
        if not entity_id or not child_id:
            continue
        entity = entities.setdefault(
            entity_id,
            {
                "name": "",
                "skills": set(),
                "voice_text": set(),
                "child_chars": {},
                "voice_media": [],
                "skill_media": [],
                "entity_scopes": set(),
                "entity_scope_valid": True,
            },
        )
        scope = derive_entity_scope(
            entity_id,
            child_id,
            row.get("parent_id"),
            row.get("entity_name"),
        )
        if scope is None:
            entity["entity_scope_valid"] = False
        else:
            entity["entity_scopes"].add(scope)
        if not entity["name"]:
            entity["name"] = str(row.get("entity_name") or "")
        if str(row.get("section_kind") or "") == "skill":
            entity["skills"].add(child_id)
        if _is_voice_child(row):
            entity["voice_text"].add(child_id)
        entity["child_chars"][child_id] = len(str(row.get("text") or ""))

    for row in media_rows:
        entity_id = str(row.get("entity_id") or "")
        entity = entities.get(entity_id)
        if entity is None:
            continue
        child_id = str(row.get("child_id") or "")
        scope = derive_entity_scope(
            entity_id,
            child_id,
            row.get("parent_id"),
            row.get("entity_name"),
        )
        if scope is None:
            entity["entity_scope_valid"] = False
        else:
            entity["entity_scopes"].add(scope)
        if _is_playable_voice_media(row) and child_id in entity["voice_text"]:
            entity["voice_media"].append(row)
        asset_type = str(row.get("asset_type") or "").casefold()
        if (
            child_id in entity["skills"]
            and asset_type in {"skill", "ultimate"}
            and bool(row.get("is_available"))
            and not bool(row.get("is_common"))
            and _is_http_url(row.get("url"))
        ):
            entity["skill_media"].append(row)

    inventory: list[CharacterInventory] = []
    for entity_id, entity in entities.items():
        scope_candidates = entity["entity_scopes"]
        entity_scope_valid = bool(entity["entity_scope_valid"]) and len(scope_candidates) == 1
        entity_scope = next(iter(scope_candidates)) if entity_scope_valid else ""
        grouped: dict[str, dict[str, list[dict[str, Any]]]] = {}
        line_sort_orders: dict[str, int] = {}
        for row in entity["voice_media"]:
            child_id = str(row.get("child_id") or "")
            language = _media_language(row)
            grouped.setdefault(child_id, {}).setdefault(language, []).append(row)
            sort_order = int(row.get("sort_order", 0) or 0)
            line_sort_orders[child_id] = min(line_sort_orders.get(child_id, sort_order), sort_order)
        playable_line_ids = tuple(
            sorted(
                grouped,
                key=lambda child_id: (
                    str(next(iter(grouped[child_id].values()))[0].get("parent_id") or ""),
                    _line_number(child_id),
                    line_sort_orders[child_id],
                    child_id,
                ),
            )
        )
        selected_rows_by_line: dict[str, tuple[dict[str, Any], ...]] = {}
        for child_id in playable_line_ids:
            selected_rows = tuple(
                row
                for language in sorted(grouped[child_id])
                if _binding_identity(
                    row := _preferred_voice_row(grouped[child_id][language])
                )
            )
            if selected_rows:
                selected_rows_by_line[child_id] = selected_rows
        selected_rows = [
            row
            for child_id in playable_line_ids
            for row in selected_rows_by_line[child_id]
        ]
        lines_by_media_id: dict[str, set[str]] = {}
        for child_id in playable_line_ids:
            for row in selected_rows_by_line[child_id]:
                media_id = _binding_identity(row)
                if media_id:
                    lines_by_media_id.setdefault(media_id, set()).add(child_id)
        media_id_line_conflicts = tuple(
            (media_id, tuple(sorted(child_ids)))
            for media_id, child_ids in sorted(lines_by_media_id.items())
            if len(child_ids) > 1
        )
        playable_media_ids = tuple(sorted(
            _binding_identity(row) for row in selected_rows if _binding_identity(row)
        ))
        languages = tuple(sorted({_media_language(row) for row in selected_rows}))
        inventory.append(
            CharacterInventory(
                entity_id=entity_id,
                entity_name=str(entity["name"]),
                skill_child_ids=tuple(sorted(entity["skills"])),
                voice_text_child_ids=tuple(sorted(entity["voice_text"])),
                playable_voice_line_ids=playable_line_ids,
                playable_media_ids=playable_media_ids,
                languages=languages,
                child_char_lengths=tuple(sorted(entity["child_chars"].items())),
                playable_media_by_line=tuple(
                    (
                        child_id,
                        tuple(sorted(
                            _binding_identity(row)
                            for row in selected_rows_by_line[child_id]
                            if _binding_identity(row)
                        )),
                    )
                    for child_id in playable_line_ids
                ),
                media_languages=tuple(sorted(
                    (_binding_identity(row), _media_language(row))
                    for row in selected_rows
                    if _binding_identity(row)
                )),
                skill_media_ids=tuple(sorted({
                    _binding_identity(row)
                    for row in entity["skill_media"]
                    if _binding_identity(row)
                })),
                entity_scope=entity_scope,
                entity_scope_valid=entity_scope_valid,
                media_id_line_conflicts=media_id_line_conflicts,
            )
        )
    return sorted(inventory, key=lambda item: item.entity_id)


def _route_parts(route_debug: Mapping[str, Any] | None) -> tuple[tuple[str, ...], Mapping[str, Any]]:
    route = route_debug if isinstance(route_debug, Mapping) else {}
    intents = route.get("requested_intents")
    requested = tuple(str(item) for item in intents) if isinstance(intents, (list, tuple)) else ()
    nested = route.get("retrieval_debug")
    debug = nested if isinstance(nested, Mapping) else route
    return requested, debug


def evaluate_sources(
    inventory: CharacterInventory,
    source_ids: Iterable[str],
    route_debug: Mapping[str, Any] | None,
    page_size: int,
    budgets: Mapping[str, Any],
) -> list[str]:
    """Evaluate source identity, dynamic quotas, and truthful budget shortfall."""
    failures: list[str] = []
    observed = [str(item) for item in source_ids if str(item)]
    for child_id in _duplicates(observed):
        failures.append(f"duplicate_source_id:{child_id}")

    skill_ids = set(inventory.skill_child_ids)
    voice_ids = set(inventory.voice_text_child_ids)
    allowed_ids = set(dict(inventory.child_char_lengths))
    for child_id in sorted(set(observed) - allowed_ids):
        failures.append(f"foreign_source_id:{child_id}")

    requested, debug = _route_parts(route_debug)
    if requested != ("skill", "voice"):
        failures.append("requested_intents_mismatch")

    max_sources = max(0, int(budgets.get("max_sources", 0) or 0))
    char_budget = max(0, int(budgets.get("context_budget_chars", 0) or 0))
    if len(observed) > max_sources:
        failures.append("source_count_over_budget")
    if debug.get("max_sources") != max_sources:
        failures.append("max_sources_mismatch")
    char_lengths = dict(inventory.child_char_lengths)
    unknown_length_ids = sorted({child_id for child_id in observed if child_id not in char_lengths})
    for child_id in unknown_length_ids:
        failures.append(f"unknown_source_char_length:{child_id}")
    observed_chars = sum(char_lengths[child_id] for child_id in observed if child_id in char_lengths)
    if observed_chars > char_budget:
        failures.append("observed_chars_over_budget")
    chars_used = debug.get("chars_used")
    if type(chars_used) is not int or chars_used < 0:
        failures.append("chars_used_invalid")
    else:
        if chars_used > char_budget:
            failures.append("chars_used_over_budget")
        if chars_used < observed_chars:
            failures.append("chars_used_underreported")

    skill_target = len(skill_ids) or 1
    voice_target = min(max(1, int(page_size)), len(voice_ids)) or 1
    observed_set = set(observed)
    retained = {
        "skill": len(observed_set & skill_ids),
        "voice": len(observed_set & voice_ids),
    }
    targets = {"skill": skill_target, "voice": voice_target}
    shortfall = {
        intent: max(0, targets[intent] - retained[intent])
        for intent in targets
    }
    for field, expected in (
        ("intent_targets", targets),
        ("intent_retained", retained),
        ("coverage_shortfall", shortfall),
    ):
        actual = debug.get(field)
        for intent in ("skill", "voice"):
            if not isinstance(actual, Mapping) or actual.get(intent) != expected[intent]:
                failures.append(f"{field}_mismatch:{intent}")

    required_voice_lengths = sorted(char_lengths.get(child_id, 0) for child_id in voice_ids)[: min(page_size, len(voice_ids))]
    required_chars = sum(char_lengths.get(child_id, 0) for child_id in skill_ids) + sum(required_voice_lengths)
    required_sources = len(skill_ids) + min(max(1, int(page_size)), len(voice_ids))
    fully_feasible = required_sources <= max_sources and required_chars <= char_budget
    if fully_feasible:
        if observed_set & skill_ids != skill_ids:
            failures.append("skill_source_set_mismatch")
        if retained["voice"] != min(max(1, int(page_size)), len(voice_ids)):
            failures.append("voice_source_count_mismatch")
    else:
        minimum_lengths = [
            min((char_lengths.get(child_id, 0) for child_id in ids), default=0)
            for ids in (skill_ids, voice_ids)
            if ids
        ]
        can_cover_both = len(minimum_lengths) == 2 and max_sources >= 2 and sum(minimum_lengths) <= char_budget
        if can_cover_both:
            for intent in ("skill", "voice"):
                if retained[intent] == 0:
                    failures.append(f"intent_coverage_missing:{intent}")
    return failures


def _voice_observations(panel: Mapping[str, Any]) -> tuple[list[str], list[str], dict[str, list[Mapping[str, Any]]]]:
    line_ids: list[str] = []
    media_ids: list[str] = []
    variants_by_line: dict[str, list[Mapping[str, Any]]] = {}
    lines = panel.get("lines")
    if not isinstance(lines, list):
        return line_ids, media_ids, variants_by_line
    for line in lines:
        if not isinstance(line, Mapping):
            continue
        line_id = str(line.get("voice_line_id") or "")
        if line_id:
            line_ids.append(line_id)
        variants = line.get("variants")
        valid_variants = [item for item in variants if isinstance(item, Mapping)] if isinstance(variants, list) else []
        variants_by_line.setdefault(line_id, []).extend(valid_variants)
        media_ids.extend(
            _binding_identity(item) for item in valid_variants if _binding_identity(item)
        )
    return line_ids, media_ids, variants_by_line


def _evaluate_voice_content(inventory: CharacterInventory, panel: Mapping[str, Any]) -> list[str]:
    failures: list[str] = []
    if not inventory.entity_scope_valid:
        failures.append("invalid_entity_scope")
    line_ids, media_ids, variants_by_line = _voice_observations(panel)
    expected_lines = set(inventory.playable_voice_line_ids)
    expected_media = set(inventory.playable_media_ids)
    expected_by_line = dict(inventory.playable_media_by_line)
    language_by_media = dict(inventory.media_languages)
    for line_id in _duplicates(line_ids):
        failures.append(f"duplicate_voice_line_id:{line_id}")
    for media_id in _duplicates(media_ids):
        failures.append(f"duplicate_voice_media_id:{media_id}")
    for line_id in sorted(set(line_ids) - expected_lines):
        failures.append(f"foreign_voice_line_id:{line_id}")
    for media_id in sorted(set(media_ids) - expected_media):
        failures.append(f"foreign_voice_media_id:{media_id}")
    for line_id, variants in variants_by_line.items():
        if not variants:
            failures.append(f"empty_voice_line:{line_id}")
            continue
        actual_ids = [_binding_identity(item) for item in variants if _binding_identity(item)]
        if line_id in expected_by_line and Counter(actual_ids) != Counter(expected_by_line[line_id]):
            failures.append(f"voice_media_set_mismatch:{line_id}")
        for item in variants:
            media_id = _binding_identity(item)
            if media_id in language_by_media and str(item.get("language") or "") != language_by_media[media_id]:
                failures.append(f"voice_language_mismatch:{media_id}")
            child_id = str(item.get("child_id") or line_id)
            if child_id != line_id:
                failures.append(f"voice_child_mismatch:{media_id}")
            entity_id = str(item.get("entity_id") or _canonical_entity_scope(inventory))
            if inventory.entity_scope_valid and entity_id != inventory.entity_id:
                failures.append(f"foreign_voice_entity:{media_id}")
            if _contains_local_path(item):
                failures.append(f"local_path_leak:{media_id}")
    return failures


def evaluate_first_voice_page(
    inventory: CharacterInventory,
    panel: Mapping[str, Any] | None,
) -> list[str]:
    failures: list[str] = []
    if panel is None:
        return [] if not inventory.playable_voice_line_ids else ["missing_voice_panel"]
    if not isinstance(panel, Mapping):
        return ["invalid_voice_panel"]
    if panel.get("type") != "voice" or panel.get("grouping") != "voice_line":
        failures.append("voice_panel_contract_mismatch")
    if not inventory.entity_scope_valid:
        failures.append("invalid_entity_scope")
    elif str(panel.get("entity_id") or "") != inventory.entity_id:
        failures.append("voice_panel_entity_mismatch")
    page_size = panel.get("page_size")
    if type(page_size) is not int or page_size < 1:
        failures.append("voice_page_size_invalid")
        page_size = 1
    expected_line_ids = inventory.playable_voice_line_ids[:page_size]
    line_ids, media_ids, _variants = _voice_observations(panel)
    if tuple(line_ids) != expected_line_ids:
        failures.append("first_voice_line_set_mismatch")
    expected_media_by_line = dict(inventory.playable_media_by_line)
    expected_media_ids = [
        media_id for line_id in expected_line_ids for media_id in expected_media_by_line.get(line_id, ())
    ]
    if Counter(media_ids) != Counter(expected_media_ids):
        failures.append("first_voice_media_set_mismatch")
    if panel.get("total_lines") != len(inventory.playable_voice_line_ids):
        failures.append("voice_total_lines_mismatch")
    expected_has_more = len(expected_line_ids) < len(inventory.playable_voice_line_ids)
    if panel.get("has_more") is not expected_has_more:
        failures.append("voice_has_more_mismatch")
    cursor = panel.get("next_cursor")
    if expected_has_more != bool(cursor):
        failures.append("voice_next_cursor_mismatch")
    failures.extend(_evaluate_voice_content(inventory, panel))
    return list(dict.fromkeys(failures))


def evaluate_all_voice_pages(
    inventory: CharacterInventory,
    pages: Iterable[Mapping[str, Any]],
) -> list[str]:
    page_list = list(pages)
    artifact_conflicts = [
        f"artifact_media_id_reused_across_voice_lines:{media_id}"
        for media_id, _child_ids in inventory.media_id_line_conflicts
    ]
    if not page_list:
        return artifact_conflicts + ([] if not inventory.playable_voice_line_ids else ["missing_voice_pages"])
    failures: list[str] = list(artifact_conflicts)
    all_line_ids: list[str] = []
    all_media_ids: list[str] = []
    expected_page_size = page_list[0].get("page_size")
    expected_total = len(inventory.playable_voice_line_ids)
    valid_page_size = type(expected_page_size) is int and expected_page_size > 0
    expected_page_count = math.ceil(expected_total / expected_page_size) if valid_page_size else 0
    if len(page_list) != expected_page_count:
        failures.append("voice_page_count_mismatch")
    for index, page in enumerate(page_list):
        if not isinstance(page, Mapping):
            failures.append(f"invalid_voice_page:{index}")
            continue
        line_ids, media_ids, _variants = _voice_observations(page)
        all_line_ids.extend(line_ids)
        all_media_ids.extend(media_ids)
        if page.get("type") != "voice":
            failures.append(f"voice_page_type_mismatch:{index}")
        if page.get("grouping") != "voice_line":
            failures.append(f"voice_page_grouping_mismatch:{index}")
        if not inventory.entity_scope_valid:
            failures.append(f"invalid_entity_scope:{index}")
        elif str(page.get("entity_id") or "") != inventory.entity_id:
            failures.append(f"voice_page_entity_mismatch:{index}")
        page_size = page.get("page_size")
        if type(page_size) is not int or page_size < 1:
            failures.append(f"voice_page_size_invalid:{index}")
        elif page_size != expected_page_size:
            failures.append(f"voice_page_size_mismatch:{index}")
        if page.get("total_lines") != expected_total:
            failures.append(f"voice_total_lines_mismatch:{index}")
        expected_more = valid_page_size and index < expected_page_count - 1
        expected_line_count = (
            min(expected_page_size, max(0, expected_total - index * expected_page_size))
            if valid_page_size
            else 0
        )
        if len(line_ids) != expected_line_count:
            geometry = "nonterminal" if expected_more else "terminal"
            failures.append(f"voice_{geometry}_geometry_mismatch:{index}")
        if page.get("has_more") is not expected_more:
            failures.append(f"voice_has_more_mismatch:{index}")
        cursor = page.get("next_cursor")
        if expected_more and (not isinstance(cursor, str) or not cursor):
            failures.append(f"voice_next_cursor_mismatch:{index}")
        if not expected_more and cursor is not None:
            failures.append(f"voice_terminal_cursor_present:{index}")
        failures.extend(_evaluate_voice_content(inventory, page))
    for line_id in _duplicates(all_line_ids):
        failures.append(f"duplicate_voice_line_id:{line_id}")
    for media_id in _duplicates(all_media_ids):
        failures.append(f"duplicate_voice_media_id:{media_id}")
    if tuple(all_line_ids) != inventory.playable_voice_line_ids:
        failures.append("all_voice_line_set_mismatch")
    if Counter(all_media_ids) != Counter(inventory.playable_media_ids):
        failures.append("all_voice_media_set_mismatch")
    return list(dict.fromkeys(failures))


def evaluate_media_union(route_debug: Mapping[str, Any] | None, media: Iterable[Mapping[str, Any]]) -> list[str]:
    failures: list[str] = []
    requested, _debug = _route_parts(route_debug)
    if requested != ("skill", "voice"):
        failures.append("requested_intents_mismatch")
    media_items = [item for item in media if isinstance(item, Mapping)]
    media_ids = [_binding_identity(item) for item in media_items if _binding_identity(item)]
    for media_id in _duplicates(media_ids):
        failures.append(f"duplicate_media_id:{media_id}")
    types = {str(item.get("asset_type") or item.get("role") or "").casefold() for item in media_items}
    if not (types & {"skill", "ultimate"}):
        failures.append("media_strategy_missing:skill")
    if "voice" not in types:
        failures.append("media_strategy_missing:voice")
    if _contains_local_path(media_items):
        failures.append("local_path_leak")
    return failures


class EvaluationTransportError(RuntimeError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def parse_sse_events(chunks: Iterable[bytes | str]) -> list[dict[str, Any]]:
    """Parse chunked SSE, including CRLF and multiline data fields."""
    decoder = codecs.getincrementaldecoder("utf-8")()
    decoded: list[str] = []
    try:
        for chunk in chunks:
            if isinstance(chunk, bytes):
                decoded.append(decoder.decode(chunk))
            else:
                decoded.append(decoder.decode(b"", final=False))
                decoded.append(str(chunk))
        decoded.append(decoder.decode(b"", final=True))
    except UnicodeDecodeError as exc:
        raise EvaluationTransportError("invalid_sse_utf8") from exc

    text = "".join(decoded).replace("\r\n", "\n").replace("\r", "\n")
    events: list[dict[str, Any]] = []
    for block in re.split(r"\n\n+", text):
        if not block.strip():
            continue
        event_name = "message"
        data_lines: list[str] = []
        for line in block.split("\n"):
            if not line or line.startswith(":"):
                continue
            field, separator, value = line.partition(":")
            if separator and value.startswith(" "):
                value = value[1:]
            if field == "event":
                event_name = value or "message"
            elif field == "data":
                data_lines.append(value if separator else "")
        if not data_lines:
            continue
        try:
            payload = json.loads("\n".join(data_lines))
        except json.JSONDecodeError as exc:
            raise EvaluationTransportError("invalid_sse_json") from exc
        if not isinstance(payload, dict):
            raise EvaluationTransportError("invalid_sse_payload")
        events.append({"event": event_name, "data": payload})
    return events


def _endpoint(base_url: str, path: str) -> str:
    return f"{str(base_url).rstrip('/')}/{path.lstrip('/')}"


def _read_bounded(response: Any, byte_limit: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = response.read(min(4096, byte_limit + 1 - total))
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
        if total > byte_limit:
            raise EvaluationTransportError("response_too_large")
    return b"".join(chunks)


def _transport_error(exc: BaseException) -> EvaluationTransportError:
    if isinstance(exc, EvaluationTransportError):
        return exc
    if isinstance(exc, HTTPError):
        return EvaluationTransportError(f"http_status_{exc.code}")
    if isinstance(exc, (TimeoutError, socket.timeout)):
        return EvaluationTransportError("timeout")
    if isinstance(exc, URLError):
        if isinstance(exc.reason, (TimeoutError, socket.timeout)):
            return EvaluationTransportError("timeout")
        return EvaluationTransportError("network_error")
    if isinstance(exc, OSError):
        return EvaluationTransportError("network_error")
    return EvaluationTransportError("transport_error")


def fetch_sse_events(base_url: str, question: str, *, timeout: float = DEFAULT_HTTP_TIMEOUT) -> list[dict[str, Any]]:
    body = json.dumps({"question": question}, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    request = Request(
        _endpoint(base_url, "/ask/stream"),
        data=body,
        headers={"Accept": "text/event-stream", "Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=max(0.1, float(timeout))) as response:
            chunks: list[bytes] = []
            total = 0
            while True:
                chunk = response.read(4096)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_SSE_BYTES:
                    raise EvaluationTransportError("response_too_large")
                chunks.append(chunk)
    except (HTTPError, URLError, TimeoutError, socket.timeout, OSError, EvaluationTransportError) as exc:
        raise _transport_error(exc) from exc
    return parse_sse_events(chunks)


def fetch_voice_page(base_url: str, cursor: str, *, timeout: float = DEFAULT_HTTP_TIMEOUT) -> dict[str, Any]:
    query = urlencode({"cursor": cursor})
    request = Request(
        f"{_endpoint(base_url, '/api/media/voice/page')}?{query}",
        headers={"Accept": "application/json"},
        method="GET",
    )
    try:
        with urlopen(request, timeout=max(0.1, float(timeout))) as response:
            raw = _read_bounded(response, MAX_JSON_BYTES)
    except (HTTPError, URLError, TimeoutError, socket.timeout, OSError, EvaluationTransportError) as exc:
        raise _transport_error(exc) from exc
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvaluationTransportError("invalid_json_response") from exc
    if not isinstance(payload, dict):
        raise EvaluationTransportError("invalid_json_response")
    return payload


def follow_voice_pages(
    base_url: str,
    first_panel: Mapping[str, Any] | None,
    *,
    timeout: float = DEFAULT_HTTP_TIMEOUT,
    max_pages: int | None = None,
) -> list[dict[str, Any]]:
    if first_panel is None:
        return []
    page_size = first_panel.get("page_size")
    total_lines = first_panel.get("total_lines")
    if type(page_size) is not int or page_size < 1 or type(total_lines) is not int or total_lines < 1:
        raise EvaluationTransportError("invalid_voice_page_geometry")
    declared_pages = math.ceil(total_lines / page_size)
    if declared_pages > MAX_VOICE_PAGES:
        raise EvaluationTransportError("voice_page_absolute_limit_exceeded")
    page_limit = declared_pages
    if max_pages is not None:
        page_limit = min(page_limit, max(1, int(max_pages)))
    pages = [dict(first_panel)]
    seen_cursors: set[str] = set()
    while bool(pages[-1].get("has_more")):
        cursor = str(pages[-1].get("next_cursor") or "")
        if not cursor:
            raise EvaluationTransportError("missing_next_cursor")
        if len(pages) >= page_limit:
            raise EvaluationTransportError("voice_page_limit_exceeded")
        if cursor in seen_cursors:
            raise EvaluationTransportError("repeated_next_cursor")
        seen_cursors.add(cursor)
        pages.append(fetch_voice_page(base_url, cursor, timeout=timeout))
    return pages


def _is_structured_voice_panel(panel: Mapping[str, Any]) -> bool:
    return bool(
        panel.get("type") == "voice"
        and panel.get("grouping") == "voice_line"
        and isinstance(panel.get("entity_id"), str)
        and panel.get("entity_id")
        and isinstance(panel.get("lines"), list)
        and type(panel.get("page_size")) is int
        and panel.get("page_size") > 0
        and type(panel.get("total_lines")) is int
        and panel.get("total_lines") >= 0
        and type(panel.get("has_more")) is bool
        and (panel.get("next_cursor") is None or isinstance(panel.get("next_cursor"), str))
    )


def _voice_panel(
    payload: Mapping[str, Any],
    *,
    context: str,
    required: bool,
) -> tuple[Mapping[str, Any] | None, list[str]]:
    panels = payload.get("media_panels")
    failures: list[str] = []
    valid_voice_panels: list[Mapping[str, Any]] = []
    if not isinstance(panels, list):
        failures.append(f"{context}_media_panels_invalid")
        panels = []
    for index, panel in enumerate(panels):
        if not isinstance(panel, Mapping):
            failures.append(f"malformed_media_panel:{index}")
            continue
        if panel.get("type") == "voice":
            if _is_structured_voice_panel(panel):
                valid_voice_panels.append(panel)
            else:
                failures.append(f"malformed_voice_panel:{index}")
        elif panel.get("type") == "video":
            if not isinstance(panel.get("items"), list) or not panel["items"]:
                failures.append(f"malformed_media_panel:{index}")
        else:
            failures.append(f"malformed_media_panel:{index}")
    expected_count = 1 if required else 0
    if len(valid_voice_panels) != expected_count:
        failures.append(f"{context}_voice_panel_count:{len(valid_voice_panels)}")
    return (valid_voice_panels[0] if valid_voice_panels else None), failures


def _event_payload(events: Sequence[Mapping[str, Any]], event_name: str) -> tuple[dict[str, Any], list[str]]:
    matches = [event.get("data") for event in events if event.get("event") == event_name]
    failures: list[str] = []
    if len(matches) != 1:
        failures.append(f"sse_{event_name}_event_count:{len(matches)}")
    if matches and not isinstance(matches[0], dict):
        failures.append(f"sse_{event_name}_payload_invalid")
    payload = matches[0] if matches and isinstance(matches[0], dict) else {}
    return dict(payload), failures


def _transcript_payload_failures(payload: Mapping[str, Any], context: str) -> list[str]:
    failures: list[str] = []
    sources = payload.get("sources")
    if not isinstance(sources, list):
        failures.append(f"{context}_sources_invalid")
    else:
        for index, source in enumerate(sources):
            if not isinstance(source, Mapping) or not str(source.get("child_id") or ""):
                failures.append(f"{context}_source_invalid:{index}")
    if not isinstance(payload.get("route"), Mapping):
        failures.append(f"{context}_route_invalid")
    if not isinstance(payload.get("media"), list):
        failures.append(f"{context}_media_invalid")
    if context == "done" and (
        not isinstance(payload.get("answer"), str) or not payload["answer"].strip()
    ):
        failures.append("done_answer_missing")
    return failures


def _media_ids(items: Any) -> list[str]:
    if not isinstance(items, list):
        return []
    return [
        _binding_identity(item)
        for item in items
        if isinstance(item, Mapping) and _binding_identity(item)
    ]


def _media_types(items: Any) -> list[str]:
    if not isinstance(items, list):
        return []
    return sorted({
        str(item.get("asset_type") or item.get("role") or "").casefold()
        for item in items
        if isinstance(item, Mapping) and (item.get("asset_type") or item.get("role"))
    })


def _dynamic_expectations(inventory: CharacterInventory, page_size: int) -> dict[str, Any]:
    char_lengths = dict(inventory.child_char_lengths)
    voice_target = min(page_size, len(inventory.voice_text_child_ids))
    required_voice_chars = sorted(char_lengths.get(child_id, 0) for child_id in inventory.voice_text_child_ids)[:voice_target]
    return {
        "entity_id": inventory.entity_id,
        "entity_scope": _canonical_entity_scope(inventory),
        "entity_scope_valid": inventory.entity_scope_valid,
        "S": list(inventory.skill_child_ids),
        "T": list(inventory.voice_text_child_ids),
        "V": list(inventory.playable_voice_line_ids),
        "M": list(inventory.playable_media_ids),
        "skill_media_ids": list(inventory.skill_media_ids),
        "languages": list(inventory.languages),
        "child_char_lengths": char_lengths,
        "voice_media_by_line": {
            line_id: list(media_ids)
            for line_id, media_ids in inventory.playable_media_by_line
        },
        "text_only_voice_ids": sorted(
            set(inventory.voice_text_child_ids) - set(inventory.playable_voice_line_ids)
        ),
        "media_id_line_conflicts": {
            media_id: list(child_ids)
            for media_id, child_ids in inventory.media_id_line_conflicts
        },
        "missing_sections": [
            section
            for section, values in (
                ("skill", inventory.skill_child_ids),
                ("voice", inventory.voice_text_child_ids),
            )
            if not values
        ],
        "voice_text_target": voice_target,
        "required_source_count": len(inventory.skill_child_ids) + voice_target,
        "minimum_required_chars": (
            sum(char_lengths.get(child_id, 0) for child_id in inventory.skill_child_ids)
            + sum(required_voice_chars)
        ),
    }


def _evaluate_entity(
    item: CharacterInventory,
    *,
    base_url: str,
    page_size: int,
    budgets: Mapping[str, int],
    timeout: float,
    sample_type: str | None = None,
) -> dict[str, Any]:
    query = QUERY_TEMPLATE.format(entity_name=item.entity_name)
    expectations = _dynamic_expectations(item, page_size)
    resolved_sample_type = sample_type or ("eligible" if _is_eligible(item) else "anomaly")
    evaluation: dict[str, Any] = {
        "entity_id": item.entity_id,
        "entity_scope": _canonical_entity_scope(item),
        "entity_scope_valid": item.entity_scope_valid,
        "entity_name": item.entity_name,
        "sample_type": resolved_sample_type,
        "query": query,
        "dynamic_expectations": expectations,
        "observed": {},
        "failures": [],
        "pass": False,
    }
    failures: list[str] = []
    if not item.entity_scope_valid:
        failures.append("invalid_entity_scope")
    try:
        events = fetch_sse_events(base_url, query, timeout=timeout)
    except EvaluationTransportError as exc:
        failures.append(f"transport_error:{exc.code}")
        evaluation["failures"] = failures
        return evaluation

    sources_payload, event_failures = _event_payload(events, "sources")
    failures.extend(event_failures)
    done_payload, event_failures = _event_payload(events, "done")
    failures.extend(event_failures)
    failures.extend(_transcript_payload_failures(sources_payload, "sources"))
    failures.extend(_transcript_payload_failures(done_payload, "done"))
    for event in events:
        if event.get("event") == "error":
            failures.append("sse_error_event")

    sources = sources_payload.get("sources")
    source_ids = [
        str(source.get("child_id") or "")
        for source in sources
        if isinstance(source, Mapping) and source.get("child_id")
    ] if isinstance(sources, list) else []
    route = sources_payload.get("route") if isinstance(sources_payload.get("route"), Mapping) else {}
    media = sources_payload.get("media") if isinstance(sources_payload.get("media"), list) else []
    requires_voice_panel = bool(item.playable_voice_line_ids)
    first_panel, panel_failures = _voice_panel(
        sources_payload,
        context="sources",
        required=requires_voice_panel,
    )
    failures.extend(panel_failures)
    done_panel, panel_failures = _voice_panel(
        done_payload,
        context="done",
        required=requires_voice_panel,
    )
    failures.extend(panel_failures)
    if first_panel is not None and first_panel.get("page_size") != page_size:
        failures.append("voice_page_size_config_mismatch")
    if not item.playable_voice_line_ids and first_panel is not None:
        failures.append("unexpected_empty_voice_panel")
    pages = [dict(first_panel)] if first_panel is not None else []
    try:
        pages = follow_voice_pages(
            base_url,
            first_panel,
            timeout=timeout,
        )
    except EvaluationTransportError as exc:
        failures.append(f"transport_error:{exc.code}")

    failures.extend(evaluate_sources(item, source_ids, route, page_size, budgets))
    failures.extend(evaluate_first_voice_page(item, first_panel))
    failures.extend(evaluate_all_voice_pages(item, pages))
    if _is_eligible(item):
        failures.extend(evaluate_media_union(route, media))
    elif _contains_local_path(media):
        failures.append("local_path_leak")

    first_line_ids, first_media_ids, _first_variants = (
        _voice_observations(first_panel) if first_panel is not None else ([], [], {})
    )
    all_line_ids: list[str] = []
    all_media_ids: list[str] = []
    for page in pages:
        line_ids, page_media_ids, _variants = _voice_observations(page)
        all_line_ids.extend(line_ids)
        all_media_ids.extend(page_media_ids)

    text_only_voice_ids = sorted(
        set(item.voice_text_child_ids) - set(item.playable_voice_line_ids)
    )
    retained_text_only_voice_ids = (
        sorted(set(source_ids) & set(text_only_voice_ids))
        if resolved_sample_type == "anomaly"
        else []
    )
    sampled_text_only_voice_child_id = (
        retained_text_only_voice_ids[0]
        if retained_text_only_voice_ids
        else None
    )
    sampled_text_only_source_retained = (
        bool(retained_text_only_voice_ids)
        if resolved_sample_type == "anomaly" and text_only_voice_ids
        else None
    )
    retained_text_only_player_row_ids = sorted(
        set(retained_text_only_voice_ids) & set(all_line_ids)
    )
    sampled_text_only_player_row_emitted = (
        bool(retained_text_only_player_row_ids)
        if resolved_sample_type == "anomaly" and text_only_voice_ids
        else None
    )
    if resolved_sample_type == "anomaly" and text_only_voice_ids:
        voice_target = min(max(1, int(page_size)), len(item.voice_text_child_ids))
        text_only_source_required = voice_target > len(item.playable_voice_line_ids)
        if text_only_source_required and not retained_text_only_voice_ids:
            failures.append("anomaly_text_only_voice_source_missing")
        for child_id in retained_text_only_player_row_ids:
            failures.append(
                f"anomaly_text_only_voice_player_row_emitted:{child_id}"
            )

    top_media_ids = _media_ids(media)
    top_voice_ids = {
        _binding_identity(media_item)
        for media_item in media
        if isinstance(media_item, Mapping)
        and str(media_item.get("asset_type") or media_item.get("role") or "").casefold() == "voice"
    }
    if top_voice_ids != set(first_media_ids):
        failures.append("top_level_voice_media_mismatch")
    known_skill_media = set(item.skill_media_ids)
    for media_item in media:
        if not isinstance(media_item, Mapping):
            continue
        media_type = str(media_item.get("asset_type") or media_item.get("role") or "").casefold()
        media_id = _binding_identity(media_item)
        if media_type in {"skill", "ultimate"} and media_id not in known_skill_media:
            failures.append(f"foreign_skill_media_id:{media_id}")

    if _media_ids(done_payload.get("media")) != top_media_ids:
        failures.append("sse_done_media_mismatch")
    done_sources = done_payload.get("sources")
    done_source_ids = [
        str(source.get("child_id") or "")
        for source in done_sources
        if isinstance(source, Mapping) and source.get("child_id")
    ] if isinstance(done_sources, list) else []
    if done_source_ids != source_ids:
        failures.append("sse_done_sources_mismatch")
    if done_payload.get("route") != route:
        failures.append("sse_done_route_mismatch")
    if done_panel != first_panel:
        failures.append("sse_done_voice_panel_mismatch")
    if _contains_local_path([sources_payload, done_payload, pages]):
        failures.append("local_path_leak")

    requested, observed_debug = _route_parts(route)
    child_char_lengths = dict(item.child_char_lengths)
    evaluation["observed"] = {
        "requested_intents": list(requested),
        "retrieval_debug": dict(observed_debug),
        "source_ids": source_ids,
        "source_skill_ids": sorted(set(source_ids) & set(item.skill_child_ids)),
        "source_voice_ids": sorted(set(source_ids) & set(item.voice_text_child_ids)),
        "source_count": len(source_ids),
        "source_chars": sum(
            child_char_lengths[child_id]
            for child_id in source_ids
            if child_id in child_char_lengths
        ),
        "first_voice_line_ids": first_line_ids,
        "first_voice_media_ids": first_media_ids,
        "first_page_size": first_panel.get("page_size") if first_panel is not None else None,
        "first_total_lines": first_panel.get("total_lines") if first_panel is not None else None,
        "first_has_more": first_panel.get("has_more") if first_panel is not None else None,
        "all_voice_line_ids": all_line_ids,
        "all_voice_media_ids": all_media_ids,
        "page_count": len(pages),
        "page_total_lines": [page.get("total_lines") for page in pages],
        "top_level_media_ids": top_media_ids,
        "media_types": _media_types(media),
        "retained_text_only_voice_ids": retained_text_only_voice_ids,
        "sampled_text_only_voice_child_id": sampled_text_only_voice_child_id,
        "sampled_text_only_voice_source_retained": sampled_text_only_source_retained,
        "sampled_text_only_voice_player_row_emitted": sampled_text_only_player_row_emitted,
        "text_only_source_required_by_quota": (
            min(max(1, int(page_size)), len(item.voice_text_child_ids))
            > len(item.playable_voice_line_ids)
        ),
    }

    evaluation["failures"] = list(dict.fromkeys(failures))
    evaluation["pass"] = not evaluation["failures"]
    return evaluation


def run_evaluation(
    cfg: Any,
    *,
    base_url: str,
    inventory: Iterable[CharacterInventory],
    before_snapshot_reference: str,
    limit: int = 8,
    timeout: float = DEFAULT_HTTP_TIMEOUT,
) -> dict[str, Any]:
    inventory_list = list(inventory)
    selected = select_stratified_characters(inventory_list, limit=REQUIRED_ELIGIBLE_SAMPLE_LIMIT)
    eligible_sample_count = min(
        REQUIRED_ELIGIBLE_SAMPLE_LIMIT,
        sum(1 for item in inventory_list if _is_eligible(item)),
    )
    retrieval = getattr(cfg, "retrieval")
    page_size_max = max(1, int(getattr(retrieval, "voice_page_size_max", 20) or 20))
    page_size = min(page_size_max, max(1, int(getattr(retrieval, "voice_page_size", 8) or 8)))
    configured_top_k = max(0, int(getattr(getattr(cfg, "rag"), "top_k", 0) or 0))
    configured_max_sources = max(1, int(getattr(retrieval, "max_sources", 20) or 20))
    budgets = {
        "max_sources": min(configured_top_k, configured_max_sources),
        "context_budget_chars": max(0, int(getattr(retrieval, "context_budget_chars", 0) or 0)),
    }
    evaluations = [
        _evaluate_entity(
            item,
            base_url=base_url,
            page_size=page_size,
            budgets=budgets,
            timeout=timeout,
            sample_type="eligible" if index < eligible_sample_count else "anomaly",
        )
        for index, item in enumerate(selected)
    ]
    report_failures: list[str] = []
    if eligible_sample_count == 0:
        report_failures.append("no_eligible_characters")
    for evaluation in evaluations:
        report_failures.extend(
            f"{evaluation['entity_id']}:{failure}"
            for failure in evaluation["failures"]
        )
    return {
        "config": {
            "base_url": str(base_url).rstrip("/"),
            "query_template": QUERY_TEMPLATE,
            "sample_limit": REQUIRED_ELIGIBLE_SAMPLE_LIMIT,
            "requested_limit": int(limit),
            "timeout_seconds": float(timeout),
            "voice_page_size": page_size,
            "voice_page_size_max": page_size_max,
            **budgets,
        },
        "before_snapshot_reference": before_snapshot_reference,
        "eligible_character_count": sum(1 for item in inventory_list if _is_eligible(item)),
        "eligible_sample_count": eligible_sample_count,
        "anomaly_sample_count": max(0, len(selected) - eligible_sample_count),
        "selected_entities": [item.entity_id for item in selected],
        "selected_entity_scopes": [_canonical_entity_scope(item) for item in selected],
        "evaluations": evaluations,
        "failures": report_failures,
        "overall_pass": bool(evaluations) and not report_failures,
    }


def _is_eligible(item: CharacterInventory) -> bool:
    return bool(item.skill_child_ids and item.voice_text_child_ids and item.playable_voice_line_ids)


def _is_anomaly(item: CharacterInventory) -> bool:
    missing_section = not item.skill_child_ids or not item.voice_text_child_ids
    no_playable_media = bool(item.voice_text_child_ids) and not item.playable_voice_line_ids
    partial_playable = bool(
        item.playable_voice_line_ids
        and set(item.voice_text_child_ids) - set(item.playable_voice_line_ids)
    )
    return missing_section or no_playable_media or partial_playable


def _anomaly_sort_key(item: CharacterInventory) -> tuple[int, str]:
    if item.playable_voice_line_ids and set(item.voice_text_child_ids) - set(item.playable_voice_line_ids):
        kind = 0
    elif not item.playable_voice_line_ids:
        kind = 1
    else:
        kind = 2
    return kind, item.entity_id


def _select_unique(selected: list[CharacterInventory], candidate: CharacterInventory) -> None:
    if candidate not in selected:
        selected.append(candidate)


def select_stratified_characters(
    inventory: Iterable[CharacterInventory], limit: int = 8
) -> list[CharacterInventory]:
    eligible = sorted(
        (item for item in inventory if _is_eligible(item)),
        key=lambda item: (len(item.playable_voice_line_ids), item.entity_id),
    )
    target_count = min(max(0, limit), len(eligible))
    selected: list[CharacterInventory] = []

    if target_count == 1:
        _select_unique(selected, eligible[0])
    elif target_count == 2:
        _select_unique(selected, eligible[0])
        _select_unique(selected, eligible[-1])
    elif target_count >= 3:
        _select_unique(selected, eligible[0])
        _select_unique(selected, eligible[len(eligible) // 2])
        _select_unique(selected, eligible[-1])

    for measure in (lambda item: len(item.skill_child_ids), lambda item: len(item.languages)):
        if len(selected) >= target_count or not eligible:
            break
        _select_unique(selected, min(eligible, key=lambda item: (measure(item), item.entity_id)))
        if len(selected) >= target_count:
            break
        _select_unique(selected, max(eligible, key=lambda item: (measure(item), item.entity_id)))

    if target_count:
        for index in range(target_count):
            if len(selected) >= target_count:
                break
            position = round(index * (len(eligible) - 1) / max(target_count - 1, 1))
            _select_unique(selected, eligible[position])
        for item in eligible:
            if len(selected) >= target_count:
                break
            _select_unique(selected, item)

    anomalies = sorted(
        (item for item in inventory if _is_anomaly(item) and item not in selected),
        key=_anomaly_sort_key,
    )
    if anomalies:
        selected.append(anomalies[0])
    return selected


def capture_collection_snapshot(cfg: Any) -> dict[str, object]:
    vectorstore = getattr(cfg, "vectorstore")
    collection_name = str(getattr(vectorstore, "collection_name"))
    client = MilvusClient(uri=str(getattr(vectorstore, "uri")), db_name=str(getattr(vectorstore, "db_name")))
    exists = bool(client.has_collection(collection_name))
    if not exists:
        return {
            "collection_name": collection_name,
            "exists": False,
            "schema": None,
            "row_count": None,
        }
    schema = client.describe_collection(collection_name)
    stats = client.get_collection_stats(collection_name)
    return {
        "collection_name": collection_name,
        "exists": True,
        "schema": schema,
        "row_count": int(stats.get("row_count", 0)),
    }


def compare_collection_snapshots(before: dict[str, object], after: dict[str, object]) -> list[str]:
    changes: list[str] = []
    for field in ("collection_name", "schema", "row_count"):
        if before.get(field) != after.get(field):
            changes.append(f"{field} changed")
    return changes


def _inventory_payload(inventory: list[CharacterInventory], limit: int) -> dict[str, object]:
    samples = select_stratified_characters(inventory, limit=limit)
    return {
        "eligible_character_count": sum(1 for item in inventory if _is_eligible(item)),
        "sampled_character_count": len(samples),
        "samples": [
            {
                "entity_id": item.entity_id,
                "entity_scope": _canonical_entity_scope(item),
                "entity_scope_valid": item.entity_scope_valid,
                "entity_name": item.entity_name,
                "S": list(item.skill_child_ids),
                "T": list(item.voice_text_child_ids),
                "V": list(item.playable_voice_line_ids),
                "M": list(item.playable_media_ids),
                "languages": list(item.languages),
            }
            for item in samples
        ],
    }


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _read_json_object(path: str | Path) -> dict[str, object]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"snapshot must be a JSON object: {path}")
    return payload


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read-only P0 multi-intent and voice evaluator setup.")
    parser.add_argument("command", choices=("inventory", "snapshot", "evaluate", "compare-snapshots"))
    parser.add_argument("--output")
    parser.add_argument("--before")
    parser.add_argument("--after")
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--timeout", type=float, default=DEFAULT_HTTP_TIMEOUT)
    parser.add_argument(
        "--before-snapshot",
        default="eval/multi_intent_voice_collection_before.json",
    )
    args = parser.parse_args()
    if args.command == "compare-snapshots":
        if not args.before or not args.after:
            parser.error("compare-snapshots requires --before and --after")
    elif not args.output:
        parser.error(f"{args.command} requires --output")
    return args


def main() -> int:
    args = _parse_args()
    if args.command == "compare-snapshots":
        failures = compare_collection_snapshots(
            _read_json_object(args.before),
            _read_json_object(args.after),
        )
        payload = {"failures": failures, "overall_pass": not failures}
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return 0 if not failures else 1

    cfg = get_config()
    output_path = Path(args.output)
    if args.command in {"inventory", "evaluate"}:
        snapshot = resolve_runtime_artifact_snapshot(cfg)
        inventory = build_character_inventory(
            iter_jsonl(snapshot.child_blocks), iter_jsonl(snapshot.media_assets)
        )
        if args.command == "inventory":
            payload = _inventory_payload(inventory, limit=args.limit)
        else:
            payload = run_evaluation(
                cfg,
                base_url=args.base_url,
                inventory=inventory,
                before_snapshot_reference=args.before_snapshot,
                limit=args.limit,
                timeout=args.timeout,
            )
    else:
        payload = capture_collection_snapshot(cfg)
    _write_json(output_path, payload)
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    if args.command == "evaluate" and payload.get("overall_pass") is not True:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
