from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from src.rag.citations import (
    build_source_map,
    format_citation_context,
    normalize_citation_format,
    validate_citations,
    validate_or_repair_answer,
)
from src.rag.chain import RAGChain, _conversation_messages
from src.rag.conversation import build_conversation_turn, project_turns
from src.rag.contracts import SourceRef
from src.rag.prompts import get_rag_prompt
from src.rag.tracing import RequestTrace


def _final_sources():
    return [
        {
            "name": "Fixture A",
            "heading_path": "Section A",
            "entity_type": "fixture",
            "entity_id": "entity-a",
            "child_id": "child-a",
            "parent_id": "parent-a",
            "content": "Evidence A",
        },
        {
            "name": "Fixture B",
            "heading_path": "Section B",
            "entity_type": "fixture",
            "entity_id": "entity-b",
            "child_id": "child-b",
            "parent_id": "parent-b",
            "content": "Evidence B",
        },
    ]


def _source_map() -> tuple[SourceRef, ...]:
    return build_source_map(_final_sources())[1]


def test_source_map_assigns_local_ids_in_final_source_order():
    sources, source_map = build_source_map(_final_sources())

    assert [row["citation_id"] for row in sources] == ["S01", "S02"]
    assert source_map[0].child_id == sources[0]["child_id"]
    with pytest.raises(TypeError):
        sources[0]["citation_id"] = "S99"


def test_citation_context_uses_short_ids_not_display_titles_as_labels():
    sources, source_map = build_source_map(_final_sources())

    context = format_citation_context(sources, source_map)

    assert context.splitlines()[:2] == [
        "[S01] Fixture A / Section A",
        "Evidence A",
    ]
    assert "[Fixture A]" not in context


@pytest.mark.parametrize(
    "answer", ["Conclusion [S99]", "Conclusion [Title]", "Conclusion [S01,S02]"]
)
def test_validator_rejects_unknown_or_noncanonical_labels(answer):
    result = validate_citations(answer, _source_map(), "grounded")

    assert result.valid is False


def test_multiple_sources_use_multiple_independent_tokens():
    result = validate_citations("Conclusion [S01][S02]", _source_map(), "grounded")

    assert result.valid is True
    assert result.used_ids == ("S01", "S02")


def test_grounded_answer_requires_at_least_one_current_source_id():
    result = validate_citations("No citation", _source_map(), "grounded")

    assert result.valid is False
    assert result.missing_required is True


def test_ungrounded_answer_cannot_claim_source_ids():
    result = validate_citations("Free answer [S01]", _source_map(), "ungrounded")

    assert result.valid is False


def test_safe_normalization_only_splits_existing_ids():
    normalized, changed = normalize_citation_format(
        "Conclusion [S01, S02], unknown [S01,S99]",
        frozenset({"S01", "S02"}),
    )

    assert changed is True
    assert normalized == "Conclusion [S01][S02], unknown [S01,S99]"


def test_safe_normalization_preserves_non_citation_brackets_and_keeps_unknown_ids_invalid():
    normalized, changed = normalize_citation_format(
        "灵感是铃鸣的走兽[兽] [S01], label [Fixture A], unknown [S99]",
        frozenset({"S01", "S02"}),
    )

    assert changed is False
    assert normalized == "灵感是铃鸣的走兽[兽] [S01], label [Fixture A], unknown [S99]"
    validation = validate_citations(normalized, _source_map(), "grounded")
    assert validation.valid is False
    assert validation.invalid_ids == ("S99",)
    assert "invalid_citation_label" not in validation.warnings


def test_fullwidth_source_brackets_are_normalized_but_unknown_ids_remain_invalid():
    normalized, changed = normalize_citation_format(
        "Conclusion 【S01】【S02】, unknown 【S99】",
        frozenset({"S01", "S02"}),
    )

    assert changed is True
    assert normalized == "Conclusion [S01][S02], unknown [S99]"
    validation = validate_citations(normalized, _source_map(), "grounded")
    assert validation.valid is False
    assert validation.invalid_ids == ("S99",)


def test_validator_rejects_fullwidth_unknown_id_even_when_ascii_id_is_valid():
    validation = validate_citations(
        "Supported [S01], forged 【S99】",
        _source_map(),
        "grounded",
    )

    assert validation.valid is False


class _RepairSpy:
    def __init__(self, answers: Sequence[str]):
        self.answers = iter(answers)
        self.call_count = 0

    def __call__(self, draft, context, source_map):
        del draft, context, source_map
        self.call_count += 1
        return next(self.answers)


def test_invalid_grounded_answer_is_repaired_at_most_once():
    repair = _RepairSpy(["Repaired [S01]"])

    answer, validation = validate_or_repair_answer(
        draft="Invalid [missing]",
        context="[S01] Evidence A",
        source_map=_source_map(),
        grounding_mode="grounded",
        repair=repair,
    )

    assert answer == "Repaired [S01]"
    assert repair.call_count == 1
    assert validation.valid is True
    assert validation.repair_attempts == 1


def test_repaired_answer_gets_deterministic_combined_id_normalization():
    repair = _RepairSpy(["Repaired [S01, S02]"])

    answer, validation = validate_or_repair_answer(
        draft="Invalid [missing]",
        context="[S01] Evidence A\n[S02] Evidence B",
        source_map=_source_map(),
        grounding_mode="grounded",
        repair=repair,
    )

    assert answer == "Repaired [S01][S02]"
    assert repair.call_count == 1
    assert validation.valid is True
    assert validation.repair_attempts == 1
    assert validation.normalized is True


