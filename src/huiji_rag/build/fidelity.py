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
from .projection import CorpusProjection, SemanticChild, SemanticRecordLink


_ALLOWED_CHANGE_KINDS = frozenset(
    {"preserved_exact", "preserved_rekeyed", "corrected_semantics", "new_source_record"}
)
_ALLOWED_SECTION_CORRECTIONS = frozenset(
    {
        ("culture", "collection"),
        ("item", "culture_dossier"),
        ("items", "culture_dossier"),
        ("profile", "story"),
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
    candidate_children = tuple(
        child.block.to_json() for child in projection.children
    )

    ledger: list[dict[str, Any]] = []
    blockers: list[str] = []
    categories: Counter[str] = Counter()
    record_classifications: dict[
        tuple[str, str],
        tuple[str, tuple[str, ...]],
    ] = {}
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
            projection,
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
    projection: CorpusProjection | None = None,
) -> tuple[
    list[dict[str, Any]],
    list[str],
    dict[tuple[str, str], tuple[str, tuple[str, ...]]],
    int,
]:
    active = _unique_by_id(active_rows, id_field, f"active {record_kind}")
    candidate = _unique_by_id(candidate_rows, id_field, f"candidate {record_kind}")
    story_candidate_metadata_by_source = (
        _story_candidate_metadata_by_source(projection.children)
        if projection is not None and record_kind == "child"
        else {}
    )
    story_parents = (
        {parent.parent_id: parent.to_json() for parent in projection.parents}
        if projection is not None
        else {}
    )
    links_by_legacy: dict[str, list[SemanticRecordLink]] = defaultdict(list)
    new_links: dict[str, SemanticRecordLink] = {}
    link_triples: set[tuple[str, str, str]] = set()
    for link in links:
        if link.record_kind != record_kind:
            continue
        triple = (link.record_kind, link.legacy_id, link.candidate_id)
        if triple in link_triples:
            key = link.legacy_id or link.candidate_id
            raise ValueError(f"duplicate {record_kind} fidelity link: {key}")
        link_triples.add(triple)
        if link.legacy_id:
            links_by_legacy[link.legacy_id].append(link)
        else:
            if link.candidate_id in new_links:
                raise ValueError(
                    f"duplicate {record_kind} fidelity link: {link.candidate_id}"
                )
            new_links[link.candidate_id] = link
    for legacy_id, group in links_by_legacy.items():
        if len(group) > 1 and not _looks_like_story_expansion(record_kind, group):
            raise ValueError(f"duplicate {record_kind} fidelity link: {legacy_id}")

    ledger: list[dict[str, Any]] = []
    blockers: list[str] = []
    classifications: dict[tuple[str, str], tuple[str, tuple[str, ...]]] = {}
    mapped_candidate_ids: set[str] = set()
    story_expansion_candidate_ids: set[str] = set()
    unexplained = 0
    for active_id, old_row in active.items():
        group = tuple(links_by_legacy.get(active_id, ()))
        candidate_ids = tuple(
            sorted(link.candidate_id for link in group)
            if group
            else (active_id,)
        )
        candidate_group = tuple(
            candidate[candidate_id]
            for candidate_id in candidate_ids
            if candidate_id in candidate
        )
        link = group[0] if len(group) == 1 else None
        classification = group[0].change_kind if group else "preserved_exact"
        reason_code = classification
        story_valid = False
        if group and _looks_like_story_correction(record_kind, group):
            story_valid, reason_code = _validate_story_correction_group(
                record_kind=record_kind,
                active_id=active_id,
                active_row=old_row,
                group=group,
                candidate_rows=candidate,
                story_candidate_metadata_by_source=(
                    story_candidate_metadata_by_source
                ),
                story_parents=story_parents,
            )
            if not story_valid:
                classification = "blocked_ambiguous"
                blockers.append(
                    f"blocked_ambiguous_{record_kind}:{active_id}:{reason_code}"
                )
        elif not group and _is_legacy_story_profile(active_row=old_row):
            classification = "blocked_ambiguous"
            reason_code = "story_profile_requires_exact_source_migration_link"
            blockers.append(
                f"blocked_ambiguous_{record_kind}:{active_id}:{reason_code}"
            )
        elif len(group) > 1:
            raise ValueError(f"duplicate {record_kind} fidelity link: {active_id}")

        if not candidate_group:
            if classification != "blocked_ambiguous":
                classification = "unexplained_missing"
                reason_code = "active_identity_has_no_candidate_record"
            blockers.append(f"unexplained_{record_kind}_missing:{active_id}")
            unexplained += 1
        elif len(candidate_group) != len(candidate_ids):
            classification = "blocked_ambiguous"
            reason_code = "story_expansion_candidate_missing"
            blockers.append(
                f"blocked_ambiguous_{record_kind}:{active_id}:{reason_code}"
            )
        elif classification not in _ALLOWED_CHANGE_KINDS:
            if classification != "blocked_ambiguous":
                reason_code = "change_kind_not_whitelisted"
                blockers.append(
                    f"unapproved_{record_kind}_change:{active_id}:{classification}"
                )
        elif group and any(
            not _SHA256_RE.fullmatch(item.source_content_sha256)
            for item in group
        ):
            reason_code = "source_evidence_hash_invalid"
            blockers.append(f"invalid_{record_kind}_source_evidence:{active_id}")
        elif classification == "preserved_exact" and candidate_ids != (active_id,):
            reason_code = "preserved_exact_changes_identity"
            blockers.append(f"invalid_preserved_exact_link:{active_id}")
        elif classification == "preserved_rekeyed" and candidate_ids == (active_id,):
            reason_code = "preserved_rekeyed_does_not_change_identity"
            blockers.append(f"invalid_preserved_rekeyed_link:{active_id}")
        elif classification == "new_source_record":
            reason_code = "new_source_record_has_active_predecessor"
            blockers.append(f"invalid_new_source_link:{active_id}")
        elif classification == "corrected_semantics":
            correction = (
                group[0].legacy_section,
                group[0].candidate_section,
            )
            if correction not in _ALLOWED_SECTION_CORRECTIONS or (
                correction == ("profile", "story") and not story_valid
            ):
                reason_code = "section_correction_not_whitelisted"
                blockers.append(f"unapproved_section_correction:{active_id}")

        can_consume = (
            classification in _ALLOWED_CHANGE_KINDS
            and len(candidate_group) == len(candidate_ids)
            and not (
                classification == "corrected_semantics"
                and group
                and (
                    group[0].legacy_section,
                    group[0].candidate_section,
                )
                == ("profile", "story")
                and not story_valid
            )
        )
        is_story_expansion = (
            record_kind == "child"
            and story_valid
            and len(group) >= 1
        )
        duplicate_story_consumption = can_consume and (
            (
                is_story_expansion
                and any(
                    candidate_id in mapped_candidate_ids
                    for candidate_id in candidate_ids
                )
            )
            or (
                not is_story_expansion
                and any(
                    candidate_id in story_expansion_candidate_ids
                    for candidate_id in candidate_ids
                )
            )
        )
        if duplicate_story_consumption:
            classification = "blocked_ambiguous"
            reason_code = "candidate_has_multiple_active_predecessors"
            blockers.append(
                f"blocked_ambiguous_{record_kind}:{active_id}:{reason_code}"
            )
            can_consume = False
        if can_consume:
            mapped_candidate_ids.update(candidate_ids)
            if is_story_expansion:
                story_expansion_candidate_ids.update(candidate_ids)

        active_hash = _row_hash(old_row)
        if not candidate_group:
            candidate_hash = ""
        elif len(candidate_group) == 1:
            candidate_hash = _row_hash(candidate_group[0])
        else:
            candidate_hash = _hash_identity_list(
                _row_hash(row) for row in candidate_group
            )
        source_evidence = [
            _link_source_evidence(item)
            for item in sorted(group, key=lambda item: item.candidate_id)
        ]
        ledger_id = _ledger_id(
            record_kind,
            active_id,
            "|".join(candidate_ids),
        )
        details = {
            "payload_changed": bool(
                candidate_group and active_hash != candidate_hash
            ),
            "legacy_section": "" if not group else group[0].legacy_section,
            "candidate_section": "" if not group else group[0].candidate_section,
        }
        if is_story_expansion:
            details["candidate_count"] = len(candidate_group)
        row = {
            "schema_version": "huiji.fidelity-ledger/v1",
            "ledger_id": ledger_id,
            "record_kind": record_kind,
            "active_identity": active_id,
            "candidate_identities": [
                candidate_id
                for candidate_id in candidate_ids
                if candidate_id in candidate
            ],
            "classification": classification,
            "reason_code": reason_code,
            "active_sha256": active_hash,
            "candidate_sha256": candidate_hash,
            "source_evidence": source_evidence,
            "details": details,
        }
        ledger.append(row)
        classifications[(record_kind, active_id)] = (
            classification,
            candidate_ids if can_consume else (),
        )

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


def _looks_like_story_expansion(
    record_kind: str,
    group: Sequence[SemanticRecordLink],
) -> bool:
    return (
        record_kind == "child"
        and bool(group)
        and all(
            link.change_kind == "corrected_semantics"
            and link.legacy_section == "profile"
            and link.candidate_section == "story"
            for link in group
        )
    )


def _is_legacy_story_profile(*, active_row: Mapping[str, Any]) -> bool:
    return (
        str(active_row.get("entity_type") or "") == "story"
        and str(active_row.get("category") or "") == "story"
        and str(active_row.get("section_kind") or "") == "profile"
    )


def _looks_like_story_correction(
    record_kind: str,
    group: Sequence[SemanticRecordLink],
) -> bool:
    return (
        record_kind in {"parent", "child"}
        and bool(group)
        and all(
            link.change_kind == "corrected_semantics"
            and link.legacy_section == "profile"
            and link.candidate_section == "story"
            for link in group
        )
    )


def _validate_story_correction_group(
    *,
    record_kind: str,
    active_id: str,
    active_row: Mapping[str, Any],
    group: Sequence[SemanticRecordLink],
    candidate_rows: Mapping[str, Mapping[str, Any]],
    story_candidate_metadata_by_source: Mapping[
        tuple[str, str],
        Mapping[str, Mapping[str, Any]],
    ],
    story_parents: Mapping[str, Mapping[str, Any]],
) -> tuple[bool, str]:
    if not group:
        return False, "story_group_empty"
    first = group[0]
    source_title = first.source_title
    source_sha256 = first.source_content_sha256
    title_match = re.fullmatch(r"Data:Story/([^/]+)\.json", source_title)
    if title_match is None or not _SHA256_RE.fullmatch(source_sha256):
        return False, "story_source_identity_invalid"
    story_id = title_match.group(1)
    common = {
        (
            link.source_title,
            link.source_content_sha256,
            link.change_kind,
            link.legacy_section,
            link.candidate_section,
        )
        for link in group
    }
    if len(common) != 1:
        return False, "story_group_mixed_source_or_semantics"
    if any(link.legacy_id != active_id for link in group):
        return False, "story_group_legacy_identity_mismatch"
    if (
        str(active_row.get("entity_type") or "") != "story"
        or str(active_row.get("category") or "") != "story"
        or str(active_row.get("section_kind") or "") != "profile"
        or not _all_source_refs_complete(active_row)
        or not _row_has_source(
            active_row,
            source_title,
            source_sha256,
            path="$",
        )
        or _row_has_conflicting_source_hash(
            active_row,
            source_title,
            source_sha256,
        )
    ):
        return False, "story_active_source_or_section_invalid"

    target_ids = tuple(sorted(link.candidate_id for link in group))
    if len(target_ids) != len(set(target_ids)):
        return False, "story_group_duplicate_candidate"
    target_rows = {
        candidate_id: candidate_rows.get(candidate_id)
        for candidate_id in target_ids
    }
    if any(row is None for row in target_rows.values()):
        return False, "story_group_candidate_missing"

    expected_parent_id = f"story:{story_id}/story"
    if record_kind == "parent":
        if len(group) != 1 or first.json_path != "$":
            return False, "story_parent_group_shape_invalid"
        row = target_rows[target_ids[0]]
        assert row is not None
        if (
            target_ids[0] != expected_parent_id
            or str(row.get("parent_id") or "") != expected_parent_id
            or str(row.get("entity_id") or "") != story_id
            or str(row.get("entity_type") or "") != "story"
            or str(row.get("category") or "") != "story"
            or str(row.get("section_kind") or "") != "story"
            or not _all_source_refs_complete(row)
            or not _row_has_source(
                row,
                source_title,
                source_sha256,
                path="$",
            )
            or _row_has_conflicting_source_hash(
                row,
                source_title,
                source_sha256,
            )
        ):
            return False, "story_parent_source_or_identity_invalid"
        return True, "corrected_semantics"

    if record_kind != "child":
        return False, "story_record_kind_invalid"
    source_members = dict(
        story_candidate_metadata_by_source.get(
            (source_title, source_sha256),
            {},
        )
    )
    if set(target_ids) != set(source_members):
        return False, "story_group_partial_candidate_membership"
    if not source_members:
        return False, "story_group_has_no_candidates"

    parent_row = story_parents.get(expected_parent_id)
    if (
        parent_row is None
        or str(parent_row.get("entity_id") or "") != story_id
        or str(parent_row.get("entity_type") or "") != "story"
        or str(parent_row.get("category") or "") != "story"
        or str(parent_row.get("section_kind") or "") != "story"
        or set(parent_row.get("child_ids") or ()) != set(source_members)
        or not _row_has_source(
            parent_row,
            source_title,
            source_sha256,
            path="$",
        )
    ):
        return False, "story_parent_closure_invalid"

    links_by_candidate = {link.candidate_id: link for link in group}
    stable_tokens: set[str] = set()
    expected_owner = f"story:{story_id}"
    for candidate_id, metadata in source_members.items():
        row = candidate_rows[candidate_id]
        stable_token = str(metadata.get("stable_source_token") or "")
        source_token_kind = str(metadata.get("source_token_kind") or "")
        source_fields = metadata.get("source_fields")
        source_json_path = (
            str(source_fields.get("json_path") or "")
            if isinstance(source_fields, Mapping)
            else ""
        )
        matching_paths = {
            item["path"]
            for item in _source_ref_values(row)
            if item["title"] == source_title
            and item["hash"] == source_sha256
        }
        link = links_by_candidate[candidate_id]
        if (
            not stable_token
            or stable_token in stable_tokens
            or not source_token_kind
            or str(row.get("entity_id") or "") != story_id
            or str(row.get("entity_type") or "") != "story"
            or str(row.get("category") or "") != "story"
            or str(row.get("section_kind") or "") != "story"
            or str(row.get("parent_id") or "") != expected_parent_id
            or str(metadata.get("owner_entity_id") or "") != expected_owner
            or str(metadata.get("owner_page_id") or "") != expected_owner
            or candidate_id != f"{expected_parent_id}/{stable_token}"
            or not _all_source_refs_complete(row)
            or _row_has_conflicting_source_hash(
                row,
                source_title,
                source_sha256,
            )
            or not link.json_path.startswith("$.")
            or link.json_path not in matching_paths
            or source_json_path != link.json_path
        ):
            return False, "story_child_source_owner_or_token_invalid"
        stable_tokens.add(stable_token)
    return True, "corrected_semantics"


def _source_ref_values(row: Mapping[str, Any]) -> tuple[dict[str, str], ...]:
    values: list[dict[str, str]] = []
    for raw in row.get("source_refs") or ():
        if not isinstance(raw, Mapping):
            continue
        values.append(
            {
                "kind": str(raw.get("source_kind") or raw.get("kind") or ""),
                "title": str(
                    raw.get("source_title") or raw.get("title") or ""
                ),
                "hash": str(
                    raw.get("source_content_sha256")
                    or raw.get("content_sha256")
                    or ""
                ),
                "path": str(
                    raw.get("json_path") or raw.get("source_row_id") or ""
                ),
            }
        )
    return tuple(values)


def _story_candidate_metadata_by_source(
    children: Sequence[SemanticChild],
) -> dict[tuple[str, str], dict[str, Mapping[str, Any]]]:
    result: dict[
        tuple[str, str],
        dict[str, Mapping[str, Any]],
    ] = defaultdict(dict)
    for child in children:
        candidate_id = child.block.child_id
        row = child.block.to_json()
        if (
            str(row.get("entity_type") or "") != "story"
            or str(row.get("category") or "") != "story"
            or str(row.get("section_kind") or "") != "story"
        ):
            continue
        for ref in _source_ref_values(row):
            if (
                re.fullmatch(r"Data:Story/([^/]+)\.json", ref["title"])
                and _SHA256_RE.fullmatch(ref["hash"])
            ):
                result[(ref["title"], ref["hash"])][candidate_id] = {
                    "stable_source_token": child.stable_source_token,
                    "source_token_kind": child.source_token_kind,
                    "owner_entity_id": child.owner_entity_id,
                    "owner_page_id": child.owner_page_id,
                    "source_fields": dict(child.source_fields),
                }
    return dict(result)


def _all_source_refs_complete(row: Mapping[str, Any]) -> bool:
    refs = _source_ref_values(row)
    return bool(refs) and all(
        ref["kind"]
        and ref["title"]
        and _SHA256_RE.fullmatch(ref["hash"])
        and ref["path"]
        for ref in refs
    )


def _row_has_source(
    row: Mapping[str, Any],
    title: str,
    source_sha256: str,
    *,
    path: str | None = None,
) -> bool:
    return any(
        ref["title"] == title
        and ref["hash"] == source_sha256
        and (path is None or ref["path"] == path)
        for ref in _source_ref_values(row)
    )


def _row_has_conflicting_source_hash(
    row: Mapping[str, Any],
    title: str,
    source_sha256: str,
) -> bool:
    return any(
        ref["title"] == title and ref["hash"] != source_sha256
        for ref in _source_ref_values(row)
    )


def _reconcile_exclusions(
    active_rows: Sequence[Mapping[str, Any]], projection: CorpusProjection
) -> tuple[list[dict[str, Any]], list[str]]:
    candidate_by_source: dict[str, list[Any]] = defaultdict(list)
    candidate_by_identity: dict[str, Any] = {}
    for exclusion in projection.exclusions:
        candidate_identity = _exclusion_candidate_identity(exclusion)
        existing = candidate_by_identity.get(candidate_identity)
        if existing is not None:
            if existing.to_json() != exclusion.to_json():
                raise ValueError(
                    "fidelity ledger contains conflicting candidate exclusion identity"
                )
            continue
        candidate_by_identity[candidate_identity] = exclusion
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
                _exclusion_candidate_identity(item)
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
    for exclusion in candidate_by_identity.values():
        key = (exclusion.source_title, exclusion.reason_code)
        if key in matched:
            continue
        candidate_id = _exclusion_candidate_identity(exclusion)
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
                        "source_identity": exclusion.source_identity,
                        "source_content_sha256": exclusion.source_content_sha256,
                        "json_path": exclusion.json_path,
                    }
                ],
                "details": {},
            }
        )
    return ledger, blockers


def _exclusion_candidate_identity(exclusion: Any) -> str:
    return (
        f"{exclusion.source_title}#{exclusion.json_path}:{exclusion.reason_code}:"
        f"source:{exclusion.source_identity}"
    )


def _reconcile_child_bm25(
    active_children: Sequence[Mapping[str, Any]],
    active_bm25: Sequence[Mapping[str, Any]],
    classifications: Mapping[
        tuple[str, str],
        tuple[str, tuple[str, ...]],
    ],
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
        classification, candidate_ids = classifications.get(
            ("child", active_id), ("unexplained_missing", ())
        )
        reason = "derived_from_child_fidelity"
        if active_id != expected_id:
            classification = "unexplained_bm25_sequence_drift"
            reason = "active_child_bm25_sequence_mismatch"
            blockers.append(f"active_child_bm25_sequence_mismatch:{index}")
        rows.append(
            {
                "schema_version": "huiji.fidelity-ledger/v1",
                "ledger_id": _ledger_id(
                    "child_bm25",
                    f"{index}:{active_id}",
                    "|".join(candidate_ids),
                ),
                "record_kind": "child_bm25",
                "active_identity": f"{index}:{active_id}",
                "candidate_identities": list(candidate_ids),
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
