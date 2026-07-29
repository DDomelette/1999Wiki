from __future__ import annotations

import hashlib
import socket
import sqlite3
import urllib.request
from pathlib import Path

import pytest

from src.huiji_rag.build.page_sources import (
    CrawlerSemanticInputs,
    JoinedPageRevision,
    JsonlRow,
    PageMetadata,
    PageRevisionJoin,
    RevisionMetadata,
    build_page_revision_join,
)
from src.huiji_rag.build.projection import (
    project_page_semantics,
    project_wikitext_media_intents,
)
from src.huiji_rag.build.topic_projection import TopicChildProjection, TopicProjection
from src.huiji_rag.build.wikitext_projection import (
    normalize_wikitext_filename,
    project_wikitext_pages,
    scan_wikitext,
)
from src.huiji_rag.models import ChildBlock


def _joined(pageid: int, title: str, revid: int) -> JoinedPageRevision:
    return JoinedPageRevision(
        page=PageMetadata(pageid, 0, title, revid, "active", pageid),
        revision=RevisionMetadata(
            pageid, 0, title, revid, hashlib.sha256(title.encode()).hexdigest(), pageid, 0, 1
        ),
    )


def _row(pageid: int, title: str, revid: int, content: str) -> JsonlRow:
    return JsonlRow(
        row={
            "site": "res1999",
            "pageid": pageid,
            "ns": 0,
            "title": title,
            "revid": revid,
            "content": content,
            "content_sha256": hashlib.sha256(content.encode()).hexdigest(),
        },
        source_name="wikitext.jsonl",
        line_number=pageid,
        byte_offset=pageid * 10,
        byte_length=len(content.encode()),
    )


def _project(specs: list[tuple[int, str, str]], **kwargs):
    joined = tuple(_joined(pageid, title, pageid * 10) for pageid, title, _ in specs)
    rows = tuple(_row(pageid, title, pageid * 10, content) for pageid, title, content in specs)
    return project_wikitext_pages(PageRevisionJoin(joined, (), ()), rows, **kwargs)


def _project_revision(
    pageid: int,
    title: str,
    revid: int,
    content: str,
):
    joined = (_joined(pageid, title, revid),)
    rows = (_row(pageid, title, revid, content),)
    return project_wikitext_pages(PageRevisionJoin(joined, (), ()), rows)


def test_scanner_tracks_lead_h2_h3_through_h6_heading_paths_and_offsets() -> None:
    content = "Lead.\n== H2 ==\nTwo.\n=== H3 ===\nThree.\n==== H4 ====\nFour.\n===== H5 =====\nFive.\n====== H6 ======\nSix."
    scan = scan_wikitext(content)
    assert [section.heading_path for section in scan.sections] == [
        (),
        ("H2",),
        ("H2", "H3"),
        ("H2", "H3", "H4"),
        ("H2", "H3", "H4", "H5"),
        ("H2", "H3", "H4", "H5", "H6"),
    ]
    assert [section.visible_text for section in scan.sections] == [
        "Lead.",
        "Two.",
        "Three.",
        "Four.",
        "Five.",
        "Six.",
    ]
    for section in scan.sections:
        assert content[section.char_start : section.char_end].strip()


def test_internal_links_keep_label_as_visible_text_without_aliasing_target() -> None:
    scan = scan_wikitext("See [[Target|Visible Label]] and [[Plain Target]].")
    assert scan.sections[0].visible_text == "See Visible Label and Plain Target."
    assert [(link.target, link.label) for link in scan.links] == [
        ("Target", "Visible Label"),
        ("Plain Target", "Plain Target"),
    ]
    assert scan.display_titles == ()


