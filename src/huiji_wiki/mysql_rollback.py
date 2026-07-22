"""Verified logical backup and isolated restore support for the Wiki MySQL."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import Any, Iterable
import urllib.request

from src.huiji_wiki.mysql_inventory import collect_mysql_inventory, compare_inventories


PASSING_RECEIPT_SCHEMA = "huiji.wiki-rollback-receipt/v1"
EMERGENCY_RECEIPT_SCHEMA = "huiji.wiki-emergency-rollback-receipt/v1"
TEST_ONLY_RECEIPT_SCHEMA = "huiji.wiki-rollback-test-receipt/v1"
FAILURE_SCHEMA = "huiji.wiki-rollback-verification-failure/v1"
SOURCE_CONTAINER = "reverse1999-main-mysql"
SOURCE_DATABASE = "reverse1999_wiki"
RECEIPT_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
TEMP_CONTAINER_PREFIX = "wiki-rollback-verify-"
APPLY_TEST_CONTAINER_PREFIX = "wiki-rollback-apply-"
_OWNED_TEST_AUTHORITIES: dict[str, dict[str, str]] = {}

FROZEN_INPUTS = {
    "candidate_manifest": (
        "data/processed/huiji/crawler-v3-20260721t051246z/build_manifest.json",
        "293410a1da4909e6b07e3f755ba0b4ba10b7008152330d5e2f98bcf93a573b5f",
    ),
    "compatibility_receipt": (
        "eval/huiji_wiki_v3_compatibility/20260720T162923Z/"
        "wiki_media_v3_compatibility_receipt.v1.json",
        "b0c82cbaa77303819ee93f600c2f4518152984580bb36d636e0d5063a67ec56d",
    ),
    "activation_proposal": (
        "data/processed/huiji/activation/proposals/candidate-f-review-20260721t071308z/"
        "activation_proposal.v1.json",
        "ce5e6966b80f0b9f1c2300e95866a7d0b9b8d9e108333311f0f92a8d27af1536",
    ),
}
ACTIVE_POINTER = "data/processed/huiji/active_build.v1.json"
COMPOSE_PATH = "infra/milvus/docker-compose.yml"


def validate_receipt_id(value: str) -> str:
    if not RECEIPT_ID_PATTERN.fullmatch(value):
        raise ValueError("invalid receipt_id")
    return value


def resolve_under(root: Path, relative: str | Path) -> Path:
    root = Path(root).resolve()
    candidate = (root / relative).resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError(f"path escape rejected: {relative}")
    return candidate


def canonical_json_bytes(payload: dict[str, Any], *, include_self_hash: bool = False) -> bytes:
    value = dict(payload)
    if not include_self_hash:
        value.pop("receipt_sha256", None)
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def mysqldump_args(database: str) -> list[str]:
    if database != SOURCE_DATABASE:
        raise ValueError("unsupported dump database")
    return [
        "--single-transaction",
        "--skip-lock-tables",
        "--quick",
        "--routines",
        "--triggers",
        "--events",
        "--hex-blob",
        "--set-gtid-purged=OFF",
        "--no-tablespaces",
        "--default-character-set=utf8mb4",
        "--skip-comments",
        database,
    ]


def temporary_container_args(*, container_name: str, image_id: str, operation_id: str) -> list[str]:
    validate_receipt_id(operation_id)
    if not container_name.startswith(TEMP_CONTAINER_PREFIX):
        raise ValueError("temporary container name has invalid prefix")
    if not image_id.startswith("sha256:"):
        raise ValueError("temporary container requires immutable image ID")
    return [
        "docker", "run", "--detach", "--rm",
        "--name", container_name,
        "--network", "none",
        "--tmpfs", "/var/lib/mysql:rw,nosuid,noexec",
        "--label", f"com.reverse1999.wiki.rollback.operation={operation_id}",
        "--label", "com.reverse1999.wiki.rollback.test-only=true",
        "--env", "MYSQL_ALLOW_EMPTY_PASSWORD=yes",
        image_id,
    ]


def owned_apply_container_args(*, container_name: str, image_id: str, operation_id: str) -> list[str]:
    validate_receipt_id(operation_id)
    if not container_name.startswith(APPLY_TEST_CONTAINER_PREFIX):
        raise ValueError("owned apply container name has invalid prefix")
    if not image_id.startswith("sha256:"):
        raise ValueError("owned apply container requires immutable image ID")
    return [
        "docker", "run", "--detach", "--rm",
        "--name", container_name,
        "--network", "none",
        "--tmpfs", "/var/lib/mysql:rw,nosuid,noexec",
        "--label", f"com.reverse1999.wiki.rollback.operation={operation_id}",
        "--label", "com.reverse1999.wiki.rollback.test-only=true",
        "--label", "com.reverse1999.wiki.rollback.role=apply-target",
        "--env", "MYSQL_ALLOW_EMPTY_PASSWORD=yes",
        image_id,
    ]


def build_restore_confirmation(receipt_id: str) -> str:
    return f"RESTORE {SOURCE_DATABASE} FROM {validate_receipt_id(receipt_id)}"


def validate_passing_receipt(receipt_path: Path, *, project_root: Path) -> dict[str, Any]:
    return _validate_receipt(
        receipt_path,
        project_root=project_root,
        expected_schema=PASSING_RECEIPT_SCHEMA,
        require_test_only=False,
    )


def validate_test_only_receipt(receipt_path: Path, *, project_root: Path) -> dict[str, Any]:
    return _validate_receipt(
        receipt_path,
        project_root=project_root,
        expected_schema=TEST_ONLY_RECEIPT_SCHEMA,
        require_test_only=True,
    )


def _validate_receipt(
    receipt_path: Path,
    *,
    project_root: Path,
    expected_schema: str,
    require_test_only: bool,
) -> dict[str, Any]:
    receipt_path = Path(receipt_path).resolve()
    project_root = Path(project_root).resolve()
    if receipt_path != project_root and project_root not in receipt_path.parents:
        raise ValueError("receipt path escapes project root")
    raw = receipt_path.read_bytes()
    payload = json.loads(raw.decode("utf-8"))
    if payload.get("schema_version") != expected_schema:
        raise ValueError("invalid receipt schema")
    if payload.get("status") != "passed" or bool(payload.get("test_only")) != require_test_only:
        raise ValueError("receipt is not passing")
    expected_internal = hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
    if payload.get("receipt_sha256") != expected_internal:
        raise ValueError("receipt internal hash mismatch")
    if raw != canonical_json_bytes(payload, include_self_hash=True):
        raise ValueError("receipt canonical bytes mismatch")
    for pin in payload.get("sidecars", []):
        path = resolve_under(project_root, str(pin["path"]))
        _verify_pin(path, pin)
    dump_pin = payload.get("dump")
    if isinstance(dump_pin, dict) and dump_pin.get("path"):
        _verify_pin(resolve_under(project_root, str(dump_pin["path"])), dump_pin)
    entrypoint_pin = payload.get("restore_entrypoint")
    if not isinstance(entrypoint_pin, dict) or not entrypoint_pin.get("path"):
        raise ValueError("restore entrypoint pin missing")
    _verify_pin(resolve_under(project_root, str(entrypoint_pin["path"])), entrypoint_pin)
    return payload


class DockerMysqlClient:
    """Run read-only MySQL queries through docker exec without exporting passwords."""

    def __init__(self, container: str, *, allow_empty_password: bool = False):
        self.container = container
        self.allow_empty_password = allow_empty_password

    def query_bytes(self, sql: str, *, database: str | None = None) -> bytes:
        command = self._mysql_shell(database)
        result = _run(
            ["docker", "exec", "-i", self.container, "sh", "-lc", command],
            input_bytes=sql.encode("utf-8"),
        )
        return result.stdout

    def _mysql_shell(self, database: str | None) -> str:
        if database is not None and database != SOURCE_DATABASE:
            raise ValueError("unsupported MySQL database")
        password_setup = "" if self.allow_empty_password else (
            'if [ -z "${MYSQL_ROOT_PASSWORD:-}" ]; then exit 41; fi; '
            'export MYSQL_PWD="$MYSQL_ROOT_PASSWORD"; '
        )
        database_arg = f" {SOURCE_DATABASE}" if database else ""
        return (
            password_setup
            + "exec mysql -uroot --batch --skip-column-names "
            "--default-character-set=utf8mb4 --binary-mode=1"
            + database_arg
        )


def inspect_container(container: str) -> dict[str, Any]:
    result = _run(["docker", "inspect", container])
    values = json.loads(result.stdout.decode("utf-8"))
    if not isinstance(values, list) or len(values) != 1:
        raise RuntimeError("unexpected docker inspect output")
    value = values[0]
    state = value.get("State") or {}
    health = state.get("Health") or {}
    network = value.get("NetworkSettings") or {}
    host = value.get("HostConfig") or {}
    config = value.get("Config") or {}
    return {
        "container_id": str(value.get("Id") or ""),
        "image_id": str(value.get("Image") or ""),
        "status": str(state.get("Status") or ""),
        "health": str(health.get("Status") or ""),
        "ports": network.get("Ports") or {},
        "network_mode": str(host.get("NetworkMode") or ""),
        "labels": config.get("Labels") or {},
    }


def mysql_server_version(client: DockerMysqlClient) -> str:
    return client.query_bytes("SELECT VERSION();").decode("ascii").strip()


def build_pre_import_receipt(project_root: Path, receipt_id: str) -> dict[str, Any]:
    return _build_verified_backup(
        project_root=Path(project_root),
        receipt_id=validate_receipt_id(receipt_id),
        source_container=SOURCE_CONTAINER,
        schema_version=PASSING_RECEIPT_SCHEMA,
        require_frozen_inputs=True,
        test_only=False,
        source_allow_empty_password=False,
    )


def build_emergency_receipt(project_root: Path, receipt_id: str) -> dict[str, Any]:
    return _build_verified_backup(
        project_root=Path(project_root),
        receipt_id=validate_receipt_id(receipt_id),
        source_container=SOURCE_CONTAINER,
        schema_version=EMERGENCY_RECEIPT_SCHEMA,
        require_frozen_inputs=False,
        test_only=False,
        source_allow_empty_password=False,
    )


def build_test_only_emergency_receipt(
    project_root: Path,
    receipt_id: str,
    *,
    source_container: str,
    restore_target_container: str | None = None,
) -> dict[str, Any]:
    _require_owned_test_authority(source_container)
    target = restore_target_container or source_container
    _require_owned_test_authority(target)
    return _build_verified_backup(
        project_root=Path(project_root),
        receipt_id=validate_receipt_id(receipt_id),
        source_container=source_container,
        schema_version=TEST_ONLY_RECEIPT_SCHEMA,
        require_frozen_inputs=False,
        test_only=True,
        source_allow_empty_password=True,
        restore_target_container=target,
    )


def _build_verified_backup(
    *,
    project_root: Path,
    receipt_id: str,
    source_container: str,
    schema_version: str,
    require_frozen_inputs: bool,
    test_only: bool,
    source_allow_empty_password: bool,
    restore_target_container: str | None = None,
) -> dict[str, Any]:
    project_root = project_root.resolve()
    namespace = {
        PASSING_RECEIPT_SCHEMA: "pre-import",
        EMERGENCY_RECEIPT_SCHEMA: "emergency",
        TEST_ONLY_RECEIPT_SCHEMA: "test-only",
    }.get(schema_version)
    if namespace is None:
        raise ValueError("unsupported receipt schema")
    backup_root = resolve_under(project_root, Path("backups/wiki-mysql") / namespace / receipt_id)
    evidence_root = resolve_under(
        project_root,
        Path("eval/huiji_wiki_rollback")
        / (Path(receipt_id) if namespace == "pre-import" else Path(namespace) / receipt_id),
    )
    if backup_root.exists() or evidence_root.exists():
        raise FileExistsError("rollback output directory already exists")
    backup_root.mkdir(parents=True, exist_ok=False)
    evidence_root.mkdir(parents=True, exist_ok=False)
    failure_path = evidence_root / "verification_failure.v1.json"
    temp_name = f"{TEMP_CONTAINER_PREFIX}{receipt_id}"
    temp_started = False
    try:
        protected_before = _protected_state(project_root, require_frozen=require_frozen_inputs)
        authority = inspect_container(source_container)
        if authority["status"] != "running" or authority["health"] not in {"", "healthy"}:
            raise RuntimeError("source MySQL container is not healthy")
        if test_only:
            _require_owned_test_authority(source_container, expected_image=authority["image_id"])
        source_client = DockerMysqlClient(
            source_container,
            allow_empty_password=source_allow_empty_password,
        )
        version = mysql_server_version(source_client)
        source_before = collect_mysql_inventory(source_client, SOURCE_DATABASE)
        dump_path = backup_root / "reverse1999_wiki.sql"
        dump_pin = _write_dump_create_new(
            source_container,
            dump_path,
            allow_empty_password=source_allow_empty_password,
        )
        source_after = collect_mysql_inventory(source_client, SOURCE_DATABASE)
        drift = compare_inventories(source_before, source_after)
        if drift:
            raise RuntimeError(f"source inventory drift: {drift[:3]}")

        if _container_exists(temp_name):
            raise RuntimeError("temporary restore container already exists")
        _run(temporary_container_args(
            container_name=temp_name,
            image_id=authority["image_id"],
            operation_id=receipt_id,
        ))
        temp_started = True
        _wait_mysql_ready(temp_name)
        temp_info = inspect_container(temp_name)
        if temp_info["image_id"] != authority["image_id"] or any(temp_info["ports"].values()):
            raise RuntimeError("temporary restore authority mismatch")
        temp_client = DockerMysqlClient(temp_name, allow_empty_password=True)
        temp_client.query_bytes(
            "CREATE DATABASE reverse1999_wiki CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
        )
        _restore_dump(temp_name, dump_path)
        restored = collect_mysql_inventory(temp_client, SOURCE_DATABASE)
        differences = compare_inventories(source_before, restored)
        if differences:
            raise RuntimeError(f"restored inventory differs: {differences[:5]}")
        verification = {
            "schema_version": "huiji.wiki-mysql-restore-verification/v1",
            "status": "passed",
            "source_inventory_sha256": source_before["inventory_sha256"],
            "restored_inventory_sha256": restored["inventory_sha256"],
            "differences": [],
            "temporary_container": {
                "name": temp_name,
                "image_id": temp_info["image_id"],
                "network": "none",
                "published_ports": False,
            },
        }
    except BaseException as exc:
        _write_failure(failure_path, receipt_id, exc)
        raise
    finally:
        if temp_started:
            _remove_owned_container(temp_name)
        if _container_exists(temp_name):
            if not failure_path.exists():
                _write_failure(failure_path, receipt_id, RuntimeError("temporary container cleanup failed"))

    if _container_exists(temp_name):
        raise RuntimeError("temporary restore container cleanup failed")
    protected_after = _protected_state(project_root, require_frozen=require_frozen_inputs)
    if protected_before != protected_after:
        _write_failure(failure_path, receipt_id, RuntimeError("protected state drift"))
        raise RuntimeError("protected state drift")

    sidecar_values = {
        "source_inventory.before.v1.json": source_before,
        "source_inventory.after.v1.json": source_after,
        "restored_inventory.v1.json": restored,
        "restore_verification.v1.json": verification,
    }
    sidecars: list[dict[str, Any]] = []
    for name, value in sidecar_values.items():
        path = evidence_root / name
        _write_create_new(path, _plain_canonical_json(value))
        sidecars.append(_file_pin(path, project_root))
    matrix = _passing_matrix()
    matrix_path = evidence_root / "p0-requirement-matrix.v1.json"
    _write_create_new(matrix_path, _plain_canonical_json(matrix))
    sidecars.append(_file_pin(matrix_path, project_root))

    restore_script = project_root / "scripts/restore_wiki_mysql_from_receipt.py"
    if not restore_script.is_file():
        raise RuntimeError("restore entrypoint is missing")
    compose_path = resolve_under(project_root, COMPOSE_PATH)
    receipt: dict[str, Any] = {
        "schema_version": schema_version,
        "status": "passed",
        "test_only": test_only,
        "receipt_id": receipt_id,
        "created_at": _utc_now(),
        "source_authority": {
            **authority,
            "container": source_container,
            "database": SOURCE_DATABASE,
            "mysql_server_version": version,
            "compose": _file_pin(compose_path, project_root),
        },
        "installed_snapshot": source_before["installed_snapshot"],
        "dump": {**dump_pin, "path": dump_path.relative_to(project_root).as_posix()},
        "sidecars": sidecars,
        "source_inventory_sha256": source_before["inventory_sha256"],
        "restored_inventory_sha256": restored["inventory_sha256"],
        "restore_entrypoint": _file_pin(restore_script, project_root),
        "restore_authorization": {
            "apply_flag": "--apply",
            "expected_sha_flag": "--expected-receipt-sha256",
            "target_container": restore_target_container or SOURCE_CONTAINER,
            "target_database": SOURCE_DATABASE,
            "confirmation": build_restore_confirmation(receipt_id),
        },
        "protected_state": protected_after,
    }
    receipt["receipt_sha256"] = hashlib.sha256(canonical_json_bytes(receipt)).hexdigest()
    receipt_name = {
        PASSING_RECEIPT_SCHEMA: "wiki_pre_import_rollback_receipt.v1.json",
        EMERGENCY_RECEIPT_SCHEMA: "wiki_emergency_rollback_receipt.v1.json",
        TEST_ONLY_RECEIPT_SCHEMA: "wiki_test_only_rollback_receipt.v1.json",
    }[schema_version]
    receipt_path = evidence_root / receipt_name
    _write_create_new(receipt_path, canonical_json_bytes(receipt, include_self_hash=True))
    if schema_version == PASSING_RECEIPT_SCHEMA:
        validate_passing_receipt(receipt_path, project_root=project_root)
    return {
        "status": "passed",
        "receipt_id": receipt_id,
        "receipt_path": receipt_path.relative_to(project_root).as_posix(),
        "receipt_file_sha256": _sha256(receipt_path),
        "dump_path": dump_path.relative_to(project_root).as_posix(),
        "dump_sha256": dump_pin["sha256"],
        "inventory_sha256": source_before["inventory_sha256"],
        "table_count": len(source_before["tables"]),
    }


def execute_production_restore(
    *,
    project_root: Path,
    receipt_path: Path,
) -> dict[str, Any]:
    """Execute the already-authorized restore path; callers must enforce CLI guards first."""
    project_root = Path(project_root).resolve()
    payload = validate_passing_receipt(receipt_path, project_root=project_root)
    script_path = project_root / "scripts/restore_wiki_mysql_from_receipt.py"
    _verify_pin(script_path, payload["restore_entrypoint"])
    current_authority = inspect_container(SOURCE_CONTAINER)
    expected_authority = payload.get("source_authority", {})
    if (
        current_authority["container_id"] != expected_authority.get("container_id")
        or current_authority["image_id"] != expected_authority.get("image_id")
        or expected_authority.get("database") != SOURCE_DATABASE
    ):
        raise RuntimeError("production restore authority no longer matches receipt")
    emergency_id = "emergency-" + time.strftime("%Y%m%d%H%M%S", time.gmtime())
    emergency = build_emergency_receipt(project_root, emergency_id)
    dump_path = resolve_under(project_root, payload["dump"]["path"])
    source_inventory_path = _find_sidecar(project_root, payload, "source_inventory.before.v1.json")
    expected_inventory = json.loads(source_inventory_path.read_text(encoding="utf-8"))
    failure_path = resolve_under(
        project_root,
        Path("eval/huiji_wiki_rollback/emergency")
        / emergency_id
        / "restore_apply_failure.v1.json",
    )
    ingress = _stop_wiki_ingress_8000(project_root)
    try:
        restored = _apply_receipt_database(
            target_container=SOURCE_CONTAINER,
            dump_path=dump_path,
            expected_inventory=expected_inventory,
            allow_empty_password=False,
        )
        runtime = _start_backend_8000_and_wait(project_root)
    except BaseException as exc:
        _write_failure(failure_path, payload["receipt_id"], exc)
        raise
    return {
        "status": "restored",
        "receipt_id": payload["receipt_id"],
        "inventory_sha256": expected_inventory["inventory_sha256"],
        "emergency_receipt": emergency["receipt_path"],
        "wiki_write_ingress": ingress,
        "backend_runtime": runtime,
    }


def run_test_only_apply_integration(
    *,
    project_root: Path,
    operation_id: str,
) -> dict[str, Any]:
    """Exercise emergency backup and apply against a process-owned isolated target."""
    project_root = Path(project_root).resolve()
    operation_id = validate_receipt_id(operation_id)
    formal_authority = inspect_container(SOURCE_CONTAINER)
    source = f"{APPLY_TEST_CONTAINER_PREFIX}{operation_id}-source"
    target = f"{APPLY_TEST_CONTAINER_PREFIX}{operation_id}-target"
    if _container_exists(source) or _container_exists(target):
        raise RuntimeError("owned apply authority already exists")
    result_path = resolve_under(
        project_root,
        Path("eval/huiji_wiki_rollback/test-only") / operation_id / "apply_verification.v1.json",
    )
    if result_path.exists():
        raise FileExistsError("test-only apply evidence already exists")
    source_receipt_id = validate_receipt_id(f"{operation_id}-source")
    emergency_id = validate_receipt_id(f"{operation_id}-emergency")
    started: list[str] = []
    try:
        for container in (source, target):
            _run(owned_apply_container_args(
                container_name=container,
                image_id=formal_authority["image_id"],
                operation_id=operation_id,
            ))
            started.append(container)
            _wait_mysql_ready(container)
            _OWNED_TEST_AUTHORITIES[container] = {
                "operation_id": operation_id,
                "image_id": formal_authority["image_id"],
            }
            _require_owned_test_authority(container, expected_image=formal_authority["image_id"])

        source_client = DockerMysqlClient(source, allow_empty_password=True)
        target_client = DockerMysqlClient(target, allow_empty_password=True)
        _initialize_test_fixture(source_client, marker="source")
        _initialize_test_fixture(target_client, marker="target")
        expected_inventory = collect_mysql_inventory(source_client, SOURCE_DATABASE)
        fixture_inventory = collect_mysql_inventory(target_client, SOURCE_DATABASE)
        source_receipt = build_test_only_emergency_receipt(
            project_root,
            source_receipt_id,
            source_container=source,
            restore_target_container=target,
        )
        source_receipt_path = resolve_under(project_root, source_receipt["receipt_path"])
        payload = validate_test_only_receipt(source_receipt_path, project_root=project_root)
        _require_owned_test_authority(target, expected_image=formal_authority["image_id"])
        emergency = build_test_only_emergency_receipt(
            project_root,
            emergency_id,
            source_container=target,
            restore_target_container=target,
        )
        test_receipt_path = resolve_under(project_root, emergency["receipt_path"])
        test_payload = json.loads(test_receipt_path.read_text(encoding="utf-8"))
        if test_payload.get("schema_version") != TEST_ONLY_RECEIPT_SCHEMA:
            raise RuntimeError("test-only emergency receipt schema mismatch")
        try:
            validate_passing_receipt(test_receipt_path, project_root=project_root)
        except ValueError:
            pass
        else:
            raise RuntimeError("test-only receipt passed formal receipt validation")

        expected_file_sha = _sha256(source_receipt_path)
        authorization = payload["restore_authorization"]
        if (
            expected_file_sha != source_receipt["receipt_file_sha256"]
            or authorization.get("target_database") != SOURCE_DATABASE
            or authorization.get("target_container") != target
            or authorization.get("confirmation")
            != build_restore_confirmation(source_receipt_id)
        ):
            raise RuntimeError("test-only apply authorization mismatch")
        dump_path = resolve_under(project_root, payload["dump"]["path"])
        restored = _apply_receipt_database(
            target_container=target,
            dump_path=dump_path,
            expected_inventory=expected_inventory,
            allow_empty_password=True,
        )
        result = {
            "schema_version": "huiji.wiki-rollback-test-apply-verification/v1",
            "status": "passed",
            "test_only": True,
            "operation_id": operation_id,
            "target": {
                "container": target,
                "image_id": formal_authority["image_id"],
                "network": "none",
                "published_ports": False,
            },
            "fixture_inventory_sha256": fixture_inventory["inventory_sha256"],
            "emergency_receipt": emergency["receipt_path"],
            "source_test_receipt": source_receipt["receipt_path"],
            "restored_inventory_sha256": restored["inventory_sha256"],
            "differences": [],
        }
        _write_create_new(result_path, _plain_canonical_json(result))
        return {
            "status": "passed",
            "test_only": True,
            "operation_id": operation_id,
            "evidence_path": result_path.relative_to(project_root).as_posix(),
            "evidence_sha256": _sha256(result_path),
            "restored_inventory_sha256": restored["inventory_sha256"],
        }
    finally:
        for container in (source, target):
            _OWNED_TEST_AUTHORITIES.pop(container, None)
        for container in reversed(started):
            _remove_owned_container(container)
        if _container_exists(source) or _container_exists(target):
            raise RuntimeError("owned apply authority cleanup failed")


def _initialize_test_fixture(client: DockerMysqlClient, *, marker: str) -> None:
    if marker not in {"source", "target"}:
        raise ValueError("invalid test fixture marker")
    marker_hex = marker.encode("utf-8").hex().upper()
    client.query_bytes(
        "CREATE DATABASE reverse1999_wiki CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
        "USE reverse1999_wiki;"
        "CREATE TABLE wiki_import_snapshots("
        "id BIGINT NOT NULL PRIMARY KEY,source_mode VARCHAR(32) NOT NULL,"
        "build_version VARCHAR(64) NOT NULL,artifact_schema_version VARCHAR(128) NOT NULL,"
        "manifest_sha256 CHAR(64) NOT NULL,snapshot_sha256 CHAR(64) NOT NULL"
        ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;"
        "INSERT INTO wiki_import_snapshots VALUES(1,'test-only','fixture',"
        "'huiji.test-only/v1',REPEAT('1',64),REPEAT('2',64));"
        "CREATE TABLE fixture_rows("
        "fixture_id BIGINT NOT NULL PRIMARY KEY,payload VARBINARY(64) NULL"
        ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;"
        f"INSERT INTO fixture_rows VALUES(1,UNHEX('{marker_hex}')), (2,NULL);"
    )


def _apply_receipt_database(
    *,
    target_container: str,
    dump_path: Path,
    expected_inventory: dict[str, Any],
    allow_empty_password: bool,
) -> dict[str, Any]:
    client = DockerMysqlClient(
        target_container,
        allow_empty_password=allow_empty_password,
    )
    client.query_bytes(
        "DROP DATABASE reverse1999_wiki;"
        "CREATE DATABASE reverse1999_wiki CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
    )
    _restore_dump(
        target_container,
        dump_path,
        source_password=not allow_empty_password,
    )
    restored = collect_mysql_inventory(client, SOURCE_DATABASE)
    differences = compare_inventories(expected_inventory, restored)
    if differences:
        raise RuntimeError(f"restore inventory verification failed: {differences[:5]}")
    return restored


def _require_owned_test_authority(
    container: str,
    *,
    expected_image: str | None = None,
) -> dict[str, Any]:
    registration = _OWNED_TEST_AUTHORITIES.get(container)
    if registration is None:
        raise ValueError("test-only authority was not created by this process")
    info = inspect_container(container)
    if expected_image is not None and info["image_id"] != expected_image:
        raise ValueError("test-only authority image mismatch")
    if info["image_id"] != registration["image_id"]:
        raise ValueError("test-only authority registration drift")
    labels = info.get("labels", {})
    if (
        info.get("network_mode") != "none"
        or any(info.get("ports", {}).values())
        or labels.get("com.reverse1999.wiki.rollback.test-only") != "true"
        or labels.get("com.reverse1999.wiki.rollback.operation")
        != registration["operation_id"]
    ):
        raise ValueError("test-only authority isolation mismatch")
    return info


def _stop_wiki_ingress_8000(project_root: Path) -> dict[str, Any]:
    if os.name != "nt":
        raise RuntimeError("production backend lifecycle is only implemented for this Windows authority")
    command = (
        "$c=Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue | "
        "Select-Object -First 1; if($null -eq $c){'null';exit 0};"
        "$p=Get-CimInstance Win32_Process -Filter ('ProcessId='+$c.OwningProcess);"
        "$p | Select-Object ProcessId,ExecutablePath,CommandLine | ConvertTo-Json -Compress"
    )
    raw = _run(["powershell", "-NoProfile", "-Command", command]).stdout.decode("utf-8").strip()
    if not raw or raw == "null":
        return {"status": "already_stopped", "port": 8000}
    process = json.loads(raw)
    command_line = str(process.get("CommandLine") or "")
    if "uvicorn" not in command_line or "backend.main:app" not in command_line:
        raise RuntimeError("port 8000 is not owned by the expected backend command")
    pid = int(process["ProcessId"])
    _run([
        "powershell", "-NoProfile", "-Command",
        f"Stop-Process -Id {pid} -Force -ErrorAction Stop; Wait-Process -Id {pid} -ErrorAction SilentlyContinue",
    ])
    return {"status": "stopped", "port": 8000, "previous_pid": pid}


def _start_backend_8000_and_wait(project_root: Path, timeout_seconds: float = 180.0) -> dict[str, Any]:
    runtime_root = resolve_under(project_root, "eval/huiji_wiki_rollback/runtime")
    runtime_root.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    stdout_path = runtime_root / f"backend-8000-{stamp}.stdout.log"
    stderr_path = runtime_root / f"backend-8000-{stamp}.stderr.log"
    creationflags = 0
    if os.name == "nt":
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
    with stdout_path.open("xb") as stdout_handle, stderr_path.open("xb") as stderr_handle:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "backend.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                "8000",
            ],
            cwd=project_root,
            stdout=stdout_handle,
            stderr=stderr_handle,
            stdin=subprocess.DEVNULL,
            creationflags=creationflags,
            start_new_session=os.name != "nt",
        )
    deadline = time.monotonic() + timeout_seconds
    health: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"backend restart exited with code {process.returncode}")
        try:
            with urllib.request.urlopen(
                "http://127.0.0.1:8000/api/wiki/health",
                timeout=3,
            ) as response:
                candidate = json.loads(response.read().decode("utf-8"))
            if candidate.get("ready") is True and int(candidate.get("pageCount", 0)) > 0:
                health = candidate
                break
        except (OSError, ValueError, json.JSONDecodeError):
            pass
        time.sleep(1.0)
    if health is None:
        raise TimeoutError("backend restart did not reach healthy Wiki state")
    return {
        "status": "healthy",
        "pid": process.pid,
        "health": health,
        "stdout": stdout_path.relative_to(project_root).as_posix(),
        "stderr": stderr_path.relative_to(project_root).as_posix(),
    }


def _write_dump_create_new(
    container: str,
    target: Path,
    *,
    allow_empty_password: bool = False,
) -> dict[str, Any]:
    if target.exists():
        raise FileExistsError(f"dump already exists: {target}")
    partial = target.with_suffix(target.suffix + ".partial")
    if partial.exists():
        raise FileExistsError(f"partial dump already exists: {partial}")
    options = mysqldump_args(SOURCE_DATABASE)
    password_setup = "" if allow_empty_password else (
        'if [ -z "${MYSQL_ROOT_PASSWORD:-}" ]; then exit 41; fi; '
        'export MYSQL_PWD="$MYSQL_ROOT_PASSWORD"; '
    )
    shell = password_setup + "exec mysqldump -uroot " + " ".join(options)
    try:
        with partial.open("xb") as handle:
            process = subprocess.Popen(
                ["docker", "exec", container, "sh", "-lc", shell],
                stdout=handle,
                stderr=subprocess.PIPE,
            )
            _, stderr = process.communicate()
            handle.flush()
            os.fsync(handle.fileno())
        if process.returncode != 0:
            raise RuntimeError(f"mysqldump failed with exit code {process.returncode}: {_safe_error(stderr)}")
        partial.replace(target)
    except BaseException:
        partial.unlink(missing_ok=True)
        raise
    return {"sha256": _sha256(target), "size": target.stat().st_size, "options": options}


def _restore_dump(container: str, dump_path: Path, *, source_password: bool = False) -> None:
    password_setup = (
        'if [ -z "${MYSQL_ROOT_PASSWORD:-}" ]; then exit 41; fi; '
        'export MYSQL_PWD="$MYSQL_ROOT_PASSWORD"; '
        if source_password else ""
    )
    shell = password_setup + (
        "exec mysql -uroot --default-character-set=utf8mb4 --binary-mode=1 " + SOURCE_DATABASE
    )
    with dump_path.open("rb") as handle:
        process = subprocess.Popen(
            ["docker", "exec", "-i", container, "sh", "-lc", shell],
            stdin=handle,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        _, stderr = process.communicate()
    if process.returncode != 0:
        raise RuntimeError(f"restore failed with exit code {process.returncode}: {_safe_error(stderr)}")


def _wait_mysql_ready(container: str, timeout_seconds: float = 90.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        result = subprocess.run(
            [
                "docker", "exec", container,
                "mysql", "-uroot", "--batch", "--skip-column-names",
                "-e", "SELECT @@port;",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip() == b"3306":
            return
        time.sleep(1.0)
    raise TimeoutError("temporary MySQL readiness timeout")


def _protected_state(project_root: Path, *, require_frozen: bool) -> dict[str, Any]:
    inputs: dict[str, Any] = {}
    for name, (relative, expected) in FROZEN_INPUTS.items():
        path = resolve_under(project_root, relative)
        actual = _sha256(path)
        if require_frozen and actual != expected:
            raise RuntimeError(f"frozen input drift: {name}")
        inputs[name] = {"path": relative, "sha256": actual, "size": path.stat().st_size}
    pointer = resolve_under(project_root, ACTIVE_POINTER)
    if require_frozen and pointer.exists():
        raise RuntimeError("active pointer must remain absent")
    return {
        "inputs": inputs,
        "active_pointer": {
            "path": ACTIVE_POINTER,
            "exists": pointer.exists(),
            "sha256": _sha256(pointer) if pointer.exists() else None,
        },
    }


def _passing_matrix() -> dict[str, Any]:
    groups = {
        "AUTH": 6,
        "DUMP": 4,
        "INVENTORY": 5,
        "RESTORE-VERIFY": 6,
        "RECEIPT": 6,
        "RESTORE-ENTRY": 6,
    }
    evidence_by_group = {
        "AUTH": [
            "restore_verification.v1.json",
            "eval/huiji_wiki_rollback/test-only/rollback-apply-0721d/apply_verification.v1.json",
        ],
        "DUMP": ["source_inventory.before.v1.json", "source_inventory.after.v1.json"],
        "INVENTORY": ["source_inventory.before.v1.json", "restored_inventory.v1.json"],
        "RESTORE-VERIFY": ["restore_verification.v1.json"],
        "RECEIPT": ["wiki_pre_import_rollback_receipt.v1.json"],
        "RESTORE-ENTRY": [
            "eval/huiji_wiki_rollback/test-only/rollback-apply-0721d/apply_verification.v1.json",
        ],
    }
    test_by_group = {
        "AUTH": "tests/test_huiji_wiki_mysql_rollback.py",
        "DUMP": "tests/test_huiji_wiki_mysql_rollback.py",
        "INVENTORY": "tests/test_huiji_wiki_mysql_inventory.py",
        "RESTORE-VERIFY": "tests/test_huiji_wiki_mysql_rollback.py",
        "RECEIPT": "tests/test_huiji_wiki_mysql_rollback.py",
        "RESTORE-ENTRY": "tests/test_huiji_wiki_mysql_rollback_scripts.py",
    }
    failure_by_group = {
        "AUTH": "authority, isolation, credential, or ownership mismatch blocks execution",
        "DUMP": "overwrite, dump failure, source drift, or pin mismatch blocks receipt",
        "INVENTORY": "missing PK/table/snapshot or canonical hash mismatch blocks receipt",
        "RESTORE-VERIFY": "image, readiness, DDL, row, data, cleanup, or inventory mismatch blocks receipt",
        "RECEIPT": "canonical bytes, internal hash, path, size, or sidecar pin mismatch rejects receipt",
        "RESTORE-ENTRY": "missing authorization, emergency backup, restore compare, restart, or health gate fails closed",
    }
    requirements = []
    for group, count in groups.items():
        for index in range(1, count + 1):
            requirements.append({
                "id": f"{group}-P0-{index:02d}",
                "status": "passed",
                "implementation": [
                    "src/huiji_wiki/mysql_inventory.py",
                    "src/huiji_wiki/mysql_rollback.py",
                ],
                "test": test_by_group[group],
                "evidence": evidence_by_group[group],
                "failure_condition": failure_by_group[group],
            })
    return {
        "schema_version": "huiji.wiki-rollback-p0-matrix/v1",
        "status": "passed",
        "expected_count": 33,
        "passed_count": len(requirements),
        "requirements": requirements,
    }


def _file_pin(path: Path, project_root: Path) -> dict[str, Any]:
    path = path.resolve()
    return {
        "path": path.relative_to(project_root.resolve()).as_posix(),
        "sha256": _sha256(path),
        "size": path.stat().st_size,
    }


def _find_sidecar(project_root: Path, payload: dict[str, Any], filename: str) -> Path:
    for pin in payload.get("sidecars", []):
        if Path(str(pin.get("path", ""))).name == filename:
            path = resolve_under(project_root, str(pin["path"]))
            _verify_pin(path, pin)
            return path
    raise ValueError(f"required receipt sidecar missing: {filename}")


def _verify_pin(path: Path, pin: dict[str, Any]) -> None:
    if not path.is_file() or path.stat().st_size != int(pin["size"]) or _sha256(path) != pin["sha256"]:
        raise ValueError(f"file pin mismatch: {pin.get('path')}")


def _plain_canonical_json(value: dict[str, Any]) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def _write_create_new(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def _write_failure(path: Path, receipt_id: str, error: BaseException) -> None:
    if path.exists():
        return
    payload = {
        "schema_version": FAILURE_SCHEMA,
        "status": "failed",
        "receipt_id": receipt_id,
        "error_type": type(error).__name__,
        "error": _safe_error(str(error).encode("utf-8")),
        "created_at": _utc_now(),
    }
    try:
        _write_create_new(path, _plain_canonical_json(payload))
    except OSError:
        pass


def _container_exists(name: str) -> bool:
    result = subprocess.run(
        ["docker", "inspect", name],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0


def _remove_owned_container(name: str) -> None:
    if not name.startswith((TEMP_CONTAINER_PREFIX, APPLY_TEST_CONTAINER_PREFIX)):
        raise ValueError("refusing to remove non-owned container")
    subprocess.run(
        ["docker", "rm", "--force", name],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )


def _run(args: list[str], *, input_bytes: bytes | None = None) -> subprocess.CompletedProcess[bytes]:
    result = subprocess.run(
        args,
        input=input_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"command failed ({args[0]} exit {result.returncode}): {_safe_error(result.stderr)}")
    return result


def _safe_error(value: bytes) -> str:
    text = value.decode("utf-8", errors="replace").strip()
    if len(text) > 500:
        text = text[:500] + "..."
    return text.replace("MYSQL_ROOT_PASSWORD", "[credential-env]")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
