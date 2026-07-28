# True SSE Answer Streaming Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stream actual DeepSeek answer chunks to the browser with server-driven phase updates, authoritative citation-validated finalization, one-shot correction, and media hidden until completion.

**Architecture:** Split the existing RAG execution service into immutable preparation and shared finalization stages so synchronous and streaming transports use one retrieval snapshot and one validation path. Keep transport orchestration in `backend/sse.py`: blocking preparation/finalization run off the event loop, model chunks are consumed asynchronously with cancellation and heartbeat handling, and the frontend reduces the richer SSE protocol into one assistant-message state machine.

**Tech Stack:** Python 3.11, FastAPI/Starlette `StreamingResponse`, LangChain `ChatOpenAI`, asyncio, pytest; React 18, TypeScript, Zustand, Vitest/Testing Library; Caddy and Docker Compose for transport verification.

## Global Constraints

- Work only in `D:\1999Wiki\.worktrees\codex\true-sse-streaming` on branch `codex/true-sse-streaming`.
- Keep synchronous `POST /ask` externally compatible.
- Every streamed token must be an actual model increment, never a fixed-size slice of a completed answer.
- `done.answer` is authoritative; only the final validated answer may enter conversation memory.
- Media/source metadata may arrive early but media, sources, and actions render only after `done`.
- Client abort, disconnect, generation failure, or validation failure must not commit memory.
- Use backend-driven `understanding`, `retrieving`, `generating`, `validating`, and `corrected` phases; do not invent percentages or timer-driven progress.
- Keep `/media/...`, MinIO, Wiki media, COS boundaries, prompts, models, vector retrieval, and blue/green topology unchanged.
- Do not merge `main`, publish images, or modify the production server until the user approves the local preview.
- Keep the existing Linux/Docker `uvloop` dependency; Windows tests use the existing environment because `uvloop==0.22.1` is not installable on Windows.
- Do not upgrade npm dependencies or address the pre-existing audit findings in this feature.
- Never touch or stage `D:\1999Wiki\docs\superpowers\plans\2026-07-24-blue-green-final-hardening.md`.

---

## File Map

- `src/rag/execution.py`: owns `PreparedExecution`, retrieval preparation, generation messages, draft finalization, and synchronous parity.
- `src/rag/chain.py`: exposes the execution service methods and an async model-chunk iterator without duplicating prompt construction.
- `backend/sse.py`: owns SSE encoding, phase/event order, heartbeat, disconnect checks, error semantics, serialization, and memory commit boundary.
- `src/rag/tracing.py`: retains real first-token marks and exposes timing without synthesizing them at completion.
- `tests/test_rag_execution.py`: proves preparation is immutable, sync execution invokes each stage once, and supplied drafts finalize identically.
- `tests/test_sse.py`: proves event ordering, real early chunks, correction, errors, heartbeat, cancellation, memory, and sync/stream parity.
- `frontend/react-app/src/api/sse.ts`: parses the extended SSE protocol.
- `frontend/react-app/src/api/sse.test.ts`: proves status/correction/heartbeat/chunk parsing and terminal-event behavior.
- `frontend/react-app/src/types/index.ts`: defines the stream phase and assistant-message state.
- `frontend/react-app/src/store/chatStore.ts`: reduces callbacks into draft/final/pending-media/correction state and ignores stale streams.
- `frontend/react-app/src/store/chatStore.test.ts`: proves state transitions, media gating, correction, partial error, abort, and stale-event isolation.
- `frontend/react-app/src/components/chat/MessageBubble.tsx`: renders the dynamic phase, correction notice, partial-error notice, and final media.
- `frontend/react-app/src/components/chat/MessageBubble.test.tsx`: proves user-visible phase/correction/error/media behavior.
- `frontend/react-app/src/components/sections/ChatSection.css`: styles phase and notice elements without changing the page design.
- `docker/frontend.Caddyfile`: only if the transport test proves buffering; otherwise leave unchanged.

---

### Task 1: Split RAG Execution into Preparation and Finalization

**Files:**
- Modify: `src/rag/execution.py`
- Modify: `src/rag/chain.py`
- Test: `tests/test_rag_execution.py`