def test_file_namespaces_and_gallery_preserve_original_filename_and_context() -> None:
    scan = scan_wikitext(
        "== Art ==\n[[文件:Original_Name.PNG|thumb|Caption]]\n"
        "<gallery>\nImage:Second File.jpg|Second caption\n图像:第三张.webp|第三张\n</gallery>"
    )
    assert [(image.filename, image.source_kind, image.heading_path) for image in scan.images] == [
        ("Original_Name.PNG", "file_link", ("Art",)),
        ("Second File.jpg", "gallery", ("Art",)),
        ("第三张.webp", "gallery", ("Art",)),
    ]
    assert [image.caption for image in scan.images] == ["Caption", "Second caption", "第三张"]


def test_file_options_separate_caption_alt_link_layout_and_unknown_options() -> None:
    image = scan_wikitext(
        "[[File:Poster.png|thumb|right|220px|x300px|alt=Alt text|link=Story|mystery=yes|A caption]]"
    )
    assert image.images[0].layout_options == ("thumb", "right", "220px", "x300px")
    assert image.images[0].alt == "Alt text"
    assert image.images[0].link_target == "Story"
    assert image.images[0].caption == "A caption"
    assert image.images[0].unknown_options == ("mystery=yes",)
    assert "unknown_image_option" in {
        item.reason_code for item in image.diagnostics
    }


def test_simple_display_title_adds_alias_but_dynamic_form_is_diagnostic() -> None:
    scan = scan_wikitext(
        "{{DisplayTitle|Natural title}}\n{{DISPLAYTITLE:Static colon form}}\n"
        "{{DISPLAYTITLE:{{PAGENAME}} suffix}}\nBody."
    )
    assert scan.display_titles == ("Natural title",)
    assert "dynamic_display_title" in {item.reason_code for item in scan.diagnostics}
    assert scan.sections[0].visible_text == "Body."


def test_nested_links_and_templates_do_not_cross_consume_tokens() -> None:
    scan = scan_wikitext(
        "{{Unsupported|[[Inner|inside]]|{{Nested|x}}}}\n"
        "After [[Target|legal label]].\n== Later ==\nLater body."
    )
    assert scan.links[-1].label == "legal label"
    assert scan.sections[-1].heading_path == ("Later",)
    assert scan.sections[-1].visible_text == "Later body."


def test_unsupported_template_html_unbalanced_link_and_unclosed_gallery_are_isolated() -> None:
    scan = scan_wikitext(
        "{{#invoke:Module|x}}\n<div style=\"background:url(x.png)\">ignored</div>\n"
        "[[broken\n== Valid ==\nText [[Good|label]].\n"
        "<gallery>\nFile:lost.png|lost\n== Still Valid ==\nFinal [[File:kept.png|kept]]."
    )
    reasons = {item.reason_code for item in scan.diagnostics}
    assert {
        "unsupported_template_media",
        "unsupported_html_media",
        "unbalanced_wikilink",
        "unclosed_gallery",
    } <= reasons
    assert scan.sections[-1].heading_path == ("Still Valid",)
    assert "Final" in scan.sections[-1].visible_text
    assert scan.images[-1].filename == "kept.png"


def test_scanner_never_calls_network_wiki_api_mysql_or_renderer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*_args, **_kwargs):
        raise AssertionError("external dependency called")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    monkeypatch.setattr(sqlite3, "connect", forbidden)
    assert scan_wikitext("Offline [[Target|text]].").sections[0].visible_text


def test_table_projection_preserves_header_cell_and_row_order() -> None:
    scan = scan_wikitext(
        "{| class=\"wikitable\"\n! Name !! Value\n|-\n| First || One\n|-\n| Second || Two\n|}"
    )
    assert scan.sections[0].visible_text.splitlines() == [
        "Name | Value",
        "First | One",
        "Second | Two",
    ]


def test_exact_redirect_adds_alias_and_emits_no_redirect_body_child() -> None:
    result = _project(
        [
            (1, "Target", "Target body."),
            (2, "Alias", "#REDIRECT [[Target]]\nRedirect body must not project."),
        ]
    )
    assert result.pages[0].entity_aliases == ("Alias",)
    assert all(child.entity_name != "Alias" for child in result.children)
    assert result.redirects == (("Alias", "Target"),)


