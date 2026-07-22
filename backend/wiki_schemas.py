"""Pydantic schemas for the wiki browser API."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class WikiCategoryItem(BaseModel):
    key: str
    label: str
    count: int
    templateGroup: str = ""
    animationProfile: str = ""
    themeToken: str = ""


class WikiCategoriesResponse(BaseModel):
    categories: list[WikiCategoryItem]


class WikiPageListItem(BaseModel):
    pageId: str
    pageType: str
    title: str
    subtitle: str
    category: str
    route: str
    thumbnail: str = ""
    summary: str = ""


class WikiPageListResponse(BaseModel):
    items: list[WikiPageListItem]
    nextCursor: str | None = None


class WikiPageDetailResponse(BaseModel):
    pageId: str
    pageType: str
    title: str
    subtitle: str
    category: str
    route: str
    content: dict[str, Any]
    mediaLinks: list[dict[str, Any]] = []
    relations: list[dict[str, Any]] = []
    linkSpans: list[dict[str, Any]] = []
    sourcePageid: int | None = None
    sourceTitle: str = ""


class WikiRouteResolveResponse(BaseModel):
    route: str | None = None
    query: str = ""


class WikiHealthResponse(BaseModel):
    ready: bool
    pageCount: int = 0
    categoryCount: int = 0
    mediaLinkCount: int = 0
    mediaResourceCount: int = 0
    mediaBindingCount: int = 0
    linkSpanCount: int = 0
    aliasCount: int = 0
    sourceMode: str = ""
    buildVersion: str = ""
    artifactSchemaVersion: str = ""
    activationEpoch: int | None = None
    manifestSha256Prefix: str = ""
    stale: bool = False
    error: str = ""
