from __future__ import annotations

import hashlib
import inspect
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from src.huiji_rag import builder as builder_module
from src.huiji_rag import minio_strict
from src.huiji_rag.builder import EvbBuilder, strict_object_requests_from_build_manifest
from src.huiji_rag.minio_strict import InventoryObject, ObjectInventory
from src.huiji_rag.io import evb_build_paths
from src.huiji_rag.models import BuildRequest


def _write_json(path: Path, payload: dict[str, object]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in rows),
        encoding="utf-8",
    )
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _v3_binding_id(row: dict[str, object]) -> str:
    identity = [
        "evb.media-binding/v1",
        row["owner_entity_id"],
        row["owner_page_id"],
        row["parent_id"],
        row["child_id"],
        row["section"],
        row["media_role"],
        row.get("variant", ""),
        row.get("skin_id", ""),
        row.get("event_name", ""),
        row.get("language", ""),
        row["source_binding_token"],
        row["resource_id"],
    ]
    encoded = json.dumps(identity, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return "binding:sha256:" + hashlib.sha256(encoded).hexdigest()


def _v3_runtime_row(
    *,
    body: bytes,
    filename: str,
    asset_type: str,
    media_role: str,
    binding_status: str,
    mime: str,
    child_id: str,
    source_binding_token: str,
) -> dict[str, object]:
    sha1 = hashlib.sha1(body).hexdigest()
    sha256 = hashlib.sha256(body).hexdigest()
    suffix = Path(filename).suffix.lower()
    row: dict[str, object] = {
        "artifact_schema_version": "evb.media-asset/v3",
        "resource_id": f"resource:sha256:{sha256}",
        "media_id": f"media:sha1:{sha1}",
        "owner_entity_id": "character:fixture",
        "owner_page_id": "char:fixture",
        "parent_id": "char:fixture/voice" if asset_type == "voice" else "char:fixture/skills",
        "child_id": child_id,
        "section": "voice" if asset_type == "voice" else "skills",
        "asset_type": asset_type,
        "media_role": media_role,
        "variant": "",
        "skin_id": "",
        "event_name": "fixture_event" if asset_type == "voice" else "",
        "language": "en" if asset_type == "voice" else "",
        "source_binding_token": source_binding_token,
        "mime": mime,
        "filename": filename,
        "object_key": f"reverse1999/{asset_type}/{sha1[:2]}/{sha1}{suffix}",
        "is_available": False,
        "sha1": sha1,
        "source_sha1": sha1,
        "content_sha256": sha256,
        "size": len(body),
        "binding_status": binding_status,
    }
    row["binding_id"] = _v3_binding_id(row)
    return row


def _write_v3_candidate(tmp_path: Path) -> tuple[Path, Path, ObjectInventory, list[dict[str, object]]]:
    raw_root = tmp_path / "raw"
    voice = b"shared voice bytes"
    skill = b"skill image bytes"
    runtime_rows = [
        _v3_runtime_row(
            body=voice,
            filename="voice.mp3",
            asset_type="voice",
            media_role="voice",
            binding_status="exact",
            mime="audio/mpeg",
            child_id="char:fixture/voice/event-a",
            source_binding_token="voice:event-a:en",
        ),
        _v3_runtime_row(
            body=voice,
            filename="voice.mp3",
            asset_type="voice",
            media_role="voice",
            binding_status="exact",
            mime="audio/mpeg",
            child_id="char:fixture/voice/event-b",
            source_binding_token="voice:event-b:en",
        ),
        _v3_runtime_row(
            body=skill,
            filename="skill.png",
            asset_type="skill",
            media_role="skill",
            binding_status="not_applicable",
            mime="image/png",
            child_id="char:fixture/skills/skill-a",
            source_binding_token="skill:a",
        ),
    ]
    binding_rows: list[dict[str, object]] = []
    for index, row in enumerate(runtime_rows):
        if row["asset_type"] == "voice":
            local_relpath = f"assets/{'a' if index == 0 else 'z'}-voice.mp3"
            (raw_root / local_relpath).parent.mkdir(parents=True, exist_ok=True)
            (raw_root / local_relpath).write_bytes(voice)
        else:
            local_relpath = "assets/skill.png"
            (raw_root / local_relpath).write_bytes(skill)
        binding_rows.append(
            {
                "schema_version": "huiji.media-binding-inventory/v3",
                "binding_id": row["binding_id"],
                "resource_id": row["resource_id"],
                "owner_entity_id": row["owner_entity_id"],
                "owner_page_id": row["owner_page_id"],
                "parent_id": row["parent_id"],
                "child_id": row["child_id"],
                "media_role": row["media_role"],
                "source_binding_token": row["source_binding_token"],
                "object_key": row["object_key"],
                "sha1": row["sha1"],
                "content_sha256": row["content_sha256"],
                "size": row["size"],
                "local_relpath": local_relpath,
            }
        )

    build_root = tmp_path / "candidate"
    runtime_path = build_root / "runtime" / "media_assets.v3.jsonl"
    binding_path = build_root / "diagnostic" / "binding_inventory.v3.jsonl"
    runtime_sha = _write_jsonl(runtime_path, runtime_rows)
    binding_sha = _write_jsonl(binding_path, binding_rows)
    artifacts = [
        {
            "relative_path": "runtime/media_assets.v3.jsonl",
            "schema_version": "evb.media-asset/v3",
            "sha256": runtime_sha,
            "size": runtime_path.stat().st_size,
            "row_count": len(runtime_rows),
        },
        {
            "relative_path": "diagnostic/binding_inventory.v3.jsonl",
            "schema_version": "huiji.media-binding-inventory/v3",
            "sha256": binding_sha,
            "size": binding_path.stat().st_size,
            "row_count": len(binding_rows),
        },
    ]
    unique_missing = sorted({str(row["object_key"]) for row in runtime_rows})
    build_manifest = build_root / "build_manifest.json"
    _write_json(
        build_manifest,
        {
            "schema_version": "huiji.corpus-build/v2",
            "artifact_schema_version": "evb.media-asset/v3",
            "artifacts": artifacts,
            "blockers": [
                f"media_unavailable:{len(runtime_rows)}",
                *(f"minio_object_missing:{key}" for key in unique_missing),
            ],
        },
    )
    orphan = InventoryObject(
        object_key="reverse1999/image/aa/" + "a" * 40 + ".webp",
        version_id=None,
        etag="orphan-etag",
        sha1="a" * 40,
        sha256="b" * 64,
        size=1,
        application_operation_id="fixture-operation",
    )
    inventory = ObjectInventory.create(
        "reverse1999-assets",
        "reverse1999",
        (orphan,),
        bucket_policy_summary="absent",
    )
    return build_manifest, raw_root, inventory, runtime_rows


def _repin_v3_artifact(build_manifest: Path, relative_path: str, artifact: Path) -> None:
    manifest = json.loads(build_manifest.read_text(encoding="utf-8"))
    entry = next(
        item for item in manifest["artifacts"] if item["relative_path"] == relative_path
    )
    entry["sha256"] = hashlib.sha256(artifact.read_bytes()).hexdigest()
    entry["size"] = artifact.stat().st_size
    entry["row_count"] = len(artifact.read_text(encoding="utf-8").splitlines())
    _write_json(build_manifest, manifest)


def _request(
    tmp_path: Path,
    *,
    build_version: str = "evb-gate",
    include_dev_inventory: bool = True,
    projection_sha256: str | None = "a" * 64,
) -> BuildRequest:
    baseline = tmp_path / "baseline.v1.json"
    baseline_sha256 = _write_json(
        baseline,
        {"schema_version": "evb.baseline/v1", "source_inventory_sha256": "fixture-source"},
    )
    sidecar = tmp_path / "bundle" / "source_inventory.v1.json"
    sidecar_sha256 = _write_json(sidecar, {"schema_version": "evb.fixture/v1", "name": "source"})
    sidecars = [{"path": "source_inventory.v1.json", "sha256": sidecar_sha256}]
    if include_dev_inventory:
        inventory = {"schema_version": "evb.fixture/v1", "name": "dev_inventory"}
        if projection_sha256 is not None:
            inventory["canonical_non_media_projection_sha256"] = projection_sha256
        inventory_path = tmp_path / "bundle" / "dev_inventory.v1.json"
        sidecars.append(
            {"path": "dev_inventory.v1.json", "sha256": _write_json(inventory_path, inventory)}
        )
    bundle = tmp_path / "bundle" / "preflight_bundle_manifest.v1.json"
    bundle_sha256 = _write_json(
        bundle,
        {
            "schema_version": "evb.preflight-bundle/v1",
            "baseline_sha256": baseline_sha256,
            "sidecars": sidecars,
        },
    )
    return BuildRequest(
        build_version=build_version,
        baseline_path=baseline,
        expected_baseline_sha256=baseline_sha256,
        preflight_bundle_path=bundle,
        expected_preflight_bundle_sha256=bundle_sha256,
        output_root=tmp_path / "output",
        dry_run=True,
    )


def test_evb_build_paths_are_contained_and_reject_dev(tmp_path):
    paths = evb_build_paths(tmp_path / "processed", "evb-gate")

    assert paths.build_root == (tmp_path / "processed" / "evb-gate").resolve()
    for path in paths.all_paths():
        assert path.is_relative_to(paths.build_root)

    with pytest.raises(ValueError):
        evb_build_paths(tmp_path / "processed", "dev")
    with pytest.raises(ValueError):
        evb_build_paths(tmp_path / "processed", "../escape")


def test_evb_build_paths_reject_live_dev_root_and_descendants():
    repository_root = Path(__file__).parents[1]
    live_dev_root = repository_root / "data" / "processed" / "huiji" / "dev"

    with pytest.raises(ValueError, match="live dev"):
        evb_build_paths(live_dev_root, "evb-gate")
    with pytest.raises(ValueError, match="live dev"):
        evb_build_paths(live_dev_root / "nested", "evb-gate")


def test_builder_never_imports_pyc_or_mutation_clients(tmp_path):
    source = inspect.getsource(EvbBuilder).lower()
    assert "pymilvus" not in source
    assert "minio" not in source
    assert ".pyc" not in source

    request = _request(tmp_path, build_version="dev")
    with pytest.raises(ValueError):
        EvbBuilder().build_offline(request)
    assert not request.output_root.exists()


def test_offline_build_rejects_stale_hash_and_sidecar_mismatch_before_write(tmp_path):
    stale = _request(tmp_path)
    with pytest.raises(ValueError, match="baseline SHA-256"):
        EvbBuilder().build_offline(
            BuildRequest(**{**stale.__dict__, "expected_baseline_sha256": "0" * 64})
        )
    assert not stale.output_root.exists()

    mismatch = _request(tmp_path / "mismatch")
    sidecar = mismatch.preflight_bundle_path.parent / "source_inventory.v1.json"
    sidecar.write_text('{"changed":true}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="sidecar SHA-256"):
        EvbBuilder().build_offline(mismatch)
    assert not mismatch.output_root.exists()


def test_offline_build_rejects_report_root_outside_isolated_build_root(tmp_path):
    request = _request(tmp_path)
    sibling_report_request = BuildRequest(
        **{**request.__dict__, "report_root": request.output_root / "reports"}
    )

    with pytest.raises(ValueError, match="build_root"):
        EvbBuilder().build_offline(sibling_report_request)

    assert not request.output_root.exists()


def test_offline_build_requires_dev_inventory_sidecar(tmp_path):
    request = _request(tmp_path, include_dev_inventory=False)

    with pytest.raises(ValueError, match="dev_inventory.v1.json"):
        EvbBuilder().build_offline(request)


@pytest.mark.parametrize("projection_sha256", [None, "A" * 64])
def test_offline_build_requires_lowercase_dev_projection_hash(tmp_path, projection_sha256):
    request = _request(tmp_path, projection_sha256=projection_sha256)

    with pytest.raises(ValueError, match="canonical projection"):
        EvbBuilder().build_offline(request)


def test_offline_build_writes_only_under_requested_isolated_root(tmp_path):
    request = _request(tmp_path)

    result = EvbBuilder().build_offline(request)

    assert result.build_manifest.is_file()
    assert result.build_manifest.is_relative_to(request.output_root.resolve())
    payload = json.loads(result.build_manifest.read_text(encoding="utf-8"))
    assert payload["baseline_sha256"] == request.expected_baseline_sha256
    assert payload["dry_run"] is True


def test_offline_cli_artifact_fixture_writes_complete_v2_outputs(tmp_path):
    repository = Path(__file__).parents[1]
    baseline = repository / "tests" / "fixtures" / "evb" / "baseline.v1.json"
    bundle = repository / "tests" / "fixtures" / "evb" / "preflight_bundle" / "preflight_bundle_manifest.v1.json"
    output_root = tmp_path / "official-c14"

    completed = subprocess.run(
        [
            sys.executable,
            str(repository / "scripts" / "build_huiji_evb.py"),
            "offline",
            "--build-version",
            "evb-gate",
            "--baseline",
            str(baseline),
            "--expected-baseline-sha256",
            hashlib.sha256(baseline.read_bytes()).hexdigest(),
            "--preflight-bundle",
            str(bundle),
            "--expected-preflight-bundle-sha256",
            hashlib.sha256(bundle.read_bytes()).hexdigest(),
            "--dry-run",
            "--output-root",
            str(output_root),
        ],
        cwd=repository,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    build_root = output_root / "evb-gate"
    expected = {
        "build_manifest.json",
        "build_report.json",
        "parent_blocks.jsonl",
        "child_blocks.jsonl",
        "indexes/child_text_bm25.json",
        "diagnostic/binding_inventory.v1.jsonl",
        "runtime/media_assets.v2.jsonl",
        "runtime/media_assets.v2.schema.json",
        "runtime/media_assets.v2.manifest.json",
    }
    assert {
        path.relative_to(build_root).as_posix()
        for path in build_root.rglob("*")
        if path.is_file()
    } == expected


def test_offline_script_imports_project_from_repository_root():
    script = Path(__file__).parents[1] / "scripts" / "build_huiji_evb.py"

    completed = subprocess.run(
        [sys.executable, str(script), "offline"],
        cwd=Path(__file__).parents[1],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 2
    assert "--build-version" in completed.stderr


def test_strict_requests_reject_source_escape_before_filesystem_metadata_access(
    tmp_path, monkeypatch
):
    build_root = tmp_path / "build"
    runtime = build_root / "runtime" / "media_assets.v2.jsonl"
    outside = tmp_path / "outside.mp3"
    outside.write_bytes(b"voice")
    row = {
        "asset_type": "voice",
        "binding_status": "exact",
        "sha1": hashlib.sha1(b"voice").hexdigest(),
        "content_sha256": hashlib.sha256(b"voice").hexdigest(),
        "object_key": "reverse1999/voice/ef/escape.mp3",
        "local_relpath": "../outside.mp3",
        "mime": "audio/mpeg",
        "filename": "voice.mp3",
    }
    runtime.parent.mkdir(parents=True)
    runtime.write_text(json.dumps(row) + "\n", encoding="utf-8")
    artifact_manifest = build_root / "diagnostic" / "media_assets.v2.manifest.json"
    _write_json(
        artifact_manifest,
        {
            "file_paths": {"media_assets_v2": "runtime/media_assets.v2.jsonl"},
            "file_sha256": {"media_assets_v2": hashlib.sha256(runtime.read_bytes()).hexdigest()},
        },
    )
    build_manifest = build_root / "build_manifest.json"
    _write_json(
        build_manifest,
        {"media_artifact_manifest": "diagnostic/media_assets.v2.manifest.json"},
    )
    outside_stat_calls: list[Path] = []
    original_stat = Path.stat
    resolved_outside = outside.resolve()
    resolved_raw_root = (tmp_path / "raw").resolve()

    def monitored_stat(path: Path, *args, **kwargs):
        absolute = Path(os.path.abspath(path))
        try:
            absolute.relative_to(resolved_raw_root)
        except ValueError:
            if absolute == resolved_outside:
                outside_stat_calls.append(absolute)
        return original_stat(path, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", monitored_stat)

    with pytest.raises(ValueError, match="configured raw root"):
        strict_object_requests_from_build_manifest(
            build_manifest,
            ObjectInventory.create("reverse1999-assets", "reverse1999", ()),
            tmp_path / "raw",
        )
    assert outside_stat_calls == []


def test_v3_strict_resolution_joins_bindings_and_deduplicates_physical_objects(tmp_path):
    build_manifest, raw_root, inventory, runtime_rows = _write_v3_candidate(tmp_path)
    authorities = (
        minio_strict.MediaOperationAuthority(
            "voice", "voice", "exact", "audio/mpeg", ".mp3"
        ),
        minio_strict.MediaOperationAuthority(
            "skill", "skill", "not_applicable", "image/png", ".png"
        ),
    )

    result = builder_module.resolve_strict_object_requests_from_build_manifest(
        build_manifest,
        inventory,
        raw_root,
        allowed_media_authorities=authorities,
    )

    assert result.candidate_unique_object_count == 2
    assert result.missing_binding_count == 3
    assert result.missing_remote_count == 2
    assert result.same_hash_count == 0
    assert result.hash_mismatch_count == 0
    assert result.orphan_remote_count == 1
    assert dict(result.missing_authority_counts) == {"skill/skill": 1, "voice/voice": 1}
    assert len(result.missing_requests) == 2
    voice_request = next(item for item in result.missing_requests if item.asset_type == "voice")
    assert voice_request.local_path == (raw_root / "assets" / "a-voice.mp3").resolve()
    assert {item.object_key for item in result.missing_requests} == {
        str(row["object_key"]) for row in runtime_rows
    }
    expected_key_hash = hashlib.sha256(
        "".join(
            f"{key}\n"
            for key in sorted({str(row["object_key"]) for row in runtime_rows})
        ).encode("utf-8")
    ).hexdigest()
    assert result.ordered_missing_object_keys_sha256 == expected_key_hash


def test_v3_strict_resolution_rejects_cross_binding_physical_identity_conflict(tmp_path):
    build_manifest, raw_root, inventory, _ = _write_v3_candidate(tmp_path)
    binding_path = build_manifest.parent / "diagnostic" / "binding_inventory.v3.jsonl"
    rows = [json.loads(line) for line in binding_path.read_text(encoding="utf-8").splitlines()]
    rows[1]["content_sha256"] = "f" * 64
    binding_sha = _write_jsonl(binding_path, rows)
    manifest = json.loads(build_manifest.read_text(encoding="utf-8"))
    entry = next(
        item
        for item in manifest["artifacts"]
        if item["relative_path"] == "diagnostic/binding_inventory.v3.jsonl"
    )
    entry["sha256"] = binding_sha
    entry["size"] = binding_path.stat().st_size
    _write_json(build_manifest, manifest)

    with pytest.raises(ValueError, match="physical identity"):
        builder_module.resolve_strict_object_requests_from_build_manifest(
            build_manifest,
            inventory,
            raw_root,
            allowed_media_authorities=(
                minio_strict.MediaOperationAuthority(
                    "voice", "voice", "exact", "audio/mpeg", ".mp3"
                ),
                minio_strict.MediaOperationAuthority(
                    "skill", "skill", "not_applicable", "image/png", ".png"
                ),
            ),
        )


def test_v3_strict_resolution_rejects_unapproved_missing_media_authority(tmp_path):
    build_manifest, raw_root, inventory, _ = _write_v3_candidate(tmp_path)

    with pytest.raises(ValueError, match="media authority"):
        builder_module.resolve_strict_object_requests_from_build_manifest(
            build_manifest,
            inventory,
            raw_root,
            allowed_media_authorities=(
                minio_strict.MediaOperationAuthority(
                    "voice", "voice", "exact", "audio/mpeg", ".mp3"
                ),
            ),
        )


def test_v3_strict_resolution_validates_every_local_copy_before_plan(tmp_path):
    build_manifest, raw_root, inventory, _ = _write_v3_candidate(tmp_path)
    (raw_root / "assets" / "z-voice.mp3").write_bytes(b"changed duplicate")

    with pytest.raises(ValueError, match="local media source (size|hash) mismatch"):
        builder_module.resolve_strict_object_requests_from_build_manifest(
            build_manifest,
            inventory,
            raw_root,
            allowed_media_authorities=(
                minio_strict.MediaOperationAuthority(
                    "voice", "voice", "exact", "audio/mpeg", ".mp3"
                ),
                minio_strict.MediaOperationAuthority(
                    "skill", "skill", "not_applicable", "image/png", ".png"
                ),
            ),
        )


def test_v3_strict_resolution_rejects_artifact_hash_drift_before_rows_are_used(tmp_path):
    build_manifest, raw_root, inventory, _ = _write_v3_candidate(tmp_path)
    runtime_path = build_manifest.parent / "runtime" / "media_assets.v3.jsonl"
    runtime_path.write_bytes(runtime_path.read_bytes() + b" ")

    with pytest.raises(ValueError, match="SHA-256"):
        builder_module.resolve_strict_object_requests_from_build_manifest(
            build_manifest,
            inventory,
            raw_root,
            allowed_media_authorities=(
                minio_strict.MediaOperationAuthority(
                    "voice", "voice", "exact", "audio/mpeg", ".mp3"
                ),
            ),
        )


def test_v3_strict_resolution_rejects_binding_set_gap_and_path_escape(tmp_path):
    build_manifest, raw_root, inventory, _ = _write_v3_candidate(tmp_path)
    binding_path = build_manifest.parent / "diagnostic" / "binding_inventory.v3.jsonl"
    rows = [json.loads(line) for line in binding_path.read_text(encoding="utf-8").splitlines()]
    rows[0]["local_relpath"] = "../escape.mp3"
    _write_jsonl(binding_path, rows)
    _repin_v3_artifact(
        build_manifest, "diagnostic/binding_inventory.v3.jsonl", binding_path
    )

    with pytest.raises(ValueError, match="configured raw root"):
        builder_module.resolve_strict_object_requests_from_build_manifest(
            build_manifest,
            inventory,
            raw_root,
            allowed_media_authorities=(
                minio_strict.MediaOperationAuthority(
                    "voice", "voice", "exact", "audio/mpeg", ".mp3"
                ),
                minio_strict.MediaOperationAuthority(
                    "skill", "skill", "not_applicable", "image/png", ".png"
                ),
            ),
        )

    build_manifest, raw_root, inventory, _ = _write_v3_candidate(tmp_path / "gap")
    binding_path = build_manifest.parent / "diagnostic" / "binding_inventory.v3.jsonl"
    rows = [json.loads(line) for line in binding_path.read_text(encoding="utf-8").splitlines()]
    _write_jsonl(binding_path, rows[:-1])
    _repin_v3_artifact(
        build_manifest, "diagnostic/binding_inventory.v3.jsonl", binding_path
    )
    with pytest.raises(ValueError, match="binding_id sets differ"):
        builder_module.resolve_strict_object_requests_from_build_manifest(
            build_manifest,
            inventory,
            raw_root,
            allowed_media_authorities=(
                minio_strict.MediaOperationAuthority(
                    "voice", "voice", "exact", "audio/mpeg", ".mp3"
                ),
                minio_strict.MediaOperationAuthority(
                    "skill", "skill", "not_applicable", "image/png", ".png"
                ),
            ),
        )


def test_v3_strict_resolution_rejects_runtime_quarantine_and_unknown_blocker(tmp_path):
    build_manifest, raw_root, inventory, _ = _write_v3_candidate(tmp_path)
    runtime_path = build_manifest.parent / "runtime" / "media_assets.v3.jsonl"
    rows = [json.loads(line) for line in runtime_path.read_text(encoding="utf-8").splitlines()]
    rows[0]["binding_status"] = "quarantined"
    _write_jsonl(runtime_path, rows)
    _repin_v3_artifact(build_manifest, "runtime/media_assets.v3.jsonl", runtime_path)

    with pytest.raises(ValueError, match="binding status is not upload-safe"):
        builder_module.resolve_strict_object_requests_from_build_manifest(
            build_manifest,
            inventory,
            raw_root,
            allowed_media_authorities=(
                minio_strict.MediaOperationAuthority(
                    "voice", "voice", "exact", "audio/mpeg", ".mp3"
                ),
                minio_strict.MediaOperationAuthority(
                    "skill", "skill", "not_applicable", "image/png", ".png"
                ),
            ),
        )

    build_manifest, raw_root, inventory, _ = _write_v3_candidate(tmp_path / "blocker")
    manifest = json.loads(build_manifest.read_text(encoding="utf-8"))
    manifest["blockers"].append("source_drift:unexpected")
    _write_json(build_manifest, manifest)
    with pytest.raises(ValueError, match="non-MinIO blocker"):
        builder_module.resolve_strict_object_requests_from_build_manifest(
            build_manifest,
            inventory,
            raw_root,
            allowed_media_authorities=(
                minio_strict.MediaOperationAuthority(
                    "voice", "voice", "exact", "audio/mpeg", ".mp3"
                ),
                minio_strict.MediaOperationAuthority(
                    "skill", "skill", "not_applicable", "image/png", ".png"
                ),
            ),
        )
