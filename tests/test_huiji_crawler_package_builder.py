from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

import pytest
import yaml

from bootstrap.package_verify import verify_package
from src.huiji_crawler_packaging.dependency_lock import inspect_wheelhouse
from src.huiji_crawler_packaging.standard_package import (
    PackageBuildError,
    create_deterministic_zip,
    evaluate_size,
    generate_manifest,
    generate_supply_chain_materials,
    load_file_policy,
    materialize_staging,
    scan_stage,
)
from tests.test_huiji_crawler_dependency_lock import write_wheel


def _policy(root: Path, entries: list[dict[str, object]]) -> Path:
    path = root / "files.yaml"
    path.write_text(
        yaml.safe_dump({"schema_version": "huiji_crawler_files.v1", "files": entries}, sort_keys=False),
        encoding="utf-8",
    )
    return path


def test_allowlist_rejects_globs_unknown_roles_duplicate_destinations_and_missing_inputs(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    (root / "a.py").write_text("a = 1\n", encoding="utf-8")
    base = {"source": "a.py", "destination": "a.py", "role": "runtime_source", "critical": False}
    cases = [
        [dict(base, source="*.py")],
        [dict(base, role="unknown")],
        [base, dict(base, source="a.py")],
        [dict(base, source="missing.py")],
    ]

    for index, entries in enumerate(cases):
        with pytest.raises(PackageBuildError):
            load_file_policy(root, _policy(root, entries))


def test_staging_contains_only_explicit_runtime_files_and_excludes_regenerable_data(tmp_path: Path) -> None:
    root = tmp_path / "project"
    stage = tmp_path / "stage"
    root.mkdir()
    (root / "runtime.py").write_text("value = 1\n", encoding="utf-8")
    (root / "data.json").write_text("regenerable", encoding="utf-8")
    policy = load_file_policy(
        root,
        _policy(
            root,
            [
                {
                    "source": "runtime.py",
                    "destination": "src/runtime.py",
                    "role": "runtime_source",
                    "critical": False,
                }
            ],
        ),
    )

    roles = materialize_staging(root, policy, stage)

    assert sorted(path.relative_to(stage).as_posix() for path in stage.rglob("*") if path.is_file()) == [
        "src/runtime.py"
    ]
    assert roles == {"src/runtime.py": ("runtime_source", False)}


def test_secret_scan_uses_private_cookie_values_without_serializing_them(tmp_path: Path) -> None:
    stage = tmp_path / "stage"
    stage.mkdir()
    (stage / "safe.py").write_text("value = 'private-cookie-value'\n", encoding="utf-8")

    report = scan_stage(stage, secret_values=(("huiji_session", "private-cookie-value"),))
    encoded = json.dumps(report, sort_keys=True)

    assert report["violation_count"] == 1
    assert report["violations"][0]["cookie_name"] == "huiji_session"
    assert "private-cookie-value" not in encoded


def test_secret_scan_does_not_treat_a_one_character_cookie_as_a_global_substring(tmp_path: Path) -> None:
    stage = tmp_path / "stage"
    stage.mkdir()
    (stage / "safe.py").write_text("builder_version = 1\n", encoding="utf-8")

    report = scan_stage(stage, secret_values=(("_gat", "1"),))

    assert report["violation_count"] == 0


def test_secret_scan_still_blocks_a_contextual_short_cookie_leak(tmp_path: Path) -> None:
    stage = tmp_path / "stage"
    stage.mkdir()
    (stage / "leak.txt").write_text("Cookie: _gat=1\n", encoding="utf-8")

    report = scan_stage(stage, secret_values=(("_gat", "1"),))

    assert report["violation_count"] == 1
    assert report["violations"] == [
        {"file": "leak.txt", "kind": "credential_value", "cookie_name": "_gat"}
    ]


def test_secret_scan_blocks_a_short_value_in_canonical_cookie_json(tmp_path: Path) -> None:
    stage = tmp_path / "stage"
    stage.mkdir()
    (stage / "credential.json").write_text(
        '{"cookies":[{"name":"_gat","path":"/","secure":true,"value":"1"}]}\n',
        encoding="utf-8",
    )

    report = scan_stage(stage, secret_values=(("_gat", "1"),))

    assert report["violation_count"] == 1
    assert report["violations"][0]["cookie_name"] == "_gat"


def test_manifest_covers_every_immutable_payload_and_verifier_agrees(tmp_path: Path) -> None:
    stage = tmp_path / "stage"
    stage.mkdir()
    required = {
        "huiji-crawler.cmd",
        "bootstrap/package_verify.py",
        "src/huiji_crawler_tool/cli.py",
        "config/crawler.yaml",
        "requirements-crawler.lock.txt",
    }
    roles: dict[str, tuple[str, bool]] = {}
    for relative in sorted(required):
        path = stage / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(relative, encoding="utf-8")
        roles[relative] = ("runtime_source", True)

    manifest = generate_manifest(stage, roles)

    assert {item["path"] for item in manifest["files"]} == required
    assert verify_package(stage)["status"] == "passed"


def test_sbom_notices_and_license_files_match_wheel_metadata(tmp_path: Path) -> None:
    wheelhouse = tmp_path / "wheels"
    write_wheel(wheelhouse, "Alpha", "1.0")
    requirements = tmp_path / "requirements.in"
    requirements.write_text("Alpha==1.0\n", encoding="utf-8")
    lock = inspect_wheelhouse(requirements, wheelhouse)
    stage = tmp_path / "stage"
    stage.mkdir()

    roles = generate_supply_chain_materials(stage, lock.records, source_tree_hash="a" * 64)
    sbom = json.loads((stage / "sbom.cdx.json").read_text(encoding="utf-8"))
    notices = json.loads((stage / "THIRD_PARTY_NOTICES.json").read_text(encoding="utf-8"))

    assert sbom["bomFormat"] == "CycloneDX"
    assert sbom["components"][0]["name"] == "alpha"
    assert notices["components"][0]["version"] == "1.0"
    assert any(path.startswith("THIRD_PARTY_LICENSES/alpha/") for path in roles)


def test_zip_order_timestamp_permissions_and_hash_are_deterministic(tmp_path: Path) -> None:
    stage = tmp_path / "stage"
    stage.mkdir()
    (stage / "z.txt").write_text("z", encoding="utf-8")
    (stage / "a.txt").write_text("a", encoding="utf-8")
    first = tmp_path / "first.zip"
    second = tmp_path / "second.zip"

    create_deterministic_zip(stage, first)
    create_deterministic_zip(stage, second)

    assert hashlib.sha256(first.read_bytes()).digest() == hashlib.sha256(second.read_bytes()).digest()
    with zipfile.ZipFile(first) as archive:
        assert archive.namelist() == ["a.txt", "z.txt"]
        assert len({info.date_time for info in archive.infolist()}) == 1
        assert all((info.external_attr >> 16) & 0o777 == 0o644 for info in archive.infolist())


def test_size_target_warns_and_only_zip_over_50_mib_blocks() -> None:
    assert evaluate_size(11 * 1024 * 1024, reference_mib=10, hard_mib=50)["status"] == "warning"
    with pytest.raises(PackageBuildError, match="50 MiB"):
        evaluate_size(51 * 1024 * 1024, reference_mib=10, hard_mib=50)
