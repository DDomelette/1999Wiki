from __future__ import annotations

import json
from dataclasses import replace

import pytest

from src.huiji_rag.artifacts import (
    INTERNAL_MEDIA_ASSET_V2_FIELDS,
    MEDIA_ASSET_V2_FIELDS,
    adapt_legacy_media_row,
    build_binding_inventory,
    build_entity_name_directory,
    build_entity_name_exclusions,
    build_runtime_media_projection,
    canonical_nonvoice_projection_sha256,
    write_media_artifacts,
)
from src.huiji_rag.io import evb_build_paths, iter_jsonl
from src.huiji_rag.models import (
    ArtifactManifest,
    BindingRecord,
    BindingStatus,
    EntityNameDirectory,
    MediaArtifacts,
    ResourceRow,
    VoiceSourceRow,
)


LEGACY_FIELDS = (
    "media_id",
    "entity_id",
    "entity_name",
    "parent_id",
    "child_id",
    "asset_type",
    "mime",
    "filename",
    "title",
    "source_url",
    "url",
    "object_key",
    "is_available",
    "is_common",
    "attach_policy",
    "search_text",
    "content_hash",
    "panel_group",
    "sort_order",
    "duration_ms",
    "quality_flags",
    "local_relpath",
    "sha1",
)
V2_FIELDS = (
    "event_name",
    "language",
    "source_sha1",
    "content_sha256",
    "binding_status",
    "artifact_schema_version",
    "binding_key",
)
PUBLIC_BASE_URL = "https://media.example.test/assets"
BUCKET_NAME = "fixture-bucket"


def _directory(
    entries: dict[str, tuple[str, str]] | None = None,
    conflicts: dict[str, tuple[tuple[str, str], ...]] | None = None,
) -> EntityNameDirectory:
    return EntityNameDirectory(entries=entries or {}, conflicts=conflicts or {})


def _schema(**overrides: object) -> dict[str, object]:
    schema: dict[str, object] = {
        "schema_version": "evb.media-assets/v2",
        "fields": list(MEDIA_ASSET_V2_FIELDS),
        "internal_fields": list(INTERNAL_MEDIA_ASSET_V2_FIELDS),
    }
    schema.update(overrides)
    return schema


def _legacy_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "media_id": "media:sha1:" + "a" * 40,
        "entity_id": "3003",
        "entity_name": "Matilda",
        "parent_id": "char:3003/voice",
        "child_id": "char:3003/voice:1300301",
        "asset_type": "image",
        "mime": "image/webp",
        "filename": "portrait.webp",
        "title": "Portrait",
        "source_url": "https://source.example/portrait.webp",
        "url": "https://cdn.example/portrait.webp",
        "object_key": "reverse1999/image/aa/portrait.webp",
        "is_available": True,
        "is_common": False,
        "attach_policy": "auto",
        "search_text": "Matilda portrait",
        "content_hash": "c" * 64,
        "panel_group": "",
        "sort_order": 4,
        "duration_ms": 0,
        "quality_flags": ["verified"],
        "local_relpath": "assets/files/portrait.webp",
        "sha1": "a" * 40,
    }
    row.update(overrides)
    return row


def _binding(status: BindingStatus = BindingStatus.EXACT, **overrides: object) -> BindingRecord:
    source = VoiceSourceRow(
        event_name="WakeUp",
        language="en",
        source_id="source:voice:1",
        entity_id="char:3003",
        parent_id="char:3003/voice",
        child_id="char:3003/voice:1300301",
        transcript="Wake up.",
    )
    matches = ()
    if status is not BindingStatus.SHORTFALL:
        matches = (
            ResourceRow(
                filename="En_WakeUp.mp3",
                language="en",
                sha1="b" * 40,
                sha256="c" * 64,
                resource_id="resource:voice:1",
                source_url="https://source.example/En_WakeUp.mp3",
                title="Wake up",
                mime="audio/mpeg",
                local_relpath="assets/files/b/En_WakeUp.mp3",
                object_key="reverse1999/voice/bb/" + "b" * 40 + ".mp3",
            ),
        )
    record = BindingRecord.from_match(source, "En_WakeUp.mp3", matches, status)
    return replace(record, **overrides)


def test_v2_schema_has_exact_fields_and_internal_visibility():
    assert tuple(MEDIA_ASSET_V2_FIELDS) == LEGACY_FIELDS + V2_FIELDS
    assert set(INTERNAL_MEDIA_ASSET_V2_FIELDS) == {
        "local_relpath",
        "sha1",
        "source_sha1",
        "content_sha256",
        "binding_key",
        "quality_flags",
        "object_key",
        "source_url",
    }


