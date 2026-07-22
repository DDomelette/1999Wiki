from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.audit_frontend_crawler_media import (
    APPLY_CONFIRMATION_TOKEN,
    audit_frontend_images,
    load_crawler_sha1s,
    prune_non_crawler_images,
)


def test_audit_frontend_images_matches_content_hashes_not_filenames(tmp_path: Path):
    manifest = tmp_path / "resources_manifest.jsonl"
    crawler_body = b"crawler"
    crawler_sha1 = hashlib.sha1(crawler_body).hexdigest()
    manifest.write_text(json.dumps({"sha1": crawler_sha1}) + "\n", encoding="utf-8")
    images = tmp_path / "public" / "images"
    images.mkdir(parents=True)
    (images / "renamed.png").write_bytes(crawler_body)
    (images / "foreign.png").write_bytes(b"foreign")

    rows = audit_frontend_images(images, load_crawler_sha1s(manifest))

    assert [(row.relative_path, row.crawler) for row in rows] == [
        ("foreign.png", False),
        ("renamed.png", True),
    ]


def test_prune_non_crawler_images_requires_confirmation_and_preserves_crawler_files(tmp_path: Path):
    images = tmp_path / "images"
    images.mkdir()
    crawler = images / "crawler.png"
    foreign = images / "nested" / "foreign.png"
    crawler.write_bytes(b"crawler")
    foreign.parent.mkdir()
    foreign.write_bytes(b"foreign")
    crawler_sha1 = hashlib.sha1(b"crawler").hexdigest()
    rows = audit_frontend_images(images, {crawler_sha1})

    with pytest.raises(ValueError, match="confirmation token"):
        prune_non_crawler_images(images, rows, confirmation="wrong")

    deleted = prune_non_crawler_images(
        images,
        rows,
        confirmation=APPLY_CONFIRMATION_TOKEN,
    )

    assert deleted == ("nested/foreign.png",)
    assert crawler.is_file()
    assert not foreign.exists()
