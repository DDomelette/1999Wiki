from src.huiji_wiki.content_blocks import build_content_blocks


def test_builds_stable_structured_blocks_and_preserves_zero_false():
    children = [{
        "child_id": "char:1/profile:0000",
        "section_kind": "profile",
        "title": "基础资料",
        "text": "## 档案\n稀有度：0\n已解锁: false\n\n- 条目一\n- 条目二",
        "media_ids": ["m1"],
    }]
    first = build_content_blocks("char:1", children)
    second = build_content_blocks("char:1", children)
    assert first == second
    assert {block["type"] for block in first} >= {"heading", "facts", "list"}
    facts = next(block for block in first if block["type"] == "facts")
    assert facts["items"] == [{"label": "稀有度", "value": "0"}, {"label": "已解锁", "value": "false"}]
    assert first[0]["mediaIds"] == ["m1"]


def test_marks_short_plain_paragraphs_for_reveal_and_separates_voice():
    blocks = build_content_blocks("char:1", [
        {"child_id": "a", "section_kind": "dossier", "text": "一段适合滚动显示的短文本。"},
        {"child_id": "b", "section_kind": "voice", "text": "语音台词", "media_ids": ["voice-1"]},
    ])
    assert next(block for block in blocks if block["type"] == "paragraph")["reveal"] is True
    assert next(block for block in blocks if block["type"] == "voice_reference")["mediaIds"] == ["voice-1"]


def test_hard_bounds_unpunctuated_text_and_omits_empty_json():
    blocks = build_content_blocks("item:1", [
        {"child_id": "long", "section_kind": "profile", "text": "字" * 501},
        {"child_id": "empty", "section_kind": "profile", "text": "{}"},
    ])
    paragraphs = [block for block in blocks if block["type"] == "paragraph"]
    assert [len(block["text"]) for block in paragraphs] == [240, 240, 21]
    assert not [block for block in blocks if block["type"] == "structured"]


def test_builds_specialized_profile_facts_and_skill_table():
    blocks = build_content_blocks("char:1", [
        {"child_id": "profile", "section_kind": "profile", "text": "角色资料\n稀有度: 5\n职业: 3"},
        {"child_id": "skill", "section_kind": "skill", "text": "风入林\n星级 1 / Rank 1: 基础效果\n星级 2 / Rank 2: 强化效果"},
    ])

    assert [(block["type"], block["section"]) for block in blocks] == [
        ("heading", "profile"), ("facts", "profile"), ("heading", "skill"), ("table", "skill")
    ]
    assert blocks[-1]["rows"] == [["星级", "效果"], ["1", "基础效果"], ["2", "强化效果"]]
