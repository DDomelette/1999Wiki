from __future__ import annotations

import asyncio
import re
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Literal, Sequence
from uuid import UUID

from langchain_core.messages import AIMessage, HumanMessage

from .contracts import EntityRef


GroundingMode = Literal["grounded", "ungrounded", "none", "mixed"]
MemoryStatus = Literal["disabled", "new", "hit", "expired"]
RewriteMode = Literal["none", "planner", "fallback"]

MAX_TURNS = 6
TTL_SECONDS = 30 * 60
MAX_SESSIONS = 4096
MAX_STORED_CODE_POINTS = 16_000
MAX_PROJECTED_CODE_POINTS = 8_000
MAX_QUESTION_CODE_POINTS = 1_000
MAX_ANSWER_CODE_POINTS = 4_000
TRUNCATION_MARKER = "\n[truncated]"
HISTORY_ASSISTANT_PREFIX = "[Historical conversation; not current evidence]"
HISTORY_CITATION_EXPIRED = "[Historical citation expired]"
_HISTORY_CITATION_RE = re.compile(r"\[S\d{2,}\]")

_CONTEXT_PRONOUNS = (
    "她",
    "他",
    "它",
    "这个角色",
    "该角色",
    "那个角色",
    "这个人",
    "那个人",
    "这位",
    "那位",
)
_SECTION_TERMS = (
    "技能",
    "神秘术",
    "传承",
    "塑造",
    "语音",
    "台词",
    "洞悉",
    "物品",
    "文化",
    "背景",
    "资料",
    "生日",
    "图片",
    "立绘",
    "皮肤",
    "视频",
    "pv",
)
_BACK_REFERENCE_TERMS = (
    "继续",
    "刚才",
    "上一个",
    "上面",
    "详细说",
    "展开说",
    "接着",
    "还有",
)


def _truncate(value: object, limit: int) -> str:
    text = str(value or "")
    if len(text) <= limit:
        return text
    if limit <= len(TRUNCATION_MARKER):
        return TRUNCATION_MARKER[:limit]
    return text[: limit - len(TRUNCATION_MARKER)] + TRUNCATION_MARKER


def _ordered_strings(values: Sequence[object]) -> tuple[str, ...]:
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in result:
            result.append(text)
    return tuple(result)


def project_assistant_history(answer: object) -> str:
    """Mark assistant history as non-evidence and invalidate request-local IDs."""
    neutralized = neutralize_historical_citations(str(answer or ""))
    return f"{HISTORY_ASSISTANT_PREFIX}\n{neutralized}"


def neutralize_historical_citations(answer: str) -> str:
    return _HISTORY_CITATION_RE.sub(HISTORY_CITATION_EXPIRED, answer)


def history_messages(projection: "ConversationProjection") -> list[object]:
    messages: list[object] = []
    for turn in projection.turns:
        messages.append(HumanMessage(content=turn.original_question))
        messages.append(AIMessage(content=project_assistant_history(turn.answer)))
    return messages


@dataclass(frozen=True)
class ConversationTurn:
    original_question: str
    standalone_question: str
    answer: str
    entity: str | None
    entity_type: str | None
    requested_intents: tuple[str, ...]
    category: str | None
    grounding_mode: GroundingMode
    completed_at: datetime
    entity_id: str | None = None


def build_conversation_turn(
    *,
    original_question: str,
    standalone_question: str,
    answer: str,
    entity: str | None,
    entity_type: str | None,
    requested_intents: Sequence[object],
    category: str | None,
    grounding_mode: GroundingMode,
    completed_at: datetime,
    entity_id: str | None = None,
) -> ConversationTurn:
    if grounding_mode not in {"grounded", "ungrounded", "none", "mixed"}:
        raise ValueError(f"unsupported grounding mode: {grounding_mode}")
    return ConversationTurn(
        original_question=_truncate(original_question, MAX_QUESTION_CODE_POINTS),
        standalone_question=_truncate(standalone_question, MAX_QUESTION_CODE_POINTS),
        answer=_truncate(answer, MAX_ANSWER_CODE_POINTS),
        entity=str(entity).strip() if entity else None,
        entity_type=str(entity_type).strip() if entity_type else None,
        requested_intents=_ordered_strings(requested_intents),
        category=str(category).strip() if category else None,
        grounding_mode=grounding_mode,
        completed_at=completed_at,
        entity_id=str(entity_id).strip() if entity_id else None,
    )