def test_dangling_cycle_cross_namespace_and_conflicting_redirect_are_diagnostic() -> None:
    result = _project(
        [
            (1, "Dangling", "#REDIRECT [[Missing]]"),
            (2, "Cycle A", "#REDIRECT [[Cycle B]]"),
            (3, "Cycle B", "#REDIRECT [[Cycle A]]"),
            (4, "Cross", "#REDIRECT [[Template:Nope]]"),
            (5, "Conflict", "#REDIRECT [[Cycle A]]\n#REDIRECT [[Cycle B]]"),
        ]
    )
    reasons = {item.reason_code for item in result.diagnostics}
    assert {
        "dangling_redirect",
        "redirect_cycle",
        "cross_namespace_redirect",
        "conflicting_redirect",
    } <= reasons
    assert result.children == ()


def test_page_ids_use_pageid_heading_sha20_occurrence_and_zero_padded_chunk() -> None:
    result = _project([(7, "Page", "Lead.\n== Same ==\nOne.\n== Same ==\nTwo.")])
    ids = [child.child_id for child in result.children]
    heading_token = hashlib.sha256("Same".encode()).hexdigest()[:20]
    assert ids == [
        "page:7/section:lead/chunk:0000",
        f"page:7/section:{heading_token}/chunk:0000",
        f"page:7/section:{heading_token}-occurrence-02/chunk:0000",
    ]
    assert "duplicate_heading_path_occurrence" in {
        item.reason_code for item in result.diagnostics
    }


def test_page_chunking_targets_1200_caps_indivisible_blocks_at_1600_and_has_no_overlap() -> None:
    paragraphs = ["A" * 700, "B" * 700, "C" * 1700]
    result = _project([(1, "Long", "\n\n".join(paragraphs))])
    contents = [child.content for child in result.children]
    assert contents[:2] == paragraphs[:2]
    assert all(len(content) <= 1600 for content in contents)
    assert "".join(contents) == "".join(paragraphs)


def test_page_search_text_contains_title_alias_heading_link_labels_and_content() -> None:
    result = _project(
        [
            (1, "Page", "{{DisplayTitle|Natural}}\n== Heading ==\nBody [[Target|Label]]."),
            (2, "Redirect", "#REDIRECT [[Page]]"),
        ]
    )
    search = result.children[0].search_text
    assert all(value in search for value in ("Page", "Natural", "Redirect", "Heading", "Label", "Body"))


def test_page_route_tags_require_structured_definition_story_or_event_evidence() -> None:
    plain = _project([(1, "Plain", "story event words only.")])
    assert plain.children[0].route_tags == ("page",)
    structured = _project(
        [(1, "Defined", "Defined is a documented concept.")],
        structured_route_tags={1: ("story", "event")},
    )
    assert structured.children[0].route_tags == ("page", "definition", "story", "event")


def test_sparse_page_child_requires_verified_link_or_image_and_empty_page_is_excluded() -> None:
    sparse = _project([(1, "Sparse", "[[Target]]"), (2, "Empty", "{{Navbox}} [[Category:X]]")])
    assert sparse.children[0].quality_flags == ("sparse_text",)
    assert {item.reason_code for item in sparse.exclusions} == {"empty_page"}


def test_repeated_build_has_equal_page_ids_order_content_hash_and_source_refs() -> None:
    specs = [(2, "B", "B body."), (1, "A", "A body.\n== H ==\nH body.")]
    first = _project(specs)
    second = _project(list(reversed(specs)))
    assert [page.to_json() for page in first.pages] == [page.to_json() for page in second.pages]
    assert [child.to_json() for child in first.children] == [
        child.to_json() for child in second.children
    ]
    for child in first.children:
        assert child.source_refs[0]["source_row_id"].endswith(
            f":{child.source_refs[0]['char_start']}:{child.source_refs[0]['char_end']}"
        )
        assert not Path(child.source_refs[0]["source_title"]).is_absolute()


