from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

import backend.main as main_mod


ROOT = Path(__file__).resolve().parents[1]
VERIFIER = ROOT / "deploy" / "bin" / "verify-rag-closure.py"
SUBSYSTEMS = ("configuration", "rag_artifacts", "milvus", "minio", "mysql")
SECRET_SENTINELS = (
    "deepseek-secret-sentinel",
    "siliconflow-secret-sentinel",
    "minio-access-secret-sentinel",
    "minio-secret-secret-sentinel",
    "mysql-user-secret-sentinel",
    "mysql-password-secret-sentinel",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        (
            json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")
    )


def _closure_fixture(root: Path) -> list[Path]:
    build_version = "fixture-build"
    activation_id = "fixture-activation"
    build_root = root / build_version
    artifact_payloads = {
        "parent_blocks": ("parent_blocks.jsonl", b'{"parent_id":"p1"}\n'),
        "child_blocks": ("child_blocks.jsonl", b'{"child_id":"c1"}\n'),
        "media_assets": (
            "runtime/media_assets.v3.jsonl",
            b'{"binding_id":"b1"}\n',
        ),
        "child_bm25": ("indexes/child_text_bm25.json", b'{"ids":["c1"]}\n'),
        "media_bm25": (
            "indexes/media_binding_bm25.v3.json",
            b'{"ids":["b1"]}\n',
        ),
        "media_schema": (
            "runtime/media_assets.v3.schema.json",
            b'{"schema_version":"evb.media-assets/v3"}\n',
        ),
        "media_manifest": (
            "runtime/media_assets.v3.manifest.json",
            b'{"schema_version":"evb.media-artifact-manifest/v3"}\n',
        ),
    }
    artifact_paths: dict[str, Path] = {}
    for name, (relative, raw) in artifact_payloads.items():
        target = build_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        artifact_paths[name] = target

    build_manifest = build_root / "build_manifest.json"
    _write_json(
        build_manifest,
        {
            "schema_version": "huiji.corpus-build/v2",
            "artifact_schema_version": "evb.media-asset/v3",
            "build_version": build_version,
            "artifacts": [
                {
                    "relative_path": path.relative_to(build_root).as_posix(),
                    "sha256": _sha256(path),
                    "size": path.stat().st_size,
                }
                for path in artifact_paths.values()
            ],
        },
    )

    transaction_root = root / "activation" / "transactions" / activation_id
    collection_manifest = transaction_root / "collection_manifest.v1.json"
    _write_json(
        collection_manifest,
        {
            "schema_version": "evb.collection-manifest/v1",
            "artifact_schema_version": "evb.media-asset/v3",
            "build_version": build_version,
            "build_manifest": {
                "relative_path": (
                    f"data/processed/huiji/{build_version}/build_manifest.json"
                ),
                "sha256": _sha256(build_manifest),
                "size": build_manifest.stat().st_size,
            },
            "artifacts": {
                name: {
                    "relative_path": (
                        "data/processed/huiji/"
                        + path.relative_to(root).as_posix()
                    ),
                    "sha256": _sha256(path),
                    "size": path.stat().st_size,
                }
                for name, path in artifact_paths.items()
            },
            "milvus": {
                "collection": "fixture-collection",
                "database": "fixture-db",
                "schema_sha256": "a" * 64,
            },
            "embedding": {
                "model_id": "fixture-model",
                "config_fingerprint": "b" * 64,
            },
        },
    )
    deployment_inventory = transaction_root / "deployment_inventory.v1.json"
    _write_json(
        deployment_inventory,
        {
            "schema_version": "huiji.activation-deployment-inventory/v1",
            "activation_id": activation_id,
        },
    )
    pointer = root / "active_build.v1.json"
    _write_json(
        pointer,
        {
            "schema_version": "evb.active-build/v1",
            "generation": 1,
            "build_version": build_version,
            "previous_build_version": "previous-build",
            "build_manifest_sha256": _sha256(build_manifest),
            "milvus_collection_name": "fixture-collection",
            "collection_schema_fingerprint": "a" * 64,
            "collection_manifest_sha256": _sha256(collection_manifest),
            "embedding_model_id": "fixture-model",
            "embedding_config_fingerprint": "b" * 64,
            "artifact_schema_version": "evb.media-asset/v3",
            "deployment_inventory_sha256": _sha256(deployment_inventory),
            "activation_epoch": 1,
            "activation_id": activation_id,
            "activated_at_utc": "2026-07-22T06:59:27Z",
        },
    )
    return [
        pointer,
        build_manifest,
        collection_manifest,
        deployment_inventory,
        *artifact_paths.values(),
    ]


def _production_cfg(processed_root: Path) -> SimpleNamespace:
    return SimpleNamespace(
        llm=SimpleNamespace(api_key=SECRET_SENTINELS[0]),
        embedding=SimpleNamespace(api_key=SECRET_SENTINELS[1]),
        huiji=SimpleNamespace(
            enabled=True,
            source_mode="huiji_crawler",
            processed_root=processed_root,
        ),
        vectorstore=SimpleNamespace(
            provider="milvus",
            uri="http://standalone:19530",
            db_name="fixture-db",
            collection_name="fixture-collection",
        ),
        assets=SimpleNamespace(
            provider="minio",
            endpoint="minio:9000",
            bucket_name="fixture-bucket",
            secure=False,
            access_key=SECRET_SENTINELS[2],
            secret_key=SECRET_SENTINELS[3],
        ),
        mysql=SimpleNamespace(
            host="mysql",
            port=3306,
            database="fixture-wiki",
            user=SECRET_SENTINELS[4],
            password=SECRET_SENTINELS[5],
            charset="utf8mb4",
        ),
        paths=SimpleNamespace(project_root=ROOT),
    )


@contextmanager
def _production_client(
    monkeypatch: pytest.MonkeyPatch,
    processed_root: Path,
) -> Iterator[TestClient]:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("HUIJI_PROCESSED_ROOT", str(processed_root))
    monkeypatch.setattr(main_mod, "cfg", _production_cfg(processed_root))
    monkeypatch.setattr(main_mod, "_probe_milvus", lambda: True, raising=False)
    monkeypatch.setattr(main_mod, "_probe_minio", lambda: True, raising=False)
    monkeypatch.setattr(main_mod, "_probe_mysql", lambda: True, raising=False)
    monkeypatch.setattr(main_mod, "_ensure_loaded", lambda: None)
    with TestClient(main_mod.app) as client:
        yield client


def _assert_only_failure(response, subsystem: str) -> None:
    assert response.status_code == 503
    payload = response.json()
    assert payload == {
        "status": "not_ready",
        "checks": {
            name: ("fail" if name == subsystem else "pass")
            for name in SUBSYSTEMS
        },
        "failing_subsystems": [subsystem],
    }
    serialized = response.text
    for sentinel in SECRET_SENTINELS:
        assert sentinel not in serialized


def test_liveness_is_lightweight_and_separate_from_readiness(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(main_mod, "_ensure_loaded", lambda: None)
    with TestClient(main_mod.app) as client:
        monkeypatch.setattr(
            main_mod,
            "_ensure_loaded",
            lambda: pytest.fail("liveness attempted dependency loading"),
        )
        response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "alive"}


@pytest.mark.parametrize("uri", ["", "http://127.0.0.1:19530", "http://localhost:19530"])
def test_production_readiness_rejects_missing_or_loopback_milvus_configuration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    uri: str,
) -> None:
    _closure_fixture(tmp_path)
    with _production_client(monkeypatch, tmp_path) as client:
        main_mod.cfg.vectorstore.uri = uri
        response = client.get("/health/ready")
    _assert_only_failure(response, "milvus")


