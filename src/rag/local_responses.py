"""Central deterministic responses for non-retrieval tasks."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AssistantCapabilities:
    identity: str
    project: str
    primary_capability: str


CAPABILITIES = AssistantCapabilities(
    identity="本项目的 AI 助手",
    project="《重返未来：1999》",
    primary_capability="主要基于已接入的知识库回答游戏相关问题",
)

_LOCAL_FALLBACK = "当前无法生成本地说明，请稍后重试。"


def render_local_response(task_type: str, query: str, *, reason: str) -> str:
    language = _language_for(query)
    try:
        if task_type == "assistant_meta":
            if language == "en":
                return (
                    "I am this project's AI assistant. I primarily answer questions about "
                    "Reverse: 1999 using the connected knowledge base."
                )
            return (
                f"我是{CAPABILITIES.identity}，{CAPABILITIES.primary_capability}"
                f"{CAPABILITIES.project}。"
            )
        if task_type == "social_smalltalk":
            if language == "en":
                return "I do not eat or have a body, but I can chat or help look up information."
            if any(marker in query for marker in ("饭", "吃")):
                return "我不吃饭，也没有身体，不过可以陪你聊聊或继续查资料。"
            return "你好！我没有人类的生活经历，不过可以陪你聊聊或继续查资料。"
        if task_type == "general_open" and reason == "general_open_denied":
            if language == "en":
                return (
                    "Answers outside the connected knowledge base require explicit free "
                    "supplement permission. You can enable that option and try again."
                )
            return "这个问题超出当前知识库范围；如需数据库外回答，请明确开启自由补充后重试。"
        if task_type == "out_of_scope":
            if language == "en":
                return "That operation is outside this assistant's supported capabilities."
            return "这个操作不在当前助手支持的能力范围内。"
    except Exception:
        return _LOCAL_FALLBACK
    return _LOCAL_FALLBACK


def _language_for(query: str) -> str:
    return "zh" if any("\u4e00" <= character <= "\u9fff" for character in query) else "en"


__all__ = ["AssistantCapabilities", "CAPABILITIES", "render_local_response"]
