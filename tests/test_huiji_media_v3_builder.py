from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path

import pytest

from src.huiji_rag.build.contracts import VoiceBindingInput
from src.huiji_rag.build.contracts import normalize_media_v3_rows
from src.huiji_rag.build.media_v3 import (
    MediaV3Config,
    assemble_media_v3,
    prepare_voice_resource_rows,
    reconcile_active_media_occurrences,
)
from src.huiji_rag.build.projection import (
    CorpusProjection,
    MediaBindingIntent,
    SemanticChild,
)
from src.huiji_rag.build.voice_stage import VoiceBindingStage
from src.huiji_rag.models import ChildBlock, VoiceSourceRow


SOURCE_SHA = "f" * 64


def _source_ref(title: str) -> dict[str, object]:
    return {
        "kind": "data_page",
        "title": title,
        "revid": 7,
        "content_sha256": SOURCE_SHA,
        "json_path": "$",
    }


def _child(
    entity_id: str,
    section: str,
    token: str,
    *,
    title: str,
    chunk_index: int = 0,
) -> SemanticChild:
    owner_page_id = f"char:{entity_id}"
    parent_id = f"{owner_page_id}/{section}"
    child_id = f"{parent_id}/{token}"
    ref = _source_ref(f"Data:Char/{entity_id}.json")
    return SemanticChild(
        block=ChildBlock(
            child_id=child_id,
            parent_id=parent_id,
            entity_id=entity_id,
            entity_name=f"Character {entity_id}",
            category="character",
            section_kind=section,
            title=title,
            text=title,
            search_text=title,
            chunk_index=chunk_index,
            media_ids=(),
            media_policy="on_intent" if section == "voice" else "auto",
            source_refs=(ref,),
            content_hash=hashlib.sha256(title.encode()).hexdigest(),
        ),
        stable_source_token=token,
        source_token_kind="source_id",
        owner_entity_id=f"character:{entity_id}",
        owner_page_id=owner_page_id,
    )


def _resource(raw_root: Path, filename: str, content: bytes) -> dict[str, object]:
    sha1 = hashlib.sha1(content).hexdigest()
    relative = Path("assets") / sha1 / filename
    path = raw_root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return {
        "name": filename,
        "title": f"File:{filename}",
        "descriptionurl": f"https://source.test/wiki/File:{filename}",
        "url": f"https://source.test/files/{filename}",
        "local_relpath": relative.as_posix(),
        "mime": "audio/mpeg" if filename.endswith(".mp3") else "image/png",
        "sha1": sha1,
        "size": len(content),
        "width": 128 if not filename.endswith(".mp3") else 0,
        "height": 256 if not filename.endswith(".mp3") else 0,
    }


def _wikitext_child(
    pageid: int,
    child_token: str,
    *,
    source_title: str,
) -> SemanticChild:
    owner_page_id = f"page:{pageid}"
    parent_id = f"{owner_page_id}/section:lead"
    child_id = f"{parent_id}/{child_token}"
    ref = {
        "source_kind": "crawler_wikitext",
        "source_title": source_title,
        "source_row_id": f"wikitext:{pageid}:10:0:20",
        "source_content_sha256": hashlib.sha256(source_title.encode()).hexdigest(),
        "pageid": pageid,
        "revid": 10,
        "heading_path": ("lead",),
        "char_start": 0,
        "char_end": 20,
    }
    return SemanticChild(
        block=ChildBlock(
            child_id=child_id,
            parent_id=parent_id,
            entity_id=owner_page_id,
            entity_name=source_title,
            category="page",
            section_kind="lead",
            title=source_title,
            text="Page media context.",
            search_text=f"{source_title} Page media context.",
            chunk_index=0,
            media_ids=(),
            media_policy="auto",
            source_refs=(ref,),
            content_hash=hashlib.sha256(b"Page media context.").hexdigest(),
            entity_type="page",
            route_tags=("page",),
            heading_path=("lead",),
        ),
        stable_source_token=child_token,
        source_token_kind="chunk",
        owner_entity_id=owner_page_id,
        owner_page_id=owner_page_id,
    )