def test_page_image_references_disambiguate_identical_offsets_across_pages() -> None:
    content = "== Shared ==\n[[File:Shared.png|thumb|Shared caption]]\nBody."
    first = _project([(2, "Page B", content), (1, "Page A", content)])
    second = _project([(1, "Page A", content), (2, "Page B", content)])

    assert [item.to_json() for item in first.image_references] == [
        item.to_json() for item in second.image_references
    ]
    assert [item.pageid for item in first.image_references] == [1, 2]
    assert [item.revid for item in first.image_references] == [10, 20]
    assert [item.source_title for item in first.image_references] == [
        "Page A",
        "Page B",
    ]
    assert len({item.image.char_start for item in first.image_references}) == 1
    assert len({item.image.heading_path for item in first.image_references}) == 1
    assert [item.owner_page_id for item in first.image_references] == [
        "page:1",
        "page:2",
    ]
    assert [item.parent_id for item in first.image_references] == [
        first.children[0].parent_id,
        first.children[1].parent_id,
    ]
    assert [item.child_id for item in first.image_references] == [
        first.children[0].child_id,
        first.children[1].child_id,
    ]
    assert [item.source_ref["source_row_id"] for item in first.image_references] == [
        f"wikitext:1:10:{first.image_references[0].image.char_start}:"
        f"{first.image_references[0].image.char_end}",
        f"wikitext:2:20:{first.image_references[1].image.char_start}:"
        f"{first.image_references[1].image.char_end}",
    ]
    assert all(
        item.source_ref["source_content_sha256"]
        == hashlib.sha256(content.encode()).hexdigest()
        for item in first.image_references
    )
    with pytest.raises(TypeError):
        first.image_references[0].source_ref["pageid"] = 99
    assert isinstance(first.image_references[0].source_ref["heading_path"], tuple)


def test_named_four_file_fixture_projects_through_independent_page_stage() -> None:
    inputs = CrawlerSemanticInputs.from_root(
        Path("tests/fixtures/huiji_topic_story_media_projection")
    )
    result = project_page_semantics(
        build_page_revision_join(inputs.pages(), inputs.revisions()),
        inputs.revisions(),
    )

    assert [page.entity_name for page in result.pages] == ["测试页面"]
    assert result.pages[0].entity_aliases == ("测试页面",)
    assert [child.heading_path for child in result.children] == [
        ("lead",),
        ("章节",),
        ("章节", "表格"),
    ]
    assert result.image_references[0].image.filename == "Banner_测试页面.png"


def test_wikitext_relation_token_is_stable_without_revision_caption_or_time() -> None:
    first = _project_revision(
        7,
        "Stable",
        10,
        "== Art ==\n[[File:Same Image.PNG|thumb|First caption]]",
    )
    second = _project_revision(
        7,
        "Stable",
        99,
        "== Art ==\n[[File:Same Image.PNG|thumb|Changed caption]]",
    )

    first_intent = first.media_intents[0]
    second_intent = second.media_intents[0]
    assert first_intent.source_binding_token == second_intent.source_binding_token
    assert first_intent.source_binding_token.startswith("wiki:7:")
    assert "caption" not in first_intent.source_binding_token.casefold()


def test_file_and_gallery_bind_exact_page_section_chunk_and_heading_path() -> None:
    result = _project(
        [
            (
                5,
                "Media Page",
                "Lead.\n== Art ==\nBefore.\n"
                "[[File:Inline.png|thumb|Inline caption]]\n"
                "<gallery>\nFile:Gallery.jpg|Gallery caption\n</gallery>\nAfter.",
            )
        ]
    )

    assert len(result.media_intents) == 2
    assert [item.source_kind for item in result.media_intents] == [
        "file_link",
        "gallery",
    ]
    assert all(item.owner_entity_id == "page:5" for item in result.media_intents)
    assert all(item.owner_page_id == "page:5" for item in result.media_intents)
    assert all(
        item.parent_id.startswith("page:5/section:")
        for item in result.media_intents
    )
    assert all(
        item.child_id in {child.child_id for child in result.children}
        for item in result.media_intents
    )
    assert all(item.heading_path == ("Art",) for item in result.media_intents)
    assert [item.normalized_filename for item in result.media_intents] == [
        "Inline.png",
        "Gallery.jpg",
    ]
    assert all(
        item.source_ref["char_start"] < item.source_ref["char_end"]
        for item in result.media_intents
    )


