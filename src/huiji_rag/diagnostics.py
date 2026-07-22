"""Read-only EventName voice-binding conflict classification and closure diagnostics."""
from __future__ import annotations

import hashlib
from collections import defaultdict
from typing import Any, Iterable, Mapping, Sequence

from .models import BindingRecord, BindingStatus, ConflictClosure, ConflictResult


def transcript_sha256(text: str | None) -> str:
    """Return the deterministic UTF-8 digest for a transcript, including a missing one."""
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def classify_binding_conflicts(rows: Sequence[BindingRecord]) -> ConflictResult:
    """Classify immutable binding evidence without attempting any external mutation."""
    records = _records_by_id(rows)
    causes: dict[str, set[str]] = {record_id: set() for record_id in records}
    statuses: dict[str, BindingStatus] = {}

    for record_id, row in records.items():
        status = row.binding_status
        if status is BindingStatus.FATAL:
            causes[record_id].add("duplicate_eventname_sha")
        elif status is BindingStatus.SHORTFALL:
            causes[record_id].add("missing_exact_resource")
        statuses[record_id] = status

    by_sha: dict[str, list[tuple[str, BindingRecord]]] = defaultdict(list)
    for record_id, row in records.items():
        if statuses[record_id] is not BindingStatus.EXACT:
            continue
        for sha256 in sorted(set(value for value in row.content_sha256 if value)):
            by_sha[sha256].append((record_id, row))

    for shared_rows in by_sha.values():
        if len(shared_rows) < 2:
            continue
        shared_ids = [record_id for record_id, _row in shared_rows]
        child_ids = {row.child_id for _record_id, row in shared_rows if row.child_id}
        event_names = {row.event_name for _record_id, row in shared_rows}
        transcript_hashes_by_language: dict[str, set[str]] = defaultdict(set)
        for _record_id, row in shared_rows:
            transcript_hashes_by_language[row.language].add(
                transcript_sha256(row.transcript)
            )
        group_causes: set[str] = set()
        if len(child_ids) > 1:
            group_causes.add("cross_child_sha")
        if len(event_names) > 1 or any(
            len(hashes) > 1 for hashes in transcript_hashes_by_language.values()
        ):
            group_causes.add("same_sha_different_event_or_text")
        if group_causes:
            for record_id in shared_ids:
                statuses[record_id] = BindingStatus.QUARANTINED
                causes[record_id].update(group_causes)

    root_causes = {
        record_id: tuple(sorted(record_causes))
        for record_id, record_causes in sorted(causes.items())
    }
    status_by_id = {record_id: statuses[record_id] for record_id in sorted(records)}
    quality_flags_by_id = {
        record_id: _quality_flags(records[record_id], status_by_id[record_id], root_causes[record_id])
        for record_id in sorted(records)
    }
    return ConflictResult(
        fatal_ids=_ids_for_status(status_by_id, BindingStatus.FATAL),
        quarantined_ids=_ids_for_status(status_by_id, BindingStatus.QUARANTINED),
        shortfall_ids=_ids_for_status(status_by_id, BindingStatus.SHORTFALL),
        exact_ids=_ids_for_status(status_by_id, BindingStatus.EXACT),
        runtime_ids=_ids_for_status(status_by_id, BindingStatus.EXACT),
        stop_mutations=any(status is BindingStatus.FATAL for status in status_by_id.values()),
        root_causes=root_causes,
        status_by_id=status_by_id,
        quality_flags_by_id=quality_flags_by_id,
    )