**Interfaces:**
- Produces:
  - `GenerationMode = Literal["grounded", "free_supplement", "none"]`
  - `PreparedExecution`
  - `RAGExecutionService.prepare(request, conversation, trace) -> PreparedExecution`
  - `RAGExecutionService.finalize(prepared, draft, trace) -> ResponsePacket`
  - `RAGExecutionService.execute(request, conversation, trace) -> ResponsePacket`
  - `RAGChain.prepare_execution(question, category, route_options, action_payload, conversation, memory_status, memory_turns_used, trace) -> PreparedExecution`
  - `RAGChain.finalize_execution(prepared, draft, trace) -> ResponsePacket`
- Consumes existing `AskExecutionInput`, `FrozenRetrievalPacket`, `ResponsePacket`, normalization helpers, and citation validation.

- [ ] **Step 1: Write failing preparation/finalization tests**

Add focused tests to `tests/test_rag_execution.py`:

```python
def test_prepare_freezes_one_retrieval_snapshot_and_does_not_call_answer_llm(tmp_path):
    chain, planner, retriever, registry, llm = _chain(tmp_path, ["unused"])
    prepared = chain.prepare_execution("Question")
    assert prepared.generation_mode == "grounded"
    assert prepared.retrieval_packet.sources[0]["name"] == "Fixture"
    assert planner.calls == retriever.calls == registry.calls == 1
    assert llm.calls == 0


def test_finalize_uses_supplied_draft_and_shared_citation_rules(tmp_path):
    chain, *_ = _chain(tmp_path, ["unused"])
    prepared = chain.prepare_execution("Question")
    packet = chain.finalize_execution(prepared, "Answer [S01]")
    assert packet.answer == "Answer [S01]"
    assert packet.citation_validation.valid is True
    assert packet.turn_outcome == "grounded"


def test_execute_is_prepare_generate_finalize_once(tmp_path):
    chain, planner, retriever, registry, llm = _chain(tmp_path, ["Answer [S01]"])
    packet = chain.execute("Question")
    assert packet.answer == "Answer [S01]"
    assert planner.calls == retriever.calls == registry.calls == llm.calls == 1
```

- [ ] **Step 2: Run the new tests and verify RED**

Run:

```powershell
python -m pytest tests/test_rag_execution.py -k "prepare_freezes or finalize_uses or execute_is_prepare" -q
```

Expected: failures because `prepare_execution`, `finalize_execution`, and `PreparedExecution` do not exist.

- [ ] **Step 3: Implement immutable preparation**

In `src/rag/execution.py`, introduce:

```python
GenerationMode = Literal["grounded", "free_supplement", "none"]


@dataclass(frozen=True)
class PreparedExecution:
    request: AskExecutionInput
    conversation: ConversationProjection
    retrieval_packet: FrozenRetrievalPacket
    answer_context: str
    generation_messages: tuple[Any, ...]
    generation_mode: GenerationMode
    immediate_answer: str | None
    missing_intents: tuple[str, ...]
```

`prepare()` performs exactly one `chain.retrieve()`, creates the existing `FrozenRetrievalPacket`, computes the generation branch, and creates grounded or free-supplement messages. It must not invoke the answer LLM.

For `generation_mode == "none"`, set `immediate_answer` to the existing retrieval failure, API-key, or empty-retrieval message. For generated branches, set it to `None`.

- [ ] **Step 4: Implement shared finalization and preserve sync behavior**

Move the existing normalization/citation code into:

```python
def finalize(
    self,
    prepared: PreparedExecution,
    draft: str | None,
    trace: RequestTrace | NullTrace | None = None,
) -> ResponsePacket:
```

Rules:

- `none`: use `prepared.immediate_answer`, `grounding_mode="none"`, not committable.
- `free_supplement`: validate the supplied draft with empty context; preserve the existing prefix exactly once.
- `grounded`: run all existing normalizers in their existing order, then `validate_or_repair_answer`.
- Build `ResponsePacket` only from `prepared.retrieval_packet`.
- Call `trace.mark_validated_ready()` only after the packet is complete.

Refactor `execute()` to call `prepare()`, perform one existing synchronous model invocation for generated branches, mark the first model token after the full sync invoke as it currently does, and call `finalize()`.

