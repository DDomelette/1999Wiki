from __future__ import annotations

import json
import mimetypes
from pathlib import Path
from urllib.parse import quote

from config.config import AssetStorageCfg


class MinioObjectConflictError(RuntimeError):
    pass


class MinioAssetStorage:
    def __init__(self, cfg: AssetStorageCfg) -> None:
        if not cfg.access_key or not cfg.secret_key:
            raise ValueError("MINIO_ACCESS_KEY and MINIO_SECRET_KEY must be set in the environment")
        try:
            from minio import Minio
        except ModuleNotFoundError as exc:
            raise RuntimeError("minio package is required. Install it with: python -m pip install minio") from exc

        self._cfg = cfg
        self._client = Minio(
            cfg.endpoint,
            access_key=cfg.access_key,
            secret_key=cfg.secret_key,
            secure=cfg.secure,
        )
        if not self._client.bucket_exists(cfg.bucket_name):
            self._client.make_bucket(cfg.bucket_name)
        self._client.set_bucket_policy(cfg.bucket_name, self._public_read_policy(cfg.bucket_name))

    @staticmethod
    def _public_read_policy(bucket_name: str) -> str:
        return json.dumps({
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"AWS": ["*"]},
                    "Action": ["s3:GetObject"],
                    "Resource": [f"arn:aws:s3:::{bucket_name}/*"],
                }
            ],
        })

    def upload_file(self, local_path: Path, object_key: str, sha1: str = "") -> str:
        content_type = mimetypes.guess_type(str(local_path))[0] or "application/octet-stream"
        metadata = {"sha1": sha1} if sha1 else {}
        try:
            stat = self._client.stat_object(self._cfg.bucket_name, object_key)
        except Exception:
            stat = None

        if stat is not None:
            remote_sha1 = ""
            if hasattr(stat, "metadata") and stat.metadata:
                remote_sha1 = stat.metadata.get("X-Amz-Meta-Sha1", "") or stat.metadata.get("sha1", "")
            if sha1 and remote_sha1 and remote_sha1 != sha1:
                raise MinioObjectConflictError(
                    f"object_key conflict: {object_key} remote_sha1={remote_sha1} local_sha1={sha1}"
                )
            if int(getattr(stat, "size", -1)) == local_path.stat().st_size:
                quoted_key = quote(object_key, safe="/")
                return f"{self._cfg.public_base_url.rstrip('/')}/{self._cfg.bucket_name}/{quoted_key}"

        self._client.fput_object(
            self._cfg.bucket_name,
            object_key,
            str(local_path),
            content_type=content_type,
            metadata=metadata,
        )
        quoted_key = quote(object_key, safe="/")
        return f"{self._cfg.public_base_url.rstrip('/')}/{self._cfg.bucket_name}/{quoted_key}"