@pytest.mark.parametrize("credential", ["access_key", "secret_key"])
def test_production_readiness_rejects_missing_minio_credentials(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    credential: str,
) -> None:
    _closure_fixture(tmp_path)
    with _production_client(monkeypatch, tmp_path) as client:
        setattr(main_mod.cfg.assets, credential, "")
        response = client.get("/health/ready")
    _assert_only_failure(response, "minio")


@pytest.mark.parametrize("credential", ["user", "password"])
def test_production_readiness_rejects_missing_mysql_credentials(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    credential: str,
) -> None:
    _closure_fixture(tmp_path)
    with _production_client(monkeypatch, tmp_path) as client:
        setattr(main_mod.cfg.mysql, credential, "")
        response = client.get("/health/ready")
    _assert_only_failure(response, "mysql")


def test_production_readiness_rejects_missing_active_pointer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with _production_client(monkeypatch, tmp_path) as client:
        response = client.get("/health/ready")
    _assert_only_failure(response, "rag_artifacts")


@pytest.mark.parametrize("mutation", ["missing", "hash_mismatch"])
@pytest.mark.parametrize("closure_index", range(1, 11))
def test_production_readiness_rejects_every_broken_manifest_declared_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    closure_index: int,
    mutation: str,
) -> None:
    closure = _closure_fixture(tmp_path)
    target = closure[closure_index]
    if mutation == "missing":
        target.unlink()
    else:
        target.write_bytes(target.read_bytes() + b"tampered")
    with _production_client(monkeypatch, tmp_path) as client:
        response = client.get("/health/ready")
    _assert_only_failure(response, "rag_artifacts")