Expose thin `RAGChain.prepare_execution()` and `RAGChain.finalize_execution()` methods that construct `AskExecutionInput` consistently with `execute()`.

- [ ] **Step 5: Run execution tests and verify GREEN**

Run:

```powershell
python -m pytest tests/test_rag_execution.py -q
```

Expected: all tests pass, including existing normalization, retry, packet, and serializer tests.

- [ ] **Step 6: Commit Task 1**

```powershell
git add -- src/rag/execution.py src/rag/chain.py tests/test_rag_execution.py
git commit -m "refactor: split RAG preparation and finalization"
```

---

### Task 2: Implement the True Streaming Backend Protocol

**Files:**
- Modify: `src/rag/chain.py`
- Modify: `backend/sse.py`
- Modify: `src/rag/tracing.py` only if a new public timing mark is required
- Test: `tests/test_sse.py`

**Interfaces:**
- Consumes `PreparedExecution` and `RAGChain.finalize_execution()` from Task 1.
- Produces:
  - `RAGChain.astream_prepared(prepared) -> AsyncIterator[str]`
  - `status`, `sources`, `token`, `answer_replace`, `done`, and terminal `error` events.
  - SSE comments from `sse_heartbeat()`.

- [ ] **Step 1: Write a failing true-token ordering test**

Add an async fake whose model waits between actual chunks. Assert on generator yields rather than a buffered `TestClient` response:

```python
def test_stream_emits_real_model_chunk_before_generation_finishes():
    async def scenario():
        chain = _AsyncStreamingChain(chunks=("first", " second"))
        generator = rag_stream_generator(chain, "Question", None)
        first_events = [await anext(generator) for _ in range(5)]
        assert _event_names(first_events) == [
            "status", "status", "sources", "status", "token",
        ]
        assert _event_data(first_events[-1])["token"] == "first"
        assert chain.finished is False
        await generator.aclose()
    asyncio.run(scenario())
```

The fake must implement real preparation/finalization boundaries and only set `finished=True` after its last async chunk. This catches any return to post-completion slicing.

- [ ] **Step 2: Run the ordering test and verify RED**

Run:

```powershell
python -m pytest tests/test_sse.py -k "real_model_chunk" -q
```

Expected: failure because current generator first calls complete `execute()` and its first event is `sources`.

- [ ] **Step 3: Add the asynchronous model iterator**

In `src/rag/chain.py`:

```python
async def astream_prepared(self, prepared: PreparedExecution):
    if prepared.generation_mode == "none":
        return
    async for chunk in self._llm.astream(list(prepared.generation_messages)):
        text = _chunk_text(chunk)
        if text:
            yield text
```

Requirements:

- Free-supplement prefix is emitted exactly once before provider chunks.
- `_chunk_text()` accepts strings and LangChain chunks whose `content` may be a string or a list of content blocks; it emits text only.
- If a test/compatibility LLM has no `astream`, adapt its synchronous `stream()` through a bounded queue and cancellation flag; do not call `invoke()`.
- Closing the async generator closes/cancels the upstream iterator where supported.

- [ ] **Step 4: Rewrite `rag_stream_generator` around real stages**

Implement this state machine in `backend/sse.py`:

```python
yield sse_event("status", {"phase": "understanding"})
yield sse_event("status", {"phase": "retrieving"})
prepared = await _await_with_heartbeats(
    asyncio.to_thread(
        chain.prepare_execution,
        question,
        category,
        route_options,
        action_payload,
        lease.projection,
        lease.status,
        len(lease.projection.turns),
        trace,
    ),
    is_disconnected=is_disconnected,
)
yield sse_event("sources", prepared_public_payload)
if prepared.generation_mode != "none":
    yield sse_event("status", {"phase": "generating"})
    async for token in chain.astream_prepared(prepared):
        draft_parts.append(token)
        trace.mark_model_first_token()
        trace.mark_visible_first_token()
        yield sse_event("token", {"token": token})
    yield sse_event("status", {"phase": "validating"})
packet = await _await_with_heartbeats(
    asyncio.to_thread(chain.finalize_execution, prepared, "".join(draft_parts), trace),
    is_disconnected=is_disconnected,
)
```

