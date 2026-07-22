from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable
from urllib.parse import urlparse
from urllib.request import Request, urlopen


ALLOWED_RESOURCE_HOST_SUFFIXES = ("huijistatic.com",)


@dataclass(frozen=True)
class DownloadConfig:
    out: Path
    db_path: str | Path
    workers: int = 2
    limit: int | None = None
    timeout: float = 30.0
    retries: int = 2
    sleep: float = 0.2
    include_failed: bool = False
    mime_prefixes: tuple[str, ...] = ()
    log_every: int = 100
    user_agent: str = "1999Search-resource-downloader/1.0"


@dataclass(frozen=True)
class DownloadJob:
    name: str
    url: str
    local_relpath: str
    size: int | None
    sha1: str | None
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
        self.out = Path(config.out).resolve()
        self.db_path = Path(config.db_path)
        self.urlopen_fn = urlopen_fn
        self.sleep_fn = sleep_fn
        self.error_log = self.out / "resource_download_errors.jsonl"

    def run(self, progress_fn: Callable[[int, DownloadSummary, DownloadResult], None] | None = None) -> DownloadSummary:
        jobs = list(self.iter_jobs())
        summary = DownloadSummary(total=len(jobs))
        if not jobs:
            return summary

        workers = max(1, int(self.config.workers))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(self.download_one, job) for job in jobs]
            for done, future in enumerate(as_completed(futures), start=1):
                result = future.result()
                self._apply_result(result)
                if result.status == "downloaded":
                    summary.downloaded += 1
                    summary.bytes_downloaded += result.bytes_written
                elif result.status == "skipped":
                    summary.skipped += 1
                else:
                    summary.failed += 1
                    self._log_error(result)
                if progress_fn is not None:
                    progress_fn(done, summary, result)
        return summary

    def iter_jobs(self) -> Iterable[DownloadJob]:
        statuses = ["not_downloaded"]
        if self.config.include_failed:
            statuses.append("failed")
        placeholders = ",".join("?" for _ in statuses)
        params: list[object] = list(statuses)
        where = [f"download_status IN ({placeholders})", "url != ''"]
        for prefix in self.config.mime_prefixes:
            where.append("mime LIKE ?")
            params.append(f"{prefix}%")
        sql = (
            "SELECT name, url, local_relpath, size, sha1, mime FROM resources "
            f"WHERE {' AND '.join(where)} ORDER BY name"
        )
        if self.config.limit is not None:
            sql += " LIMIT ?"
            params.append(int(self.config.limit))

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            for row in conn.execute(sql, params):
                yield DownloadJob(
                    name=str(row["name"]),
                    url=str(row["url"]),
                    local_relpath=str(row["local_relpath"]),
                    size=int(row["size"]) if row["size"] is not None else None,
                    sha1=str(row["sha1"]) if row["sha1"] else None,
                    mime=str(row["mime"]) if row["mime"] else None,
                )

    def download_one(self, job: DownloadJob) -> DownloadResult:
        try:
            target = self._target_path(job.local_relpath)
            self._guard_url(job.url)
            if self._is_valid_file(target, job):
                return DownloadResult(job=job, status="skipped", bytes_written=0)
            target.parent.mkdir(parents=True, exist_ok=True)
            part = target.with_name(target.name + ".part")
            self._download_to_part(job, part)
            if not self._is_valid_file(part, job):
                if part.exists():
                    part.unlink()
                return DownloadResult(job=job, status="failed", error="downloaded file failed size or sha1 validation")
            shutil.move(str(part), str(target))
            return DownloadResult(job=job, status="downloaded", bytes_written=target.stat().st_size)
        except Exception as exc:
            return DownloadResult(job=job, status="failed", error=f"{type(exc).__name__}: {exc}")

    def _download_to_part(self, job: DownloadJob, part: Path) -> None:
        last_error: Exception | None = None
        for attempt in range(int(self.config.retries) + 1):
            try:
                self._download_once(job, part)
                return
            except Exception as exc:
                last_error = exc
                if attempt < int(self.config.retries):
                    self.sleep_fn(max(0.0, float(self.config.sleep)) * (attempt + 1))
        if last_error is not None:
            raise last_error

    def _download_once(self, job: DownloadJob, part: Path) -> None:
        headers = {"User-Agent": self.config.user_agent, "Accept": "*/*"}
        mode = "wb"
        resume_from = part.stat().st_size if part.exists() else 0
        if resume_from > 0 and (job.size is None or resume_from < job.size):
            headers["Range"] = f"bytes={resume_from}-"
            mode = "ab"
        elif job.size is not None and resume_from >= job.size:
            return

        request = Request(job.url, headers=headers)
        with self.urlopen_fn(request, timeout=self.config.timeout) as response:
            status = int(getattr(response, "status", 200) or 200)
            if mode == "ab" and status != 206:
                mode = "wb"
            if status >= 400:
                raise RuntimeError(f"HTTP {status}")
            with part.open(mode + "") as handle:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    handle.write(chunk)

    def _target_path(self, local_relpath: str) -> Path:
        target = (self.out / local_relpath).resolve()
        if target != self.out and self.out not in target.parents:
            raise ValueError(f"resource path escapes output directory: {local_relpath}")
        return target

    def _guard_url(self, url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme != "https":
            raise ValueError(f"blocked non-https resource URL: {url}")
        host = parsed.netloc.lower()
        if not any(host == suffix or host.endswith("." + suffix) for suffix in ALLOWED_RESOURCE_HOST_SUFFIXES):
            raise ValueError(f"blocked resource host: {host}")

    def _is_valid_file(self, path: Path, job: DownloadJob) -> bool:
        if not path.exists() or not path.is_file():
            return False
        if job.size is not None and path.stat().st_size != int(job.size):
            return False
        if job.sha1:
            return _file_sha1(path) == job.sha1.lower()
        return True

    def _apply_result(self, result: DownloadResult) -> None:
        status = "downloaded" if result.status in {"downloaded", "skipped"} else "failed"
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("UPDATE resources SET download_status=? WHERE name=?", (status, result.job.name))

    def _log_error(self, result: DownloadResult) -> None:
        self.error_log.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "name": result.job.name,
            "url": result.job.url,
            "local_relpath": result.job.local_relpath,
            "mime": result.job.mime,
            "error": result.error,
        }
        with self.error_log.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def _file_sha1(path: Path) -> str:
    digest = hashlib.sha1()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
