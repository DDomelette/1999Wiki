"""Record-level active-to-candidate fidelity accounting for crawler builds."""
from __future__ import annotations

import hashlib
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Sequence

from .contracts import canonical_json_bytes
from .media_v3 import LegacyMediaReconciliation
from .projection import CorpusProjection, SemanticRecordLink


_ALLOWED_CHANGE_KINDS = frozenset(
    {"preserved_exact", "preserved_rekeyed", "corrected_semantics", "new_source_record"}
)
_ALLOWED_SECTION_CORRECTIONS = frozenset(
    {
        ("culture", "collection"),
        ("item", "culture_dossier"),
        ("items", "culture_dossier"),
    }
)
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")


@dataclass(frozen=True)
class FidelityResult:
    ledger_rows: tuple[Mapping[str, Any], ...]
    build_diff: Mapping[str, Any]
    blockers: tuple[str, ...]
    category_counts: Mapping[str, int] = field(default_factory=dict)
    unexplained_parent_child_loss: int = 0
    unexplained_binding_loss: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "ledger_rows",
            tuple(MappingProxyType(dict(row)) for row in self.ledger_rows),
        )
        object.__setattr__(self, "build_diff", MappingProxyType(dict(self.build_diff)))
        object.__setattr__(self, "blockers", tuple(sorted(set(self.blockers))))
        object.__setattr__(
            self,
            "category_counts",
            MappingProxyType(dict(sorted(self.category_counts.items()))),
        )

    @property
    def passed(self) -> bool:
        return not self.blockers


