from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from src.rag.prompts import SYSTEM_TEMPLATE, get_rag_prompt


def test_rag_prompt_allows_limited_summary_when_context_is_incomplete():
    assert "资料不足" in SYSTEM_TEMPLATE
    assert "基于已有信息" in SYSTEM_TEMPLATE
    assert "有限总结" in SYSTEM_TEMPLATE


def test_prompt_requires_current_short_citation_ids():
    assert "[S01]" in SYSTEM_TEMPLATE
    assert "[S01][S03]" in SYSTEM_TEMPLATE
    assert "S ID" in SYSTEM_TEMPLATE


def test_prompt_requires_structured_values_to_be_copied_exactly():
    assert "字段值原样复制" in SYSTEM_TEMPLATE
    assert "单位" in SYSTEM_TEMPLATE
    assert "原始值" in SYSTEM_TEMPLATE
    assert "枚举" in SYSTEM_TEMPLATE


def test_prompt_preserves_raw_markers_and_rejects_false_premises():
    assert "不得补充单位" in SYSTEM_TEMPLATE
    assert "保留原始标点和括号" in SYSTEM_TEMPLATE
    assert "错误前提" in SYSTEM_TEMPLATE
    assert "内部 intent" in SYSTEM_TEMPLATE


def test_prompt_requires_epistemic_qualifiers_to_be_preserved():
    assert "据传" in SYSTEM_TEMPLATE
    assert "不确定性" in SYSTEM_TEMPLATE
    assert "主体归属" in SYSTEM_TEMPLATE


def test_prompt_keeps_history_roles_below_system_and_current_context_is_fact_authority():
    prompt = get_rag_prompt()
    history = [
        HumanMessage(content="旧问题"),
        AIMessage(content="[非知识库自由补充历史]\n旧回答"),
    ]

    messages = prompt.format_messages(
        context="本轮证据",
        history=history,
        question="当前问题",
    )

    assert isinstance(messages[0], SystemMessage)
    assert "历史回答仅用于对话连贯" in messages[0].content
    assert "本轮检索到的已知信息是唯一事实依据" in messages[0].content
    assert isinstance(messages[1], HumanMessage)
    assert isinstance(messages[2], AIMessage)
    assert messages[-1].content == "当前问题"