def test_failed_repair_returns_safe_fallback_not_invalid_draft():
    repair = _RepairSpy(["Still invalid [S99]"])

    answer, validation = validate_or_repair_answer(
        draft="Original invalid [S99]",
        context="[S01] Evidence A",
        source_map=_source_map(),
        grounding_mode="grounded",
        repair=repair,
    )

    assert repair.call_count == 1
    assert validation.valid is True
    assert validation.repair_attempts == 1
    assert "Original invalid" not in answer
    assert "资料不足" in answer
    assert "[S01]" in answer
    assert "citation_safe_fallback" in validation.warnings


def test_repair_exception_closes_error_span_and_returns_safe_fallback():
    trace = RequestTrace()

    def broken_repair(draft, context, source_map):
        del draft, context, source_map
        raise RuntimeError("repair unavailable")

    answer, validation = validate_or_repair_answer(
        draft="Invalid [S99]",
        context="[S01] Evidence A",
        source_map=_source_map(),
        grounding_mode="grounded",
        repair=broken_repair,
        trace=trace,
    )

    repair_span = next(span for span in trace.snapshot().spans if span.name == "citation.repair")
    assert repair_span.status == "error"
    assert repair_span.error_class == "RuntimeError"
    assert validation.valid is True
    assert "资料不足" in answer
    assert "[S01]" in answer
    assert "citation_safe_fallback" in validation.warnings


def test_ungrounded_source_tokens_are_removed_without_repair():
    repair = _RepairSpy(["must not be used"])

    answer, validation = validate_or_repair_answer(
        draft="Free answer [S01]",
        context="",
        source_map=(),
        grounding_mode="ungrounded",
        repair=repair,
    )

    assert answer == "Free answer"
    assert validation.valid is True
    assert "ungrounded_citation_removed" in validation.warnings
    assert repair.call_count == 0


def test_history_projection_marks_every_assistant_turn_and_neutralizes_ids():
    turn = build_conversation_turn(
        original_question="Earlier question",
        standalone_question="Earlier question",
        answer="Earlier answer [S01]",
        entity="fixture",
        entity_type="fixture",
        requested_intents=("general",),
        category=None,
        grounding_mode="grounded",
        completed_at=datetime.now(timezone.utc),
    )

    messages = _conversation_messages(project_turns([turn]))

    assert messages[1].content.startswith("[Historical conversation; not current evidence]")
    assert "[S01]" not in messages[1].content
    assert "[Historical citation expired]" in messages[1].content


class _CitationPlanner:
    def plan(self, question, category=None, conversation=None):
        del category, conversation
        return SimpleNamespace(
            normalized_query=question,
            intent="general",
            secondary_intents=(),
            entity="fixture",
            entity_type="fixture",
            entity_id="fixture-1",
            confidence=1.0,
            route="rag_grounded",
        )


class _CitationRetriever:
    last_route_debug = {}
    last_omitted_actions = []

    def search(self, query, category=None, query_plan=None):
        del query, category, query_plan
        return [{
            "name": "Fixture",
            "category": "fixture",
            "source": "fixture.json",
            "score": 1.0,
            "content": "Current evidence",
            "heading_path": "Fixture > Evidence",
            "child_id": "child-1",
            "parent_id": "parent-1",
            "entity_type": "fixture",
            "entity_id": "fixture-1",
        }]


class _EmptyRegistry:
    def find_for_retrieval(self, plan, sources):
        del plan, sources
        return []


class _SequenceLLM:
    def __init__(self, answers):
        self.answers = iter(answers)
        self.calls = []

    def invoke(self, messages):
        self.calls.append(list(messages))
        return SimpleNamespace(content=next(self.answers))


def _citation_chain(tmp_path, answers):
    cfg = SimpleNamespace(
        llm=SimpleNamespace(api_key=""),
        assets=SimpleNamespace(
            public_base_url="/media",
            bucket_name="reverse1999-assets",
        ),
        huiji=SimpleNamespace(
            enabled=True,
            source_mode="huiji_crawler",
            raw_root=tmp_path / "raw",
            processed_root=tmp_path / "processed",
            build_version="build",
        ),
        paths=SimpleNamespace(project_root=tmp_path),
    )
    chain = RAGChain(cfg, _CitationRetriever())
    chain._query_planner = _CitationPlanner()
    chain._asset_registry = _EmptyRegistry()
    chain._prompt = get_rag_prompt()
    chain._llm = _SequenceLLM(answers)
    return chain


def test_chain_assigns_source_ids_and_repairs_before_committing(tmp_path):
    chain = _citation_chain(tmp_path, ["Invalid [S99]", "Repaired [S01]"])

    result = chain.ask("Question")

    assert result["sources"][0]["citation_id"] == "S01"
    assert result["answer"] == "Repaired [S01]"
    assert result["_citation_validation"].valid is True
    assert result["_citation_validation"].repair_attempts == 1
    assert result["_turn_outcome"] == "grounded"
    assert len(chain._llm.calls) == 2
    assert "[S01] Fixture / Fixture > Evidence\nCurrent evidence" in chain._llm.calls[0][0].content


def test_chain_blocks_invalid_repair_before_memory_commit(tmp_path):
    chain = _citation_chain(tmp_path, ["Invalid [S99]", "Still invalid [S99]"])

    result = chain.ask("Question")

    assert "Invalid [S99]" not in result["answer"]
    assert result["_citation_validation"].valid is True
    assert "citation_safe_fallback" in result["_citation_validation"].warnings
    assert result["_turn_outcome"] == "not_committable"
    assert len(chain._llm.calls) == 2