def _wikitext_intent(
    child: SemanticChild,
    filename: str,
    *,
    token: str = "wiki:1:lead:abc:1",
) -> MediaBindingIntent:
    ref = {
        **child.block.source_refs[0],
        "original_filename": filename,
        "normalized_filename": filename,
        "original_caption": "Caption",
        "link_target": "",
        "display_title_source": "explicit_caption",
        "context_before": "Before",
        "context_after": "After",
        "adjacent_context_sha256": hashlib.sha256(b"Before\0After").hexdigest(),
    }
    return MediaBindingIntent(
        source_binding_token=token,
        owner_entity_id=child.owner_entity_id,
        owner_page_id=child.owner_page_id,
        parent_id=child.block.parent_id,
        child_id=child.block.child_id,
        section="lead",
        media_role="page_image",
        resource_stem="",
        title="Caption",
        source_refs=(ref,),
        resolver_mode="wikitext_exact",
        exact_filename=filename,
        original_filename=filename,
        heading_path=("lead",),
        title_source="explicit_caption",
        caption="Caption",
        adjacent_context_sha256=ref["adjacent_context_sha256"],
    )


def _fixture(tmp_path: Path):
    raw_root = tmp_path / "raw"
    raw_root.mkdir()
    resources = (
        _resource(raw_root, "100.png", b"shared skill bytes"),
        _resource(raw_root, "Belonging-200.webp", b"collection bytes"),
        _resource(raw_root, "Zh_Event_1001_Hello.mp3", b"voice bytes"),
        _resource(raw_root, "Bgmusic_theme.mp3", b"not a voice binding resource"),
    )
    config = MediaV3Config(
        raw_root=raw_root,
        public_base_url="http://127.0.0.1:9002",
        bucket_name="reverse1999-assets",
    )
    skill_a = _child("1001", "skills", "skill-100", title="Skill A")
    skill_b = _child("1002", "skills", "skill-100", title="Skill B")
    collection = _child("1001", "collection", "200", title="Collection")
    voice = _child("1001", "voice", "10", title="Greeting", chunk_index=3)
    intents = (
        MediaBindingIntent(
            source_binding_token="skill:100:100",
            owner_entity_id=skill_a.owner_entity_id,
            owner_page_id=skill_a.owner_page_id,
            parent_id=skill_a.block.parent_id,
            child_id=skill_a.block.child_id,
            section="skills",
            media_role="skill",
            resource_stem="Skill-100",
            title="Skill A",
            source_refs=skill_a.block.source_refs,
        ),
        MediaBindingIntent(
            source_binding_token="skill:100:100",
            owner_entity_id=skill_b.owner_entity_id,
            owner_page_id=skill_b.owner_page_id,
            parent_id=skill_b.block.parent_id,
            child_id=skill_b.block.child_id,
            section="skills",
            media_role="skill",
            resource_stem="Skill-100",
            title="Skill B",
            source_refs=skill_b.block.source_refs,
        ),
        MediaBindingIntent(
            source_binding_token="collection:200:200",
            owner_entity_id=collection.owner_entity_id,
            owner_page_id=collection.owner_page_id,
            parent_id=collection.block.parent_id,
            child_id=collection.block.child_id,
            section="collection",
            media_role="collection_item",
            resource_stem="Belonging-200",
            title="Collection",
            source_refs=collection.block.source_refs,
        ),
    )
    voice_source = VoiceSourceRow(
        source_id="Data:Char/1001.json:10:zh",
        entity_id="char:1001",
        parent_id=voice.block.parent_id,
        child_id=voice.block.child_id,
        audio_id="10",
        event_name="Event_1001_Hello",
        language="zh",
        transcript="Hello",
    )
    prepared = prepare_voice_resource_rows(config, resources)
    voice_result = VoiceBindingStage().run(
        VoiceBindingInput(
            source_rows=(voice_source,),
            resource_rows=prepared.resource_rows,
        )
    )
    projection = CorpusProjection(
        parents=(),
        children=(skill_a, skill_b, collection, voice),
        voice_sources=(voice_source,),
        media_intents=intents,
        exclusions=(),
        identity_fallbacks=(),
        record_links=(),
    )
    return config, resources, projection, voice_result, prepared


