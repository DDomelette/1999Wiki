from __future__ import annotations

import pytest

from backend.schemas import AskResponse, normalize_route, sanitize_transport_value
from src.rag.chain import RAGChain
from src.rag.direct_conversation import (
    answer_direct_question,
    build_direct_response_packet,
    classify_direct_question,
)
from src.rag.serializers import response_packet_to_public_dict


@pytest.mark.parametrize(
    "question",
    [
        "你是谁",
        "你是什么",
        "你能回答什么",
        "你会什么",
        "我怎么使用",
        "怎么用",
        "自由补充是什么",
        "扩大检索有什么用",
    ],
)
def test_assistant_help_questions_are_direct(question: str) -> None:
    assert classify_direct_question(question) == "assistant_meta"


@pytest.mark.parametrize(
    "question",
    [
        "你好",
        "在吗",
        "午饭吃了吗",
        "谢谢",
        "再见",
    ],
)
def test_bounded_smalltalk_questions_are_direct(question: str) -> None:
    assert classify_direct_question(question) == "smalltalk"


def test_game_question_is_not_intercepted() -> None:
    assert classify_direct_question("玛蒂尔达的技能怎么用") is None


def test_meta_copy_is_subtype_specific() -> None:
    identity = answer_direct_question("assistant_meta", "你是什么")
    capability = answer_direct_question("assistant_meta", "你能回答什么")
    usage = answer_direct_question("assistant_meta", "我怎么使用")

    assert len({identity, capability, usage}) == 3
    assert "知识库助手" in identity
    assert "技能" in capability
    assert "语音" in capability
    assert "直接输入" in usage


def test_meal_smalltalk_acknowledges_prompt_and_redirects_naturally() -> None:
    answer = answer_direct_question("smalltalk", "午饭吃了吗")

    assert "不需要吃饭" in answer
    assert "角色" in answer or "剧情" in answer


def test_direct_packet_has_no_retrieval_or_recovery_payload() -> None:
    packet = build_direct_response_packet(
        "你能回答什么",
        memory_status="new",
        memory_turns_used=0,
    )

    assert packet is not None
    retrieval = packet.retrieval_packet
    assert retrieval.requested_intents == ("meta_question",)
    assert retrieval.sources == ()
    assert retrieval.assets == ()
    assert retrieval.media == ()
    assert retrieval.omitted_actions == ()
    assert retrieval.failure_actions == ()
    assert retrieval.route_decision.effective_route == "llm_general"
    assert retrieval.route_decision.route_reason == "direct_assistant_response"
    assert packet.grounding_mode == "none"
    assert packet.turn_outcome == "not_committable"
    assert dict(packet.memory_info) == {
        "status": "new",
        "turns_used": 0,
        "rewrite_mode": "none",
    }


def test_smalltalk_packet_uses_a_non_retrieval_intent() -> None:
    packet = build_direct_response_packet("午饭吃了吗")

    assert packet is not None
    assert packet.retrieval_packet.requested_intents == ("smalltalk",)
    assert packet.retrieval_packet.route_decision.effective_route == "llm_general"


def test_direct_packet_normalizes_invalid_memory_diagnostics() -> None:
    packet = build_direct_response_packet(
        "你是谁",
        memory_status="unexpected",
        memory_turns_used=-4,
    )

    assert packet is not None
    assert dict(packet.memory_info) == {
        "status": "disabled",
        "turns_used": 0,
        "rewrite_mode": "none",
    }


def test_non_direct_question_returns_no_packet() -> None:
    assert build_direct_response_packet("介绍一下玛蒂尔达") is None


class _ExplodingExecutionService:
    def execute(self, *args, **kwargs):
        raise AssertionError("normal RAG execution must not run")


def test_rag_chain_execute_bypasses_normal_pipeline_for_direct_question() -> None:
    chain = RAGChain.__new__(RAGChain)
    chain._execution_service = _ExplodingExecutionService()

    packet = chain.execute("我怎么使用", memory_status="new")

    assert "直接输入" in packet.answer
    assert packet.turn_outcome == "not_committable"


class _RecordingExecutionService:
    def __init__(self) -> None:
        self.requests = []

    def execute(self, request, conversation, trace):
        self.requests.append(request)
        return "normal-result"


def test_rag_chain_execute_preserves_normal_question_path() -> None:
    service = _RecordingExecutionService()
    chain = RAGChain.__new__(RAGChain)
    chain._execution_service = service

    result = chain.execute("介绍一下玛蒂尔达")

    assert result == "normal-result"
    assert service.requests[0].question == "介绍一下玛蒂尔达"


def test_direct_packet_validates_as_public_response() -> None:
    packet = build_direct_response_packet("我怎么使用")

    assert packet is not None
    response = AskResponse.model_validate(response_packet_to_public_dict(packet))
    assert response.route is not None
    assert response.route.route_reason == "direct_assistant_response"
    assert response.failure_actions == []


def test_route_normalization_preserves_direct_smalltalk_metadata() -> None:
    packet = build_direct_response_packet("午饭吃了吗")

    assert packet is not None
    public = response_packet_to_public_dict(packet)
    route = normalize_route(public["route"])

    assert route is not None
    assert route["intent"] == "smalltalk"
    assert route["requested_intents"] == ["smalltalk"]
    assert route["semantic_intents"] == ["smalltalk"]
    assert route["route_reason"] == "direct_assistant_response"


def test_transport_sanitizer_keeps_direct_answer_timing() -> None:
    sanitized = sanitize_transport_value({
        "stage_ms": {
            "answer.direct": 1.25,
            "unknown.stage": 2.5,
        },
    })

    assert sanitized == {"stage_ms": {"answer.direct": 1.25}}
