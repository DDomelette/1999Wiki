"""Versioned contracts shared by the full-chain RAG evaluator."""
from __future__ import annotations

import json
import math
import re
from dataclasses import asdict, dataclass, field, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Mapping


CONTRACT_SCHEMA_VERSION = "rag_eval.contracts/v2"
REVIEWED_P0_INTENTS = (
    "intro",
    "profile_fact",
    "skill",
    "item",
    "culture",
    "voice",
    "media",
    "video",
    "psychube",
    "story",
    "general_game",
    "meta_question",
)
REVIEWED_SAMPLE_MINIMUMS: Mapping[str, float] = {
    "unique": 48,
    "D1": 16,
    "D2": 12,
    "D3": 12,
    "D4": 8,
    "entities": 8,
    "repeat_rate": 0.1,
}
_EVENT_CODE_RE = re.compile(r"[A-Z][A-Z0-9_]*\.[A-Z][A-Z0-9_]*\Z")
_MODULES = frozenset({"M1", "M2", "M3", "M4", "M5"})


class Severity(str, Enum):
    PASS = "PASS"
    SEV4 = "SEV-4"
    SEV3 = "SEV-3"
    SEV2 = "SEV-2"
    SEV1 = "SEV-1"
    SEV0 = "SEV-0"

    @property
    def rank(self) -> int:
        return {
            "SEV-0": 0,
            "SEV-1": 1,
            "SEV-2": 2,
            "SEV-3": 3,
            "SEV-4": 4,
            "PASS": 5,
        }[self.value]

    @property
    def otel_number(self) -> int | None:
        return {
            "SEV-0": 21,
            "SEV-1": 20,
            "SEV-2": 17,
            "SEV-3": 13,
            "SEV-4": 9,
            "PASS": None,
        }[self.value]

    @property
    def otel_text(self) -> str:
        return {
            "SEV-0": "FATAL",
            "SEV-1": "ERROR4",
            "SEV-2": "ERROR",
            "SEV-3": "WARN",
            "SEV-4": "INFO",
            "PASS": "PASS",
        }[self.value]


class Difficulty(str, Enum):
    D1 = "D1"
    D2 = "D2"
    D3 = "D3"
    D4 = "D4"


def worst_severity(values: list[Severity] | tuple[Severity, ...]) -> Severity:
    return min(values, key=lambda item: item.rank, default=Severity.PASS)


@dataclass(frozen=True)
class EvaluationEvent:
    event_code: str
    module: str
    severity: Severity
    severity_number: int | None
    case_ids: tuple[str, ...] = ()
    observed: Mapping[str, object] = field(default_factory=dict)
    expected: Mapping[str, object] = field(default_factory=dict)
    recommended_action: str = ""

    def __post_init__(self) -> None:
        if self.module not in _MODULES:
            raise ValueError(f"unknown evaluation module: {self.module}")
        if not _EVENT_CODE_RE.fullmatch(self.event_code):
            raise ValueError(f"invalid event_code: {self.event_code}")
        if self.severity_number != self.severity.otel_number:
            raise ValueError(
                "severity_number does not match severity: "
                f"{self.severity_number!r} != {self.severity.otel_number!r}"
            )

    @classmethod
    def create(
        cls,
        event_code: str,
        module: str,
        severity: Severity,
        *,
        case_ids: tuple[str, ...] = (),
        observed: Mapping[str, object] | None = None,
        expected: Mapping[str, object] | None = None,
        recommended_action: str = "",
    ) -> "EvaluationEvent":
        return cls(
            event_code=event_code,
            module=module,
            severity=severity,
            severity_number=severity.otel_number,
            case_ids=case_ids,
            observed=observed or {},
            expected=expected or {},
            recommended_action=recommended_action,
        )

    def to_json(self) -> dict[str, object]:
        payload = to_jsonable(self)
        assert isinstance(payload, dict)
        payload["severity_text"] = self.severity.otel_text
        return payload


@dataclass(frozen=True)
class JudgeIdentity:
    base_url: str
    model: str
    prompt_version: str

    def to_json(self) -> dict[str, str]:
        return {
            "base_url": self.base_url,
            "model": self.model,
            "prompt_version": self.prompt_version,
        }


@dataclass(frozen=True)
class DifficultyThreshold:
    target: float
    floor: float
    floor_pass_rate: float


@dataclass(frozen=True)
class Thresholds:
    schema_version: str
    p0_intents: tuple[str, ...]
    sample_minimums: Mapping[str, float]
    difficulty: Mapping[Difficulty, DifficultyThreshold]
    weights: Mapping[str, Mapping[str, float]]
    reliability: Mapping[str, float]
    judge: Mapping[str, float]
    sync_stream_parity_minimum: int