Then:

- Validate `AskResponse.model_validate(response_packet_to_public_dict(packet))`.
- Compare the concatenated streamed draft with `packet.answer`.
- Emit `answer_replace` and `status(corrected)` only when they differ.
- Add `corrected: bool` and timing to `done`.
- Use `response_packet_to_public_dict(packet)` for final public data.
- Stop importing or calling `response_packet_to_sse_events()` from the live backend path; retain the serializer for existing offline/evaluation compatibility.
- Check disconnect before expensive work and before every business event.
- Mark completion only for terminal `done`.
- Build `completed_turn` only for a validated final packet.

- [ ] **Step 5: Add failing correction, non-correction, and branch tests**

Add tests that hand the finalizer literal drafts/finals. Use `_parse_sse("".join(blocks))` and assert these literal outcomes:

```python
assert [name for name, _ in corrected_events] == [
    "status", "status", "sources", "status", "token",
    "status", "answer_replace", "status", "done",
]
assert next(data for name, data in corrected_events if name == "answer_replace") == {
    "answer": "Final [S01]",
    "reason": "citation_validation",
}
assert not any(name == "answer_replace" for name, _ in unchanged_events)
assert not any(name == "token" for name, _ in no_model_events)
assert source_events[0][1]["sources"] == done_events[0][1]["sources"]
assert stream_done["answer"] == sync_payload["answer"] == "Final [S01]"
```

Create one named test for each assertion group:

- `test_stream_replaces_draft_once_when_validation_changes_answer`
- `test_stream_does_not_replace_when_final_answer_matches_chunks`
- `test_no_model_branch_emits_no_fake_tokens`
- `test_sources_and_done_share_one_frozen_retrieval_snapshot`
- `test_sync_and_stream_done_are_publicly_equivalent_for_same_draft`

Assertions must use literal event sequences and answers, not production serializers to compute expected output.

- [ ] **Step 6: Run correction/branch tests and verify RED, then GREEN**

Run before implementation completion and confirm the new tests fail for missing events:

```powershell
python -m pytest tests/test_sse.py -k "replaces_draft or does_not_replace or no_model_branch or frozen_retrieval or publicly_equivalent" -q
```

After the minimal event implementation, run the same command and require all selected tests to pass.

- [ ] **Step 7: Commit Task 2**

```powershell
git add -- src/rag/chain.py backend/sse.py src/rag/tracing.py tests/test_sse.py
git commit -m "feat: stream model answer chunks over SSE"
```

---

### Task 3: Add Heartbeat, Failure, Cancellation, and Memory Guarantees

**Files:**
- Modify: `backend/sse.py`
- Test: `tests/test_sse.py`

**Interfaces:**
- Consumes Task 2 state machine.
- Produces:
  - `_await_with_heartbeats(awaitable, *, heartbeat_seconds, is_disconnected)`
  - safe terminal error payload `{message, phase, partial}`
  - cancellation-safe lease release.

- [ ] **Step 1: Write failing edge-case tests**

Add six named tests with literal assertions:

```python
assert ": heartbeat\n\n" in heartbeat_blocks
assert [data["phase"] for name, data in heartbeat_events if name == "status"] == [
    "understanding", "retrieving", "generating", "validating",
]
assert error_before == {"message": SAFE_STREAM_ERROR, "phase": "generating", "partial": False}
assert error_after == {"message": SAFE_STREAM_ERROR, "phase": "generating", "partial": True}
assert replacement_after_validation_failure["reason"] == "safe_fallback"
assert not any(name == "done" for name, _ in validation_failure_events)
assert upstream.closed is True
assert disconnected_memory_turns == ()
assert successful_memory_turns[-1].answer == "Final corrected [S01]"
```

Name the tests:

- `test_long_prepare_emits_heartbeat_comment_without_repeating_status`
- `test_generation_failure_before_first_token_has_partial_false`
- `test_generation_failure_after_first_token_preserves_partial_draft`
- `test_validation_failure_replaces_draft_with_safe_fallback_and_errors`
- `test_disconnect_closes_upstream_and_never_commits_memory`
- `test_success_commits_only_the_final_corrected_answer`

