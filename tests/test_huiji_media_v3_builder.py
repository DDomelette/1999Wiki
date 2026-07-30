from __future__ import annotations

import hashlib
import inspect
from dataclasses import replace
from pathlib import Path

import pytest

from src.huiji_rag.build import media_v3 as media_v3_module
from src.huiji_rag.build.contracts import (
    VoiceBindingInput,
    canonical_json_bytes,
    compute_binding_id,
)
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
    SemanticRecordLink,
)
from src.huiji_rag.build.voice_stage import VoiceBindingStage
from src.huiji_rag.models import ChildBlock, ParentBlock, VoiceSourceRow


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


def _legacy_media_case(tmp_path: Path):
    config, resources, projection, voice_result, _prepared = _fixture(tmp_path)
    collection = next(
        child for child in projection.children if child.block.section_kind == "collection"
    )
    parent = ParentBlock(
        parent_id=collection.block.parent_id,
        entity_id=collection.block.entity_id,
        entity_name=collection.block.entity_name,
        entity_aliases=(),
        category=collection.block.category,
        section_kind=collection.block.section_kind,
        title=collection.block.title,
        summary_text=collection.block.text,
        source_refs=collection.block.source_refs,
        child_ids=(collection.block.child_id,),
        content_hash=collection.block.content_hash,
    )
    projection = replace(projection, parents=(parent,))
    assembly = assemble_media_v3(config, projection, resources, voice_result)
    candidate = next(
        dict(row)
        for row in assembly.runtime_rows
        if row["media_role"] == "collection_item"
    )
    crawler_ref = next(
        ref
        for ref in candidate["source_refs"]
        if ref["source_kind"] == "crawler_resource"
    )
    active = {
        "entity_id": candidate["entity_id"],
        "entity_name": candidate["entity_name"],
        "parent_id": candidate["parent_id"],
        "child_id": candidate["child_id"],
        "media_id": candidate["media_id"],
        "sha1": candidate["sha1"],
        "filename": candidate["filename"],
        "title": crawler_ref["source_title"],
        "local_relpath": "legacy/path/is/not/manifest/evidence.png",
        "asset_type": candidate["asset_type"],
        "mime": candidate["mime"],
        "url": candidate["url"],
    }
    return config, resources, projection, voice_result, assembly, active


def _reconcile_case(
    config: MediaV3Config,
    projection: CorpusProjection,
    voice_result,
    assembly,
    resource_manifest_rows,
    *active_rows: dict[str, object],
    verified_source_removal_receipts=None,
):
    kwargs = {
        "raw_root": config.raw_root,
        "resource_manifest_rows": resource_manifest_rows,
    }
    if verified_source_removal_receipts is not None:
        kwargs["verified_source_removal_receipts"] = (
            verified_source_removal_receipts
        )
    return reconcile_active_media_occurrences(
        active_rows, assembly, projection, voice_result, **kwargs
    )


def _candidate_for_active(assembly, active: dict[str, object]) -> dict[str, object]:
    return next(
        dict(row)
        for row in assembly.runtime_rows
        if row["media_id"] == active["media_id"]
        and row["sha1"] == active["sha1"]
        and row["filename"] == active["filename"]
    )


def _manifest_for_active(resource_rows, active: dict[str, object]) -> dict[str, object]:
    return next(
        dict(row)
        for row in resource_rows
        if row["sha1"] == active["sha1"]
        and row["name"] == active["filename"]
        and row["title"] == active["title"]
    )


def _verified_removal_receipt(
    active: dict[str, object], **overrides: object
) -> dict[str, object]:
    payload = {
        "schema_version": "huiji.verified-source-removal-receipt/v1",
        "legacy_media_id": active["media_id"],
        "sha1": active["sha1"],
        "filename": active["filename"],
        "title": active["title"],
        "parent_id": active["parent_id"],
        "child_id": active["child_id"],
        "source_inventory_sha256": "9" * 64,
        "removal_reason": "relation_removed_from_pinned_source",
        **overrides,
    }
    return {
        **payload,
        "receipt_sha256": hashlib.sha256(
            canonical_json_bytes(payload, trailing_newline=False)
        ).hexdigest(),
    }