def test_media_v3_uses_explicit_relations_and_preserves_shared_bindings(tmp_path: Path) -> None:
    config, resources, projection, voice_result, prepared = _fixture(tmp_path)

    result = assemble_media_v3(config, projection, reversed(resources), voice_result)

    assert prepared.blockers == ()
    assert len(prepared.resource_rows) == 1
    assert result.blockers == ()
    assert result.binding_count == 4
    assert result.resource_count == 3
    assert result.shared_resource_groups == 1
    assert result.counts_by_role == {
        "collection_item": 1,
        "skill": 2,
        "voice": 1,
    }
    assert all("local_relpath" not in row for row in result.runtime_rows)
    assert all(row["is_available"] is False for row in result.runtime_rows)
    assert all(str(row["url"]).startswith("http://127.0.0.1:9002/") for row in result.runtime_rows)

    skill_rows = [row for row in result.runtime_rows if row["media_role"] == "skill"]
    assert len({row["resource_id"] for row in skill_rows}) == 1
    assert len({row["binding_id"] for row in skill_rows}) == 2
    assert {row["owner_entity_id"] for row in skill_rows} == {
        "character:1001",
        "character:1002",
    }
    assert all(row["asset_type"] == "skill" for row in skill_rows)
    assert all(row["filename"] == "100.png" for row in skill_rows)
    assert all("/image/" in row["object_key"] for row in skill_rows)

    collection_rows = [
        row for row in result.runtime_rows if row["media_role"] == "collection_item"
    ]
    assert len(collection_rows) == 1
    assert collection_rows[0]["asset_type"] == "image"
    assert "/image/" in collection_rows[0]["object_key"]

    voice_rows = [row for row in result.runtime_rows if row["media_role"] == "voice"]
    assert len(voice_rows) == 1
    assert voice_rows[0]["binding_status"] == "exact"
    assert voice_rows[0]["source_binding_token"] == "voice:10:zh"
    assert voice_rows[0]["child_id"] == "char:1001/voice/10"
    assert all("local_relpath" in row for row in result.binding_inventory)

    rebuilt = assemble_media_v3(config, projection, resources, voice_result)
    assert [dict(row) for row in rebuilt.runtime_rows] == [
        dict(row) for row in result.runtime_rows
    ]


def test_required_missing_resource_blocks_but_text_only_relations_remain_diagnostic(
    tmp_path: Path,
) -> None:
    config, resources, projection, voice_result, _prepared = _fixture(tmp_path)
    child = projection.children[0]
    missing = MediaBindingIntent(
        source_binding_token="skill:missing",
        owner_entity_id=child.owner_entity_id,
        owner_page_id=child.owner_page_id,
        parent_id=child.block.parent_id,
        child_id=child.block.child_id,
        section="skills",
        media_role="skill",
        resource_stem="Skill-404",
        title="Missing",
        source_refs=child.block.source_refs,
        missing_policy="required",
    )
    optional_missing = MediaBindingIntent(
        source_binding_token="skill:optional-missing",
        owner_entity_id=child.owner_entity_id,
        owner_page_id=child.owner_page_id,
        parent_id=child.block.parent_id,
        child_id=child.block.child_id,
        section="skills",
        media_role="skill",
        resource_stem="Skill-405",
        title="Optional missing",
        source_refs=child.block.source_refs,
    )
    no_reference = MediaBindingIntent(
        source_binding_token="collection:no-icon",
        owner_entity_id=child.owner_entity_id,
        owner_page_id=child.owner_page_id,
        parent_id=child.block.parent_id,
        child_id=child.block.child_id,
        section="collection",
        media_role="collection_item",
        resource_stem="",
        title="Text only",
        source_refs=child.block.source_refs,
    )
    changed = CorpusProjection(
        parents=projection.parents,
        children=projection.children,
        voice_sources=projection.voice_sources,
        media_intents=(
            *projection.media_intents,
            missing,
            optional_missing,
            no_reference,
        ),
        exclusions=projection.exclusions,
        identity_fallbacks=projection.identity_fallbacks,
        record_links=projection.record_links,
    )

    result = assemble_media_v3(config, changed, resources, voice_result)

    assert "media_resource_missing:skill:missing" in result.blockers
    assert not any("skill:optional-missing" in blocker for blocker in result.blockers)
    reasons = {row["reason_code"] for row in result.unresolved_intents}
    assert "referenced_resource_missing" in reasons
    assert "source_has_no_resource_reference" in reasons
    assert not any("collection:no-icon" in blocker for blocker in result.blockers)