def build_fidelity_ledger(
    *,
    active_parent_rows: Iterable[Mapping[str, Any]],
    active_child_rows: Iterable[Mapping[str, Any]],
    active_excluded_rows: Iterable[Mapping[str, Any]],
    projection: CorpusProjection,
    legacy_media: LegacyMediaReconciliation,
    active_child_bm25_records: Iterable[Mapping[str, Any]] = (),
    active_media_bm25_records: Iterable[Mapping[str, Any]] = (),
) -> FidelityResult:
    """Classify each active identity exactly once and reject count-only fidelity."""
    active_parents = tuple(dict(row) for row in active_parent_rows)
    active_children = tuple(dict(row) for row in active_child_rows)
    active_excluded = tuple(dict(row) for row in active_excluded_rows)
    active_child_bm25 = tuple(dict(row) for row in active_child_bm25_records)
    active_media_bm25 = tuple(dict(row) for row in active_media_bm25_records)
    candidate_parents = tuple(parent.to_json() for parent in projection.parents)
    candidate_children = tuple(child.block.to_json() for child in projection.children)

    ledger: list[dict[str, Any]] = []
    blockers: list[str] = []
    categories: Counter[str] = Counter()
    record_classifications: dict[tuple[str, str], tuple[str, str]] = {}
    unexplained_parent_child_loss = 0

    for record_kind, active_rows, candidate_rows, id_field in (
        ("parent", active_parents, candidate_parents, "parent_id"),
        ("child", active_children, candidate_children, "child_id"),
    ):
        rows, row_blockers, classifications, unexplained = _reconcile_records(
            record_kind,
            active_rows,
            candidate_rows,
            id_field,
            projection.record_links,
        )
        ledger.extend(rows)
        blockers.extend(row_blockers)
        categories.update(row["classification"] for row in rows)
        record_classifications.update(classifications)
        unexplained_parent_child_loss += unexplained

    excluded_rows, excluded_blockers = _reconcile_exclusions(
        active_excluded, projection
    )
    ledger.extend(excluded_rows)
    blockers.extend(excluded_blockers)
    categories.update(row["classification"] for row in excluded_rows)

    for occurrence in legacy_media.occurrence_rows:
        row = {
            "schema_version": "huiji.fidelity-ledger/v1",
            "ledger_id": str(occurrence["occurrence_id"]),
            "record_kind": "media_binding",
            "active_identity": str(occurrence["occurrence_id"]),
            "candidate_identities": list(occurrence["candidate_binding_ids"]),
            "classification": str(occurrence["classification"]),
            "reason_code": str(occurrence["reason_code"]),
            "active_sha256": str(occurrence["active_row_sha256"]),
            "candidate_sha256": _hash_identity_list(
                occurrence["candidate_binding_ids"]
            ),
            "source_evidence": list(occurrence["candidate_source_refs"]),
            "details": {
                "resource_id": occurrence["resource_id"],
                "active_media_id": occurrence["active_media_id"],
                "active_child_id": occurrence["active_child_id"],
                "candidate_child_id": occurrence["candidate_child_id"],
            },
        }
        ledger.append(row)
        categories[row["classification"]] += 1
    if legacy_media.unexplained_binding_loss:
        blockers.append(
            f"unexplained_binding_loss:{legacy_media.unexplained_binding_loss}"
        )

    bm25_rows, bm25_blockers = _reconcile_child_bm25(
        active_children,
        active_child_bm25,
        record_classifications,
    )
    ledger.extend(bm25_rows)
    blockers.extend(bm25_blockers)
    categories.update(row["classification"] for row in bm25_rows)

    media_bm25_rows, media_bm25_blockers = _reconcile_media_bm25(
        legacy_media, active_media_bm25
    )
    ledger.extend(media_bm25_rows)
    blockers.extend(media_bm25_blockers)
    categories.update(row["classification"] for row in media_bm25_rows)

    ledger.sort(
        key=lambda row: (
            str(row["record_kind"]),
            str(row["active_identity"]),
            str(row["ledger_id"]),
        )
    )
    ledger_ids = [str(row["ledger_id"]) for row in ledger]
    if len(set(ledger_ids)) != len(ledger_ids):
        raise ValueError("fidelity ledger contains duplicate ledger identities")
    if unexplained_parent_child_loss:
        blockers.append(
            f"unexplained_parent_child_loss:{unexplained_parent_child_loss}"
        )

    build_diff = {
        "schema_version": "huiji.build-diff/v1",
        "active_counts": {
            "parents": len(active_parents),
            "children": len(active_children),
            "excluded": len(active_excluded),
            "media_bindings": legacy_media.active_occurrence_count,
            "child_bm25": len(active_child_bm25),
            "media_bm25": len(active_media_bm25),
        },
        "candidate_counts": {
            "parents": len(candidate_parents),
            "children": len(candidate_children),
            "excluded": len(projection.exclusions),
        },
        "category_counts": dict(sorted(categories.items())),
        "unexplained_parent_child_loss": unexplained_parent_child_loss,
        "unexplained_binding_loss": legacy_media.unexplained_binding_loss,
        "allowed_change_kinds": sorted(_ALLOWED_CHANGE_KINDS),
        "allowed_section_corrections": [
            list(pair) for pair in sorted(_ALLOWED_SECTION_CORRECTIONS)
        ],
    }
    return FidelityResult(
        ledger_rows=tuple(ledger),
        build_diff=build_diff,
        blockers=tuple(blockers),
        category_counts=dict(categories),
        unexplained_parent_child_loss=unexplained_parent_child_loss,
        unexplained_binding_loss=legacy_media.unexplained_binding_loss,
    )