def test_inline_image_after_split_block_binds_child_containing_visible_context() -> None:
    result = _project(
        [
            (
                6,
                "Split Context",
                "A" * 1700
                + "[[File:Late.png|Inline marker]]"
                + "B" * 100,
            )
        ]
    )

    intent = result.media_intents[0]
    child = next(item for item in result.children if item.child_id == intent.child_id)
    assert "Inline marker" in child.content
    assert intent.source_ref["context_before"] in child.content
    assert intent.source_ref["context_after"] in child.content


def test_same_filename_in_same_section_increments_occurrence_only() -> None:
    result = _project(
        [
            (
                3,
                "Occurrences",
                "== One ==\n[[File:Same.png|A]]\n[[File:Same.png|B]]\n"
                "== Two ==\n[[File:Same.png|C]]",
            )
        ]
    )

    assert [item.occurrence for item in result.media_intents] == [1, 2, 1]
    assert not result.media_intents[0].source_binding_token.endswith(":1")
    assert result.media_intents[1].source_binding_token.endswith(":2")
    assert not result.media_intents[2].source_binding_token.endswith(":1")
    assert result.media_intents[0].normalized_filename == "Same.png"
    assert (
        result.media_intents[0].source_binding_token
        != result.media_intents[2].source_binding_token
    )


def test_same_resource_across_pages_sections_and_topics_preserves_all_bindings() -> None:
    pages = _project(
        [
            (1, "Page A", "== One ==\n[[File:Shared.png|A]]"),
            (2, "Page B", "== Two ==\n[[File:Shared.png|B]]"),
        ]
    )
    source_child_id = pages.media_intents[0].child_id
    source_child = next(
        child for child in pages.children if child.child_id == source_child_id
    )
    topic_block = ChildBlock(
        child_id="topic:shared/topic/source:1",
        parent_id="topic:shared/topic",
        entity_id="shared",
        entity_name="Shared Topic",
        category="topic",
        section_kind="topic",
        title="Shared Topic",
        text=source_child.content,
        search_text=source_child.search_text,
        chunk_index=0,
        media_ids=(),
        media_policy="text_only",
        source_refs=source_child.source_refs,
        content_hash=source_child.content_hash,
        entity_type="topic",
        ancestor_ids=("topic:shared", "topic:shared/topic"),
        route_tags=("topic",),
        heading_path=source_child.heading_path,
    )
    topic = TopicProjection(
        parents=(),
        children=(
            TopicChildProjection(
                block=topic_block,
                owner_entity_id="topic:shared",
                owner_page_id="topic:shared",
                source_fields={
                    "source_child_id": source_child_id,
                    "source_parent_id": source_child.parent_id,
                    "source_owner_entity_id": source_child.owner_entity_id,
                    "source_owner_page_id": source_child.owner_page_id,
                    "source_entity_type": "page",
                    "evidence_kind": "exact_heading",
                },
            ),
        ),
        diagnostics=(),
        catalog_fingerprint_sha256="a" * 64,
    )

    intents = project_wikitext_media_intents(pages, topic)

    assert len(intents) == 3
    assert len({item.source_binding_token for item in intents}) == 3
    assert {item.owner_page_id for item in intents} == {
        "page:1",
        "page:2",
        "topic:shared",
    }
    assert {item.exact_filename for item in intents} == {"Shared.png"}


