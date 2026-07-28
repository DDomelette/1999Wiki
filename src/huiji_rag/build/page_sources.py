"""Streaming crawler inputs, recovery evidence, and page/revision joins."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Iterator, Mapping

from .contracts import CRAWLER_SOURCE_FILENAMES

try:
    import psutil
except ImportError:  # pragma: no cover - development and production include psutil
    psutil = None


_REQUIRED_FIELDS = {
    "pages.jsonl": ("site", "pageid", "title"),
    "wikitext.jsonl": ("site", "pageid", "revid", "title"),
    "data_pages.jsonl": ("site", "pageid", "revid", "title"),
    "resources_manifest.jsonl": ("site", "title", "url"),
}


@dataclass(frozen=True)
class SourceDiagnostic:
    reason_code: str
    source_name: str
    line_number: int
    source_identity: str
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "details", MappingProxyType(dict(self.details)))

    def to_json(self) -> dict[str, Any]:
        return {
            "reason_code": self.reason_code,
            "source_name": self.source_name,
            "line_number": self.line_number,
            "source_identity": self.source_identity,
            "details": dict(self.details),
        }


@dataclass(frozen=True)
class SemanticSourceMetrics:
    source_name: str
    read_rows: int
    accepted_rows: int
    excluded_rows: int
    peak_rss_bytes: int | str
    elapsed_seconds: float
    reason_counts: Mapping[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "reason_counts", MappingProxyType(dict(sorted(self.reason_counts.items())))
        )


@dataclass(frozen=True)
class JsonlRow:
    row: Mapping[str, Any]
    source_name: str
    line_number: int
    byte_offset: int
    byte_length: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "row", MappingProxyType(dict(self.row)))

    def projection_row(self) -> dict[str, Any]:
        return {
            **self.row,
            "__source_file": self.source_name,
            "__source_line_number": self.line_number,
            "__source_byte_offset": self.byte_offset,
        }


class JsonlStream:
    """Repeatable binary JSONL stream with bounded row-level diagnostics."""

    def __init__(
        self,
        path: Path,
        *,
        source_name: str,
        max_line_bytes: int = 64 * 1024 * 1024,
    ) -> None:
        self.path = Path(path)
        self.source_name = source_name
        self.max_line_bytes = max(1, int(max_line_bytes))
        self.diagnostics: tuple[SourceDiagnostic, ...] = ()
        self.metrics = SemanticSourceMetrics(
            source_name=source_name,
            read_rows=0,
            accepted_rows=0,
            excluded_rows=0,
            peak_rss_bytes="unavailable",
            elapsed_seconds=0.0,
        )

    def __iter__(self) -> Iterator[JsonlRow]:
        before = _file_signature(self.path)
        started = time.monotonic()
        diagnostics: list[SourceDiagnostic] = []
        reason_counts: dict[str, int] = {}
        read_rows = 0
        accepted_rows = 0
        physical_line_number = 0
        peak_rss = _rss_bytes()
        with self.path.open("rb") as handle:
            while True:
                byte_offset = handle.tell()
                raw_line = handle.readline(self.max_line_bytes + 1)
                if not raw_line:
                    break
                physical_line_number += 1
                byte_length = len(raw_line)
                line_too_large = (
                    byte_length > self.max_line_bytes and not raw_line.endswith(b"\n")
                )
                if line_too_large:
                    while raw_line and not raw_line.endswith(b"\n"):
                        raw_line = handle.readline(self.max_line_bytes + 1)
                        byte_length += len(raw_line)
                if not raw_line.strip():
                    continue
                read_rows += 1
                peak_rss = _max_rss(peak_rss, _rss_bytes())
                reason_code = ""
                value: Any = None
                if line_too_large or byte_length > self.max_line_bytes:
                    reason_code = "line_too_large"
                else:
                    try:
                        text = raw_line.decode("utf-8")
                    except UnicodeDecodeError:
                        reason_code = "utf8_error"
                    else:
                        try:
                            value = json.loads(text)
                        except json.JSONDecodeError:
                            reason_code = "json_parse_error"
                        else:
                            if not isinstance(value, dict) or not _valid_schema(
                                self.source_name, value
                            ):
                                reason_code = "schema_error"
                if reason_code:
                    reason_counts[reason_code] = reason_counts.get(reason_code, 0) + 1
                    diagnostics.append(
                        SourceDiagnostic(
                            reason_code=reason_code,
                            source_name=self.source_name,
                            line_number=physical_line_number,
                            source_identity=f"{self.source_name}:{physical_line_number}",
                        )
                    )
                    continue
                accepted_rows += 1
                yield JsonlRow(
                    row=value,
                    source_name=self.source_name,
                    line_number=physical_line_number,
                    byte_offset=byte_offset,
                    byte_length=byte_length,
                )
        if _file_signature(self.path) != before:
            raise ValueError(f"crawler source changed while being read: {self.source_name}")
        self.diagnostics = tuple(diagnostics)
        self.metrics = SemanticSourceMetrics(
            source_name=self.source_name,
            read_rows=read_rows,
            accepted_rows=accepted_rows,
            excluded_rows=len(diagnostics),
            peak_rss_bytes=peak_rss,
            elapsed_seconds=max(0.0, time.monotonic() - started),
            reason_counts=reason_counts,
        )


@dataclass(frozen=True)
class CrawlerSemanticInputs:
    raw_root: Path
    source_filenames: tuple[str, ...] = CRAWLER_SOURCE_FILENAMES

    @classmethod
    def from_root(cls, raw_root: Path) -> "CrawlerSemanticInputs":
        root_input = Path(raw_root)
        if root_input.is_symlink():
            raise ValueError("crawler raw root must not be a symlink")
        root = root_input.resolve(strict=True)
        if not root.is_dir():
            raise FileNotFoundError(f"crawler raw root is not a directory: {root}")
        for filename in CRAWLER_SOURCE_FILENAMES:
            _contained_source_file(root, filename)
        return cls(raw_root=root)

    def pages(self) -> JsonlStream:
        return self._stream("pages.jsonl")

    def revisions(self) -> JsonlStream:
        return self._stream("wikitext.jsonl")

    def data_pages(self) -> JsonlStream:
        return self._stream("data_pages.jsonl")

    def resources(self) -> JsonlStream:
        return self._stream("resources_manifest.jsonl")

    def iter_data_page_mappings(self) -> Iterator[dict[str, Any]]:
        for item in self.data_pages():
            yield item.projection_row()

    def iter_resource_mappings(self) -> Iterator[dict[str, Any]]:
        for item in self.resources():
            yield item.projection_row()

    def _stream(self, filename: str) -> JsonlStream:
        return JsonlStream(
            _contained_source_file(self.raw_root, filename),
            source_name=filename,
        )


@dataclass(frozen=True)
class PageMetadata:
    pageid: int
    namespace: int
    title: str
    lastrevid: int
    status: str
    line_number: int


@dataclass(frozen=True)
class RevisionMetadata:
    pageid: int
    namespace: int
    title: str
    revid: int
    content_sha256: str
    line_number: int
    byte_offset: int
    byte_length: int


@dataclass(frozen=True)
class JoinedPageRevision:
    page: PageMetadata
    revision: RevisionMetadata


@dataclass(frozen=True)
class PageRevisionJoin:
    joined: tuple[JoinedPageRevision, ...]
    diagnostics: tuple[SourceDiagnostic, ...]
    blockers: tuple[str, ...]


@dataclass(frozen=True)
class RecoveryGateEvidence:
    snapshot_id: str
    invalid_payload_rows: int
    sqlite_quick_check: str
    data_pages_sha256: str
    crawl_state_sha256: str


def build_page_revision_join(
    page_rows: Iterator[JsonlRow] | JsonlStream,
    revision_rows: Iterator[JsonlRow] | JsonlStream,
) -> PageRevisionJoin:
    pages: dict[int, PageMetadata] = {}
    revisions: dict[tuple[int, int], RevisionMetadata] = {}
    page_conflicts: set[int] = set()
    revision_conflicts: set[tuple[int, int]] = set()
    diagnostics: list[SourceDiagnostic] = []

    for item in page_rows:
        row = item.row
        page = PageMetadata(
            pageid=int(row["pageid"]),
            namespace=int(row.get("ns", 0) or 0),
            title=str(row["title"]),
            lastrevid=int(row.get("lastrevid", 0) or 0),
            status=str(row.get("status") or "active"),
            line_number=item.line_number,
        )
        previous = pages.get(page.pageid)
        if previous is None:
            pages[page.pageid] = page
        elif _page_identity(previous) != _page_identity(page):
            page_conflicts.add(page.pageid)

    for item in revision_rows:
        row = item.row
        revision = RevisionMetadata(
            pageid=int(row["pageid"]),
            namespace=int(row.get("ns", 0) or 0),
            title=str(row["title"]),
            revid=int(row["revid"]),
            content_sha256=str(row.get("content_sha256") or ""),
            line_number=item.line_number,
            byte_offset=item.byte_offset,
            byte_length=item.byte_length,
        )
        key = (revision.pageid, revision.revid)
        previous = revisions.get(key)
        if previous is None:
            revisions[key] = revision
        elif _revision_identity(previous) != _revision_identity(revision):
            revision_conflicts.add(key)

    joined: list[JoinedPageRevision] = []
    for pageid, page in sorted(pages.items()):
        if pageid in page_conflicts:
            diagnostics.append(_join_diagnostic("page_identity_conflict", pageid))
            continue
        if page.namespace != 0:
            diagnostics.append(_join_diagnostic("non_main_namespace", pageid))
            continue
        if page.status != "active":
            diagnostics.append(_join_diagnostic("inactive_page", pageid))
            continue
        key = (pageid, page.lastrevid)
        if key in revision_conflicts:
            diagnostics.append(
                _join_diagnostic(
                    "revision_identity_conflict", pageid, revid=page.lastrevid
                )
            )
            continue
        revision = revisions.get(key)
        if revision is None:
            diagnostics.append(
                _join_diagnostic("missing_latest_revision", pageid, revid=page.lastrevid)
            )
            continue
        if revision.title != page.title or revision.namespace != page.namespace:
            diagnostics.append(
                _join_diagnostic("page_revision_identity_conflict", pageid)
            )
            continue
        joined.append(JoinedPageRevision(page=page, revision=revision))

    for pageid, revid in sorted(revisions):
        if pageid not in pages:
            diagnostics.append(_join_diagnostic("orphan_revision", pageid, revid=revid))

    blockers = [
        *(f"page_identity_conflict:{pageid}" for pageid in sorted(page_conflicts)),
        *(
            f"revision_identity_conflict:{pageid}:{revid}"
            for pageid, revid in sorted(revision_conflicts)
        ),
    ]
    diagnostics.sort(
        key=lambda item: (item.source_identity, item.reason_code, item.line_number)
    )
    return PageRevisionJoin(
        joined=tuple(joined),
        diagnostics=tuple(diagnostics),
        blockers=tuple(blockers),
    )


def validate_recovery_gate(
    raw_root: Path,
    *,
    manifest_path: Path,
    audit_receipt_path: Path,
    apply_receipt_path: Path,
) -> RecoveryGateEvidence:
    root = Path(raw_root).resolve(strict=True)
    manifest = _read_json_object(manifest_path, "recovery manifest")
    audit = _read_json_object(audit_receipt_path, "recovery audit receipt")
    apply = _read_json_object(apply_receipt_path, "recovery apply receipt")
    snapshot_id = str(manifest.get("snapshot_id") or "")
    if not snapshot_id:
        raise ValueError("recovery manifest snapshot_id is missing")
    if audit.get("status") != "ready" or audit.get("snapshot_id") != snapshot_id:
        raise ValueError("recovery audit receipt is not ready for this snapshot")
    if apply.get("status") != "completed" or apply.get("snapshot_id") != snapshot_id:
        raise ValueError("recovery apply receipt is not completed for this snapshot")
    files = manifest.get("files")
    apply_files = apply.get("files")
    if not isinstance(files, dict) or not isinstance(apply_files, dict):
        raise ValueError("recovery evidence file inventory is missing")
    data_spec = files.get("data_pages.jsonl")
    if not isinstance(data_spec, dict):
        raise ValueError("recovery manifest is missing data_pages.jsonl")
    expected_invalid_payload_rows = int(data_spec.get("invalid_payload_rows", -1))
    invalid_payload_rows = int(audit.get("invalid_payload_rows", -1))
    if (
        expected_invalid_payload_rows < 0
        or invalid_payload_rows != expected_invalid_payload_rows
    ):
        raise ValueError("recovery audit receipt invalid payload count mismatch")

    verified: dict[str, str] = {}
    for filename in ("data_pages.jsonl", "crawl_state.sqlite"):
        spec = files.get(filename)
        receipt = apply_files.get(filename)
        if not isinstance(spec, dict) or not isinstance(receipt, dict):
            raise ValueError(f"recovery evidence is missing {filename}")
        path = _contained_file(root, filename)
        expected_size = int(spec.get("size", -1))
        expected_sha256 = str(spec.get("sha256") or "").lower()
        digest = _hash_file(path)
        if path.stat().st_size != expected_size or digest != expected_sha256:
            raise ValueError(f"recovered {filename} identity mismatch")
        if (
            int(receipt.get("size", -1)) != expected_size
            or str(receipt.get("sha256") or "").lower() != expected_sha256
        ):
            raise ValueError(f"recovery apply receipt identity mismatch for {filename}")
        verified[filename] = digest

    rows = 0
    invalid = 0
    for item in JsonlStream(
        _contained_file(root, "data_pages.jsonl"),
        source_name="data_pages.jsonl",
    ):
        rows += 1
        if item.row.get("json_valid") is False:
            invalid += 1
    if int(data_spec.get("rows", rows)) != rows or invalid != invalid_payload_rows:
        raise ValueError("recovered data_pages.jsonl row evidence mismatch")

    sqlite_path = _contained_file(root, "crawl_state.sqlite")
    uri = sqlite_path.as_uri() + "?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        row = connection.execute("PRAGMA quick_check").fetchone()
    quick_check = str(row[0]) if row else "no result"
    if quick_check != "ok":
        raise ValueError(f"recovered crawl_state.sqlite quick_check: {quick_check}")
    return RecoveryGateEvidence(
        snapshot_id=snapshot_id,
        invalid_payload_rows=invalid_payload_rows,
        sqlite_quick_check=quick_check,
        data_pages_sha256=verified["data_pages.jsonl"],
        crawl_state_sha256=verified["crawl_state.sqlite"],
    )


def _valid_schema(source_name: str, row: Mapping[str, Any]) -> bool:
    required = _REQUIRED_FIELDS.get(source_name, ())
    return all(field in row and row[field] not in (None, "") for field in required)


def _contained_source_file(root: Path, filename: str) -> Path:
    if filename not in CRAWLER_SOURCE_FILENAMES:
        raise ValueError(f"unsupported crawler source file: {filename}")
    return _contained_file(root, filename)


def _contained_file(root: Path, filename: str) -> Path:
    raw = root / filename
    if raw.is_symlink():
        raise ValueError(f"crawler source must not be a symlink: {filename}")
    path = raw.resolve(strict=True)
    try:
        path.relative_to(root)
    except ValueError as error:
        raise ValueError(f"crawler source escapes raw root: {filename}") from error
    if not path.is_file() or path.suffix.casefold() == ".pyc":
        raise FileNotFoundError(f"crawler source file is missing: {filename}")
    return path


def _read_json_object(path: Path, label: str) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"{label} must contain a JSON object")
    return value


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _file_signature(path: Path) -> tuple[int, int]:
    stat = path.stat()
    return stat.st_size, stat.st_mtime_ns


def _rss_bytes() -> int | str:
    if psutil is None:
        return "unavailable"
    try:
        return int(psutil.Process().memory_info().rss)
    except (OSError, RuntimeError):
        return "unavailable"


def _max_rss(current: int | str, candidate: int | str) -> int | str:
    if isinstance(current, int) and isinstance(candidate, int):
        return max(current, candidate)
    if isinstance(candidate, int):
        return candidate
    return current


def _page_identity(page: PageMetadata) -> tuple[str, int, int, str]:
    return page.title, page.namespace, page.lastrevid, page.status


def _revision_identity(revision: RevisionMetadata) -> tuple[str, str]:
    return revision.title, revision.content_sha256


def _join_diagnostic(
    reason_code: str,
    pageid: int,
    *,
    revid: int | None = None,
) -> SourceDiagnostic:
    source_identity = f"page:{pageid}"
    details: dict[str, Any] = {"pageid": pageid}
    if revid is not None:
        source_identity += f":revision:{revid}"
        details["revid"] = revid
    return SourceDiagnostic(
        reason_code=reason_code,
        source_name="page_revision_join",
        line_number=0,
        source_identity=source_identity,
        details=details,
    )
