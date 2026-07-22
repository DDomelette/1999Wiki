"""SSE encoding over one validated RAG execution packet."""
from __future__ import annotations

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
    """Execute once, then serialize only the frozen validated packet."""
    trace = make_request_trace()
    lease = ConversationLease.disabled()
    completed_turn = None
    with trace.span("memory.acquire"):
        if memory_store is not None:
            lease = await acquire_lease(memory_store, conversation_id)
    try:
        try:
            execution_request = AskExecutionInput(
                question=question,
                category=category,
                route_options=route_options or {},
                action_payload=action_payload,
                memory_status=lease.status,
                memory_turns_used=len(lease.projection.turns),
            )
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
            yield sse_event(
                "error",
                {"message": f"RAG execution failed: {type(exc).__name__}: {exc}"},
            )
            return

        with trace.span("response.serialize"):
            AskResponse.model_validate(response_packet_to_public_dict(packet))
            events = response_packet_to_sse_events(packet)
        for event in events:
            if is_disconnected is not None and await is_disconnected():
                return
            event_data = event.to_dict()
            if event.event == "token":
                trace.mark_visible_first_token()
            if event.event == "done" and packet.turn_outcome in {"grounded", "ungrounded"}:
                trace.mark_visible_first_token()
                trace.mark_completed()
                completed_turn = build_completed_turn(
                    execution_request,
                    packet,
                    datetime.now(timezone.utc),
                )
            elif event.event == "done":
                trace.mark_visible_first_token()
                trace.mark_completed()
            if event.event in {"sources", "done"}:
                event_data["timing"] = trace_snapshot_to_public(trace.snapshot())
            yield sse_event(event.event, event_data)
    finally:
        if memory_store is not None:
            await release_lease(memory_store, lease, completed_turn)