def _with_candidate_rows(assembly, *rows: dict[str, object]):
    inventory_by_binding = {
        row["binding_id"]: dict(row) for row in assembly.binding_inventory
    }
    inventories = []
    for row in rows:
        base = dict(next(iter(inventory_by_binding.values())))
        for field in (
            "binding_id",
            "resource_id",
            "owner_entity_id",
            "owner_page_id",
            "parent_id",
            "child_id",
            "media_role",
            "source_binding_token",
            "sha1",
            "content_sha256",
            "size",
        ):
            base[field] = row[field]
        inventories.append(base)
    return replace(
        assembly,
        runtime_rows=tuple(rows),
        binding_inventory=tuple(inventories),
        binding_count=len(rows),
    )


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


def test_active_occurrence_mapping_preserves_multiplicity_and_blocks_legacy_guess(
    tmp_path: Path,
) -> None:
    config, resources, projection, voice_result, assembly, exact = (
        _legacy_media_case(tmp_path)
    )
    broad_resource = _resource(config.raw_root, "Bgmusic_theme.mp3", b"legacy guess")
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
        (exact, dict(exact), broad),
        assembly,
        projection,
        voice_result,
        raw_root=config.raw_root,
        resource_manifest_rows=resources,
    )

    assert result.active_occurrence_count == 3
    assert len(result.occurrence_rows) == 3
    assert len({row["occurrence_id"] for row in result.occurrence_rows}) == 3
    assert result.category_counts == {
        "ambiguous_binding": 2,
        "missing_resource_metadata": 1,
    }
    assert result.unexplained_binding_loss == 3
    legacy = next(
        row
        for row in result.occurrence_rows
        if row["active_media_id"] == broad["media_id"]
    )
    assert legacy["classification"] == "missing_resource_metadata"
    assert legacy["resource_id"] == ""
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


def test_legacy_media_real_v1_boundary_uses_separate_manifest_bytes(
    tmp_path: Path,
) -> None:
    config, resources, projection, voice_result, assembly, active = (
        _legacy_media_case(tmp_path)
    )
    manifest = _manifest_for_active(resources, active)
    candidate = _candidate_for_active(assembly, active)
    candidate_only_fields = {
        "size",
        "owner_entity_id",
        "owner_page_id",
        "source_refs",
        "binding_id",
        "resource_id",
        "source_binding_token",
        "content_sha256",
    }

    assert "resource_manifest_rows" in inspect.signature(
        reconcile_active_media_occurrences
    ).parameters
    assert candidate_only_fields.isdisjoint(active)

    result = _reconcile_case(
        config, projection, voice_result, assembly, resources, active
    )

    assert result.category_counts == {"preserved_binding": 1}
    assert result.occurrence_rows[0]["candidate_binding_ids"] == [
        candidate["binding_id"]
    ]
    assert result.occurrence_rows[0]["local_evidence"] == {
        "content_sha256": candidate["content_sha256"],
        "size": manifest["size"],
        "sha1": manifest["sha1"],
        "local_relpath": manifest["local_relpath"],
    }


@pytest.mark.parametrize(
    ("manifest_case", "expected"),
    [
        ("identical_duplicate", "preserved_binding"),
        ("missing", "missing_resource_metadata"),
        ("conflicting_duplicate", "missing_resource_metadata"),
        ("invalid_size", "missing_resource_metadata"),
        ("candidate_size_mismatch", "ambiguous_binding"),
        ("missing_manifest_bytes", "missing_local_bytes"),
    ],
)
def test_legacy_media_manifest_identity_is_unique_exact_and_authoritative(
    tmp_path: Path,
    manifest_case: str,
    expected: str,
) -> None:
    config, resources, projection, voice_result, assembly, active = (
        _legacy_media_case(tmp_path)
    )
    manifest = _manifest_for_active(resources, active)
    other_resources = tuple(
        row
        for row in resources
        if not (
            row["sha1"] == active["sha1"]
            and row["name"] == active["filename"]
            and row["title"] == active["title"]
        )
    )
    manifests = resources
    if manifest_case == "identical_duplicate":
        manifests = (*resources, dict(manifest))
    elif manifest_case == "missing":
        manifests = other_resources
    elif manifest_case == "conflicting_duplicate":
        manifests = (*resources, {**manifest, "size": int(manifest["size"]) + 1})
    elif manifest_case == "invalid_size":
        manifests = (*other_resources, {**manifest, "size": "invalid"})
    elif manifest_case == "candidate_size_mismatch":
        candidate = _candidate_for_active(assembly, active)
        candidate["size"] = int(candidate["size"]) + 1
        assembly = _with_candidate_rows(assembly, candidate)
    elif manifest_case == "missing_manifest_bytes":
        manifests = (
            *other_resources,
            {**manifest, "local_relpath": "assets/missing/manifest-path.png"},
        )

    result = _reconcile_case(
        config, projection, voice_result, assembly, manifests, active
    )

    assert result.occurrence_rows[0]["classification"] == expected