def test_media_v3_selects_one_deterministic_preferred_format_per_relation(
    tmp_path: Path,
) -> None:
    config, resources, projection, voice_result, _prepared = _fixture(tmp_path)
    png_alternative = _resource(
        config.raw_root,
        "Belonging-200.png",
        b"collection png alternative",
    )

    result = assemble_media_v3(
        config,
        projection,
        (*resources, png_alternative),
        voice_result,
    )

    collection_rows = [
        row for row in result.runtime_rows if row["media_role"] == "collection_item"
    ]
    assert result.blockers == ()
    assert len(collection_rows) == 1
    assert collection_rows[0]["filename"] == "Belonging-200.webp"


def test_same_physical_voice_resource_uses_one_canonical_payload_across_languages(
    tmp_path: Path,
) -> None:
    config, resources, projection, _voice_result, _prepared = _fixture(tmp_path)
    english_resource = _resource(
        config.raw_root,
        "En_Event_1001_Hello.mp3",
        b"voice bytes",
    )
    chinese = projection.voice_sources[0]
    english = replace(
        chinese,
        source_id="Data:Char/1001.json:10:en",
        language="en",
        transcript="English transcript",
    )
    all_resources = (*resources, english_resource)
    prepared = prepare_voice_resource_rows(config, all_resources)
    voice_result = VoiceBindingStage().run(
        VoiceBindingInput(
            source_rows=(chinese, english),
            resource_rows=prepared.resource_rows,
        )
    )
    changed = replace(
        projection,
        voice_sources=(chinese, english),
    )

    result = assemble_media_v3(config, changed, all_resources, voice_result)
    voice_rows = [row for row in result.runtime_rows if row["media_role"] == "voice"]
    resources_v3, bindings_v3 = normalize_media_v3_rows(result.runtime_rows)

    assert result.blockers == ()
    assert len(voice_rows) == 2
    assert {row["language"] for row in voice_rows} == {"zh", "en"}
    assert len({row["resource_id"] for row in voice_rows}) == 1
    assert len({row["filename"] for row in voice_rows}) == 1
    assert len({row["source_url"] for row in voice_rows}) == 1
    assert len(bindings_v3) == result.binding_count
    assert len(resources_v3) == result.resource_count


def test_local_path_escape_is_diagnostic_and_blocks_readiness(tmp_path: Path) -> None:
    config, resources, projection, voice_result, _prepared = _fixture(tmp_path)
    outside = tmp_path / "outside.png"
    outside.write_bytes(b"outside")
    escaped = {
        "name": "Skill-100.png",
        "title": "File:Skill-100.png",
        "local_relpath": "../outside.png",
        "sha1": hashlib.sha1(b"outside").hexdigest(),
        "size": len(b"outside"),
        "mime": "image/png",
    }

    result = assemble_media_v3(config, projection, (*resources, escaped), voice_result)

    assert any("local_path_escape" in blocker for blocker in result.blockers)
    assert any(
        row["reason_code"] == "local_path_escape" for row in result.unresolved_intents
    )


