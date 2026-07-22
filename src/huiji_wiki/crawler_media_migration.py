from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Any, Iterable, Mapping


class CrawlerMediaConflictError(ValueError):
    """Raised when crawler media cannot be mapped to a verified shared object."""


@dataclass(frozen=True)
class CrawlerMediaOperation:
    object_key: str
    local_path: Path
    sha1: str
    mime: str
    size: int


@dataclass(frozen=True)
class CrawlerMediaAudit:
    existing: tuple[CrawlerMediaOperation, ...]
    missing: tuple[CrawlerMediaOperation, ...]
    conflicts: tuple[CrawlerMediaOperation, ...]


def _sha1_file(path: Path) -> str:
    digest = hashlib.sha1()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _required_text(link: Mapping[str, Any], field: str) -> str:
    value = str(link.get(field) or "").strip()
    if not value:
        raise CrawlerMediaConflictError(f"crawler media is missing {field}")
    return value


def build_crawler_media_operations(
    media_links: Iterable[Mapping[str, Any]],
    raw_root: str | Path,
    *,
    object_prefix: str,
) -> tuple[CrawlerMediaOperation, ...]:
    root = Path(raw_root).resolve()
    prefix = object_prefix.strip("/")
    allowed_prefixes = (f"{prefix}/image/", f"{prefix}/portrait/")
    operations: dict[str, CrawlerMediaOperation] = {}

    for link in media_links:
        if link.get("source_kind") != "huiji_crawler":
            continue

        relative_path = _required_text(link, "local_relpath")
        object_key = _required_text(link, "object_key").replace("\\", "/")
        declared_sha1 = _required_text(link, "sha1").lower()
        mime = _required_text(link, "mime")

        local_path = (root / relative_path).resolve()
        if not local_path.is_relative_to(root):
            raise CrawlerMediaConflictError(f"crawler media escapes raw root: {relative_path}")
        if not local_path.is_file():
            raise CrawlerMediaConflictError(f"crawler media file is missing: {relative_path}")
        if not object_key.startswith(allowed_prefixes):
            raise CrawlerMediaConflictError(
                f"crawler media must use shared object prefix {allowed_prefixes}: {object_key}"
            )

        actual_sha1 = _sha1_file(local_path)
        if actual_sha1 != declared_sha1:
            raise CrawlerMediaConflictError(
                f"crawler media sha1 mismatch for {relative_path}: "
                f"declared={declared_sha1}, actual={actual_sha1}"
            )
        if Path(object_key).stem.lower() != declared_sha1:
            raise CrawlerMediaConflictError(
                f"object key sha1 mismatch for {relative_path}: {object_key}"
            )

        operation = CrawlerMediaOperation(
            object_key=object_key,
            local_path=local_path,
            sha1=declared_sha1,
            mime=mime,
            size=local_path.stat().st_size,
        )
        previous = operations.get(object_key)
        if previous is not None and previous != operation:
            raise CrawlerMediaConflictError(f"conflicting crawler media mapping: {object_key}")
        operations[object_key] = operation

    return tuple(operations.values())


def _is_missing_object_error(error: Exception) -> bool:
    if isinstance(error, FileNotFoundError):
        return True
    return str(getattr(error, "code", "")) in {"NoSuchKey", "NoSuchObject", "NotFound"}


def audit_crawler_media_objects(
    client: Any,
    bucket: str,
    operations: Iterable[CrawlerMediaOperation],
) -> CrawlerMediaAudit:
    existing: list[CrawlerMediaOperation] = []
    missing: list[CrawlerMediaOperation] = []
    conflicts: list[CrawlerMediaOperation] = []

    for operation in operations:
        try:
            remote = client.stat_object(bucket, operation.object_key)
        except Exception as error:
            if not _is_missing_object_error(error):
                raise
            missing.append(operation)
            continue
        if int(remote.size) == operation.size:
            existing.append(operation)
        else:
            conflicts.append(operation)

    return CrawlerMediaAudit(
        existing=tuple(existing),
        missing=tuple(missing),
        conflicts=tuple(conflicts),
    )


def upload_missing_crawler_media(
    client: Any,
    bucket: str,
    audit: CrawlerMediaAudit,
) -> tuple[CrawlerMediaOperation, ...]:
    if audit.conflicts:
        keys = ", ".join(item.object_key for item in audit.conflicts[:5])
        raise CrawlerMediaConflictError(f"remote object conflicts must be resolved first: {keys}")

    uploaded: list[CrawlerMediaOperation] = []
    for operation in audit.missing:
        with operation.local_path.open("rb") as stream:
            client.put_object(
                bucket,
                operation.object_key,
                stream,
                operation.size,
                content_type=operation.mime,
                metadata={"sha1": operation.sha1, "source-kind": "huiji-crawler"},
            )
        uploaded.append(operation)
    return tuple(uploaded)


def delete_private_media_prefix(
    client: Any,
    bucket: str,
    private_prefix: str,
) -> tuple[str, ...]:
    normalized = private_prefix.strip("/")
    if not normalized.endswith("/wiki-supplement"):
        raise ValueError("cleanup requires the exact legacy private prefix")
    prefix = normalized + "/"
    keys = tuple(
        str(item.object_name)
        for item in client.list_objects(bucket, prefix=prefix, recursive=True)
    )
    for key in keys:
        if not key.startswith(prefix):
            raise CrawlerMediaConflictError(f"private prefix listing escaped cleanup boundary: {key}")
        client.remove_object(bucket, key)
    return keys