def _reconcile_records(
    record_kind: str,
    active_rows: Sequence[Mapping[str, Any]],
    candidate_rows: Sequence[Mapping[str, Any]],
    id_field: str,
    links: Sequence[SemanticRecordLink],
) -> tuple[
    list[dict[str, Any]],
    list[str],
    dict[tuple[str, str], tuple[str, str]],
    int,
]:
    active = _unique_by_id(active_rows, id_field, f"active {record_kind}")
    candidate = _unique_by_id(candidate_rows, id_field, f"candidate {record_kind}")
    link_by_legacy: dict[str, SemanticRecordLink] = {}
    new_links: dict[str, SemanticRecordLink] = {}
    for link in links:
        if link.record_kind != record_kind:
            continue
        target = new_links if not link.legacy_id else link_by_legacy
        key = link.candidate_id if not link.legacy_id else link.legacy_id
        if key in target:
            raise ValueError(f"duplicate {record_kind} fidelity link: {key}")
        target[key] = link

    ledger: list[dict[str, Any]] = []
    blockers: list[str] = []
    classifications: dict[tuple[str, str], tuple[str, str]] = {}
    mapped_candidate_ids: set[str] = set()
    unexplained = 0
    for active_id, old_row in active.items():
        link = link_by_legacy.get(active_id)
        candidate_id = link.candidate_id if link is not None else active_id
        new_row = candidate.get(candidate_id)
        classification = link.change_kind if link is not None else "preserved_exact"
        reason_code = classification
        if new_row is None:
            classification = "unexplained_missing"
            reason_code = "active_identity_has_no_candidate_record"
            blockers.append(f"unexplained_{record_kind}_missing:{active_id}")
            unexplained += 1
        elif classification not in _ALLOWED_CHANGE_KINDS:
            reason_code = "change_kind_not_whitelisted"
            blockers.append(f"unapproved_{record_kind}_change:{active_id}:{classification}")
        elif link is not None and not _SHA256_RE.fullmatch(
            link.source_content_sha256
        ):
            reason_code = "source_evidence_hash_invalid"
            blockers.append(f"invalid_{record_kind}_source_evidence:{active_id}")
        elif classification == "preserved_exact" and candidate_id != active_id:
            reason_code = "preserved_exact_changes_identity"
            blockers.append(f"invalid_preserved_exact_link:{active_id}")
        elif classification == "preserved_rekeyed" and candidate_id == active_id:
            reason_code = "preserved_rekeyed_does_not_change_identity"
            blockers.append(f"invalid_preserved_rekeyed_link:{active_id}")
        elif classification == "new_source_record":
            reason_code = "new_source_record_has_active_predecessor"
            blockers.append(f"invalid_new_source_link:{active_id}")
        elif classification == "corrected_semantics" and (
            link is None
            or (link.legacy_section, link.candidate_section)
            not in _ALLOWED_SECTION_CORRECTIONS
        ):
            reason_code = "section_correction_not_whitelisted"
            blockers.append(f"unapproved_section_correction:{active_id}")
        if new_row is not None:
            mapped_candidate_ids.add(candidate_id)
        active_hash = _row_hash(old_row)
        candidate_hash = "" if new_row is None else _row_hash(new_row)
        source_evidence = [] if link is None else [_link_source_evidence(link)]
        ledger_id = _ledger_id(record_kind, active_id, candidate_id)
        row = {
            "schema_version": "huiji.fidelity-ledger/v1",
            "ledger_id": ledger_id,
            "record_kind": record_kind,
            "active_identity": active_id,
            "candidate_identities": [] if new_row is None else [candidate_id],
            "classification": classification,
            "reason_code": reason_code,
            "active_sha256": active_hash,
            "candidate_sha256": candidate_hash,
            "source_evidence": source_evidence,
            "details": {
                "payload_changed": bool(new_row is not None and active_hash != candidate_hash),
                "legacy_section": "" if link is None else link.legacy_section,
                "candidate_section": "" if link is None else link.candidate_section,
            },
        }
        ledger.append(row)
        classifications[(record_kind, active_id)] = (classification, candidate_id)

    for candidate_id, new_row in candidate.items():
        if candidate_id in mapped_candidate_ids:
            continue
        link = new_links.get(candidate_id)
        classification = "new_source_record" if link is not None else "unexplained_addition"
        reason_code = classification
        if link is None or link.change_kind != "new_source_record":
            blockers.append(f"unexplained_{record_kind}_addition:{candidate_id}")
        elif not _SHA256_RE.fullmatch(link.source_content_sha256):
            reason_code = "source_evidence_hash_invalid"
            blockers.append(f"invalid_{record_kind}_source_evidence:{candidate_id}")
        ledger.append(
            {
                "schema_version": "huiji.fidelity-ledger/v1",
                "ledger_id": _ledger_id(record_kind, "", candidate_id),
                "record_kind": record_kind,
                "active_identity": "",
                "candidate_identities": [candidate_id],
                "classification": classification,
                "reason_code": reason_code,
                "active_sha256": "",
                "candidate_sha256": _row_hash(new_row),
                "source_evidence": [] if link is None else [_link_source_evidence(link)],
                "details": {
                    "payload_changed": True,
                    "legacy_section": "" if link is None else link.legacy_section,
                    "candidate_section": "" if link is None else link.candidate_section,
                },
            }
        )
    return ledger, blockers, classifications, unexplained


