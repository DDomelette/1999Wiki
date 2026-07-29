from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field, replace
from typing import Any, Mapping

import pytest

from src.huiji_rag.build.topic_projection import (
    DEFAULT_TOPIC_CATALOG_PATH,
    TopicCatalogError,
    load_topic_catalog,
    project_topics,
    validate_topic_catalog,
)
from src.huiji_rag.build.projection import project_topic_semantics
from src.huiji_rag.build.wikitext_projection import PageChildProjection
from src.huiji_rag.models import ChildBlock


def _source_ref(
    title: str,
    *,
    pageid: int = 1,
    revid: int = 10,
) -> dict[str, Any]:
    return {
        "source_title": title,
        "pageid": pageid,
        "revid": revid,
        "source_content_sha256": hashlib.sha256(title.encode()).hexdigest(),
        "json_path": "$",
    }


def _page_child(
    child_id: str,
    *,
    title: str,
    content: str,
    aliases: tuple[str, ...] = (),
    heading_path: tuple[str, ...] = ("lead",),
    route_tags: tuple[str, ...] = ("page",),
) -> PageChildProjection:
    source_refs = (_source_ref(title),)
    return PageChildProjection(
        category="page",
        entity_type="page",
        entity_id="page:1",
        entity_name=title,
        entity_aliases=aliases,
        owner_entity_id="page:1",
        owner_page_id="page:1",
        route_tags=route_tags,
        parent_id="page:1/section:lead",
        child_id=child_id,
        heading_path=heading_path,
        section_kind="lead" if heading_path == ("lead",) else "section",
        content=content,
        text=content,
        search_text=f"{title} {' '.join(heading_path)} {content}",
        source_refs=source_refs,
        quality_flags=(),
        content_hash=hashlib.sha256(content.encode()).hexdigest(),
    )


@dataclass(frozen=True)
class _BlockSource:
    block: ChildBlock
    owner_entity_id: str
    owner_page_id: str
    source_fields: Mapping[str, Any] = field(default_factory=dict)


def _block_source(
    child_id: str,
    *,
    content: str,
    source_title: str = "Data:Story/1.json",
    route_tags: tuple[str, ...] = ("story",),
    source_fields: Mapping[str, Any] | None = None,
) -> _BlockSource:
    block = ChildBlock(
        child_id=child_id,
        parent_id="story:1/story",
        entity_id="1",
        entity_name="Source Story",
        category="story",
        section_kind="story",
        title="Source Story",
        text=content,
        search_text=f"Source Story {content}",
        chunk_index=0,
        media_ids=(),
        media_policy="text_only",
        source_refs=(_source_ref(source_title),),
        content_hash=hashlib.sha256(content.encode()).hexdigest(),
        entity_type="story",
        ancestor_ids=("story:1", "story:1/story"),
        route_tags=route_tags,
        heading_path=("story:1", "step-1"),
    )
    return _BlockSource(
        block=block,
        owner_entity_id="story:1",
        owner_page_id="story:1",
        source_fields=source_fields or {},
    )


def _catalog(*topics: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "huiji.topic-catalog/v1",
        "topics": list(topics),
    }


