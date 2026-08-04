# Direct Assistant Conversation Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Answer assistant-help and bounded small-talk prompts naturally without entering RAG retrieval, requiring free-supplement authorization, or contaminating RAG conversation memory.

**Architecture:** Add one isolated direct-conversation module that classifies a narrow prompt surface and builds a complete immutable `ResponsePacket`. `RAGChain.execute` consults this boundary before creating `AskExecutionInput`; ordinary questions continue through the existing execution service unchanged.

**Tech Stack:** Python 3, FastAPI, LangChain message types, pytest, existing immutable RAG contracts and SSE serializer.

## Global Constraints

- Apply the behavior in the backend so `/ask`, `/ask/stream`, React, Streamlit, and Gradio share one policy.
- Do not query Milvus, BM25, the planner LLM, answer LLM, or citation repair for direct prompts.
- Do not require `DEEPSEEK_API_KEY` for direct prompts.
- Do not commit direct replies to `ConversationMemoryStore`.
- Return no sources, assets, media, omitted actions, or failure actions.
- Preserve the current free-supplement authorization policy for all non-direct questions.
- Keep the recognized small-talk surface deliberately narrow; this is not open-domain chat.

---

## File Structure

- `src/rag/direct_conversation.py`: owns direct prompt normalization, classification, deterministic copy, and immutable packet construction.
- `src/rag/chain.py`: invokes the direct boundary at the start of `RAGChain.execute` and otherwise preserves the current execution path.
- `tests/test_direct_conversation.py`: covers classification, copy selection, packet invariants, execution bypass, sync/SSE parity, and memory isolation.

### Task 1: Define Direct Classification and Copy

**Files:**
- Create: `tests/test_direct_conversation.py`
- Create: `src/rag/direct_conversation.py`

**Interfaces:**
- Produces: `classify_direct_question(question: str) -> Literal["assistant_meta", "smalltalk"] | None`.
- Produces: `answer_direct_question(kind: DirectQuestionKind, question: str) -> str`.
- Consumes: no planner, retriever, LLM, or runtime artifact.

- [ ] **Step 1: Write failing classifier and copy tests**

Add table-driven tests equivalent to:

```python
@pytest.mark.parametrize("question", [
    "你是谁", "你是什么", "你能回答什么", "你会什么",
    "我怎么使用", "怎么用", "自由补充是什么", "扩大检索有什么用",
])
def test_assistant_help_questions_are_direct(question):
    assert classify_direct_question(question) == "assistant_meta"


@pytest.mark.parametrize("question", [
    "你好", "在吗", "午饭吃了吗", "谢谢", "再见",
])
def test_bounded_smalltalk_questions_are_direct(question):
    assert classify_direct_question(question) == "smalltalk"


def test_game_question_is_not_intercepted():
    assert classify_direct_question("玛蒂尔达的技能怎么用") is None


def test_meta_copy_is_subtype_specific():
    identity = answer_direct_question("assistant_meta", "你是什么")
    capability = answer_direct_question("assistant_meta", "你能回答什么")
    usage = answer_direct_question("assistant_meta", "我怎么使用")
    assert identity != capability != usage
    assert "知识库助手" in identity
    assert "技能" in capability and "语音" in capability
    assert "直接输入" in usage


def test_meal_smalltalk_acknowledges_prompt_and_redirects_naturally():
    answer = answer_direct_question("smalltalk", "午饭吃了吗")
    assert "不需要吃饭" in answer
    assert "角色" in answer or "剧情" in answer
```

- [ ] **Step 2: Run focused tests and verify RED**

Run:

```bash
pytest tests/test_direct_conversation.py -q
```

Expected: collection fails because `src.rag.direct_conversation` does not exist.

- [ ] **Step 3: Implement narrow normalization and classification**

Create `src/rag/direct_conversation.py` with:

```python
from __future__ import annotations

import re
from typing import Literal, TypeAlias

DirectQuestionKind: TypeAlias = Literal["assistant_meta", "smalltalk"]

_PUNCTUATION_RE = re.compile(r"[\s，。！？!?、,.：:；;（）()\"'“”‘’]+")


def _compact(question: str) -> str:
    return _PUNCTUATION_RE.sub("", str(question or "").strip().lower())
```

