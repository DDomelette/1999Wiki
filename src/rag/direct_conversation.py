"""Deterministic answers for assistant help and bounded small talk."""
from __future__ import annotations

import re
from typing import Literal, TypeAlias

DirectQuestionKind: TypeAlias = Literal["assistant_meta", "smalltalk"]

_PUNCTUATION_RE = re.compile(r"[\s，。！？!?、,.：:；;（）()\"'“”‘’]+")

_IDENTITY_QUESTIONS = frozenset({
    "你是谁",
    "你是什么",
    "你是做什么的",
    "你这个助手是什么",
    "你这助手是什么",
})
_CAPABILITY_QUESTIONS = frozenset({
    "你能回答什么",
    "你能回答啥",
    "你能查什么",
    "你会什么",
    "你能做什么",
    "你能干什么",
    "有哪些功能",
    "这个助手能做什么",
    "这个助手能查什么",
})
_USAGE_QUESTIONS = frozenset({
    "怎么使用",
    "如何使用",
    "怎么用",
    "我怎么使用",
    "这个助手怎么用",
    "这个网站怎么用",
    "使用方法",
    "如何提问",
    "怎么提问",
})

_GREETING_QUESTIONS = frozenset({"你好", "嗨", "哈喽", "hello", "早上好", "早安", "晚安"})
_PRESENCE_QUESTIONS = frozenset({"在吗", "你在吗"})
_MEAL_QUESTIONS = frozenset({"吃饭了吗", "你吃饭了吗", "午饭吃了吗", "晚饭吃了吗"})
_THANKS_QUESTIONS = frozenset({"谢谢", "感谢", "多谢", "谢谢你"})
_FAREWELL_QUESTIONS = frozenset({"再见", "拜拜", "回头见"})


def _compact(question: str) -> str:
    return _PUNCTUATION_RE.sub("", str(question or "").strip().lower())


def _is_mode_help(compact: str) -> bool:
    return len(compact) <= 24 and ("自由补充" in compact or "扩大检索" in compact)


def classify_direct_question(question: str) -> DirectQuestionKind | None:
    compact = _compact(question)
    if not compact:
        return None
    if (
        compact in _IDENTITY_QUESTIONS
        or compact in _CAPABILITY_QUESTIONS
        or compact in _USAGE_QUESTIONS
        or _is_mode_help(compact)
    ):
        return "assistant_meta"
    if compact in (
        _GREETING_QUESTIONS
        | _PRESENCE_QUESTIONS
        | _MEAL_QUESTIONS
        | _THANKS_QUESTIONS
        | _FAREWELL_QUESTIONS
    ):
        return "smalltalk"
    return None


def answer_direct_question(kind: DirectQuestionKind, question: str) -> str:
    compact = _compact(question)
    if kind == "assistant_meta":
        if compact in _IDENTITY_QUESTIONS:
            return (
                "我是《重返未来：1999》知识库助手，负责根据已接入的资料回答游戏相关问题。"
                "你可以直接问角色、技能、剧情、心相、语音或图片等内容。"
            )
        if compact in _CAPABILITY_QUESTIONS:
            return (
                "我可以查询《重返未来：1999》的角色基础资料、技能、单品、文化档案、剧情、"
                "心相、语音、图片和视频。也可以继续追问同一角色，例如“她的技能呢？”。"
            )
        if compact in _USAGE_QUESTIONS:
            return (
                "直接输入角色名和问题即可，例如“玛蒂尔达有哪些技能？”或“介绍一下牙仙”。"
                "资料不够时可以使用“扩大检索”；只有需要非知识库补充时再启用“自由补充”。"
            )
        if "扩大检索" in compact:
            return (
                "“扩大检索”会增加知识库检索范围，适合当前资料覆盖不完整时重试；"
                "它仍然只使用知识库证据。"
            )
        if "自由补充" in compact:
            return (
                "“自由补充”允许在知识库没有结果时给出非知识库回答。"
                "这类内容会明确标注，不能视为知识库事实。"
            )
        return (
            "我是《重返未来：1999》知识库助手。你可以直接输入角色名和问题，"
            "查询基础资料、技能、剧情、心相、语音、图片等内容。"
        )

    if compact in _MEAL_QUESTIONS:
        return (
            "我不需要吃饭，不过可以陪你聊聊。你可以告诉我一个角色名，"
            "或者直接问一段剧情、技能或设定。"
        )
    if compact in _THANKS_QUESTIONS:
        return "不客气。还有角色、剧情或资料需要查，可以继续问。"
    if compact in _FAREWELL_QUESTIONS:
        return "再见。之后需要查《重返未来：1999》的资料时再来。"
    if compact in _PRESENCE_QUESTIONS:
        return "在。直接把角色名或问题发给我就行。"
    return "你好。可以直接问我《重返未来：1999》的角色、技能、剧情或其他资料。"


__all__ = [
    "DirectQuestionKind",
    "answer_direct_question",
    "classify_direct_question",
]
