from __future__ import annotations

import hashlib
import json
from io import BytesIO

import pytest

import scripts.download_huiji_resources as download_script
from src.huiji_rag.build.contracts import canonical_mapping_jsonl_bytes
from src.huijiwiki.resource_downloader import (
    DownloadConfig,
    DownloadSummary,
    ResourceDownloader,
)


class FakeResponse:
    def __init__(self, body: bytes):
        self.stream = BytesIO(body)
        self.status = 200

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self, size: int = -1) -> bytes:
        return self.stream.read(size)


def secure_args(tmp_path, *, allowlist_sha256: str = "a" * 64) -> list[str]:
    return [
        "--staging-root",
        str(tmp_path / "staging"),
        "--allowlist",
        str(tmp_path / "referenced_media_allowlist.v1.jsonl"),
        "--allowlist-sha256",
        allowlist_sha256,
        "--source-inventory-sha256",
        "s" * 64,
        "--approval",
        str(tmp_path / "approval.json"),
        "--staging-receipt",
        str(tmp_path / "staging" / "download_receipt.v1.jsonl"),
    ]


@pytest.mark.parametrize(
    "legacy_option",
    ["--db", "--out", "--limit", "--include-failed", "--mime-prefix"],
)
def test_parser_rejects_legacy_sqlite_query_and_unrestricted_output_options(
    tmp_path,
    legacy_option: str,
) -> None:
    argv = [*secure_args(tmp_path), legacy_option]
    if legacy_option in {"--db", "--out", "--limit", "--mime-prefix"}:
        argv.append("legacy-value")

    with pytest.raises(SystemExit) as error:
        download_script.build_parser().parse_args(argv)

    assert error.value.code == 2


def test_parser_builds_exact_pinned_download_config(tmp_path) -> None:
    argv = [
        *secure_args(tmp_path),
        "--workers",
        "3",
        "--timeout",
        "12.5",
        "--retries",
        "4",
        "--sleep",
        "0.75",
        "--log-every",
        "9",
    ]

    args = download_script.build_parser().parse_args(argv)
    config = download_script.build_download_config(args)

    assert config == DownloadConfig(
        staging_root=tmp_path / "staging",
        allowlist_path=tmp_path / "referenced_media_allowlist.v1.jsonl",
        expected_allowlist_sha256="a" * 64,
        expected_source_inventory_sha256="s" * 64,
        approval_path=tmp_path / "approval.json",
        staging_receipt_path=tmp_path / "staging" / "download_receipt.v1.jsonl",
        workers=3,
        timeout=12.5,
        retries=4,
        sleep=0.75,
        log_every=9,
    )


def test_cli_without_approval_refuses_without_traceback_network_or_staging_write(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    allowlist = tmp_path / "referenced_media_allowlist.v1.jsonl"
    allowlist.write_bytes(b"")
    allowlist_sha256 = hashlib.sha256(b"").hexdigest()
    network_calls: list[object] = []

    def downloader_factory(config):
        return ResourceDownloader(
            config,
            urlopen_fn=lambda request, timeout: network_calls.append(request),
        )

    monkeypatch.setattr(download_script, "ResourceDownloader", downloader_factory)

    exit_code = download_script.main(
        secure_args(tmp_path, allowlist_sha256=allowlist_sha256)
    )

    captured = capsys.readouterr()
    assert exit_code != 0
    assert "explicit approval" in captured.err
    assert "Traceback" not in captured.err
    assert captured.out == ""
    assert network_calls == []
    assert not (tmp_path / "staging").exists()


def test_cli_approved_fake_response_downloads_only_allowlist_to_staging(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    body = b"approved-image"
    sha1 = hashlib.sha1(body).hexdigest()
    sha256 = hashlib.sha256(body).hexdigest()
    row = {
        "schema_version": "huiji.referenced-media-allowlist-entry/v1",
        "resource_id": f"resource:{sha256}",
        "binding_ids": ["binding:approved"],
        "filename": "Approved.png",
        "url": "https://huiji-public.huijistatic.com/res1999/Approved.png",
        "mime": "image/png",
        "size": len(body),
        "sha1": sha1,
        "content_sha256": sha256,
        "local_relpath": f"assets/{sha1}/Approved.png",
        "object_key": f"reverse1999/image/{sha1}/Approved.png",
        "expected_download_bytes": len(body),
        "new_object_bytes": len(body),
    }
    allowlist_bytes = canonical_mapping_jsonl_bytes([row])
    allowlist = tmp_path / "referenced_media_allowlist.v1.jsonl"
    allowlist.write_bytes(allowlist_bytes)
    allowlist_sha256 = hashlib.sha256(allowlist_bytes).hexdigest()
    staging_root = (tmp_path / "staging").resolve()
    (tmp_path / "approval.json").write_text(
        json.dumps(
            {
                "schema_version": "huiji.media-download-approval/v1",
                "approval_state": "approved",
                "allowlist_sha256": allowlist_sha256,
                "source_inventory_sha256": "s" * 64,
                "expected_bytes": len(body),
                "workers": 1,
                "staging_root": str(staging_root),
            }
        ),
        encoding="utf-8",
    )
    network_urls: list[str] = []

    def fake_urlopen(request, timeout):
        network_urls.append(request.full_url)
        return FakeResponse(body)

    def downloader_factory(config):
        return ResourceDownloader(config, urlopen_fn=fake_urlopen)

    monkeypatch.setattr(download_script, "ResourceDownloader", downloader_factory)

    exit_code = download_script.main(
        [
            *secure_args(tmp_path, allowlist_sha256=allowlist_sha256),
            "--workers",
            "1",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert json.loads(captured.out) == DownloadSummary(
        total=1,
        downloaded=1,
        bytes_downloaded=len(body),
    ).to_json()
    assert network_urls == [row["url"]]
    assert (staging_root / row["local_relpath"]).read_bytes() == body
    assert (staging_root / "download_receipt.v1.jsonl").is_file()
    assert not (tmp_path / "crawl_state.sqlite").exists()
