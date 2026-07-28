"""SSE encoding over one validated RAG execution packet."""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Awaitable, Callable
from uuid import UUID

from backend.conversation_runtime import acquire_lease, release_lease
from backend.schemas import AskResponse, sanitize_transport_value
from src.rag.conversation import (
    ConversationLease,
    ConversationMemoryStore,
)
from src.rag.execution import AskExecutionInput, build_completed_turn
from src.rag.serializers import (
    retrieval_packet_to_public_dict,
    response_packet_to_public_dict,
    response_packet_to_sse_events,
)
from src.rag.tracing import make_request_trace, trace_snapshot_to_public


def sse_event(event: str, data: dict[str, Any]) -> str:
    raw_token = data.get("token") if event == "token" else None
    sanitized = sanitize_transport_value(data)
    if not isinstance(sanitized, dict):
        sanitized = {}
    if event == "token":
        safe_token = sanitize_transport_value({"value": raw_token})
        if isinstance(safe_token, dict) and "value" in safe_token:
            sanitized["token"] = safe_token["value"]
    return f"event: {event}\ndata: {json.dumps(sanitized, ensure_ascii=False)}\n\n"


async def rag_stream_generator(
    chain: Any,
    question: str,
    category: str | None,
    route_options: dict[str, bool] | None = None,
    action_payload: dict[str, Any] | None = None,
    memory_store: ConversationMemoryStore | None = None,
    conversation_id: UUID | None = None,
    is_disconnected: Callable[[], Awaitable[bool]] | None = None,
) -> AsyncGenerator[str, None]:
    """Stream real model increments when the chain exposes staged execution."""
    trace = make_request_trace()
    lease = ConversationLease.disabled()
    completed_turn = None
    with trace.span("memory.acquire"):
        if memory_store is not None:
            lease = await acquire_lease(memory_store, conversation_id)
    try:
        if not all(
            hasattr(chain, name)
            for name in ("prepare_execution", "astream_prepared", "finalize_execution")
        ):
            async for block, turn in _legacy_stream(
                chain=chain,
                question=question,
                category=category,
                route_options=route_options,
                action_payload=action_payload,
                lease=lease,
                trace=trace,
                is_disconnected=is_disconnected,
            ):
                if turn is not None:
                    completed_turn = turn
                yield block
            return

        execution_request = AskExecutionInput(
            question=question,
            category=category,
            route_options=route_options or {},
            action_payload=action_payload,
            memory_status=lease.status,
            memory_turns_used=len(lease.projection.turns),
        )
        if await _disconnected(is_disconnected):
            return
        yield sse_event("status", {"phase": "understanding"})
        if await _disconnected(is_disconnected):
            return
        yield sse_event("status", {"phase": "retrieving"})

        try:
            prepared = await asyncio.to_thread(
                chain.prepare_execution,
                question,
                category=category,
                route_options=route_options or {},
                action_payload=action_payload,
                conversation=lease.projection,
                memory_status=lease.status,
                memory_turns_used=len(lease.projection.turns),
                trace=trace,
            )
        except Exception as exc:
            yield sse_event(
                "error",
                {"message": f"RAG execution failed: {type(exc).__name__}: {exc}"},
            )
            return

        if await _disconnected(is_disconnected):
            return
        grounding_mode = {
            "grounded": "grounded",
            "free_supplement": "ungrounded",
            "none": "none",
        }.get(prepared.generation_mode, "none")
        sources_data = retrieval_packet_to_public_dict(
            prepared.retrieval_packet,
            grounding_mode=grounding_mode,
            citation_warning="",
            memory_info={
                "status": lease.status,
                "turns_used": len(lease.projection.turns),
                "rewrite_mode": str(
                    getattr(
                        prepared.retrieval_packet.plan,
                        "context_rewrite_mode",
                        "none",
                    )
                    or "none"
                ),
            },
        )
        sources_data["timing"] = trace_snapshot_to_public(trace.snapshot())
        yield sse_event("sources", sources_data)

        draft_parts: list[str] = []
        if prepared.generation_mode != "none":
            if await _disconnected(is_disconnected):
                return
            yield sse_event("status", {"phase": "generating"})
            try:
                with trace.span("answer.llm"):
                    async for token in chain.astream_prepared(prepared):
                        if await _disconnected(is_disconnected):
                            return
                        if not token:
                            continue
                        draft_parts.append(str(token))
                        trace.mark_model_first_token()
                        trace.mark_visible_first_token()
                        yield sse_event("token", {"token": str(token)})
            except Exception as exc:
                yield sse_event(
                    "error",
                    {"message": f"RAG execution failed: {type(exc).__name__}: {exc}"},
                )
                return
            if await _disconnected(is_disconnected):
                return
            yield sse_event("status", {"phase": "validating"})

        try:
            packet = await asyncio.to_thread(
                chain.finalize_execution,
                prepared,
                "".join(draft_parts) if prepared.generation_mode != "none" else None,
                trace,
            )
        except Exception as exc:
            yield sse_event(
                "error",
                {"message": f"RAG execution failed: {type(exc).__name__}: {exc}"},
            )
            return

        with trace.span("response.serialize"):
            AskResponse.model_validate(response_packet_to_public_dict(packet))
            done_data = response_packet_to_public_dict(packet)
        streamed_draft = "".join(draft_parts)
        corrected = (
            prepared.generation_mode != "none"
            and streamed_draft != packet.answer
        )
        if corrected:
            if await _disconnected(is_disconnected):
                return
            yield sse_event(
                "answer_replace",
                {"answer": packet.answer, "reason": "citation_validation"},
            )
            yield sse_event("status", {"phase": "corrected"})
        if await _disconnected(is_disconnected):
            return
        trace.mark_completed()
        done_data["corrected"] = corrected
        done_data["timing"] = trace_snapshot_to_public(trace.snapshot())
        completed_turn = build_completed_turn(
            execution_request,
            packet,
            datetime.now(timezone.utc),
        )
        yield sse_event("done", done_data)
    finally:
        if memory_store is not None:
            await release_lease(memory_store, lease, completed_turn)


