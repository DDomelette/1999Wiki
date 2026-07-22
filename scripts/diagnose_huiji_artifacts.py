from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.config import get_config
from src.huiji_rag.io import build_paths, iter_jsonl
from src.huiji_rag.diagnostics import (
    build_quarantine_listing,
    classify_binding_conflicts,
    expand_conflict_closure,
)
from src.huiji_rag.models import BindingRecord, ResourceRow, VoiceSourceRow
from src.huiji_rag.normalizer import ascii_filename_key, expected_voice_filename
from src.huiji_rag.voice_binding import bind_voice_row, index_voice_resources


LOCAL_PATH_MARKERS = ("D:\\", "C:\\", "file://", "..\\")
REQUIRED_MEDIA_FIELDS = (
    "media_id",
    "entity_name",
    "parent_id",
    "child_id",
    "asset_type",
    "attach_policy",
    "object_key",
    "url",
)
_TRANSCRIPT_FIELDS = (
    ("content", "zh"),
    ("encontent", "en"),
    ("twcontent", "zh-hant"),
    ("jpcontent", "jp"),
    ("kocontent", "kr"),
)
_RESOURCE_PREFIXES = (
    ("Zh_", "zh"),
    ("En_", "en"),
    ("Tw_", "zh-hant"),
    ("Jp_", "jp"),
    ("Kr_", "kr"),
)
_R03_LISTING_NAME = "task-3-r03-cross-child-listing.v1.json"
_R03_CURRENT_NAME = "task-3-r03-current.json"
_CHAR_DATA_TITLE_RE = re.compile(r"Data:Char/[^/]+\.json\Z")


def _is_http_url(value: Any) -> bool:
    text = str(value or "").strip()
    return text.startswith(("http://", "https://"))


def _has_local_path_marker(value: Any) -> bool:
    text = str(value or "")
    return any(marker in text for marker in LOCAL_PATH_MARKERS)


def _load_manifest(processed_dir: Path) -> dict[str, Any]:
    manifest = processed_dir / "build_manifest.json"
    if not manifest.exists():
        return {}
    return json.loads(manifest.read_text(encoding="utf-8"))


def _media_ids_from_children(children: Iterable[dict[str, Any]]) -> set[str]:
    ids: set[str] = set()
    for child in children:
        for media_id in child.get("media_ids") or []:
            text = str(media_id or "").strip()
            if text:
                ids.add(text)
    return ids


def diagnose_binding_records(rows: Sequence[BindingRecord]) -> dict[str, Any]:
    """Return a serializable read-only conflict and runtime-projection summary."""
    result = classify_binding_conflicts(rows)
    return {
        "binding_records": len(rows),
        "fatal_ids": list(result.fatal_ids),
        "quarantined_ids": list(result.quarantined_ids),
        "shortfall_ids": list(result.shortfall_ids),
        "exact_ids": list(result.exact_ids),
        "runtime_ids": list(result.runtime_ids),
        "stop_mutations": result.stop_mutations,
        "root_causes": {key: list(value) for key, value in result.root_causes.items()},
        "quality_flags_by_id": {
            key: list(value) for key, value in result.quality_flags_by_id.items()
        },
    }


