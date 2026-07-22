from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class IntegrityConfig:
    out: Path
    db_path: Path | None = None
    verify_resource_files: bool = True
    verify_resource_hash: bool = True
    issue_limit: int = 200


@dataclass(frozen=True)
class IntegrityIssue:
    severity: str
    code: str
    message: str
    ref: str = ""

    def to_json(self) -> dict[str, str]:
        return {
            "severity": self.severity,
            "code": self.code,
            "ref": self.ref,
            "message": self.message,
        }


@dataclass
class IntegrityReport:
    counts: dict[str, int] = field(default_factory=dict)
    issues: list[IntegrityIssue] = field(default_factory=list)
    error_count: int = 0
    warning_count: int = 0
    issue_limit: int = 200

    @property
    def ok(self) -> bool:
        return self.error_count == 0

    def add_error(self, code: str, message: str, ref: str = "") -> None:
        self.error_count += 1
        self._append_issue(IntegrityIssue("error", code, message, ref))

    def add_warning(self, code: str, message: str, ref: str = "") -> None:
        self.warning_count += 1
        self._append_issue(IntegrityIssue("warning", code, message, ref))

    def _append_issue(self, issue: IntegrityIssue) -> None:
        if len(self.issues) < self.issue_limit:
            self.issues.append(issue)

    def to_json(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "counts": dict(sorted(self.counts.items())),
            "issues": [issue.to_json() for issue in self.issues],
            "issues_truncated": self.error_count + self.warning_count > len(self.issues),
        }


def verify_integrity(config: IntegrityConfig) -> IntegrityReport:
    out = Path(config.out).resolve()
    db_path = Path(config.db_path or out / "crawl_state.sqlite").resolve()
    report = IntegrityReport(issue_limit=max(1, int(config.issue_limit)))
    report.counts["issue_sample_limit"] = report.issue_limit

    if not out.exists():
        report.add_error("output_root_missing", f"Output directory does not exist: {out}", str(out))
        return report
    if not db_path.exists():
        report.add_error("state_db_missing", f"Crawl state database does not exist: {db_path}", str(db_path))
        return report

    try:
        with _connect(db_path) as conn:
            _verify_database_tables(conn, report)
            if report.error_count:
                return report

            latest_full_run_id = _verify_latest_full_run(conn, report)
            pages_by_id = _read_jsonl_by_key(out / "pages.jsonl", "pageid", report, "pages_jsonl")
            revisions_by_key = _read_revision_jsonl(out / "wikitext.jsonl", report)
            data_revisions_by_key = _read_revision_jsonl(out / "data_pages.jsonl", report, required=False)
            resources_by_name = _read_jsonl_by_key(
                out / "resources_manifest.jsonl",
                "name",
                report,
                "resources_manifest_jsonl",
            )

            _verify_namespace_scans(conn, latest_full_run_id, report)
            _verify_pages(conn, pages_by_id, revisions_by_key, data_revisions_by_key, report)
            _verify_resources(
                conn,
                out,
                resources_by_name,
                verify_resource_files=config.verify_resource_files,
                verify_resource_hash=config.verify_resource_hash,
                report=report,
            )
    except sqlite3.DatabaseError as exc:
        report.add_error("state_db_unreadable", f"Could not read crawl state database: {exc}", str(db_path))

    return report


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _verify_database_tables(conn: sqlite3.Connection, report: IntegrityReport) -> None:
    expected = {"pages", "revisions", "resources", "runs", "namespace_scans"}
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    existing = {str(row["name"]) for row in rows}
    for table in sorted(expected - existing):
        report.add_error("state_table_missing", f"SQLite table is missing: {table}", table)


def _load_json_object(text: str) -> dict[str, Any]:
    try:
        payload = json.loads(text or "{}")
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _verify_latest_full_run(conn: sqlite3.Connection, report: IntegrityReport) -> int | None:
    rows = conn.execute("SELECT run_id, status, config_json FROM runs ORDER BY run_id DESC").fetchall()
    report.counts["runs"] = len(rows)
    full_rows: list[sqlite3.Row] = []
    for row in rows:
        config = _load_json_object(str(row["config_json"]))
        if (
            config.get("dry_run") is False
            and config.get("include_file_manifest") is True
            and config.get("limit") is None
        ):
            full_rows.append(row)

    report.counts["full_runs"] = len(full_rows)
    if not full_rows:
        report.add_error(
            "full_run_missing",
            "No completed full crawl run was found. Run .\\crawl_huiji_res1999.bat -Mode Full first.",
        )
        return None

    latest = full_rows[0]
    run_id = int(latest["run_id"])
    report.counts["latest_full_run_id"] = run_id
    if str(latest["status"]) != "completed":
        report.add_error(
            "full_run_not_completed",
            f"Latest full crawl run is {latest['status']!r}, not 'completed'.",
            str(run_id),
        )
    return run_id