def _turn_code_points(turn: ConversationTurn) -> int:
    return len(turn.original_question) + len(turn.standalone_question) + len(turn.answer)


@dataclass(frozen=True)
class ConversationProjection:
    turns: tuple[ConversationTurn, ...] = ()
    code_points: int = 0

    @property
    def last_entity_ref(self) -> EntityRef | None:
        for turn in reversed(self.turns):
            if turn.entity and turn.entity_type and turn.entity_id:
                return EntityRef(
                    entity_type=turn.entity_type,
                    entity_id=turn.entity_id,
                    entity_name=turn.entity,
                    resolution_mode="history_exact",
                )
        return None

    @property
    def last_entity(self) -> str | None:
        ref = self.last_entity_ref
        return ref.entity_name if ref else None

    @property
    def last_entity_type(self) -> str | None:
        ref = self.last_entity_ref
        return ref.entity_type if ref else None

    @property
    def last_entity_id(self) -> str | None:
        ref = self.last_entity_ref
        return ref.entity_id if ref else None

    def planner_payload(self) -> dict[str, object]:
        return {
            "last_entity": self.last_entity,
            "last_entity_type": self.last_entity_type,
            "last_entity_id": self.last_entity_id,
            "recent_questions": [turn.original_question for turn in self.turns],
            "recent_standalone_questions": [
                turn.standalone_question for turn in self.turns
            ],
            "recent_requested_intents": [
                list(turn.requested_intents) for turn in self.turns
            ],
        }


EMPTY_PROJECTION = ConversationProjection()


def project_turns(
    turns: Sequence[ConversationTurn],
    *,
    max_turns: int = MAX_TURNS,
    max_code_points: int = MAX_PROJECTED_CODE_POINTS,
) -> ConversationProjection:
    selected: list[ConversationTurn] = []
    total = 0
    for turn in reversed(tuple(turns)[-max_turns:]):
        size = _turn_code_points(turn)
        if total + size > max_code_points:
            break
        selected.append(turn)
        total += size
    selected.reverse()
    return ConversationProjection(tuple(selected), total)


def is_contextual_follow_up(query: str) -> bool:
    normalized = "".join(str(query or "").strip().lower().split())
    if not normalized:
        return False
    if any(token in normalized for token in _CONTEXT_PRONOUNS):
        return True
    if any(token in normalized for token in _SECTION_TERMS):
        return True
    return len(normalized) <= 40 and any(
        token in normalized for token in _BACK_REFERENCE_TERMS
    )


def category_accepts_entity(category: str | None, entity_type: str | None) -> bool:
    normalized_category = str(category).strip() if category else None
    normalized_type = str(entity_type).strip() if entity_type else None
    if normalized_category is None:
        return True
    return normalized_type == "character" and normalized_category == "人物"


@dataclass
class _Entry:
    generation: int
    turns: deque[ConversationTurn]
    last_accessed: float
    lock: asyncio.Lock
    active_leases: int = 0
    invalidated_reason: str = ""


@dataclass
class ConversationLease:
    conversation_id: UUID | None
    expected_generation: int
    projection: ConversationProjection
    status: MemoryStatus
    _entry: _Entry | None = field(default=None, repr=False)
    _released: bool = field(default=False, repr=False)

    @classmethod
    def disabled(cls) -> "ConversationLease":
        return cls(
            conversation_id=None,
            expected_generation=-1,
            projection=EMPTY_PROJECTION,
            status="disabled",
        )


