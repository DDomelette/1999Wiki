from __future__ import annotations

import asyncio
import ast
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from langchain_core.messages import AIMessage

from src.rag.conversation import (
    MAX_PROJECTED_CODE_POINTS,
    MAX_SESSIONS,
    MAX_STORED_CODE_POINTS,
    TRUNCATION_MARKER,
    ConversationMemoryStore,
    ConversationTurn,
    build_conversation_turn,
    category_accepts_entity,
    history_messages,
    is_contextual_follow_up,
    project_turns,
)


class FakeClock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


def _uuid(index: int) -> UUID:
    return UUID(f"00000000-0000-4000-8000-{index:012d}")


def _turn(
    index: int,
    *,
    entity: str = "角色甲",
    answer_size: int = 8,
    question_size: int | None = None,
    intents: tuple[str, ...] = ("skill",),
    grounding_mode: str = "grounded",
    entity_id: str | None = "char:test",
) -> ConversationTurn:
    question = f"问题{index}" if question_size is None else "问" * question_size
    return build_conversation_turn(
        original_question=question,
        standalone_question=f"{entity} {question}",
        answer="答" * answer_size,
        entity=entity,
        entity_type="character",
        entity_id=entity_id,
        requested_intents=intents,
        category="人物",
        grounding_mode=grounding_mode,
        completed_at=datetime(2026, 7, 14, tzinfo=timezone.utc),
    )


def test_build_turn_applies_field_limits_and_ordered_unique_intents():
    turn = build_conversation_turn(
        original_question="问" * 1200,
        standalone_question="独" * 1200,
        answer="答" * 5000,
        entity="角色甲",
        entity_type="character",
        requested_intents=("voice", "skill", "voice", ""),
        category="人物",
        grounding_mode="ungrounded",
        completed_at=datetime(2026, 7, 14, tzinfo=timezone.utc),
    )

    assert len(turn.original_question) == 1000
    assert len(turn.standalone_question) == 1000
    assert len(turn.answer) == 4000
    assert turn.original_question.endswith(TRUNCATION_MARKER)
    assert turn.standalone_question.endswith(TRUNCATION_MARKER)
    assert turn.answer.endswith(TRUNCATION_MARKER)
    assert turn.requested_intents == ("voice", "skill")
    assert turn.grounding_mode == "ungrounded"


def test_projection_keeps_recent_complete_turns_and_hides_answers_from_planner():
    turns = [_turn(index, answer_size=3000) for index in range(8)]

    projection = project_turns(turns)
    payload = projection.planner_payload()

    assert len(projection.turns) <= 6
    assert projection.code_points <= MAX_PROJECTED_CODE_POINTS
    assert projection.turns[-1].original_question == "问题7"
    assert payload["last_entity"] == "角色甲"
    assert payload["last_entity_type"] == "character"
    assert payload["last_entity_id"] == "char:test"
    assert payload["recent_questions"] == [turn.original_question for turn in projection.turns]
    assert payload["recent_standalone_questions"] == [
        turn.standalone_question for turn in projection.turns
    ]
    assert payload["recent_requested_intents"] == [
        list(turn.requested_intents) for turn in projection.turns
    ]
    assert "answer" not in str(payload).lower()
    assert "答" not in str(payload)


def test_history_anchor_requires_complete_owner_identity():
    complete = project_turns([_turn(1, entity_id="story-1")])
    incomplete = project_turns([_turn(2, entity_id=None)])

    assert complete.last_entity_ref is not None
    assert complete.last_entity_ref.ownership_key == ("character", "story-1")
    assert incomplete.last_entity_ref is None
    assert incomplete.last_entity is None
    assert incomplete.planner_payload()["last_entity_id"] is None


def test_all_assistant_history_is_non_evidence_and_old_ids_are_neutralized():
    grounded = replace(_turn(1), answer="Old grounded fact [S01]")
    ungrounded = replace(
        _turn(2, grounding_mode="ungrounded"),
        answer="Old free answer [S02]",
    )

    messages = history_messages(project_turns([grounded, ungrounded]))
    assistant_text = [message.content for message in messages if isinstance(message, AIMessage)]

    assert all(text.startswith("[Historical conversation; not current evidence]") for text in assistant_text)
    assert all("[S01]" not in text and "[S02]" not in text for text in assistant_text)
    assert all("[Historical citation expired]" in text for text in assistant_text)