def _verify_namespace_scans(conn: sqlite3.Connection, run_id: int | None, report: IntegrityReport) -> None:
    if run_id is None:
        return
    run = conn.execute("SELECT config_json FROM runs WHERE run_id=?", (run_id,)).fetchone()
    config = _load_json_object(str(run["config_json"])) if run else {}
    namespaces = config.get("namespaces")
    if not isinstance(namespaces, list):
        report.add_warning("namespaces_unknown", "Latest full run does not record a namespaces list.", str(run_id))
        return

    completed = 0
    for ns in namespaces:
        row = conn.execute(
            "SELECT status FROM namespace_scans WHERE run_id=? AND ns=?",
            (run_id, int(ns)),
        ).fetchone()
        if row is None:
            report.add_error("namespace_scan_missing", "Namespace scan record is missing.", str(ns))
            continue
        if str(row["status"]) != "completed":
            report.add_error(
                "namespace_scan_not_completed",
                f"Namespace scan status is {row['status']!r}, not 'completed'.",
                str(ns),
            )
            continue
        completed += 1
    report.counts["namespace_scans_completed"] = completed


def _read_jsonl_by_key(
    path: Path,
    key: str,
    report: IntegrityReport,
    label: str,
    required: bool = True,
) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    if not path.exists():
        if required:
            report.add_error(f"{label}_missing", f"JSONL file is missing: {path.name}", path.name)
        return records

    lines = 0
    duplicates = 0
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            text = line.strip()
            if not text:
                continue
            lines += 1
            try:
                record = json.loads(text)
            except json.JSONDecodeError as exc:
                report.add_error(
                    f"{label}_invalid_json",
                    f"{path.name}:{line_number} is not valid JSON: {exc}",
                    f"{path.name}:{line_number}",
                )
                continue
            if not isinstance(record, dict):
                report.add_error(
                    f"{label}_invalid_record",
                    f"{path.name}:{line_number} is not a JSON object.",
                    f"{path.name}:{line_number}",
                )
                continue
            value = record.get(key)
            if value is None:
                report.add_error(
                    f"{label}_key_missing",
                    f"{path.name}:{line_number} does not contain key {key!r}.",
                    f"{path.name}:{line_number}",
                )
                continue
            map_key = str(value)
            if map_key in records:
                duplicates += 1
            records[map_key] = record

    report.counts[f"{label}_lines"] = lines
    report.counts[f"{label}_unique"] = len(records)
    report.counts[f"{label}_duplicates"] = duplicates
    return records


def _read_revision_jsonl(
    path: Path,
    report: IntegrityReport,
    required: bool = True,
) -> dict[tuple[int, int], dict[str, Any]]:
    records: dict[tuple[int, int], dict[str, Any]] = {}
    if not path.exists():
        if required:
            report.add_error("wikitext_jsonl_missing", f"JSONL file is missing: {path.name}", path.name)
        return records

    lines = 0
    duplicates = 0
    label = path.stem
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            text = line.strip()
            if not text:
                continue
            lines += 1
            try:
                record = json.loads(text)
            except json.JSONDecodeError as exc:
                report.add_error(
                    f"{label}_invalid_json",
                    f"{path.name}:{line_number} is not valid JSON: {exc}",
                    f"{path.name}:{line_number}",
                )
                continue
            try:
                record_key = (int(record["pageid"]), int(record["revid"]))
            except (KeyError, TypeError, ValueError):
                report.add_error(
                    f"{label}_revision_key_missing",
                    f"{path.name}:{line_number} does not contain integer pageid and revid.",
                    f"{path.name}:{line_number}",
                )
                continue
            if record_key in records:
                duplicates += 1
            records[record_key] = record
            _verify_revision_hash(record, report, f"{path.name}:{line_number}")

    report.counts[f"{label}_lines"] = lines
    report.counts[f"{label}_unique_revisions"] = len(records)
    report.counts[f"{label}_duplicates"] = duplicates
    return records


def _verify_revision_hash(record: dict[str, Any], report: IntegrityReport, ref: str) -> None:
    content = record.get("content")
    expected = record.get("content_sha256")
    if content is None or not expected:
        return
    actual = hashlib.sha256(str(content).encode("utf-8")).hexdigest()
    if actual != str(expected).lower():
        report.add_error("revision_sha256_mismatch", "Revision content_sha256 does not match content.", ref)


