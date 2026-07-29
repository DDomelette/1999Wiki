from __future__ import annotations

import hashlib
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from src.huiji_rag.build.contracts import (
    MEDIA_DOWNLOAD_APPROVAL_SCHEMA_VERSION,
    MEDIA_DOWNLOAD_RECEIPT_SCHEMA_VERSION,
    REFERENCED_MEDIA_ALLOWLIST_ENTRY_SCHEMA_VERSION,
    canonical_json_bytes,
)


ALLOWED_RESOURCE_HOST_SUFFIXES = ("huijistatic.com",)


class ApprovalRequiredError(RuntimeError):
    """Raised before any network or staging write when approval is absent."""


@dataclass(frozen=True)
class DownloadConfig:
    staging_root: Path
    allowlist_path: Path
    expected_allowlist_sha256: str
    expected_source_inventory_sha256: str
    approval_path: Path
    staging_receipt_path: Path
    workers: int
    timeout: float = 30.0
    retries: int = 2
    sleep: float = 0.2
    log_every: int = 100
    user_agent: str = "1999Search-resource-downloader/2.0"

    def __post_init__(self) -> None:
        for field_name in (
            "staging_root",
            "allowlist_path",
            "approval_path",
            "staging_receipt_path",
        ):
            object.__setattr__(self, field_name, Path(getattr(self, field_name)))
        if self.workers < 1:
            raise ValueError("download worker count must be positive")


@dataclass(frozen=True)
class DownloadJob:
    resource_id: str
    binding_ids: tuple[str, ...]
    name: str
    url: str
    local_relpath: str
    size: int
    sha1: str
    content_sha256: str
    expected_download_bytes: int
    mime: str | None


@dataclass(frozen=True)
class DownloadResult:
    job: DownloadJob
    status: str
    bytes_written: int = 0
    error: str | None = None


@dataclass
class DownloadSummary:
    total: int = 0
    downloaded: int = 0
    skipped: int = 0
    failed: int = 0
    bytes_downloaded: int = 0

    def to_json(self) -> dict[str, int]:
        return {
            "total": self.total,
            "downloaded": self.downloaded,
            "skipped": self.skipped,
            "failed": self.failed,
            "bytes_downloaded": self.bytes_downloaded,
        }


