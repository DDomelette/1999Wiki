from __future__ import annotations

import hashlib
import json

from src.huijiwiki.integrity import IntegrityConfig, verify_integrity
from src.huijiwiki.models import PageIndexRecord, RevisionRecord, ResourceRecord, content_sha256
from src.huijiwiki.state import CrawlStateStore


def _write_jsonl(path, *records):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True))
            handle.write("\n")


def _page(pageid: int, revid: int, ns: int = 0, title: str = "Example") -> PageIndexRecord:
    return PageIndexRecord(
        site="res1999",
        pageid=pageid,
        ns=ns,
        title=title,
        lastrevid=revid,
        length=100,
        touched="2026-07-02T00:00:00Z",
        seen_at="2026-07-02T08:00:00+08:00",
    )


def _revision(page: PageIndexRecord, content: str = "wikitext") -> RevisionRecord:
    return RevisionRecord(
        site="res1999",
        pageid=page.pageid,
        ns=page.ns,
        title=page.title,
        revid=page.lastrevid,
        timestamp="2026-07-02T00:00:00Z",
        content_model="wikitext",
        content_format="text/x-wiki",
        content=content,
        fetched_at="2026-07-02T08:00:00+08:00",
    )


def _resource(name: str, body: bytes, status: str = "downloaded") -> ResourceRecord:
    sha1 = hashlib.sha1(body).hexdigest()
    return ResourceRecord(
        site="res1999",
        source="huiji_file_namespace",
        title=f"File:{name}",
        name=name,
        url=f"https://huiji-public.huijistatic.com/res1999/uploads/0/00/{name}",
        descriptionurl=f"https://res1999.huijiwiki.com/wiki/File:{name}",
        mime="image/png",
        size=len(body),
        width=1,
        height=1,
        sha1=sha1,
        timestamp="2026-07-02T00:00:00Z",
        local_relpath=f"assets/files/{sha1}/{name}",
        download_status=status,
        seen_at="2026-07-02T08:00:00+08:00",
    )


def _complete_dataset(tmp_path):
    out = tmp_path / "res1999"
    db_path = out / "crawl_state.sqlite"
    store = CrawlStateStore(db_path)
    store.initialize()
    run_id = store.start_run(
        {
            "dry_run": False,
            "include_file_manifest": True,
            "limit": None,
            "namespaces": [0, 3500],
        }
    )

    normal_page = _page(1, 10, ns=0, title="角色")
    data_page = _page(2, 20, ns=3500, title="Data:角色.json")
    for page in (normal_page, data_page):
        store.upsert_page_index(page)
        revision = _revision(page, content=f"content-{page.pageid}")
        store.mark_revision_fetched(
            pageid=page.pageid,
            revid=page.lastrevid,
            content_sha256=content_sha256(revision.content),
            stored_in="wikitext.jsonl",
        )

    store.mark_namespace_scan_started(run_id, 0)
    store.mark_namespace_scan_completed(run_id, 0, {normal_page.pageid})
    store.mark_namespace_scan_started(run_id, 3500)
    store.mark_namespace_scan_completed(run_id, 3500, {data_page.pageid})

    body = b"image-bytes"
    resource = _resource("Example.png", body)
    store.upsert_resource(resource)
    target = out / resource.local_relpath
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(body)

    revisions = [_revision(normal_page, "content-1"), _revision(data_page, "content-2")]
    _write_jsonl(out / "pages.jsonl", normal_page.to_json(), data_page.to_json())
    _write_jsonl(out / "wikitext.jsonl", *(revision.to_json() for revision in revisions))
    _write_jsonl(out / "data_pages.jsonl", revisions[1].to_json())
    _write_jsonl(out / "resources_manifest.jsonl", resource.to_json())

    store.finish_run(
        run_id,
        "completed",
        {
            "indexed_pages": 2,
            "fetched_revisions": 2,
            "resources_indexed": 1,
        },
    )
    return out, db_path, store, resource


def test_integrity_verifier_accepts_complete_dataset(tmp_path):
    out, db_path, _store, _resource = _complete_dataset(tmp_path)

    report = verify_integrity(IntegrityConfig(out=out, db_path=db_path))

    assert report.ok is True
    assert report.counts["active_pages"] == 2
    assert report.counts["resources"] == 1
    assert report.counts["downloaded_resources"] == 1
    assert report.issues == []


def test_integrity_verifier_reports_missing_revision(tmp_path):
    out, db_path, store, _resource = _complete_dataset(tmp_path)
    store.mark_revision_fetched(pageid=1, revid=9, content_sha256="old", stored_in="wikitext.jsonl")

    report = verify_integrity(IntegrityConfig(out=out, db_path=db_path))

    assert report.ok is False
    assert any(issue.code == "page_revision_outdated" and issue.ref == "1" for issue in report.issues)


def test_integrity_verifier_reports_missing_resource_file(tmp_path):
    out, db_path, _store, resource = _complete_dataset(tmp_path)
    (out / resource.local_relpath).unlink()

    report = verify_integrity(IntegrityConfig(out=out, db_path=db_path))

    assert report.ok is False
    assert any(issue.code == "resource_file_missing" and issue.ref == resource.name for issue in report.issues)


def test_integrity_verifier_can_skip_resource_file_checks_before_download(tmp_path):
    out, db_path, store, resource = _complete_dataset(tmp_path)
    (out / resource.local_relpath).unlink()
    with store._connect() as conn:
        conn.execute("UPDATE resources SET download_status='not_downloaded' WHERE name=?", (resource.name,))

    report = verify_integrity(IntegrityConfig(out=out, db_path=db_path, verify_resource_files=False))

    assert report.ok is True
    assert report.counts["resources"] == 1
    assert report.counts["downloaded_resources"] == 0
    assert report.counts["verified_resource_files"] == 0


def test_integrity_verifier_reports_resource_sha1_mismatch(tmp_path):
    out, db_path, _store, resource = _complete_dataset(tmp_path)
    (out / resource.local_relpath).write_bytes(b"wrong-bytes")

    report = verify_integrity(IntegrityConfig(out=out, db_path=db_path))

    assert report.ok is False
    assert any(issue.code == "resource_sha1_mismatch" and issue.ref == resource.name for issue in report.issues)
