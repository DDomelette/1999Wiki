from __future__ import annotations

import asyncio
import logging
from uuid import UUID

import pytest
from pydantic import ValidationError

from backend.schemas import AskRequest, AskResponse
from src.rag.conversation import ConversationLease
from tests.conftest import CONVERSATION_ID


def test_ask_request_accepts_uuid_and_rejects_invalid_id():
    valid = AskRequest.model_validate({
        "question": "q",
        "conversation_id": CONVERSATION_ID,
    })

    assert str(valid.conversation_id).endswith("0001")
    with pytest.raises(ValidationError):
        AskRequest.model_validate({
            "question": "q",
            "conversation_id": "not-a-uuid",
        })


def test_ask_request_normalizes_legacy_route_action_at_the_api_boundary():
    request = AskRequest.model_validate({
        "question": "fixture",
        "action_payload": {
            "label": "legacy",
            "query": "fixture",
            "intent": "llm_general",
            "packet_policy": "free_supplement",
        },
    })

    assert request.action_payload is not None
    assert request.action_payload.action_type == "force_free_supplement"
    assert request.action_payload.intent == ""
    assert request.action_payload.packet_policy == ""


def test_sync_ask_commits_only_after_valid_success_response(client_with_memory_chain):
    first = client_with_memory_chain.post("/ask", json={
        "question": "介绍角色甲",
        "conversation_id": CONVERSATION_ID,
    })
    second = client_with_memory_chain.post("/ask", json={
        "question": "她的技能呢",
        "conversation_id": CONVERSATION_ID,
    })

    assert first.status_code == 200
    assert first.json()["memory"] == {
        "status": "new",
        "turns_used": 0,
        "rewrite_mode": "none",
    }
    assert second.json()["memory"] == {
        "status": "hit",
        "turns_used": 1,
        "rewrite_mode": "planner",
    }
    serialized = second.text
    assert "conversation_id" not in serialized
    assert "_conversation_plan" not in serialized
    assert "fixture content" not in serialized


def test_sync_ask_does_not_commit_when_final_public_validation_fails(
    client_with_memory_chain,
    monkeypatch,
):
    from backend import main as main_mod

    original = AskResponse.model_validate
    calls = 0

    def fail_second_validation(cls, value, *args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise ValueError("simulated final public validation failure")
        return original(value, *args, **kwargs)

    monkeypatch.setattr(
        AskResponse,
        "model_validate",
        classmethod(fail_second_validation),
    )
    conversation_id = UUID("00000000-0000-4000-8000-000000000088")

    with pytest.raises(ValueError, match="final public validation"):
        client_with_memory_chain.post("/ask", json={
            "question": "介绍角色甲",
            "conversation_id": str(conversation_id),
        })

    async def stored_turns():
        store = main_mod._state["memory"]
        lease = await store.acquire(conversation_id)
        try:
            return lease.projection.turns
        finally:
            await store.release(lease)

    assert asyncio.run(stored_turns()) == ()


def test_delete_is_idempotent_and_invalidates_old_history(client_with_memory_chain):
    client_with_memory_chain.post("/ask", json={
        "question": "介绍角色甲",
        "conversation_id": CONVERSATION_ID,
    })

    assert client_with_memory_chain.delete(
        f"/conversations/{CONVERSATION_ID}"
    ).status_code == 204
    assert client_with_memory_chain.delete(
        f"/conversations/{CONVERSATION_ID}"
    ).status_code == 204

    after_clear = client_with_memory_chain.post("/ask", json={
        "question": "她的技能呢",
        "conversation_id": CONVERSATION_ID,
    })
    assert after_clear.json()["memory"]["status"] == "new"
    assert after_clear.json()["memory"]["turns_used"] == 0


def test_missing_conversation_id_remains_disabled(client_with_memory_chain):
    response = client_with_memory_chain.post("/ask", json={"question": "介绍角色甲"})

    assert response.status_code == 200
    assert response.json()["memory"] == {
        "status": "disabled",
        "turns_used": 0,
        "rewrite_mode": "none",
    }


def test_openapi_publishes_strict_subtask_info_and_extended_enums():
    from backend.main import app

    schemas = app.openapi()["components"]["schemas"]
    subtask = schemas["SubtaskInfo"]
    properties = subtask["properties"]

    assert subtask["additionalProperties"] is False
    assert set(properties) == {
        "subtask_id",
        "order",
        "task_type",
        "query",
        "effective_route",
        "retrieval_outcome",
        "grounding_mode",
        "status",
        "citation_ids",
    }
    assert "composite" in schemas["RouteInfo"]["properties"]["effective_route"]["enum"]
    assert "not_applicable" in properties["retrieval_outcome"]["enum"]
    assert "mixed" in schemas["AskResponse"]["properties"]["grounding_mode"]["enum"]


class _BrokenStore:
    async def acquire(self, conversation_id):
        raise RuntimeError(f"acquire secret {conversation_id}")

    async def release(self, lease, turn):
        raise RuntimeError("release secret")

    async def clear(self, conversation_id):
        raise RuntimeError(f"clear secret {conversation_id}")


def test_runtime_helpers_fail_open_without_exposing_values(caplog):
    from backend.conversation_runtime import acquire_lease, clear_memory, release_lease

    async def scenario():
        store = _BrokenStore()
        conversation_id = UUID(CONVERSATION_ID)

        lease = await acquire_lease(store, conversation_id)
        released = await release_lease(store, ConversationLease.disabled(), None)
        cleared = await clear_memory(store, conversation_id)
        return lease, released, cleared

    caplog.set_level(logging.WARNING)
    lease, released, cleared = asyncio.run(scenario())
    assert lease.status == "disabled"
    assert released is False
    assert cleared is False
    assert CONVERSATION_ID not in caplog.text
    assert "secret" not in caplog.text


def test_access_log_filter_redacts_only_conversation_uuid_path():
    from backend.conversation_runtime import ConversationPathRedactionFilter

    record = logging.LogRecord(
        name="uvicorn.access",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg='%s - "%s %s HTTP/%s" %d',
        args=(
            "127.0.0.1:1234",
            "DELETE",
            f"/conversations/{CONVERSATION_ID}?reason=user",
            "1.1",
            204,
        ),
        exc_info=None,
    )

    assert ConversationPathRedactionFilter().filter(record) is True
    path = record.args[2]
    assert path.startswith("/conversations/sha256:")
    assert path.endswith("?reason=user")
    assert CONVERSATION_ID not in path
    assert len(path.split("sha256:", 1)[1].split("?", 1)[0]) == 12
