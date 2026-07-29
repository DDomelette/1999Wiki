from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable

import pytest

from src.huiji_rag.build.contracts import (
    CorpusBuildRequest,
    CorpusCapacityPlanningEvidence,
    canonical_json_bytes,
)
from src.huiji_rag.build.orchestrator import HuijiCorpusBuilder
from src.huiji_rag.build.media_download_plan import MEDIA_SELECTION_POLICY_SHA256
from src.huiji_rag.build.projection import (
    MediaBindingIntent,
    project_crawler_semantics,
    validate_corpus_projection,
)
from src.huiji_rag.minio_strict import ObjectInventory
import src.huiji_rag.build.orchestrator as orchestrator_module


REPO_ROOT = Path(__file__).resolve().parents[1]
SHARED_FIXTURE = REPO_ROOT / "tests/fixtures/contracts/huiji_media_v3"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json_bytes(payload))


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            + "\n"
            for row in rows
        ),
        encoding="utf-8",
        newline="\n",
    )


def _fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    project = tmp_path / "project"
    raw = project / "data/huiji/res1999"
    content = json.dumps(
        {"id": 41, "name": "Sample Item", "description": "Source backed text."},
        ensure_ascii=False,
        separators=(",", ":"),
    )
    data_row = {
        "site": "res1999",
        "pageid": 41,
        "revid": 410,
        "title": "Data:Item/41.json",
        "content": content,
        "content_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
    }
    page_content = "== Overview ==\nSource-backed page text."
    page_content_sha256 = hashlib.sha256(page_content.encode("utf-8")).hexdigest()
    _write_jsonl(
        raw / "pages.jsonl",
        [
            {
                "site": "res1999",
                "pageid": 41,
                "ns": 0,
                "lastrevid": 409,
                "status": "active",
                "seen_at": "snapshot",
                "title": "暴雨",
            }
        ],
    )
    _write_jsonl(
        raw / "wikitext.jsonl",
        [
            {
                "site": "res1999",
                "pageid": 41,
                "ns": 0,
                "revid": 409,
                "title": "暴雨",
                "content": page_content,
                "content_sha256": page_content_sha256,
            }
        ],
    )
    _write_jsonl(raw / "data_pages.jsonl", [data_row])
    _write_jsonl(raw / "resources_manifest.jsonl", [])
    with sqlite3.connect(raw / "crawl_state.sqlite") as connection:
        connection.execute("CREATE TABLE crawl_runs (id INTEGER PRIMARY KEY)")

    recovery_manifest = project / "config/recovery/fixture.json"
    recovery_audit = project / "eval/recovery/audit.json"
    recovery_apply = project / "eval/recovery/apply.json"
    _write_json(
        recovery_manifest,
        {
            "schema_version": "huiji-source-recovery/v1",
            "snapshot_id": "fixture",
            "files": {
                name: {
                    "size": (raw / name).stat().st_size,
                    "sha256": _sha256(raw / name),
                    **(
                        {"rows": 1, "invalid_payload_rows": 0}
                        if name == "data_pages.jsonl"
                        else {}
                    ),
                }
                for name in ("data_pages.jsonl", "crawl_state.sqlite")
            },
            "recover": ["data_pages.jsonl", "crawl_state.sqlite"],
        },
    )
    _write_json(
        recovery_audit,
        {
            "status": "ready",
            "snapshot_id": "fixture",
            "invalid_payload_rows": 0,
        },
    )
    _write_json(
        recovery_apply,
        {
            "status": "completed",
            "snapshot_id": "fixture",
            "files": {
                name: {
                    "status": "already_present",
                    "size": (raw / name).stat().st_size,
                    "sha256": _sha256(raw / name),
                }
                for name in ("data_pages.jsonl", "crawl_state.sqlite")
            },
        },
    )

    projection = project_crawler_semantics([data_row])
    active_root = project / "data/processed/huiji/dev"
    active_files = {
        "parent_blocks.jsonl": [row.to_json() for row in projection.parents],
        "child_blocks.jsonl": [row.block.to_json() for row in projection.children],
        "excluded_entities.jsonl": [],
        "media_assets.jsonl": [],
    }
    for name, rows in active_files.items():
        _write_jsonl(active_root / name, rows)
    _write_json(
        active_root / "indexes/child_text_bm25.json",
        {"records": active_files["child_blocks.jsonl"]},
    )
    _write_json(active_root / "indexes/media_asset_bm25.json", {"records": []})

    file_paths = {
        "parent_blocks.jsonl": active_root / "parent_blocks.jsonl",
        "child_blocks.jsonl": active_root / "child_blocks.jsonl",
        "excluded_entities.jsonl": active_root / "excluded_entities.jsonl",
        "media_assets.jsonl": active_root / "media_assets.jsonl",
        "child_text_bm25.json": active_root / "indexes/child_text_bm25.json",
        "media_asset_bm25.json": active_root / "indexes/media_asset_bm25.json",
    }
    baseline = project / "eval/baseline.json"
    _write_json(
        baseline,
        {
            "schema_version": "huiji.corpus-preservation-baseline/v2",
            "status": "pass",
            "active_artifacts": {
                "files": {
                    name: {
                        "path": path.relative_to(project).as_posix(),
                        "sha256": _sha256(path),
                        "size": path.stat().st_size,
                    }
                    for name, path in file_paths.items()
                }
            },
        },
    )

    fixture_root = project / "tests/fixtures/contracts/huiji_media_v3"
    fixture_root.mkdir(parents=True)
    fixture_names = (
        "media_assets.v3.schema.json",
        "media_assets.v3.jsonl",
        "expected_resources.json",
        "expected_bindings.json",
    )
    for name in fixture_names:
        shutil.copy2(SHARED_FIXTURE / name, fixture_root / name)
    receipt = project / "eval/wiki/compatibility-receipt.v1.json"
    _write_json(
        receipt,
        {
            "schema_version": "huiji.wiki-media-v3-compatibility-receipt/v1",
            "status": "passed",
            "fixtures": [
                {
                    "path": f"tests/fixtures/contracts/huiji_media_v3/{name}",
                    "sha256": _sha256(fixture_root / name),
                }
                for name in fixture_names
            ],
        },
    )

    inventory = project / "eval/minio/inventory.v1.json"
    inventory_payload = ObjectInventory.create(
            "reverse1999-assets",
            "reverse1999",
            (),
            captured_at_utc="2026-07-21T00:00:00Z",
            bucket_policy_summary="absent",
        ).to_json()
    _write_json(inventory, inventory_payload)
    monkeypatch.setattr(
        orchestrator_module,
        "capture_code_fingerprint",
        lambda *_args, **_kwargs: {
            "schema_version": "huiji.builder-code-fingerprint/v1",
            "files": [],
            "code_fingerprint_sha256": "c" * 64,
        },
    )

    def request(version: str, run_name: str) -> CorpusBuildRequest:
        return CorpusBuildRequest(
            build_version=version,
            raw_root=raw,
            processed_root=project / "data/processed/huiji",
            run_dir=project / "eval/runs" / run_name,
            fidelity_baseline_path=baseline,
            expected_fidelity_baseline_sha256=_sha256(baseline),
            wiki_compatibility_receipt_path=receipt,
            expected_wiki_compatibility_receipt_sha256=_sha256(receipt),
            configured_build_version="dev",
            project_root=project,
            minio_inventory_path=inventory,
            expected_minio_inventory_sha256=_sha256(inventory),
            public_base_url="http://127.0.0.1:9002",
            bucket_name="reverse1999-assets",
            object_prefix="reverse1999",
            embedding_provider="test",
            embedding_model="test-model",
            forbidden_collection_names=("active",),
            recovery_manifest_path=recovery_manifest,
            recovery_audit_receipt_path=recovery_audit,
            recovery_apply_receipt_path=recovery_apply,
            capacity_planning=CorpusCapacityPlanningEvidence(
                phase="p0",
                workers=2,
                free_local_bytes=40 * 1024**3,
                known_cloud_free_or_quota_bytes=40 * 1024**3,
                other_storage_growth_bytes=0,
                candidate_artifact_estimate_bytes=0,
                selection_policy_sha256=MEDIA_SELECTION_POLICY_SHA256,
                media_budget_baseline_inventory_sha256=str(
                    inventory_payload["inventory_sha256"]
                ),
            ),
        )

    return project, request