def test_active_occurrence_mapping_preserves_multiplicity_and_classifies_legacy_guess(
    tmp_path: Path,
) -> None:
    config, resources, projection, voice_result, _prepared = _fixture(tmp_path)
    assembly = assemble_media_v3(config, projection, resources, voice_result)
    inventory_by_binding = {
        row["binding_id"]: row for row in assembly.binding_inventory
    }
    preserved = dict(assembly.runtime_rows[0])
    preserved["local_relpath"] = inventory_by_binding[preserved["binding_id"]][
        "local_relpath"
    ]
    broad_resource = next(row for row in resources if row["name"] == "Bgmusic_theme.mp3")
    broad = {
        "media_id": "media:sha1:" + str(broad_resource["sha1"]),
        "sha1": broad_resource["sha1"],
        "asset_type": "voice",
        "entity_id": "1001",
        "parent_id": "char:1001/profile",
        "child_id": "char:1001/profile/root",
        "local_relpath": broad_resource["local_relpath"],
    }

    result = reconcile_active_media_occurrences(
        (preserved, preserved, broad),
        assembly,
        projection,
        voice_result,
        raw_root=config.raw_root,
    )

    assert result.active_occurrence_count == 3
    assert len(result.occurrence_rows) == 3
    assert len({row["occurrence_id"] for row in result.occurrence_rows}) == 3
    assert result.category_counts == {
        "legacy_non_explicit_relation": 1,
        "preserved_binding": 2,
    }
    assert result.unexplained_binding_loss == 0
    legacy = next(
        row
        for row in result.occurrence_rows
        if row["classification"] == "legacy_non_explicit_relation"
    )
    assert str(legacy["resource_id"]).startswith("resource:sha256:")
    assert legacy["candidate_binding_ids"] == []


def test_wikitext_resolver_matches_full_filename_and_never_stem(tmp_path: Path) -> None:
    config, resources, projection, voice_result, _prepared = _fixture(tmp_path)
    child = _wikitext_child(1, "chunk:0000", source_title="Exact Page")
    exact_resource = _resource(config.raw_root, "Shared.png", b"exact bytes")
    exact_resource["sha256"] = hashlib.sha256(b"exact bytes").hexdigest()
    exact = _wikitext_intent(child, "Shared.png")
    title_only = _wikitext_intent(
        child,
        "TitleOnly.png",
        token="wiki:1:lead:title-only",
    )
    same_stem_wrong_extension = _wikitext_intent(
        child,
        "Shared.jpg",
        token="wiki:1:lead:def:1",
    )
    title_only_resource = _resource(
        config.raw_root,
        "TitleOnly.png",
        b"title-only bytes",
    )
    title_only_resource["sha256"] = hashlib.sha256(
        b"title-only bytes"
    ).hexdigest()
    title_only_resource.pop("name")
    changed = replace(
        projection,
        children=(*projection.children, child),
        media_intents=(
            *projection.media_intents,
            exact,
            title_only,
            same_stem_wrong_extension,
        ),
    )

    result = assemble_media_v3(
        config,
        changed,
        (*resources, exact_resource, title_only_resource),
        voice_result,
    )

    exact_rows = [
        row
        for row in result.runtime_rows
        if row["source_binding_token"] == exact.source_binding_token
    ]
    assert len(exact_rows) == 1
    assert exact_rows[0]["filename"] == "Shared.png"
    title_only_rows = [
        row
        for row in result.runtime_rows
        if row["source_binding_token"] == title_only.source_binding_token
    ]
    assert len(title_only_rows) == 1
    assert title_only_rows[0]["filename"] == "TitleOnly.png"
    missing = next(
        row
        for row in result.unresolved_intents
        if row["source_binding_token"] == same_stem_wrong_extension.source_binding_token
    )
    assert missing["reason_code"] == "referenced_resource_missing"
    assert missing["resolver_mode"] == "wikitext_exact"


