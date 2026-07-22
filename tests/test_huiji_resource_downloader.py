from __future__ import annotations

import hashlib
from io import BytesIO

import pytest

from src.huijiwiki.models import ResourceRecord
from src.huijiwiki.resource_downloader import DownloadConfig, ResourceDownloader
from src.huijiwiki.state import CrawlStateStore


class FakeResponse:
    def __init__(self, body: bytes, status: int = 200, headers: dict[str, str] | None = None):
        self.stream = BytesIO(body)
        self.status = status
        self.headers = headers or {"Content-Length": str(len(body))}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self, size: int = -1) -> bytes:
        return self.stream.read(size)


def make_resource(name: str, body: bytes, **overrides) -> ResourceRecord:
    sha1 = hashlib.sha1(body).hexdigest()
    values = {
        "site": "res1999",
        "source": "huiji_file_namespace",
        "title": f"文件:{name}",
        "name": name,
        "url": f"https://huiji-public.huijistatic.com/res1999/uploads/0/00/{name}",
        "descriptionurl": f"https://res1999.huijiwiki.com/wiki/File:{name}",
        "mime": "image/png",
        "size": len(body),
        "width": 1,
        "height": 1,
        "sha1": sha1,
        "timestamp": "2026-07-03T00:00:00Z",
        "local_relpath": f"assets/files/{sha1}/{name}",
        "download_status": "not_downloaded",
        "seen_at": "2026-07-03T08:00:00+08:00",
    }
    values.update(overrides)
    return ResourceRecord(**values)


def make_store(tmp_path, *resources: ResourceRecord) -> tuple[CrawlStateStore, str]:
    db_path = tmp_path / "crawl_state.sqlite"
    store = CrawlStateStore(db_path)
    store.initialize()
    for resource in resources:
        store.upsert_resource(resource)
    return store, str(db_path)


def test_resource_downloader_writes_file_and_updates_status(tmp_path):
    body = b"image-bytes"
    resource = make_resource("Example.png", body)
    store, db_path = make_store(tmp_path, resource)
    requested_urls = []

    def fake_urlopen(request, timeout):
        requested_urls.append(request.full_url)
        return FakeResponse(body)

    downloader = ResourceDownloader(
        DownloadConfig(out=tmp_path / "out", db_path=db_path, workers=1),
        urlopen_fn=fake_urlopen,
    )

    summary = downloader.run()

    target = tmp_path / "out" / resource.local_relpath
    assert target.read_bytes() == body
    assert requested_urls == [resource.url]
    assert store.get_resource(resource.name)["download_status"] == "downloaded"
    assert summary.downloaded == 1
    assert summary.failed == 0


def test_resource_downloader_skips_existing_valid_file_and_updates_status(tmp_path):
    body = b"already-downloaded"
    resource = make_resource("Cached.webp", body, mime="image/webp")
    store, db_path = make_store(tmp_path, resource)
    target = tmp_path / "out" / resource.local_relpath
    target.parent.mkdir(parents=True)
    target.write_bytes(body)

    def fail_urlopen(request, timeout):
        raise AssertionError("existing valid file should not be downloaded again")

    downloader = ResourceDownloader(
        DownloadConfig(out=tmp_path / "out", db_path=db_path, workers=1),
        urlopen_fn=fail_urlopen,
    )

    summary = downloader.run()

    assert target.read_bytes() == body
    assert store.get_resource(resource.name)["download_status"] == "downloaded"
    assert summary.skipped == 1
    assert summary.downloaded == 0


def test_resource_downloader_rejects_path_escape(tmp_path):
    body = b"bad"
    resource = make_resource("Bad.png", body, local_relpath="../Bad.png")
    store, db_path = make_store(tmp_path, resource)

    downloader = ResourceDownloader(
        DownloadConfig(out=tmp_path / "out", db_path=db_path, workers=1),
        urlopen_fn=lambda request, timeout: FakeResponse(body),
    )

    summary = downloader.run()

    assert not (tmp_path / "Bad.png").exists()
    assert store.get_resource(resource.name)["download_status"] == "failed"
    assert summary.failed == 1


def test_resource_downloader_filters_by_mime_prefix_and_limit(tmp_path):
    png = make_resource("A.png", b"a", mime="image/png")
    mp3 = make_resource("A.mp3", b"b", mime="audio/mpeg")
    store, db_path = make_store(tmp_path, png, mp3)

    downloader = ResourceDownloader(
        DownloadConfig(out=tmp_path / "out", db_path=db_path, workers=1, mime_prefixes=("image/",), limit=1),
        urlopen_fn=lambda request, timeout: FakeResponse(b"a"),
    )

    summary = downloader.run()

    assert summary.total == 1
    assert store.get_resource(png.name)["download_status"] == "downloaded"
    assert store.get_resource(mp3.name)["download_status"] == "not_downloaded"