def test_binding_inventory_contains_all_statuses():
    rows = tuple(
        build_binding_inventory(
            (
                _binding(BindingStatus.EXACT),
                _binding(
                    BindingStatus.SHORTFALL,
                    source_id="source:shortfall",
                    quality_flags=("missing_exact_resource",),
                ),
                _binding(
                    BindingStatus.QUARANTINED,
                    source_id="source:quarantined",
                    quality_flags=("cross_child_sha",),
                ),
                _binding(
                    BindingStatus.FATAL,
                    source_id="source:fatal",
                    quality_flags=("duplicate_eventname_sha",),
                ),
            )
        )
    )

    assert [row["binding_status"] for row in rows] == [
        "exact",
        "shortfall",
        "quarantined",
        "fatal",
    ]
    assert all(row["schema_version"] == "evb.binding-inventory/v1" for row in rows)
    assert all(row["source"] and row["matches"] for row in rows if row["binding_status"] != "shortfall")
    assert all("diagnostic_classification" in row for row in rows)
    assert [row["diagnostic_classification"]["root_causes"] for row in rows] == [
        [],
        ["missing_exact_resource"],
        ["cross_child_sha"],
        ["duplicate_eventname_sha"],
    ]


def test_runtime_projection_contains_exact_voice_and_not_applicable_nonvoice_only():
    projection = tuple(
        build_runtime_media_projection(
            [_legacy_row()],
            (
                _binding(BindingStatus.EXACT),
                _binding(BindingStatus.SHORTFALL, source_id="source:shortfall"),
                _binding(BindingStatus.QUARANTINED, source_id="source:quarantined"),
                _binding(BindingStatus.FATAL, source_id="source:fatal"),
            ),
            _directory({"char:3003": ("3003", "Matilda")}),
            PUBLIC_BASE_URL,
            BUCKET_NAME,
        )
    )

    assert [row["binding_status"] for row in projection] == ["not_applicable", "exact"]
    assert projection[0]["asset_type"] == "image"
    assert projection[1]["media_id"] == "media:sha1:" + "b" * 40
    assert projection[1]["binding_key"] == "char:3003/voice:1300301|en|En_WakeUp.mp3"


def test_legacy_adapter_maps_every_named_v1_field():
    legacy = _legacy_row()

    adapted = adapt_legacy_media_row(legacy)

    assert {field: adapted[field] for field in LEGACY_FIELDS} == legacy
    assert adapted["event_name"] is None
    assert adapted["language"] is None
    assert adapted["source_sha1"] == legacy["sha1"]
    assert adapted["content_sha256"] is None
    assert adapted["binding_status"] == "not_applicable"
    assert adapted["artifact_schema_version"] == "evb.media-asset/v1_legacy"
    assert adapted["binding_key"] is None


def test_legacy_adapter_preserves_bootstrap_voice_without_exact_binding():
    legacy = _legacy_row(
        asset_type="voice",
        mime="audio/mpeg",
        filename="legacy.mp3",
        attach_policy="on_intent",
    )

    adapted = adapt_legacy_media_row(legacy)

    assert {field: adapted[field] for field in LEGACY_FIELDS} == legacy
    assert adapted["binding_status"] == "not_applicable"
    assert adapted["artifact_schema_version"] == "evb.media-asset/v1_legacy"
    assert adapted["event_name"] is None
    assert adapted["binding_key"] is None


def test_nonvoice_projection_is_canonically_equivalent():
    legacy_rows = [_legacy_row(), _legacy_row(media_id="media:sha1:" + "d" * 40, sha1="d" * 40)]

    adapted = [adapt_legacy_media_row(row) for row in reversed(legacy_rows)]

    assert canonical_nonvoice_projection_sha256(legacy_rows) == canonical_nonvoice_projection_sha256(adapted)


def test_media_ids_remain_full_sha1():
    row = next(
        build_runtime_media_projection(
            (),
            (_binding(BindingStatus.EXACT),),
            _directory({"char:3003": ("3003", "Matilda")}),
            PUBLIC_BASE_URL,
            BUCKET_NAME,
        )
    )

    assert row["media_id"] == "media:sha1:" + "b" * 40
    assert row["sha1"] == "b" * 40


