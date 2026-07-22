from __future__ import annotations

import sys
import types
import inspect
from pathlib import Path

import pytest

from config.config import AssetStorageCfg


class FakeStat:
    def __init__(self, size: int, metadata: dict[str, str] | None = None) -> None:
        self.size = size
        self.metadata = metadata or {}


class FakeMinioClient:
    existing: dict[str, FakeStat] = {}
    uploads: list[tuple[str, str, str, dict[str, str]]] = []

    def __init__(self, *args, **kwargs) -> None:
        pass

    def bucket_exists(self, bucket_name: str) -> bool:
        return True

    def make_bucket(self, bucket_name: str) -> None:
        raise AssertionError("bucket already exists in fake")

    def set_bucket_policy(self, bucket_name: str, policy: str) -> None:
        pass

    def stat_object(self, bucket_name: str, object_key: str) -> FakeStat:
        if object_key not in self.existing:
            raise FileNotFoundError(object_key)
        return self.existing[object_key]

    def fput_object(
        self,
        bucket_name: str,
        object_key: str,
        local_path: str,
        content_type: str,
        metadata=None,
    ) -> None:
        self.uploads.append((bucket_name, object_key, local_path, metadata or {}))
        self.existing[object_key] = FakeStat(Path(local_path).stat().st_size, metadata or {})


@pytest.fixture(autouse=True)
def fake_minio_module(monkeypatch):
    FakeMinioClient.existing = {}
    FakeMinioClient.uploads = []
    module = types.SimpleNamespace(Minio=FakeMinioClient)
    monkeypatch.setitem(sys.modules, "minio", module)


def _cfg() -> AssetStorageCfg:
    return AssetStorageCfg(
        provider="minio",
        endpoint="127.0.0.1:9002",
        public_base_url="http://127.0.0.1:9002",
        bucket_name="reverse1999-assets",
        secure=False,
        object_prefix="reverse1999",
        access_key="minioadmin",
        secret_key="minioadmin",
    )


def test_upload_file_skips_existing_matching_object(tmp_path):
    from src.assets.minio_store import MinioAssetStorage

    local = tmp_path / "asset.png"
    local.write_bytes(b"same")
    object_key = "reverse1999/image/ab/abc.png"
    FakeMinioClient.existing[object_key] = FakeStat(
        size=4,
        metadata={"X-Amz-Meta-Sha1": "abc"},
    )

    storage = MinioAssetStorage(_cfg())
    url = storage.upload_file(local, object_key, sha1="abc")

    assert url == "http://127.0.0.1:9002/reverse1999-assets/reverse1999/image/ab/abc.png"
    assert FakeMinioClient.uploads == []


def test_upload_file_raises_on_existing_different_sha1(tmp_path):
    from src.assets.minio_store import MinioAssetStorage, MinioObjectConflictError

    local = tmp_path / "asset.png"
    local.write_bytes(b"new")
    object_key = "reverse1999/image/ab/abc.png"
    FakeMinioClient.existing[object_key] = FakeStat(
        size=3,
        metadata={"X-Amz-Meta-Sha1": "different"},
    )

    storage = MinioAssetStorage(_cfg())

    with pytest.raises(MinioObjectConflictError):
        storage.upload_file(local, object_key, sha1="abc")


def test_evb_strict_uploader_does_not_reuse_mutating_storage_helper():
    from src.huiji_rag import minio_strict

    source = inspect.getsource(minio_strict)
    forbidden = (
        "MinioAssetStorage",
        ".put_object(",
        ".fput_object(",
        ".make_bucket(",
        ".set_bucket_policy(",
        ".remove_object(",
    )
    assert all(token not in source for token in forbidden)