async def _disconnected(
    is_disconnected: Callable[[], Awaitable[bool]] | None,
) -> bool:
    return bool(is_disconnected is not None and await is_disconnected())


async def _legacy_stream(
    *,
    chain: Any,
    question: str,
    category: str | None,
    route_options: dict[str, bool] | None,
    action_payload: dict[str, Any] | None,
    lease: ConversationLease,
    trace: Any,
    is_disconnected: Callable[[], Awaitable[bool]] | None,
) -> AsyncGenerator[tuple[str, Any], None]:
    execution_request = AskExecutionInput(
        question=question,
        category=category,
        route_options=route_options or {},
        action_payload=action_payload,
        memory_status=lease.status,
        memory_turns_used=len(lease.projection.turns),
    )
    try:
        packet = chain.execute(
            question,
            category=category,
            route_options=route_options or {},
            action_payload=action_payload,
            conversation=lease.projection,
            memory_status=lease.status,
            memory_turns_used=len(lease.projection.turns),
            trace=trace,
        )
    except Exception as exc:
        yield (
            sse_event(
                "error",
                {"message": f"RAG execution failed: {type(exc).__name__}: {exc}"},
            ),
            None,
        )
        return

    with trace.span("response.serialize"):
        AskResponse.model_validate(response_packet_to_public_dict(packet))
        events = response_packet_to_sse_events(packet)
    for event in events:
        if await _disconnected(is_disconnected):
            return
        event_data = event.to_dict()
        completed_turn = None
        if event.event == "token":
            trace.mark_visible_first_token()
        if event.event == "done":
            trace.mark_visible_first_token()
            trace.mark_completed()
            completed_turn = build_completed_turn(
                execution_request,
                packet,
                datetime.now(timezone.utc),
            )
        if event.event in {"sources", "done"}:
            event_data["timing"] = trace_snapshot_to_public(trace.snapshot())
        yield sse_event(event.event, event_data), completed_turn