Use a short injected `heartbeat_seconds=0.01` in tests rather than sleeping 10 seconds. Assert memory by reacquiring the real `ConversationMemoryStore`; do not assert only that a mock was called.

- [ ] **Step 2: Run edge-case tests and verify RED**

Run:

```powershell
python -m pytest tests/test_sse.py -k "heartbeat_comment or generation_failure or validation_failure or closes_upstream or final_corrected_answer" -q
```

Expected: failures because heartbeat/error semantics and cancellation cleanup are absent.

- [ ] **Step 3: Implement heartbeat and cancellation-safe waits**

Use an `asyncio.Task` plus timed waits:

```python
async def _await_with_heartbeats(awaitable, *, heartbeat_seconds, is_disconnected):
    task = asyncio.create_task(awaitable)
    try:
        while not task.done():
            if await _disconnected(is_disconnected):
                task.cancel()
                raise ClientDisconnected
            done, _ = await asyncio.wait({task}, timeout=heartbeat_seconds)
            if not done:
                yield ": heartbeat\n\n"
        return await task
    finally:
        if not task.done():
            task.cancel()
```

Because an async generator cannot both `yield` and directly `return value`, implement this as a small event/value iterator or keep the task loop inline in a focused helper object. The observable contract is one heartbeat comment per idle interval and one prepared/final value, not this exact internal syntax.

- [ ] **Step 4: Implement safe terminal failures**

- Before first token: `status(failed)` then `error({phase, partial:false})`.
- After first token: preserve already-sent text in the browser and emit `status(failed)` then `error({phase, partial:true})`.
- Validation exception after draft: emit one `answer_replace` with a fixed safe fallback and `reason:"safe_fallback"`, then `status(failed)` and terminal `error`.
- Log exception class/details server-side; public `message` must not contain raw exception text.
- Never emit `done` after `error`.
- In `finally`, close upstream and release memory lease with `completed_turn=None` unless the validated `done` path completed.

- [ ] **Step 5: Run the full backend streaming suite**

Run:

```powershell
python -m pytest tests/test_sse.py tests/test_rag_execution.py tests/test_conversation_memory.py -q
```

Expected: all tests pass. The existing Windows Torch DLL diagnostic may appear, but pytest must exit `0` with no failed tests.

- [ ] **Step 6: Commit Task 3**

```powershell
git add -- backend/sse.py tests/test_sse.py
git commit -m "feat: harden streaming cancellation and failures"
```

---

### Task 4: Parse the Extended SSE Protocol in React

**Files:**
- Modify: `frontend/react-app/src/api/sse.ts`
- Modify: `frontend/react-app/src/api/sse.test.ts`

**Interfaces:**
- Produces:
  - `StreamPhase`
  - `AnswerReplaceReason`
  - `onStatus(phase)`
  - `onAnswerReplace(answer, reason)`
  - `onError(message, {phase, partial})`
- Existing `onSources`, `onToken`, and `onDone` remain compatible.

- [ ] **Step 1: Write failing parser tests**

Add a single literal stream containing split chunks, a heartbeat, phases, correction, and done:

```typescript
it('parses phases, ignores heartbeat, replaces answer, and stops at done', async () => {
  // Literal wire events; deliberately split "answer_replace" across reads.
  expect(phases).toEqual(['understanding', 'generating', 'validating', 'corrected'])
  expect(replacements).toEqual([{ answer: 'final [S01]', reason: 'citation_validation' }])
  expect(tokens).toEqual(['draft'])
  expect(eventsAfterDone).toEqual([])
})
```

Add an error test asserting `{ phase: 'generating', partial: true }`.

- [ ] **Step 2: Run parser tests and verify RED**

Run:

```powershell
npm test -- --run src/api/sse.test.ts
```

from `frontend/react-app`.

Expected: TypeScript/test failures because the callbacks and types do not exist.

- [ ] **Step 3: Implement typed parsing**

Add:

```typescript
export type StreamPhase =
  | 'understanding' | 'retrieving' | 'generating'
  | 'validating' | 'corrected' | 'cancelled' | 'failed'

export type AnswerReplaceReason = 'citation_validation' | 'safe_fallback'

export interface StreamErrorInfo {
  phase?: StreamPhase
  partial: boolean
}
```