@pytest.mark.parametrize(
    "active_change",
    [
        {"entity_id": ""},
        {"parent_id": "page:1001/collection"},
    ],
)
def test_legacy_media_owner_derivation_is_limited_to_character_rows(
    tmp_path: Path,
    active_change: dict[str, str],
) -> None:
    config, resources, projection, voice_result, assembly, active = (
        _legacy_media_case(tmp_path)
    )
    active.update(active_change)
    if "parent_id" in active_change:
        candidate = _candidate_for_active(assembly, active)
        projection = replace(
            projection,
            record_links=(
                SemanticRecordLink(
                    record_kind="parent",
                    legacy_id=str(active["parent_id"]),
                    candidate_id=str(candidate["parent_id"]),
                    change_kind="preserved_rekeyed",
                    source_title="Data:Char/1001.json",
                    source_content_sha256=SOURCE_SHA,
                    json_path="$.character_data.0",
                    legacy_section="collection",
                    candidate_section="collection",
                ),
            ),
        )

    result = _reconcile_case(
        config, projection, voice_result, assembly, resources, active
    )

    assert result.occurrence_rows[0]["classification"] == "conflicting_binding"


def test_legacy_media_candidate_lookup_is_bounded_to_exact_media_sha1_bucket(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config, resources, projection, voice_result, assembly, active = (
        _legacy_media_case(tmp_path)
    )
    candidate = _candidate_for_active(assembly, active)
    unrelated = []
    for index in range(40):
        sha1 = f"{index + 100:040x}"
        row = {
            **candidate,
            "media_id": f"media:sha1:{sha1}",
            "sha1": sha1,
            "source_sha1": sha1,
            "source_binding_token": f"unrelated:{index}",
        }
        row["binding_id"] = compute_binding_id(row)
        unrelated.append(row)
    assembly = _with_candidate_rows(assembly, *unrelated, candidate)
    calls = 0
    exact_match = media_v3_module._exact_legacy_resource_match

    def counted_exact_match(*args, **kwargs):
        nonlocal calls
        calls += 1
        return exact_match(*args, **kwargs)

    monkeypatch.setattr(
        media_v3_module, "_exact_legacy_resource_match", counted_exact_match
    )

    result = _reconcile_case(
        config, projection, voice_result, assembly, resources, active
    )

    assert result.occurrence_rows[0]["classification"] == "preserved_binding"
    assert calls == 1


def test_legacy_media_complete_child_and_parent_successor_sets_stay_ambiguous(
    tmp_path: Path,
) -> None:
    config, resources, projection, voice_result, assembly, active = (
        _legacy_media_case(tmp_path)
    )
    candidate = _candidate_for_active(assembly, active)
    legacy_child = "char:1001/culture:legacy"
    legacy_parent = "char:1001/culture"
    active.update({"child_id": legacy_child, "parent_id": legacy_parent})
    links = tuple(
        SemanticRecordLink(
            record_kind=kind,
            legacy_id=legacy_id,
            candidate_id=candidate_id,
            change_kind="preserved_rekeyed",
            source_title="Data:Char/1001.json",
            source_content_sha256=SOURCE_SHA,
            json_path="$.character_data.0",
            legacy_section="culture",
            candidate_section="collection",
        )
        for kind, legacy_id, candidate_id in (
            ("child", legacy_child, candidate["child_id"]),
            ("child", legacy_child, str(candidate["child_id"]) + ":successor"),
            ("parent", legacy_parent, candidate["parent_id"]),
            ("parent", legacy_parent, str(candidate["parent_id"]) + ":successor"),
        )
    )

    result = _reconcile_case(
        config,
        replace(projection, record_links=links),
        voice_result,
        assembly,
        resources,
        active,
    )

    assert result.occurrence_rows[0]["classification"] == "ambiguous_binding"
    assert result.occurrence_rows[0]["candidate_child_ids"] == sorted(
        [candidate["child_id"], str(candidate["child_id"]) + ":successor"]
    )
    assert result.occurrence_rows[0]["candidate_parent_ids"] == sorted(
        [candidate["parent_id"], str(candidate["parent_id"]) + ":successor"]
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "legacy_media_id",
        "legacy_sha1",
        "stem_only",
        "fuzzy_title",
        "ordinal_only",
        "count_only",
    ],
)
def test_legacy_media_resource_identity_requires_every_exact_field(
    tmp_path: Path,
    mutation: str,
) -> None:
    config, resources, projection, voice_result, assembly, active = (
        _legacy_media_case(tmp_path)
    )
    candidate = _candidate_for_active(assembly, active)
    if mutation == "legacy_media_id":
        active["media_id"] = "media:sha1:" + "0" * 40
    elif mutation == "legacy_sha1":
        active["sha1"] = "0" * 40
    elif mutation == "stem_only":
        active["filename"] = Path(str(candidate["filename"])).stem
    elif mutation == "fuzzy_title":
        active["title"] = str(active["title"]).lower()
    elif mutation == "ordinal_only":
        active["filename"] = ""
        active["legacy_ordinal"] = candidate["sort_order"]
    elif mutation == "count_only":
        active["filename"] = ""
        active["candidate_count_hint"] = 1
    changed = _with_candidate_rows(assembly, candidate)

    result = _reconcile_case(
        config, projection, voice_result, changed, resources, active
    )

    expected = (
        "ambiguous_binding"
        if mutation == "legacy_media_id"
        else "missing_resource_metadata"
    )
    assert result.occurrence_rows[0]["classification"] == expected
    assert result.occurrence_rows[0]["candidate_binding_ids"] == []