def _wrap(
    monkeypatch: pytest.MonkeyPatch,
    owner: object,
    name: str,
    events: list[str],
    label: str,
) -> None:
    original: Callable[..., Any] = getattr(owner, name)

    def wrapped(*args: Any, **kwargs: Any):
        events.append(label)
        return original(*args, **kwargs)

    monkeypatch.setattr(owner, name, wrapped)


def test_full_builder_runs_fixed_stages_and_two_roots_have_equal_semantic_hashes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _project, request = _fixture(tmp_path, monkeypatch)
    events: list[str] = []
    _wrap(monkeypatch, orchestrator_module, "capture_corpus_source_inventory", events, "source")
    _wrap(monkeypatch, orchestrator_module, "validate_recovery_gate", events, "recovery")
    _wrap(monkeypatch, orchestrator_module, "build_page_revision_join", events, "join")
    _wrap(monkeypatch, orchestrator_module, "project_crawler_semantics", events, "projection")
    _wrap(monkeypatch, orchestrator_module.media_stage, "prepare_voice_resource_rows", events, "voice_resources")
    _wrap(monkeypatch, orchestrator_module.VoiceBindingStage, "run", events, "voice")
    _wrap(monkeypatch, orchestrator_module.media_stage, "assemble_media_v3", events, "media")
    _wrap(monkeypatch, orchestrator_module, "build_media_download_plan", events, "capacity")
    _wrap(monkeypatch, orchestrator_module, "build_fidelity_ledger", events, "fidelity")
    _wrap(monkeypatch, orchestrator_module, "write_candidate_artifacts", events, "artifacts")
    original_read_jsonl = orchestrator_module._read_jsonl

    def reject_source_list_load(path: Path):
        if path.name in {"data_pages.jsonl", "resources_manifest.jsonl"}:
            raise AssertionError("crawler semantic sources must use streaming readers")
        return original_read_jsonl(path)

    monkeypatch.setattr(orchestrator_module, "_read_jsonl", reject_source_list_load)

    first = HuijiCorpusBuilder().build_candidate(request("candidate-a", "run-a"))
    second = HuijiCorpusBuilder().build_candidate(request("candidate-b", "run-b"))

    expected = [
        "recovery",
        "source",
        "join",
        "projection",
        "voice_resources",
        "voice",
        "media",
        "capacity",
        "fidelity",
        "artifacts",
    ]
    assert events == expected * 2
    assert first.state.value == second.state.value == "ready_for_embedding"
    first_receipt = json.loads(
        (Path(first.build_root).parents[3] / "eval/runs/run-a/candidate_result.v1.json").read_text(
            encoding="utf-8"
        )
    )
    second_receipt = json.loads(
        (Path(second.build_root).parents[3] / "eval/runs/run-b/candidate_result.v1.json").read_text(
            encoding="utf-8"
        )
    )
    assert first_receipt["semantic_artifact_sha256"] == second_receipt[
        "semantic_artifact_sha256"
    ]
    assert first.build_root != second.build_root