def _verify_pages(
    conn: sqlite3.Connection,
    pages_by_id: dict[str, dict[str, Any]],
    revisions_by_key: dict[tuple[int, int], dict[str, Any]],
    data_revisions_by_key: dict[tuple[int, int], dict[str, Any]],
    report: IntegrityReport,
) -> None:
    rows = conn.execute("SELECT * FROM pages WHERE status='active' ORDER BY pageid").fetchall()
    report.counts["active_pages"] = len(rows)
    data_pages = 0
    complete = 0
    for row in rows:
        pageid = int(row["pageid"])
        lastrevid = int(row["lastrevid"])
        ref = str(pageid)
        jsonl_page = pages_by_id.get(ref)
        if jsonl_page is None:
            report.add_error("pages_record_missing", "pages.jsonl does not contain this active page.", ref)
        elif int(jsonl_page.get("lastrevid", -1)) != lastrevid:
            report.add_error("pages_record_outdated", "pages.jsonl lastrevid does not match SQLite pages.", ref)

        fetched = row["last_fetched_revid"]
        if fetched is None:
            report.add_error("page_revision_missing", "Active page has no fetched revision.", ref)
            continue
        if int(fetched) != lastrevid:
            report.add_error("page_revision_outdated", "Fetched revision does not match latest page lastrevid.", ref)
            continue

        state_revision = conn.execute(
            "SELECT revid FROM revisions WHERE pageid=? AND revid=?",
            (pageid, lastrevid),
        ).fetchone()
        if state_revision is None:
            report.add_error("revision_state_missing", "SQLite revisions table lacks the latest fetched revision.", ref)
            continue
        if (pageid, lastrevid) not in revisions_by_key:
            report.add_error("wikitext_record_missing", "wikitext.jsonl lacks the latest fetched revision.", ref)
            continue

        if int(row["ns"]) == 3500 or str(row["title"]).startswith("Data:"):
            data_pages += 1
            if (pageid, lastrevid) not in data_revisions_by_key:
                report.add_error("data_page_record_missing", "data_pages.jsonl lacks this Data page revision.", ref)
                continue
        complete += 1

    report.counts["data_pages"] = data_pages
    report.counts["complete_page_revisions"] = complete


def _verify_resources(
    conn: sqlite3.Connection,
    out: Path,
    resources_by_name: dict[str, dict[str, Any]],
    verify_resource_files: bool,
    verify_resource_hash: bool,
    report: IntegrityReport,
) -> None:
    rows = conn.execute("SELECT * FROM resources ORDER BY name").fetchall()
    report.counts["resources"] = len(rows)
    downloaded = 0
    verified_files = 0
    bytes_total = 0
    out_resolved = out.resolve()
    for row in rows:
        name = str(row["name"])
        if name not in resources_by_name:
            report.add_error("resource_manifest_record_missing", "resources_manifest.jsonl lacks this resource.", name)
        if not row["url"]:
            report.add_error("resource_url_missing", "Resource URL is empty.", name)
        local_relpath = str(row["local_relpath"] or "")
        if not local_relpath:
            report.add_error("resource_local_path_missing", "Resource local_relpath is empty.", name)
            continue

        target = (out_resolved / local_relpath).resolve()
        if target != out_resolved and out_resolved not in target.parents:
            report.add_error("resource_path_escape", "Resource local path escapes output directory.", name)
            continue

        status = str(row["download_status"])
        if not verify_resource_files:
            continue

        if status != "downloaded":
            report.add_error("resource_not_downloaded", f"Resource download_status is {status!r}.", name)
            continue
        downloaded += 1

        if not target.exists() or not target.is_file():
            report.add_error("resource_file_missing", "Downloaded resource file is missing on disk.", name)
            continue

        size = row["size"]
        file_size = target.stat().st_size
        if size is not None and file_size != int(size):
            report.add_error(
                "resource_size_mismatch",
                f"Resource file size is {file_size}, expected {int(size)}.",
                name,
            )
            continue

        sha1 = str(row["sha1"] or "")
        if verify_resource_hash and sha1:
            actual_sha1 = _file_sha1(target)
            if actual_sha1 != sha1.lower():
                report.add_error("resource_sha1_mismatch", "Resource sha1 does not match file content.", name)
                continue

        verified_files += 1
        bytes_total += file_size

    report.counts["downloaded_resources"] = downloaded
    report.counts["verified_resource_files"] = verified_files
    report.counts["verified_resource_bytes"] = bytes_total


def _file_sha1(path: Path) -> str:
    digest = hashlib.sha1()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