def test_identical_exact_filename_sha1_size_rows_merge_source_evidence(
    tmp_path: Path,
) -> None:
    config, resources, projection, voice_result, _prepared = _fixture(tmp_path)
    child = _wikitext_child(2, "chunk:0000", source_title="Duplicate Page")
    intent = _wikitext_intent(child, "Duplicate.png", token="wiki:2:lead:abc:1")
    first = _resource(config.raw_root, "Duplicate.png", b"duplicate bytes")
    first["sha256"] = hashlib.sha256(b"duplicate bytes").hexdigest()
    second = {
        **first,
        "title": "File:Duplicate.png",
        "manifest_source_id": "second-row",
    }
    changed = replace(
        projection,
        children=(*projection.children, child),
        media_intents=(*projection.media_intents, intent),
    )

    result = assemble_media_v3(
        config,
        changed,
        (*resources, first, second),
        voice_result,
    )

    rows = [
        row
        for row in result.runtime_rows
        if row["source_binding_token"] == intent.source_binding_token
    ]
    assert len(rows) == 1
    assert not any("resource_filename_conflict" in item for item in result.blockers)
    resource_refs = [
        ref
        for ref in rows[0]["source_refs"]
        if ref["source_kind"] == "crawler_resource"
    ]
    assert len(resource_refs) == 2


def test_same_exact_resource_preserves_multiple_wikitext_bindings(
    tmp_path: Path,
) -> None:
    config, resources, projection, voice_result, _prepared = _fixture(tmp_path)
    first_child = _wikitext_child(20, "chunk:0000", source_title="First Page")
    second_child = _wikitext_child(21, "chunk:0000", source_title="Second Page")
    first_intent = _wikitext_intent(
        first_child,
        "SharedExact.png",
        token="wiki:20:lead:abc",
    )
    second_intent = _wikitext_intent(
        second_child,
        "SharedExact.png",
        token="wiki:21:lead:abc",
    )
    resource = _resource(config.raw_root, "SharedExact.png", b"shared exact")
    resource["sha256"] = hashlib.sha256(b"shared exact").hexdigest()
    changed = replace(
        projection,
        children=(*projection.children, first_child, second_child),
        media_intents=(
            *projection.media_intents,
            first_intent,
            second_intent,
        ),
    )

    result = assemble_media_v3(
        config,
        changed,
        (*resources, resource),
        voice_result,
    )

    rows = [
        row
        for row in result.runtime_rows
        if row["source_binding_token"]
        in {first_intent.source_binding_token, second_intent.source_binding_token}
    ]
    assert len(rows) == 2
    assert len({row["resource_id"] for row in rows}) == 1
    assert len({row["binding_id"] for row in rows}) == 2
    assert {row["owner_page_id"] for row in rows} == {"page:20", "page:21"}


def test_exact_filename_with_different_sha1_or_size_blocks_binding(
    tmp_path: Path,
) -> None:
    config, resources, projection, voice_result, _prepared = _fixture(tmp_path)
    child = _wikitext_child(3, "chunk:0000", source_title="Conflict Page")
    intent = _wikitext_intent(child, "Conflict.png", token="wiki:3:lead:abc:1")
    first = _resource(config.raw_root, "Conflict.png", b"first")
    first["sha256"] = hashlib.sha256(b"first").hexdigest()
    second = _resource(config.raw_root, "nested/Conflict.png", b"second")
    second["name"] = "Conflict.png"
    second["title"] = "File:Conflict.png"
    second["sha256"] = hashlib.sha256(b"second").hexdigest()
    changed = replace(
        projection,
        children=(*projection.children, child),
        media_intents=(*projection.media_intents, intent),
    )

    result = assemble_media_v3(
        config,
        changed,
        (*resources, first, second),
        voice_result,
    )

    assert not any(
        row["source_binding_token"] == intent.source_binding_token
        for row in result.runtime_rows
    )
    unresolved = next(
        row
        for row in result.unresolved_intents
        if row["source_binding_token"] == intent.source_binding_token
    )
    assert unresolved["reason_code"] == "resource_filename_conflict"
    assert any("resource_filename_conflict" in item for item in result.blockers)


def test_legacy_data_intents_keep_separate_stem_resolver(tmp_path: Path) -> None:
    config, resources, projection, voice_result, _prepared = _fixture(tmp_path)

    result = assemble_media_v3(config, projection, resources, voice_result)

    skill = next(row for row in result.runtime_rows if row["media_role"] == "skill")
    assert skill["filename"] == "100.png"
    assert projection.media_intents[0].resolver_mode == "legacy_stem"


