from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .models import FetchDecision, PageIndexRecord, ResourceRecord


class CrawlStateStore:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def initialize(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS pages (
                    pageid INTEGER PRIMARY KEY,
                    ns INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    lastrevid INTEGER NOT NULL,
                    length INTEGER NOT NULL,
                    touched TEXT NOT NULL,
                    status TEXT NOT NULL,
                    first_seen_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    last_fetched_revid INTEGER
                );
                CREATE TABLE IF NOT EXISTS revisions (
                    revid INTEGER PRIMARY KEY,
                    pageid INTEGER NOT NULL,
                    content_sha256 TEXT NOT NULL,
                    stored_in TEXT NOT NULL,
                    fetched_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS resources (
                    name TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    url TEXT NOT NULL,
                    mime TEXT,
                    size INTEGER,
                    width INTEGER,
                    height INTEGER,
                    sha1 TEXT,
                    timestamp TEXT,
                    local_relpath TEXT NOT NULL,
                    download_status TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS runs (
                    run_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    finished_at TEXT,
                    status TEXT NOT NULL,
                    config_json TEXT NOT NULL,
                    summary_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE TABLE IF NOT EXISTS namespace_scans (
                    run_id INTEGER NOT NULL,
                    ns INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    seen_pageids_json TEXT NOT NULL DEFAULT '[]',
                    PRIMARY KEY (run_id, ns)
                );
                """
            )

    def start_run(self, config: dict[str, object]) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO runs (status, config_json) VALUES (?, ?)",
                ("running", json.dumps(config, ensure_ascii=False, sort_keys=True)),
            )
            return int(cur.lastrowid)

    def finish_run(self, run_id: int, status: str, summary: dict[str, object]) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE runs SET status=?, finished_at=CURRENT_TIMESTAMP, summary_json=? WHERE run_id=?",
                (status, json.dumps(summary, ensure_ascii=False, sort_keys=True), run_id),
            )

    def upsert_page_index(self, record: PageIndexRecord) -> None:
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT first_seen_at, last_fetched_revid FROM pages WHERE pageid=?",
                (record.pageid,),
            ).fetchone()
            first_seen_at = existing["first_seen_at"] if existing else record.seen_at
            last_fetched_revid = existing["last_fetched_revid"] if existing else None
            conn.execute(
                """
                INSERT OR REPLACE INTO pages
                (pageid, ns, title, lastrevid, length, touched, status, first_seen_at, last_seen_at, last_fetched_revid)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.pageid,
                    record.ns,
                    record.title,
                    record.lastrevid,
                    record.length,
                    record.touched,
                    record.status,
                    first_seen_at,
                    record.seen_at,
                    last_fetched_revid,
                ),
            )

    def should_fetch(self, pageid: int, remote_lastrevid: int, force: bool = False) -> FetchDecision:
        if force:
            return FetchDecision(pageid=pageid, should_fetch=True, reason="force")
        row = self.get_page(pageid)
        if row is None:
            return FetchDecision(pageid=pageid, should_fetch=True, reason="new")
        fetched = row["last_fetched_revid"]
        if fetched is None:
            return FetchDecision(pageid=pageid, should_fetch=True, reason="not_fetched")
        if int(fetched) != int(remote_lastrevid):
            return FetchDecision(pageid=pageid, should_fetch=True, reason="changed")
        return FetchDecision(pageid=pageid, should_fetch=False, reason="unchanged")

    def mark_revision_fetched(self, pageid: int, revid: int, content_sha256: str, stored_in: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO revisions (revid, pageid, content_sha256, stored_in) VALUES (?, ?, ?, ?)",
                (revid, pageid, content_sha256, stored_in),
            )
            conn.execute("UPDATE pages SET last_fetched_revid=? WHERE pageid=?", (revid, pageid))

    def mark_namespace_scan_started(self, run_id: int, ns: int) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO namespace_scans (run_id, ns, status, seen_pageids_json) VALUES (?, ?, ?, ?)",
                (run_id, ns, "running", "[]"),
            )

    def mark_namespace_scan_completed(self, run_id: int, ns: int, seen_pageids: set[int]) -> None:
        seen_json = json.dumps(sorted(seen_pageids))
        with self._connect() as conn:
            conn.execute(
                "UPDATE namespace_scans SET status=?, seen_pageids_json=? WHERE run_id=? AND ns=?",
                ("completed", seen_json, run_id, ns),
            )
            if seen_pageids:
                placeholders = ",".join("?" for _ in seen_pageids)
                conn.execute(
                    f"UPDATE pages SET status='missing' WHERE ns=? AND pageid NOT IN ({placeholders})",
                    (ns, *sorted(seen_pageids)),
                )
            else:
                conn.execute("UPDATE pages SET status='missing' WHERE ns=?", (ns,))

    def upsert_resource(self, record: ResourceRecord) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO resources
                (name, title, url, mime, size, width, height, sha1, timestamp, local_relpath, download_status, last_seen_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.name,
                    record.title,
                    record.url,
                    record.mime,
                    record.size,
                    record.width,
                    record.height,
                    record.sha1,
                    record.timestamp,
                    record.local_relpath,
                    record.download_status,
                    record.seen_at,
                ),
            )

    def get_page(self, pageid: int) -> sqlite3.Row | None:
        with self._connect() as conn:
            return conn.execute("SELECT * FROM pages WHERE pageid=?", (pageid,)).fetchone()

    def get_resource(self, name: str) -> sqlite3.Row | None:
        with self._connect() as conn:
            return conn.execute("SELECT * FROM resources WHERE name=?", (name,)).fetchone()