@pytest.mark.parametrize(
    ("subsystem", "probe"),
    [
        ("milvus", "_probe_milvus"),
        ("minio", "_probe_minio"),
        ("mysql", "_probe_mysql"),
    ],
)
def test_production_readiness_reports_only_the_unusable_dependency_without_secrets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    subsystem: str,
    probe: str,
) -> None:
    _closure_fixture(tmp_path)
    with _production_client(monkeypatch, tmp_path) as client:
        monkeypatch.setattr(main_mod, probe, lambda: False, raising=False)
        response = client.get("/health/ready")
    _assert_only_failure(response, subsystem)


def test_production_readiness_reports_configuration_failure_without_secrets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _closure_fixture(tmp_path)
    with _production_client(monkeypatch, tmp_path) as client:
        main_mod.cfg.llm.api_key = ""
        response = client.get("/health/ready")
    _assert_only_failure(response, "configuration")


def test_production_readiness_requires_explicit_artifact_root_configuration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _closure_fixture(tmp_path)
    with _production_client(monkeypatch, tmp_path) as client:
        monkeypatch.delenv("HUIJI_PROCESSED_ROOT")
        response = client.get("/health/ready")
    _assert_only_failure(response, "configuration")


def test_production_readiness_passes_all_explicit_gates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _closure_fixture(tmp_path)
    with _production_client(monkeypatch, tmp_path) as client:
        response = client.get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "checks": {name: "pass" for name in SUBSYSTEMS},
        "failing_subsystems": [],
    }


def test_minio_readiness_probe_has_bounded_connect_and_read_timeouts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: dict[str, object] = {}

    class FakeMinio:
        def __init__(self, *args, **kwargs):
            observed.update(kwargs)

        def bucket_exists(self, bucket_name: str) -> bool:
            assert bucket_name == "fixture-bucket"
            return True

    monkeypatch.setattr(main_mod, "cfg", _production_cfg(tmp_path))
    monkeypatch.setitem(
        sys.modules,
        "minio",
        SimpleNamespace(Minio=FakeMinio),
    )
    assert main_mod._probe_minio() is True
    http_client = observed["http_client"]
    timeout = http_client.connection_pool_kw["timeout"]
    assert timeout.connect_timeout == 3
    assert timeout.read_timeout == 3


def _run_verifier(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(VERIFIER), "--root", str(root)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def test_closure_verifier_reports_manifest_derived_count_and_bytes(
    tmp_path: Path,
) -> None:
    closure = _closure_fixture(tmp_path)
    expected_bytes = sum(path.stat().st_size for path in closure)
    result = _run_verifier(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == (
        f"verified 11 files totaling {expected_bytes} bytes"
    )


def test_closure_verifier_rejects_manifest_path_escape(
    tmp_path: Path,
) -> None:
    closure = _closure_fixture(tmp_path)
    collection_path = closure[2]
    collection = json.loads(collection_path.read_text(encoding="utf-8"))
    collection["artifacts"]["parent_blocks"]["relative_path"] = "../outside.json"
    _write_json(collection_path, collection)
    pointer_path = closure[0]
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    pointer["collection_manifest_sha256"] = _sha256(collection_path)
    _write_json(pointer_path, pointer)

    result = _run_verifier(tmp_path)
    assert result.returncode != 0
    assert "escape" in (result.stdout + result.stderr).lower()


@pytest.mark.skipif(
    os.name == "nt",
    reason="Windows symlink creation requires host-specific privilege",
)
def test_closure_verifier_rejects_symlinked_artifact_component(
    tmp_path: Path,
) -> None:
    closure = _closure_fixture(tmp_path)
    target = closure[4]
    outside = tmp_path.parent / "outside-artifact.jsonl"
    outside.write_bytes(target.read_bytes())
    target.unlink()
    target.symlink_to(outside)

    result = _run_verifier(tmp_path)
    assert result.returncode != 0
    assert "symlink" in (result.stdout + result.stderr).lower()