@pytest.mark.parametrize(
    "candidate_identity_failure",
    [
        "filename",
        "crawler_ref_row_id",
        "crawler_ref_title",
        "content_sha256",
        "resource_id",
        "size",
        "binding_id",
    ],
)
def test_legacy_media_valid_manifest_candidate_identity_failures_are_zero_exact_candidate_ambiguity(
    tmp_path: Path,
    candidate_identity_failure: str,
) -> None:
    config, resources, projection, voice_result, assembly, active = (
        _legacy_media_case(tmp_path)
    )
    manifest = _manifest_for_active(resources, active)
    candidate = _candidate_for_active(assembly, active)
    if candidate_identity_failure == "filename":
        candidate["filename"] = "different-" + str(candidate["filename"])
    elif candidate_identity_failure.startswith("crawler_ref_"):
        field = (
            "source_row_id"
            if candidate_identity_failure == "crawler_ref_row_id"
            else "source_title"
        )
        candidate["source_refs"] = [
            {
                **dict(ref),
                **(
                    {field: "mismatched-crawler-resource-evidence"}
                    if ref["source_kind"] == "crawler_resource"
                    else {}
                ),
            }
            for ref in candidate["source_refs"]
        ]
    elif candidate_identity_failure == "content_sha256":
        candidate["content_sha256"] = "0" * 64
    elif candidate_identity_failure == "resource_id":
        candidate["resource_id"] = "resource:sha256:" + "1" * 64
        candidate["binding_id"] = compute_binding_id(candidate)
    elif candidate_identity_failure == "size":
        candidate["size"] = int(candidate["size"]) + 1
    else:
        candidate["binding_id"] = "binding:sha256:" + "0" * 64
    changed = _with_candidate_rows(assembly, candidate)
    coarse_bucket = [
        row
        for row in changed.runtime_rows
        if row["media_id"] == active["media_id"]
        and row["sha1"] == active["sha1"]
    ]

    result = _reconcile_case(
        config, projection, voice_result, changed, resources, active
    )

    assert manifest["sha1"] == active["sha1"]
    assert len(coarse_bucket) == 1
    assert result.occurrence_rows[0]["candidate_binding_ids"] == []
    assert result.occurrence_rows[0]["classification"] == "ambiguous_binding"


