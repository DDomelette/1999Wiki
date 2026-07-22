from __future__ import annotations

import json
from dataclasses import replace
from types import SimpleNamespace

import pytest

from src.rag_eval.contracts import Difficulty, EvalCase, Severity
from src.rag_eval.judge import (
    AnswerJudge,
    JudgeConfigError,
    JudgeResult,
    load_judge_config,
)


def _production():
    return SimpleNamespace(
        llm=SimpleNamespace(base_url="https://production.example/v1", model="answer-model")
    )


def _env():
    return {
        "RAG_EVAL_JUDGE_BASE_URL": "https://judge.example/v1",
        "RAG_EVAL_JUDGE_MODEL": "judge-model",
        "RAG_EVAL_JUDGE_API_KEY": "secret",
    }


def _case(difficulty=Difficulty.D1):
    return EvalCase(
        case_id="fixture-case",
        query="测试实体甲的技能是什么？",
        difficulty=difficulty,
        scenario="text" if difficulty is not Difficulty.D4 else "boundary",
        expected_entity_id="entity-a",
        expected_entity_ids=("entity-a",),
        expected_entity_name="测试实体甲",
        expected_intents=("skill",),
    )


class _Message:
    def __init__(self, content):
        self.content = content


class _Client:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def invoke(self, messages):
        self.calls.append(messages)
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return _Message(response)


def _judge_payload(**overrides):
    payload = {
        "schema_version": "rag_judge.v1",
        "groundedness": 5,
        "relevance": 5,
        "completeness": 5,
        "refusal_correctness": 5,
        "unsupported_claims": [],
        "missing_requirements": [],
        "reason": "supported",
        "passed": True,
    }
    payload.update(overrides)
    return json.dumps(payload, ensure_ascii=False)


def test_load_judge_config_requires_distinct_model_and_all_env_values():
    with pytest.raises(JudgeConfigError, match="missing"):
        load_judge_config(_production(), {})

    same = {
        "RAG_EVAL_JUDGE_BASE_URL": "https://production.example/v1",
        "RAG_EVAL_JUDGE_MODEL": "answer-model",
        "RAG_EVAL_JUDGE_API_KEY": "secret",
    }
    with pytest.raises(JudgeConfigError, match="distinct"):
        load_judge_config(_production(), same)


def test_judge_config_is_temperature_zero_and_identity_has_no_secret():
    config = load_judge_config(_production(), _env())

    assert config.temperature == 0.0
    assert "secret" not in repr(config)
    assert set(config.identity.to_json()) == {"base_url", "model", "prompt_version"}


def test_answer_judge_parses_valid_schema_and_records_prompt_version():
    client = _Client([_judge_payload()])
    judge = AnswerJudge(load_judge_config(_production(), _env()), client=client)

    result = judge.evaluate_answer(
        _case(),
        answer="技能说明。[S01]",
        context="[S01] 测试实体甲 / 技能\n技能证据",
        sources=[{"citation_id": "S01", "name": "测试实体甲", "child_id": "c1"}],
    )

    assert result.judge.groundedness == 5
    assert result.judge.prompt_version == "rag-answer-judge/v1"
    assert result.events == ()
    assert len(client.calls) == 1


def test_short_source_map_id_is_a_valid_citation():
    client = _Client([_judge_payload()])
    judge = AnswerJudge(load_judge_config(_production(), _env()), client=client)

    result = judge.evaluate_answer(
        _case(),
        answer="测试结论。[S01]",
        context="[S01] 测试实体甲 / 基础资料\n测试结论。",
        sources=[{"citation_id": "S01", "name": "测试实体甲", "heading_path": "基础资料"}],
    )

    assert result.citation_validity == 1.0
    assert not any(event.event_code == "ANSWER.INVALID_CITATION" for event in result.events)


def test_short_citation_ids_do_not_depend_on_display_label_format():
    judge = AnswerJudge(
        load_judge_config(_production(), _env()),
        client=_Client([_judge_payload()]),
    )
    result = judge.evaluate_answer(
        _case(),
        answer="测试结论。[S01]",
        context="[S01] 测试实体甲 / 基础资料\n测试结论。",
        sources=[{"citation_id": "S01", "name": "测试实体甲", "heading_path": "测试实体甲 / 基础资料"}],
    )
    assert result.citation_validity == 1.0
    assert result.citation_names == ("S01",)


def test_inline_bracketed_content_is_not_treated_as_a_citation():
    judge = AnswerJudge(
        load_judge_config(_production(), _env()),
        client=_Client([_judge_payload()]),
    )
    result = judge.evaluate_answer(
        _case(),
        answer="灵感是恒姿[岩] 秘具兜售。[S01]",
        context="[S01] 测试实体甲 / 条目\n灵感是恒姿[岩] 秘具兜售。",
        sources=[{"citation_id": "S01", "name": "测试实体甲", "heading_path": "条目"}],
    )
    assert result.citation_names == ("S01",)
    assert result.citation_validity == 1.0


def test_answer_judge_retries_malformed_json_once():
    client = _Client(["not json", _judge_payload(relevance=4)])
    judge = AnswerJudge(load_judge_config(_production(), _env()), client=client)

    result = judge.evaluate_answer(
        _case(),
        answer="技能说明。[S01]",
        context="[S01] 测试实体甲\n技能证据",
        sources=[{"citation_id": "S01", "name": "测试实体甲"}],
    )

    assert result.judge.relevance == 4
    assert len(client.calls) == 2


