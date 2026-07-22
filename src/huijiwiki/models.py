from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import PurePosixPath
from urllib.parse import quote

from .errors import ReadOnlyViolation

SITE_KEY = "res1999"
API_URL = "https://res1999.huijiwiki.com/api.php"
WIKI_BASE_URL = "https://res1999.huijiwiki.com/wiki/"
READ_ONLY_ACTIONS = {"query"}
WRITE_ACTIONS = {
    "edit",
    "upload",
    "delete",
    "move",
    "purge",
    "rollback",
    "protect",
    "block",
    "unblock",
    "patrol",
    "mergehistory",
    "import",
}


def ensure_read_only_action(params: dict[str, object]) -> None:
    action = str(params.get("action", "query")).lower()
    if action in WRITE_ACTIONS or action not in READ_ONLY_ACTIONS:
        raise ReadOnlyViolation(f"Blocked MediaWiki action: {action}")


def build_source_url(title: str) -> str:
    normalized = title.replace(" ", "_")
    return WIKI_BASE_URL + quote(normalized, safe=":/()_-.,")


def content_sha256(content: str) -> str:
    return sha256(content.encode("utf-8")).hexdigest()


def stable_resource_relpath(name: str, sha1: str | None, pageid: int | None) -> str:
    key = sha1 or (f"pageid-{pageid}" if pageid is not None else "unknown")
    return str(PurePosixPath("assets") / "files" / key / name)


@dataclass(frozen=True)
class PageIndexRecord:
    site: str
    pageid: int
    ns: int
    title: str
    lastrevid: int
    length: int
    touched: str
    seen_at: str
    status: str = "active"

    def to_json(self) -> dict[str, object]:
        payload = asdict(self)
        payload["source_url"] = build_source_url(self.title)
        return payload


@dataclass(frozen=True)
class RevisionRecord:
    site: str
    pageid: int
    ns: int
    title: str
    revid: int
    timestamp: str
    content_model: str
    content_format: str
    content: str
    fetched_at: str

    def to_json(self) -> dict[str, object]:
        payload = asdict(self)
        payload["source_url"] = build_source_url(self.title)
        payload["content_sha256"] = content_sha256(self.content)
        return payload


@dataclass(frozen=True)
class ResourceRecord:
    site: str
    source: str
    title: str
    name: str
    url: str
    descriptionurl: str
    mime: str | None
    size: int | None
    width: int | None
    height: int | None
    sha1: str | None
    timestamp: str | None
    local_relpath: str
    download_status: str
    seen_at: str

    def to_json(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class FetchDecision:
    pageid: int
    should_fetch: bool
    reason: str

    def to_json(self) -> dict[str, object]:
        return asdict(self)