@pytest.mark.parametrize("cardinality", ["candidate", "source", "successor"])
def test_legacy_media_non_unique_cardinality_is_ambiguous(
    tmp_path: Path,
    cardinality: str,
) -> None:
    config, resources, projection, voice_result, assembly, active = (
        _legacy_media_case(tmp_path)
    )
    candidate = _candidate_for_active(assembly, active)
    expected_binding_ids = [candidate["binding_id"]]
    if cardinality == "candidate":
        duplicate = {**candidate, "source_binding_token": "collection:200:duplicate"}
        duplicate["binding_id"] = compute_binding_id(duplicate)
        assembly = _with_candidate_rows(assembly, candidate, duplicate)
        expected_binding_ids.append(duplicate["binding_id"])
    elif cardinality == "source":
        intent = next(
            item
            for item in projection.media_intents
            if item.source_binding_token == candidate["source_binding_token"]
        )
        projection = replace(projection, media_intents=(*projection.media_intents, intent))
    else:
        legacy_child = "char:1001/culture:legacy"
        active["child_id"] = legacy_child
        links = tuple(
            SemanticRecordLink(
                record_kind="child",
                legacy_id=legacy_child,
                candidate_id=value,
                change_kind="preserved_rekeyed",
                source_title="Data:Char/1001.json",
                source_content_sha256=SOURCE_SHA,
                json_path="$.character_data.0",
                legacy_section="culture",
                candidate_section="collection",
            )
            for value in (candidate["child_id"], str(candidate["child_id"]) + ":other")
        )
        projection = replace(projection, record_links=links)

    result = _reconcile_case(
        config, projection, voice_result, assembly, resources, active
    )

    assert result.occurrence_rows[0]["classification"] == "ambiguous_binding"
    assert result.occurrence_rows[0]["candidate_binding_ids"] == sorted(
        expected_binding_ids
    )


def test_legacy_media_zero_candidate_cardinality_is_ambiguous(
    tmp_path: Path,
) -> None:
    config, resources, projection, voice_result, assembly, active = (
        _legacy_media_case(tmp_path)
    )
    assembly = _with_candidate_rows(assembly)

    result = _reconcile_case(
        config, projection, voice_result, assembly, resources, active
    )

    assert result.occurrence_rows[0]["classification"] == "ambiguous_binding"
    assert result.occurrence_rows[0]["candidate_binding_ids"] == []


def test_legacy_media_zero_source_relation_cardinality_is_ambiguous(
    tmp_path: Path,
) -> None:
    config, resources, projection, voice_result, assembly, active = (
        _legacy_media_case(tmp_path)
    )
    candidate = _candidate_for_active(assembly, active)
    projection = replace(
        projection,
        media_intents=tuple(
            intent
            for intent in projection.media_intents
            if intent.source_binding_token != candidate["source_binding_token"]
        ),
    )

    result = _reconcile_case(
        config, projection, voice_result, assembly, resources, active
    )

    assert result.occurrence_rows[0]["classification"] == "ambiguous_binding"
    assert result.occurrence_rows[0]["candidate_binding_ids"] == [
        candidate["binding_id"]
    ]


@pytest.mark.parametrize("successor_kind", ["parent", "child"])
def test_legacy_media_zero_successor_cardinality_is_ambiguous(
    tmp_path: Path,
    successor_kind: str,
) -> None:
    config, resources, projection, voice_result, assembly, active = (
        _legacy_media_case(tmp_path)
    )
    candidate = _candidate_for_active(assembly, active)
    active[f"{successor_kind}_id"] = f"char:1001/legacy-{successor_kind}"

    result = _reconcile_case(
        config, projection, voice_result, assembly, resources, active
    )

    row = result.occurrence_rows[0]
    assert row["classification"] == "ambiguous_binding"
    assert row[f"candidate_{successor_kind}_ids"] == []
    assert row["candidate_binding_ids"] == [candidate["binding_id"]]


