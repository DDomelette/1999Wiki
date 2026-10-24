from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from typing import Any, Mapping

from src.codex_supervisor.contracts import WorkerState


def apply_event(
    state: WorkerState, event: Mapping[str, Any]
) -> WorkerState:
    """Reduce one public Codex JSONL event into durable worker state."""
    ordinal = int(
        event.get("_supervisor_event_ordinal", state.last_event_ordinal + 1)
    )
    if ordinal <= state.last_event_ordinal:
        return state

    event_key = str(
        event.get("_supervisor_event_key")
        or _event_key(state.session_id, ordinal, event)
    )
    updated = replace(
        state,
        last_event_key=event_key,
        last_event_ordinal=ordinal,
    )
    event_type = str(event.get("type", ""))

    if event_type == "thread.started":
        return replace(updated, session_id=_clean(event.get("thread_id")))
    if event_type == "turn.started":
        return updated.with_status("running")
    if event_type == "item.started":
        item = _mapping(event.get("item"))
        if item.get("type") == "command_execution":
            return replace(updated, current_action=_clean(item.get("command")))
        return updated
    if event_type == "item.completed":
        return _apply_completed_item(updated, _mapping(event.get("item")))
    if event_type == "turn.completed":
        usage = _mapping(event.get("usage"))
        updated = replace(
            updated,
            usage=updated.usage.add(
                input_tokens=_integer(usage.get("input_tokens")),
                cached_input_tokens=_integer(
                    usage.get("cached_input_tokens")
                ),
                output_tokens=_integer(usage.get("output_tokens")),
                reasoning_output_tokens=_integer(
                    usage.get("reasoning_output_tokens")
                ),
            ),
        )
        return updated.with_status("completed_pending_review")
    if event_type == "turn.failed":
        message = _public_error(event)
        return replace(
            updated.with_status("failed"),
            blocker=message,
            last_error=message,
        )
    if event_type == "error":
        return replace(updated, last_error=_public_error(event))
    return updated


def _apply_completed_item(
    state: WorkerState, item: Mapping[str, Any]
) -> WorkerState:
    if item.get("type") == "command_execution":
        output = _clean(item.get("aggregated_output"))
        summary = _last_nonempty_line(output)
        return replace(
            state,
            last_exit_code=_optional_integer(item.get("exit_code")),
            tests_summary=summary
            if _looks_like_test(state.current_action)
            else state.tests_summary,
        )
    if item.get("type") in {"agent_message", "message"}:
        summary = _clean(item.get("text") or item.get("content"))
        if summary:
            return replace(state, summary=summary[:1000])
    return state


def _event_key(
    session_id: str | None,
    ordinal: int,
    event: Mapping[str, Any],
) -> str:
    canonical = json.dumps(
        {
            key: value
            for key, value in event.items()
            if not key.startswith("_supervisor_")
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]
    return f"{session_id or 'pending'}:{ordinal}:{digest}"


def _public_error(event: Mapping[str, Any]) -> str:
    error = event.get("error")
    if isinstance(error, Mapping):
        message = error.get("message")
    else:
        message = error or event.get("message")
    clean = _clean(message) or "Codex worker failed"
    return clean.replace("Traceback", "internal error")[:1000]


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _integer(value: Any) -> int:
    return 0 if value is None else int(value)


def _optional_integer(value: Any) -> int | None:
    return None if value is None else int(value)


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _last_nonempty_line(value: str | None) -> str | None:
    if not value:
        return None
    lines = [line.strip() for line in value.splitlines() if line.strip()]
    return lines[-1][:1000] if lines else None


def _looks_like_test(command: str | None) -> bool:
    command_text = (command or "").lower()
    return (
        "pytest" in command_text
        or "unittest" in command_text
        or "tox" in command_text
        or "nox" in command_text
    )