def diagnose_artifacts(processed_dir: str | Path, raw_root: str | Path | None = None) -> dict[str, Any]:
    processed = Path(processed_dir)
    manifest = _load_manifest(processed)
    media_path = processed / "media_assets.jsonl"
    child_path = processed / "child_blocks.jsonl"
    media_rows = list(iter_jsonl(media_path)) if media_path.exists() else []
    child_rows = list(iter_jsonl(child_path)) if child_path.exists() else []

    required_missing: list[dict[str, Any]] = []
    non_http_url_count = 0
    local_path_url_count = 0
    object_keys: list[str] = []
    local_missing = 0
    raw = Path(raw_root) if raw_root else None

    for row in media_rows:
        missing_fields = [field for field in REQUIRED_MEDIA_FIELDS if not str(row.get(field) or "").strip()]
        if missing_fields:
            required_missing.append({"media_id": row.get("media_id", ""), "missing_fields": missing_fields})
        url = row.get("url", "")
        if not _is_http_url(url):
            non_http_url_count += 1
        if _has_local_path_marker(url):
            local_path_url_count += 1
        object_key = str(row.get("object_key") or "").strip()
        if object_key:
            object_keys.append(object_key)
        if raw is not None and row.get("local_relpath"):
            if not (raw / str(row["local_relpath"])).exists():
                local_missing += 1

    media_ids = {str(row.get("media_id") or "") for row in media_rows if str(row.get("media_id") or "")}
    child_media_ids = _media_ids_from_children(child_rows)
    missing_asset_ids = sorted(child_media_ids - media_ids)
    media_without_child_reference = sorted(media_ids - child_media_ids)

    return {
        "build_version": manifest.get("build_version", processed.name),
        "processed_dir": str(processed),
        "media_records": len(media_rows),
        "child_records": len(child_rows),
        "unique_object_keys": len(set(object_keys)),
        "duplicate_object_key_records": len(object_keys) - len(set(object_keys)),
        "asset_type_counts": dict(Counter(str(row.get("asset_type") or "unknown") for row in media_rows)),
        "attach_policy_counts": dict(Counter(str(row.get("attach_policy") or "unknown") for row in media_rows)),
        "non_http_url_count": non_http_url_count,
        "local_path_url_count": local_path_url_count,
        "missing_required_field_count": sum(len(item["missing_fields"]) for item in required_missing),
        "missing_required_field_samples": required_missing[:20],
        "child_media_missing_asset_count": len(missing_asset_ids),
        "child_media_missing_asset_samples": missing_asset_ids[:20],
        "media_without_child_reference_count": len(media_without_child_reference),
        "media_without_child_reference_samples": media_without_child_reference[:20],
        "missing_local_file_count": local_missing,
    }


def default_processed_dir(cfg: Any) -> Path:
    return build_paths(cfg).build_root


def voice_source_rows_from_data_pages(rows: Iterable[dict[str, Any]]) -> tuple[VoiceSourceRow, ...]:
    """Extract only non-empty localized EventName transcripts from character data pages."""
    sources: list[VoiceSourceRow] = []
    for page in rows:
        title = str(page.get("title") or "")
        if not _CHAR_DATA_TITLE_RE.fullmatch(title):
            continue
        payload = page.get("content")
        if isinstance(payload, str):
            payload = json.loads(payload)
        if not isinstance(payload, dict):
            continue
        for voice in payload.get("character_voice") or []:
            if not isinstance(voice, dict):
                continue
            event_name = voice.get("eventName")
            if not isinstance(event_name, str) or not event_name.strip():
                continue
            hero_id = str(voice.get("heroId") or "")
            audio_id = str(voice.get("audio") or "")
            if not hero_id or not audio_id:
                continue
            for field, language in _TRANSCRIPT_FIELDS:
                transcript = voice.get(field)
                if not isinstance(transcript, str) or not transcript.strip():
                    continue
                canonical_language = language
                parent_id = f"char:{hero_id}/voice"
                sources.append(
                    VoiceSourceRow(
                        source_id=f"{title}:{audio_id}:{canonical_language}",
                        entity_id=f"char:{hero_id}",
                        parent_id=parent_id,
                        child_id=f"{parent_id}:{audio_id}",
                        audio_id=audio_id,
                        event_name=event_name,
                        language=canonical_language,
                        transcript=str(transcript),
                    )
                )
    return tuple(sorted(sources, key=lambda row: row.source_id))