Use exact normalized sets for identity, capability, usage, greeting, presence,
meal, thanks, and farewell prompts. Treat a question containing “自由补充” or
“扩大检索” as assistant help only when its compact length is at most 24 code
points. Do not use loose fragments such as bare “使用”, because
“玛蒂尔达的技能怎么用” must remain a game question.

- [ ] **Step 4: Implement deterministic subtype copy**

Implement `answer_direct_question` with separate identity, capability, usage,
mode-help, greeting/presence, meal, thanks, and farewell responses. The default
assistant-help response must summarize identity, supported knowledge areas, and
one example question. The default small-talk response must acknowledge the user
and invite a scoped follow-up without inventing game facts.

- [ ] **Step 5: Run focused tests and verify GREEN**

Run:

```bash
pytest tests/test_direct_conversation.py -q
```

Expected: classifier and copy tests pass while packet/integration tests are not
yet present.

- [ ] **Step 6: Commit the classifier**

```bash
git add src/rag/direct_conversation.py tests/test_direct_conversation.py
git commit -m "feat: classify direct assistant conversations"
```

### Task 2: Build Trustworthy Direct Response Packets

**Files:**
- Modify: `src/rag/direct_conversation.py`
- Modify: `tests/test_direct_conversation.py`

**Interfaces:**
- Produces: `build_direct_response_packet(question: str, *, category: str | None = None, route_options: Mapping[str, bool] | None = None, action_payload: Mapping[str, object] | None = None, memory_status: str = "disabled", memory_turns_used: int = 0, trace: RequestTrace | NullTrace | None = None) -> ResponsePacket | None`.
- Consumes: `QueryPlan`, `RouteAuthorization`, `RouteDecision`, `FrozenRetrievalPacket`, `CitationValidation`, and `ResponsePacket`.

- [ ] **Step 1: Add failing packet-invariant tests**

Add tests equivalent to:

```python
def test_direct_packet_has_no_retrieval_or_recovery_payload():
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
    assert packet.memory_info == {
        "status": "new", "turns_used": 0, "rewrite_mode": "none",
    }


def test_non_direct_question_returns_none():
    assert build_direct_response_packet("介绍一下玛蒂尔达") is None
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
pytest tests/test_direct_conversation.py -q
```

Expected: FAIL because `build_direct_response_packet` is absent.

- [ ] **Step 3: Implement packet construction**

Construct a `QueryPlan` with intent `meta_question` or `smalltalk`, no entity,
empty retrieval fields, confidence `1.0`, `route="llm_general"`, copied route
options, and `planning_status="direct"`.

Construct route metadata and contracts with:

```python
authorization = RouteAuthorization(
    semantic_intents=(intent,),
    proposed_route="llm_general",
    allow_free_supplement_after_empty=False,
    force_free_supplement=False,
    authorization_reason="direct_assistant_response",
)
decision = RouteDecision(
    authorization=authorization,
    retrieval_outcome="empty",
    effective_route="llm_general",
    route_reason="direct_assistant_response",
)
```

The `FrozenRetrievalPacket` must contain no retrieval or recovery payload. The
`ResponsePacket` must use `CitationValidation(valid=True)`,
`grounding_mode="none"`, and `turn_outcome="not_committable"`.
Normalize unknown memory statuses to `disabled` and negative turn counts to
zero. When a trace is supplied, wrap construction in `answer.direct`, then mark
response availability and validation readiness once.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run:

```bash
pytest tests/test_direct_conversation.py -q
```

Expected: all classifier, copy, and packet tests pass.

- [ ] **Step 5: Commit packet construction**

```bash
git add src/rag/direct_conversation.py tests/test_direct_conversation.py
git commit -m "feat: build direct conversation packets"
```

### Task 3: Integrate the Boundary Before RAG Execution

**Files:**
- Modify: `src/rag/chain.py`
- Modify: `tests/test_direct_conversation.py`

