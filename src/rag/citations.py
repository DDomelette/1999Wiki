from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Literal, cast

from .contracts import (
    BranchResult,
    CitationValidation,
    GlobalSourceAllocation,
    SourceRef,
    freeze_value,
)
from .tracing import NullTrace, RequestTrace

GroundingMode = Literal["grounded", "ungrounded"]
RepairCallback = Callable[[str, str, tuple[SourceRef, ...]], str]

_CANONICAL_TOKEN_RE = re.compile(r"\[(S\d{2,})\]")
_S_LIKE_BRACKET_RE = re.compile(r"\[\s*S\d{2,}(?:\s*[,，]\s*S\d{2,})*\s*\]")
_ANY_BRACKET_RE = re.compile(r"\[([^\[\]]+)\]")
_FULLWIDTH_BRACKET_RE = re.compile(r"【([^【】]+)】")
_COMBINED_IDS_RE = re.compile(r"^\s*S\d{2,}(?:\s*[,，]\s*S\d{2,})+\s*$")


class SourceIdentityCollision(ValueError):
    """A stable source identity mapped to conflicting evidence."""

    def __init__(self, subtask_id: str) -> None:
        self.subtask_id = str(subtask_id)
        super().__init__("source_identity_collision")


def build_global_source_map(
    branch_sources: Sequence[tuple[str, Sequence[Mapping[str, Any]]]],
) -> GlobalSourceAllocation:
    global_sources: list[Mapping[str, Any]] = []
    source_refs: list[SourceRef] = []
    branch_ids: dict[str, tuple[str, ...]] = {}
    identities: dict[tuple[str, str, str, str], tuple[str, str, str]] = {}
    citation_by_identity: dict[tuple[str, str, str, str], str] = {}

    for subtask_id, sources in branch_sources:
        allocated: list[str] = []
        for source in sources:
            identity = (
                _text(source.get("entity_type")),
                _text(source.get("entity_id")),
                _text(source.get("child_id")),
                _text(source.get("parent_id")),
            )
            fingerprint = (
                _text(source.get("content")),
                _text(source.get("content_hash")),
                _source_reference_fingerprint(source.get("source_refs")),
            )
            previous = identities.get(identity)
            if previous is not None and previous != fingerprint:
                raise SourceIdentityCollision(str(subtask_id))
            citation_id = citation_by_identity.get(identity)
            if citation_id is None:
                citation_id = f"S{len(global_sources) + 1:02d}"
                identities[identity] = fingerprint
                citation_by_identity[identity] = citation_id
                row = dict(source)
                row["citation_id"] = citation_id
                global_sources.append(cast(Mapping[str, Any], freeze_value(row)))
                source_refs.append(_source_ref(citation_id, source))
            allocated.append(citation_id)
        branch_ids[str(subtask_id)] = tuple(dict.fromkeys(allocated))
    return GlobalSourceAllocation(
        sources=tuple(global_sources),
        source_map=tuple(source_refs),
        branch_source_ids=branch_ids,
    )


def validate_global_citations(
    branches: Sequence[BranchResult],
    allocation: GlobalSourceAllocation,
) -> CitationValidation:
    known_ids = {ref.citation_id for ref in allocation.source_map}
    public_ids = [
        _text(source.get("citation_id"))
        for source in allocation.sources
    ]
    invalid: list[str] = []
    used: list[str] = []
    for branch in branches:
        allowed = set(allocation.branch_source_ids.get(branch.subtask_id, ()))
        branch_ids = tuple(_CANONICAL_TOKEN_RE.findall(branch.answer))
        if branch.grounding_mode == "grounded" and branch.status == "succeeded":
            if not branch.citation_validation.valid:
                invalid.append("branch_validation_failed")
            if not branch_ids:
                invalid.append("missing_required")
            invalid.extend(item for item in branch_ids if item not in allowed)
        elif branch_ids:
            invalid.extend(branch_ids)
        invalid.extend(item for item in branch.source_ids if item not in known_ids)
        used.extend(branch_ids)
    if len(public_ids) != len(set(public_ids)) or set(public_ids) != known_ids:
        invalid.append("global_source_map_invalid")
    invalid_ids = tuple(dict.fromkeys(invalid))
    return CitationValidation(
        valid=not invalid_ids,
        used_ids=tuple(dict.fromkeys(used)),
        invalid_ids=invalid_ids,
        missing_required="missing_required" in invalid_ids,
    )


