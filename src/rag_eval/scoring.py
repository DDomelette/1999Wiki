"""Scenario scoring and hierarchical severity aggregation."""
from __future__ import annotations

from dataclasses import dataclass
from statistics import fmean
from typing import Iterable, Mapping, Sequence

from .contracts import (
    CaseResult,
    Difficulty,
    EvaluationEvent,
    ModuleResult,
    Severity,
    Thresholds,
    worst_severity,
)


MODULES = ("M1", "M2", "M3", "M4", "M5")
P0_SPEC_IDS: Mapping[str, tuple[str, ...]] = {
    "M1": tuple(f"READY-P0-{index:02d}" for index in range(1, 5)),
    "M2": tuple(f"RETR-P0-{index:02d}" for index in range(1, 6)),
    "M3": tuple(f"ANSWER-P0-{index:02d}" for index in range(1, 7)),
    "M4": tuple(f"MEDIA-P0-{index:02d}" for index in range(1, 6)),
    "M5": tuple(f"RELY-P0-{index:02d}" for index in range(1, 5)),
}


@dataclass(frozen=True)
class ScoredCase:
    case_id: str
    difficulty: Difficulty
    scenario: str
    components: Mapping[str, float]
    score: float
    events: tuple[EvaluationEvent, ...]


@dataclass(frozen=True)
class DifficultyResult:
    difficulty: Difficulty
    count: int
    mean_score: float | None
    floor_pass_rate: float | None
    target: float
    floor: float
    required_floor_pass_rate: float
    severity: Severity


@dataclass(frozen=True)
class RunWarning:
    code: str
    message: str
    recommended_action: str


@dataclass(frozen=True)
class RunSummary:
    global_severity: Severity
    accepted: bool
    accepted_with_warnings: bool
    modules: Mapping[str, ModuleResult]
    difficulties: Mapping[Difficulty, DifficultyResult]
    events: tuple[EvaluationEvent, ...]
    warnings: tuple[RunWarning, ...]
    case_count: int
    quality_case_count: int
    coverage: Mapping[str, Mapping[str, object]]


def score_case(case: CaseResult, thresholds: Thresholds) -> ScoredCase:
    weights = thresholds.weights.get(case.scenario)
    if weights is None:
        raise ValueError(f"unknown scenario: {case.scenario}")
    missing = sorted(set(weights) - set(case.module_scores))
    if missing:
        raise ValueError(f"missing module scores for {case.case_id}: {', '.join(missing)}")

    components: dict[str, float] = {}
    for module in weights:
        value = float(case.module_scores[module])
        if not 0.0 <= value <= 100.0:
            raise ValueError(f"module score {module} must be in 0..100")
        components[module] = value
    total = sum(components[module] * weight for module, weight in weights.items())
    return ScoredCase(
        case_id=case.case_id,
        difficulty=case.difficulty,
        scenario=case.scenario,
        components=components,
        score=round(total, 6),
        events=case.events,
    )


def classify_difficulty(
    difficulty: Difficulty,
    scores: Sequence[float],
    thresholds: Thresholds,
) -> DifficultyResult:
    threshold = thresholds.difficulty[difficulty]
    normalized = [float(score) for score in scores]
    if any(not 0.0 <= score <= 100.0 for score in normalized):
        raise ValueError("difficulty scores must be in 0..100")
    if not normalized:
        return DifficultyResult(
            difficulty=difficulty,
            count=0,
            mean_score=None,
            floor_pass_rate=None,
            target=threshold.target,
            floor=threshold.floor,
            required_floor_pass_rate=threshold.floor_pass_rate,
            severity=Severity.PASS,
        )

    mean_score = fmean(normalized)
    floor_pass_rate = sum(score >= threshold.floor for score in normalized) / len(normalized)
    if floor_pass_rate < threshold.floor_pass_rate or mean_score < threshold.floor:
        severity = Severity.SEV2
    elif mean_score < threshold.target:
        severity = Severity.SEV3
    else:
        severity = Severity.PASS
    return DifficultyResult(
        difficulty=difficulty,
        count=len(normalized),
        mean_score=round(mean_score, 6),
        floor_pass_rate=round(floor_pass_rate, 6),
        target=threshold.target,
        floor=threshold.floor,
        required_floor_pass_rate=threshold.floor_pass_rate,
        severity=severity,
    )