def test_manifest_missing_and_local_not_downloaded_are_distinct(tmp_path: Path) -> None:
    config, resources, projection, voice_result, _prepared = _fixture(tmp_path)
    child = _wikitext_child(4, "chunk:0000", source_title="Availability Page")
    missing = _wikitext_intent(child, "Missing.png", token="wiki:4:lead:aaa:1")
    not_downloaded = _wikitext_intent(
        child,
        "NotDownloaded.png",
        token="wiki:4:lead:bbb:1",
    )
    manifest_only = {
        "name": "NotDownloaded.png",
        "title": "File:NotDownloaded.png",
        "local_relpath": "assets/not-downloaded/NotDownloaded.png",
        "download_status": " NOT_DOWNLOADED ",
        "sha1": hashlib.sha1(b"declared").hexdigest(),
        "sha256": hashlib.sha256(b"declared").hexdigest(),
        "size": len(b"declared"),
        "mime": "image/png",
    }
    changed = replace(
        projection,
        children=(*projection.children, child),
        media_intents=(*projection.media_intents, missing, not_downloaded),
    )

    result = assemble_media_v3(
        config,
        changed,
        (*resources, manifest_only),
        voice_result,
    )

    reasons = {
        row["source_binding_token"]: row["reason_code"]
        for row in result.unresolved_intents
        if row["source_binding_token"] in {
            missing.source_binding_token,
            not_downloaded.source_binding_token,
        }
    }
    assert reasons == {
        missing.source_binding_token: "referenced_resource_missing",
        not_downloaded.source_binding_token: "referenced_resource_not_downloaded",
    }
    assert not any(
        token in blocker
        for blocker in result.blockers
        for token in (
            missing.source_binding_token,
            not_downloaded.source_binding_token,
        )
    )


def test_downloaded_manifest_with_missing_local_path_preserves_integrity_blocker(
    tmp_path: Path,
) -> None:
    config, resources, projection, voice_result, _prepared = _fixture(tmp_path)
    child = _wikitext_child(40, "chunk:0000", source_title="Downloaded Page")
    intent = _wikitext_intent(
        child,
        "Downloaded.png",
        token="wiki:40:lead:downloaded",
    )
    manifest_row = {
        "name": "Downloaded.png",
        "title": "File:Downloaded.png",
        "local_relpath": "",
        "download_status": "Downloaded",
        "sha1": hashlib.sha1(b"declared").hexdigest(),
        "sha256": hashlib.sha256(b"declared").hexdigest(),
        "size": len(b"declared"),
        "mime": "image/png",
    }
    changed = replace(
        projection,
        children=(*projection.children, child),
        media_intents=(*projection.media_intents, intent),
    )

    result = assemble_media_v3(
        config,
        changed,
        (*resources, manifest_row),
        voice_result,
    )

    unresolved = next(
        row
        for row in result.unresolved_intents
        if row["source_binding_token"] == intent.source_binding_token
    )
    assert unresolved["reason_code"] == "local_path_missing"
    assert any(
        intent.source_binding_token in blocker and "local_path_missing" in blocker
        for blocker in result.blockers
    )
    assert not any(
        row["source_binding_token"] == intent.source_binding_token
        for row in result.runtime_rows
    )


@pytest.mark.parametrize("download_status", [None, "", "queued", "not-downloaded"])
def test_unproven_download_status_with_missing_file_fails_closed(
    tmp_path: Path,
    download_status: str | None,
) -> None:
    config, resources, projection, voice_result, _prepared = _fixture(tmp_path)
    child = _wikitext_child(41, "chunk:0000", source_title="Unknown Status Page")
    intent = _wikitext_intent(
        child,
        "UnknownStatus.png",
        token=f"wiki:41:lead:{download_status or 'missing'}",
    )
    manifest_row = {
        "name": "UnknownStatus.png",
        "title": "File:UnknownStatus.png",
        "local_relpath": "assets/missing/UnknownStatus.png",
        "sha1": hashlib.sha1(b"declared").hexdigest(),
        "sha256": hashlib.sha256(b"declared").hexdigest(),
        "size": len(b"declared"),
        "mime": "image/png",
    }
    if download_status is not None:
        manifest_row["download_status"] = download_status
    changed = replace(
        projection,
        children=(*projection.children, child),
        media_intents=(*projection.media_intents, intent),
    )

    result = assemble_media_v3(
        config,
        changed,
        (*resources, manifest_row),
        voice_result,
    )

    unresolved = next(
        row
        for row in result.unresolved_intents
        if row["source_binding_token"] == intent.source_binding_token
    )
    assert unresolved["reason_code"] == "local_file_missing"
    assert any(
        intent.source_binding_token in blocker and "local_file_missing" in blocker
        for blocker in result.blockers
    )
    assert not any(
        row["source_binding_token"] == intent.source_binding_token
        for row in result.runtime_rows
    )