def build_source_map(
    sources: Sequence[Mapping[str, Any]],
) -> tuple[tuple[Mapping[str, Any], ...], tuple[SourceRef, ...]]:
    """Assign request-local citation IDs after final source ordering is frozen."""
    frozen_sources: list[Mapping[str, Any]] = []
    source_refs: list[SourceRef] = []

    for index, source in enumerate(sources, start=1):
        citation_id = f"S{index:02d}"
        row = dict(source)
        row["citation_id"] = citation_id
        frozen_sources.append(cast(Mapping[str, Any], freeze_value(row)))
        source_refs.append(
            SourceRef(
                citation_id=citation_id,
                entity_type=_text(source.get("entity_type")),
                entity_id=_text(source.get("entity_id")),
                child_id=_text(source.get("child_id")),
                parent_id=_text(source.get("parent_id")),
                display_name=_text(source.get("name")),
                heading_path=_text(source.get("heading_path")),
            )
        )

    return tuple(frozen_sources), tuple(source_refs)


def _source_ref(citation_id: str, source: Mapping[str, Any]) -> SourceRef:
    return SourceRef(
        citation_id=citation_id,
        entity_type=_text(source.get("entity_type")),
        entity_id=_text(source.get("entity_id")),
        child_id=_text(source.get("child_id")),
        parent_id=_text(source.get("parent_id")),
        display_name=_text(source.get("name")),
        heading_path=_text(source.get("heading_path")),
    )


def _source_reference_fingerprint(value: Any) -> str:
    if not isinstance(value, (list, tuple)):
        return ""
    rows: list[tuple[str, str, str, str]] = []
    for item in value:
        if not isinstance(item, Mapping):
            return "invalid_source_refs"
        rows.append((
            _text(item.get("site") or item.get("source_kind")),
            _text(item.get("title") or item.get("source_title")),
            _text(item.get("revid") or item.get("source_row_id")),
            _text(item.get("content_sha256") or item.get("source_content_sha256")),
        ))
    return repr(tuple(rows))


def format_citation_context(
    sources: Sequence[Mapping[str, Any]],
    source_map: Sequence[SourceRef],
) -> str:
    if len(sources) != len(source_map):
        raise ValueError("sources and source_map must have equal lengths")

    blocks: list[str] = []
    for source, ref in zip(sources, source_map, strict=True):
        content = str(source.get("content") or "").strip()
        labels = tuple(dict.fromkeys(
            value
            for value in (
                ref.display_name,
                ref.heading_path,
                str(source.get("section_kind") or "").strip(),
            )
            if value
        ))
        header = f"[{ref.citation_id}]"
        if labels:
            header = f"{header} {' / '.join(labels)}"
        blocks.append(f"{header}\n{content}".rstrip())
    return "\n\n".join(blocks)


def normalize_citation_format(
    answer: str,
    known_ids: frozenset[str],
) -> tuple[str, bool]:
    """Split combined brackets only when every member is a current source ID."""

    fullwidth_normalized = _FULLWIDTH_BRACKET_RE.sub(
        lambda match: (
            f"[{match.group(1).strip()}]"
            if re.match(r"^\s*[sS]\s*\d", match.group(1))
            else match.group(0)
        ),
        answer,
    )

    def replace(match: re.Match[str]) -> str:
        content = match.group(1)
        if re.match(r"^\s*[sS]\s*\d", content):
            ids = tuple(re.findall(r"S\d{2,}", content))
            if (
                len(ids) >= 2
                and _COMBINED_IDS_RE.fullmatch(content)
                and all(citation_id in known_ids for citation_id in ids)
            ):
                return "".join(f"[{citation_id}]" for citation_id in ids)
            return match.group(0)
        return match.group(0)

    normalized = _ANY_BRACKET_RE.sub(replace, fullwidth_normalized)
    return normalized, normalized != answer