Update callbacks and parser:

- Ignore comment-only heartbeat blocks.
- Validate phase/reason against literal sets before invoking callbacks.
- `answer_replace` invokes `onAnswerReplace`.
- `done` invokes `onDone` and makes the parser ignore later business events.
- `error` invokes the enriched `onError` and terminates parsing.
- Flush the decoder at EOF and parse a final complete block if present.
- Keep callbacks required in the store, but make new callbacks optional if needed to avoid breaking unrelated direct test callers.

- [ ] **Step 4: Run parser tests and verify GREEN**

Run:

```powershell
npm test -- --run src/api/sse.test.ts
```

Expected: all SSE parser tests pass.

- [ ] **Step 5: Commit Task 4**

```powershell
git add -- frontend/react-app/src/api/sse.ts frontend/react-app/src/api/sse.test.ts
git commit -m "feat: parse streaming phases and answer corrections"
```

---

### Task 5: Implement the Frontend Message State Machine and Media Gate

**Files:**
- Modify: `frontend/react-app/src/types/index.ts`
- Modify: `frontend/react-app/src/store/chatStore.ts`
- Modify: `frontend/react-app/src/store/chatStore.test.ts`

**Interfaces:**
- Consumes Task 4 callbacks.
- Produces message fields:
  - `phase?: StreamPhase`
  - `finalized?: boolean`
  - `corrected?: boolean`
  - `correctionNotice?: boolean`
  - `partialError?: boolean`
  - `pendingSources?`, `pendingAssets?`, `pendingMedia?`, `pendingMediaPanels?`
- `sources/assets/media/mediaPanels` remain renderable final fields and are not populated from `onSources`.

- [ ] **Step 1: Write failing store tests**

Add tests that capture the real `StreamCallbacks` passed by the store, drive them in protocol order, and assert literal Zustand state:

```typescript
callbacks.onStatus?.('generating')
callbacks.onToken('Draft')
expect(assistant().phase).toBe('generating')
expect(assistant().content).toBe('Draft')

callbacks.onSources([source], [asset], [media], { mediaPanels: [panel] })
expect(assistant().media).toBeUndefined()
expect(assistant().pendingMedia).toEqual([media])

callbacks.onAnswerReplace?.('Final [S01]', 'citation_validation')
callbacks.onDone('Final [S01]', [source], [asset], [media], { mediaPanels: [panel] })
expect(assistant()).toMatchObject({
  content: 'Final [S01]',
  finalized: true,
  corrected: true,
  streaming: false,
  media: [media],
  mediaPanels: [panel],
})

callbacks.onError('生成中断', { phase: 'generating', partial: true })
expect(assistant()).toMatchObject({ content: 'Draft', partialError: true, streaming: false })
expect(assistant().pendingMedia).toBeUndefined()
```

Use a deferred `streamAsk` promise for abort/stale-event tests. After `abort()`, reject it with `new DOMException('Aborted', 'AbortError')`; assert the assistant is cancelled and its content does not become `请求失败`. Start a later request and invoke callbacks captured from the first request; assert the second assistant is unchanged.

For the media test, invoke `onSources` and inspect real Zustand state before invoking `onDone`; `message.media` and `message.mediaPanels` must remain empty while their pending equivalents are populated.

- [ ] **Step 2: Run store tests and verify RED**

Run:

```powershell
npm test -- --run src/store/chatStore.test.ts
```

Expected: failures because phases, pending media, correction, and partial error fields do not exist.

- [ ] **Step 3: Implement phase and pending-data reduction**

Use a request identity captured by each `send()`:

```typescript
const requestId = makeId()
const updateActive = (patch: Partial<Message>) => set(state => {
  if (state.activeRequestId !== requestId) return state
  // update only this assistant message by id, not blindly the last element
})
```

Rules:

- Assistant starts at `phase:'understanding'`, `streaming:true`, `finalized:false`.
- `onStatus` updates `phase`; `corrected` also sets `corrected` and `correctionNotice`.
- `onSources` populates only pending fields and diagnostics.
- `onToken` appends content but does not clear phase.
- `onAnswerReplace` atomically replaces content.
- `onDone` copies final payload to renderable fields, clears pending fields, sets `finalized:true`, `streaming:false`, and clears the ordinary phase.
- `onError(partial=true)` preserves content and marks `partialError`; non-partial errors use the safe error message. Both clear pending media and end streaming.
- Abort sets `phase:'cancelled'`, ends streaming, clears pending media, invalidates `activeRequestId`, and suppresses the expected `AbortError`.

- [ ] **Step 4: Make correction notice lifetime explicit**

When `corrected` arrives, schedule a 2.5-second dismissal tied to message ID and request ID. The timer may only turn `correctionNotice` off; it must not create phases, delay `done`, or change media. Clear/abort invalidates stale timer updates.

Use fake timers in the test to prove the notice survives `done` and later disappears.

- [ ] **Step 5: Run store tests and verify GREEN**

Run:

```powershell
npm test -- --run src/store/chatStore.test.ts
```

Expected: all chat-store tests pass.

- [ ] **Step 6: Commit Task 5**

```powershell
git add -- frontend/react-app/src/types/index.ts frontend/react-app/src/store/chatStore.ts frontend/react-app/src/store/chatStore.test.ts
git commit -m "feat: manage streamed answer and pending media state"
```

---

### Task 6: Render Phases, Correction, Partial Errors, and Final Media

**Files:**
- Modify: `frontend/react-app/src/components/chat/MessageBubble.tsx`
- Modify: `frontend/react-app/src/components/chat/MessageBubble.test.tsx`
- Modify: `frontend/react-app/src/components/sections/ChatSection.css`

**Interfaces:**
- Consumes final message fields from Task 5.
- Produces accessible UI hooks:
  - `[data-stream-phase]`
  - `[data-correction-notice]`
  - `[data-partial-error]`

- [ ] **Step 1: Write failing component tests**

Add:

```typescript
it.each([
  ['understanding', '正在理解问题…'],
  ['retrieving', '正在检索资料…'],
  ['generating', '正在生成回答…'],
  ['validating', '正在校验引用…'],
])('renders the backend phase %s', (phase, label) => {
  render(<MessageBubble message={{
    id: 'phase', role: 'assistant', content: 'Draft', streaming: true,
    phase: phase as StreamPhase,
  }} />)
  expect(screen.getByRole('status')).toHaveTextContent(label)
})

it('shows correction and partial-error notices from message state', () => {
  render(<MessageBubble message={{
    id: 'notice', role: 'assistant', content: 'Final', finalized: true,
    correctionNotice: true, partialError: true,
  }} />)
  expect(screen.getByText('已完成引用校验并修正')).toBeInTheDocument()
  expect(screen.getByText('回答未完成，未经过引用校验')).toBeInTheDocument()
})
```

Use actual `MessageBubble` rendering and query accessible text/media; do not assert mock components.

For media gating, render one streaming message containing only `pendingMedia` and assert no image exists, then rerender it with `streaming:false`, `finalized:true`, and the same item in `media`; assert the image URL is rendered.

- [ ] **Step 2: Run component tests and verify RED**

Run:

```powershell
npm test -- --run src/components/chat/MessageBubble.test.tsx
```

Expected: failures because phase mapping and notice elements are missing.

- [ ] **Step 3: Implement the minimal UI**

In `MessageBubble.tsx`:

- Map phase enum to the approved Chinese text.
- Render one `role="status"` phase line while streaming.
- Render correction notice independently while `correctionNotice` is true.
- Render “回答未完成，未经过引用校验” when `partialError`.
- Keep existing `!message.streaming` final media/source/action gates.
- Never render pending fields.

Move inline phase styles into `ChatSection.css` using:

```css
.message-bubble__stream-status {
  margin-bottom: 6px;
  color: var(--accent-gold);
  font-size: 0.875rem;
}
.message-bubble__correction-notice,
.message-bubble__partial-error {
  margin-top: 6px;
  color: var(--text-secondary);
  font-size: 0.8rem;
}
```

Preserve current typography, gold accent, responsive layout, and reduced-motion behavior.

