from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import datetime

from .models import PageIndexRecord, SITE_KEY

PAGEIDS_BATCH_SIZE = 50


def now_local_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def batched(values: list[dict], size: int) -> Iterator[list[dict]]:
    batch: list[dict] = []
    for value in values:
        batch.append(value)
        if len(batch) == size:
            yield batch
            batch = []
    if batch:
        yield batch


class PageEnumerator:
    def __init__(self, client, seen_at_fn: Callable[[], str] = now_local_iso) -> None:
        self.client = client
        self.seen_at_fn = seen_at_fn

    def iter_namespace(self, namespace: int) -> Iterator[PageIndexRecord]:
        params: dict[str, object] = {
            "list": "allpages",
            "apnamespace": namespace,
            "aplimit": "500",
            "apfilterredir": "nonredirects",
        }
        while True:
            payload = self.client.query(params)
            pages = list(payload.get("query", {}).get("allpages", []))
            pages = self._ensure_page_info(pages)
            for page in pages:
                yield PageIndexRecord(
                    site=SITE_KEY,
                    pageid=int(page["pageid"]),
                    ns=int(page.get("ns", namespace)),
                    title=str(page["title"]),
                    lastrevid=int(page.get("lastrevid", 0)),
                    length=int(page.get("length", 0)),
                    touched=str(page.get("touched", "")),
                    seen_at=self.seen_at_fn(),
                )
            cont = payload.get("continue", {})
            if "apcontinue" not in cont:
                break
            params["apcontinue"] = cont["apcontinue"]

    def _ensure_page_info(self, pages: list[dict]) -> list[dict]:
        missing = [
            page
            for page in pages
            if "lastrevid" not in page or "length" not in page or "touched" not in page
        ]
        if not missing:
            return pages
        info_by_pageid: dict[int, dict] = {}
        for batch in batched(missing, PAGEIDS_BATCH_SIZE):
            info_payload = self.client.query(
                {
                    "prop": "info",
                    "pageids": "|".join(str(page["pageid"]) for page in batch),
                }
            )
            info_pages = info_payload.get("query", {}).get("pages", [])
            if isinstance(info_pages, dict):
                info_pages = info_pages.values()
            info_by_pageid.update({int(page["pageid"]): page for page in info_pages})
        merged: list[dict] = []
        for page in pages:
            merged_page = dict(page)
            merged_page.update(info_by_pageid.get(int(page["pageid"]), {}))
            merged.append(merged_page)
        return merged
