"""Generic entity ownership checks for retrieval and media packets."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

from src.rag.contracts import EntityRef


class OwnershipViolation(RuntimeError):
    """Raised when an owner-bound request would expose another entity."""


@dataclass(frozen=True)
class OwnershipDiagnostics:
    stage: str
    before_count: int
    after_count: int
    owner_mismatch: int
    missing_owner_metadata: int
    expected_ownership_key: tuple[str, str] | None = None

    @property
    def owner_shortfall(self) -> int:
        return max(0, self.before_count - self.after_count)


def ownership_key(row: Mapping[str, object]) -> tuple[str, str] | None:
    entity_type = str(row.get("entity_type") or "").strip()
    entity_id = str(row.get("entity_id") or "").strip()
    return (entity_type, entity_id) if entity_type and entity_id else None


def filter_owned_rows(
    rows: Iterable[Mapping[str, object]],
    owner: EntityRef | None,
    stage: str,
) -> tuple[list[dict[str, object]], OwnershipDiagnostics]:
    materialized = [dict(row) for row in rows]
    if owner is None:
        return materialized, OwnershipDiagnostics(
            stage=stage,
            before_count=len(materialized),
            after_count=len(materialized),
            owner_mismatch=0,
            missing_owner_metadata=0,
        )

    kept: list[dict[str, object]] = []
    owner_mismatch = 0
    missing_owner_metadata = 0
    for row in materialized:
        key = ownership_key(row)
        if key is None:
            missing_owner_metadata += 1
        elif key == owner.ownership_key:
            kept.append(row)
        else:
            owner_mismatch += 1
    return kept, OwnershipDiagnostics(
        stage=stage,
        before_count=len(materialized),
        after_count=len(kept),
        owner_mismatch=owner_mismatch,
        missing_owner_metadata=missing_owner_metadata,
        expected_ownership_key=owner.ownership_key,
    )


def validate_target_parent(
    parent_id: str | None,
    owner: EntityRef | None,
    rows: Iterable[Mapping[str, object]],
) -> str | None:
    target = str(parent_id or "").strip()
    if not target:
        return None
    matches = [row for row in rows if str(row.get("parent_id") or "").strip() == target]
    if not matches:
        raise OwnershipViolation("target parent is absent from the current retrieval rows")
    if owner is not None and not any(ownership_key(row) == owner.ownership_key for row in matches):
        raise OwnershipViolation("target parent does not belong to the resolved owner")
    return target


def validate_owned_media(
    media: Iterable[Mapping[str, object]],
    owner: EntityRef | None,
) -> tuple[list[dict[str, object]], OwnershipDiagnostics]:
    return filter_owned_rows(media, owner, "media")


def assert_packet_ownership(
    entity_ref: EntityRef | None,
    sources: Sequence[Mapping[str, object]],
    media: Sequence[Mapping[str, object]],
) -> None:
    if entity_ref is None:
        return
    mismatches = [
        item
        for item in (*sources, *media)
        if ownership_key(item) != entity_ref.ownership_key
    ]
    if mismatches:
        raise OwnershipViolation("final packet contains owner mismatch")


__all__ = [
    "OwnershipDiagnostics",
    "OwnershipViolation",
    "assert_packet_ownership",
    "filter_owned_rows",
    "ownership_key",
    "validate_owned_media",
    "validate_target_parent",
]
