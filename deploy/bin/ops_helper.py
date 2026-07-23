#!/usr/bin/env python3
"""Strict, non-evaluating helpers for the production operations scripts."""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import stat
import sys
import tempfile
from pathlib import Path
from typing import Iterable


KEY_RE = re.compile(r"[A-Z][A-Z0-9_]*")
RELEASE_RE = re.compile(r"sha-[0-9a-f]{7}")
GENERATION_RE = re.compile(r"gen-[0-9a-f]{24}")
PLACEHOLDER_RE = re.compile(r"\$\{[^}]*\}")
IMAGE_REPOSITORIES = {
    "BACKEND_IMAGE": "ghcr.io/ddomelette/1999wiki-backend",
    "FRONTEND_IMAGE": "ghcr.io/ddomelette/1999wiki-frontend",
}
RELEASE_KEYS = (
    "BACKEND_IMAGE",
    "FRONTEND_IMAGE",
    "BACKEND_PORT",
    "FRONTEND_PORT",
)
APP_REQUIRED = (
    "APP_ENV",
    "MILVUS_URI",
    "MILVUS_DB_NAME",
    "MILVUS_COLLECTION_NAME",
    "MINIO_ENDPOINT",
    "MINIO_ACCESS_KEY",
    "MINIO_SECRET_KEY",
    "MINIO_BUCKET",
    "MEDIA_PUBLIC_BASE_URL",
    "MYSQL_HOST",
    "MYSQL_PORT",
    "MYSQL_DATABASE",
    "MYSQL_USER",
    "MYSQL_PASSWORD",
    "DEEPSEEK_API_KEY",
    "SILICONFLOW_API_KEY",
    "HUIJI_PROCESSED_ROOT",
)
INFRA_REQUIRED = (
    "MYSQL_ROOT_PASSWORD",
    "MYSQL_USER",
    "MYSQL_PASSWORD",
    "MINIO_ROOT_USER",
    "MINIO_ROOT_PASSWORD",
)
CADDY_REQUIRED = ("SITE_ADDRESS", "MINIO_PROXY_UPSTREAM")
STATE_KEYS = (
    "STATE_VERSION",
    "GENERATION",
    "ACTIVE_SLOT",
    "ACTIVE_RELEASE",
    "ACTIVE_PROJECT",
    "ACTIVE_FRONTEND_PORT",
    "ACTIVE_RELEASE_SNAPSHOT",
    "ACTIVE_APP_SNAPSHOT",
    "ACTIVE_BACKEND_IMAGE",
    "ACTIVE_FRONTEND_IMAGE",
    "HAS_PREVIOUS",
    "PREVIOUS_SLOT",
    "PREVIOUS_RELEASE",
    "PREVIOUS_PROJECT",
    "PREVIOUS_FRONTEND_PORT",
    "PREVIOUS_RELEASE_SNAPSHOT",
    "PREVIOUS_APP_SNAPSHOT",
    "PREVIOUS_BACKEND_IMAGE",
    "PREVIOUS_FRONTEND_IMAGE",
    "PREVIOUS_FRAGMENT_BACKUP",
)
JOURNAL_KEYS = (
    "JOURNAL_VERSION",
    "GENERATION",
    "OPERATION",
    "PHASE",
    "OLD_FRAGMENT_BACKUP",
    "OLD_STATE_PRESENT",
    "OLD_STATE_BACKUP",
    "NEW_STATE_GENERATION",
)


class ControlError(ValueError):
    pass


def fail(message: str) -> None:
    raise ControlError(message)