def test_builder_composes_page_rows_and_source_backed_new_record_links(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _project, request = _fixture(tmp_path, monkeypatch)

    result = HuijiCorpusBuilder().build_candidate(
        request("page-integration", "page-integration-run")
    )

    assert result.state.value == "ready_for_embedding"
    parents = [
        json.loads(line)
        for line in (result.build_root / "parent_blocks.jsonl").read_text(
            encoding="utf-8"
        ).splitlines()
    ]
    children = [
        json.loads(line)
        for line in (result.build_root / "child_blocks.jsonl").read_text(
            encoding="utf-8"
        ).splitlines()
    ]
    assert any(row["category"] == "page" and row["parent_id"] == "page:41" for row in parents)
    page_children = [row for row in children if row["category"] == "page"]
    assert page_children
    assert page_children[0]["source_refs"][0]["source_title"] == "暴雨"
    assert any(row["category"] == "topic" for row in parents)
    assert any(row["category"] == "topic" for row in children)
    ledger = [
        json.loads(line)
        for line in (result.build_root / "diagnostic/fidelity_ledger.v1.jsonl").read_text(
            encoding="utf-8"
        ).splitlines()
    ]
    page_rows = [row for row in ledger if "page:41" in row["candidate_identities"]]
    assert page_rows
    assert {row["classification"] for row in page_rows} == {"new_source_record"}


def test_projection_closure_rejects_unknown_parent_and_duplicate_media_identity() -> None:
    projection = project_crawler_semantics(
        [
            {
                "pageid": 41,
                "revid": 410,
                "title": "Data:Item/41.json",
                "content": '{"id":41,"name":"Sample","description":"Text"}',
                "content_sha256": "a" * 64,
            }
        ]
    )
    child = projection.children[0]
    invalid_child = replace(child, block=replace(child.block, parent_id="missing-parent"))
    with pytest.raises(ValueError, match="unknown parent"):
        validate_corpus_projection(replace(projection, children=(invalid_child,)))

    intent = MediaBindingIntent(
        source_binding_token="duplicate-token",
        owner_entity_id=child.owner_entity_id,
        owner_page_id=child.owner_page_id,
        parent_id=child.block.parent_id,
        child_id=child.block.child_id,
        section=child.block.section_kind,
        media_role="illustration",
        resource_stem="sample",
        title="Sample",
    )
    with pytest.raises(ValueError, match="duplicate media source identities"):
        validate_corpus_projection(
            replace(projection, media_intents=(intent, intent))
        )

    with pytest.raises(ValueError, match="incomplete source ref"):
        validate_corpus_projection(
            replace(
                projection,
                children=(
                    replace(
                        child,
                        block=replace(child.block, source_refs=({"title": "unsafe"},)),
                    ),
                ),
            )
        )

    parent = next(item for item in projection.parents if item.parent_id == child.block.parent_id)
    with pytest.raises(ValueError, match="missing from parent child_ids"):
        validate_corpus_projection(
            replace(
                projection,
                parents=(replace(parent, child_ids=()),),
                children=(child,),
            )
        )

    source_ref = dict(child.block.source_refs[0])
    source_ref.pop("kind", None)
    source_ref.pop("source_kind", None)
    with pytest.raises(ValueError, match="incomplete source ref"):
        validate_corpus_projection(
            replace(
                projection,
                children=(
                    replace(
                        child,
                        block=replace(child.block, source_refs=(source_ref,)),
                    ),
                ),
            )
        )


def _character_aggregate_projection():
    content = json.dumps(
        {
            "id": 3003,
            "name": "Aggregate Character",
            "character_data": [
                {
                    "id": 1,
                    "type": 1,
                    "title": "Profile",
                    "text": "Source-backed profile text.",
                }
            ],
            "character_voice": [
                {
                    "audio": 300301,
                    "name": "Greeting",
                    "eventName": "aggregate_greeting",
                    "content": "Hello.#0",
                }
            ],
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return project_crawler_semantics(
        [
            {
                "pageid": 3003,
                "revid": 30030,
                "title": "Data:Char/3003.json",
                "content": content,
                "content_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
            }
        ]
    )


def test_character_root_aggregate_accepts_declared_descendant_children() -> None:
    projection = _character_aggregate_projection()
    root = next(parent for parent in projection.parents if parent.parent_id == "char:3003")
    descendants = [
        child for child in projection.children if child.block.child_id in root.child_ids
    ]

    assert descendants
    assert all(root.parent_id in child.block.ancestor_ids for child in descendants)
    assert all(child.block.parent_id != root.parent_id for child in descendants)

    validate_corpus_projection(projection)


def test_character_root_aggregate_rejects_undeclared_ancestor_relation() -> None:
    projection = _character_aggregate_projection()
    root = next(parent for parent in projection.parents if parent.parent_id == "char:3003")
    descendant = next(
        child for child in projection.children if child.block.child_id in root.child_ids
    )
    invalid_descendant = replace(
        descendant,
        block=replace(
            descendant.block,
            ancestor_ids=tuple(
                ancestor
                for ancestor in descendant.block.ancestor_ids
                if ancestor != root.parent_id
            ),
        ),
    )

    with pytest.raises(ValueError, match="parent-child closure failed: char:3003"):
        validate_corpus_projection(
            replace(
                projection,
                children=tuple(
                    invalid_descendant if child is descendant else child
                    for child in projection.children
                ),
            )
        )


def test_parent_aggregate_rejects_missing_listed_child() -> None:
    projection = _character_aggregate_projection()
    root = next(parent for parent in projection.parents if parent.parent_id == "char:3003")

    with pytest.raises(ValueError, match="parent-child closure failed: char:3003"):
        validate_corpus_projection(
            replace(
                projection,
                parents=tuple(
                    replace(parent, child_ids=(*parent.child_ids, "char:3003/missing"))
                    if parent is root
                    else parent
                    for parent in projection.parents
                ),
            )
        )


def test_builder_fingerprints_all_thread_c_stages_and_frozen_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _project, request = _fixture(tmp_path, monkeypatch)
    captured_paths: list[Path] = []

    def capture(_root: Path, paths: tuple[Path, ...]) -> dict[str, Any]:
        captured_paths.extend(paths)
        return {
            "schema_version": "huiji.builder-code-fingerprint/v1",
            "files": [],
            "code_fingerprint_sha256": "c" * 64,
        }

    monkeypatch.setattr(orchestrator_module, "capture_code_fingerprint", capture)
    request_value = request("fingerprints", "fingerprints-run")
    first_config = orchestrator_module._config_fingerprint(request_value)
    monkeypatch.setattr(
        orchestrator_module.wikitext_stage,
        "_PARSER_CONFIG_SHA256",
        "0" * 64,
    )
    second_config = orchestrator_module._config_fingerprint(request_value)

    result = HuijiCorpusBuilder().build_candidate(request_value)

    assert result.state.value == "ready_for_embedding"
    relative_paths = {path.as_posix() for path in captured_paths}
    assert {
        "src/huiji_rag/build/wikitext_projection.py",
        "src/huiji_rag/build/story_projection.py",
        "src/huiji_rag/build/topic_projection.py",
        "src/huiji_rag/build/media_download_plan.py",
        "src/huiji_rag/resources/topic_catalog.v1.json",
    } <= relative_paths
    assert first_config != second_config
    assert orchestrator_module.P0_MEDIA_NEW_BYTES_MAX == 268435456
    assert orchestrator_module.P1_MEDIA_CUMULATIVE_NEW_BYTES_MAX == 2147483648
    assert orchestrator_module.MIN_FREE_AFTER_COMMIT_BYTES == 12884901888


def test_builder_not_downloaded_wikitext_media_is_diagnostic_only_without_handoff(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project, request = _fixture(tmp_path, monkeypatch)
    raw = project / "data/huiji/res1999"
    content = "== Gallery ==\n[[File:Missing Art.PNG|caption]]"
    content_sha256 = hashlib.sha256(content.encode("utf-8")).hexdigest()
    _write_jsonl(
        raw / "wikitext.jsonl",
        [
            {
                "site": "res1999",
                "pageid": 41,
                "ns": 0,
                "revid": 409,
                "title": "暴雨",
                "content": content,
                "content_sha256": content_sha256,
            }
        ],
    )
    _write_jsonl(
        raw / "resources_manifest.jsonl",
        [
            {
                "site": "res1999",
                "title": "文件:Missing Art.PNG",
                "url": "https://huiji-public.huijistatic.com/res1999/uploads/1/11/Missing_Art.PNG",
                "source": "huiji_file_namespace",
                "filename": "Missing Art.PNG",
                "sha1": "1" * 40,
                "size": 123,
                "download_status": "not_downloaded",
                "local_relpath": "assets/files/1/Missing Art.PNG",
            }
        ],
    )
    request_value = request("not-downloaded", "not-downloaded-run")
    recovery_manifest = json.loads(
        request_value.recovery_manifest_path.read_text(encoding="utf-8")
    )
    for name in ("data_pages.jsonl", "crawl_state.sqlite"):
        recovery_manifest["files"][name]["size"] = (raw / name).stat().st_size
        recovery_manifest["files"][name]["sha256"] = _sha256(raw / name)
    _write_json(request_value.recovery_manifest_path, recovery_manifest)
    request_value = replace(
        request_value,
        expected_fidelity_baseline_sha256=_sha256(request_value.fidelity_baseline_path),
    )

    result = HuijiCorpusBuilder().build_candidate(request_value)

    assert result.state.value == "diagnostic_only"
    assert result.build_root.is_dir()
    receipt = json.loads(
        (project / "eval/runs/not-downloaded-run/candidate_result.v1.json").read_text(
            encoding="utf-8"
        )
    )
    assert receipt["state"] == "diagnostic_only"
    assert receipt["diagnostics"] == ["referenced_resource_not_downloaded"]
    assert receipt["build_manifest"]
    assert not (result.build_root / "handoff/embedding_handoff.v1.json").exists()
    report = json.loads(
        (result.build_root / "build_report.json").read_text(encoding="utf-8")
    )
    manifest = json.loads(
        (result.build_root / "build_manifest.json").read_text(encoding="utf-8")
    )
    assert report["next_gate"] == receipt["next_gate"]
    assert report["diagnostic_reasons"] == receipt["diagnostics"]
    assert manifest["diagnostic_reasons"] == receipt["diagnostics"]
    allowlist = [
        json.loads(line)
        for line in (
            project
            / "eval/runs/not-downloaded-run/referenced_media_allowlist.v1.jsonl"
        ).read_text(encoding="utf-8").splitlines()
    ]
    assert len(allowlist) == 1
    assert allowlist[0]["filename"] == "Missing Art.PNG"
    assert allowlist[0]["size"] == 123
    assert allowlist[0]["expected_download_bytes"] == 123
    assert allowlist[0]["download_status"] == "not_downloaded"
    assert allowlist[0]["resource_id"] == "resource:predownload-sha1:" + "1" * 40
    assert allowlist[0]["content_sha256"] is None
    assert allowlist[0]["owner_ids"] == ["page:41"]
    capacity = json.loads(
        (
            project / "eval/runs/not-downloaded-run/media_capacity_report.v1.json"
        ).read_text(encoding="utf-8")
    )
    assert capacity["capacity_totals"]["selected_media_new_bytes"] == 123
    assert capacity["capacity_totals"]["MinIO_existing_object_bytes"] == 0

    verification = HuijiCorpusBuilder().verify_candidate(
        result.build_root,
        _sha256(result.build_manifest),
    )
    assert verification["next_gate"] == receipt["next_gate"]
    assert verification["diagnostic_reasons"] == receipt["diagnostics"]


def test_builder_capacity_states_prevent_ready_handoff(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _project, request = _fixture(tmp_path, monkeypatch)
    base = request("capacity-base", "capacity-base-run")

    unknown = HuijiCorpusBuilder().build_candidate(
        replace(
            base,
            build_version="capacity-unknown",
            run_dir=base.run_dir.parent / "capacity-unknown-run",
            capacity_planning=replace(
                base.capacity_planning,
                known_cloud_free_or_quota_bytes=None,
            ),
        )
    )
    assert unknown.state.value == "diagnostic_only"
    assert not (unknown.build_root / "handoff/embedding_handoff.v1.json").exists()

    blocked = HuijiCorpusBuilder().build_candidate(
        replace(
            base,
            build_version="capacity-blocked",
            run_dir=base.run_dir.parent / "capacity-blocked-run",
            capacity_planning=replace(
                base.capacity_planning,
                free_local_bytes=1024,
            ),
        )
    )
    assert blocked.state.value == "blocked"
    assert "capacity_blocked" in blocked.blockers
    assert not (blocked.build_root / "handoff/embedding_handoff.v1.json").exists()

    not_requested = HuijiCorpusBuilder().build_candidate(
        replace(
            base,
            build_version="capacity-not-requested",
            run_dir=base.run_dir.parent / "capacity-not-requested-run",
            capacity_planning=None,
        )
    )
    assert not_requested.state.value == "diagnostic_only"
    receipt = json.loads(
        (base.run_dir.parent / "capacity-not-requested-run/candidate_result.v1.json").read_text(
            encoding="utf-8"
        )
    )
    assert "capacity_not_requested" in receipt["diagnostics"]


def test_expected_gate_failure_is_blocked_but_unexpected_exception_propagates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project, request = _fixture(tmp_path, monkeypatch)
    bad = replace(
        request("bad-baseline", "bad-baseline-run"),
        expected_fidelity_baseline_sha256="0" * 64,
    )
    blocked = HuijiCorpusBuilder().build_candidate(bad)
    assert blocked.state.value == "blocked"
    assert blocked.blockers == ("fidelity_baseline_sha256_mismatch",)
    assert not blocked.build_root.exists()
    evidence = json.loads(
        (project / "eval/runs/bad-baseline-run/candidate_result.v1.json").read_text(
            encoding="utf-8"
        )
    )
    assert evidence["state"] == "blocked"

    missing_recovery = replace(
        request("missing-recovery", "missing-recovery-run"),
        recovery_manifest_path=None,
        recovery_audit_receipt_path=None,
        recovery_apply_receipt_path=None,
    )
    recovery_blocked = HuijiCorpusBuilder().build_candidate(missing_recovery)
    assert recovery_blocked.state.value == "blocked"
    assert recovery_blocked.blockers == ("source_recovery_invalid",)

    monkeypatch.setattr(
        orchestrator_module,
        "project_crawler_semantics",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("unexpected")),
    )
    with pytest.raises(RuntimeError, match="unexpected"):
        HuijiCorpusBuilder().build_candidate(
            request("unexpected-error", "unexpected-error-run")
        )


def test_builder_incomplete_not_downloaded_identity_keeps_capacity_unknown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project, request = _fixture(tmp_path, monkeypatch)
    raw = project / "data/huiji/res1999"
    content = "== Gallery ==\n[[File:Incomplete Art.PNG|caption]]"
    _write_jsonl(
        raw / "wikitext.jsonl",
        [
            {
                "site": "res1999",
                "pageid": 41,
                "ns": 0,
                "revid": 409,
                "title": "暴雨",
                "content": content,
                "content_sha256": hashlib.sha256(
                    content.encode("utf-8")
                ).hexdigest(),
            }
        ],
    )
    _write_jsonl(
        raw / "resources_manifest.jsonl",
        [
            {
                "site": "res1999",
                "title": "文件:Incomplete Art.PNG",
                "url": "https://res1999.huijiwiki.com/wiki/File:Incomplete_Art.PNG",
                "source": "huiji_file_namespace",
                "filename": "Incomplete Art.PNG",
                "sha1": "3" * 40,
                "size": 321,
                "download_status": "not_downloaded",
                "local_relpath": "assets/files/3/Incomplete Art.PNG",
            }
        ],
    )
    request_value = request("capacity-incomplete", "capacity-incomplete-run")
    recovery_manifest = json.loads(
        request_value.recovery_manifest_path.read_text(encoding="utf-8")
    )
    for name in ("data_pages.jsonl", "crawl_state.sqlite"):
        recovery_manifest["files"][name]["size"] = (raw / name).stat().st_size
        recovery_manifest["files"][name]["sha256"] = _sha256(raw / name)
    _write_json(request_value.recovery_manifest_path, recovery_manifest)
    request_value = replace(
        request_value,
        expected_fidelity_baseline_sha256=_sha256(
            request_value.fidelity_baseline_path
        ),
    )

    result = HuijiCorpusBuilder().build_candidate(request_value)

    assert result.state.value == "diagnostic_only"
    receipt = json.loads(
        (project / "eval/runs/capacity-incomplete-run/candidate_result.v1.json")
        .read_text(encoding="utf-8")
    )
    assert receipt["diagnostics"] == [
        "capacity_planning_incomplete",
        "referenced_resource_not_downloaded",
        "unknown_capacity",
    ]
    capacity = json.loads(
        (project / "eval/runs/capacity-incomplete-run/media_capacity_report.v1.json")
        .read_text(encoding="utf-8")
    )
    assert capacity["state"] == "unknown_capacity"
    assert capacity["capacity_sufficient"] is None
    assert capacity["not_eligible"][0]["reason_code"] == (
        "capacity_planning_incomplete"
    )
    assert capacity["not_eligible"][0]["binding_ids"]


def test_recovery_failure_does_not_publish_receipt_path_or_raw_exception(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project, request = _fixture(tmp_path, monkeypatch)
    sensitive_receipt = (
        project
        / "PRIVATE_RECOVERY_RECEIPTS_DO_NOT_PUBLISH"
        / "operator-only"
        / "apply.json"
    )
    blocked = HuijiCorpusBuilder().build_candidate(
        replace(
            request("missing-sensitive-receipt", "missing-sensitive-receipt-run"),
            recovery_apply_receipt_path=sensitive_receipt,
        )
    )

    assert blocked.state.value == "blocked"
    assert blocked.blockers == ("source_recovery_invalid",)
    artifact_path = (
        project
        / "eval/runs/missing-sensitive-receipt-run/candidate_result.v1.json"
    )
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    public_text = json.dumps(artifact, ensure_ascii=False, sort_keys=True)
    assert artifact["failure_detail"] == "recovery evidence is unavailable or invalid"
    assert str(sensitive_receipt) not in public_text
    assert sensitive_receipt.as_posix() not in public_text
    assert "PRIVATE_RECOVERY_RECEIPTS_DO_NOT_PUBLISH" not in public_text
    assert "apply.json" not in public_text
    assert "[Errno" not in public_text
    assert "No such file or directory" not in public_text


def test_semantic_gate_failure_does_not_publish_internal_path_or_exception(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project, request = _fixture(tmp_path, monkeypatch)
    sensitive = project / "PRIVATE_SEMANTIC_INPUT" / "secret.jsonl"
    monkeypatch.setattr(
        orchestrator_module,
        "project_crawler_semantics",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ValueError(f"invalid source at {sensitive}")
        ),
    )

    result = HuijiCorpusBuilder().build_candidate(
        request("semantic-failure", "semantic-failure-run")
    )

    assert result.state.value == "blocked"
    assert result.blockers == ("semantic_projection_invalid",)
    artifact = json.loads(
        (project / "eval/runs/semantic-failure-run/candidate_result.v1.json").read_text(
            encoding="utf-8"
        )
    )
    public_text = json.dumps(artifact, ensure_ascii=False, sort_keys=True)
    assert artifact["failure_detail"] == (
        "candidate gate did not pass: semantic_projection_invalid"
    )
    assert str(sensitive) not in public_text
    assert "PRIVATE_SEMANTIC_INPUT" not in public_text