def test_display_title_precedence_records_explicit_adjacent_heading_page_filename_source() -> None:
    result = _project(
        [
            (1, "Caption Page", "[[File:A.png|Explicit caption]]"),
            (2, "Link Page", "[[Target|Adjacent label]] [[File:B.png]]"),
            (3, "Heading Page", "== Heading title ==\n[[File:C.png]]"),
            (4, "Page title", "[[File:D.png]]"),
            (5, "", "[[File:E.png]]"),
        ]
    )

    assert [(item.title, item.title_source) for item in result.media_intents] == [
        ("Explicit caption", "explicit_caption"),
        ("Adjacent label", "adjacent_link_label"),
        ("Heading title", "heading"),
        ("Page title", "page_title"),
        ("E.png", "filename_fallback"),
    ]


def test_media_source_ref_keeps_filename_caption_link_offsets_title_source_and_context_hash() -> None:
    result = _project(
        [
            (
                8,
                "Evidence",
                "== Art ==\nBefore "
                "[[File:Original Name.PNG|thumb|alt=Alt text|link=Target|"
                "mystery=yes|Caption]] after.",
            )
        ]
    )
    intent = result.media_intents[0]
    ref = intent.source_ref

    assert ref["original_filename"] == "Original Name.PNG"
    assert ref["normalized_filename"] == "Original_Name.png"
    assert ref["original_caption"] == "Caption"
    assert ref["alt"] == "Alt text"
    assert ref["link_target"] == "Target"
    assert ref["layout_options"] == ("thumb",)
    assert ref["unknown_options"] == ("mystery=yes",)
    assert ref["heading_path"] == ("Art",)
    assert ref["char_start"] < ref["char_end"]
    assert ref["display_title_source"] == "explicit_caption"
    assert len(ref["adjacent_context_sha256"]) == 64


def test_context_uses_at_most_200_visible_chars_each_side_without_crossing_heading() -> None:
    result = _project(
        [
            (
                9,
                "Context",
                "== Here ==\n"
                + "A" * 250
                + "[[File:Context.png|Caption]]"
                + "B" * 250
                + "\n== Other ==\n"
                + "MUST_NOT_CROSS",
            )
        ]
    )
    ref = result.media_intents[0].source_ref

    assert ref["context_before"] == "A" * 200
    assert ref["context_after"] == "B" * 200
    assert "MUST_NOT_CROSS" not in ref["context_after"]


def test_media_role_uses_location_options_and_caption_not_filename_prefix_only() -> None:
    result = _project(
        [
            (
                10,
                "Roles",
                "[[File:Lead.png|center|800px]]\n"
                "[[File:Banner_named_only.png]]\n"
                "== Posters ==\n[[File:X.png|Event poster]]\n"
                "<gallery>\nFile:G.png|Gallery\n</gallery>",
            )
        ]
    )

    assert [item.media_role for item in result.media_intents] == [
        "banner",
        "page_image",
        "poster",
        "gallery_image",
    ]


def test_small_navigation_icon_is_decorative_exclusion_with_fingerprinted_threshold() -> None:
    result = _project(
        [(11, "Decorative", "[[File:Nav.png|32x32px|link=Next|Navigation icon]]")]
    )

    assert result.media_intents == ()
    diagnostic = next(
        item
        for item in result.diagnostics
        if item.reason_code == "decorative_media_excluded"
    )
    assert diagnostic.details["minimum_dimension_px"] == 96
    assert diagnostic.details["declared_width"] == 32
    assert diagnostic.details["declared_height"] == 32
    assert len(diagnostic.details["parser_config_sha256"]) == 64


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("File:My Image.PNG", "My_Image.png"),
        ("Image:%EF%BC%A6oo_bar.JpG", "Foo_bar.jpg"),
        ("https://example.test/wiki/File:Space%20Name.WEBP", "Space_Name.webp"),
        ("文件:示例 图像.SVG", "示例_图像.svg"),
    ],
)
def test_wikitext_filename_normalizes_prefix_url_nfkc_space_underscore_and_extension_case(
    raw: str,
    expected: str,
) -> None:
    assert normalize_wikitext_filename(raw) == expected