def test_answer_judge_retries_one_transient_execution_failure():
    client = _Client([RuntimeError("transient judge failure"), _judge_payload()])
    judge = AnswerJudge(load_judge_config(_production(), _env()), client=client)

    result = judge.evaluate_answer(
        _case(),
        answer="技能说明。[S01]",
        context="[S01] 测试实体甲\n技能证据。",
        sources=[{"citation_id": "S01", "name": "测试实体甲"}],
    )

    assert result.judge.groundedness == 5
    assert len(client.calls) == 2
    assert "ANSWER.JUDGE_FAILED" not in {event.event_code for event in result.events}


def test_answer_judge_retries_schema_invalid_json_once():
    invalid = _judge_payload(groundedness=5.0)
    client = _Client([invalid, _judge_payload(groundedness=4)])
    judge = AnswerJudge(load_judge_config(_production(), _env()), client=client)

    result = judge.evaluate_answer(
        _case(),
        answer="技能说明。[S01]",
        context="[S01] 测试实体甲\n技能证据。",
        sources=[{"citation_id": "S01", "name": "测试实体甲"}],
    )

    assert result.judge.groundedness == 4
    assert len(client.calls) == 2


def test_answer_judge_accepts_integral_float_scores_after_one_failed_repair():
    invalid = _judge_payload(groundedness=5.0)
    client = _Client([invalid, invalid])
    judge = AnswerJudge(load_judge_config(_production(), _env()), client=client)

    result = judge.evaluate_answer(
        _case(),
        answer="技能说明。[S01]",
        context="[S01] 测试实体甲\n技能证据。",
        sources=[{"citation_id": "S01", "name": "测试实体甲"}],
    )

    assert result.judge.groundedness == 5
    assert len(client.calls) == 2
    assert "ANSWER.JUDGE_FAILED" not in {event.event_code for event in result.events}


def test_answer_judge_receives_expected_behavior_and_operational_metadata():
    client = _Client([_judge_payload()])
    judge = AnswerJudge(load_judge_config(_production(), _env()), client=client)

    judge.evaluate_answer(
        replace(
            _case(),
            expected_behavior="insufficient_evidence",
            allow_no_sources=True,
        ),
        answer="知识库中未找到相关内容。",
        context="",
        sources=[{
            "citation_id": "S01",
            "entity_type": "psychube",
            "entity_id": "fixture-psychube",
            "child_id": "psychube:fixture:0001",
            "name": "Fixture psychube",
            "heading_path": "Fixture psychube",
        }],
        media=[{
            "media_id": "media:fixture",
            "asset_type": "portrait",
            "title": "Fixture portrait",
        }],
        failure_actions=[{
            "action_type": "expand_search",
            "label": "扩大范围重新搜索",
        }],
    )

    system_prompt = client.calls[0][0].content
    payload = json.loads(client.calls[0][1].content)
    assert "insufficient_evidence" in system_prompt
    assert "partial_answer" in system_prompt
    assert "clarify_or_failure_action" in system_prompt
    assert "media IDs, types, and titles" in system_prompt
    assert "paginated voice" in system_prompt.lower()
    assert "human-readable labels" in system_prompt
    assert "only against the user's requested scope" in system_prompt
    assert "source identity metadata" in system_prompt
    assert "no_fabrication" in system_prompt
    assert "does not mean the cited text source contains those media fields" in system_prompt
    assert "expected entity metadata resolves pronouns" in system_prompt
    assert payload["expected_behavior"] == "insufficient_evidence"
    assert payload["expected_entity_name"] == "测试实体甲"
    assert payload["expected_entity_ids"] == ["entity-a"]
    assert payload["conversation_mode"] == "standalone"
    assert payload["operational_metadata"]["grounding_sources"][0]["entity_type"] == "psychube"
    assert payload["operational_metadata"]["attached_media"][0]["media_id"] == "media:fixture"
    assert payload["operational_metadata"]["failure_actions"][0]["action_type"] == "expand_search"


def test_fake_citation_is_sev1_even_when_judge_scores_high():
    judge = AnswerJudge(
        load_judge_config(_production(), _env()),
        client=_Client([_judge_payload()]),
    )

    result = judge.evaluate_answer(
        _case(),
        answer="技能说明。[S99]",
        context="[S01] 测试实体甲\n技能证据",
        sources=[{"citation_id": "S01", "name": "测试实体甲"}],
    )

    assert any(
        event.event_code == "ANSWER.INVALID_CITATION" and event.severity is Severity.SEV1
        for event in result.events
    )


def test_groundedness_one_is_sev1_candidate():
    judge = AnswerJudge(
        load_judge_config(_production(), _env()),
        client=_Client([_judge_payload(groundedness=1, passed=False, unsupported_claims=["编造事实"])]),
    )

    result = judge.evaluate_answer(
        _case(),
        answer="编造事实。[S01]",
        context="[S01] 测试实体甲\n技能证据",
        sources=[{"citation_id": "S01", "name": "测试实体甲"}],
    )

    assert any(event.event_code == "ANSWER.UNGROUNDED_CLAIM" for event in result.events)
    assert result.severity is Severity.SEV1


def test_pair_judge_reports_semantic_contradiction():
    pair_payload = json.dumps(
        {
            "schema_version": "rag_pair_judge.v1",
            "equivalent": False,
            "contradictions": ["技能数量矛盾"],
            "reason": "one says two and one says three",
        },
        ensure_ascii=False,
    )
    judge = AnswerJudge(
        load_judge_config(_production(), _env()),
        client=_Client([pair_payload]),
    )

    result = judge.evaluate_answer_pair(
        _case(),
        stream_answer="有两个技能",
        sync_answer="有三个技能",
        context="技能证据",
    )

    assert result.equivalent is False
    assert result.contradictions == ("技能数量矛盾",)


def test_judge_result_rejects_out_of_range_scores():
    with pytest.raises(ValueError, match="1..5"):
        JudgeResult.from_payload(
            json.loads(_judge_payload(groundedness=6)),
            prompt_version="rag-answer-judge/v1",
        )
