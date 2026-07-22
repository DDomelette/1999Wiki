from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from src.huiji_wiki.crawler_media_migration import (
    CrawlerMediaAudit,
    CrawlerMediaConflictError,
    audit_crawler_media_objects,
    build_crawler_media_operations,
    delete_private_media_prefix,
    upload_missing_crawler_media,
)


def _write_asset(root: Path, relative_path: str, body: bytes) -> tuple[str, int]:
    target = root / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(body)
    return hashlib.sha1(body).hexdigest(), len(body)


def test_build_crawler_media_operations_uses_only_verified_shared_objects(tmp_path: Path):
    sha1, size = _write_asset(tmp_path, "assets/files/a/Headicon_large-300301.webp", b"avatar")
    key = f"reverse1999/portrait/{sha1[:2]}/{sha1}.webp"
    links = [
        {
            "source_kind": "huiji_crawler",
            "local_relpath": "assets/files/a/Headicon_large-300301.webp",
            "object_key": key,
            "sha1": sha1,
            "mime": "image/webp",
        },
        {
            "source_kind": "huiji_crawler",
            "local_relpath": "assets/files/a/Headicon_large-300301.webp",
            "object_key": key,
            "sha1": sha1,
            "mime": "image/webp",
        },
        {"source_kind": "processed_artifact", "object_key": "reverse1999/voice/a.mp3"},
    ]

    operations = build_crawler_media_operations(links, tmp_path, object_prefix="reverse1999")

    assert len(operations) == 1
    assert operations[0].object_key == key
    assert operations[0].sha1 == sha1
    assert operations[0].size == size
    assert operations[0].local_path == (tmp_path / "assets/files/a/Headicon_large-300301.webp").resolve()


def test_build_crawler_media_operations_rejects_private_prefix_and_hash_mismatch(tmp_path: Path):
    sha1, _ = _write_asset(tmp_path, "assets/files/a/item.webp", b"crawler")
    base = {
        "source_kind": "huiji_crawler",
        "local_relpath": "assets/files/a/item.webp",
        "sha1": sha1,
        "mime": "image/webp",
    }

    with pytest.raises(CrawlerMediaConflictError, match="shared object prefix"):
        build_crawler_media_operations(
            [{**base, "object_key": f"reverse1999/wiki-supplement/{sha1}.webp"}],
            tmp_path,
            object_prefix="reverse1999",
        )
    with pytest.raises(CrawlerMediaConflictError, match="sha1 mismatch"):
        build_crawler_media_operations(
            [{**base, "sha1": "0" * 40, "object_key": f"reverse1999/image/00/{'0' * 40}.webp"}],
            tmp_path,
            object_prefix="reverse1999",
        )


def test_audit_crawler_media_objects_separates_existing_missing_and_conflicts(tmp_path: Path):
    first_sha1, _ = _write_asset(tmp_path, "assets/files/a/first.webp", b"first")
    second_sha1, _ = _write_asset(tmp_path, "assets/files/b/second.webp", b"second")
    third_sha1, _ = _write_asset(tmp_path, "assets/files/c/third.webp", b"third")
    operations = build_crawler_media_operations(
        [
            {
                "source_kind": "huiji_crawler",
                "local_relpath": f"assets/files/{letter}/{name}.webp",
                "object_key": f"reverse1999/image/{sha1[:2]}/{sha1}.webp",
                "sha1": sha1,
                "mime": "image/webp",
            }
            for letter, name, sha1 in (
                ("a", "first", first_sha1),
                ("b", "second", second_sha1),
                ("c", "third", third_sha1),
            )
        ],
        tmp_path,
        object_prefix="reverse1999",
    )

    class Client:
        def stat_object(self, _bucket, key):
            if second_sha1 in key:
                raise FileNotFoundError(key)
            operation = next(item for item in operations if item.object_key == key)
            size = operation.size + 1 if third_sha1 in key else operation.size
            return type("Stat", (), {"size": size})()

    audit = audit_crawler_media_objects(Client(), "reverse1999-assets", operations)

    assert [item.object_key for item in audit.existing] == [operations[0].object_key]
    assert [item.object_key for item in audit.missing] == [operations[1].object_key]
    assert [item.object_key for item in audit.conflicts] == [operations[2].object_key]


def test_upload_missing_crawler_media_refuses_conflicts_and_uploads_only_missing(tmp_path: Path):
    sha1, size = _write_asset(tmp_path, "assets/files/a/item.webp", b"crawler")
    operation = build_crawler_media_operations(
        [
            {
                "source_kind": "huiji_crawler",
                "local_relpath": "assets/files/a/item.webp",
                "object_key": f"reverse1999/image/{sha1[:2]}/{sha1}.webp",
                "sha1": sha1,
                "mime": "image/webp",
            }
        ],
        tmp_path,
        object_prefix="reverse1999",
    )[0]

    class Client:
        def __init__(self):
            self.uploads = []

        def put_object(self, bucket, key, stream, length, content_type, metadata):
            self.uploads.append((bucket, key, stream.read(), length, content_type, metadata))

    client = Client()
    with pytest.raises(CrawlerMediaConflictError, match="remote object conflicts"):
        upload_missing_crawler_media(
            client,
            "reverse1999-assets",
            CrawlerMediaAudit(existing=(), missing=(), conflicts=(operation,)),
        )

    uploaded = upload_missing_crawler_media(
        client,
        "reverse1999-assets",
        CrawlerMediaAudit(existing=(), missing=(operation,), conflicts=()),
    )

    assert uploaded == (operation,)
    assert client.uploads == [
        (
            "reverse1999-assets",
            operation.object_key,
            b"crawler",
            size,
            "image/webp",
            {"sha1": sha1, "source-kind": "huiji-crawler"},
        )
    ]


def test_delete_private_media_prefix_is_narrow_and_reports_deleted_keys():
    class Client:
        def __init__(self):
            self.deleted = []

        def list_objects(self, _bucket, prefix, recursive):
            assert prefix == "reverse1999/wiki-supplement/"
            assert recursive is True
            return [
                type("Object", (), {"object_name": "reverse1999/wiki-supplement/a.webp"})(),
                type("Object", (), {"object_name": "reverse1999/wiki-supplement/b.webp"})(),
            ]

        def remove_object(self, bucket, key):
            self.deleted.append((bucket, key))

    client = Client()
    with pytest.raises(ValueError, match="exact legacy private prefix"):
        delete_private_media_prefix(client, "reverse1999-assets", "reverse1999/")

    deleted = delete_private_media_prefix(
        client,
        "reverse1999-assets",
        "reverse1999/wiki-supplement/",
    )

    assert deleted == (
        "reverse1999/wiki-supplement/a.webp",
        "reverse1999/wiki-supplement/b.webp",
    )
