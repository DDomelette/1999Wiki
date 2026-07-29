"""Immutable contracts shared by the trustworthy RAG execution pipeline."""
from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass, replace
from types import MappingProxyType
from typing import Literal, Mapping, Sequence, TypeAlias, cast


RetrievalOutcome: TypeAlias = Literal[
    "sufficient",
    "partial",
    "empty",
    "failed",
    "not_applicable",
]
ExecutionRoute: TypeAlias = Literal[
    "rag_grounded",
    "expanded_rag",
    "llm_general",
    "local_response",
    "composite",
]
GroundingMode: TypeAlias = Literal["grounded", "ungrounded", "none", "mixed"]
TurnOutcome: TypeAlias = Literal[
    "grounded",
    "ungrounded",
    "mixed",
    "local",
    "not_committable",
]
BranchStatus: TypeAlias = Literal["succeeded", "empty", "denied", "failed"]

_RETRIEVAL_OUTCOMES = frozenset({
    "sufficient",
    "partial",
    "empty",
    "failed",
    "not_applicable",
})
_EXECUTION_ROUTES = frozenset({
    "rag_grounded",
    "expanded_rag",
    "llm_general",
    "local_response",
    "composite",
})
_GROUNDING_MODES = frozenset({"grounded", "ungrounded", "none", "mixed"})
_TURN_OUTCOMES = frozenset({
    "grounded",
    "ungrounded",
    "mixed",
    "local",
    "not_committable",
})
_BRANCH_STATUSES = frozenset({"succeeded", "empty", "denied", "failed"})


def aggregate_grounding_mode(
    branch_modes: Sequence[GroundingMode],
) -> GroundingMode:
    modes = frozenset(branch_modes)
    if not modes:
        return "none"
    if not modes <= _GROUNDING_MODES - {"mixed"}:
        raise ValueError("branch grounding mode is outside the public contract")
    if len(modes) == 1:
        return cast(GroundingMode, next(iter(modes)))
    return "mixed"


def aggregate_retrieval_outcome(
    kb_outcomes: Sequence[RetrievalOutcome],
) -> RetrievalOutcome:
    outcomes = tuple(kb_outcomes)
    if not outcomes:
        return "not_applicable"
    if any(outcome not in _RETRIEVAL_OUTCOMES - {"not_applicable"} for outcome in outcomes):
        raise ValueError("KB retrieval outcome is outside the public contract")
    unique = frozenset(outcomes)
    if unique == {"sufficient"}:
        return "sufficient"
    if unique == {"empty"}:
        return "empty"
    if unique == {"failed"}:
        return "failed"
    return "partial"


def _stable_sort_key(value: object) -> tuple[str, str]:
    return type(value).__qualname__, repr(value)


