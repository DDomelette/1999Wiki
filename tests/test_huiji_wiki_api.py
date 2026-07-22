from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend import wiki
from src.huiji_wiki.repository import InvalidWikiCursor, WikiRepositoryUnavailable


class FakeRepo:
    def list_categories(self):
        return [
            type(
                "Category",
                (),
                {
                    "to_json": lambda self: {
                        "key": "character",
                        "label": "角色",
                        "count": 1,
                        "templateGroup": "character",
                    }
                },
            )()
        ]

    def list_pages(self, category="", q="", page_type="", limit=30, cursor=""):
        page = type(
            "Page",
            (),
            {
                "page_id": "char:3074",
                "page_type": "character",
                "title": "爱兹拉",
                "subtitle": "Ezra Theodore",
                "category": "角色",
                "route": "/wiki/char/3074",
                "content_json": {"summary": "角色摘要" * 80},
            },
        )()
        return [page], None

    def first_media_url_by_page(self, page_ids):
        return {"char:3074": "D:\\assets\\local-thumbnail.png"}

    def get_health(self):
        return {
            "ready": True,
            "pageCount": 132,
            "categoryCount": 1,
            "mediaLinkCount": 15398,
            "linkSpanCount": 998,
            "aliasCount": 263,
            "error": "",
        }

    def get_page_detail(self, page_id):
        return {
            "pageId": page_id,
            "pageType": "character",
            "title": "爱兹拉",
            "subtitle": "Ezra Theodore",
            "category": "角色",
            "route": "/wiki/char/3074",
            "sourcePageid": 3074,
            "sourceTitle": "Data:Char/3074.json",
            "content": {"summary": "角色摘要"},
            "mediaLinks": [
                {
                    "mediaId": "safe-image",
                    "assetId": "safe-image",
                    "assetType": "portrait",
                    "mime": "image/webp",
                    "url": "http://127.0.0.1:9002/reverse1999-assets/reverse1999/portrait/aa/safe.webp",
                    "title": "安全图片",
                    "alt": "安全图片",
                    "role": "portrait",
                    "sectionKey": "profile",
                    "displayOrder": 1,
                    "objectKey": "reverse1999/portrait/aa/safe.webp",
                    "local_relpath": "assets/files/safe.webp",
                    "sha1": "abc",
                    "width": 1024,
                    "height": 2048,
                    "variant": "initial",
                },
                {
                    "mediaId": "local-path",
                    "assetType": "image",
                    "url": "D:\\assets\\local-path.png",
                    "title": "本地路径",
                },
            ],
            "relations": [],
            "linkSpans": [
                {
                    "pageId": page_id,
                    "sectionKey": "summary",
                    "text": "维尔汀",
                    "targetRoute": "/wiki/char/3001",
                    "confidence": 0.95,
                }
            ],
        }

    def get_page_detail_by_route(self, route):
        if route == "/wiki/char/3074":
            return self.get_page_detail("char:3074")
        raise KeyError(route)

    def resolve_route(self, entity_id="", source_id="", title=""):
        if entity_id == "3074":
            return "/wiki/char/3074"
        return None


def _client(monkeypatch) -> TestClient:
    app = FastAPI()
    app.include_router(wiki.router)
    monkeypatch.setattr(wiki, "get_wiki_repository", lambda: FakeRepo())
    return TestClient(app)


def _client_with_repo(monkeypatch, repo) -> TestClient:
    app = FastAPI()
    app.include_router(wiki.router)
    monkeypatch.setattr(wiki, "get_wiki_repository", lambda: repo)
    return TestClient(app)


def test_categories_and_pages_use_camel_case_contract(monkeypatch):
    client = _client(monkeypatch)

    categories = client.get("/api/wiki/categories").json()
    assert categories["categories"][0]["templateGroup"] == "character"

    pages = client.get("/api/wiki/pages?category=角色").json()
    item = pages["items"][0]
    assert item["pageId"] == "char:3074"
    assert item["pageType"] == "character"
    assert item["summary"].startswith("角色摘要")
    assert len(item["summary"]) <= 180
    assert item["thumbnail"] == ""
    assert "D:\\" not in str(pages)
    assert "local_relpath" not in str(pages)


def test_wiki_health_exposes_canonical_counts_without_supplement_fields(monkeypatch):
    client = _client(monkeypatch)

    payload = client.get("/api/wiki/health").json()

    assert payload["ready"] is True
    assert payload["pageCount"] == 132
    assert payload["mediaLinkCount"] == 15398
    assert "supplementReady" not in payload
    assert "supplementPageCount" not in payload
    assert "supplementBlockCount" not in payload


