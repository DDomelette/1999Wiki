from __future__ import annotations

import pytest

from src.rag.citations import (
    SourceIdentityCollision,
    build_global_source_map,
    validate_global_citations,
)
from src.rag.contracts import BranchResult, CitationValidation


def _source(child_id: str, *, sha: str = "a" * 64):
    return {
        "entity_type": "topic",
        "entity_id": "topic:storm",
        "child_id": child_id,
        "parent_id": f"page:{child_id}",
        "name": child_id,
        "heading_path": "定义",
        "content": f"content:{sha}",
        "source_refs": [{
            "site": "huiji",
            "title": child_id,
            "revid": "1",
            "content_sha256": sha,
        }],
    }


def _branch(subtask_id: str, answer: str, source_ids: tuple[str, ...]):
    return BranchResult(
        subtask_id=subtask_id,
        order=int(subtask_id[1:]),
        task_type="knowledge_base",
        query=subtask_id,
        effective_route="rag_grounded",
        retrieval_outcome="sufficient",
        grounding_mode="grounded",
        status="succeeded",
        answer=answer,
        source_ids=source_ids,
        entity_ref=None,
        citation_validation=CitationValidation(valid=True, used_ids=source_ids),
        public_error="",
    )


def test_two_kb_branches_share_one_global_sequence():
    allocation = build_global_source_map([
        ("T01", [_source("child-a"), _source("shared")]),
        ("T02", [_source("child-b"), _source("shared")]),
    ])

    assert [row["citation_id"] for row in allocation.sources] == ["S01", "S02", "S03"]
    assert allocation.branch_source_ids["T01"] == ("S01", "S02")
    assert allocation.branch_source_ids["T02"] == ("S03", "S02")


def test_same_identity_with_different_content_hash_is_rejected():
    with pytest.raises(SourceIdentityCollision):
        build_global_source_map([
            ("T01", [_source("shared", sha="a" * 64)]),
            ("T02", [_source("shared", sha="b" * 64)]),
        ])


def test_global_validation_enforces_branch_whitelists_and_ungrounded_cleanup():
    allocation = build_global_source_map([
        ("T01", [_source("child-a")]),
        ("T02", [_source("child-b")]),
    ])

    valid = validate_global_citations(
        (
            _branch("T01", "A [S01]", ("S01",)),
            _branch("T02", "B [S02]", ("S02",)),
        ),
        allocation,
    )
    assert valid.valid is True

    invalid = validate_global_citations(
        (
            _branch("T01", "A [S02]", ("S01",)),
            _branch("T02", "B [S02]", ("S02",)),
        ),
        allocation,
    )
    assert invalid.valid is False
    assert invalid.invalid_ids == ("S02",)
