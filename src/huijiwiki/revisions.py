from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from datetime import datetime

from .models import RevisionRecord, SITE_KEY


def now_local_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def batched(values: Iterable[int], size: int) -> Iterator[list[int]]:
    batch: list[int] = []
    for value in values:
        batch.append(int(value))
        if len(batch) == size:
            yield batch
            batch = []
    if batch:
        yield batch


def parse_revision_page(page: dict, fetched_at: str) -> RevisionRecord:
    revisions = page.get("revisions") or []
    rev = revisions[0] if revisions else {}
    slot = (rev.get("slots") or {}).get("main") or {}
    content = slot.get("content", rev.get("*", ""))
    return RevisionRecord(
        site=SITE_KEY,
        pageid=int(page["pageid"]),
        ns=int(page.get("ns", 0)),
        title=str(page["title"]),
        revid=int(rev.get("revid", 0)),
        timestamp=str(rev.get("timestamp", "")),
        content_model=str(slot.get("contentmodel", page.get("contentmodel", "wikitext"))),
        content_format=str(slot.get("contentformat", "text/x-wiki")),
        content=str(content),
        fetched_at=fetched_at,
    )


class RevisionFetcher:
    def __init__(
        self,
        client,
        fetched_at_fn: Callable[[], str] = now_local_iso,
        batch_size: int = 50,
    ) -> None:
        self.client = client
        self.fetched_at_fn = fetched_at_fn
        self.batch_size = batch_size

    def fetch_pageids(self, pageids: Iterable[int]) -> Iterator[RevisionRecord]:
        for batch in batched(pageids, self.batch_size):
            payload = self.client.query(
                {
                    "prop": "revisions",
                    "pageids": "|".join(str(pageid) for pageid in batch),
                    "rvprop": "ids|timestamp|content",
                    "rvslots": "main",
                }
            )
            pages = payload.get("query", {}).get("pages", [])
            if isinstance(pages, dict):
                pages = pages.values()
            for page in pages:
                yield parse_revision_page(page, fetched_at=self.fetched_at_fn())