- [ ] **Step 4: Run component tests and verify GREEN**

Run:

```powershell
npm test -- --run src/components/chat/MessageBubble.test.tsx
```

Expected: all MessageBubble tests pass.

- [ ] **Step 5: Commit Task 6**

```powershell
git add -- frontend/react-app/src/components/chat/MessageBubble.tsx frontend/react-app/src/components/chat/MessageBubble.test.tsx frontend/react-app/src/components/sections/ChatSection.css
git commit -m "feat: show answer streaming progress and corrections"
```

---

### Task 7: Integration Verification and Local Preview

**Files:**
- Modify: `tests/test_sse.py` if an integration assertion is missing
- Modify: `docker/frontend.Caddyfile` only if measured buffering requires `flush_interval -1`
- Test: backend, frontend, build, Docker/local SSE timing

**Interfaces:**
- Produces a locally previewable feature branch only.
- Does not merge, push release images, or deploy.

- [ ] **Step 1: Add a timing integration test**

Create a deterministic async chain with two gated chunks. Assert:

```python
first_token_index < validating_index < done_index
first_token_received_before_model_finished is True
```

Also assert `sources` carries media but `done` is the only authoritative completion event.

- [ ] **Step 2: Run complete backend verification**

Run:

```powershell
python -m pytest tests/test_sse.py tests/test_rag_execution.py tests/test_conversation_memory.py tests/test_rag_eval_client.py tests/test_rag_eval_deterministic.py -q
```

Expected: exit code `0`, no failed tests.

- [ ] **Step 3: Run complete frontend verification**

From `frontend/react-app`:

```powershell
npm test -- --run
npm run build
```

Expected: all Vitest files pass; TypeScript and Vite production build exit `0`.

- [ ] **Step 4: Verify transport headers and non-buffering**

Start the local app through the normal Docker Compose/Caddy path. Use an SSE timing probe that prints timestamp, event name, and payload prefix as each line arrives:

```powershell
curl.exe -N -H "Content-Type: application/json" `
  -d '{"question":"请介绍一个资料充足的角色"}' `
  http://127.0.0.1:<local-port>/api/ask/stream
```

Acceptance:

- status arrives before retrieval completes;
- at least one token is visible before `validating` and `done`;
- tokens arrive over multiple timestamps for a sufficiently long answer;
- response has `text/event-stream`, `Cache-Control: no-cache`, and no buffering behavior.

If and only if Caddy still batches events, add `flush_interval -1` to the `/api/*` reverse proxy and add a configuration test that executes/parses the Caddyfile rather than grepping source text.

- [ ] **Step 5: Manually verify media and correction behavior**

In the local browser:

1. Ask a long grounded question and observe the four live phases plus incremental text.
2. Ask an image question; verify no image request starts during generation and images appear after completion.
3. Ask for voice/audio; verify panels, pagination, and playback after completion.
4. Exercise a fixture/query that triggers citation correction; verify one whole-answer correction and the 2.5-second notice.
5. Stop a long answer; verify the partial-answer warning, hidden media, and no memory continuation from the aborted answer.

- [ ] **Step 6: Run fresh final verification and inspect scope**

Run:

```powershell
git diff --check
git status --short
python -m pytest tests/test_sse.py tests/test_rag_execution.py tests/test_conversation_memory.py tests/test_rag_eval_client.py tests/test_rag_eval_deterministic.py -q
Set-Location frontend/react-app
npm test -- --run
npm run build
```

Return to the worktree root and confirm only planned files changed.

- [ ] **Step 7: Commit any verified integration-only changes**

If Task 7 changed tracked files:

```powershell
git add -- tests/test_sse.py docker/frontend.Caddyfile
git commit -m "test: verify true SSE delivery"
```

Do not create an empty commit.

- [ ] **Step 8: Stop at the local-preview checkpoint**

Provide:

- local preview URL;
- exact branch and commit;
- automated test/build counts;
- measured first-status, first-token, validation, and completion times;
- known limitations;
- explicit statement that `main`, registries, and production remain unchanged.

Wait for the user’s local-experience approval before invoking the branch-finishing, merge, image publication, or blue/green deployment workflow.
