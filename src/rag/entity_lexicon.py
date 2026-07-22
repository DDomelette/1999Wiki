"""Huiji-backed entity lexicon for fallback query planning."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from src.rag.contracts import EntityRef


_PLACEHOLDER_NAMES = {"???"}


@dataclass(frozen=True)
class EntityMatch:
    canonical: str
    matched_text: str
    aliases: tuple[str, ...]
    entity_type: str
    entity_id: str

    @property
    def ownership_key(self) -> tuple[str, str]:
        return self.entity_type, self.entity_id

    def to_ref(self, resolution_mode: str) -> EntityRef:
        return EntityRef(
            self.entity_type,
            self.entity_id,
            self.canonical,
            self.aliases,
            resolution_mode,
        )


@dataclass(frozen=True)
class EntityResolution:
    entity_ref: EntityRef | None
    ambiguous: tuple[EntityRef, ...] = ()


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _is_placeholder_name(value: str) -> bool:
    return bool(value) and (value in _PLACEHOLDER_NAMES or set(value) == {"?"})


def _dedupe(parts: Iterable[str]) -> tuple[str, ...]:
    out: list[str] = []
    for part in parts:
        text = _clean_text(part)
        if text and text not in out:
            out.append(text)
    return tuple(out)


class EntityLexicon:
    def __init__(self, entries: tuple[tuple[str, EntityMatch], ...]) -> None:
        self._entries = entries

    @classmethod
    def from_records(cls, records: Iterable[dict[str, Any]]) -> EntityLexicon:
        owners: dict[tuple[str, str], tuple[str, tuple[str, ...]]] = {}
        for row in records:
            canonical = _clean_text(row.get("entity_name") or row.get("name"))
            entity_type = _clean_text(row.get("entity_type"))
            entity_id = _clean_text(row.get("entity_id"))
            if (
                not canonical
                or _is_placeholder_name(canonical)
                or not entity_type
                or not entity_id
            ):
                continue
            aliases_raw = row.get("entity_aliases")
            if aliases_raw is None:
                aliases_raw = row.get("aliases")
            if isinstance(aliases_raw, str):
                aliases_raw = (aliases_raw,)
            aliases = tuple(
                alias
                for alias in _dedupe(aliases_raw or ())
                if alias != canonical and not _is_placeholder_name(alias)
            )
            key = (entity_type, entity_id)
            existing_canonical, existing_aliases = owners.get(key, (canonical, ()))
            merged_aliases = _dedupe(
                (
                    *existing_aliases,
                    *((canonical,) if canonical != existing_canonical else ()),
                    *aliases,
                )
            )
            owners[key] = (existing_canonical, merged_aliases)

        entries: list[tuple[str, EntityMatch]] = []
        for (entity_type, entity_id), (canonical, aliases) in owners.items():
            entries.append((canonical, EntityMatch(
                canonical=canonical,
                matched_text=canonical,
                aliases=aliases,
                entity_type=entity_type,
                entity_id=entity_id,
            )))
            for alias in aliases:
                entries.append((alias, EntityMatch(
                    canonical=canonical,
                    matched_text=alias,
                    aliases=aliases,
                    entity_type=entity_type,
                    entity_id=entity_id,
                )))
        entries.sort(
            key=lambda item: (
                -len(item[0]),
                item[0].casefold(),
                item[1].entity_type,
                item[1].entity_id,
            )
        )
        return cls(tuple(entries))

    @classmethod
    def from_huiji(cls, cfg: Any, artifact_snapshot: Any | None = None) -> EntityLexicon:
        from src.huiji_rag.io import iter_jsonl
        from src.huiji_rag.runtime_artifacts import resolve_runtime_artifact_snapshot

        snapshot = artifact_snapshot or resolve_runtime_artifact_snapshot(cfg)
        return cls.from_records(iter_jsonl(snapshot.parent_blocks))

    def match(
        self,
        query: str,
        entity_type_hint: str | None = None,
    ) -> EntityMatch | None:
        candidates = self._longest_matches(query)
        hint = _clean_text(entity_type_hint)
        if hint:
            candidates = tuple(item for item in candidates if item.entity_type == hint)
        by_owner = {candidate.ownership_key: candidate for candidate in candidates}
        if len(by_owner) != 1:
            return None
        return next(iter(by_owner.values()))

    def resolve(
        self,
        query: str,
        entity_type_hint: str | None = None,
    ) -> EntityResolution:
        candidates = self._longest_matches(query)
        hint = _clean_text(entity_type_hint)
        if hint:
            candidates = tuple(item for item in candidates if item.entity_type == hint)
        by_owner: dict[tuple[str, str], EntityMatch] = {}
        for candidate in candidates:
            by_owner.setdefault(candidate.ownership_key, candidate)
        if len(by_owner) == 1:
            match = next(iter(by_owner.values()))
            mode = "current_exact" if match.matched_text == match.canonical else "current_alias"
            return EntityResolution(match.to_ref(mode))
        ambiguous = tuple(
            match.to_ref("ambiguous")
            for _, match in sorted(by_owner.items(), key=lambda item: item[0])
        )
        return EntityResolution(None, ambiguous)

    def _longest_matches(self, query: str) -> tuple[EntityMatch, ...]:
        lowered_query = query.casefold()
        matched: list[EntityMatch] = []
        longest = 0
        for term, match in self._entries:
            if term in query or term.casefold() in lowered_query:
                length = len(term)
                if length < longest:
                    break
                if length > longest:
                    matched.clear()
                    longest = length
                matched.append(match)
        return tuple(matched)


__all__ = ["EntityLexicon", "EntityMatch", "EntityResolution"]