def test_page_detail_filters_media_to_public_whitelist(monkeypatch):
    client = _client(monkeypatch)

    detail = client.get("/api/wiki/pages/char:3074").json()

    assert detail["pageId"] == "char:3074"
    assert [item["mediaId"] for item in detail["mediaLinks"]] == ["safe-image"]
    media = detail["mediaLinks"][0]
    assert media == {
        "mediaId": "safe-image",
        "assetId": "safe-image",
        "assetType": "portrait",
        "mime": "image/webp",
        "url": "http://127.0.0.1:9002/reverse1999-assets/reverse1999/portrait/aa/safe.webp",
        "title": "安全图片",
        "alt": "安全图片",
        "role": "portrait",
        "sectionKey": "profile",
        "displayOrder": 1,
        "sha1": "abc",
        "width": 1024,
        "height": 2048,
        "variant": "initial",
    }
    assert "objectKey" not in media
    assert "local_relpath" not in str(detail)
    assert "D:\\" not in str(detail)


def test_page_detail_by_route_uses_static_route_before_page_id_path(monkeypatch):
    client = _client(monkeypatch)

    detail = client.get("/api/wiki/pages/by-route?route=/wiki/char/3074").json()

    assert detail["pageId"] == "char:3074"
    assert detail["route"] == "/wiki/char/3074"
    assert "local_relpath" not in str(detail)
    assert "D:\\" not in str(detail)


def test_page_detail_preserves_explicit_skin_media_contract(monkeypatch):
    class SkinContractRepo(FakeRepo):
        def get_page_detail(self, page_id):
            detail = super().get_page_detail(page_id)
            detail["content"]["skins"] = [
                {
                    "name": "Initial",
                    "mediaIds": {
                        "stage_live2d": "skin-live2d",
                        "stage_portrait": "skin-portrait",
                        "skin_background": "skin-background",
                    },
                }
            ]
            detail["mediaLinks"] = [
                {
                    "mediaId": media_id,
                    "assetId": media_id,
                    "assetType": "portrait" if role != "skin_background" else "image",
                    "mime": "image/webp",
                    "url": f"http://127.0.0.1:9002/reverse1999-assets/reverse1999/{media_id}.webp",
                    "title": media_id,
                    "alt": media_id,
                    "role": role,
                    "sectionKey": "skins",
                    "displayOrder": order,
                    "objectKey": f"reverse1999/{media_id}.webp",
                    "local_relpath": f"assets/files/{media_id}.webp",
                }
                for order, (media_id, role) in enumerate(
                    (
                        ("skin-live2d", "stage_live2d"),
                        ("skin-portrait", "stage_portrait"),
                        ("skin-background", "skin_background"),
                    ),
                    start=1,
                )
            ]
            return detail

    client = _client_with_repo(monkeypatch, SkinContractRepo())

    detail = client.get("/api/wiki/pages/char:3074").json()

    assert detail["content"]["skins"][0]["mediaIds"] == {
        "stage_live2d": "skin-live2d",
        "stage_portrait": "skin-portrait",
        "skin_background": "skin-background",
    }
    assert {item["role"] for item in detail["mediaLinks"]} == {
        "stage_live2d",
        "stage_portrait",
        "skin_background",
    }
    assert "objectKey" not in str(detail)
    assert "local_relpath" not in str(detail)


def test_page_detail_by_route_returns_404_for_unknown_route(monkeypatch):
    client = _client(monkeypatch)

    response = client.get("/api/wiki/pages/by-route?route=/wiki/missing")

    assert response.status_code == 404
    assert response.json()["detail"] == "Wiki page not found"


def test_route_resolve_returns_null_for_missing_route(monkeypatch):
    client = _client(monkeypatch)

    assert client.get("/api/wiki/routes/resolve?entity_id=3074").json() == {
        "route": "/wiki/char/3074",
        "query": "3074",
    }
    assert client.get("/api/wiki/routes/resolve?title=不存在").json() == {
        "route": None,
        "query": "不存在",
    }


def test_pages_maps_invalid_opaque_cursor_to_400_without_echoing_payload(monkeypatch):
    class InvalidCursorRepo(FakeRepo):
        def list_pages(self, category="", q="", page_type="", limit=30, cursor=""):
            raise InvalidWikiCursor("secret cursor payload")

    response = _client_with_repo(monkeypatch, InvalidCursorRepo()).get("/api/wiki/pages?cursor=bad-secret")

    assert response.status_code == 400
    assert response.json() == {"detail": "无效的 Wiki 分页游标"}
    assert "secret" not in response.text


def test_pages_and_search_map_repository_failure_to_503_without_connection_details(monkeypatch):
    class UnavailableRepo(FakeRepo):
        def list_pages(self, category="", q="", page_type="", limit=30, cursor=""):
            raise WikiRepositoryUnavailable("mysql://user:password@private-host")

    client = _client_with_repo(monkeypatch, UnavailableRepo())

    for path in ("/api/wiki/pages", "/api/wiki/search?q=露西"):
        response = client.get(path)
        assert response.status_code == 503
        assert response.json() == {"detail": "Wiki 数据暂不可用"}
        assert "password" not in response.text
        assert "private-host" not in response.text