@pytest.mark.parametrize(
    "evidence_case",
    [
        "absent_manifest",
        "conflicting_manifest",
        "invalid_manifest",
    ],
)
def test_legacy_media_absent_invalid_or_conflicting_manifest_remains_missing_metadata(
    tmp_path: Path,
    evidence_case: str,
) -> None:
    config, resources, projection, voice_result, assembly, active = (
        _legacy_media_case(tmp_path)
    )
    manifest = _manifest_for_active(resources, active)
    other_resources = tuple(
        row
        for row in resources
        if not (
            row["sha1"] == active["sha1"]
            and row["name"] == active["filename"]
            and row["title"] == active["title"]
        )
    )
    manifests = resources
    if evidence_case == "absent_manifest":
        manifests = other_resources
    elif evidence_case == "conflicting_manifest":
        manifests = (*resources, {**manifest, "size": int(manifest["size"]) + 1})
    elif evidence_case == "invalid_manifest":
        manifests = (*other_resources, {**manifest, "size": "invalid"})

    result = _reconcile_case(
        config, projection, voice_result, assembly, manifests, active
    )

    assert result.occurrence_rows[0]["classification"] == (
        "missing_resource_metadata"
    )


def test_legacy_media_singleton_cardinalities_with_closure_identity_mismatch_are_conflicting(
    tmp_path: Path,
) -> None:
    config, resources, projection, voice_result, assembly, active = (
        _legacy_media_case(tmp_path)
    )
    candidate = _candidate_for_active(assembly, active)
    candidate["owner_page_id"] = "char:9999"
    candidate["binding_id"] = compute_binding_id(candidate)
    assembly = _with_candidate_rows(assembly, candidate)

    result = _reconcile_case(
        config, projection, voice_result, assembly, resources, active
    )

    row = result.occurrence_rows[0]
    assert row["classification"] == "conflicting_binding"
    assert row["candidate_parent_ids"] == [candidate["parent_id"]]
    assert row["candidate_child_ids"] == [candidate["child_id"]]
    assert row["candidate_binding_ids"] == [candidate["binding_id"]]


def test_legacy_media_bytes_are_checked_after_ambiguity_and_closure(
    tmp_path: Path,
) -> None:
    config, resources, projection, voice_result, assembly, active = (
        _legacy_media_case(tmp_path)
    )
    manifest = _manifest_for_active(resources, active)
    other_resources = tuple(
        row
        for row in resources
        if not (
            row["sha1"] == active["sha1"]
            and row["name"] == active["filename"]
            and row["title"] == active["title"]
        )
    )
    missing_bytes_resources = (
        *other_resources,
        {**manifest, "local_relpath": "assets/missing/not-present.png"},
    )
    candidate = _candidate_for_active(assembly, active)
    duplicate = {**candidate, "source_binding_token": "collection:200:duplicate"}
    duplicate["binding_id"] = compute_binding_id(duplicate)
    ambiguous = _with_candidate_rows(assembly, candidate, duplicate)
    conflict_candidate = {**candidate, "owner_page_id": "char:9999"}
    conflict_candidate["binding_id"] = compute_binding_id(conflict_candidate)
    conflicting = _with_candidate_rows(assembly, conflict_candidate)

    missing_result = _reconcile_case(
        config,
        projection,
        voice_result,
        assembly,
        missing_bytes_resources,
        active,
    )
    ambiguous_result = _reconcile_case(
        config,
        projection,
        voice_result,
        ambiguous,
        missing_bytes_resources,
        active,
    )
    conflict_result = _reconcile_case(
        config,
        projection,
        voice_result,
        conflicting,
        missing_bytes_resources,
        active,
    )

    assert missing_result.occurrence_rows[0]["classification"] == "missing_local_bytes"
    assert ambiguous_result.occurrence_rows[0]["classification"] == "ambiguous_binding"
    assert conflict_result.occurrence_rows[0]["classification"] == "conflicting_binding"
    assert missing_result.occurrence_rows[0]["local_evidence"] == {}


