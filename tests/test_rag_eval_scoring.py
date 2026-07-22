from __future__ import annotations

from pathlib import Path

import pytest

from src.rag_eval.contracts import (
    CaseResult,
    Difficulty,
    EvaluationEvent,
    Severity,
    load_thresholds,
)
from src.rag_eval.scoring import (
    P0_SPEC_IDS,
    classify_difficulty,
    classify_run,
    score_case,
    summarize_modules,
)


THRESHOLDS = load_thresholds(Path("eval/rag_full_chain_thresholds.v1.json"))


def _event(
    severity: Severity,
    *,
    module: str = "M2",
    code: str = "RETR.CROSS_ENTITY_SOURCE",
) -> EvaluationEvent:
    return EvaluationEvent.create(
        event_code=code,
        module=module,
        severity=severity,
        case_ids=("case-1",),
        recommended_action="inspect the failing module",
    )


def _case(
    *,
    case_id: str = "case-1",
    difficulty: Difficulty = Difficulty.D1,
    scenario: str = "text",
    scores: dict[str, float] | None = None,
    events: tuple[EvaluationEvent, ...] = (),
) -> CaseResult:
    return CaseResult(
        case_id=case_id,
        difficulty=difficulty,
        scenario=scenario,
        module_scores=scores or {"M2": 100, "M3": 100, "M5": 100},
        events=events,
    )


@pytest.mark.parametrize(
    ("scenario", "scores", "expected"),
    [
        ("text", {"M2": 80, "M3": 60, "M5": 100}, 72),
        ("media", {"M2": 80, "M4": 90, "M5": 100}, 88),
        ("hybrid", {"M2": 80, "M3": 70, "M4": 90, "M5": 100}, 82),
        ("boundary", {"M2": 80, "M3": 90, "M5": 100}, 88),
    ],
)
def test_score_case_uses_reviewed_scenario_weights(scenario, scores, expected):
    scored = score_case(_case(scenario=scenario, scores=scores), THRESHOLDS)
    assert scored.score == pytest.approx(expected)
    assert scored.components == scores


def test_score_case_rejects_missing_applicable_module():
    with pytest.raises(ValueError, match="missing module scores.*M3"):
        score_case(_case(scores={"M2": 100, "M5": 100}), THRESHOLDS)


def test_score_case_rejects_unknown_scenario_and_out_of_range_component():
    with pytest.raises(ValueError, match="unknown scenario"):
        score_case(_case(scenario="other"), THRESHOLDS)
    with pytest.raises(ValueError, match="0..100"):
        score_case(_case(scores={"M2": 101, "M3": 100, "M5": 100}), THRESHOLDS)


def test_difficulty_classification_has_pass_warning_and_failure_bands():
    passed = classify_difficulty(Difficulty.D3, [80] * 12, THRESHOLDS)
    warning = classify_difficulty(Difficulty.D3, [72] * 12, THRESHOLDS)
    failed = classify_difficulty(Difficulty.D3, [69] * 12, THRESHOLDS)
    assert passed.severity is Severity.PASS
    assert warning.severity is Severity.SEV3
    assert failed.severity is Severity.SEV2


def test_d4_requires_every_case_to_reach_floor():
    result = classify_difficulty(Difficulty.D4, [95] * 7 + [84], THRESHOLDS)
    assert result.floor_pass_rate == pytest.approx(0.875)
    assert result.severity is Severity.SEV2


def test_module_summary_keeps_each_module_independent():
    cases = [
        _case(case_id="a", scores={"M2": 90, "M3": 70, "M5": 100}),
        _case(case_id="b", scores={"M2": 100, "M3": 80, "M5": 100}),
    ]
    modules = summarize_modules(cases)
    assert modules["M2"].score == 95
    assert modules["M3"].score == 75
    assert modules["M5"].score == 100
    assert set(modules) == {"M1", "M2", "M3", "M4", "M5"}
    assert modules["M1"].score is None


def test_hard_event_dominates_high_average_score():
    result = classify_run(
        [_case(events=(_event(Severity.SEV1),))],
        THRESHOLDS,
    )
    assert result.global_severity is Severity.SEV1
    assert result.accepted is False
    assert result.accepted_with_warnings is False


def test_warning_requires_action_and_is_not_accepted():
    cases = [
        _case(
            case_id=f"d3-{index}",
            difficulty=Difficulty.D3,
            scores={"M2": 72, "M3": 72, "M5": 72},
        )
        for index in range(12)
    ]
    result = classify_run(cases, THRESHOLDS)
    assert result.global_severity is Severity.SEV3
    assert result.accepted is False
    assert result.accepted_with_warnings is True
    assert result.warnings
    assert all(item.recommended_action for item in result.warnings)
    expected = {spec_id for ids in P0_SPEC_IDS.values() for spec_id in ids}
    assert set(result.coverage) == expected
    assert len(result.coverage) == 24


def test_repeat_cases_do_not_change_quality_aggregation():
    original = _case(case_id="original", scores={"M2": 100, "M3": 100, "M5": 100})
    repeated = _case(case_id="repeat", scores={"M2": 0, "M3": 0, "M5": 0})
    result = classify_run(
        [original, repeated],
        THRESHOLDS,
        excluded_case_ids={"repeat"},
    )

    assert result.case_count == 2
    assert result.quality_case_count == 1
    assert result.difficulties[Difficulty.D1].count == 1
    assert result.modules["M2"].score == 100