def _reconcile_exclusions(
    active_rows: Sequence[Mapping[str, Any]], projection: CorpusProjection
) -> tuple[list[dict[str, Any]], list[str]]:
    candidate_by_source: dict[str, list[Any]] = defaultdict(list)
    for exclusion in projection.exclusions:
        candidate_by_source[exclusion.source_title].append(exclusion)
    ledger: list[dict[str, Any]] = []
    blockers: list[str] = []
    matched: set[tuple[str, str]] = set()
    for index, active in enumerate(active_rows):
        source = str(active.get("source") or active.get("source_title") or "")
        candidates = candidate_by_source.get(source, ())
        classification = "preserved_exclusion" if candidates else "unexplained_missing"
        reason = (
            "active_exclusion_has_crawler_exclusion"
            if candidates
            else "active_exclusion_has_no_candidate_evidence"
        )
        if not candidates:
            blockers.append(f"unexplained_exclusion_missing:{source or index}")
        candidate_ids = sorted(
            {
                f"{item.source_title}#{item.json_path}:{item.reason_code}"
                for item in candidates
            }
        )
        for item in candidates:
            matched.add((item.source_title, item.reason_code))
        active_identity = f"active-exclusion:{index}:{source}"
        ledger.append(
            {
                "schema_version": "huiji.fidelity-ledger/v1",
                "ledger_id": _ledger_id("excluded", active_identity, "|".join(candidate_ids)),
                "record_kind": "excluded",
                "active_identity": active_identity,
                "candidate_identities": candidate_ids,
                "classification": classification,
                "reason_code": reason,
                "active_sha256": _row_hash(active),
                "candidate_sha256": _hash_identity_list(candidate_ids),
                "source_evidence": [
                    {
                        "source_title": item.source_title,
                        "source_content_sha256": item.source_content_sha256,
                        "json_path": item.json_path,
                    }
                    for item in candidates
                ],
                "details": {},
            }
        )
    for exclusion in projection.exclusions:
        key = (exclusion.source_title, exclusion.reason_code)
        if key in matched:
            continue
        candidate_id = f"{exclusion.source_title}#{exclusion.json_path}:{exclusion.reason_code}"
        ledger.append(
            {
                "schema_version": "huiji.fidelity-ledger/v1",
                "ledger_id": _ledger_id("excluded", "", candidate_id),
                "record_kind": "excluded",
                "active_identity": "",
                "candidate_identities": [candidate_id],
                "classification": "new_source_exclusion",
                "reason_code": exclusion.reason_code,
                "active_sha256": "",
                "candidate_sha256": _row_hash(exclusion.to_json()),
                "source_evidence": [
                    {
                        "source_title": exclusion.source_title,
                        "source_content_sha256": exclusion.source_content_sha256,
                        "json_path": exclusion.json_path,
                    }
                ],
                "details": {},
            }
        )
    return ledger, blockers


