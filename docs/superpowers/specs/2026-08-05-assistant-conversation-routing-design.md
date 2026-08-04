# Direct Assistant Conversation Routing Design

## Status

Approved for implementation on 2026-08-05. The user approved the proposed
assistant-meta and small-talk routing fix after code review of the production
chat behavior.

## Problem

The question planner recognizes some assistant-facing prompts as
`meta_question`, but the normal execution path still treats them as RAG
requests. With no entity and no matching evidence, the retriever returns an
empty packet, route policy keeps the request grounded unless the user manually
enables free supplement, and the UI shows a knowledge-base failure with
recovery actions.

Closely related phrasings are inconsistent because the explicit meta patterns
are narrow. Casual prompts such as greetings or meal questions have no
first-class intent and can enter broad retrieval or generic free supplement.
When free supplement is used, prior assistant answers are included as history,
which can cause later prompts such as “我怎么使用” to repeat an earlier identity
answer.

## Approaches Considered

1. **Direct backend conversation boundary before planning (selected).** Detect a
   narrow set of assistant-help and small-talk prompts at the start of
   `RAGChain.execute`, return a deterministic `ResponsePacket`, and bypass the
   planner, retriever, answer LLM, citation repair, and conversation commit.
   This is the smallest trustworthy change and applies consistently to sync and
   SSE clients.
2. **Add new intents throughout planner, retriever, route policy, and execution.**
   This is architecturally pure but expands the retrieval contract for requests
   that should never retrieve evidence. It requires more policy and packet
   changes than the behavior warrants.
3. **Intercept prompts in the React store.** Rejected because it would fix only
   one client, duplicate backend policy in TypeScript, leave `/ask` and other
   frontends inconsistent, and permit client bypass.

## Design

Add `src/rag/direct_conversation.py` as an isolated boundary with three public
operations:

- `classify_direct_question(question)` returns `assistant_meta`, `smalltalk`, or
  `None` from normalized user text;
- `answer_direct_question(kind, question)` returns a deterministic, concise
  response chosen by subtype;
- `build_direct_response_packet(...)` builds a complete immutable
  `ResponsePacket` or returns `None`.

`RAGChain.execute` calls `build_direct_response_packet` before constructing
`AskExecutionInput`. A direct packet uses:

- a `QueryPlan` with `meta_question` or `smalltalk` intent, no entity, empty
  retrieval fields, and `route="llm_general"`;
- a `RouteDecision` with `effective_route="llm_general"`,
  `retrieval_outcome="empty"`, and a direct-response reason;
- no sources, assets, media, omitted actions, or failure actions;
- `grounding_mode="none"` and `turn_outcome="not_committable"`;
- the existing memory status and turn count for diagnostics, but no history
  projection or conversation commit.

The direct path must work without an LLM API key and must not call the planner,
retriever, answer LLM, or citation repair.

## Supported Behavior

Assistant-help classification covers equivalent forms of:

- identity: “你是谁”, “你是什么”, “你这助手是什么”;
- capability: “你能回答什么”, “能查什么”, “你会什么”, “有哪些功能”;
- usage: “怎么使用”, “怎么用”, “使用方法”, “如何提问”;
- mode help: questions mentioning “扩大检索” or “自由补充”.

Small-talk classification covers a deliberately small surface:

- greetings and presence checks;
- meal questions;
- thanks;
- farewells.

Replies remain scoped to the product. They may acknowledge the conversational
prompt and invite a relevant follow-up, but they do not invent game facts.

## Memory and UI Semantics

Direct replies are not committed to `ConversationMemoryStore`. This prevents
identity, usage help, and casual exchanges from contaminating later entity
resolution or being echoed as historical assistant context.

Because the direct packet contains no failure actions, the React UI does not
render “扩大范围重新搜索” or “使用自由补充重答” for these prompts. No frontend
special case is required.

## Verification

TDD coverage must prove:

1. screenshot-equivalent phrasings classify consistently;
2. assistant-help answers differ by identity, capability, and usage subtype;
3. small-talk responses are natural but bounded;
4. direct execution does not call planner, retriever, or LLM;
5. direct packets contain no sources or recovery actions and are not
   committable;
6. direct answers work when `llm_ready()` is false;
7. ordinary game questions continue through the existing RAG execution path;
8. sync and SSE endpoints serialize the same direct answer semantics.

## Non-goals

- open-domain chat;
- model-generated assistant persona;
- changing the free-supplement authorization policy for arbitrary questions;
- modifying retrieval artifacts, Milvus, prompts for grounded game answers, or
  frontend visual design.