class ResourceDownloader:
    def __init__(
        self,
        config: DownloadConfig,
        urlopen_fn: Callable[..., object] = urlopen,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        self.config = config
        self.staging_root = config.staging_root.resolve()
        self.urlopen_fn = urlopen_fn
        self.sleep_fn = sleep_fn

    def run(
        self,
        progress_fn: Callable[[int, DownloadSummary, DownloadResult], None] | None = None,
    ) -> DownloadSummary:
        approval = self._load_approval()
        jobs = tuple(self._load_allowlist())
        self._verify_approval(approval, jobs)
        summary = DownloadSummary(total=len(jobs))
        if not jobs:
            return summary

        with ThreadPoolExecutor(max_workers=self.config.workers) as executor:
            futures = [executor.submit(self.download_one, job) for job in jobs]
            for done, future in enumerate(as_completed(futures), start=1):
                result = future.result()
                if result.status == "downloaded":
                    summary.downloaded += 1
                    summary.bytes_downloaded += result.bytes_written
                elif result.status == "skipped":
                    summary.skipped += 1
                else:
                    summary.failed += 1
                self._append_receipt(result)
                if progress_fn is not None:
                    progress_fn(done, summary, result)
        return summary

    def _load_approval(self) -> Mapping[str, Any]:
        if not self.config.approval_path.is_file():
            raise ApprovalRequiredError(
                "explicit approval metadata is required before download"
            )
        try:
            approval = json.loads(
                self.config.approval_path.read_text(encoding="utf-8")
            )
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise ApprovalRequiredError(
                "explicit approval metadata is invalid"
            ) from error
        if (
            not isinstance(approval, dict)
            or approval.get("schema_version")
            != MEDIA_DOWNLOAD_APPROVAL_SCHEMA_VERSION
            or approval.get("approval_state") != "approved"
        ):
            raise ApprovalRequiredError(
                "explicit approval metadata is not approved"
            )
        return approval

    def _load_allowlist(self) -> Iterable[DownloadJob]:
        try:
            payload = self.config.allowlist_path.read_bytes()
        except OSError as error:
            raise ValueError("approved allowlist is unavailable") from error
        actual_sha256 = hashlib.sha256(payload).hexdigest()
        if actual_sha256 != self.config.expected_allowlist_sha256:
            raise ValueError("approved allowlist SHA-256 does not match")
        seen_resources: set[str] = set()
        for line_number, raw_line in enumerate(payload.splitlines(), start=1):
            if not raw_line.strip():
                continue
            try:
                row = json.loads(raw_line.decode("utf-8"))
            except (UnicodeError, json.JSONDecodeError) as error:
                raise ValueError(
                    f"approved allowlist row {line_number} is invalid"
                ) from error
            yield self._allowlist_job(row, line_number, seen_resources)

    def _allowlist_job(
        self,
        row: object,
        line_number: int,
        seen_resources: set[str],
    ) -> DownloadJob:
        if (
            not isinstance(row, dict)
            or row.get("schema_version")
            != REFERENCED_MEDIA_ALLOWLIST_ENTRY_SCHEMA_VERSION
        ):
            raise ValueError(f"approved allowlist row {line_number} has wrong schema")
        required = (
            "resource_id",
            "binding_ids",
            "filename",
            "url",
            "local_relpath",
            "size",
            "sha1",
            "content_sha256",
            "expected_download_bytes",
        )
        if any(field not in row for field in required):
            raise ValueError(
                f"approved allowlist row {line_number} is missing required fields"
            )
        resource_id = str(row["resource_id"])
        if not resource_id or resource_id in seen_resources:
            raise ValueError("approved allowlist resource IDs must be unique")
        seen_resources.add(resource_id)
        binding_ids = row["binding_ids"]
        if (
            not isinstance(binding_ids, list)
            or not binding_ids
            or any(not isinstance(value, str) or not value for value in binding_ids)
            or binding_ids != sorted(set(binding_ids))
        ):
            raise ValueError("approved allowlist binding IDs must be sorted and unique")
        size = int(row["size"])
        expected_download_bytes = int(row["expected_download_bytes"])
        if size < 0 or expected_download_bytes not in {0, size}:
            raise ValueError("approved allowlist expected bytes are invalid")
        sha1 = str(row["sha1"]).lower()
        sha256 = str(row["content_sha256"]).lower()
        if len(sha1) != 40 or any(value not in "0123456789abcdef" for value in sha1):
            raise ValueError("approved allowlist SHA-1 is invalid")
        if len(sha256) != 64 or any(
            value not in "0123456789abcdef" for value in sha256
        ):
            raise ValueError("approved allowlist SHA-256 is invalid")
        return DownloadJob(
            resource_id=resource_id,
            binding_ids=tuple(binding_ids),
            name=str(row["filename"]),
            url=str(row["url"]),
            local_relpath=str(row["local_relpath"]),
            size=size,
            sha1=sha1,
            content_sha256=sha256,
            expected_download_bytes=expected_download_bytes,
            mime=str(row["mime"]) if row.get("mime") else None,
        )

    def _verify_approval(
        self, approval: Mapping[str, Any], jobs: tuple[DownloadJob, ...]
    ) -> None:
        expected_bytes = sum(job.expected_download_bytes for job in jobs)
        expected = {
            "allowlist_sha256": self.config.expected_allowlist_sha256,
            "source_inventory_sha256": (
                self.config.expected_source_inventory_sha256
            ),
            "expected_bytes": expected_bytes,
            "workers": self.config.workers,
            "staging_root": str(self.staging_root),
        }
        for field, value in expected.items():
            if approval.get(field) != value:
                raise ValueError(f"download approval {field} does not match")
        receipt = self.config.staging_receipt_path.resolve()
        if receipt.name.lower() == "crawl_state.sqlite":
            raise ValueError("canonical crawl state cannot be a download receipt")
        if receipt == self.staging_root or self.staging_root not in receipt.parents:
            raise ValueError("download receipt must remain below staging root")

    def download_one(self, job: DownloadJob) -> DownloadResult:
        part: Path | None = None
        try:
            target = self._target_path(job.local_relpath)
            self._guard_url(job.url)
            if self._is_valid_file(target, job):
                return DownloadResult(job=job, status="skipped")
            if job.expected_download_bytes == 0:
                return DownloadResult(
                    job=job,
                    status="failed",
                    error="approved job permits no download bytes",
                )
            target.parent.mkdir(parents=True, exist_ok=True)
            part = target.with_name(target.name + ".part")
            self._download_to_part(job, part)
            if not self._is_valid_file(part, job):
                if part.exists():
                    part.unlink()
                return DownloadResult(
                    job=job,
                    status="failed",
                    error="downloaded file failed size or digest validation",
                )
            os.replace(part, target)
            return DownloadResult(
                job=job,
                status="downloaded",
                bytes_written=target.stat().st_size,
            )
        except Exception as error:
            if part is not None and part.exists():
                part.unlink()
            return DownloadResult(
                job=job,
                status="failed",
                error=f"{type(error).__name__}: {error}",
            )

    def _download_to_part(self, job: DownloadJob, part: Path) -> None:
        last_error: Exception | None = None
        for attempt in range(self.config.retries + 1):
            try:
                self._download_once(job, part)
                return
            except Exception as error:
                last_error = error
                if attempt < self.config.retries:
                    self.sleep_fn(max(0.0, self.config.sleep) * (attempt + 1))
        if last_error is not None:
            raise last_error

    def _download_once(self, job: DownloadJob, part: Path) -> None:
        headers = {"User-Agent": self.config.user_agent, "Accept": "*/*"}
        mode = "wb"
        resume_from = part.stat().st_size if part.exists() else 0
        if 0 < resume_from < job.size:
            headers["Range"] = f"bytes={resume_from}-"
            mode = "ab"
        elif resume_from >= job.size:
            return
        request = Request(job.url, headers=headers)
        with self.urlopen_fn(request, timeout=self.config.timeout) as response:
            status = int(getattr(response, "status", 200) or 200)
            if mode == "ab" and status != 206:
                mode = "wb"
            if status >= 400:
                raise RuntimeError(f"HTTP {status}")
            with part.open(mode) as handle:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    handle.write(chunk)

    def _target_path(self, local_relpath: str) -> Path:
        target = (self.staging_root / local_relpath).resolve()
        if target == self.staging_root or self.staging_root not in target.parents:
            raise ValueError("resource path escapes staging root")
        return target

    def _guard_url(self, url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme != "https":
            raise ValueError("blocked non-https resource URL")
        host = (parsed.hostname or "").lower()
        if not any(
            host == suffix or host.endswith("." + suffix)
            for suffix in ALLOWED_RESOURCE_HOST_SUFFIXES
        ):
            raise ValueError("blocked resource host")

    def _is_valid_file(self, path: Path, job: DownloadJob) -> bool:
        if not path.is_file() or path.stat().st_size != job.size:
            return False
        sha1, sha256 = _file_digests(path)
        return sha1 == job.sha1 and sha256 == job.content_sha256

    def _append_receipt(self, result: DownloadResult) -> None:
        receipt = self.config.staging_receipt_path.resolve()
        receipt.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "schema_version": MEDIA_DOWNLOAD_RECEIPT_SCHEMA_VERSION,
            "allowlist_sha256": self.config.expected_allowlist_sha256,
            "source_inventory_sha256": (
                self.config.expected_source_inventory_sha256
            ),
            "resource_id": result.job.resource_id,
            "binding_ids": list(result.job.binding_ids),
            "status": result.status,
            "bytes_written": result.bytes_written,
            "error": result.error,
        }
        with receipt.open("ab") as handle:
            handle.write(canonical_json_bytes(record))


def _file_digests(path: Path) -> tuple[str, str]:
    sha1 = hashlib.sha1()
    sha256 = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            sha1.update(chunk)
            sha256.update(chunk)
    return sha1.hexdigest(), sha256.hexdigest()