def _reconcile_child_bm25(
    active_children: Sequence[Mapping[str, Any]],
    active_bm25: Sequence[Mapping[str, Any]],
    classifications: Mapping[tuple[str, str], tuple[str, str]],
) -> tuple[list[dict[str, Any]], list[str]]:
    if not active_bm25:
        return [], []
    blockers: list[str] = []
    rows: list[dict[str, Any]] = []
    if len(active_children) != len(active_bm25):
        blockers.append("active_child_bm25_count_mismatch")
    for index, record in enumerate(active_bm25):
        active_id = str(record.get("child_id") or record.get("id") or "")
        expected_id = (
            str(active_children[index].get("child_id") or "")
            if index < len(active_children)
            else ""
        )
        classification, candidate_id = classifications.get(
            ("child", active_id), ("unexplained_missing", "")
        )
        reason = "derived_from_child_fidelity"
        if active_id != expected_id:
            classification = "unexplained_bm25_sequence_drift"
            reason = "active_child_bm25_sequence_mismatch"
            blockers.append(f"active_child_bm25_sequence_mismatch:{index}")
        rows.append(
            {
                "schema_version": "huiji.fidelity-ledger/v1",
                "ledger_id": _ledger_id("child_bm25", f"{index}:{active_id}", candidate_id),
                "record_kind": "child_bm25",
                "active_identity": f"{index}:{active_id}",
                "candidate_identities": [candidate_id] if candidate_id else [],
                "classification": classification,
                "reason_code": reason,
                "active_sha256": _row_hash(record),
                "candidate_sha256": "",
                "source_evidence": [],
                "details": {"sequence_index": index},
            }
        )
    return rows, blockers


def _reconcile_media_bm25(
    legacy_media: LegacyMediaReconciliation,
    active_bm25: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    if not active_bm25:
        return [], []
    blockers: list[str] = []
    rows: list[dict[str, Any]] = []
    occurrences = legacy_media.occurrence_rows
    if len(occurrences) != len(active_bm25):
        blockers.append("active_media_bm25_count_mismatch")
    for index, record in enumerate(active_bm25):
        occurrence = occurrences[index] if index < len(occurrences) else None
        active_media_id = str(record.get("media_id") or "")
        classification = "unexplained_bm25_sequence_drift"
        candidate_ids: list[str] = []
        occurrence_id = ""
        if occurrence is not None:
            occurrence_id = str(occurrence["occurrence_id"])
            candidate_ids = list(occurrence["candidate_binding_ids"])
            classification = str(occurrence["classification"])
            if active_media_id != str(occurrence["active_media_id"]):
                classification = "unexplained_bm25_sequence_drift"
                blockers.append(f"active_media_bm25_sequence_mismatch:{index}")
        rows.append(
            {
                "schema_version": "huiji.fidelity-ledger/v1",
                "ledger_id": _ledger_id(
                    "media_bm25", f"{index}:{active_media_id}", occurrence_id
                ),
                "record_kind": "media_bm25",
                "active_identity": f"{index}:{active_media_id}",
                "candidate_identities": candidate_ids,
                "classification": classification,
                "reason_code": "derived_from_media_occurrence_fidelity",
                "active_sha256": _row_hash(record),
                "candidate_sha256": _hash_identity_list(candidate_ids),
                "source_evidence": [],
                "details": {"sequence_index": index, "occurrence_id": occurrence_id},
            }
        )
    return rows, blockers


def _unique_by_id(
    rows: Sequence[Mapping[str, Any]], id_field: str, label: str
) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        identity = str(row.get(id_field) or row.get("id") or "")
        if not identity or identity in result:
            raise ValueError(f"{label} contains an empty or duplicate {id_field}")
        result[identity] = row
    return result


def _link_source_evidence(link: SemanticRecordLink) -> dict[str, Any]:
    return {
        "source_title": link.source_title,
        "source_content_sha256": link.source_content_sha256,
        "json_path": link.json_path,
        "legacy_section": link.legacy_section,
        "candidate_section": link.candidate_section,
    }


def _row_hash(row: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        canonical_json_bytes(dict(row), trailing_newline=False)
    ).hexdigest()


def _hash_identity_list(values: Iterable[object]) -> str:
    normalized = sorted(str(value) for value in values)
    if not normalized:
        return ""
    return hashlib.sha256(
        canonical_json_bytes(normalized, trailing_newline=False)
    ).hexdigest()


def _ledger_id(record_kind: str, active_identity: str, candidate_identity: str) -> str:
    payload = [
        "huiji.fidelity-ledger-identity/v1",
        record_kind,
        active_identity,
        candidate_identity,
    ]
    return "fidelity:sha256:" + hashlib.sha256(
        canonical_json_bytes(payload, trailing_newline=False)
    ).hexdigest()


__all__ = ["FidelityResult", "build_fidelity_ledger"]