@dataclass(frozen=True)
class EvalCase:
    case_id: str
    query: str
    difficulty: Difficulty
    scenario: str
    expected_entity_id: str = ""
    expected_entity_ids: tuple[str, ...] = ()
    expected_entity_name: str = ""
    expected_ownership_key: tuple[str, str] | None = None
    expected_intents: tuple[str, ...] = ()
    expected_source_ids: tuple[str, ...] = ()
    source_relevance: Mapping[str, float] = field(default_factory=dict)
    expected_media_ids: tuple[str, ...] = ()
    forbidden_media_types: tuple[str, ...] = ()
    allow_no_sources: bool = False
    expected_behavior: str = "grounded_answer"
    route_options: Mapping[str, object] = field(default_factory=dict)
    action_payload: Mapping[str, object] = field(default_factory=dict)
    expected_retrieval_outcome: str = ""
    expected_effective_route: str = ""
    conversation_mode: str = "standalone"
    repeat_of: str | None = None
    derivation: Mapping[str, object] = field(default_factory=dict)

    def to_json(self) -> dict[str, object]:
        payload = to_jsonable(self)
        assert isinstance(payload, dict)
        return payload


@dataclass(frozen=True)
class CaseResult:
    case_id: str
    difficulty: Difficulty
    scenario: str
    module_scores: Mapping[str, float]
    events: tuple[EvaluationEvent, ...] = ()
    observed: Mapping[str, object] = field(default_factory=dict)
    judge: Mapping[str, object] = field(default_factory=dict)
    score: float | None = None


@dataclass(frozen=True)
class ModuleResult:
    module: str
    severity: Severity
    score: float | None
    events: tuple[EvaluationEvent, ...] = ()


@dataclass(frozen=True)
class RunManifest:
    run_id: str
    started_at_utc: str
    seed: int
    build_version: str
    collection_name: str
    production_model: str
    judge_identity: JudgeIdentity
    thresholds_sha256: str
    schema_version: str = "rag_eval.run_manifest/v2"


def to_jsonable(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {key: to_jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, Mapping):
        return {
            (key.value if isinstance(key, Enum) else str(key)): to_jsonable(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [to_jsonable(item) for item in value]
    return value


def load_thresholds(path: Path) -> Thresholds:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("thresholds must contain a JSON object")
    schema_version = str(payload.get("schema_version") or "")
    if schema_version != "rag_eval.thresholds/v1":
        raise ValueError(f"unsupported thresholds schema_version: {schema_version}")
    p0_intents = tuple(str(item) for item in payload.get("p0_intents") or ())
    if p0_intents != REVIEWED_P0_INTENTS:
        raise ValueError("p0_intents differs from the reviewed P0 intent list")

    sample_minimums = payload.get("sample_minimums")
    if not isinstance(sample_minimums, dict):
        raise ValueError("sample_minimums must be an object")
    normalized_minimums = {str(key): float(value) for key, value in sample_minimums.items()}
    for key, minimum in REVIEWED_SAMPLE_MINIMUMS.items():
        actual = normalized_minimums.get(key)
        if actual is None or actual < float(minimum):
            raise ValueError(f"sample minimum {key} must be at least {minimum}")

    difficulty_payload = payload.get("difficulty")
    if not isinstance(difficulty_payload, dict):
        raise ValueError("difficulty must be an object")
    difficulty: dict[Difficulty, DifficultyThreshold] = {}
    for level in Difficulty:
        raw = difficulty_payload.get(level.value)
        if not isinstance(raw, dict):
            raise ValueError(f"difficulty {level.value} is required")
        threshold = DifficultyThreshold(
            target=float(raw.get("target")),
            floor=float(raw.get("floor")),
            floor_pass_rate=float(raw.get("floor_pass_rate")),
        )
        if threshold.target < threshold.floor:
            raise ValueError(f"difficulty {level.value} target must be >= floor")
        if not 0.0 <= threshold.floor_pass_rate <= 1.0:
            raise ValueError(f"difficulty {level.value} floor_pass_rate is invalid")
        difficulty[level] = threshold

    weights_payload = payload.get("weights")
    if not isinstance(weights_payload, dict):
        raise ValueError("weights must be an object")
    weights: dict[str, dict[str, float]] = {}
    for scenario in ("text", "media", "hybrid", "boundary"):
        raw = weights_payload.get(scenario)
        if not isinstance(raw, dict):
            raise ValueError(f"weights {scenario} is required")
        normalized = {str(key): float(value) for key, value in raw.items()}
        if not math.isclose(sum(normalized.values()), 1.0, abs_tol=1e-9):
            raise ValueError(f"weights {scenario} must sum to 1.0")
        weights[scenario] = normalized

    reliability = _number_mapping(payload.get("reliability"), "reliability")
    judge = _number_mapping(payload.get("judge"), "judge")
    parity_minimum = int(payload.get("sync_stream_parity_minimum", 0))
    if parity_minimum < 8:
        raise ValueError("sync_stream_parity_minimum must be at least 8")
    return Thresholds(
        schema_version=schema_version,
        p0_intents=p0_intents,
        sample_minimums=normalized_minimums,
        difficulty=difficulty,
        weights=weights,
        reliability=reliability,
        judge=judge,
        sync_stream_parity_minimum=parity_minimum,
    )


def _number_mapping(value: object, label: str) -> dict[str, float]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return {str(key): float(item) for key, item in value.items()}
