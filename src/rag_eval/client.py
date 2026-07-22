"""Bounded HTTP/SSE collector for real full-chain evaluation."""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Iterable, Mapping, Sequence

import requests

from src.rag_eval.contracts import EvalCase


MAX_JSON_BYTES = 4 * 1024 * 1024
MAX_SSE_BYTES = 16 * 1024 * 1024
MAX_VOICE_PAGES = 512


class ClientProtocolError(ValueError):
    """Raised for an unsafe or malformed backend protocol response."""


@dataclass(frozen=True)
class TimingObservation:
    started_at_utc: str
    retrieval_ms: float | None
    ttft_ms: float | None
    total_ms: float
    packet_ready_ms: float | None = None
    model_first_token_ms: float | None = None
    validated_ready_ms: float | None = None
    visible_first_token_ms: float | None = None
    completed_ms: float | None = None
    stage_ms: Mapping[str, float] = field(default_factory=dict)
    error_stages: tuple[str, ...] = ()
    warning: str = ""


@dataclass(frozen=True)
class SSETranscript:
    success: bool
    sources_payload: Mapping[str, object] = field(default_factory=dict)
    tokens: tuple[str, ...] = ()
    done_payload: Mapping[str, object] = field(default_factory=dict)
    answer: str = ""
    error: str = ""
    event_names: tuple[str, ...] = ()


@dataclass(frozen=True)
class ObservedExchange:
    case_id: str
    endpoint: str
    success: bool
    status_code: int | None
    route: Mapping[str, object]
    sources: tuple[Mapping[str, object], ...]
    media: tuple[Mapping[str, object], ...]
    media_panels: tuple[Mapping[str, object], ...]
    failure_actions: tuple[Mapping[str, object], ...]
    answer: str
    timing: TimingObservation
    error: str = ""
    raw: Mapping[str, object] = field(default_factory=dict)
    voice_pages: tuple[Mapping[str, object], ...] = ()
    entity_ref: Mapping[str, object] = field(default_factory=dict)
    ownership_key: tuple[str, str] | None = None
    semantic_intents: tuple[str, ...] = ()
    source_map: Mapping[str, Mapping[str, object]] = field(default_factory=dict)
    grounding_mode: str = "none"
    route_decision: Mapping[str, object] = field(default_factory=dict)
    omitted_actions: tuple[Mapping[str, object], ...] = ()
    memory: Mapping[str, object] = field(default_factory=dict)
    stage_trace: Mapping[str, object] = field(default_factory=dict)


def parse_sse_lines(
    lines: Iterable[str | bytes],
    *,
    on_event: Callable[[str, Mapping[str, object]], None] | None = None,
    max_bytes: int = MAX_SSE_BYTES,
) -> SSETranscript:
    event_name = ""
    data_parts: list[str] = []
    seen_sources = False
    sources_payload: Mapping[str, object] = {}
    done_payload: Mapping[str, object] = {}
    tokens: list[str] = []
    error = ""
    names: list[str] = []
    byte_count = 0

    def flush() -> None:
        nonlocal event_name, data_parts, seen_sources, sources_payload, done_payload, error
        if not event_name and not data_parts:
            return
        if not event_name:
            raise ClientProtocolError("SSE event is missing event name")
        raw_data = "\n".join(data_parts)
        try:
            payload = json.loads(raw_data) if raw_data else {}
        except json.JSONDecodeError as exc:
            raise ClientProtocolError(f"SSE {event_name} data is not valid JSON") from exc
        if not isinstance(payload, dict):
            raise ClientProtocolError(f"SSE {event_name} data is not a JSON object")
        if event_name == "sources":
            if seen_sources:
                raise ClientProtocolError("SSE contains duplicate sources event")
            seen_sources = True
            sources_payload = payload
        elif event_name == "token":
            if not seen_sources:
                raise ClientProtocolError("SSE token appeared before sources")
            token = payload.get("token")
            if not isinstance(token, str):
                raise ClientProtocolError("SSE token is not a string")
            if token:
                tokens.append(token)
        elif event_name == "done":
            if not seen_sources:
                raise ClientProtocolError("SSE done appeared before sources")
            done_payload = payload
        elif event_name == "error":
            error = str(payload.get("message") or "unknown SSE error")
        names.append(event_name)
        if on_event:
            on_event(event_name, payload)
        event_name = ""
        data_parts = []

    for line in lines:
        text = line.decode("utf-8") if isinstance(line, bytes) else line
        byte_count += len(text.encode("utf-8")) + 1
        if byte_count > max_bytes:
            raise ClientProtocolError("SSE response exceeded byte limit")
        if text == "":
            flush()
            continue
        if text.startswith(":"):
            continue
        if text.startswith("event:"):
            event_name = text[6:].strip()
        elif text.startswith("data:"):
            data_parts.append(text[5:].lstrip())
    flush()

    if not done_payload and not error:
        raise ClientProtocolError("SSE stream ended without done or error")
    answer = str(done_payload.get("answer") or "") if done_payload else ""
    return SSETranscript(
        success=bool(done_payload) and not error,
        sources_payload=sources_payload,
        tokens=tuple(tokens),
        done_payload=done_payload,
        answer=answer,
        error=error,
        event_names=tuple(names),
    )