def _topic(
    topic_id: str,
    name: str,
    *,
    aliases: list[str] | None = None,
    exact_page_titles: list[str] | None = None,
    exact_heading_titles: list[str] | None = None,
    required_route_tags: list[str] | None = None,
    definition_patterns: list[str] | None = None,
    structured_relations: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    return {
        "topic_id": topic_id,
        "name": name,
        "aliases": aliases or [],
        "exact_page_titles": exact_page_titles or [],
        "exact_heading_titles": exact_heading_titles or [],
        "required_route_tags": required_route_tags or [],
        "definition_patterns": definition_patterns or [],
        "structured_relations": structured_relations or [],
    }


def test_topic_catalog_v1_contains_storm_and_reverse_1999_selectors() -> None:
    catalog = load_topic_catalog(DEFAULT_TOPIC_CATALOG_PATH)
    topics = {item.topic_id: item for item in catalog.topics}

    assert catalog.schema_version == "huiji.topic-catalog/v1"
    assert tuple(topics) == ("reverse-1999", "storm")
    assert topics["storm"].name == "暴雨"
    assert "暴雨" in topics["storm"].exact_page_titles
    assert topics["reverse-1999"].name == "重返未来：1999"
    assert "重返未来1999" in topics["reverse-1999"].aliases
    assert all(item.selector_count > 0 for item in topics.values())


def test_catalog_is_selector_metadata_not_fact_content() -> None:
    raw = json.loads(DEFAULT_TOPIC_CATALOG_PATH.read_text(encoding="utf-8"))
    forbidden = {"content", "text", "facts", "description", "summary", "prose"}

    assert not any(forbidden.intersection(item) for item in raw["topics"])
    assert all(
        "\n" not in value
        for item in raw["topics"]
        for field_name, field_value in item.items()
        if field_name != "definition_patterns"
        for value in (
            field_value if isinstance(field_value, list) else [field_value]
        )
        if isinstance(value, str)
    )


@pytest.mark.parametrize(
    "mutate",
    [
        lambda raw: raw["topics"].append(copy.deepcopy(raw["topics"][0])),
        lambda raw: raw["topics"][1]["aliases"].append(raw["topics"][0]["name"]),
        lambda raw: raw["topics"][0].update(
            {
                "exact_page_titles": [],
                "exact_heading_titles": [],
                "definition_patterns": [],
                "structured_relations": [],
            }
        ),
        lambda raw: raw["topics"][0].update({"selection_mode": "fuzzy"}),
        lambda raw: raw["topics"].reverse(),
        lambda raw: raw["topics"][0]["aliases"].reverse(),
    ],
)
def test_catalog_validation_fails_closed_for_identity_selector_and_ordering(
    mutate,
) -> None:
    raw = json.loads(DEFAULT_TOPIC_CATALOG_PATH.read_text(encoding="utf-8"))
    mutate(raw)

    with pytest.raises(TopicCatalogError):
        validate_topic_catalog(raw)


def test_topic_accepts_exact_page_title_redirect_heading_or_controlled_definition() -> None:
    catalog = validate_topic_catalog(
        _catalog(
            _topic(
                "storm",
                "暴雨",
                exact_page_titles=["Storm Alias", "暴雨"],
                exact_heading_titles=["暴雨机制"],
                required_route_tags=["page"],
                definition_patterns=[r"^暴雨是"],
            )
        )
    )
    sources = [
        _page_child("page-title", title="暴雨", content="Exact title evidence."),
        _page_child(
            "redirect",
            title="Storm",
            aliases=("Storm Alias",),
            content="Redirect evidence.",
        ),
        _page_child(
            "heading",
            title="World",
            heading_path=("世界观", "暴雨机制"),
            content="Heading evidence.",
        ),
        _page_child(
            "definition",
            title="World",
            content="暴雨是周期性降临的异常现象。",
            heading_path=("世界观",),
            route_tags=("page", "definition"),
        ),
    ]

    result = project_topics(sources, catalog=catalog)

    assert [child.source_fields["evidence_kind"] for child in result.children] == [
        "exact_page_title",
        "redirect_alias",
        "exact_heading",
        "controlled_definition",
    ]
    assert [child.block.content for child in result.children] == [
        source.content for source in sources
    ]
    assert result.children[-1].block.route_tags == (
        "topic",
        "definition",
        "worldview",
    )


def test_explicit_structured_relation_is_exact_and_source_backed() -> None:
    catalog = validate_topic_catalog(
        _catalog(
            _topic(
                "storm",
                "暴雨",
                structured_relations=[
                    {"field": "topic_ids", "value": "storm"},
                ],
            )
        )
    )
    exact = _block_source(
        "story:1/story/step-1",
        content="Structured relation evidence.",
        source_fields={"topic_ids": ("storm",)},
    )
    near = _block_source(
        "story:2/story/step-1",
        content="Near relation must not bind.",
        source_fields={"topic_ids": ("storm-event",)},
    )

    result = project_topics([exact, near], catalog=catalog)

    assert [child.block.content for child in result.children] == [
        "Structured relation evidence."
    ]
    assert result.children[0].source_fields["evidence_kind"] == "structured_relation"


def test_scattered_character_voice_mentions_do_not_create_topic_children() -> None:
    catalog = validate_topic_catalog(
        _catalog(
            _topic(
                "storm",
                "暴雨",
                definition_patterns=[r"暴雨"],
            )
        )
    )
    voice = _block_source(
        "char:1/voice/line-1",
        content="角色语音只是提到了暴雨。",
        route_tags=("voice",),
    )

    result = project_topics([voice], catalog=catalog)

    assert result.children == ()
    assert result.parents == ()
    assert [(item.topic_id, item.reason_code) for item in result.diagnostics] == [
        ("storm", "topic_evidence_shortfall")
    ]


def test_topic_child_copies_one_source_child_and_preserves_owner_and_refs() -> None:
    catalog = validate_topic_catalog(
        _catalog(
            _topic("storm", "暴雨", exact_page_titles=["暴雨"])
        )
    )
    source = _page_child(
        "page:7/section:lead/chunk:0000",
        title="暴雨",
        content="Source text stays byte-for-byte.",
        heading_path=("定义",),
    )

    child = project_topics([source], catalog=catalog).children[0]

    assert child.block.content == child.block.text == source.content
    assert child.block.source_refs == source.source_refs
    assert child.source_fields == {
        "evidence_kind": "exact_page_title",
        "source_child_id": source.child_id,
        "source_parent_id": source.parent_id,
        "source_owner_entity_id": source.owner_entity_id,
        "source_owner_page_id": source.owner_page_id,
        "source_entity_type": source.entity_type,
    }
    assert child.owner_entity_id == "topic:storm"
    assert child.owner_page_id == "topic:storm"


def test_one_source_child_can_bind_multiple_topics_without_text_hash_dedup() -> None:
    catalog = validate_topic_catalog(
        _catalog(
            _topic("alpha", "Alpha", exact_page_titles=["Shared"]),
            _topic("beta", "Beta", exact_page_titles=["Shared"]),
        )
    )
    source = _page_child("shared-child", title="Shared", content="Shared evidence.")

    result = project_topics([source], catalog=catalog)

    assert [child.block.entity_id for child in result.children] == ["alpha", "beta"]
    assert len({child.block.child_id for child in result.children}) == 2
    assert {child.source_fields["source_child_id"] for child in result.children} == {
        "shared-child"
    }
    assert [child.block.content for child in result.children] == [
        "Shared evidence.",
        "Shared evidence.",
    ]


def test_topic_without_eligible_evidence_emits_shortfall_not_synthetic_content() -> None:
    catalog = validate_topic_catalog(
        _catalog(
            _topic("storm", "暴雨", exact_page_titles=["暴雨"])
        )
    )

    result = project_topics([], catalog=catalog)

    assert result.parents == ()
    assert result.children == ()
    assert result.diagnostics[0].reason_code == "topic_evidence_shortfall"
    assert result.diagnostics[0].details == {"selector_count": 1}


def test_empty_content_with_valid_source_refs_is_ignored_as_topic_evidence() -> None:
    catalog = validate_topic_catalog(
        _catalog(_topic("sparse", "Sparse", exact_heading_titles=["lead"]))
    )
    source = _page_child("sparse-child", title="Other", content="")

    result = project_topics([source], catalog=catalog)

    assert result.parents == ()
    assert result.children == ()
    assert [(item.topic_id, item.reason_code) for item in result.diagnostics] == [
        ("sparse", "topic_evidence_shortfall")
    ]


def test_empty_content_exact_title_source_cannot_create_topic_child() -> None:
    catalog = validate_topic_catalog(
        _catalog(_topic("sparse", "Sparse", exact_page_titles=["Sparse"]))
    )
    source = _page_child("sparse-title", title="Sparse", content="")

    result = project_topics([source], catalog=catalog)

    assert result.parents == ()
    assert result.children == ()
    assert result.diagnostics[0].reason_code == "topic_evidence_shortfall"


def test_topic_source_missing_source_refs_remains_fail_closed() -> None:
    catalog = validate_topic_catalog(
        _catalog(_topic("sparse", "Sparse", exact_page_titles=["Sparse"]))
    )
    source = replace(
        _page_child("missing-refs", title="Sparse", content="Evidence."),
        source_refs=(),
    )

    with pytest.raises(ValueError, match="source refs"):
        project_topics([source], catalog=catalog)


def test_non_empty_topic_source_missing_heading_path_remains_fail_closed() -> None:
    catalog = validate_topic_catalog(
        _catalog(_topic("sparse", "Sparse", exact_page_titles=["Sparse"]))
    )
    source = replace(
        _page_child("missing-heading", title="Sparse", content="Evidence."),
        heading_path=(),
    )

    with pytest.raises(ValueError, match="heading path"):
        project_topics([source], catalog=catalog)


def test_topic_page_story_rows_share_exact_public_child_contract() -> None:
    catalog = validate_topic_catalog(
        _catalog(
            _topic("storm", "暴雨", exact_page_titles=["暴雨"])
        )
    )
    page = _page_child("page-child", title="暴雨", content="Page evidence.")
    story = _block_source("story-child", content="Story evidence.")
    topic = project_topics([page], catalog=catalog).children[0]
    frozen_fields = {
        "category",
        "entity_type",
        "entity_id",
        "entity_name",
        "entity_aliases",
        "owner_entity_id",
        "owner_page_id",
        "route_tags",
        "parent_id",
        "child_id",
        "heading_path",
        "section_kind",
        "content",
        "search_text",
        "source_refs",
    }

    assert frozen_fields <= set(page.to_json())
    assert frozen_fields <= set(story.block.to_json()) | {
        "owner_entity_id",
        "owner_page_id",
    }
    assert frozen_fields <= set(topic.to_json())
    assert "owner_type" not in topic.to_json()


def test_projection_adapter_selects_from_page_and_story_children() -> None:
    catalog = validate_topic_catalog(
        _catalog(
            _topic(
                "storm",
                "暴雨",
                exact_page_titles=["暴雨"],
                structured_relations=[
                    {"field": "topic_ids", "value": "storm"},
                ],
            )
        )
    )
    page = _page_child("page-child", title="暴雨", content="Page evidence.")
    story = _block_source(
        "story-child",
        content="Story evidence.",
        source_fields={"topic_ids": ("storm",)},
    )

    page_result = type("PageResult", (), {"children": (page,)})()
    data_result = type("DataResult", (), {"children": (story,)})()

    result = project_topic_semantics(page_result, data_result, catalog=catalog)

    assert [child.block.content for child in result.children] == [
        "Page evidence.",
        "Story evidence.",
    ]