class ConversationMemoryStore:
    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.monotonic,
        max_sessions: int = MAX_SESSIONS,
        ttl_seconds: float = TTL_SECONDS,
    ) -> None:
        self._clock = clock
        self._max_sessions = max(0, int(max_sessions))
        self._ttl_seconds = float(ttl_seconds)
        self._entries: dict[UUID, _Entry] = {}
        self._guard = asyncio.Lock()

    async def acquire(self, conversation_id: UUID | None) -> ConversationLease:
        if conversation_id is None:
            return ConversationLease.disabled()

        async with self._guard:
            now = self._clock()
            entry = self._entries.get(conversation_id)
            if entry is None:
                self._remove_expired_inactive(now)
                if len(self._entries) >= self._max_sessions:
                    victim = self._oldest_inactive_entry()
                    if victim is None:
                        return ConversationLease.disabled()
                    del self._entries[victim]
                if self._max_sessions == 0:
                    return ConversationLease.disabled()
                entry = _Entry(0, deque(), now, asyncio.Lock())
                self._entries[conversation_id] = entry
            expected_generation = entry.generation
            entry.active_leases += 1

        try:
            await entry.lock.acquire()
        except BaseException:
            async with self._guard:
                entry.active_leases = max(0, entry.active_leases - 1)
                self._remove_empty_entry(conversation_id, entry)
            raise

        async with self._guard:
            now = self._clock()
            stale = (
                self._entries.get(conversation_id) is not entry
                or entry.generation != expected_generation
            )
            expired = False
            if not stale and now - entry.last_accessed > self._ttl_seconds:
                entry.generation += 1
                expected_generation = entry.generation
                entry.turns.clear()
                entry.invalidated_reason = "expired"
                expired = True
            entry.last_accessed = now
            projection = EMPTY_PROJECTION if stale else project_turns(tuple(entry.turns))
            status: MemoryStatus
            if expired:
                status = "expired"
            elif projection.turns:
                status = "hit"
            else:
                status = "new"
            return ConversationLease(
                conversation_id=conversation_id,
                expected_generation=expected_generation,
                projection=projection,
                status=status,
                _entry=entry,
            )

    async def release(
        self,
        lease: ConversationLease,
        turn: ConversationTurn | None = None,
    ) -> bool:
        if lease._released:
            return False
        lease._released = True
        entry = lease._entry
        if entry is None or lease.conversation_id is None:
            return False

        committed = False
        try:
            async with self._guard:
                current = self._entries.get(lease.conversation_id)
                generation_matches = (
                    current is entry
                    and entry.generation == lease.expected_generation
                )
                if generation_matches:
                    entry.last_accessed = self._clock()
                    if turn is not None:
                        entry.turns.append(turn)
                        self._trim_entry(entry)
                        entry.invalidated_reason = ""
                        committed = True
                entry.active_leases = max(0, entry.active_leases - 1)
                self._remove_empty_entry(lease.conversation_id, entry)
        finally:
            if entry.lock.locked():
                entry.lock.release()
        return committed

    async def clear(self, conversation_id: UUID) -> None:
        async with self._guard:
            entry = self._entries.get(conversation_id)
            if entry is None:
                return
            if entry.active_leases == 0:
                del self._entries[conversation_id]
                return
            entry.generation += 1
            entry.turns.clear()
            entry.invalidated_reason = "cleared"
            entry.last_accessed = self._clock()

    def _remove_expired_inactive(self, now: float) -> None:
        expired_ids = [
            conversation_id
            for conversation_id, entry in self._entries.items()
            if entry.active_leases == 0
            and now - entry.last_accessed > self._ttl_seconds
        ]
        for conversation_id in expired_ids:
            del self._entries[conversation_id]

    def _oldest_inactive_entry(self) -> UUID | None:
        inactive = (
            (entry.last_accessed, str(conversation_id), conversation_id)
            for conversation_id, entry in self._entries.items()
            if entry.active_leases == 0
        )
        try:
            return min(inactive)[2]
        except ValueError:
            return None

    def _remove_empty_entry(self, conversation_id: UUID, entry: _Entry) -> None:
        if (
            self._entries.get(conversation_id) is entry
            and entry.active_leases == 0
            and not entry.turns
        ):
            del self._entries[conversation_id]

    @staticmethod
    def _trim_entry(entry: _Entry) -> None:
        while len(entry.turns) > MAX_TURNS:
            entry.turns.popleft()
        while (
            entry.turns
            and sum(_turn_code_points(turn) for turn in entry.turns)
            > MAX_STORED_CODE_POINTS
        ):
            entry.turns.popleft()
