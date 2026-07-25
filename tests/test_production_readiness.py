from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import threading
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
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


@pytest.mark.parametrize("uri", ["http://[", "http://[::1"])
def test_production_readiness_rejects_malformed_milvus_uri_without_500_or_secrets(
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


def test_production_readiness_full_verification_runs_once_at_startup_then_uses_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _closure_fixture(tmp_path)
    original_run = subprocess.run
    verifier_calls = 0

    def counting_run(*args, **kwargs):
        nonlocal verifier_calls
        verifier_calls += 1
        return original_run(*args, **kwargs)

    monkeypatch.setattr(main_mod.subprocess, "run", counting_run)
    with _production_client(monkeypatch, tmp_path) as client:
        assert verifier_calls == 1
        assert client.get("/health/ready").status_code == 200
        assert client.get("/health/ready").status_code == 200
    assert verifier_calls == 1


def test_production_readiness_tamper_reverification_is_fail_closed_and_cached(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    closure = _closure_fixture(tmp_path)
    original_run = subprocess.run
    verifier_calls = 0

    def counting_run(*args, **kwargs):
        nonlocal verifier_calls
        verifier_calls += 1
        return original_run(*args, **kwargs)

    monkeypatch.setattr(main_mod.subprocess, "run", counting_run)
    with _production_client(monkeypatch, tmp_path) as client:
        assert verifier_calls == 1
        closure[-1].write_bytes(closure[-1].read_bytes() + b"tampered")
        first = client.get("/health/ready")
        second = client.get("/health/ready")
    _assert_only_failure(first, "rag_artifacts")
    _assert_only_failure(second, "rag_artifacts")
    assert verifier_calls == 2


def test_production_readiness_invalidates_negative_cache_after_downstream_repair(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    closure = _closure_fixture(tmp_path)
    target = closure[-1]
    original = target.read_bytes()
    target.unlink()
    original_run = subprocess.run
    verifier_calls = 0

    def counting_run(*args, **kwargs):
        nonlocal verifier_calls
        verifier_calls += 1
        return original_run(*args, **kwargs)

    monkeypatch.setattr(main_mod.subprocess, "run", counting_run)
    with _production_client(monkeypatch, tmp_path) as client:
        assert verifier_calls == 1
        _assert_only_failure(client.get("/health/ready"), "rag_artifacts")
        assert verifier_calls == 1
        target.write_bytes(original)
        assert client.get("/health/ready").status_code == 200
    assert verifier_calls == 2


def test_production_readiness_retries_transient_verifier_failure_after_cooldown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _closure_fixture(tmp_path)
    original_run = subprocess.run
    verifier_calls = 0
    monotonic = [0.0]

    def transient_then_success(*args, **kwargs):
        nonlocal verifier_calls
        verifier_calls += 1
        if verifier_calls == 1:
            raise subprocess.TimeoutExpired(args[0], timeout=15)
        return original_run(*args, **kwargs)

    monkeypatch.setattr(main_mod, "_rag_monotonic", lambda: monotonic[0], raising=False)
    monkeypatch.setattr(main_mod.subprocess, "run", transient_then_success)
    with _production_client(monkeypatch, tmp_path) as client:
        _assert_only_failure(client.get("/health/ready"), "rag_artifacts")
        assert verifier_calls == 1
        monotonic[0] = 61.0
        assert client.get("/health/ready").status_code == 200
    assert verifier_calls == 2


def test_production_readiness_rejects_mutation_between_verification_and_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    closure = _closure_fixture(tmp_path)
    metadata = subprocess.run(
        [
            sys.executable,
            str(VERIFIER),
            "--root",
            str(tmp_path),
            "--metadata-json",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert metadata.returncode == 0, metadata.stdout + metadata.stderr
    mutated = False

    def racing_success(*args, **kwargs):
        nonlocal mutated
        if not mutated:
            closure[-1].write_bytes(closure[-1].read_bytes() + b"tampered")
            mutated = True
        return metadata

    monkeypatch.setattr(main_mod.subprocess, "run", racing_success)
    with _production_client(monkeypatch, tmp_path) as client:
        response = client.get("/health/ready")
    _assert_only_failure(response, "rag_artifacts")


def test_production_readiness_coalesces_concurrent_tamper_reverification(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    closure = _closure_fixture(tmp_path)
    with _production_client(monkeypatch, tmp_path):
        closure[-1].write_bytes(closure[-1].read_bytes() + b"tampered")
        entered = threading.Event()
        duplicate_entered = threading.Event()
        release = threading.Event()
        calls = 0
        calls_lock = threading.Lock()

        def blocking_failure(*args, **kwargs):
            nonlocal calls
            with calls_lock:
                calls += 1
                if calls > 1:
                    duplicate_entered.set()
            entered.set()
            release.wait(timeout=2)
            return SimpleNamespace(returncode=1)

        monkeypatch.setattr(main_mod.subprocess, "run", blocking_failure)
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(main_mod._verify_rag_artifacts)
            assert entered.wait(timeout=1)
            second = pool.submit(main_mod._verify_rag_artifacts)
            assert not duplicate_entered.wait(timeout=0.2)
            release.set()
            assert first.result(timeout=1) is False
            assert second.result(timeout=1) is False
        assert calls == 1


@pytest.mark.skipif(
    os.name == "nt",
    reason="Windows symlink creation requires host-specific privilege",
)
def test_production_readiness_rejects_symlinked_configured_root_before_resolve(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actual_root = tmp_path / "actual"
    _closure_fixture(actual_root)
    linked_root = tmp_path / "linked"
    linked_root.symlink_to(actual_root, target_is_directory=True)
    with _production_client(monkeypatch, linked_root) as client:
        response = client.get("/health/ready")
    _assert_only_failure(response, "rag_artifacts")


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


def test_closure_verifier_allows_unselected_build_output_without_hashing_it(
    tmp_path: Path,
) -> None:
    closure = _closure_fixture(tmp_path)
    build_manifest_path = closure[1]
    extra = build_manifest_path.parent / "extra.json"
    build_manifest = json.loads(build_manifest_path.read_text(encoding="utf-8"))
    build_manifest["artifacts"].append(
        {
            "relative_path": extra.relative_to(build_manifest_path.parent).as_posix(),
            "sha256": "0" * 64,
            "size": 15,
        }
    )
    _write_json(build_manifest_path, build_manifest)

    collection_path = closure[2]
    collection = json.loads(collection_path.read_text(encoding="utf-8"))
    collection["build_manifest"]["sha256"] = _sha256(build_manifest_path)
    collection["build_manifest"]["size"] = build_manifest_path.stat().st_size
    _write_json(collection_path, collection)

    pointer_path = closure[0]
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    pointer["build_manifest_sha256"] = _sha256(build_manifest_path)
    pointer["collection_manifest_sha256"] = _sha256(collection_path)
    _write_json(pointer_path, pointer)

    result = _run_verifier(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    expected_bytes = sum(path.stat().st_size for path in closure)
    assert result.stdout.strip() == (
        f"verified 11 files totaling {expected_bytes} bytes"
    )


def test_closure_verifier_rejects_canonical_duplicate_build_paths(
    tmp_path: Path,
) -> None:
    closure = _closure_fixture(tmp_path)
    build_manifest_path = closure[1]
    build_manifest = json.loads(build_manifest_path.read_text(encoding="utf-8"))
    duplicate = dict(build_manifest["artifacts"][0])
    build_manifest["artifacts"].append(duplicate)
    _write_json(build_manifest_path, build_manifest)

    collection_path = closure[2]
    collection = json.loads(collection_path.read_text(encoding="utf-8"))
    collection["build_manifest"]["sha256"] = _sha256(build_manifest_path)
    collection["build_manifest"]["size"] = build_manifest_path.stat().st_size
    _write_json(collection_path, collection)

    pointer_path = closure[0]
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    pointer["build_manifest_sha256"] = _sha256(build_manifest_path)
    pointer["collection_manifest_sha256"] = _sha256(collection_path)
    _write_json(pointer_path, pointer)

    result = _run_verifier(tmp_path)
    assert result.returncode != 0
    assert "duplicate canonical" in (result.stdout + result.stderr).lower()


def test_closure_verifier_rejects_raw_duplicate_alias_in_build_manifest(
    tmp_path: Path,
) -> None:
    closure = _closure_fixture(tmp_path)
    build_manifest_path = closure[1]
    build_manifest = json.loads(build_manifest_path.read_text(encoding="utf-8"))
    alias = dict(build_manifest["artifacts"][0])
    alias["relative_path"] = f"./{alias['relative_path']}"
    build_manifest["artifacts"].append(alias)
    _write_json(build_manifest_path, build_manifest)

    collection_path = closure[2]
    collection = json.loads(collection_path.read_text(encoding="utf-8"))
    collection["build_manifest"]["sha256"] = _sha256(build_manifest_path)
    collection["build_manifest"]["size"] = build_manifest_path.stat().st_size
    _write_json(collection_path, collection)

    pointer_path = closure[0]
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    pointer["build_manifest_sha256"] = _sha256(build_manifest_path)
    pointer["collection_manifest_sha256"] = _sha256(collection_path)
    _write_json(pointer_path, pointer)

    result = _run_verifier(tmp_path)
    assert result.returncode != 0
    assert "canonical" in (result.stdout + result.stderr).lower()


def test_closure_verifier_rejects_non_string_sha_in_unselected_build_entry(
    tmp_path: Path,
) -> None:
    closure = _closure_fixture(tmp_path)
    build_manifest_path = closure[1]
    build_manifest = json.loads(build_manifest_path.read_text(encoding="utf-8"))
    build_manifest["artifacts"].append(
        {
            "relative_path": "diagnostic/not-mounted.json",
            "sha256": int("1" * 64),
            "size": 1,
        }
    )
    _write_json(build_manifest_path, build_manifest)

    collection_path = closure[2]
    collection = json.loads(collection_path.read_text(encoding="utf-8"))
    collection["build_manifest"]["sha256"] = _sha256(build_manifest_path)
    collection["build_manifest"]["size"] = build_manifest_path.stat().st_size
    _write_json(collection_path, collection)

    pointer_path = closure[0]
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    pointer["build_manifest_sha256"] = _sha256(build_manifest_path)
    pointer["collection_manifest_sha256"] = _sha256(collection_path)
    _write_json(pointer_path, pointer)

    result = _run_verifier(tmp_path)
    assert result.returncode != 0
    assert "sha-256 is invalid" in (result.stdout + result.stderr).lower()


def test_closure_verifier_metadata_fingerprint_includes_directory_components(
    tmp_path: Path,
) -> None:
    _closure_fixture(tmp_path)
    result = subprocess.run(
        [
            sys.executable,
            str(VERIFIER),
            "--root",
            str(tmp_path),
            "--metadata-json",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    fingerprint_paths = {entry[0] for entry in payload["fingerprint"]}
    assert "." in fingerprint_paths
    assert "fixture-build" in fingerprint_paths
    assert "fixture-build/runtime" in fingerprint_paths
    assert "activation/transactions/fixture-activation" in fingerprint_paths


def test_closure_verifier_observation_race_uses_transient_exit_code(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spec = importlib.util.spec_from_file_location(
        "verify_rag_closure_test_module",
        VERIFIER,
    )
    assert spec is not None and spec.loader is not None
    verifier_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verifier_module)

    def raise_observation_race(_root):
        raise verifier_module.TransientVerificationError(
            "artifact changed during verification"
        )

    monkeypatch.setattr(
        verifier_module,
        "_verified_closure",
        raise_observation_race,
    )
    assert verifier_module.main(["--root", str(tmp_path)]) == 75


@pytest.mark.parametrize(
    "aliased_path",
    [
        "data/processed/huiji/fixture-build/./parent_blocks.jsonl",
        "data/processed/huiji/fixture-build//parent_blocks.jsonl",
    ],
)
def test_closure_verifier_rejects_raw_path_normalization_aliases(
    tmp_path: Path,
    aliased_path: str,
) -> None:
    closure = _closure_fixture(tmp_path)
    collection_path = closure[2]
    collection = json.loads(collection_path.read_text(encoding="utf-8"))
    collection["artifacts"]["parent_blocks"]["relative_path"] = aliased_path
    _write_json(collection_path, collection)
    pointer_path = closure[0]
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    pointer["collection_manifest_sha256"] = _sha256(collection_path)
    _write_json(pointer_path, pointer)

    result = _run_verifier(tmp_path)
    assert result.returncode != 0
    assert "canonical" in (result.stdout + result.stderr).lower()


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
