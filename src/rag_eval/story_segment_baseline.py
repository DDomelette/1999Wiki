"""Frozen Story Segment evaluation and baseline-equivalence contracts.

This module deliberately implements a narrow, deterministic bridge from the
currently active Child retrieval format to the Story Atom gold artifact.  It
does not perform fuzzy matching and never consumes generated or rewritten text.
"""
from __future__ import annotations

import hashlib
import json
import math
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Mapping, Sequence


EVAL_CASE_SCHEMA_VERSION = "rag.story-segment-eval-case/v1"
THRESHOLDS_SCHEMA_VERSION = "rag.story-segment-thresholds/v1"
MATCHER_SCHEMA_VERSION = "rag.story-segment-atom-equivalence/v1"
STAGES = ("retrieval_at_k", "final_context")
MATCH_RULES = (
    "exact_atom_id",
    "exact_source_path_revision_hash",
    "unique_exact_text_span",
    "unmatched",
    "ambiguous",
)
STRATUM_MINIMUMS: Mapping[str, int] = {
    "exact_atom": 12,
    "single_story_fact": 10,
    "single_story_multi_detail": 10,
    "branch_boundary": 8,
    "multi_story": 8,
    "topic_story": 8,
    "character_story_shortfall": 4,
    "authorization": 12,
    "answer_scope": 8,
}
AUTHORIZATION_ORIGINS = frozenset({"direct_query", "verified_continuation", "validated_conversation_anchor"})
AUTHORIZATION_COVERAGE = frozenset({"complete", "page_partial", "anchor_follow_up", "open_story_domain"})
RETRIEVAL_OUTCOMES = frozenset({"sufficient", "partial", "empty", "failed", "not_applicable"})
EVIDENCE_STATES = frozenset({"sufficient", "partial", "empty"})
NARRATIVE_COVERAGE = frozenset({"local", "bounded", "non_exhaustive"})


def canonical_evidence_text(text: str) -> str:
    """Apply the only normalization permitted by Spec section 25.6."""

    if not isinstance(text, str):
        raise TypeError("evidence text must be a string")
    return unicodedata.normalize("NFC", text.replace("\r\n", "\n").replace("\r", "\n"))