def test_local_and_mixed_turn_outcomes_are_preserved_in_history():
    local = replace(
        _turn(1),
        grounding_mode="none",
        entity=None,
        entity_type=None,
        entity_id=None,
        answer="Local answer [S01]",
    )
    mixed = replace(
        _turn(2),
        grounding_mode="mixed",
        answer="Mixed answer [S02]",
    )

    projection = project_turns([local, mixed])
    messages = history_messages(projection)
    assistant_text = [
        message.content for message in messages if isinstance(message, AIMessage)
    ]

    assert [turn.grounding_mode for turn in projection.turns] == ["none", "mixed"]
    assert all("[S01]" not in text and "[S02]" not in text for text in assistant_text)


def test_conversation_runtime_has_no_persistence_dependencies_or_file_writes():
    module_path = Path(__file__).parents[1] / "src" / "rag" / "conversation.py"
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    imported_roots = {
        alias.name.split(".", 1)[0]
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    called_attributes = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }

    assert not imported_roots & {"pymilvus", "minio", "pymysql", "sqlalchemy"}
    assert not called_attributes & {"write_text", "write_bytes", "open", "dump"}


def test_projection_counts_unicode_code_points_and_never_splits_a_turn():
    first = _turn(1, answer_size=3999, question_size=999)
    second = _turn(2, answer_size=3999, question_size=999)

    projection = project_turns((first, second))

    assert projection.turns == (second,)
    assert projection.code_points == sum(
        len(value)
        for value in (
            second.original_question,
            second.standalone_question,
            second.answer,
        )
    )
    assert projection.code_points <= MAX_PROJECTED_CODE_POINTS


def test_follow_up_and_category_rules_are_explicit():
    assert is_contextual_follow_up("她的技能和语音呢") is True
    assert is_contextual_follow_up("技能呢") is True
    assert is_contextual_follow_up("请继续详细说") is True
    assert is_contextual_follow_up("刚才那个角色还有别的语音吗") is True
    assert is_contextual_follow_up("一个没有回指的新问题") is False
    assert category_accepts_entity("人物", "character") is True
    assert category_accepts_entity("心相", "character") is False
    assert category_accepts_entity(None, "unknown") is True
    assert category_accepts_entity("人物", "unknown") is False


def test_store_enforces_six_turn_and_stored_text_budgets():
    async def scenario() -> None:
        store = ConversationMemoryStore()
        conversation_id = _uuid(1)
        for index in range(8):
            lease = await store.acquire(conversation_id)
            await store.release(lease, _turn(index, answer_size=3000))

        lease = await store.acquire(conversation_id)
        try:
            stored = tuple(lease._entry.turns)
            assert len(stored) <= 6
            assert sum(
                len(turn.original_question)
                + len(turn.standalone_question)
                + len(turn.answer)
                for turn in stored
            ) <= MAX_STORED_CODE_POINTS
            assert lease.projection.code_points <= MAX_PROJECTED_CODE_POINTS
            assert stored[-1].original_question == "问题7"
        finally:
            await store.release(lease)

    asyncio.run(scenario())


def test_clear_invalidates_an_inflight_lease_before_release():
    async def scenario() -> None:
        store = ConversationMemoryStore()
        conversation_id = _uuid(2)
        lease = await store.acquire(conversation_id)

        await store.clear(conversation_id)
        committed = await store.release(lease, _turn(1))
        next_lease = await store.acquire(conversation_id)
        try:
            assert committed is False
            assert next_lease.projection.turns == ()
            assert next_lease.status == "new"
        finally:
            await store.release(next_lease)

    asyncio.run(scenario())


def test_clear_invalidates_a_lease_that_was_waiting_before_clear():
    async def scenario() -> None:
        store = ConversationMemoryStore()
        conversation_id = _uuid(20)
        active = await store.acquire(conversation_id)
        waiting = asyncio.create_task(store.acquire(conversation_id))
        await asyncio.sleep(0)

        await store.clear(conversation_id)
        assert await store.release(active, _turn(1)) is False
        stale = await asyncio.wait_for(waiting, timeout=0.2)
        assert stale.projection.turns == ()
        assert await store.release(stale, _turn(2)) is False

        fresh = await store.acquire(conversation_id)
        try:
            assert fresh.status == "new"
            assert fresh.projection.turns == ()
        finally:
            await store.release(fresh)

    asyncio.run(scenario())


def test_cancelled_waiter_releases_its_capacity_reservation():
    async def scenario() -> None:
        store = ConversationMemoryStore(max_sessions=1)
        conversation_id = _uuid(21)
        active = await store.acquire(conversation_id)
        waiting = asyncio.create_task(store.acquire(conversation_id))
        await asyncio.sleep(0)
        waiting.cancel()
        try:
            await waiting
        except asyncio.CancelledError:
            pass

        assert active._entry is not None
        assert active._entry.active_leases == 1
        assert await store.release(active) is False
        replacement = await store.acquire(_uuid(22))
        assert replacement.status == "new"
        await store.release(replacement)

    asyncio.run(scenario())