class RagEvalClient:
    def __init__(
        self,
        base_url: str,
        *,
        session: requests.Session | object | None = None,
        timeout: tuple[float, float] = (5.0, 60.0),
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.session = session or requests.Session()
        self.session.trust_env = False
        self.timeout = timeout
        self.clock = clock

    def ask(
        self,
        case: EvalCase,
        *,
        conversation_id: str | None = None,
    ) -> ObservedExchange:
        started_at = _utc_now()
        start = self.clock()
        status_code: int | None = None
        try:
            body = _request_body(case, conversation_id)
            response = self.session.post(
                f"{self.base_url}/ask",
                json=body,
                timeout=self.timeout,
            )
            status_code = int(response.status_code)
            response.raise_for_status()
            if len(response.content) > MAX_JSON_BYTES:
                raise ClientProtocolError("JSON response exceeded byte limit")
            payload = response.json()
            if not isinstance(payload, dict):
                raise ClientProtocolError("ask response is not a JSON object")
            total_ms = max(0.0, (self.clock() - start) * 1000.0)
            return _exchange_from_payload(
                case.case_id,
                "/ask",
                payload,
                status_code,
                TimingObservation(started_at, None, None, total_ms),
            )
        except Exception as error:
            total_ms = max(0.0, (self.clock() - start) * 1000.0)
            return _failed_exchange(
                case.case_id,
                "/ask",
                status_code,
                TimingObservation(started_at, None, None, total_ms),
                str(error),
            )

    def ask_stream(
        self,
        case: EvalCase,
        *,
        conversation_id: str | None = None,
    ) -> ObservedExchange:
        started_at = _utc_now()
        start = self.clock()
        status_code: int | None = None
        packet_ready_ms: float | None = None
        ttft_ms: float | None = None

        def on_event(event: str, payload: Mapping[str, object]) -> None:
            nonlocal packet_ready_ms, ttft_ms
            now = self.clock()
            if event == "sources" and packet_ready_ms is None:
                packet_ready_ms = max(0.0, (now - start) * 1000.0)
            if event == "token" and payload.get("token") and ttft_ms is None:
                ttft_ms = max(0.0, (now - start) * 1000.0)

        try:
            body = _request_body(case, conversation_id)
            response = self.session.post(
                f"{self.base_url}/ask/stream",
                json=body,
                timeout=self.timeout,
                stream=True,
                headers={"Accept": "text/event-stream"},
            )
            status_code = int(response.status_code)
            response.raise_for_status()
            transcript = parse_sse_lines(
                response.iter_lines(decode_unicode=True, chunk_size=1),
                on_event=on_event,
            )
            total_ms = max(0.0, (self.clock() - start) * 1000.0)
            timing = TimingObservation(
                started_at,
                None,
                ttft_ms,
                total_ms,
                packet_ready_ms=packet_ready_ms,
            )
            if not transcript.success:
                return _failed_exchange(
                    case.case_id,
                    "/ask/stream",
                    status_code,
                    timing,
                    transcript.error or "SSE stream failed",
                    raw={
                        "sources_event": dict(transcript.sources_payload),
                        "events": list(transcript.event_names),
                    },
                )
            combined = dict(transcript.done_payload)
            for key, value in transcript.sources_payload.items():
                combined.setdefault(key, value)
            combined["answer"] = transcript.answer
            return _exchange_from_payload(
                case.case_id,
                "/ask/stream",
                combined,
                status_code,
                timing,
                raw={
                    **combined,
                    "sources_event": dict(transcript.sources_payload),
                    "done_event": dict(transcript.done_payload),
                    "events": list(transcript.event_names),
                },
            )
        except Exception as error:
            total_ms = max(0.0, (self.clock() - start) * 1000.0)
            return _failed_exchange(
                case.case_id,
                "/ask/stream",
                status_code,
                TimingObservation(
                    started_at,
                    None,
                    ttft_ms,
                    total_ms,
                    packet_ready_ms=packet_ready_ms,
                ),
                str(error),
            )

    def clear_conversation(self, conversation_id: str) -> int:
        response = self.session.delete(
            f"{self.base_url}/conversations/{conversation_id}",
            timeout=self.timeout,
        )
        response.raise_for_status()
        status_code = int(response.status_code)
        if status_code != 204:
            raise ClientProtocolError(
                f"conversation clear returned HTTP {status_code}, expected 204"
            )
        return status_code

    def cancel_stream_after_first_token(
        self,
        case: EvalCase,
        *,
        conversation_id: str,
    ) -> tuple[str, ...]:
        response = self.session.post(
            f"{self.base_url}/ask/stream",
            json={
                "question": case.query,
                "conversation_id": conversation_id,
            },
            timeout=self.timeout,
            stream=True,
            headers={"Accept": "text/event-stream"},
        )
        names: list[str] = []
        event_name = ""
        data_parts: list[str] = []
        byte_count = 0

        def flush() -> bool:
            nonlocal event_name, data_parts
            if not event_name and not data_parts:
                return False
            if not event_name:
                raise ClientProtocolError("SSE event is missing event name")
            raw_data = "\n".join(data_parts)
            try:
                payload = json.loads(raw_data) if raw_data else {}
            except json.JSONDecodeError as exc:
                raise ClientProtocolError(
                    f"SSE {event_name} data is not valid JSON"
                ) from exc
            if not isinstance(payload, dict):
                raise ClientProtocolError(
                    f"SSE {event_name} data is not a JSON object"
                )
            names.append(event_name)
            should_stop = event_name == "token" and bool(payload.get("token"))
            event_name = ""
            data_parts = []
            return should_stop

        try:
            response.raise_for_status()
            for line in response.iter_lines(decode_unicode=True, chunk_size=1):
                text = line.decode("utf-8") if isinstance(line, bytes) else line
                byte_count += len(text.encode("utf-8")) + 1
                if byte_count > MAX_SSE_BYTES:
                    raise ClientProtocolError("SSE response exceeded byte limit")
                if text == "":
                    if flush():
                        return tuple(names)
                    continue
                if text.startswith(":"):
                    continue
                if text.startswith("event:"):
                    event_name = text[6:].strip()
                elif text.startswith("data:"):
                    data_parts.append(text[5:].lstrip())
            if flush():
                return tuple(names)
            raise ClientProtocolError("SSE stream ended before first non-empty token")
        finally:
            close = getattr(response, "close", None)
            if callable(close):
                close()

    def collect_voice_pages(
        self,
        media_panels: Sequence[Mapping[str, object]],
    ) -> tuple[Mapping[str, object], ...]:
        pages = [dict(panel) for panel in media_panels if panel.get("type") == "voice"]
        if not pages:
            return ()
        seen_cursors: set[str] = set()
        current = pages[-1]
        while bool(current.get("has_more")):
            if len(pages) >= MAX_VOICE_PAGES:
                raise ClientProtocolError("voice pagination exceeded page limit")
            cursor = str(current.get("next_cursor") or "")
            if not _safe_cursor(cursor):
                raise ClientProtocolError("unsafe voice cursor")
            if cursor in seen_cursors:
                raise ClientProtocolError("repeated voice cursor")
            seen_cursors.add(cursor)
            response = self.session.get(
                f"{self.base_url}/api/media/voice/page",
                params={"cursor": cursor},
                timeout=self.timeout,
            )
            response.raise_for_status()
            if len(response.content) > MAX_JSON_BYTES:
                raise ClientProtocolError("voice page exceeded byte limit")
            payload = response.json()
            if not isinstance(payload, dict):
                raise ClientProtocolError("voice page is not a JSON object")
            if payload.get("type") != "voice" or not isinstance(payload.get("lines"), list):
                raise ClientProtocolError("voice page has invalid shape")
            current = payload
            pages.append(payload)
        return tuple(pages)


def _exchange_from_payload(
    case_id: str,
    endpoint: str,
    payload: Mapping[str, object],
    status_code: int,
    timing: TimingObservation,
    *,
    raw: Mapping[str, object] | None = None,
) -> ObservedExchange:
    answer = payload.get("answer")
    if not isinstance(answer, str):
        raise ClientProtocolError("response answer is not a string")
    route = _mapping(payload.get("route"))
    sources = _mapping_tuple(payload.get("sources"))
    media = _mapping_tuple(payload.get("media"))
    media_panels = _mapping_tuple(payload.get("media_panels"))
    timing_payload = _mapping(payload.get("timing"))
    observed_timing = _merge_server_timing(timing, timing_payload)
    source_map = _source_map(sources)
    ownership_key = _packet_ownership_key(route, sources, media, media_panels)
    entity_ref = _entity_ref(route, sources, ownership_key)
    semantic_intents = _string_tuple(
        route.get("semantic_intents") or route.get("requested_intents")
    )
    route_decision = {
        key: route[key]
        for key in (
            "proposed_route",
            "effective_route",
            "retrieval_outcome",
            "route_reason",
        )
        if key in route
    }
    return ObservedExchange(
        case_id=case_id,
        endpoint=endpoint,
        success=True,
        status_code=status_code,
        route=route,
        sources=sources,
        media=media,
        media_panels=media_panels,
        failure_actions=_mapping_tuple(payload.get("failure_actions")),
        answer=answer,
        timing=observed_timing,
        raw=raw or dict(payload),
        entity_ref=entity_ref,
        ownership_key=ownership_key,
        semantic_intents=semantic_intents,
        source_map=source_map,
        grounding_mode=str(payload.get("grounding_mode") or "none"),
        route_decision=route_decision,
        omitted_actions=_mapping_tuple(payload.get("omitted_actions")),
        memory=_mapping(payload.get("memory")),
        stage_trace=timing_payload,
    )


def _failed_exchange(
    case_id: str,
    endpoint: str,
    status_code: int | None,
    timing: TimingObservation,
    error: str,
    *,
    raw: Mapping[str, object] | None = None,
) -> ObservedExchange:
    return ObservedExchange(
        case_id=case_id,
        endpoint=endpoint,
        success=False,
        status_code=status_code,
        route={},
        sources=(),
        media=(),
        media_panels=(),
        failure_actions=(),
        answer="",
        timing=timing,
        error=error,
        raw=raw or {},
    )


def _mapping(value: object) -> Mapping[str, object]:
    return dict(value) if isinstance(value, Mapping) else {}


def _mapping_tuple(value: object) -> tuple[Mapping[str, object], ...]:
    if not isinstance(value, list):
        return ()
    if not all(isinstance(item, Mapping) for item in value):
        raise ClientProtocolError("response list contains a non-object item")
    return tuple(dict(item) for item in value)


def _request_body(case: EvalCase, conversation_id: str | None) -> dict[str, object]:
    body: dict[str, object] = {"question": case.query}
    if conversation_id is not None:
        body["conversation_id"] = conversation_id
    if case.route_options:
        body["route_options"] = dict(case.route_options)
    if case.action_payload:
        body["action_payload"] = dict(case.action_payload)
    return body


def _merge_server_timing(
    external: TimingObservation,
    payload: Mapping[str, object],
) -> TimingObservation:
    stage_raw = payload.get("stage_ms")
    stage_ms = {
        str(key): float(value)
        for key, value in (stage_raw.items() if isinstance(stage_raw, Mapping) else ())
        if isinstance(value, (int, float)) and not isinstance(value, bool) and float(value) >= 0
    }
    retrieval_values = [
        value for key, value in stage_ms.items() if key.startswith("retrieval.")
    ]
    retrieval_ms = sum(retrieval_values) if retrieval_values else external.retrieval_ms
    errors = payload.get("error_stages")
    return TimingObservation(
        started_at_utc=external.started_at_utc,
        retrieval_ms=retrieval_ms,
        ttft_ms=external.ttft_ms,
        total_ms=external.total_ms,
        packet_ready_ms=external.packet_ready_ms,
        model_first_token_ms=_optional_number(payload.get("model_first_token_ms")),
        validated_ready_ms=_optional_number(payload.get("validated_ready_ms")),
        visible_first_token_ms=_optional_number(payload.get("visible_first_token_ms")),
        completed_ms=_optional_number(payload.get("completed_ms")),
        stage_ms=stage_ms,
        error_stages=_string_tuple(errors),
        warning=str(payload.get("warning") or ""),
    )


def _source_map(
    sources: Sequence[Mapping[str, object]],
) -> Mapping[str, Mapping[str, object]]:
    output: dict[str, Mapping[str, object]] = {}
    for source in sources:
        citation_id = str(source.get("citation_id") or "")
        if not citation_id:
            continue
        if citation_id in output:
            raise ClientProtocolError(f"duplicate source citation_id: {citation_id}")
        output[citation_id] = {
            key: source.get(key)
            for key in (
                "citation_id",
                "entity_type",
                "entity_id",
                "child_id",
                "parent_id",
                "name",
                "heading_path",
            )
        }
    return output


def _packet_ownership_key(
    route: Mapping[str, object],
    sources: Sequence[Mapping[str, object]],
    media: Sequence[Mapping[str, object]],
    panels: Sequence[Mapping[str, object]],
) -> tuple[str, str] | None:
    direct = _ownership_key(route)
    if direct is not None:
        return direct
    keys = {
        key
        for item in (*sources, *media, *_panel_items(panels))
        if (key := _ownership_key(item)) is not None
    }
    return next(iter(keys)) if len(keys) == 1 else None


def _entity_ref(
    route: Mapping[str, object],
    sources: Sequence[Mapping[str, object]],
    owner: tuple[str, str] | None,
) -> Mapping[str, object]:
    if owner is None:
        return {}
    name = str(route.get("entity") or "")
    if not name:
        name = next((str(item.get("name") or "") for item in sources if item.get("name")), "")
    return {"entity_type": owner[0], "entity_id": owner[1], "entity_name": name}


def _ownership_key(value: Mapping[str, object]) -> tuple[str, str] | None:
    entity_type = str(value.get("entity_type") or "")
    entity_id = str(value.get("entity_id") or "")
    return (entity_type, entity_id) if entity_type and entity_id else None


def _panel_items(
    panels: Sequence[Mapping[str, object]],
) -> tuple[Mapping[str, object], ...]:
    output: list[Mapping[str, object]] = []
    for panel in panels:
        for line in panel.get("lines") or ():
            if isinstance(line, Mapping):
                output.extend(item for item in line.get("variants") or () if isinstance(item, Mapping))
        output.extend(item for item in panel.get("items") or () if isinstance(item, Mapping))
    return tuple(output)


def _string_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(dict.fromkeys(str(item) for item in value if str(item)))


def _optional_number(value: object) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool) and float(value) >= 0:
        return float(value)
    return None


def _safe_cursor(value: str) -> bool:
    if not value or len(value) > 8192:
        return False
    lowered = value.lower()
    return not (
        "file:" in lowered
        or "\\" in value
        or "../" in value
        or re.search(r"(?:^|[^a-z0-9])[a-z]:/", lowered)
    )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