def resource_rows_for_sources(
    manifest_rows: Iterable[dict[str, Any]],
    source_rows: Sequence[VoiceSourceRow],
    raw_root: Path,
    *,
    object_prefix: str = "reverse1999",
    sha256_for_path: Any | None = None,
) -> tuple[tuple[ResourceRow, ...], dict[str, int]]:
    """Hash only manifest resources whose exact language/filename key is source-required."""
    digest = sha256_for_path or _file_sha256
    needed_keys = {
        (source.language, ascii_filename_key(expected_voice_filename(source.event_name, source.language)))
        for source in source_rows
    }
    resources: list[ResourceRow] = []
    voice_resource_rows = 0
    unmatched = 0
    missing_local = 0
    missing_sha256 = 0
    for manifest in manifest_rows:
        filename = str(manifest.get("name") or "")
        language = _resource_language(filename)
        if language is None:
            continue
        voice_resource_rows += 1
        if (language, ascii_filename_key(filename)) not in needed_keys:
            unmatched += 1
            continue
        local_relpath = str(manifest.get("local_relpath") or "")
        local_path = raw_root / local_relpath
        sha256 = ""
        if not local_relpath or not local_path.is_file():
            missing_local += 1
        else:
            sha256 = str(digest(local_path))
            if not sha256:
                missing_sha256 += 1
        resources.append(
            ResourceRow(
                filename=filename,
                language=language,
                sha1=str(manifest.get("sha1") or ""),
                sha256=sha256,
                resource_id=str(manifest.get("sha1") or local_relpath),
                source_url=str(manifest.get("url") or ""),
                title=str(manifest.get("title") or ""),
                mime=str(manifest.get("mime") or ""),
                local_relpath=local_relpath,
                object_key=_voice_object_key(object_prefix, str(manifest.get("sha1") or ""), filename),
            )
        )
    return tuple(resources), {
        "voice_resource_rows": voice_resource_rows,
        "needed_matching_resource_rows": len(resources),
        "unmatched_voice_resource_rows_not_hashed": unmatched,
        "computable_local_sha256": sum(1 for row in resources if row.sha256),
        "missing_local_file": missing_local,
        "missing_sha256": missing_sha256,
    }


def generate_r03_evidence(
    raw_root: Path,
    evidence_dir: Path,
    *,
    object_prefix: str = "reverse1999",
) -> dict[str, Any]:
    """Rebuild R03 evidence from raw files without constructing any mutation client."""
    sources = voice_source_rows_from_data_pages(iter_jsonl(raw_root / "data_pages.jsonl"))
    resources, resource_counts = resource_rows_for_sources(
        iter_jsonl(raw_root / "resources_manifest.jsonl"),
        sources,
        raw_root,
        object_prefix=object_prefix,
    )
    resource_index = index_voice_resources(resources)
    bindings = tuple(bind_voice_row(source, resource_index) for source in sources)
    result = classify_binding_conflicts(bindings)
    closure = expand_conflict_closure(set(result.quarantined_ids), bindings)
    listing = build_quarantine_listing(
        bindings,
        result,
        provenance={
            "source_input_sha256": {
                "data_pages.jsonl": _file_sha256(raw_root / "data_pages.jsonl"),
                "resources_manifest.jsonl": _file_sha256(raw_root / "resources_manifest.jsonl"),
            },
            "resource_inventory": resource_counts,
            "classification": {
                "voice_source_rows": len(sources),
                "classified_rows": len(bindings),
                "fatal": len(result.fatal_ids),
                "shortfall": len(result.shortfall_ids),
                "exact_runtime": len(result.runtime_ids),
                "mutation_stop": result.stop_mutations,
            },
            "closure": {
                "closure_sha256": closure.closure_sha256,
                "round_counts": list(closure.round_counts),
                "visited_counts": dict(closure.visited_counts),
                "visited_rows": len(closure.visited_ids),
                "total_rows": len(bindings),
                "whole_corpus_visited": closure.whole_corpus_visited,
            },
            "mutation_client_instantiated": False,
        },
    )
    return write_r03_evidence(evidence_dir, listing)