def test_release_is_idempotent_and_unlocks_exactly_once():
    async def scenario() -> None:
        store = ConversationMemoryStore()
        conversation_id = _uuid(23)
        lease = await store.acquire(conversation_id)

        assert await store.release(lease, _turn(1)) is True
        assert await store.release(lease, _turn(2)) is False

        current = await asyncio.wait_for(store.acquire(conversation_id), timeout=0.2)
        try:
            assert [turn.original_question for turn in current.projection.turns] == ["问题1"]
        finally:
            await store.release(current)

    asyncio.run(scenario())


def test_same_conversation_serializes_while_distinct_conversations_run_in_parallel():
    async def scenario() -> None:
        store = ConversationMemoryStore()
        first_id = _uuid(3)
        other_id = _uuid(4)
        first_lease = await store.acquire(first_id)
        waiting = asyncio.create_task(store.acquire(first_id))
        await asyncio.sleep(0)
        assert waiting.done() is False

        other_lease = await asyncio.wait_for(store.acquire(other_id), timeout=0.2)
        await store.release(other_lease)
        await store.release(first_lease, _turn(1))

        second_lease = await asyncio.wait_for(waiting, timeout=0.2)
        try:
            assert second_lease.projection.turns[-1].original_question == "问题1"
        finally:
            await store.release(second_lease)

    asyncio.run(scenario())


def test_ttl_returns_expired_without_reusing_old_turns_and_accepts_new_commit():
    async def scenario() -> None:
        clock = FakeClock()
        store = ConversationMemoryStore(clock=clock)
        conversation_id = _uuid(5)
        first = await store.acquire(conversation_id)
        await store.release(first, _turn(1))

        clock.advance(1801)
        expired = await store.acquire(conversation_id)
        assert expired.status == "expired"
        assert expired.projection.turns == ()
        assert await store.release(expired, _turn(2)) is True

        current = await store.acquire(conversation_id)
        try:
            assert current.status == "hit"
            assert [turn.original_question for turn in current.projection.turns] == ["问题2"]
        finally:
            await store.release(current)

    asyncio.run(scenario())


def test_capacity_evicts_oldest_inactive_entry_but_never_active_entry():
    async def scenario() -> None:
        clock = FakeClock()
        store = ConversationMemoryStore(clock=clock, max_sessions=2)
        active_id = _uuid(6)
        old_id = _uuid(7)
        new_id = _uuid(8)

        active = await store.acquire(active_id)
        clock.advance(1)
        old = await store.acquire(old_id)
        await store.release(old, _turn(1, entity="角色乙"))
        clock.advance(1)
        new = await store.acquire(new_id)
        await store.release(new, _turn(2, entity="角色丙"))

        assert active_id in store._entries
        assert old_id not in store._entries
        assert new_id in store._entries
        assert await store.release(active, _turn(3)) is True

    asyncio.run(scenario())


def test_capacity_fails_open_when_every_entry_has_an_active_lease():
    async def scenario() -> None:
        store = ConversationMemoryStore(max_sessions=2)
        first = await store.acquire(_uuid(9))
        second = await store.acquire(_uuid(10))
        disabled = await store.acquire(_uuid(11))
        try:
            assert disabled.status == "disabled"
            assert disabled.conversation_id is None
            assert disabled.projection.turns == ()
        finally:
            await store.release(disabled)
            await store.release(first)
            await store.release(second)

    asyncio.run(scenario())


def test_unknown_clear_is_idempotent_and_does_not_allocate_a_session():
    async def scenario() -> None:
        store = ConversationMemoryStore(max_sessions=2)
        conversation_id = _uuid(12)

        await store.clear(conversation_id)
        await store.clear(conversation_id)

        assert conversation_id not in store._entries
        assert len(store._entries) == 0

    asyncio.run(scenario())


def test_store_hard_capacity_and_failure_release_leave_locks_reusable():
    async def scenario() -> None:
        store = ConversationMemoryStore(max_sessions=MAX_SESSIONS)
        for index in range(1, MAX_SESSIONS + 2):
            lease = await store.acquire(_uuid(index + 100))
            await store.release(lease, _turn(index))

        assert len(store._entries) == MAX_SESSIONS
        assert _uuid(101) not in store._entries

        conversation_id = _uuid(5000)
        lease = await store.acquire(conversation_id)
        try:
            raise RuntimeError("simulated request failure")
        except RuntimeError:
            await store.release(lease, turn=None)

        retry = await asyncio.wait_for(store.acquire(conversation_id), timeout=0.2)
        await store.release(retry)

    asyncio.run(scenario())
