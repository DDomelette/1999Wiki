"""板块元数据接口测试。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture
def client(monkeypatch, tmp_path):
    """构造带 mock 向量库的客户端。"""
    from backend import main as main_mod
    from tests.conftest import MockVectorstore

    # 重置单例与 _state
    main_mod._state = {"vs": None, "retriever": None, "chain": None, "loaded": False}
    monkeypatch.setattr(main_mod, "_ensure_loaded", lambda: None)
    monkeypatch.setattr(main_mod, "_state", {
        "vs": MockVectorstore(doc_counts={"人物": 105, "心相": 90, "剧情": 46,
                                          "世界": 1, "阵营": 4, "日历": 506}),
        "retriever": None, "chain": None, "loaded": True,
    })
    return TestClient(main_mod.app)


def test_categories_returns_six_categories(client):
    """返回 6 类,每类含 key/title/subtitle/description/doc_count/cover_prompt。"""
    resp = client.get("/categories")
    assert resp.status_code == 200
    data = resp.json()
    cats = data["categories"]
    assert len(cats) == 6
    keys = [c["key"] for c in cats]
    assert keys == ["人物", "心相", "剧情", "世界", "阵营", "日历"]
    for c in cats:
        assert c["title"]
        assert c["subtitle"]
        assert c["description"]
        assert isinstance(c["doc_count"], int)
        assert c["doc_count"] > 0
        assert c["cover_prompt"]
    # 验证 doc_count 来自 mock
    person = next(c for c in cats if c["key"] == "人物")
    assert person["doc_count"] == 105


def test_category_docs_returns_snippets(client):
    """/category/人物/docs 返回 name/source/snippet。"""
    resp = client.get("/category/%E4%BA%BA%E7%89%A9/docs?limit=5")
    assert resp.status_code == 200
    data = resp.json()
    assert data["key"] == "人物"
    assert isinstance(data["docs"], list)
    for d in data["docs"]:
        assert d["name"]
        assert d["source"]
        assert d["snippet"]
        assert len(d["snippet"]) <= 200


def test_categories_handles_vs_none(monkeypatch):
    """vs=None 时 /categories 返回 6 类但 doc_count 全为 0。"""
    from backend import main as main_mod
    main_mod._state = {"vs": None, "retriever": None, "chain": None, "loaded": True}
    monkeypatch.setattr(main_mod, "_ensure_loaded", lambda: None)
    client = TestClient(main_mod.app)
    resp = client.get("/categories")
    assert resp.status_code == 200
    cats = resp.json()["categories"]
    assert len(cats) == 6
    for c in cats:
        assert c["doc_count"] == 0


def test_category_docs_nonexistent_key_returns_empty(monkeypatch):
    """不存在的 category key 返回 docs=[]。"""
    from backend import main as main_mod
    from tests.conftest import MockVectorstore
    main_mod._state = {
        "vs": MockVectorstore(doc_counts={"人物": 2}),
        "retriever": None, "chain": None, "loaded": True,
    }
    monkeypatch.setattr(main_mod, "_ensure_loaded", lambda: None)
    client = TestClient(main_mod.app)
    resp = client.get("/category/不存在的分类/docs")
    assert resp.status_code == 200
    data = resp.json()
    assert data["key"] == "不存在的分类"
    assert data["docs"] == []


def test_categories_doc_count_works_when_count_where_unsupported(client):
    """真实 ChromaDB 的 count() 不支持 where 参数(抛 TypeError)。

    /categories 应改用 get(where=, include=[]) + len(ids) 统计,
    而非依赖 count(where=) 导致 doc_count 全为 0。
    """
    resp = client.get("/categories")
    assert resp.status_code == 200
    cats = resp.json()["categories"]
    # MockVectorstore 的 count(where=) 已抛 TypeError,若端点仍用 count
    # 则 doc_count 全为 0;此处断言 doc_count 正确来自 get fallback
    person = next(c for c in cats if c["key"] == "人物")
    assert person["doc_count"] == 105
    calendar = next(c for c in cats if c["key"] == "日历")
    assert calendar["doc_count"] == 506


class _MilvusIterator:
    def __init__(self, batches):
        self._batches = iter(batches)
        self.closed = False

    def next(self):
        value = next(self._batches)
        if isinstance(value, BaseException):
            raise value
        return value

    def close(self):
        self.closed = True


class _MilvusClient:
    def __init__(self, iterator):
        self.iterator = iterator
        self.iterator_calls = []
        self.query_called = False

    def query_iterator(self, **kwargs):
        self.iterator_calls.append(kwargs)
        return self.iterator

    def query(self, **_kwargs):
        self.query_called = True
        raise AssertionError("legacy query() must not be used for Milvus category counts")


class _MilvusVectorstore:
    collection_name = "wiki_chunks"

    def __init__(self, client):
        self.client = client


def test_milvus_category_count_iterates_all_batches_and_escapes_filter():
    from backend import main as main_mod

    iterator = _MilvusIterator([[{"id": "1"}, {"id": "2"}], [{"id": "3"}], []])
    client = _MilvusClient(iterator)
    category = 'path\\part"quoted'

    assert main_mod._count_by_category(_MilvusVectorstore(client), category) == 3
    assert client.iterator_calls == [{
        "collection_name": "wiki_chunks",
        "batch_size": 1000,
        "limit": -1,
        "filter": 'category == "path\\\\part\\"quoted"',
        "output_fields": ["id"],
    }]
    assert client.query_called is False
    assert iterator.closed is True


def test_milvus_category_count_closes_iterator_after_empty_first_batch():
    from backend import main as main_mod

    iterator = _MilvusIterator([[]])
    client = _MilvusClient(iterator)

    assert main_mod._count_by_category(_MilvusVectorstore(client), "人物") == 0
    assert client.query_called is False
    assert iterator.closed is True


def test_milvus_category_count_logs_and_propagates_iterator_errors(caplog):
    from backend import main as main_mod

    iterator = _MilvusIterator([RuntimeError("Milvus is unavailable")])
    client = _MilvusClient(iterator)

    with pytest.raises(RuntimeError, match="Milvus is unavailable"):
        main_mod._count_by_category(_MilvusVectorstore(client), "人物")

    assert client.query_called is False
    assert iterator.closed is True
    assert "人物" in caplog.text


def test_category_docs_snippet_strips_obsidian_display_markup(monkeypatch):
    """展示用 snippet 不应把 Dataview/图片嵌入/HTML 标签直接给前端。"""
    from langchain_core.documents import Document

    from backend import main as main_mod
    from tests.conftest import MockVectorstore

    dirty_doc = Document(
        page_content=(
            "%% DATAVIEW_PUBLISHER: start\n"
            "```dataview\nTable without id\n```\n"
            "![[立绘 6 02.png]]\n"
            "<span>6 是阿派朗学派的领导者。</span>"
        ),
        metadata={"name": "6", "source": "100-UTTU人物合辑/6｜Six.md"},
    )
    main_mod._state = {
        "vs": MockVectorstore(
            doc_counts={"人物": 1},
            docs_by_category={"人物": [dirty_doc]},
        ),
        "retriever": None,
        "chain": None,
        "loaded": True,
    }
    monkeypatch.setattr(main_mod, "_ensure_loaded", lambda: None)
    client = TestClient(main_mod.app)

    resp = client.get("/category/%E4%BA%BA%E7%89%A9/docs?limit=1")

    assert resp.status_code == 200
    snippet = resp.json()["docs"][0]["snippet"]
    assert "DATAVIEW_PUBLISHER" not in snippet
    assert "```dataview" not in snippet
    assert "![[" not in snippet
    assert "<span>" not in snippet
    assert "6 是阿派朗学派的领导者" in snippet
