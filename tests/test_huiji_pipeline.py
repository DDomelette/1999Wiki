from src.huijiwiki.enumerator import PageEnumerator
from src.huijiwiki.resources import ResourceManifestBuilder
from src.huijiwiki.revisions import RevisionFetcher, parse_revision_page


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.params = []

    def query(self, params):
        self.params.append(dict(params))
        return self.responses.pop(0)


def test_page_enumerator_follows_allpages_continue():
    client = FakeClient(
        [
            {
                "continue": {"apcontinue": "B"},
                "query": {"allpages": [{"pageid": 1, "ns": 0, "title": "A", "lastrevid": 10, "length": 5, "touched": "2026-07-02T00:00:00Z"}]},
            },
            {
                "query": {"allpages": [{"pageid": 2, "ns": 0, "title": "B", "lastrevid": 20, "length": 6, "touched": "2026-07-02T00:00:00Z"}]},
            },
        ]
    )
    records = list(PageEnumerator(client, seen_at_fn=lambda: "2026-07-02T08:00:00+08:00").iter_namespace(0))

    assert [record.pageid for record in records] == [1, 2]
    assert client.params[0]["aplimit"] == "500"
    assert client.params[1]["apcontinue"] == "B"


def test_page_enumerator_uses_info_fallback_when_allpages_lacks_revision_metadata():
    client = FakeClient(
        [
            {"query": {"allpages": [{"pageid": 1, "ns": 0, "title": "A"}]}},
            {
                "query": {
                    "pages": [
                        {
                            "pageid": 1,
                            "ns": 0,
                            "title": "A",
                            "lastrevid": 10,
                            "length": 5,
                            "touched": "2026-07-02T00:00:00Z",
                        }
                    ]
                }
            },
        ]
    )

    records = list(PageEnumerator(client, seen_at_fn=lambda: "2026-07-02T08:00:00+08:00").iter_namespace(0))

    assert records[0].lastrevid == 10
    assert records[0].length == 5
    assert client.params[1]["prop"] == "info"
    assert client.params[1]["pageids"] == "1"


def test_page_enumerator_batches_info_fallback_pageids_by_50():
    allpages = [{"pageid": pageid, "ns": 0, "title": f"Page {pageid}"} for pageid in range(1, 52)]
    first_info = [
        {
            "pageid": pageid,
            "ns": 0,
            "title": f"Page {pageid}",
            "lastrevid": pageid * 10,
            "length": pageid,
            "touched": "2026-07-02T00:00:00Z",
        }
        for pageid in range(1, 51)
    ]
    second_info = [
        {
            "pageid": 51,
            "ns": 0,
            "title": "Page 51",
            "lastrevid": 510,
            "length": 51,
            "touched": "2026-07-02T00:00:00Z",
        }
    ]
    client = FakeClient(
        [
            {"query": {"allpages": allpages}},
            {"query": {"pages": first_info}},
            {"query": {"pages": second_info}},
        ]
    )

    records = list(PageEnumerator(client, seen_at_fn=lambda: "2026-07-02T08:00:00+08:00").iter_namespace(0))

    assert len(records) == 51
    info_queries = [params for params in client.params if params.get("prop") == "info"]
    assert [len(params["pageids"].split("|")) for params in info_queries] == [50, 1]
    assert records[-1].lastrevid == 510


def test_revision_fetcher_batches_by_50_and_parses_slots():
    pages = [
        {
            "pageid": 1,
            "ns": 0,
            "title": "A",
            "revisions": [
                {
                    "revid": 10,
                    "timestamp": "2026-07-02T00:00:00Z",
                    "slots": {"main": {"contentmodel": "wikitext", "contentformat": "text/x-wiki", "content": "hello"}},
                }
            ],
        }
    ]
    client = FakeClient([{"query": {"pages": pages}}])

    records = list(RevisionFetcher(client, fetched_at_fn=lambda: "2026-07-02T08:00:00+08:00").fetch_pageids([1]))

    assert records[0].content == "hello"
    assert records[0].revid == 10
    assert client.params[0]["pageids"] == "1"
    assert client.params[0]["rvprop"] == "ids|timestamp|content"


def test_parse_revision_page_accepts_legacy_star_content():
    page = {
        "pageid": 2,
        "ns": 10,
        "title": "Template:X",
        "revisions": [{"revid": 30, "timestamp": "2026-07-02T00:00:00Z", "*": "legacy content"}],
    }

    record = parse_revision_page(page, fetched_at="2026-07-02T08:00:00+08:00")

    assert record.content == "legacy content"
    assert record.content_model == "wikitext"


def test_resource_manifest_builder_follows_allimages_continue_and_does_not_download():
    client = FakeClient(
        [
            {
                "continue": {"aicontinue": "B"},
                "query": {
                    "allimages": [
                        {
                            "name": "A.png",
                            "title": "File:A.png",
                            "url": "https://img.example/A.png",
                            "descriptionurl": "https://res1999.huijiwiki.com/wiki/File:A.png",
                            "mime": "image/png",
                            "size": 100,
                            "width": 64,
                            "height": 64,
                            "sha1": "sha-a",
                            "timestamp": "2026-07-02T00:00:00Z",
                        }
                    ]
                },
            },
            {"query": {"allimages": []}},
        ]
    )

    resources = list(
        ResourceManifestBuilder(client, seen_at_fn=lambda: "2026-07-02T08:00:00+08:00").iter_resources()
    )

    assert len(resources) == 1
    assert resources[0].download_status == "not_downloaded"
    assert resources[0].local_relpath == "assets/files/sha-a/A.png"
    assert client.params[0]["aiprop"] == "url|size|mime|dimensions|sha1|timestamp"
    assert client.params[1]["aicontinue"] == "B"
