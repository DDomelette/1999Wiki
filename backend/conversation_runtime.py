from __future__ import annotations

import hashlib
import logging
import re
from typing import Any
from uuid import UUID

from backend.schemas import MemoryInfo, normalize_memory_info
from src.rag.conversation import (
    ConversationLease,
    ConversationMemoryStore,
    ConversationTurn,
)


_LOGGER = logging.getLogger(__name__)
_CONVERSATION_PATH_RE = re.compile(
    r"(?P<prefix>/conversations/)"
    r"(?P<uuid>[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-"
    r"[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12})"
)


def _log_failure(operation: str, exc: BaseException) -> None:
    _LOGGER.warning(
        "conversation memory %s failed: %s",
        operation,
        type(exc).__name__,
    )


async def acquire_lease(
    store: ConversationMemoryStore,
    conversation_id: UUID | None,
) -> ConversationLease:
    try:
        return await store.acquire(conversation_id)
    except Exception as exc:
        _log_failure("acquire", exc)
        return ConversationLease.disabled()


async def release_lease(
    store: ConversationMemoryStore,
    lease: ConversationLease,
    turn: ConversationTurn | None,
) -> bool:
    try:
        return await store.release(lease, turn)
    except Exception as exc:
        _log_failure("release", exc)
        return False


async def clear_memory(
    store: ConversationMemoryStore,
    conversation_id: UUID,
) -> bool:
    try:
        await store.clear(conversation_id)
        return True
    except Exception as exc:
        _log_failure("clear", exc)
        return False


def memory_info_for(
    lease: ConversationLease,
    plan: object | None,
) -> MemoryInfo:
    return normalize_memory_info(
        status=lease.status,
        turns_used=len(lease.projection.turns),
        rewrite_mode=getattr(plan, "context_rewrite_mode", "none"),
    )


def redact_conversation_path(path: str) -> str:
    def replace(match: re.Match[str]) -> str:
        canonical = match.group("uuid").lower()
        digest = hashlib.sha256(canonical.encode("ascii")).hexdigest()[:12]
        return f"{match.group('prefix')}sha256:{digest}"

    return _CONVERSATION_PATH_RE.sub(replace, str(path), count=1)


class ConversationPathRedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        args: Any = record.args
        if not isinstance(args, tuple) or len(args) < 3 or not isinstance(args[2], str):
            return True
        redacted = redact_conversation_path(args[2])
        if redacted != args[2]:
            next_args = list(args)
            next_args[2] = redacted
            record.args = tuple(next_args)
        return True


def install_uvicorn_access_log_filter() -> None:
    logger = logging.getLogger("uvicorn.access")
    if any(isinstance(item, ConversationPathRedactionFilter) for item in logger.filters):
        return
    logger.addFilter(ConversationPathRedactionFilter())
