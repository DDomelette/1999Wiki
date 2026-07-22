from src.huijiwiki.models import PageIndexRecord, ResourceRecord
from src.huijiwiki.state import CrawlStateStore


def _page(pageid: int, revid: int, title: str = "Example") -> PageIndexRecord:
    return PageIndexRecord(
        site="res1999",
        pageid=pageid,
        ns=0,
        title=title,
        lastrevid=revid,
        length=100,
        touched="2026-07-02T00:00:00Z",
        seen_at="2026-07-02T08:00:00+08:00",
    )


def test_state_decides_new_changed_unchanged_and_force(tmp_path):
    db = tmp_path / "crawl_state.sqlite"
    store = CrawlStateStore(db)
    store.initialize()

    assert store.should_fetch(pageid=1, remote_lastrevid=10).reason == "new"

    store.upsert_page_index(_page(1, 10))
    assert store.should_fetch(pageid=1, remote_lastrevid=10).reason == "not_fetched"

    store.mark_revision_fetched(pageid=1, revid=10, content_sha256="abc", stored_in="wikitext.jsonl")
    assert store.should_fetch(pageid=1, remote_lastrevid=10).should_fetch is False
    assert store.should_fetch(pageid=1, remote_lastrevid=10).reason == "unchanged"

    assert store.should_fetch(pageid=1, remote_lastrevid=11).reason == "changed"
    assert store.should_fetch(pageid=1, remote_lastrevid=10, force=True).reason == "force"


def test_state_tracks_renamed_and_missing_pages(tmp_path):
    store = CrawlStateStore(tmp_path / "crawl_state.sqlite")
    store.initialize()
    store.upsert_page_index(_page(2, 20, "Old Title"))
    store.mark_revision_fetched(pageid=2, revid=20, content_sha256="abc", stored_in="wikitext.jsonl")

    store.upsert_page_index(_page(2, 20, "New Title"))
    row = store.get_page(2)
    assert row["title"] == "New Title"
    assert store.should_fetch(pageid=2, remote_lastrevid=20).should_fetch is False

    run_id = store.start_run({"namespaces": [0]})
    store.mark_namespace_scan_started(run_id, 0)
    store.mark_namespace_scan_completed(run_id, 0, seen_pageids=set())
    assert store.get_page(2)["status"] == "missing"


def test_state_upserts_resource_manifest_status(tmp_path):
    store = CrawlStateStore(tmp_path / "crawl_state.sqlite")
    store.initialize()

    resource = ResourceRecord(
        site="res1999",
        source="huiji_file_namespace",
        title="File:Example.png",
        name="Example.png",
        url="https://img.example/Example.png",
        descriptionurl="https://res1999.huijiwiki.com/wiki/File:Example.png",
        mime="image/png",
        size=1024,
        width=512,
        height=512,
        sha1="abc123",
        timestamp="2026-07-02T00:00:00Z",
        local_relpath="assets/files/abc123/Example.png",
        download_status="not_downloaded",
        seen_at="2026-07-02T08:00:00+08:00",
    )
    store.upsert_resource(resource)

    row = store.get_resource("Example.png")
    assert row["sha1"] == "abc123"
    assert row["download_status"] == "not_downloaded"