def summarize_modules(
    cases: Sequence[CaseResult],
    thresholds: Thresholds | None = None,
    *,
    extra_events: Sequence[EvaluationEvent] = (),
) -> dict[str, ModuleResult]:
    results: dict[str, ModuleResult] = {}
    for module in MODULES:
        module_events = tuple(
            [event for case in cases for event in case.events if event.module == module]
            + [event for event in extra_events if event.module == module]
        )
        values = [float(case.module_scores[module]) for case in cases if module in case.module_scores]
        for value in values:
            if not 0.0 <= value <= 100.0:
                raise ValueError(f"module score {module} must be in 0..100")

        severities = [event.severity for event in module_events]
        if thresholds is not None:
            for difficulty in Difficulty:
                group = [
                    float(case.module_scores[module])
                    for case in cases
                    if case.difficulty is difficulty and module in case.module_scores
                ]
                if group:
                    severities.append(classify_difficulty(difficulty, group, thresholds).severity)
        results[module] = ModuleResult(
            module=module,
            severity=worst_severity(severities),
            score=round(fmean(values), 6) if values else None,
            events=module_events,
        )
    return results


def classify_run(
    cases: Sequence[CaseResult],
    thresholds: Thresholds,
    *,
    extra_events: Sequence[EvaluationEvent] = (),
    excluded_case_ids: set[str] | frozenset[str] = frozenset(),
) -> RunSummary:
    quality_cases = [case for case in cases if case.case_id not in excluded_case_ids]
    scored = [score_case(case, thresholds) for case in quality_cases]
    difficulties = {
        difficulty: classify_difficulty(
            difficulty,
            [item.score for item in scored if item.difficulty is difficulty],
            thresholds,
        )
        for difficulty in Difficulty
    }
    excluded_events = [
        event
        for case in cases
        if case.case_id in excluded_case_ids
        for event in case.events
    ]
    modules = summarize_modules(
        quality_cases,
        thresholds,
        extra_events=tuple((*excluded_events, *extra_events)),
    )
    events = tuple([event for case in cases for event in case.events] + list(extra_events))
    severities = [item.severity for item in difficulties.values() if item.count]
    severities.extend(item.severity for item in modules.values())
    severities.extend(event.severity for event in events)
    global_severity = worst_severity(severities)

    warnings = tuple(
        RunWarning(
            code=f"SCORE.{difficulty.value}_BELOW_TARGET",
            message=(
                f"{difficulty.value} mean {item.mean_score:.2f} is below target "
                f"{item.target:.2f}"
            ),
            recommended_action=(
                f"Inspect failed {difficulty.value} cases by module, rerun the focused set, "
                "then repeat the full acceptance sample."
            ),
        )
        for difficulty, item in difficulties.items()
        if item.count and item.severity is Severity.SEV3
    )
    accepted = global_severity in {Severity.PASS, Severity.SEV4}
    coverage = {
        spec_id: {
            "module": module,
            "severity": modules[module].severity.value,
            "covered": True,
        }
        for module, spec_ids in P0_SPEC_IDS.items()
        for spec_id in spec_ids
    }
    return RunSummary(
        global_severity=global_severity,
        accepted=accepted,
        accepted_with_warnings=global_severity is Severity.SEV3,
        modules=modules,
        difficulties=difficulties,
        events=events,
        warnings=warnings,
        case_count=len(cases),
        quality_case_count=len(quality_cases),
        coverage=coverage,
    )