def write_r03_evidence(
    evidence_dir: Path,
    listing: dict[str, Any],
) -> dict[str, Any]:
    """Write listing, compact report, and its sole canonical sidecar from one result."""
    evidence_dir.mkdir(parents=True, exist_ok=True)
    listing_path = evidence_dir / _R03_LISTING_NAME
    listing_bytes = _canonical_json_bytes(listing)
    listing_path.write_bytes(listing_bytes)
    listing_sha256 = hashlib.sha256(listing_bytes).hexdigest()
    sidecar_path = evidence_dir / f"{_R03_LISTING_NAME}.sha256"
    sidecar_path.write_text(f"{listing_sha256}  {_R03_LISTING_NAME}\n", encoding="utf-8", newline="\n")
    stale_sidecar = evidence_dir / "task-3-r03-cross-child-listing.v1.sha256"
    stale_sidecar.unlink(missing_ok=True)

    summary = listing["summary"]
    provenance = listing.get("provenance") or {}
    cause_counts = summary["cause_occurrence_counts"]
    current = {
        **dict(provenance.get("resource_inventory") or {}),
        **dict(provenance.get("classification") or {}),
        "source_input_sha256": dict(provenance.get("source_input_sha256") or {}),
        "closure": dict(provenance.get("closure") or {}),
        "mutation_client_instantiated": bool(provenance.get("mutation_client_instantiated", False)),
        "cross_child_listing_path": str(listing_path),
        "cross_child_listing_sha256": listing_sha256,
        "cross_child_occurrences": cause_counts["cross_child_sha"],
        "same_sha_different_event_or_text_occurrences": cause_counts[
            "same_sha_different_event_or_text"
        ],
        "root_cause_occurrences": cause_counts,
        "named_cause_intersection_count": summary["named_cause_intersection_count"],
        "named_cause_union_count": summary["named_cause_union_count"],
        "quarantine_occurrences_listed": summary["quarantined_total"],
        "quarantine_sha_groups": summary["quarantine_sha_groups"],
        "cross_child_sha_groups": summary["cross_child_sha_groups"],
        "quarantined": summary["quarantined_total"],
        "every_observed_cross_child_occurrence_listed": True,
        "every_quarantined_occurrence_listed": True,
    }
    (evidence_dir / _R03_CURRENT_NAME).write_bytes(_canonical_json_bytes(current))
    return {"listing_sha256": listing_sha256, "current": current}


def _resource_language(filename: str) -> str | None:
    if not filename.casefold().endswith(".mp3"):
        return None
    for prefix, language in _RESOURCE_PREFIXES:
        if filename.startswith(prefix):
            return language
    return None


def _voice_object_key(object_prefix: str, sha1: str, filename: str) -> str:
    normalized_sha1 = sha1.strip().lower()
    if len(normalized_sha1) != 40 or any(character not in "0123456789abcdef" for character in normalized_sha1):
        return ""
    suffix = Path(filename).suffix.lower()
    return f"{object_prefix.strip('/')}/voice/{normalized_sha1[:2]}/{normalized_sha1}{suffix}"


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_json_bytes(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read-only diagnostics for Huiji processed RAG artifacts.")
    parser.add_argument("--processed-dir", default="")
    parser.add_argument("--output", default="")
    parser.add_argument("--check-local-files", action="store_true")
    parser.add_argument("--r03", action="store_true")
    parser.add_argument("--raw-root", default="")
    parser.add_argument("--evidence-dir", default="")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    if args.r03:
        raw_root = Path(args.raw_root or "data/huiji/res1999")
        evidence_dir = Path(args.evidence_dir or ".superpowers/sdd/evb-2026-07-11")
        cfg = get_config()
        print(
            json.dumps(
                generate_r03_evidence(
                    raw_root,
                    evidence_dir,
                    object_prefix=str(getattr(cfg.assets, "object_prefix", "reverse1999")),
                )["current"],
                ensure_ascii=False,
                indent=2,
            )
        )
        return
    cfg = get_config()
    if args.processed_dir:
        processed_dir = Path(args.processed_dir)
    else:
        processed_dir = default_processed_dir(cfg)
    raw_root = getattr(cfg.huiji, "raw_root", None) if args.check_local_files else None
    report = diagnose_artifacts(processed_dir, raw_root=raw_root)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
