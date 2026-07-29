from __future__ import annotations

import hashlib
import json
from io import BytesIO

import pytest

from src.huiji_rag.build.contracts import canonical_mapping_jsonl_bytes
from src.huijiwiki.resource_downloader import (
    ApprovalRequiredError,
    DownloadConfig,
    ResourceDownloader,
)


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


def make_allowlist_row(name: str, body: bytes, **overrides) -> dict[str, object]:
    sha1 = hashlib.sha1(body).hexdigest()
    values = {
        "schema_version": "huiji.referenced-media-allowlist-entry/v1",
        "resource_id": f"resource:{sha1}",
        "binding_ids": [f"binding:{name}"],
        "name": name,
        "filename": name,
        "url": f"https://huiji-public.huijistatic.com/res1999/uploads/0/00/{name}",
        "mime": "image/png",
        "size": len(body),
        "sha1": sha1,
        "content_sha256": hashlib.sha256(body).hexdigest(),
        "local_relpath": f"assets/files/{sha1}/{name}",
        "object_key": f"reverse1999/image/{sha1}/{name}",
        "expected_download_bytes": len(body),
        "new_object_bytes": len(body),
    }
    values.update(overrides)
    return values


def make_downloader(
    tmp_path,
    rows: list[dict[str, object]],
    *,
    approved: bool = True,
    workers: int = 1,
    urlopen_fn=None,
) -> tuple[ResourceDownloader, list[str]]:
    allowlist_path = tmp_path / "referenced_media_allowlist.v1.jsonl"
    allowlist_bytes = canonical_mapping_jsonl_bytes(rows)
    allowlist_path.write_bytes(allowlist_bytes)
    allowlist_sha256 = hashlib.sha256(allowlist_bytes).hexdigest()
    staging_root = tmp_path / "staging"
    approval_path = tmp_path / "approval.json"
    if approved:
        approval_path.write_text(
            json.dumps(
                {
                    "schema_version": "huiji.media-download-approval/v1",
                    "approval_state": "approved",
                    "allowlist_sha256": allowlist_sha256,
                    "source_inventory_sha256": "s" * 64,
                    "expected_bytes": sum(
                        int(row["expected_download_bytes"]) for row in rows
                    ),
                    "workers": workers,
                    "staging_root": str(staging_root.resolve()),
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )
    requested_urls: list[str] = []

    def default_urlopen(request, timeout):
        requested_urls.append(request.full_url)
        row = next(row for row in rows if row["url"] == request.full_url)
        return FakeResponse(bytes.fromhex(str(row["content_sha256"]))[:0])

    downloader = ResourceDownloader(
        DownloadConfig(
            staging_root=staging_root,
            allowlist_path=allowlist_path,
            expected_allowlist_sha256=allowlist_sha256,
            expected_source_inventory_sha256="s" * 64,
            approval_path=approval_path,
            staging_receipt_path=staging_root / "download_receipt.v1.jsonl",
            workers=workers,
        ),
        urlopen_fn=urlopen_fn or default_urlopen,
    )
    return downloader, requested_urls


def test_resource_downloader_writes_only_staging_and_records_independent_receipt(tmp_path):
    body = b"image-bytes"
    row = make_allowlist_row("Example.png", body)
    requested_urls = []

    def fake_urlopen(request, timeout):
        requested_urls.append(request.full_url)
        return FakeResponse(body)

    downloader, _ = make_downloader(tmp_path, [row], urlopen_fn=fake_urlopen)

    summary = downloader.run()

    target = tmp_path / "staging" / row["local_relpath"]
    assert target.read_bytes() == body
    assert requested_urls == [row["url"]]
    receipt = tmp_path / "staging" / "download_receipt.v1.jsonl"
    assert json.loads(receipt.read_text(encoding="utf-8"))["status"] == "downloaded"
    assert not (tmp_path / "crawl_state.sqlite").exists()
    assert summary.downloaded == 1
    assert summary.failed == 0


def test_resource_downloader_skips_existing_valid_staging_file(tmp_path):
    body = b"already-downloaded"
    row = make_allowlist_row(
        "Cached.webp",
        body,
        mime="image/webp",
        expected_download_bytes=0,
    )
    target = tmp_path / "staging" / row["local_relpath"]
    target.parent.mkdir(parents=True)
    target.write_bytes(body)

    def fail_urlopen(request, timeout):
        raise AssertionError("existing valid file should not be downloaded again")

    downloader, _ = make_downloader(tmp_path, [row], urlopen_fn=fail_urlopen)

    summary = downloader.run()

    assert target.read_bytes() == body
    assert summary.skipped == 1
    assert summary.downloaded == 0


def test_zero_expected_bytes_with_missing_staging_file_makes_no_network_call(tmp_path):
    row = make_allowlist_row("Missing.webp", b"body", expected_download_bytes=0)
    calls = []
    downloader, _ = make_downloader(
        tmp_path,
        [row],
        urlopen_fn=lambda request, timeout: calls.append(request),
    )

    summary = downloader.run()

    assert summary.failed == 1
    assert calls == []
    assert not (tmp_path / "staging" / row["local_relpath"]).exists()


def test_resource_downloader_rejects_path_escape(tmp_path):
    body = b"bad"
    row = make_allowlist_row("Bad.png", body, local_relpath="../Bad.png")

    downloader, _ = make_downloader(
        tmp_path,
        [row],
        urlopen_fn=lambda request, timeout: FakeResponse(body),
    )

    summary = downloader.run()

    assert not (tmp_path / "Bad.png").exists()
    assert summary.failed == 1


def test_resource_downloader_consumes_only_allowlist_jobs(tmp_path):
    png = make_allowlist_row("A.png", b"a", mime="image/png")
    requested_urls = []

    def fake_urlopen(request, timeout):
        requested_urls.append(request.full_url)
        return FakeResponse(b"a")

    downloader, _ = make_downloader(tmp_path, [png], urlopen_fn=fake_urlopen)

    summary = downloader.run()

    assert summary.total == 1
    assert requested_urls == [png["url"]]


def test_no_approval_makes_zero_network_calls_and_zero_staging_writes(tmp_path):
    row = make_allowlist_row("A.png", b"a")
    calls = []
    downloader, _ = make_downloader(
        tmp_path,
        [row],
        approved=False,
        urlopen_fn=lambda request, timeout: calls.append(request),
    )

    with pytest.raises(ApprovalRequiredError, match="explicit approval"):
        downloader.run()

    assert calls == []
    assert not (tmp_path / "staging").exists()


def test_resource_downloader_rejects_allowlist_drift_before_network_or_writes(tmp_path):
    row = make_allowlist_row("A.png", b"a")
    calls = []
    downloader, _ = make_downloader(
        tmp_path,
        [row],
        urlopen_fn=lambda request, timeout: calls.append(request),
    )
    downloader.config.allowlist_path.write_text("{}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="allowlist SHA-256"):
        downloader.run()

    assert calls == []
    assert not (tmp_path / "staging").exists()


def test_resource_downloader_rejects_canonical_state_as_receipt(tmp_path):
    row = make_allowlist_row("A.png", b"a")
    calls = []
    downloader, _ = make_downloader(
        tmp_path,
        [row],
        urlopen_fn=lambda request, timeout: calls.append(request),
    )
    object.__setattr__(
        downloader.config,
        "staging_receipt_path",
        downloader.config.staging_root / "crawl_state.sqlite",
    )

    with pytest.raises(ValueError, match="canonical crawl state"):
        downloader.run()

    assert calls == []
    assert not (tmp_path / "staging").exists()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("workers", 2),
        ("expected_bytes", 999),
        ("staging_root", "D:/wrong/staging"),
        ("source_inventory_sha256", "x" * 64),
    ],
)
def test_resource_downloader_rejects_approval_metadata_mismatch(
    tmp_path,
    field,
    value,
):
    row = make_allowlist_row("A.png", b"a")
    calls = []
    downloader, _ = make_downloader(
        tmp_path,
        [row],
        urlopen_fn=lambda request, timeout: calls.append(request),
    )
    approval = json.loads(downloader.config.approval_path.read_text(encoding="utf-8"))
    approval[field] = value
    downloader.config.approval_path.write_text(json.dumps(approval), encoding="utf-8")

    with pytest.raises(ValueError, match="approval"):
        downloader.run()

    assert calls == []
    assert not (tmp_path / "staging").exists()


@pytest.mark.parametrize(
    "url",
    [
        "http://huiji-public.huijistatic.com/A.png",
        "https://example.com/A.png",
    ],
)
def test_resource_downloader_preserves_https_host_enforcement(tmp_path, url):
    row = make_allowlist_row("A.png", b"a", url=url)
    calls = []
    downloader, _ = make_downloader(
        tmp_path,
        [row],
        urlopen_fn=lambda request, timeout: calls.append(request),
    )

    summary = downloader.run()

    assert summary.failed == 1
    assert calls == []


def test_resource_downloader_removes_invalid_part_without_replacing_valid_file(tmp_path):
    body = b"expected"
    row = make_allowlist_row("A.png", body)
    downloader, _ = make_downloader(
        tmp_path,
        [row],
        urlopen_fn=lambda request, timeout: FakeResponse(b"wrong"),
    )

    summary = downloader.run()

    target = tmp_path / "staging" / row["local_relpath"]
    assert summary.failed == 1
    assert not target.exists()
    assert not target.with_name(target.name + ".part").exists()