@pytest.mark.parametrize(
    ("mutate", "reason_code"),
    [
        (lambda row: row.pop("sha256"), "resource_sha256_missing"),
        (
            lambda row: row.update({"sha1": "0" * 40}),
            "local_sha1_mismatch",
        ),
        (
            lambda row: row.update({"sha256": "0" * 64}),
            "local_sha256_mismatch",
        ),
        (
            lambda row: row.update({"size": int(row["size"]) + 1}),
            "local_size_mismatch",
        ),
    ],
)
def test_local_present_requires_sha1_sha256_and_size(
    tmp_path: Path,
    mutate,
    reason_code: str,
) -> None:
    config, resources, projection, voice_result, _prepared = _fixture(tmp_path)
    child = _wikitext_child(5, "chunk:0000", source_title="Validation Page")
    intent = _wikitext_intent(child, "Validate.png", token="wiki:5:lead:abc:1")
    resource = _resource(config.raw_root, "Validate.png", b"validate")
    resource["sha256"] = hashlib.sha256(b"validate").hexdigest()
    mutate(resource)
    changed = replace(
        projection,
        children=(*projection.children, child),
        media_intents=(*projection.media_intents, intent),
    )

    result = assemble_media_v3(
        config,
        changed,
        (*resources, resource),
        voice_result,
    )

    assert not any(
        row["source_binding_token"] == intent.source_binding_token
        for row in result.runtime_rows
    )
    unresolved = next(
        row
        for row in result.unresolved_intents
        if row["source_binding_token"] == intent.source_binding_token
    )
    assert unresolved["reason_code"] == reason_code
    assert any(reason_code in blocker for blocker in result.blockers)


def test_media_v3_rejects_unknown_child_and_invalid_source_ref_closure(
    tmp_path: Path,
) -> None:
    config, resources, projection, voice_result, _prepared = _fixture(tmp_path)
    child = _wikitext_child(6, "chunk:0000", source_title="Closure Page")
    valid = _wikitext_intent(child, "Closure.png", token="wiki:6:lead:abc:1")
    invalid = replace(
        valid,
        source_binding_token="wiki:6:lead:def:1",
        source_refs=(
            {
                **valid.source_refs[0],
                "adjacent_context_sha256": "",
            },
        ),
    )
    unknown = replace(
        valid,
        source_binding_token="wiki:6:lead:ghi:1",
        child_id="page:missing/section:lead/chunk:0000",
    )
    resource = _resource(config.raw_root, "Closure.png", b"closure")
    resource["sha256"] = hashlib.sha256(b"closure").hexdigest()
    changed = replace(
        projection,
        children=(*projection.children, child),
        media_intents=(*projection.media_intents, invalid, unknown),
    )

    result = assemble_media_v3(
        config,
        changed,
        (*resources, resource),
        voice_result,
    )

    reasons = {
        row["source_binding_token"]: row["reason_code"]
        for row in result.unresolved_intents
        if row["source_binding_token"] in {
            invalid.source_binding_token,
            unknown.source_binding_token,
        }
    }
    assert reasons == {
        invalid.source_binding_token: "invalid_wikitext_source_ref",
        unknown.source_binding_token: "unknown_child",
    }
    assert all(
        any(token in blocker for blocker in result.blockers)
        for token in reasons
    )