def evidence_sha256(text: str) -> str:
    return hashlib.sha256(canonical_evidence_text(text).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class AtomEvidenceTarget:
    query_id: str
    atom_id: str
    required_atom_group: str
    source_title: str
    source_json_path: str
    source_content_sha256: str
    normalized_evidence_sha256: str


@dataclass(frozen=True)
class AtomEquivalenceMatch:
    query_id: str
    stage: Literal["retrieval_at_k", "final_context"]
    result_rank: int
    atom_id: str
    match_rule: Literal[
        "exact_atom_id",
        "exact_source_path_revision_hash",
        "unique_exact_text_span",
        "unmatched",
        "ambiguous",
    ]
    matched_span: tuple[int, int] | None
    matched: bool
    reason_code: str


@dataclass(frozen=True)
class RequiredAtomGroup:
    group_id: str
    atoms: tuple[AtomEvidenceTarget, ...]


@dataclass(frozen=True)
class StorySegmentEvalCase:
    schema_version: str
    query_id: str
    query: str
    stratum: str
    query_type: str
    gold_artifact_sha256: str
    request_plan_source_spans: tuple[Mapping[str, object], ...]
    expected_authorization_origin: str | None
    expected_story_owner_ids: tuple[str, ...]
    expected_story_owner_order: tuple[str, ...]
    forbidden_owner_ids: tuple[str, ...]
    required_atom_groups: tuple[RequiredAtomGroup, ...]
    required_topic_page_sources: tuple[Mapping[str, object], ...]
    branch_constraints: Mapping[str, object]
    allow_shortfall: bool
    expected_answer_scope: Mapping[str, object]
    source_relevance: Mapping[str, object]
    expected_call_counts: Mapping[str, int]
    continuation: Mapping[str, object]
    anchor: Mapping[str, object]
    expected_retrieval_outcome: str
    review: Mapping[str, object]


@dataclass(frozen=True)
class StorySegmentThresholds:
    schema_version: str
    denominator_definitions: Mapping[str, str]
    hard_gates: Mapping[str, Mapping[str, object]]


def _is_sha256(value: object) -> bool:
    if not isinstance(value, str) or len(value) != 64:
        return False
    return all(character in "0123456789abcdef" for character in value)


def _as_string_tuple(value: object, *, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{field} must be an array of strings")
    return tuple(value)


def _as_mapping_tuple(value: object, *, field: str) -> tuple[Mapping[str, object], ...]:
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ValueError(f"{field} must be an array of objects")
    return tuple(value)


def _as_mapping(value: object, *, field: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{field} must be an object")
    return value


def _load_atom_target(query_id: str, group_id: str, payload: object) -> AtomEvidenceTarget:
    if not isinstance(payload, dict):
        raise ValueError("gold Atom must be an object")
    required = (
        "atom_id",
        "source_title",
        "source_json_path",
        "source_content_sha256",
        "normalized_evidence_sha256",
    )
    for field in required:
        if not isinstance(payload.get(field), str) or not payload[field]:
            raise ValueError(f"gold Atom {field} must be a non-empty string")
    if not _is_sha256(payload["source_content_sha256"]):
        raise ValueError("gold Atom source_content_sha256 must be lowercase SHA-256")
    if not _is_sha256(payload["normalized_evidence_sha256"]):
        raise ValueError("gold Atom normalized_evidence_sha256 must be lowercase SHA-256")
    return AtomEvidenceTarget(
        query_id=query_id,
        atom_id=payload["atom_id"],
        required_atom_group=group_id,
        source_title=payload["source_title"],
        source_json_path=payload["source_json_path"],
        source_content_sha256=payload["source_content_sha256"],
        normalized_evidence_sha256=payload["normalized_evidence_sha256"],
    )


def _load_eval_case(payload: object) -> StorySegmentEvalCase:
    if not isinstance(payload, dict):
        raise ValueError("eval row must be an object")
    if payload.get("schema_version") != EVAL_CASE_SCHEMA_VERSION:
        raise ValueError("unsupported Story Segment eval case schema")
    query_id = payload.get("query_id")
    query = payload.get("query")
    stratum = payload.get("stratum")
    if not isinstance(query_id, str) or not query_id:
        raise ValueError("query_id must be a non-empty string")
    if not isinstance(query, str) or not query:
        raise ValueError("query must be a non-empty string")
    if stratum not in STRATUM_MINIMUMS:
        raise ValueError(f"unknown stratum: {stratum!r}")
    artifact_sha = payload.get("gold_artifact_sha256")
    if not _is_sha256(artifact_sha):
        raise ValueError("gold_artifact_sha256 must be lowercase SHA-256")

    raw_groups = payload.get("required_atom_groups")
    if not isinstance(raw_groups, list):
        raise ValueError("required_atom_groups must be an array")
    groups: list[RequiredAtomGroup] = []
    group_ids: set[str] = set()
    for raw_group in raw_groups:
        if not isinstance(raw_group, dict) or set(raw_group) != {"group_id", "atoms"}:
            raise ValueError("required Atom group accepts only group_id and atoms")
        group_id = raw_group.get("group_id")
        atoms = raw_group.get("atoms")
        if not isinstance(group_id, str) or not group_id or group_id in group_ids:
            raise ValueError("required Atom group IDs must be unique non-empty strings")
        if not isinstance(atoms, list) or not atoms:
            raise ValueError("required Atom group atoms must be non-empty")
        group_ids.add(group_id)
        groups.append(
            RequiredAtomGroup(
                group_id=group_id,
                atoms=tuple(_load_atom_target(query_id, group_id, atom) for atom in atoms),
            )
        )

    expected_call_counts = _as_mapping(
        payload.get("expected_call_counts", {}), field="expected_call_counts"
    )
    if not all(
        isinstance(key, str) and isinstance(value, int) and value >= 0
        for key, value in expected_call_counts.items()
    ):
        raise ValueError("expected_call_counts must contain non-negative integers")
    review = _as_mapping(payload.get("review", {}), field="review")
    if review.get("status") != "human_reviewed" or not isinstance(
        review.get("review_basis"), str
    ):
        raise ValueError("each eval case must carry a human_reviewed review receipt")

    owner_ids = _as_string_tuple(
        payload.get("expected_story_owner_ids", []), field="expected_story_owner_ids"
    )
    owner_order = _as_string_tuple(
        payload.get("expected_story_owner_order", []), field="expected_story_owner_order"
    )
    if owner_ids != owner_order:
        raise ValueError("expected Story owner IDs and order must be identical")
    spans = _as_mapping_tuple(
        payload.get("request_plan_source_spans", []), field="request_plan_source_spans"
    )
    last_end = -1
    for span in spans:
        start, end, text = span.get("start"), span.get("end"), span.get("text")
        if not isinstance(start, int) or not isinstance(end, int) or not isinstance(text, str):
            raise ValueError("source span start/end/text types are invalid")
        if start < 0 or end <= start or start < last_end or query[start:end] != text:
            raise ValueError("source spans must be ordered, non-overlapping exact query slices")
        last_end = end

    origin = payload.get("expected_authorization_origin")
    if origin is not None and origin not in AUTHORIZATION_ORIGINS:
        raise ValueError("unknown expected authorization origin")
    if origin in {"verified_continuation", "validated_conversation_anchor"} and spans:
        raise ValueError("continuation and anchor cases cannot carry direct-query Story spans")
    outcome = payload.get("expected_retrieval_outcome")
    if outcome not in RETRIEVAL_OUTCOMES:
        raise ValueError("unknown expected retrieval outcome")
    expected_scope = _as_mapping(
        payload.get("expected_answer_scope", {}), field="expected_answer_scope"
    )
    if set(expected_scope) != {"applicable", "value"} or not isinstance(
        expected_scope.get("applicable"), bool
    ):
        raise ValueError("expected_answer_scope must contain applicable and value")
    scope_value = expected_scope.get("value")
    if expected_scope["applicable"]:
        if outcome not in {"sufficient", "partial", "empty"} or not isinstance(scope_value, dict):
            raise ValueError("applicable Story scope requires completed retrieval")
        if scope_value.get("evidence_state") not in EVIDENCE_STATES:
            raise ValueError("unknown Story evidence state")
        if scope_value.get("narrative_coverage") not in NARRATIVE_COVERAGE:
            raise ValueError("unknown Story narrative coverage")
        if scope_value.get("authorization_coverage_scope") not in AUTHORIZATION_COVERAGE:
            raise ValueError("unknown Story authorization coverage")
    elif scope_value is not None:
        raise ValueError("non-applicable Story scope value must be null")

    return StorySegmentEvalCase(
        schema_version=EVAL_CASE_SCHEMA_VERSION,
        query_id=query_id,
        query=query,
        stratum=stratum,
        query_type=str(payload.get("query_type", "")),
        gold_artifact_sha256=artifact_sha,
        request_plan_source_spans=spans,
        expected_authorization_origin=origin,
        expected_story_owner_ids=owner_ids,
        expected_story_owner_order=owner_order,
        forbidden_owner_ids=_as_string_tuple(
            payload.get("forbidden_owner_ids", []), field="forbidden_owner_ids"
        ),
        required_atom_groups=tuple(groups),
        required_topic_page_sources=_as_mapping_tuple(
            payload.get("required_topic_page_sources", []),
            field="required_topic_page_sources",
        ),
        branch_constraints=_as_mapping(
            payload.get("branch_constraints", {}), field="branch_constraints"
        ),
        allow_shortfall=bool(payload.get("allow_shortfall", False)),
        expected_answer_scope=expected_scope,
        source_relevance=_as_mapping(
            payload.get("source_relevance", {}), field="source_relevance"
        ),
        expected_call_counts=expected_call_counts,  # type: ignore[arg-type]
        continuation=_as_mapping(payload.get("continuation", {}), field="continuation"),
        anchor=_as_mapping(payload.get("anchor", {}), field="anchor"),
        expected_retrieval_outcome=outcome,
        review=review,
    )


def load_story_segment_eval(path: Path) -> tuple[StorySegmentEvalCase, ...]:
    cases: list[StorySegmentEvalCase] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            cases.append(_load_eval_case(json.loads(line)))
        except (json.JSONDecodeError, ValueError, TypeError) as exc:
            raise ValueError(f"invalid Story Segment eval row {line_number}: {exc}") from exc
    if len(cases) < 80:
        raise ValueError("Story Segment eval requires at least 80 cases")
    identifiers = [case.query_id for case in cases]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("Story Segment query_id values must be unique")
    queries = [case.query for case in cases]
    if len(queries) != len(set(queries)):
        raise ValueError("Story Segment query values must be unique")
    for stratum, minimum in STRATUM_MINIMUMS.items():
        count = sum(case.stratum == stratum for case in cases)
        if count < minimum:
            raise ValueError(f"Story Segment stratum {stratum} requires at least {minimum} cases")
    return tuple(cases)


def verify_eval_gold_against_atom_artifact(
    cases: Sequence[StorySegmentEvalCase],
    atom_artifact_path: Path,
    *,
    expected_artifact_sha256: str,
) -> int:
    """Verify every frozen gold target against the exact published Atom row."""

    if not _is_sha256(expected_artifact_sha256):
        raise ValueError("expected Story Atom artifact SHA-256 is invalid")
    digest = hashlib.sha256()
    targets = {
        target.atom_id: target
        for case in cases
        for group in case.required_atom_groups
        for target in group.atoms
    }
    found: set[str] = set()
    with atom_artifact_path.open("rb") as handle:
        for raw_line in handle:
            digest.update(raw_line)
            row = json.loads(raw_line)
            atom_id = row.get("child_id")
            target = targets.get(atom_id)
            if target is None:
                continue
            if atom_id in found:
                raise ValueError(f"duplicate Story Atom row for frozen target: {atom_id}")
            refs = row.get("source_refs")
            if not isinstance(refs, list) or len(refs) != 1 or not isinstance(refs[0], dict):
                raise ValueError(f"frozen Story Atom must have one source ref: {atom_id}")
            ref = refs[0]
            observed = (
                ref.get("source_title"),
                ref.get("json_path"),
                ref.get("source_content_sha256"),
                evidence_sha256(str(row.get("content", ""))),
            )
            expected = (
                target.source_title,
                target.source_json_path,
                target.source_content_sha256,
                target.normalized_evidence_sha256,
            )
            if observed != expected:
                raise ValueError(f"frozen Story Atom identity mismatch: {atom_id}")
            found.add(atom_id)
    if digest.hexdigest() != expected_artifact_sha256:
        raise ValueError("Story Atom artifact SHA-256 mismatch")
    missing = sorted(set(targets) - found)
    if missing:
        raise ValueError(f"frozen Story Atom targets are missing: {missing[:3]}")
    return len(found)


def load_story_segment_thresholds(path: Path) -> StorySegmentThresholds:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != THRESHOLDS_SCHEMA_VERSION:
        raise ValueError("unsupported Story Segment thresholds schema")
    denominators = _as_mapping(
        payload.get("denominator_definitions"), field="denominator_definitions"
    )
    if not denominators or not all(
        isinstance(key, str) and isinstance(value, str) and value
        for key, value in denominators.items()
    ):
        raise ValueError("denominator definitions must be non-empty strings")
    gates = _as_mapping(payload.get("hard_gates"), field="hard_gates")
    if not gates:
        raise ValueError("hard_gates must not be empty")
    for name, raw_gate in gates.items():
        if not isinstance(name, str) or not isinstance(raw_gate, dict):
            raise ValueError("hard gate entries must be objects")
        direction = raw_gate.get("direction")
        if direction not in {"minimum", "maximum", "zero", "not_below_baseline", "conditional_delta", "latency_bound"}:
            raise ValueError(f"invalid hard gate direction for {name}")
        denominator = raw_gate.get("denominator")
        if denominator not in denominators:
            raise ValueError(f"unknown denominator for hard gate {name}")
        for field in ("minimum", "maximum", "absolute_limit", "baseline_tolerance", "required_delta"):
            if field in raw_gate:
                value = raw_gate[field]
                if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(float(value)):
                    raise ValueError(f"hard gate {name}.{field} must be finite")
    return StorySegmentThresholds(
        schema_version=THRESHOLDS_SCHEMA_VERSION,
        denominator_definitions=denominators,  # type: ignore[arg-type]
        hard_gates=gates,  # type: ignore[arg-type]
    )


def _result_text(result: Mapping[str, object]) -> str | None:
    for field in ("text", "content"):
        value = result.get(field)
        if isinstance(value, str):
            return canonical_evidence_text(value)
    return None


def _source_refs(result: Mapping[str, object]) -> tuple[Mapping[str, object], ...]:
    raw = result.get("source_refs")
    if not isinstance(raw, (list, tuple)):
        return ()
    return tuple(item for item in raw if isinstance(item, Mapping))


def _same_source_version(ref: Mapping[str, object], gold: AtomEvidenceTarget) -> bool:
    title = ref.get("source_title")
    source_hash = ref.get("source_content_sha256")
    return (
        isinstance(title, str)
        and title == gold.source_title
        and isinstance(source_hash, str)
        and bool(source_hash)
        and source_hash == gold.source_content_sha256
    )


def _unmatched(
    gold: AtomEvidenceTarget,
    stage: Literal["retrieval_at_k", "final_context"],
    reason: str,
    *,
    rank: int = 0,
    ambiguous: bool = False,
) -> AtomEquivalenceMatch:
    return AtomEquivalenceMatch(
        query_id=gold.query_id,
        stage=stage,
        result_rank=rank,
        atom_id=gold.atom_id,
        match_rule="ambiguous" if ambiguous else "unmatched",
        matched_span=None,
        matched=False,
        reason_code=reason,
    )


def match_active_evidence_to_atoms(
    active_results: Sequence[Mapping[str, object]],
    gold_atoms: Sequence[AtomEvidenceTarget],
    *,
    stage: Literal["retrieval_at_k", "final_context"],
) -> tuple[AtomEquivalenceMatch, ...]:
    """Match active evidence to frozen Atoms in the only permitted order."""

    if stage not in STAGES:
        raise ValueError(f"unsupported stage: {stage!r}")
    results = tuple(active_results)
    gold = tuple(gold_atoms)
    used_spans: set[tuple[int, int, int]] = set()
    matches: list[AtomEquivalenceMatch | None] = [None] * len(gold)

    # Rule 1: exact Atom identity plus canonical evidence hash.
    for gold_index, target in enumerate(gold):
        for rank, result in enumerate(results, 1):
            if result.get("atom_id") != target.atom_id:
                continue
            supplied_hash = result.get("normalized_evidence_sha256")
            if supplied_hash != target.normalized_evidence_sha256:
                matches[gold_index] = _unmatched(
                    target,
                    stage,
                    "atom_identity_content_hash_mismatch",
                    rank=rank,
                )
            else:
                matches[gold_index] = AtomEquivalenceMatch(
                    query_id=target.query_id,
                    stage=stage,
                    result_rank=rank,
                    atom_id=target.atom_id,
                    match_rule="exact_atom_id",
                    matched_span=None,
                    matched=True,
                    reason_code="exact_atom_identity",
                )
            break

    # Rule 2: exact source path, source version and canonical evidence hash.
    for gold_index, target in enumerate(gold):
        if matches[gold_index] is not None:
            continue
        for rank, result in enumerate(results, 1):
            text = _result_text(result)
            if text is None or evidence_sha256(text) != target.normalized_evidence_sha256:
                continue
            if any(
                _same_source_version(ref, target)
                and ref.get("json_path") == target.source_json_path
                for ref in _source_refs(result)
            ):
                matches[gold_index] = AtomEquivalenceMatch(
                    query_id=target.query_id,
                    stage=stage,
                    result_rank=rank,
                    atom_id=target.atom_id,
                    match_rule="exact_source_path_revision_hash",
                    matched_span=(0, len(text)),
                    matched=True,
                    reason_code="exact_source_path_and_version",
                )
                used_spans.add((rank, 0, len(text)))
                break

    # Rule 3: unique exact text span in the same exact source version. Equal
    # gold evidence texts without an exact path are intentionally ambiguous.
    unresolved_by_identity: dict[tuple[str, str, str], list[int]] = {}
    for index, target in enumerate(gold):
        if matches[index] is None:
            key = (
                target.source_title,
                target.source_content_sha256,
                target.normalized_evidence_sha256,
            )
            unresolved_by_identity.setdefault(key, []).append(index)

    for indexes in unresolved_by_identity.values():
        if len(indexes) > 1:
            for index in indexes:
                matches[index] = _unmatched(
                    gold[index], stage, "shared_evidence_text_ambiguous", ambiguous=True
                )
            continue
        gold_index = indexes[0]
        target = gold[gold_index]
        candidates: list[tuple[int, int, int]] = []
        saw_source_ref = False
        saw_matching_version = False
        saw_multiple = False
        for rank, result in enumerate(results, 1):
            refs = _source_refs(result)
            saw_source_ref = saw_source_ref or bool(refs)
            if not any(_same_source_version(ref, target) for ref in refs):
                continue
            saw_matching_version = True
            text = _result_text(result)
            if text is None:
                continue
            # The frozen target intentionally stores only the evidence hash.
            # The D-owned capture process supplies a hash-keyed lookup loaded
            # from the same immutable Atom artifact; this is a search needle,
            # never active or generated evidence.
            target_texts = result.get("gold_evidence_text_by_sha256")
            target_text = (
                target_texts.get(target.normalized_evidence_sha256)
                if isinstance(target_texts, Mapping)
                else None
            )
            if not isinstance(target_text, str):
                continue
            target_text = canonical_evidence_text(target_text)
            if evidence_sha256(target_text) != target.normalized_evidence_sha256:
                continue
            offsets: list[int] = []
            start = text.find(target_text)
            while start >= 0:
                offsets.append(start)
                start = text.find(target_text, start + 1)
            if len(offsets) > 1:
                saw_multiple = True
            elif len(offsets) == 1:
                candidates.append((rank, offsets[0], offsets[0] + len(target_text)))
        available = [item for item in candidates if item not in used_spans]
        if len(available) == 1 and not saw_multiple:
            rank, start, end = available[0]
            used_spans.add(available[0])
            matches[gold_index] = AtomEquivalenceMatch(
                query_id=target.query_id,
                stage=stage,
                result_rank=rank,
                atom_id=target.atom_id,
                match_rule="unique_exact_text_span",
                matched_span=(start, end),
                matched=True,
                reason_code="unique_exact_text_span",
            )
        elif saw_multiple or len(available) > 1:
            matches[gold_index] = _unmatched(
                target,
                stage,
                "evidence_text_occurs_multiple_times",
                rank=available[0][0] if available else 0,
                ambiguous=True,
            )
        elif not saw_source_ref:
            matches[gold_index] = _unmatched(target, stage, "missing_source_ref")
        elif not saw_matching_version:
            matches[gold_index] = _unmatched(target, stage, "source_version_mismatch")
        else:
            matches[gold_index] = _unmatched(target, stage, "evidence_text_not_found")

    return tuple(
        match if match is not None else _unmatched(gold[index], stage, "no_active_results")
        for index, match in enumerate(matches)
    )