def strict_env(path: Path) -> dict[str, str]:
    """Parse strict unquoted KEY=VALUE records without source/eval semantics."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        fail(f"cannot read environment file: {path}")
    if "\x00" in text:
        fail(f"environment file contains NUL: {path}")
    values: dict[str, str] = {}
    for line_number, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if raw != raw.strip() or "=" not in line or line.startswith("export "):
            fail(f"invalid environment syntax at {path}:{line_number}")
        key, value = line.split("=", 1)
        if KEY_RE.fullmatch(key) is None or key in values:
            fail(f"invalid or duplicate environment key at {path}:{line_number}")
        if value != value.strip():
            fail(f"environment value has surrounding whitespace at {path}:{line_number}")
        if value.startswith(("'", '"')) or value.endswith(("'", '"')):
            fail(f"quoted environment values are forbidden at {path}:{line_number}")
        if PLACEHOLDER_RE.search(value):
            fail(f"unresolved placeholder is forbidden at {path}:{line_number}")
        values[key] = value
    return values


def require_nonempty(values: dict[str, str], required: Iterable[str], label: str) -> None:
    missing = [key for key in required if not values.get(key)]
    if missing:
        fail(f"{label} has empty required variables: {','.join(missing)}")


def validate_release(path: Path, expected_release: str | None = None) -> dict[str, str]:
    values = strict_env(path)
    if set(values) != set(RELEASE_KEYS):
        fail("release metadata must contain exactly the four approved keys")
    require_nonempty(values, RELEASE_KEYS, "release metadata")
    tags: set[str] = set()
    for key, repository in IMAGE_REPOSITORIES.items():
        match = re.fullmatch(re.escape(repository) + r":(sha-[0-9a-f]{7})", values[key])
        if match is None:
            fail(f"{key} is not an approved immutable image")
        tags.add(match.group(1))
    if len(tags) != 1:
        fail("Backend and Frontend image tags must be identical")
    release = next(iter(tags))
    if expected_release is not None and release != expected_release:
        fail("release argument does not match paired image tags")
    for key in ("BACKEND_PORT", "FRONTEND_PORT"):
        value = values[key]
        if not value.isascii() or not value.isdecimal() or not 1024 <= int(value) <= 65535:
            fail(f"{key} is not a safe unprivileged port")
    if values["BACKEND_PORT"] == values["FRONTEND_PORT"]:
        fail("Backend and Frontend ports must differ")
    return values


def validate_app(path: Path) -> dict[str, str]:
    values = strict_env(path)
    require_nonempty(values, APP_REQUIRED, "APP_ENV_FILE")
    if values["APP_ENV"] != "production":
        fail("APP_ENV must be production")
    media_base = values["MEDIA_PUBLIC_BASE_URL"].rstrip("/")
    if media_base != "/media" and re.fullmatch(r"https://[^/?#]+(?:/[^?#]*)?", media_base) is None:
        fail("MEDIA_PUBLIC_BASE_URL must be /media or an HTTPS base")
    values["MEDIA_PUBLIC_BASE_URL"] = media_base
    return values


def validate_infra(path: Path) -> dict[str, str]:
    values = strict_env(path)
    require_nonempty(values, INFRA_REQUIRED, "INFRA_ENV_FILE")
    return values


def validate_caddy(path: Path) -> dict[str, str]:
    values = strict_env(path)
    require_nonempty(values, CADDY_REQUIRED, "CADDY_ENV_FILE")
    if re.fullmatch(r"127\.0\.0\.1:[0-9]{2,5}", values["MINIO_PROXY_UPSTREAM"]) is None:
        fail("MINIO_PROXY_UPSTREAM must use IPv4 loopback")
    return values


def resolved_file(path: Path) -> Path:
    try:
        resolved = path.resolve(strict=True)
    except OSError:
        fail(f"required file is missing: {path}")
    if not resolved.is_file():
        fail(f"required path is not a regular file: {resolved}")
    return resolved


def contained(root: Path, candidate: Path) -> Path:
    root = root.resolve(strict=True)
    candidate = candidate.resolve(strict=True)
    try:
        candidate.relative_to(root)
    except ValueError:
        fail(f"path escapes protected state root: {candidate}")
    return candidate


def validate_owner_mode(path: Path, *, exact_mode: int | None = None) -> os.stat_result:
    info = path.stat()
    mode = stat.S_IMODE(info.st_mode)
    if info.st_uid not in {0, os.geteuid()}:
        fail(f"path must be owned by root or current user: {path}")
    if exact_mode is not None and mode != exact_mode:
        fail(f"path must have mode {exact_mode:04o}: {path}")
    return info


def validate_protected_file(
    path: Path,
    *,
    repo_root: Path | None = None,
    require_outside_repo: bool = False,
) -> Path:
    resolved = resolved_file(path)
    if resolved.name.endswith(".example"):
        fail(f"checked examples are forbidden: {resolved}")
    if require_outside_repo and repo_root is not None:
        repo = repo_root.resolve(strict=True)
        try:
            resolved.relative_to(repo)
        except ValueError:
            pass
        else:
            fail(f"protected file must resolve outside the Git repository: {resolved}")
    validate_owner_mode(resolved, exact_mode=0o600)
    parent = resolved.parent
    parent_info = validate_owner_mode(parent)
    if stat.S_IMODE(parent_info.st_mode) & 0o022:
        fail(f"protected parent directory is group/other writable: {parent}")
    return resolved


def validate_state_root(path: Path) -> Path:
    try:
        resolved = path.resolve(strict=True)
    except OSError:
        fail(f"deployment state root is missing: {path}")
    if not resolved.is_dir():
        fail(f"deployment state root is not a directory: {resolved}")
    validate_owner_mode(resolved, exact_mode=0o700)
    return resolved


def fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def atomic_replace(
    target: Path,
    payload: bytes,
    *,
    mode: int,
    uid: int,
    gid: int,
) -> None:
    """Write, fsync, chmod/chown, and atomically replace within target directory."""
    parent = target.parent
    if not parent.is_dir():
        fail(f"atomic target parent is missing: {parent}")
    descriptor, temp_name = tempfile.mkstemp(prefix=f".{target.name}.", dir=parent)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(descriptor, "wb", closefd=True) as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
            os.fchmod(stream.fileno(), mode)
            if os.geteuid() == 0 or (uid, gid) != (os.geteuid(), os.getegid()):
                os.fchown(stream.fileno(), uid, gid)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, target)
        fsync_directory(parent)
    finally:
        try:
            temp_path.unlink()
        except FileNotFoundError:
            pass


def durable_unlink(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        return
    fsync_directory(path.parent)


def normalized_env(values: dict[str, str], order: Iterable[str] | None = None) -> bytes:
    keys = tuple(order) if order is not None else tuple(values)
    return ("".join(f"{key}={values[key]}\n" for key in keys)).encode("utf-8")


def ensure_snapshot_file(path: Path, payload: bytes) -> None:
    if path.exists():
        validate_owner_mode(path, exact_mode=0o600)
        if path.read_bytes() != payload:
            fail(f"immutable snapshot already exists with different content: {path}")
        return
    atomic_replace(path, payload, mode=0o600, uid=os.geteuid(), gid=os.getegid())


def snapshot(
    state_root: Path,
    release: str,
    slot: str,
    release_source: Path,
    app_source: Path,
    repo_root: Path,
) -> tuple[Path, Path, dict[str, str], dict[str, str]]:
    """Create immutable validated release/app snapshots under the operations lock."""
    state_root = validate_state_root(state_root)
    if RELEASE_RE.fullmatch(release) is None or slot not in {"blue", "green"}:
        fail("invalid release or slot")
    release_source = validate_protected_file(
        release_source, repo_root=repo_root, require_outside_repo=True
    )
    app_source = validate_protected_file(
        app_source, repo_root=repo_root, require_outside_repo=True
    )
    release_values = validate_release(release_source, release)
    app_values = validate_app(app_source)
    current = state_root
    for name in ("snapshots", release, slot):
        current = current / name
        if current.exists():
            if not current.is_dir():
                fail(f"snapshot parent is not a directory: {current}")
            validate_owner_mode(current, exact_mode=0o700)
        else:
            current.mkdir(mode=0o700)
            fsync_directory(current.parent)
    release_snapshot = current / "release.env"
    app_snapshot = current / "app.env"
    ensure_snapshot_file(
        release_snapshot,
        normalized_env(release_values, RELEASE_KEYS),
    )
    ensure_snapshot_file(app_snapshot, normalized_env(app_values))
    validate_release(release_snapshot, release)
    validate_app(app_snapshot)
    validate_owner_mode(release_snapshot, exact_mode=0o600)
    validate_owner_mode(app_snapshot, exact_mode=0o600)
    return release_snapshot, app_snapshot, release_values, app_values


def load_snapshot(
    state_root: Path,
    slot: str,
    release_snapshot: Path,
) -> tuple[Path, Path, str, dict[str, str], dict[str, str]]:
    state_root = validate_state_root(state_root)
    release_snapshot = contained(state_root, release_snapshot)
    if slot not in {"blue", "green"}:
        fail("invalid slot")
    relative = release_snapshot.relative_to(state_root)
    if (
        len(relative.parts) != 4
        or relative.parts[0] != "snapshots"
        or relative.parts[2] != slot
        or relative.parts[3] != "release.env"
    ):
        fail("release snapshot path does not match snapshots/<release>/<slot>/release.env")
    release = relative.parts[1]
    if RELEASE_RE.fullmatch(release) is None:
        fail("release snapshot path has an invalid release")
    app_snapshot = release_snapshot.with_name("app.env")
    contained(state_root, app_snapshot)
    validate_owner_mode(release_snapshot, exact_mode=0o600)
    validate_owner_mode(app_snapshot, exact_mode=0o600)
    release_values = validate_release(release_snapshot, release)
    app_values = validate_app(app_snapshot)
    return release_snapshot, app_snapshot, release, release_values, app_values


def emit_snapshot(values: tuple[Path, Path, str, dict[str, str], dict[str, str]]) -> None:
    release_snapshot, app_snapshot, release, release_values, app_values = values
    for value in (
        str(release_snapshot),
        str(app_snapshot),
        release,
        release_values["BACKEND_IMAGE"],
        release_values["FRONTEND_IMAGE"],
        release_values["BACKEND_PORT"],
        release_values["FRONTEND_PORT"],
        app_values["MEDIA_PUBLIC_BASE_URL"],
    ):
        print(value)


def fragment_metadata(path: Path, service_uid: int, service_gids: set[int]) -> tuple[int, int, int]:
    path = resolved_file(path)
    info = path.stat()
    mode = stat.S_IMODE(info.st_mode)
    if mode & 0o133:
        fail("active Caddy fragment has executable or group/other writable bits")
    readable = (
        (service_uid == info.st_uid and bool(mode & stat.S_IRUSR))
        or (info.st_gid in service_gids and bool(mode & stat.S_IRGRP))
        or bool(mode & stat.S_IROTH)
    )
    if not readable:
        fail("active Caddy fragment is unreadable by the Caddy service identity")
    return info.st_uid, info.st_gid, mode


def validate_fragment(path: Path, port: str) -> None:
    text = resolved_file(path).read_text(encoding="utf-8").strip()
    if text != f"reverse_proxy 127.0.0.1:{port}":
        fail("active Caddy fragment diverges from recorded Frontend port")


def validate_state(path: Path, state_root: Path) -> dict[str, str]:
    state_root = validate_state_root(state_root)
    path = contained(state_root, path)
    validate_owner_mode(path, exact_mode=0o600)
    values = strict_env(path)
    if set(values) != set(STATE_KEYS):
        fail("active state has missing or unexpected keys")
    if values["STATE_VERSION"] != "2":
        fail("active state version is unsupported")
    if GENERATION_RE.fullmatch(values["GENERATION"]) is None:
        fail("active state generation is invalid")

    def check_deployment(prefix: str) -> tuple[Path, Path, str, dict[str, str]]:
        slot = values[f"{prefix}_SLOT"]
        release = values[f"{prefix}_RELEASE"]
        project = values[f"{prefix}_PROJECT"]
        port = values[f"{prefix}_FRONTEND_PORT"]
        if slot not in {"blue", "green"} or project != f"1999wiki-{slot}":
            fail(f"{prefix.lower()} slot/project state is invalid")
        if RELEASE_RE.fullmatch(release) is None:
            fail(f"{prefix.lower()} release state is invalid")
        loaded = load_snapshot(
            state_root,
            slot,
            Path(values[f"{prefix}_RELEASE_SNAPSHOT"]),
        )
        release_snapshot, app_snapshot, loaded_release, release_values, _ = loaded
        if loaded_release != release or str(app_snapshot) != values[f"{prefix}_APP_SNAPSHOT"]:
            fail(f"{prefix.lower()} snapshot state diverges")
        if port != release_values["FRONTEND_PORT"]:
            fail(f"{prefix.lower()} Frontend port diverges from snapshot")
        if values[f"{prefix}_BACKEND_IMAGE"] != release_values["BACKEND_IMAGE"]:
            fail(f"{prefix.lower()} Backend image diverges from snapshot")
        if values[f"{prefix}_FRONTEND_IMAGE"] != release_values["FRONTEND_IMAGE"]:
            fail(f"{prefix.lower()} Frontend image diverges from snapshot")
        return release_snapshot, app_snapshot, release, release_values

    check_deployment("ACTIVE")
    if values["HAS_PREVIOUS"] == "1":
        check_deployment("PREVIOUS")
        backup = contained(state_root, Path(values["PREVIOUS_FRAGMENT_BACKUP"]))
        validate_fragment(backup, values["PREVIOUS_FRONTEND_PORT"])
        if values["PREVIOUS_SLOT"] == values["ACTIVE_SLOT"]:
            fail("active and previous slots must differ")
    elif values["HAS_PREVIOUS"] == "0":
        for key in STATE_KEYS:
            if key.startswith("PREVIOUS_") and values[key]:
                fail("state without previous deployment contains previous values")
    else:
        fail("HAS_PREVIOUS must be 0 or 1")
    return values


def validate_journal(path: Path, state_root: Path) -> dict[str, str]:
    state_root = validate_state_root(state_root)
    path = contained(state_root, path)
    validate_owner_mode(path, exact_mode=0o600)
    values = strict_env(path)
    if set(values) != set(JOURNAL_KEYS):
        fail("transaction journal has missing or unexpected keys")
    if values["JOURNAL_VERSION"] != "1":
        fail("transaction journal version is unsupported")
    generation = values["GENERATION"]
    if GENERATION_RE.fullmatch(generation) is None:
        fail("transaction generation is invalid")
    if values["OPERATION"] not in {"switch", "rollback"}:
        fail("transaction operation is invalid")
    if values["PHASE"] not in {"prepared", "traffic_installed", "state_committed"}:
        fail("transaction phase is invalid")
    old_fragment = contained(state_root, Path(values["OLD_FRAGMENT_BACKUP"]))
    if old_fragment.name != f"tx-{generation}-old-fragment.caddy":
        fail("transaction old fragment path is invalid")
    if values["OLD_STATE_PRESENT"] == "1":
        old_state = contained(state_root, Path(values["OLD_STATE_BACKUP"]))
        if old_state.name != f"tx-{generation}-old-state.env":
            fail("transaction old state path is invalid")
        validate_state(old_state, state_root)
    elif values["OLD_STATE_PRESENT"] == "0":
        if values["OLD_STATE_BACKUP"]:
            fail("transaction without old state has a backup path")
    else:
        fail("transaction OLD_STATE_PRESENT is invalid")
    if values["NEW_STATE_GENERATION"] != generation:
        fail("transaction new state generation is invalid")
    return values


def write_env_atomic(path: Path, values: dict[str, str], order: Iterable[str]) -> None:
    current = path.stat() if path.exists() else path.parent.stat()
    uid = current.st_uid
    gid = current.st_gid
    atomic_replace(path, normalized_env(values, order), mode=0o600, uid=uid, gid=gid)


def parse_json_rows(path: Path) -> list[dict[str, object]]:
    raw = path.read_text(encoding="utf-8").strip()
    try:
        payload = json.loads(raw)
        rows = payload if isinstance(payload, list) else [payload]
    except json.JSONDecodeError:
        rows = [json.loads(line) for line in raw.splitlines() if line.strip()]
    if not all(isinstance(row, dict) for row in rows):
        fail("Compose status is not a JSON object list")
    return rows  # type: ignore[return-value]


def validate_compose_status(
    path: Path,
    backend_image: str,
    frontend_image: str,
) -> None:
    rows = parse_json_rows(path)
    services = {str(row.get("Service")): row for row in rows if row.get("Service")}
    if set(services) != {"backend", "frontend"}:
        fail("candidate must have exactly Backend and Frontend services")
    expected = {"backend": backend_image, "frontend": frontend_image}
    for service, image in expected.items():
        row = services[service]
        if row.get("State") != "running" or row.get("Health") != "healthy":
            fail(f"{service} is not running and healthy")
        actual_image = str(row.get("Image") or "")
        if actual_image != image:
            fail(f"{service} image does not match the validated snapshot")


def validate_health(path: Path) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    expected = {
        "status": "ok",
        "vectorstore_loaded": True,
        "provenance_status": "pass",
        "llm_ready": True,
    }
    if any(payload.get(key) != value for key, value in expected.items()):
        fail("health response is not fully ready")


def command_snapshot(args: argparse.Namespace) -> None:
    result = snapshot(
        Path(args.state_root),
        args.release,
        args.slot,
        Path(args.release_source),
        Path(args.app_source),
        Path(args.repo_root),
    )
    release_snapshot, app_snapshot, release_values, app_values = result
    emit_snapshot((release_snapshot, app_snapshot, args.release, release_values, app_values))


def command_load_snapshot(args: argparse.Namespace) -> None:
    emit_snapshot(
        load_snapshot(Path(args.state_root), args.slot, Path(args.release_snapshot))
    )


def command_validate_env(args: argparse.Namespace) -> None:
    path = Path(args.path)
    validators = {
        "app": validate_app,
        "infra": validate_infra,
        "caddy": validate_caddy,
    }
    if args.kind == "release":
        validate_release(path, args.release)
    else:
        validators[args.kind](path)


def command_validate_protected(args: argparse.Namespace) -> None:
    validate_protected_file(
        Path(args.path),
        repo_root=Path(args.repo_root) if args.repo_root else None,
        require_outside_repo=args.outside_repo,
    )


def command_emit_release(args: argparse.Namespace) -> None:
    values = validate_release(Path(args.path), args.release)
    for key in RELEASE_KEYS:
        print(values[key])


def command_emit_caddy(args: argparse.Namespace) -> None:
    values = validate_caddy(Path(args.path))
    for key in CADDY_REQUIRED:
        print(values[key])


def command_emit_media_base(args: argparse.Namespace) -> None:
    print(validate_app(Path(args.path))["MEDIA_PUBLIC_BASE_URL"])


def command_fragment_metadata(args: argparse.Namespace) -> None:
    uid, gid, mode = fragment_metadata(
        Path(args.path),
        int(args.service_uid),
        {int(value) for value in args.service_gids.split(",") if value},
    )
    print(uid)
    print(gid)
    print(f"{mode:o}")


def command_atomic_copy(args: argparse.Namespace) -> None:
    source = resolved_file(Path(args.source))
    if args.preserve:
        info = source.stat()
        mode = stat.S_IMODE(info.st_mode)
        uid, gid = info.st_uid, info.st_gid
    else:
        mode, uid, gid = int(args.mode, 8), int(args.uid), int(args.gid)
    atomic_replace(Path(args.target), source.read_bytes(), mode=mode, uid=uid, gid=gid)


def command_atomic_stdin(args: argparse.Namespace) -> None:
    atomic_replace(
        Path(args.target),
        sys.stdin.buffer.read(),
        mode=int(args.mode, 8),
        uid=int(args.uid),
        gid=int(args.gid),
    )


def command_validate_state(args: argparse.Namespace) -> None:
    values = validate_state(Path(args.path), Path(args.state_root))
    if args.emit:
        for key in STATE_KEYS:
            print(values[key])


def command_validate_consistency(args: argparse.Namespace) -> None:
    values = validate_state(Path(args.state), Path(args.state_root))
    validate_fragment(Path(args.fragment), values["ACTIVE_FRONTEND_PORT"])


def command_validate_journal(args: argparse.Namespace) -> None:
    values = validate_journal(Path(args.path), Path(args.state_root))
    if args.emit:
        for key in JOURNAL_KEYS:
            print(values[key])


def command_mark_journal(args: argparse.Namespace) -> None:
    path = Path(args.path)
    values = validate_journal(path, Path(args.state_root))
    values["PHASE"] = args.phase
    write_env_atomic(path, values, JOURNAL_KEYS)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)

    env_parser = commands.add_parser("validate-env")
    env_parser.add_argument("kind", choices=("app", "infra", "caddy", "release"))
    env_parser.add_argument("path")
    env_parser.add_argument("--release")
    env_parser.set_defaults(handler=command_validate_env)

    protected_parser = commands.add_parser("validate-protected")
    protected_parser.add_argument("path")
    protected_parser.add_argument("--repo-root")
    protected_parser.add_argument("--outside-repo", action="store_true")
    protected_parser.set_defaults(handler=command_validate_protected)

    release_parser = commands.add_parser("emit-release")
    release_parser.add_argument("path")
    release_parser.add_argument("--release")
    release_parser.set_defaults(handler=command_emit_release)

    caddy_parser = commands.add_parser("emit-caddy")
    caddy_parser.add_argument("path")
    caddy_parser.set_defaults(handler=command_emit_caddy)

    media_parser = commands.add_parser("emit-media-base")
    media_parser.add_argument("path")
    media_parser.set_defaults(handler=command_emit_media_base)

    snapshot_parser = commands.add_parser("snapshot")
    snapshot_parser.add_argument("state_root")
    snapshot_parser.add_argument("release")
    snapshot_parser.add_argument("slot")
    snapshot_parser.add_argument("release_source")
    snapshot_parser.add_argument("app_source")
    snapshot_parser.add_argument("repo_root")
    snapshot_parser.set_defaults(handler=command_snapshot)

    load_parser = commands.add_parser("load-snapshot")
    load_parser.add_argument("state_root")
    load_parser.add_argument("slot")
    load_parser.add_argument("release_snapshot")
    load_parser.set_defaults(handler=command_load_snapshot)

    root_parser = commands.add_parser("validate-state-root")
    root_parser.add_argument("path")
    root_parser.set_defaults(handler=lambda args: validate_state_root(Path(args.path)))

    meta_parser = commands.add_parser("fragment-metadata")
    meta_parser.add_argument("path")
    meta_parser.add_argument("service_uid")
    meta_parser.add_argument("service_gids")
    meta_parser.set_defaults(handler=command_fragment_metadata)

    fragment_parser = commands.add_parser("validate-fragment")
    fragment_parser.add_argument("path")
    fragment_parser.add_argument("port")
    fragment_parser.set_defaults(
        handler=lambda args: validate_fragment(Path(args.path), args.port)
    )

    copy_parser = commands.add_parser("atomic-copy")
    copy_parser.add_argument("source")
    copy_parser.add_argument("target")
    copy_parser.add_argument("--preserve", action="store_true")
    copy_parser.add_argument("--mode", default="600")
    copy_parser.add_argument("--uid", default=str(os.geteuid()))
    copy_parser.add_argument("--gid", default=str(os.getegid()))
    copy_parser.set_defaults(handler=command_atomic_copy)

    stdin_parser = commands.add_parser("atomic-stdin")
    stdin_parser.add_argument("target")
    stdin_parser.add_argument("mode")
    stdin_parser.add_argument("uid")
    stdin_parser.add_argument("gid")
    stdin_parser.set_defaults(handler=command_atomic_stdin)

    unlink_parser = commands.add_parser("durable-unlink")
    unlink_parser.add_argument("path")
    unlink_parser.set_defaults(handler=lambda args: durable_unlink(Path(args.path)))

    generation_parser = commands.add_parser("generation")
    generation_parser.set_defaults(
        handler=lambda _args: print("gen-" + secrets.token_hex(12))
    )

    state_parser = commands.add_parser("validate-state")
    state_parser.add_argument("path")
    state_parser.add_argument("state_root")
    state_parser.add_argument("--emit", action="store_true")
    state_parser.set_defaults(handler=command_validate_state)

    consistency_parser = commands.add_parser("validate-consistency")
    consistency_parser.add_argument("state")
    consistency_parser.add_argument("fragment")
    consistency_parser.add_argument("state_root")
    consistency_parser.set_defaults(handler=command_validate_consistency)

    journal_parser = commands.add_parser("validate-journal")
    journal_parser.add_argument("path")
    journal_parser.add_argument("state_root")
    journal_parser.add_argument("--emit", action="store_true")
    journal_parser.set_defaults(handler=command_validate_journal)

    mark_parser = commands.add_parser("mark-journal")
    mark_parser.add_argument("path")
    mark_parser.add_argument("state_root")
    mark_parser.add_argument(
        "phase", choices=("prepared", "traffic_installed", "state_committed")
    )
    mark_parser.set_defaults(handler=command_mark_journal)

    compose_parser = commands.add_parser("validate-compose-status")
    compose_parser.add_argument("path")
    compose_parser.add_argument("backend_image")
    compose_parser.add_argument("frontend_image")
    compose_parser.set_defaults(
        handler=lambda args: validate_compose_status(
            Path(args.path), args.backend_image, args.frontend_image
        )
    )

    health_parser = commands.add_parser("validate-health")
    health_parser.add_argument("path")
    health_parser.set_defaults(handler=lambda args: validate_health(Path(args.path)))
    return parser


def main() -> int:
    try:
        args = build_parser().parse_args()
        args.handler(args)
    except (ControlError, OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(f"ops-helper: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