@pytest.mark.parametrize(
    "row",
    [
        _legacy_row(media_id="media:sha1:" + "a" * 39),
        _legacy_row(sha1="a" * 39),
    ],
)
def test_legacy_adapter_rejects_invalid_rows(row):
    with pytest.raises(ValueError):
        adapt_legacy_media_row(row)


def test_runtime_projection_rejects_missing_or_unsafe_exact_voice_evidence():
    unsafe = replace(_binding(), source_sha1=("b" * 39,))
    missing = replace(_binding(), matches=(), source_sha1=(), content_sha256=())

    with pytest.raises(ValueError):
        tuple(
            build_runtime_media_projection(
                (),
                (unsafe,),
                _directory({"char:3003": ("3003", "Matilda")}),
                PUBLIC_BASE_URL,
                BUCKET_NAME,
            )
        )
    with pytest.raises(ValueError):
        tuple(
            build_runtime_media_projection(
                (),
                (missing,),
                _directory({"char:3003": ("3003", "Matilda")}),
                PUBLIC_BASE_URL,
                BUCKET_NAME,
            )
        )


def test_runtime_projection_rejects_legacy_voice_input():
    with pytest.raises(ValueError, match="nonvoice_rows"):
        tuple(
            build_runtime_media_projection(
                (_legacy_row(asset_type="voice"),),
                (),
                _directory(),
                PUBLIC_BASE_URL,
                BUCKET_NAME,
            )
        )


def test_runtime_projection_builds_escaped_public_url_and_preserves_source_url():
    binding = _binding()
    resource = replace(
        binding.matches[0],
        source_url="https://huiji.example.test/source voice.mp3",
        object_key="reverse1999/voice/bb/Voice #1.mp3",
    )
    binding = replace(
        binding,
        matches=(resource,),
        object_key=(resource.object_key,),
    )

    voice = next(
        build_runtime_media_projection(
            (),
            (binding,),
            _directory({"char:3003": ("3003", "Matilda")}),
            "https://media.example.test/public root/",
            "voice-bucket",
        )
    )

    assert voice["source_url"] == resource.source_url
    assert voice["url"] == (
        "https://media.example.test/public%20root/voice-bucket/"
        "reverse1999/voice/bb/Voice%20%231.mp3"
    )


@pytest.mark.parametrize(
    "public_base_url",
    (
        "file:///tmp/media",
        "ftp://media.example.test",
        "C:\\media",
        "https://media.example.test/path?x=1",
        "https://.",
        "https://media.example.test:not-a-port",
        "https://media.example.test:70000",
        "https://bad..label.example",
        "https://user:password@media.example.test",
        "https://media.example.test/#fragment",
        "https://media.example.test/\x01control",
    ),
)
def test_runtime_projection_rejects_unsafe_public_base(public_base_url):
    with pytest.raises(ValueError, match="public_base_url"):
        tuple(
            build_runtime_media_projection(
                (),
                (_binding(),),
                _directory({"char:3003": ("3003", "Matilda")}),
                public_base_url,
                BUCKET_NAME,
            )
        )


def test_entity_name_directory_uses_canonical_parents_and_retains_conflicts(tmp_path):
    canonical = {
        "parent_id": "char:3003",
        "entity_id": "3003",
        "entity_name": "Matilda",
        "section_kind": "entity",
    }
    noncanonical_section = {
        "parent_id": "char:3003/profile",
        "entity_id": "3003",
        "entity_name": "Not authoritative",
        "section_kind": "profile",
    }

    directory = build_entity_name_directory(
        (
            noncanonical_section,
            canonical,
            {**canonical, "entity_name": "Conflicting name"},
        )
    )

    assert isinstance(directory, EntityNameDirectory)
    assert dict(directory.entries) == {}
    assert dict(directory.conflicts) == {
        "char:3003": (("3003", "Conflicting name"), ("3003", "Matilda"))
    }
    exclusions = build_entity_name_exclusions((_binding(),), directory)
    assert exclusions[0].cause == "entity_name_exclusion:conflicting_canonical_names"
    assert tuple(
        build_runtime_media_projection(
            (), (_binding(),), directory, PUBLIC_BASE_URL, BUCKET_NAME
        )
    ) == ()

    paths = evb_build_paths(tmp_path / "isolated", "evb-artifact-test")
    write_media_artifacts(
        paths,
        MediaArtifacts(
            binding_rows=(_binding(),),
            runtime_rows=(),
            nonvoice_rows=(),
            schema=_schema(),
            manifest_inputs={"baseline_sha256": "a" * 64},
            entity_name_exclusions=exclusions,
        ),
    )
    inventory = list(iter_jsonl(paths.binding_inventory))
    assert inventory[0]["diagnostic_classification"]["exclusion_causes"] == [
        "entity_name_exclusion:conflicting_canonical_names"
    ]


