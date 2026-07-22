from src.huiji_wiki.content_quality import build_content_quality_report


def test_content_quality_report_is_deterministic_and_flags_empty_pages():
    pages = [
        {"page_id": "story:1", "route": "/wiki/story/1", "title": "One", "content_json": {"summary": "One", "blocks": []}},
        {"page_id": "story:2", "route": "/wiki/story/2", "title": "Two", "content_json": {"summary": "Summary", "blocks": [{"type": "paragraph", "text": "ok"}]}},
    ]

    report = build_content_quality_report(pages)

    assert report["pageCount"] == 2
    assert report["issuePageCount"] == 1
    assert report["issues"] == [{"pageId": "story:1", "route": "/wiki/story/1", "flags": ["empty_blocks", "title_only_summary"]}]


def test_content_quality_report_accepts_rich_crawler_character_archives():
    pages = [{
        "page_id": "char:3053",
        "route": "/wiki/character/3053",
        "title": "牙仙",
        "content_json": {
            "summary": "完整的爬虫角色档案",
            "crawlerProjectionVersion": 1,
            "skins": [{"id": "305301"}],
            "blocks": [{"type": "voice_record", "title": f"语音 {index}"} for index in range(121)],
        },
    }]

    report = build_content_quality_report(pages)

    assert report["issuePageCount"] == 0
    assert report["issues"] == []