def validate_citations(
    answer: str,
    source_map: Sequence[SourceRef],
    grounding_mode: GroundingMode,
    *,
    repair_attempts: int = 0,
    normalized: bool = False,
    warnings: Sequence[str] = (),
) -> CitationValidation:
    known_ids = frozenset(ref.citation_id for ref in source_map)
    used_sequence = tuple(_CANONICAL_TOKEN_RE.findall(answer))
    used_ids = tuple(dict.fromkeys(used_sequence))
    duplicate_ids = tuple(
        citation_id
        for citation_id in used_ids
        if used_sequence.count(citation_id) > 1
    )
    invalid_ids = tuple(citation_id for citation_id in used_ids if citation_id not in known_ids)
    malformed_labels = tuple(
        [
            match.group(0)
            for match in _ANY_BRACKET_RE.finditer(answer)
            if (
                re.match(r"^\s*[sS]\s*\d", match.group(1))
                and not re.fullmatch(r"S\d{2,}", match.group(1))
            )
        ]
        + [
            match.group(0)
            for match in _FULLWIDTH_BRACKET_RE.finditer(answer)
            if re.match(r"^\s*[sS]\s*\d", match.group(1))
        ]
    )
    missing_required = grounding_mode == "grounded" and bool(source_map) and not used_ids
    ungrounded_claim = grounding_mode == "ungrounded" and bool(used_ids)
    valid = not invalid_ids and not malformed_labels and not missing_required and not ungrounded_claim
    all_warnings = tuple(warnings)
    if malformed_labels:
        all_warnings = (*all_warnings, "invalid_citation_label")

    return CitationValidation(
        valid=valid,
        used_ids=used_ids,
        invalid_ids=invalid_ids,
        duplicate_ids=duplicate_ids,
        missing_required=missing_required,
        normalized=normalized,
        repair_attempts=repair_attempts,
        warnings=tuple(dict.fromkeys(all_warnings)),
    )


def validate_or_repair_answer(
    *,
    draft: str,
    context: str,
    source_map: Sequence[SourceRef],
    grounding_mode: GroundingMode,
    repair: RepairCallback | None = None,
    trace: RequestTrace | NullTrace | None = None,
) -> tuple[str, CitationValidation]:
    active_trace = trace or NullTrace()
    refs = tuple(source_map)
    if grounding_mode == "ungrounded":
        cleaned = _strip_source_like_tokens(draft)
        warnings = ("ungrounded_citation_removed",) if cleaned != draft else ()
        with active_trace.span("citation.validate", source_count=0):
            validation = validate_citations(cleaned, (), "ungrounded", warnings=warnings)
        return cleaned, validation

    with active_trace.span("citation.validate", source_count=len(refs)):
        validation = validate_citations(draft, refs, "grounded")
    if validation.valid:
        return draft, validation

    normalized_answer, changed = normalize_citation_format(
        draft,
        frozenset(ref.citation_id for ref in refs),
    )
    if changed:
        with active_trace.span("citation.validate", source_count=len(refs)):
            validation = validate_citations(
                normalized_answer,
                refs,
                "grounded",
                normalized=True,
                warnings=("citation_format_normalized",),
            )
        if validation.valid:
            return normalized_answer, validation

    if repair is not None:
        try:
            with active_trace.span("citation.repair", source_count=len(refs)):
                repaired = str(repair(normalized_answer, context, refs)).strip()
        except Exception:
            validation = CitationValidation(
                valid=False,
                invalid_ids=validation.invalid_ids,
                duplicate_ids=validation.duplicate_ids,
                missing_required=validation.missing_required,
                normalized=changed,
                repair_attempts=1,
                warnings=("citation_repair_failed",),
            )
        else:
            repaired, repaired_normalized = normalize_citation_format(
                repaired,
                frozenset(ref.citation_id for ref in refs),
            )
            with active_trace.span("citation.validate", source_count=len(refs)):
                validation = validate_citations(
                    repaired,
                    refs,
                    "grounded",
                    repair_attempts=1,
                    normalized=changed or repaired_normalized,
                    warnings=("citation_repair_attempted",),
                )
            if validation.valid:
                return repaired, validation

    attempts = 1 if repair is not None else 0
    if refs:
        fallback = (
            "检索到的资料不足以可靠生成完整回答；"
            f"请以本轮已检索资料为限 [{refs[0].citation_id}]。"
        )
        fallback_validation = validate_citations(
            fallback,
            refs,
            "grounded",
            repair_attempts=attempts,
            normalized=changed,
            warnings=tuple(dict.fromkeys((*validation.warnings, "citation_safe_fallback"))),
        )
        return fallback, fallback_validation

    fallback = "检索到的资料不足以可靠生成完整回答。"
    return fallback, CitationValidation(
        valid=False,
        missing_required=True,
        normalized=changed,
        repair_attempts=attempts,
        warnings=tuple(dict.fromkeys((*validation.warnings, "citation_validation_failed"))),
    )


def _strip_source_like_tokens(answer: str) -> str:
    cleaned = _S_LIKE_BRACKET_RE.sub("", answer)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r"\s+([,.;:!?，。；：！？])", r"\1", cleaned)
    return cleaned.strip()


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


__all__ = [
    "SourceIdentityCollision",
    "build_global_source_map",
    "build_source_map",
    "format_citation_context",
    "normalize_citation_format",
    "validate_citations",
    "validate_global_citations",
    "validate_or_repair_answer",
]