def test_runtime_projection_excludes_exact_binding_without_authoritative_entity_name():
    blank_directory = build_entity_name_directory(
        (
            {
                "parent_id": "char:3003",
                "entity_id": "3003",
                "entity_name": "  ",
                "section_kind": "entity",
            },
        )
    )

    assert tuple(
        build_runtime_media_projection(
            (), (_binding(),), _directory(), PUBLIC_BASE_URL, BUCKET_NAME
        )
    ) == ()
    assert tuple(
        build_runtime_media_projection(
            (), (_binding(),), blank_directory, PUBLIC_BASE_URL, BUCKET_NAME
        )
    ) == ()


def test_runtime_projection_uses_canonical_entity_identity():
    projection = tuple(
        build_runtime_media_projection(
            (_legacy_row(entity_id="legacy-wrong", entity_name="Legacy attachment"),),
            (_binding(),),
            _directory({"char:3003": ("3003", "Canonical Matilda")}),
            PUBLIC_BASE_URL,
            BUCKET_NAME,
        )
    )

    voice = next(row for row in projection if row["asset_type"] == "voice")
    assert voice["entity_id"] == "3003"
    assert voice["entity_name"] == "Canonical Matilda"


def test_write_media_artifacts_rejects_non_consumable_runtime_rows(tmp_path):
    paths = evb_build_paths(tmp_path / "isolated", "evb-artifact-test")
    artifacts = MediaArtifacts(
        binding_rows=(_binding(BindingStatus.SHORTFALL),),
        runtime_rows=(_legacy_row(asset_type="voice", binding_status="shortfall"),),
        nonvoice_rows=(),
        schema=_schema(),
        manifest_inputs={"baseline_sha256": "a" * 64},
    )

    with pytest.raises(ValueError, match="non-consumable"):
        write_media_artifacts(paths, artifacts)
    assert not paths.build_root.exists()


def test_write_media_artifacts_is_deterministic_and_records_status_counts(tmp_path):
    paths = evb_build_paths(tmp_path / "isolated", "evb-artifact-test")
    runtime_rows = tuple(
        build_runtime_media_projection(
            [_legacy_row()],
            (_binding(),),
            _directory({"char:3003": ("3003", "Matilda")}),
            PUBLIC_BASE_URL,
            BUCKET_NAME,
        )
    )
    artifacts = MediaArtifacts(
        binding_rows=(_binding(),),
        runtime_rows=runtime_rows,
        nonvoice_rows=(_legacy_row(),),
        schema=_schema(),
        manifest_inputs={
            "baseline_sha256": "a" * 64,
            "build_version": "evb-artifact-test",
            "public_base_url": PUBLIC_BASE_URL,
            "bucket_name": BUCKET_NAME,
        },
    )

    manifest = write_media_artifacts(paths, artifacts)

    assert isinstance(manifest, ArtifactManifest)
    assert manifest.runtime_status_counts == {"exact": 1, "not_applicable": 1}
    assert manifest.runtime_status_counts.get("shortfall", 0) == 0
    assert [row["media_id"] for row in iter_jsonl(paths.media_assets_v2)] == sorted(
        row["media_id"] for row in runtime_rows
    )
    assert json.loads(paths.media_manifest_v2.read_text(encoding="utf-8"))["file_sha256"] == manifest.file_sha256


def test_write_media_artifacts_rejects_duplicate_schema_fields(tmp_path):
    paths = evb_build_paths(tmp_path / "isolated", "evb-artifact-test")
    artifacts = MediaArtifacts(
        binding_rows=(),
        runtime_rows=(),
        nonvoice_rows=(),
        schema=_schema(fields=[*MEDIA_ASSET_V2_FIELDS, MEDIA_ASSET_V2_FIELDS[-1]]),
        manifest_inputs={"baseline_sha256": "a" * 64},
    )

    with pytest.raises(ValueError, match="duplicate"):
        write_media_artifacts(paths, artifacts)
    assert not paths.build_root.exists()