def build_quarantine_listing(
    rows: Sequence[BindingRecord],
    result: ConflictResult,
    *,
    provenance: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a complete, deterministic, read-only listing of quarantined bindings."""
    records = _records_by_id(rows)
    occurrences = [_quarantine_occurrence(records[record_id], result) for record_id in result.quarantined_ids]
    occurrences.sort(key=lambda item: item["source_id"])
    cause_sets = {
        cause: sorted(
            occurrence["source_id"]
            for occurrence in occurrences
            if cause in occurrence["root_causes"]
        )
        for cause in sorted({cause for occurrence in occurrences for cause in occurrence["root_causes"]})
    }
    for cause in (
        "cross_child_sha",
        "same_sha_different_event_or_text",
        "shared_sha_distinct_binding_key",
    ):
        cause_sets.setdefault(cause, [])
    cross_child = set(cause_sets["cross_child_sha"])
    same_event_or_text = set(cause_sets["same_sha_different_event_or_text"])
    sha_groups = _quarantine_sha_groups(occurrences)
    return {
        "schema_version": "evb.r03-cross-child-listing/v1",
        "provenance": dict(provenance or {}),
        "quarantined_occurrences": occurrences,
        "quarantined_sha_groups": sha_groups,
        "summary": {
            "cause_occurrence_sets": cause_sets,
            "cause_occurrence_counts": {cause: len(ids) for cause, ids in cause_sets.items()},
            "cross_child_sha_groups": sum(
                1 for group in sha_groups if any("cross_child_sha" in item["root_causes"] for item in group["occurrences"])
            ),
            "quarantine_sha_groups": len(sha_groups),
            "named_cause_intersection": sorted(cross_child & same_event_or_text),
            "named_cause_intersection_count": len(cross_child & same_event_or_text),
            "named_cause_union": sorted(cross_child | same_event_or_text),
            "named_cause_union_count": len(cross_child | same_event_or_text),
            "quarantined_total": len(occurrences),
        },
    }


def expand_conflict_closure(
    seed_ids: set[str], corpus: Sequence[BindingRecord]
) -> ConflictClosure:
    """Expand through every required evidence dimension until no new row is reachable."""
    records = _records_by_id(corpus)
    unknown_ids = sorted(seed_ids - records.keys())
    if unknown_ids:
        raise ValueError(f"conflict closure seeds not found in corpus: {', '.join(unknown_ids)}")

    values_by_id = {record_id: _closure_values(row) for record_id, row in records.items()}
    visited = set(seed_ids)
    round_counts: list[int] = []
    while True:
        shared_values = _collect_closure_values(visited, values_by_id)
        expanded = visited | {
            record_id
            for record_id, values in values_by_id.items()
            if _shares_any_value(values, shared_values)
        }
        if expanded == visited:
            break
        round_counts.append(len(expanded) - len(visited))
        visited = expanded

    visited_ids = tuple(sorted(visited))
    return ConflictClosure(
        visited_ids=visited_ids,
        round_counts=tuple(round_counts),
        visited_counts=_visited_counts(visited_ids, values_by_id),
        closure_sha256=hashlib.sha256("\n".join(visited_ids).encode("utf-8")).hexdigest(),
        whole_corpus_visited=len(visited) == len(records),
    )


def should_stop_mutations(result: ConflictResult) -> bool:
    """Fatal binding evidence blocks subsequent mutations; diagnostics remain read-only."""
    return bool(result.fatal_ids)


def _records_by_id(rows: Sequence[BindingRecord]) -> dict[str, BindingRecord]:
    records: dict[str, BindingRecord] = {}
    for row in rows:
        record_id = row.source_id
        if not record_id:
            raise ValueError("binding record requires source_id for deterministic diagnostics")
        if record_id in records:
            raise ValueError(f"duplicate binding source_id: {record_id}")
        records[record_id] = row
    return records


def _ids_for_status(
    statuses: Mapping[str, BindingStatus], status: BindingStatus
) -> tuple[str, ...]:
    return tuple(record_id for record_id, value in statuses.items() if value is status)


def _quality_flags(
    row: BindingRecord, status: BindingStatus, causes: tuple[str, ...]
) -> tuple[str, ...]:
    flags = list(row.quality_flags)
    if status is BindingStatus.QUARANTINED:
        flags.append("quarantined")
    elif status is BindingStatus.FATAL:
        flags.append("fatal")
    return tuple(dict.fromkeys((*flags, *causes)))


def _quarantine_occurrence(row: BindingRecord, result: ConflictResult) -> dict[str, Any]:
    return {
        "source_id": row.source_id,
        "child_id": row.child_id,
        "parent_id": row.parent_id,
        "entity_id": row.entity_id,
        "language": row.language,
        "event_name": row.event_name,
        "transcript": row.transcript,
        "text_sha256": row.text_sha256,
        "expected_filename": row.expected_filename,
        "resource_sha1": sorted(set(value for value in row.source_sha1 if value)),
        "content_sha256": sorted(set(value for value in row.content_sha256 if value)),
        "object_key": sorted(set(value for value in row.object_key if value)),
        "effective_status": result.status_by_id[row.source_id].value,
        "root_causes": list(result.root_causes[row.source_id]),
    }


def _quarantine_sha_groups(occurrences: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    by_sha: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for occurrence in occurrences:
        for sha256 in occurrence["content_sha256"]:
            by_sha[sha256].append(occurrence)
    return [
        {
            "sha256": sha256,
            "occurrences": sorted(group, key=lambda item: item["source_id"]),
        }
        for sha256, group in sorted(by_sha.items())
    ]


def _closure_values(row: BindingRecord) -> dict[str, frozenset[str]]:
    return {
        "entities": _nonempty((row.entity_id,)),
        "event_names": _nonempty((row.event_name,)),
        "expected_filenames": _nonempty((row.expected_filename,)),
        "sha256": _nonempty(row.content_sha256),
        "object_keys": _nonempty(row.object_key),
        "languages": _nonempty((row.language,)),
        "naming_families": _nonempty((_naming_family(row.expected_filename),)),
    }


def _nonempty(values: Iterable[str]) -> frozenset[str]:
    return frozenset(value for value in values if value)


def _naming_family(expected_filename: str) -> str:
    stem = expected_filename.rsplit(".", 1)[0]
    family, separator, suffix = stem.rpartition("_")
    return family if separator and suffix.isdigit() else stem


def _collect_closure_values(
    visited: set[str], values_by_id: Mapping[str, Mapping[str, frozenset[str]]]
) -> dict[str, set[str]]:
    collected = {dimension: set() for dimension in _dimension_names()}
    for record_id in visited:
        for dimension, values in values_by_id[record_id].items():
            collected[dimension].update(values)
    return collected


def _shares_any_value(
    row_values: Mapping[str, frozenset[str]], shared_values: Mapping[str, set[str]]
) -> bool:
    return any(row_values[dimension] & shared_values[dimension] for dimension in _dimension_names())


def _visited_counts(
    visited_ids: tuple[str, ...], values_by_id: Mapping[str, Mapping[str, frozenset[str]]]
) -> dict[str, int]:
    counts = {"rows": len(visited_ids)}
    for dimension in _dimension_names():
        counts[dimension] = len(
            set().union(*(values_by_id[record_id][dimension] for record_id in visited_ids))
            if visited_ids
            else set()
        )
    return counts


def _dimension_names() -> tuple[str, ...]:
    return (
        "entities",
        "languages",
        "event_names",
        "expected_filenames",
        "sha256",
        "object_keys",
        "naming_families",
    )