**Interfaces:**
- Consumes: `build_direct_response_packet(...)`.
- Preserves: existing `RAGExecutionService.execute(request, conversation, trace)` behavior for all non-direct questions.

- [ ] **Step 1: Add failing execution-bypass tests**

Use `RAGChain.__new__(RAGChain)` and an exploding execution-service double:

```python
class _ExplodingExecutionService:
    def execute(self, *args, **kwargs):
        raise AssertionError("normal RAG execution must not run")


def test_rag_chain_execute_bypasses_normal_pipeline_for_direct_question():
    chain = RAGChain.__new__(RAGChain)
    chain._execution_service = _ExplodingExecutionService()
    packet = chain.execute("我怎么使用", memory_status="new")
    assert "直接输入" in packet.answer
    assert packet.turn_outcome == "not_committable"


class _RecordingExecutionService:
    def __init__(self):
        self.requests = []

    def execute(self, request, conversation, trace):
        self.requests.append(request)
        return "normal-result"


def test_rag_chain_execute_preserves_normal_question_path():
    service = _RecordingExecutionService()
    chain = RAGChain.__new__(RAGChain)
    chain._execution_service = service
    assert chain.execute("介绍一下玛蒂尔达") == "normal-result"
    assert service.requests[0].question == "介绍一下玛蒂尔达"
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
pytest tests/test_direct_conversation.py -q
```

Expected: the direct test calls the exploding normal service.

- [ ] **Step 3: Add the minimal execute guard**

Import `build_direct_response_packet` in `src/rag/chain.py`. At the first line
of `RAGChain.execute`, before constructing `AskExecutionInput`, call it with the
question, category, route options, action payload, memory status, turn count,
and trace. Return the packet immediately when non-`None`; otherwise execute the
existing code unchanged.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run:

```bash
pytest tests/test_direct_conversation.py -q
```

Expected: both direct bypass and ordinary delegation pass.

- [ ] **Step 5: Commit integration**

```bash
git add src/rag/chain.py tests/test_direct_conversation.py
git commit -m "fix: route assistant help outside RAG"
```

### Task 4: Verify API Parity and Memory Isolation

**Files:**
- Modify: `tests/test_direct_conversation.py`

**Interfaces:**
- Consumes: FastAPI `/ask`, `/ask/stream`, `ConversationMemoryStore`, and the integrated `RAGChain.execute`.
- Produces: regression evidence for the screenshot sequence.

- [ ] **Step 1: Add sync/SSE and memory regression tests**

Create a `TestClient` fixture that installs an uninitialized `RAGChain` with an
exploding execution service into `backend.main._state`, supplies a fresh
`ConversationMemoryStore`, and monkeypatches `_ensure_loaded`.

Test this sequence with one conversation ID:

```text
午饭吃了吗
你能回答什么
你是什么
我怎么使用
```

Assert that:

- each response succeeds without an LLM;
- capability, identity, and usage answers are distinct;
- no response contains the knowledge-base-empty message;
- no response contains sources or failure actions;
- after all four requests, acquiring the conversation still reports no stored
  turns;
- `/ask/stream` token concatenation equals its `done.answer` and exposes the
  same `grounding_mode="none"` and route reason.

- [ ] **Step 2: Run the API regression and verify GREEN**

Run:

```bash
pytest tests/test_direct_conversation.py -q
```

Expected: all direct unit and API tests pass.

- [ ] **Step 3: Run affected backend suites**

Run:

```bash
pytest tests/test_query_plan.py tests/test_route_policy.py tests/test_sse.py tests/test_direct_conversation.py -q
```

Expected: all affected tests pass.

- [ ] **Step 4: Run full verification**

Run:

```bash
pytest -q
```

Expected: the complete Python suite passes with no regression in grounded RAG,
free supplement, citations, conversation memory, or SSE serialization.

- [ ] **Step 5: Commit API coverage**

```bash
git add tests/test_direct_conversation.py
git commit -m "test: cover direct assistant conversation flow"
```