def test_write_media_artifacts_preserves_reused_nonvoice_id_across_associations(tmp_path):
    paths = evb_build_paths(tmp_path / "isolated", "evb-artifact-test")
    first = adapt_legacy_media_row(_legacy_row())
    second = {
        **first,
        "parent_id": "char:other/profile",
        "child_id": "char:other/profile:0",
    }
    artifacts = MediaArtifacts(
        binding_rows=(),
        runtime_rows=(first, second),
        nonvoice_rows=(_legacy_row(), {**_legacy_row(), **second}),
        schema=_schema(),
        manifest_inputs={"baseline_sha256": "a" * 64},
    )

    write_media_artifacts(paths, artifacts)

    rows = list(iter_jsonl(paths.media_assets_v2))
    assert len(rows) == 2
    assert rows[0]["media_id"] == rows[1]["media_id"]
    assert {(row["parent_id"], row["child_id"]) for row in rows} == {
        (first["parent_id"], first["child_id"]),
        (second["parent_id"], second["child_id"]),
    }


def test_write_media_artifacts_rejects_duplicate_exact_voice_media_id_globally(tmp_path):
    paths = evb_build_paths(tmp_path / "isolated", "evb-artifact-test")
    voice = next(
        build_runtime_media_projection(
            (),
            (_binding(),),
            _directory({"char:3003": ("3003", "Matilda")}),
            PUBLIC_BASE_URL,
            BUCKET_NAME,
        )
    )
    duplicate_voice = {
        **voice,
        "parent_id": "char:other/voice",
        "child_id": "char:other/voice:1",
        "binding_key": "char:other/voice:1|en|En_WakeUp.mp3",
    }
    artifacts = MediaArtifacts(
        binding_rows=(),
        runtime_rows=(voice, duplicate_voice),
        nonvoice_rows=(),
        schema=_schema(),
        manifest_inputs={
            "baseline_sha256": "a" * 64,
            "public_base_url": PUBLIC_BASE_URL,
            "bucket_name": BUCKET_NAME,
        },
    )

    with pytest.raises(ValueError, match="duplicate exact voice media_id"):
        write_media_artifacts(paths, artifacts)
    assert not paths.build_root.exists()


def test_write_media_artifacts_rejects_exact_duplicate_association_before_write(tmp_path):
    paths = evb_build_paths(tmp_path / "isolated", "evb-artifact-test")
    row = adapt_legacy_media_row(_legacy_row())
    artifacts = MediaArtifacts(
        binding_rows=(),
        runtime_rows=(row, dict(row)),
        nonvoice_rows=(_legacy_row(), _legacy_row()),
        schema=_schema(),
        manifest_inputs={"baseline_sha256": "a" * 64},
    )

    with pytest.raises(ValueError, match="duplicate runtime association"):
        write_media_artifacts(paths, artifacts)
    assert not paths.build_root.exists()


@pytest.mark.parametrize(
    "schema",
    (
        _schema(schema_version="evb.media-assets/v1"),
        _schema(internal_fields=list(INTERNAL_MEDIA_ASSET_V2_FIELDS[:-1])),
        _schema(internal_fields=[*INTERNAL_MEDIA_ASSET_V2_FIELDS, "extra"]),
    ),
)
def test_write_media_artifacts_rejects_schema_contract_drift_before_write(tmp_path, schema):
    paths = evb_build_paths(tmp_path / "isolated", "evb-artifact-test")
    artifacts = MediaArtifacts(
        binding_rows=(),
        runtime_rows=(),
        nonvoice_rows=(),
        schema=schema,
        manifest_inputs={"baseline_sha256": "a" * 64},
    )

    with pytest.raises(ValueError):
        write_media_artifacts(paths, artifacts)
    assert not paths.build_root.exists()


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("artifact_schema_version", "evb.media-asset/v1"),
        ("binding_key", ""),
        ("object_key", "../voice.mp3"),
        ("local_relpath", "../voice.mp3"),
        ("source_sha1", "d" * 40),
        ("content_hash", "d" * 64),
        ("url", "https://source.example/En_WakeUp.mp3"),
        ("url", "https://media.example.test/assets/fixture-bucket/wrong.mp3"),
    ),
)
def test_write_media_artifacts_rejects_invalid_exact_voice_projection_before_write(
    tmp_path, field, value
):
    paths = evb_build_paths(tmp_path / "isolated", "evb-artifact-test")
    voice = next(
        build_runtime_media_projection(
            (),
            (_binding(),),
            _directory({"char:3003": ("3003", "Matilda")}),
            PUBLIC_BASE_URL,
            BUCKET_NAME,
        )
    )
    artifacts = MediaArtifacts(
        binding_rows=(_binding(),),
        runtime_rows=({**voice, field: value},),
        nonvoice_rows=(),
        schema=_schema(),
        manifest_inputs={
            "baseline_sha256": "a" * 64,
            "public_base_url": PUBLIC_BASE_URL,
            "bucket_name": BUCKET_NAME,
        },
    )

    with pytest.raises(ValueError):
        write_media_artifacts(paths, artifacts)
    assert not paths.build_root.exists()


