from __future__ import annotations

import ast
import inspect
from pathlib import Path

from src.huiji_rag.build.contracts import VoiceBindingInput
from src.huiji_rag.build.voice_stage import VoiceBindingStage
from src.huiji_rag.models import BindingStatus, ResourceRow, VoiceSourceRow
from src.huiji_rag.voice_binding import bind_voice_row, index_voice_resources
import src.huiji_rag.builder as evb_builder_module


def _source(language: str, source_id: str) -> VoiceSourceRow:
    return VoiceSourceRow(
        event_name="Hello",
        language=language,
        source_id=source_id,
        entity_id="1001",
        parent_id="char:1001/voice",
        child_id="char:1001/voice/event-hello",
        transcript="Hello",
    )


def _resource(language: str, prefix: str, digest: str) -> ResourceRow:
    return ResourceRow(
        filename=f"{prefix}_Hello.mp3",
        language=language,
        sha1=digest * 40,
        sha256=digest * 64,
        resource_id=f"resource:{digest}",
    )


def test_stage_and_compatibility_facade_produce_identical_exact_bindings() -> None:
    sources = (_source("zh-cn", "voice:zh"), _source("en-us", "voice:en"))
    resources = (_resource("zh", "Zh", "a"), _resource("en", "En", "b"))

    stage = VoiceBindingStage().run(
        VoiceBindingInput(source_rows=sources, resource_rows=resources)
    )
    facade_index = index_voice_resources(resources)
    facade_rows = tuple(bind_voice_row(source, facade_index) for source in sources)

    assert stage.binding_rows == facade_rows
    assert all(row.status is BindingStatus.EXACT for row in stage.binding_rows)
    assert stage.conflict_result.runtime_ids == ("voice:en", "voice:zh")
    assert stage.event_count == 1
    assert stage.language_count == 2
    assert stage.owner_count == 1
    assert stage.skin_count == 0
    assert stage.status_counts == {"exact": 2}
    assert stage.counts_by_language == {"en": 1, "zh": 1}
    assert stage.counts_by_event == {"char:1001/voice/event-hello": 2}
    assert stage.counts_by_owner == {"1001": 2}
    assert stage.exact_bindings == stage.binding_rows
    assert stage.quarantined_bindings == ()
    assert stage.ready_gate_blocked is False
    assert stage.binding_fingerprint_sha256 == stage.output_fingerprint_sha256
    assert len(stage.input_fingerprint_sha256) == 64
    assert len(stage.binding_fingerprint_sha256) == 64


def test_stage_fingerprint_is_deterministic_for_identical_input() -> None:
    request = VoiceBindingInput(
        source_rows=(_source("en", "voice:en"),),
        resource_rows=(_resource("en", "En", "b"),),
    )
    first = VoiceBindingStage().run(request)
    second = VoiceBindingStage().run(request)
    assert first == second


def test_text_only_shortfall_is_reported_without_blocking_candidate_readiness() -> None:
    result = VoiceBindingStage().run(
        VoiceBindingInput(
            source_rows=(_source("zh-hant", "voice:tw"),),
            resource_rows=(_resource("zh", "Zh", "a"),),
        )
    )

    assert result.status_counts == {"shortfall": 1}
    assert result.exact_bindings == ()
    assert result.ready_gate_blocked is False
    assert result.root_causes_by_source["voice:tw"] == ("missing_exact_resource",)


def test_stage_exposes_quarantine_occurrences_and_conflict_closure() -> None:
    sources = (
        _source("en", "voice:a"),
        VoiceSourceRow(
            event_name="Other",
            language="en",
            source_id="voice:b",
            entity_id="1002",
            parent_id="char:1002/voice",
            child_id="char:1002/voice/event-other",
            transcript="Other",
        ),
    )
    resources = (
        _resource("en", "En", "a"),
        ResourceRow(
            filename="En_Other.mp3",
            language="en",
            sha1="b" * 40,
            sha256="a" * 64,
            resource_id="resource:b",
        ),
    )

    result = VoiceBindingStage().run(
        VoiceBindingInput(source_rows=sources, resource_rows=resources)
    )

    assert result.exact_bindings == ()
    assert {row.source_id for row in result.quarantined_bindings} == {
        "voice:a",
        "voice:b",
    }
    assert result.status_counts == {"quarantined": 2}
    assert result.status_by_source == {
        "voice:a": "quarantined",
        "voice:b": "quarantined",
    }
    assert all(
        "cross_child_sha" in result.root_causes_by_source[source_id]
        for source_id in ("voice:a", "voice:b")
    )
    assert result.conflict_closure.visited_ids == ("voice:a", "voice:b")
    assert result.ready_gate_blocked is False


def test_fatal_binding_still_blocks_candidate_readiness() -> None:
    result = VoiceBindingStage().run(
        VoiceBindingInput(
            source_rows=(_source("en", "voice:fatal"),),
            resource_rows=(
                _resource("en", "En", "a"),
                _resource("en", "En", "b"),
            ),
        )
    )

    assert result.status_counts == {"fatal": 1}
    assert result.fatal_bindings == result.binding_rows
    assert result.ready_gate_blocked is True


def test_voice_matching_function_definitions_exist_only_in_voice_stage() -> None:
    root = Path("src/huiji_rag")
    definitions: dict[str, list[str]] = {"bind_voice_row": [], "index_voice_resources": []}
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in definitions:
                definitions[node.name].append(path.as_posix())

    assert definitions == {
        "bind_voice_row": ["src/huiji_rag/build/voice_stage.py"],
        "index_voice_resources": ["src/huiji_rag/build/voice_stage.py"],
    }
    builder_source = inspect.getsource(evb_builder_module.EvbBuilder)
    assert "VoiceBindingStage().run" in builder_source
    assert "bind_voice_row" not in builder_source
