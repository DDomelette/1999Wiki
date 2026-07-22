"""Single exact EventName-to-resource matching stage for every build facade."""
from __future__ import annotations

import hashlib
import re
from collections import Counter
from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

from src.huiji_rag.diagnostics import classify_binding_conflicts, expand_conflict_closure
from src.huiji_rag.models import (
    BindingRecord,
    BindingStatus,
    ConflictResult,
    ResourceRow,
    VoiceSourceRow,
)
from src.huiji_rag.normalizer import (
    ascii_filename_key,
    expected_voice_filename,
    normalize_language,
)

from .contracts import VoiceBindingInput, VoiceBindingResult, canonical_json_bytes


_SHA256_RE = re.compile(r"[0-9a-fA-F]{64}\Z")


@dataclass(frozen=True)
class VoiceResourceIndex:
    """Resources keyed only by canonical language and full ASCII filename."""

    rows_by_key: Mapping[tuple[str, str], tuple[ResourceRow, ...]]

    def get(
        self,
        key: tuple[str, str],
        default: Sequence[ResourceRow] = (),
    ) -> Sequence[ResourceRow]:
        return self.rows_by_key.get(key, default)


class VoiceBindingStage:
    """Apply the sole exact voice matching algorithm and classify its evidence."""

    def run(self, request: VoiceBindingInput) -> VoiceBindingResult:
        source_rows = tuple(_require_source(row) for row in request.source_rows)
        resource_rows = tuple(_require_resource(row) for row in request.resource_rows)
        index = index_voice_resources(resource_rows)
        bindings = tuple(bind_voice_row(source, index) for source in source_rows)
        conflicts = classify_binding_conflicts(bindings)
        exact = _bindings_with_status(bindings, conflicts, BindingStatus.EXACT)
        quarantined = _bindings_with_status(
            bindings, conflicts, BindingStatus.QUARANTINED
        )
        shortfall = _bindings_with_status(bindings, conflicts, BindingStatus.SHORTFALL)
        fatal = _bindings_with_status(bindings, conflicts, BindingStatus.FATAL)
        closure = expand_conflict_closure(
            set((*conflicts.quarantined_ids, *conflicts.fatal_ids)), bindings
        )
        source_fingerprint = _rows_fingerprint(source_rows)
        resource_fingerprint = _rows_fingerprint(resource_rows)
        input_fingerprint = _payload_fingerprint(
            {
                "source_rows_sha256": source_fingerprint,
                "source_row_count": len(source_rows),
                "resource_rows_sha256": resource_fingerprint,
                "resource_row_count": len(resource_rows),
            }
        )
        output_rows = [
            {
                "binding": row.to_json(),
                "effective_status": conflicts.status_by_id[row.source_id].value,
                "quality_flags": list(conflicts.quality_flags_by_id[row.source_id]),
                "root_causes": list(conflicts.root_causes[row.source_id]),
            }
            for row in sorted(
                bindings, key=lambda item: (item.source_id, item.child_id, item.language)
            )
        ]
        output_fingerprint = _payload_fingerprint(
            {
                "bindings": output_rows,
                "conflict_closure": {
                    "visited_ids": list(closure.visited_ids),
                    "round_counts": list(closure.round_counts),
                    "visited_counts": dict(closure.visited_counts),
                    "closure_sha256": closure.closure_sha256,
                    "whole_corpus_visited": closure.whole_corpus_visited,
                },
            }
        )
        event_ids = {
            (row.entity_id, row.child_id, row.event_name, row.skin_id)
            for row in bindings
        }
        languages = {normalize_language(row.language)[0] for row in bindings}
        skins = {(row.entity_id, row.skin_id) for row in bindings if row.skin_id}
        counts_by_language = Counter(normalize_language(row.language)[0] for row in bindings)
        counts_by_event = Counter(
            row.child_id
            or "|".join((row.entity_id, row.event_name, row.skin_id, row.audio_id))
            for row in bindings
        )
        counts_by_owner = Counter(row.entity_id for row in bindings)
        status_counts = Counter(status.value for status in conflicts.status_by_id.values())
        return VoiceBindingResult(
            binding_rows=bindings,
            exact_bindings=exact,
            quarantined_bindings=quarantined,
            shortfall_bindings=shortfall,
            fatal_bindings=fatal,
            conflict_result=conflicts,
            conflict_closure=closure,
            status_by_source={
                key: value.value for key, value in conflicts.status_by_id.items()
            },
            quality_flags_by_source=conflicts.quality_flags_by_id,
            root_causes_by_source=conflicts.root_causes,
            source_input_fingerprint_sha256=source_fingerprint,
            resource_input_fingerprint_sha256=resource_fingerprint,
            input_fingerprint_sha256=input_fingerprint,
            output_fingerprint_sha256=output_fingerprint,
            binding_fingerprint_sha256=output_fingerprint,
            status_counts=dict(sorted(status_counts.items())),
            counts_by_language=dict(sorted(counts_by_language.items())),
            counts_by_event=dict(sorted(counts_by_event.items())),
            counts_by_owner=dict(sorted(counts_by_owner.items())),
            event_count=len(event_ids),
            language_count=len(languages),
            owner_count=len(counts_by_owner),
            skin_count=len(skins),
            # Quarantine is a diagnostic-only projection: closure is complete above,
            # and quarantined rows are never exposed as exact runtime bindings.
            ready_gate_blocked=bool(fatal),
        )


def index_voice_resources(rows: Iterable[ResourceRow]) -> VoiceResourceIndex:
    grouped: dict[tuple[str, str], list[ResourceRow]] = {}
    for row in rows:
        language, _prefix = normalize_language(row.language)
        key = (language, ascii_filename_key(row.filename))
        grouped.setdefault(key, []).append(row)
    return VoiceResourceIndex({key: tuple(value) for key, value in grouped.items()})


def bind_voice_row(source: VoiceSourceRow, index: VoiceResourceIndex) -> BindingRecord:
    language, _prefix = normalize_language(source.language)
    expected = expected_voice_filename(source.event_name, language)
    matches = index.get((language, ascii_filename_key(expected)), ())
    valid_sha256 = [item.sha256 for item in matches if _SHA256_RE.fullmatch(item.sha256)]
    content_sha256 = set(valid_sha256)
    status = BindingStatus.SHORTFALL
    if matches and len(valid_sha256) == len(matches):
        status = BindingStatus.EXACT if len(content_sha256) == 1 else BindingStatus.FATAL
    return BindingRecord.from_match(source, expected, matches, status)


def _rows_fingerprint(rows: Sequence[VoiceSourceRow | ResourceRow]) -> str:
    payloads = [row.to_json() for row in rows]
    payloads.sort(key=lambda row: canonical_json_bytes(row, trailing_newline=False))
    return _payload_fingerprint(payloads)


def _payload_fingerprint(value: object) -> str:
    return hashlib.sha256(
        canonical_json_bytes(value, trailing_newline=False)
    ).hexdigest()


def _bindings_with_status(
    rows: Sequence[BindingRecord],
    conflicts: ConflictResult,
    status: BindingStatus,
) -> tuple[BindingRecord, ...]:
    return tuple(row for row in rows if conflicts.status_by_id[row.source_id] is status)


def _require_source(value: object) -> VoiceSourceRow:
    if not isinstance(value, VoiceSourceRow):
        raise TypeError("VoiceBindingInput.source_rows must contain VoiceSourceRow records")
    return value


def _require_resource(value: object) -> ResourceRow:
    if not isinstance(value, ResourceRow):
        raise TypeError("VoiceBindingInput.resource_rows must contain ResourceRow records")
    return value