def test_legacy_media_verified_bytes_distinguish_preserved_and_proven_rekey(
    tmp_path: Path,
) -> None:
    config, resources, projection, voice_result, assembly, preserved = (
        _legacy_media_case(tmp_path)
    )
    manifest = _manifest_for_active(resources, preserved)
    candidate = _candidate_for_active(assembly, preserved)
    legacy_parent = "char:1001/culture"
    legacy_child = "char:1001/culture:0200"
    rekeyed = {**preserved, "parent_id": legacy_parent, "child_id": legacy_child}
    links = tuple(
        SemanticRecordLink(
            record_kind=kind,
            legacy_id=legacy_id,
            candidate_id=candidate_id,
            change_kind="preserved_rekeyed",
            source_title="Data:Char/1001.json",
            source_content_sha256=SOURCE_SHA,
            json_path="$.character_data.0",
            legacy_section="culture",
            candidate_section="collection",
        )
        for kind, legacy_id, candidate_id in (
            ("parent", legacy_parent, candidate["parent_id"]),
            ("child", legacy_child, candidate["child_id"]),
        )
    )
    changed = replace(projection, record_links=links)

    preserved_result = _reconcile_case(
        config, projection, voice_result, assembly, resources, preserved
    )
    rekeyed_result = _reconcile_case(
        config, changed, voice_result, assembly, resources, rekeyed
    )

    assert preserved_result.occurrence_rows[0]["classification"] == "preserved_binding"
    assert rekeyed_result.occurrence_rows[0]["classification"] == "rekeyed_binding"
    for result in (preserved_result, rekeyed_result):
        assert result.occurrence_rows[0]["local_evidence"] == {
            "content_sha256": candidate["content_sha256"],
            "size": manifest["size"],
            "sha1": manifest["sha1"],
            "local_relpath": manifest["local_relpath"],
        }


def test_legacy_media_source_removal_requires_hash_pinned_explicit_evidence(
    tmp_path: Path,
) -> None:
    config, resources, projection, voice_result, assembly, active = (
        _legacy_media_case(tmp_path)
    )
    absent = replace(assembly, runtime_rows=(), binding_inventory=(), binding_count=0)
    valid_receipt = _verified_removal_receipt(active)
    forged_receipt = {
        **valid_receipt,
        "child_id": "char:1001/forged-child",
    }

    assert "verified_source_removal_receipts" in inspect.signature(
        reconcile_active_media_occurrences
    ).parameters

    no_evidence = _reconcile_case(
        config,
        projection,
        voice_result,
        absent,
        resources,
        active,
        verified_source_removal_receipts=(),
    )
    forged = _reconcile_case(
        config,
        projection,
        voice_result,
        absent,
        resources,
        active,
        verified_source_removal_receipts=(forged_receipt,),
    )
    with_evidence = _reconcile_case(
        config,
        projection,
        voice_result,
        absent,
        resources,
        active,
        verified_source_removal_receipts=(valid_receipt,),
    )
    duplicate_evidence = _reconcile_case(
        config,
        projection,
        voice_result,
        absent,
        resources,
        active,
        verified_source_removal_receipts=(valid_receipt, dict(valid_receipt)),
    )

    assert no_evidence.occurrence_rows[0]["classification"] != (
        "source_removed_with_evidence"
    )
    assert forged.occurrence_rows[0]["classification"] != (
        "source_removed_with_evidence"
    )
    assert with_evidence.occurrence_rows[0]["classification"] == (
        "source_removed_with_evidence"
    )
    assert duplicate_evidence.occurrence_rows[0]["classification"] == (
        "ambiguous_binding"
    )


def test_legacy_media_duplicate_candidate_consumption_is_ambiguous(
    tmp_path: Path,
) -> None:
    config, resources, projection, voice_result, assembly, active = (
        _legacy_media_case(tmp_path)
    )

    result = _reconcile_case(
        config,
        projection,
        voice_result,
        assembly,
        resources,
        active,
        dict(active),
    )

    assert result.category_counts == {"ambiguous_binding": 2}
    assert all(
        row["candidate_binding_ids"]
        == [_candidate_for_active(assembly, active)["binding_id"]]
        for row in result.occurrence_rows
    )


def test_legacy_media_occurrence_identity_order_and_categories_are_deterministic(
    tmp_path: Path,
) -> None:
    config, resources, projection, voice_result, assembly, active = (
        _legacy_media_case(tmp_path)
    )
    second = {**active, "legacy_occurrence_token": "second"}
    first = {**active, "legacy_occurrence_token": "first"}

    forward = _reconcile_case(
        config, projection, voice_result, assembly, resources, first, second
    )
    reverse = _reconcile_case(
        config, projection, voice_result, assembly, resources, second, first
    )

    assert forward.occurrence_rows == reverse.occurrence_rows
    assert forward.category_counts == reverse.category_counts
    assert [row["occurrence_id"] for row in forward.occurrence_rows] == sorted(
        row["occurrence_id"] for row in forward.occurrence_rows
    )
