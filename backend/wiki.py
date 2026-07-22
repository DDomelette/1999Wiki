"""FastAPI routes for the Huiji wiki browser."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.wiki_schemas import (
    WikiCategoriesResponse,
    WikiHealthResponse,
    WikiPageDetailResponse,
    WikiPageListItem,
    WikiPageListResponse,
    WikiRouteResolveResponse,
)
from config.config import get_config
from src.huiji_wiki.repository import (
    InvalidWikiCursor,
    MySQLWikiRepository,
    WikiRepository,
    WikiRepositoryUnavailable,
    is_public_media_url,
    sanitize_media_item,
)

router = APIRouter(prefix="/api/wiki", tags=["wiki"])


def get_wiki_repository() -> WikiRepository:
    return MySQLWikiRepository(get_config())


def _safe_public_url(url: str) -> str:
    return url if is_public_media_url(url) else ""


def _safe_page_detail(payload: dict) -> dict:
    detail = dict(payload)
    detail["mediaLinks"] = [
        item for item in (sanitize_media_item(dict(media)) for media in detail.get("mediaLinks", [])) if item
    ]
    return detail


@router.get("/categories", response_model=WikiCategoriesResponse)
async def wiki_categories() -> WikiCategoriesResponse:
    repo = get_wiki_repository()
    return WikiCategoriesResponse(categories=[item.to_json() for item in repo.list_categories()])


@router.get("/health", response_model=WikiHealthResponse)
async def wiki_health() -> WikiHealthResponse:
    return WikiHealthResponse(**get_wiki_repository().get_health())


@router.get("/pages", response_model=WikiPageListResponse)
async def wiki_pages(
    category: str = "",
    q: str = "",
    type: str = "",
    limit: int = 30,
    cursor: str = "",
) -> WikiPageListResponse:
    repo = get_wiki_repository()
    try:
        pages, next_cursor = repo.list_pages(category=category, q=q, page_type=type, limit=limit, cursor=cursor)
    except InvalidWikiCursor as exc:
        raise HTTPException(status_code=400, detail="无效的 Wiki 分页游标") from exc
    except WikiRepositoryUnavailable as exc:
        raise HTTPException(status_code=503, detail="Wiki 数据暂不可用") from exc
    thumbnails = repo.first_media_url_by_page([page.page_id for page in pages])
    items = [
        WikiPageListItem(
            pageId=page.page_id,
            pageType=page.page_type,
            title=page.title,
            subtitle=page.subtitle,
            category=page.category,
            route=page.route,
            thumbnail=_safe_public_url(thumbnails.get(page.page_id, "")),
            summary=str((page.content_json or {}).get("summary", ""))[:180],
        )
        for page in pages
    ]
    return WikiPageListResponse(items=items, nextCursor=next_cursor)


@router.get("/pages/by-route", response_model=WikiPageDetailResponse)
async def wiki_page_detail_by_route(route: str = "") -> WikiPageDetailResponse:
    try:
        return WikiPageDetailResponse(**_safe_page_detail(get_wiki_repository().get_page_detail_by_route(route)))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Wiki page not found") from exc


@router.get("/pages/{page_id:path}", response_model=WikiPageDetailResponse)
async def wiki_page_detail(page_id: str) -> WikiPageDetailResponse:
    try:
        return WikiPageDetailResponse(**_safe_page_detail(get_wiki_repository().get_page_detail(page_id)))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Wiki page not found") from exc


@router.get("/routes/resolve", response_model=WikiRouteResolveResponse)
async def wiki_route_resolve(
    source_id: str = "",
    entity_id: str = "",
    title: str = "",
) -> WikiRouteResolveResponse:
    route = get_wiki_repository().resolve_route(entity_id=entity_id, source_id=source_id, title=title)
    return WikiRouteResolveResponse(route=route, query=entity_id or source_id or title)


@router.get("/search", response_model=WikiPageListResponse)
async def wiki_search(q: str = "", limit: int = 30) -> WikiPageListResponse:
    return await wiki_pages(q=q, limit=limit)
