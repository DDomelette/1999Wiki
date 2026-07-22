from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from src.huiji_rag.io import write_jsonl
from src.rag.chain import RAGChain
from src.rag.retriever import Retriever, RetrievalExecutionError


class _ForbiddenVectorstore:
    def similarity_search_with_relevance_scores(self, *_args, **_kwargs):
        raise AssertionError("legacy or unplanned vector search was called")


def _cfg(
    tmp_path: Path,
    *,
    enabled: bool = True,
    source_mode: str = "huiji_crawler",
    child_rows: list[dict[str, object]] | None = None,
):
    processed_root = tmp_path / "processed"
    build_root = processed_root / "build"
    if child_rows is not None:
        write_jsonl(build_root / "child_blocks.jsonl", child_rows)
    return SimpleNamespace(
        huiji=SimpleNamespace(
            enabled=enabled,
            source_mode=source_mode,
            raw_root=tmp_path / "raw",
            processed_root=processed_root,
            build_version="build",
        ),
        rag=SimpleNamespace(top_k=4),
        reranker=SimpleNamespace(enabled=False),
        llm=SimpleNamespace(api_key=""),
        paths=SimpleNamespace(project_root=tmp_path),
    )


@pytest.mark.parametrize(
    ("enabled", "source_mode"),
    [(False, "huiji_crawler"), (True, "legacy"), (True, "")],
)
def test_retriever_rejects_unsupported_runtime_source(
    tmp_path: Path,
    enabled: bool,
    source_mode: str,
):
    with pytest.raises(RuntimeError, match="huiji_crawler"):
        Retriever(
            _cfg(
                tmp_path,
                enabled=enabled,
                source_mode=source_mode,
                child_rows=[{"child_id": "child:1", "text": "content"}],
            ),
            _ForbiddenVectorstore(),
        )


@pytest.mark.parametrize("child_rows", [None, []])
def test_retriever_fails_closed_when_required_huiji_children_are_unavailable(
    tmp_path: Path,
    child_rows: list[dict[str, object]] | None,
):
    with pytest.raises(RuntimeError, match="Huiji child artifact"):
        Retriever(_cfg(tmp_path, child_rows=child_rows), _ForbiddenVectorstore())


def test_retriever_requires_a_query_plan_and_never_enters_unplanned_vector_search(
    tmp_path: Path,
):
    retriever = Retriever(
        _cfg(
            tmp_path,
            child_rows=[
                {
                    "child_id": "char:1/profile:0",
                    "parent_id": "char:1/profile",
                    "entity_id": "1",
                    "entity_name": "Character",
                    "entity_type": "character",
                    "text": "Profile",
                }
            ],
        ),
        _ForbiddenVectorstore(),
    )

    with pytest.raises(RetrievalExecutionError, match="retrieval.plan"):
        retriever.search("Character")


@pytest.mark.parametrize(
    ("enabled", "source_mode"),
    [(False, "huiji_crawler"), (True, "legacy")],
)
def test_chain_rejects_unsupported_runtime_source(
    tmp_path: Path,
    enabled: bool,
    source_mode: str,
):
    with pytest.raises(RuntimeError, match="huiji_crawler"):
        RAGChain(
            _cfg(
                tmp_path,
                enabled=enabled,
                source_mode=source_mode,
                child_rows=[{"child_id": "child:1", "text": "content"}],
            ),
            SimpleNamespace(),
        )
