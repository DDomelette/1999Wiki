from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import datetime

from .models import ResourceRecord, SITE_KEY, stable_resource_relpath


def now_local_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


class ResourceManifestBuilder:
    def __init__(self, client, seen_at_fn: Callable[[], str] = now_local_iso) -> None:
        self.client = client
        self.seen_at_fn = seen_at_fn

    def iter_resources(self) -> Iterator[ResourceRecord]:
        params: dict[str, object] = {
            "list": "allimages",
            "ailimit": "500",
            "aiprop": "url|size|mime|dimensions|sha1|timestamp",
        }
        while True:
            payload = self.client.query(params)
            for item in payload.get("query", {}).get("allimages", []):
                name = str(item["name"])
                sha1 = item.get("sha1")
                yield ResourceRecord(
                    site=SITE_KEY,
                    source="huiji_file_namespace",
                    title=str(item.get("title", f"File:{name}")),
                    name=name,
                    url=str(item.get("url", "")),
                    descriptionurl=str(item.get("descriptionurl", "")),
                    mime=item.get("mime"),
                    size=int(item["size"]) if item.get("size") is not None else None,
                    width=int(item["width"]) if item.get("width") is not None else None,
                    height=int(item["height"]) if item.get("height") is not None else None,
                    sha1=str(sha1) if sha1 else None,
                    timestamp=item.get("timestamp"),
                    local_relpath=stable_resource_relpath(
                        name=name,
                        sha1=str(sha1) if sha1 else None,
                        pageid=None,
                    ),
                    download_status="not_downloaded",
                    seen_at=self.seen_at_fn(),
                )
            cont = payload.get("continue", {})
            if "aicontinue" not in cont:
                break
            params["aicontinue"] = cont["aicontinue"]
