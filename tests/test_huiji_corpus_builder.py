from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable

import pytest

from src.huiji_rag.build.contracts import CorpusBuildRequest, canonical_json_bytes
from src.huiji_rag.build.orchestrator import HuijiCorpusBuilder
from src.huiji_rag.build.projection import project_crawler_semantics
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
    _write_jsonl(
        raw / "pages.jsonl",
        [{"site": "res1999", "pageid": 41, "seen_at": "snapshot", "title": "Item 41"}],
    )
    _write_jsonl(
        raw / "wikitext.jsonl",
        [{"site": "res1999", "pageid": 41, "revid": 409, "title": "Item 41"}],
    )
    _write_jsonl(raw / "data_pages.jsonl", [data_row])
    _write_jsonl(raw / "resources_manifest.jsonl", [])

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
    _write_json(
        inventory,
        ObjectInventory.create(
            "reverse1999-assets",
            "reverse1999",
            (),
            captured_at_utc="2026-07-21T00:00:00Z",
            bucket_policy_summary="absent",
        ).to_json(),
    )
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
    _wrap(monkeypatch, orchestrator_module, "project_crawler_semantics", events, "projection")
    _wrap(monkeypatch, orchestrator_module.media_stage, "prepare_voice_resource_rows", events, "voice_resources")
    _wrap(monkeypatch, orchestrator_module.VoiceBindingStage, "run", events, "voice")
    _wrap(monkeypatch, orchestrator_module.media_stage, "assemble_media_v3", events, "media")
    _wrap(monkeypatch, orchestrator_module, "build_fidelity_ledger", events, "fidelity")
    _wrap(monkeypatch, orchestrator_module, "write_candidate_artifacts", events, "artifacts")

    first = HuijiCorpusBuilder().build_candidate(request("candidate-a", "run-a"))
    second = HuijiCorpusBuilder().build_candidate(request("candidate-b", "run-b"))

    expected = [
        "source",
        "projection",
        "voice_resources",
        "voice",
        "media",
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

    monkeypatch.setattr(
        orchestrator_module,
        "project_crawler_semantics",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("unexpected")),
    )
    with pytest.raises(RuntimeError, match="unexpected"):
        HuijiCorpusBuilder().build_candidate(
            request("unexpected-error", "unexpected-error-run")
        )
