from src.rag.entity_lexicon import EntityLexicon


def test_entity_lexicon_longest_match_prefers_longer_name():
    lexicon = EntityLexicon.from_records([
        {"entity_name": "玛蒂尔", "entity_type": "character", "entity_id": "fixture-1"},
        {"entity_name": "玛蒂尔达", "entity_type": "character", "entity_id": "fixture-2"},
    ])

    match = lexicon.match("看一下玛蒂尔达的图片")

    assert match is not None
    assert match.canonical == "玛蒂尔达"
    assert match.matched_text == "玛蒂尔达"
    assert match.aliases == ()
    assert match.entity_type == "character"
    assert match.entity_id == "fixture-2"


def test_entity_lexicon_alias_maps_to_canonical_name():
    lexicon = EntityLexicon.from_records([
        {
            "entity_name": "十四行诗",
            "entity_aliases": ["Sonetto"],
            "entity_type": "character",
            "entity_id": "fixture-3",
        },
    ])

    match = lexicon.match("Sonetto 的技能是什么")

    assert match is not None
    assert match.canonical == "十四行诗"
    assert match.matched_text == "Sonetto"
    assert match.aliases == ("Sonetto",)


def test_entity_lexicon_keeps_same_name_different_owner_ambiguous():
    lexicon = EntityLexicon.from_records([
        {
            "entity_name": "同名实体",
            "entity_type": "character",
            "entity_id": "c1",
        },
        {
            "entity_name": "同名实体",
            "entity_type": "story",
            "entity_id": "s1",
        },
    ])

    resolution = lexicon.resolve("介绍同名实体", entity_type_hint=None)

    assert resolution.entity_ref is None
    assert {item.ownership_key for item in resolution.ambiguous} == {
        ("character", "c1"),
        ("story", "s1"),
    }
    assert lexicon.match("介绍同名实体") is None


def test_entity_lexicon_applies_server_type_hint_after_longest_term_selection():
    lexicon = EntityLexicon.from_records([
        {
            "entity_name": "同名实体",
            "entity_type": "character",
            "entity_id": "c1",
        },
        {
            "entity_name": "同名实体",
            "entity_type": "story",
            "entity_id": "s1",
        },
    ])

    resolution = lexicon.resolve("介绍同名实体", entity_type_hint="story")

    assert resolution.entity_ref is not None
    assert resolution.entity_ref.ownership_key == ("story", "s1")
    assert resolution.entity_ref.resolution_mode == "current_exact"