def freeze_value(value: object) -> object:
    """Recursively freeze public packet values without serializing them."""
    if isinstance(value, Mapping):
        return MappingProxyType({key: freeze_value(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(freeze_value(item) for item in value)
    if isinstance(value, (set, frozenset)):
        frozen = (freeze_value(item) for item in value)
        return tuple(sorted(frozen, key=_stable_sort_key))
    if is_dataclass(value) and not isinstance(value, type):
        replacements = {
            field.name: freeze_value(getattr(value, field.name)) for field in fields(value)
        }
        try:
            return replace(value, **replacements)
        except (TypeError, ValueError):
            return MappingProxyType(replacements)
    return value


def _freeze_tuple(values: object) -> tuple[object, ...]:
    frozen = freeze_value(values)
    if not isinstance(frozen, tuple):
        raise TypeError("expected a tuple-compatible value")
    return frozen


def _freeze_mapping(values: object) -> Mapping[str, object]:
    frozen = freeze_value(values)
    if not isinstance(frozen, Mapping):
        raise TypeError("expected a mapping value")
    return cast(Mapping[str, object], frozen)


@dataclass(frozen=True)
class EntityRef:
    entity_type: str
    entity_id: str
    entity_name: str
    aliases: tuple[str, ...] = ()
    resolution_mode: str = "unresolved"

    def __post_init__(self) -> None:
        for name in ("entity_type", "entity_id", "entity_name"):
            if not str(getattr(self, name)).strip():
                raise ValueError(f"{name} must not be empty")
        object.__setattr__(self, "aliases", tuple(str(alias) for alias in self.aliases))

    @property
    def ownership_key(self) -> tuple[str, str]:
        return self.entity_type, self.entity_id


@dataclass(frozen=True)
class RouteAuthorization:
    semantic_intents: tuple[str, ...]
    proposed_route: str
    allow_free_supplement_after_empty: bool
    force_free_supplement: bool
    authorization_reason: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "semantic_intents",
            tuple(str(intent) for intent in self.semantic_intents),
        )


@dataclass(frozen=True)
class RouteDecision:
    authorization: RouteAuthorization
    retrieval_outcome: RetrievalOutcome
    effective_route: ExecutionRoute
    route_reason: str

    def __post_init__(self) -> None:
        if self.retrieval_outcome not in _RETRIEVAL_OUTCOMES:
            raise ValueError("retrieval_outcome is outside the public contract")
        if self.effective_route not in _EXECUTION_ROUTES:
            raise ValueError("effective_route is outside the public contract")


@dataclass(frozen=True)
class SourceRef:
    citation_id: str
    entity_type: str
    entity_id: str
    child_id: str
    parent_id: str
    display_name: str
    heading_path: str


@dataclass(frozen=True)
class CitationValidation:
    valid: bool
    used_ids: tuple[str, ...] = ()
    invalid_ids: tuple[str, ...] = ()
    duplicate_ids: tuple[str, ...] = ()
    missing_required: bool = False
    normalized: bool = False
    repair_attempts: int = 0
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ("used_ids", "invalid_ids", "duplicate_ids", "warnings"):
            object.__setattr__(self, name, tuple(str(item) for item in getattr(self, name)))
        if self.repair_attempts < 0:
            raise ValueError("repair_attempts must not be negative")


@dataclass(frozen=True)
class BranchResult:
    subtask_id: str
    order: int
    task_type: str
    query: str
    effective_route: ExecutionRoute
    retrieval_outcome: RetrievalOutcome
    grounding_mode: GroundingMode
    status: BranchStatus
    answer: str
    source_ids: tuple[str, ...]
    entity_ref: EntityRef | None
    citation_validation: CitationValidation
    public_error: str = ""

    def __post_init__(self) -> None:
        if not self.subtask_id or self.order < 1:
            raise ValueError("branch identity is invalid")
        if self.effective_route not in _EXECUTION_ROUTES:
            raise ValueError("branch route is outside the public contract")
        if self.retrieval_outcome not in _RETRIEVAL_OUTCOMES:
            raise ValueError("branch retrieval outcome is outside the public contract")
        if self.grounding_mode not in _GROUNDING_MODES - {"mixed"}:
            raise ValueError("branch grounding mode is outside the public contract")
        if self.status not in _BRANCH_STATUSES:
            raise ValueError("branch status is outside the public contract")
        object.__setattr__(self, "source_ids", tuple(str(item) for item in self.source_ids))


@dataclass(frozen=True)
class SubtaskInfo:
    subtask_id: str
    order: int
    task_type: str
    query: str
    effective_route: ExecutionRoute
    retrieval_outcome: RetrievalOutcome
    grounding_mode: GroundingMode
    status: BranchStatus
    citation_ids: tuple[str, ...]

    @classmethod
    def from_branch(cls, branch: BranchResult) -> "SubtaskInfo":
        return cls(
            subtask_id=branch.subtask_id,
            order=branch.order,
            task_type=branch.task_type,
            query=branch.query,
            effective_route=branch.effective_route,
            retrieval_outcome=branch.retrieval_outcome,
            grounding_mode=branch.grounding_mode,
            status=branch.status,
            citation_ids=branch.source_ids,
        )

    def __post_init__(self) -> None:
        if not self.subtask_id or self.order < 1:
            raise ValueError("subtask identity is invalid")
        if self.effective_route not in _EXECUTION_ROUTES:
            raise ValueError("subtask route is outside the public contract")
        if self.retrieval_outcome not in _RETRIEVAL_OUTCOMES:
            raise ValueError("subtask retrieval outcome is outside the public contract")
        if self.grounding_mode not in _GROUNDING_MODES - {"mixed"}:
            raise ValueError("subtask grounding mode is outside the public contract")
        if self.status not in _BRANCH_STATUSES:
            raise ValueError("subtask status is outside the public contract")
        object.__setattr__(
            self,
            "citation_ids",
            tuple(str(item) for item in self.citation_ids),
        )


@dataclass(frozen=True)
class GlobalSourceAllocation:
    sources: tuple[Mapping[str, object], ...]
    source_map: tuple[SourceRef, ...]
    branch_source_ids: Mapping[str, tuple[str, ...]]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "sources",
            cast(tuple[Mapping[str, object], ...], _freeze_tuple(self.sources)),
        )
        object.__setattr__(self, "source_map", tuple(self.source_map))
        frozen_ids = {
            str(key): tuple(str(item) for item in value)
            for key, value in self.branch_source_ids.items()
        }
        object.__setattr__(self, "branch_source_ids", MappingProxyType(frozen_ids))


@dataclass(frozen=True)
class FrozenRetrievalPacket:
    plan: object
    entity_ref: EntityRef | None
    route_decision: RouteDecision
    requested_intents: tuple[str, ...]
    sources: tuple[Mapping[str, object], ...]
    source_map: tuple[SourceRef, ...]
    media: tuple[Mapping[str, object], ...]
    media_panels: tuple[Mapping[str, object], ...]
    context: str
    diagnostics: Mapping[str, object]
    omitted_actions: tuple[Mapping[str, object], ...]
    failure_actions: tuple[Mapping[str, object], ...]
    planning_status: str
    planning_warning: str
    planning_error: str
    assets: tuple[Mapping[str, object], ...] = ()
    schema_version: str = "rag.retrieval_packet/v3"

    def __post_init__(self) -> None:
        object.__setattr__(self, "plan", freeze_value(self.plan))
        object.__setattr__(self, "requested_intents", tuple(self.requested_intents))
        object.__setattr__(self, "sources", cast(tuple[Mapping[str, object], ...], _freeze_tuple(self.sources)))
        object.__setattr__(self, "source_map", tuple(self.source_map))
        object.__setattr__(self, "media", cast(tuple[Mapping[str, object], ...], _freeze_tuple(self.media)))
        object.__setattr__(self, "media_panels", cast(tuple[Mapping[str, object], ...], _freeze_tuple(self.media_panels)))
        object.__setattr__(self, "diagnostics", _freeze_mapping(self.diagnostics))
        object.__setattr__(self, "omitted_actions", cast(tuple[Mapping[str, object], ...], _freeze_tuple(self.omitted_actions)))
        object.__setattr__(self, "failure_actions", cast(tuple[Mapping[str, object], ...], _freeze_tuple(self.failure_actions)))
        object.__setattr__(self, "assets", cast(tuple[Mapping[str, object], ...], _freeze_tuple(self.assets)))


@dataclass(frozen=True)
class ResponsePacket:
    retrieval_packet: FrozenRetrievalPacket
    answer: str
    grounding_mode: GroundingMode
    citation_validation: CitationValidation
    memory_info: Mapping[str, object]
    turn_outcome: TurnOutcome
    branch_results: tuple[BranchResult, ...] = ()
    schema_version: str = "rag.response_packet/v3"

    def __post_init__(self) -> None:
        if self.grounding_mode not in _GROUNDING_MODES:
            raise ValueError("grounding_mode is outside the public contract")
        if self.turn_outcome not in _TURN_OUTCOMES:
            raise ValueError("turn_outcome is outside the public contract")
        object.__setattr__(self, "memory_info", _freeze_mapping(self.memory_info))
        object.__setattr__(self, "branch_results", tuple(self.branch_results))


__all__ = [
    "CitationValidation",
    "BranchResult",
    "BranchStatus",
    "EntityRef",
    "ExecutionRoute",
    "FrozenRetrievalPacket",
    "GroundingMode",
    "GlobalSourceAllocation",
    "ResponsePacket",
    "RetrievalOutcome",
    "RouteAuthorization",
    "RouteDecision",
    "SourceRef",
    "SubtaskInfo",
    "TurnOutcome",
    "aggregate_grounding_mode",
    "aggregate_retrieval_outcome",
    "freeze_value",
]