def test_writer_rejects_suffix_equivalent_voice_url_from_unpinned_authority_before_write(
    tmp_path,
):
    paths = evb_build_paths(tmp_path / "isolated", "evb-artifact-test")
    voice = next(
        build_runtime_media_projection(
            (),
            (_binding(),),
            _directory({"char:3003": ("3003", "Matilda")}),
            PUBLIC_BASE_URL,
            BUCKET_NAME,
        )
    )
    attacker_url = f"https://attacker.example/other-bucket/{voice['object_key']}"
    artifacts = MediaArtifacts(
        binding_rows=(_binding(),),
        runtime_rows=({**voice, "url": attacker_url},),
        nonvoice_rows=(),
        schema=_schema(),
        manifest_inputs={
            "baseline_sha256": "a" * 64,
            "public_base_url": PUBLIC_BASE_URL,
            "bucket_name": BUCKET_NAME,
        },
    )

    with pytest.raises(ValueError, match="public URL authority"):
        write_media_artifacts(paths, artifacts)
    assert not paths.build_root.exists()


@pytest.mark.parametrize("missing_field", ("public_base_url", "bucket_name"))
def test_writer_rejects_exact_voice_without_pinned_url_authority_before_write(
    tmp_path, missing_field
):
    paths = evb_build_paths(tmp_path / "isolated", "evb-artifact-test")
    voice = next(
        build_runtime_media_projection(
            (),
            (_binding(),),
            _directory({"char:3003": ("3003", "Matilda")}),
            PUBLIC_BASE_URL,
            BUCKET_NAME,
        )
    )
    manifest_inputs = {
        "baseline_sha256": "a" * 64,
        "public_base_url": PUBLIC_BASE_URL,
        "bucket_name": BUCKET_NAME,
    }
    del manifest_inputs[missing_field]
    artifacts = MediaArtifacts(
        binding_rows=(_binding(),),
        runtime_rows=(voice,),
        nonvoice_rows=(),
        schema=_schema(),
        manifest_inputs=manifest_inputs,
    )

    with pytest.raises(ValueError, match=missing_field):
        write_media_artifacts(paths, artifacts)
    assert not paths.build_root.exists()


def test_writer_nonvoice_only_does_not_require_voice_url_authority(tmp_path):
    paths = evb_build_paths(tmp_path / "isolated", "evb-artifact-test")
    source = _legacy_row()
    artifacts = MediaArtifacts(
        binding_rows=(),
        runtime_rows=(adapt_legacy_media_row(source),),
        nonvoice_rows=(source,),
        schema=_schema(),
        manifest_inputs={"baseline_sha256": "a" * 64},
    )

    write_media_artifacts(paths, artifacts)

    assert paths.media_assets_v2.is_file()


def test_write_media_artifacts_rejects_nonvoice_projection_multiset_drift(tmp_path):
    paths = evb_build_paths(tmp_path / "isolated", "evb-artifact-test")
    source = _legacy_row()
    adapted = adapt_legacy_media_row(source)
    extra = {**adapted, "parent_id": "char:extra/profile", "child_id": "char:extra/profile:0"}
    artifacts = MediaArtifacts(
        binding_rows=(),
        runtime_rows=(adapted, extra),
        nonvoice_rows=(source,),
        schema=_schema(),
        manifest_inputs={"baseline_sha256": "a" * 64},
    )

    with pytest.raises(ValueError, match="nonvoice projection"):
        write_media_artifacts(paths, artifacts)
    assert not paths.build_root.exists()


def test_duplicate_child_ids_fail_before_build_root_creation(tmp_path):
    paths = evb_build_paths(tmp_path / "isolated", "evb-artifact-test")
    child = {
        "child_id": "child:duplicate",
        "parent_id": "parent:1",
        "text": "Text",
        "search_text": "Search",
    }
    artifacts = MediaArtifacts(
        binding_rows=(),
        runtime_rows=(),
        nonvoice_rows=(),
        schema=_schema(),
        manifest_inputs={"baseline_sha256": "a" * 64},
        child_rows=(child, dict(child)),
    )

    with pytest.raises(ValueError, match="duplicate child_id"):
        write_media_artifacts(paths, artifacts)
    assert not paths.build_root.exists()
