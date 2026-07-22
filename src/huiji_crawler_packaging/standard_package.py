from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

from bootstrap.package_verify import MANIFEST_HASH_NAME, MANIFEST_NAME, verify_package
from src.huiji_crawler_tool.path_audit import audit_crawler_paths
from src.huijiwiki.credential_schema import CanonicalCredential

from .dependency_lock import WheelRecord, validate_lock


SOURCE_DATE_EPOCH = 1784505600
FIXED_TIMESTAMP = "2026-07-20T00:00:00Z"
ZIP_NAME = "huiji-crawler-windows-standard.zip"
_ALLOWED_ROLES = {
    "bootstrap",
    "config",
    "dependency_lock",
    "dependency_spec",
    "documentation",
    "launcher",
    "runtime_source",
    "supply_chain",
}
_FORBIDDEN_PARTS = {
    ".git",
    ".idea",
    ".local",
    ".venv",
    "__pycache__",
    "data",
    "dist",
    "eval",
    "infra",
    "node_modules",
    "tests",
    "vectorstore",
    "workspace",
}
_HIGH_RISK_SECRET_RE = re.compile(
    r"(?i)(?:authorization|cookie)\s*:\s*(?:bearer\s+)?[A-Za-z0-9._~+/=-]{16,}"
)
_MIN_LITERAL_SECRET_LENGTH = 8


class PackageBuildError(RuntimeError):
    """Raised when a standard crawler package fails a build gate."""


@dataclass(frozen=True)
class FilePolicyEntry:
    source: str
    destination: str
    role: str
    critical: bool


def _canonical_bytes(payload: object) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode(
        "utf-8"
    )


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_canonical_bytes(payload))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_relative(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value or any(char in value for char in "*?[]"):
        raise PackageBuildError(f"{label} must be an exact POSIX path without globs")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or path.as_posix() != value or re.match(r"^[A-Za-z]:", value):
        raise PackageBuildError(f"{label} must be a safe project-relative path")
    return value


def _forbidden_destination(relative: str) -> bool:
    path = PurePosixPath(relative)
    if relative == ".env" or relative.endswith(".pyc"):
        return True
    return any(part.casefold() in _FORBIDDEN_PARTS for part in path.parts)


def _contains_credential_value(text: str, *, cookie_name: str, value: str) -> bool:
    if not value:
        return False
    if len(value) >= _MIN_LITERAL_SECRET_LENGTH:
        return value in text
    name_pattern = re.escape(cookie_name)
    value_pattern = re.escape(value)
    contextual_patterns = (
        rf"(?is){name_pattern}\s*[=:]\s*['\"]?{value_pattern}(?:['\";,\s]|$)",
        rf"(?is)['\"]name['\"]\s*:\s*['\"]{name_pattern}['\"].{{0,256}}"
        rf"['\"]value['\"]\s*:\s*['\"]{value_pattern}['\"]",
        rf"(?is)['\"]value['\"]\s*:\s*['\"]{value_pattern}['\"].{{0,256}}"
        rf"['\"]name['\"]\s*:\s*['\"]{name_pattern}['\"]",
    )
    return any(re.search(pattern, text) is not None for pattern in contextual_patterns)


def load_file_policy(project_root: Path, policy_path: Path) -> tuple[FilePolicyEntry, ...]:
    root = Path(project_root).expanduser().resolve(strict=True)
    try:
        payload = yaml.safe_load(Path(policy_path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise PackageBuildError(f"Cannot read file policy ({type(exc).__name__})") from exc
    if not isinstance(payload, dict) or set(payload) != {"schema_version", "files"}:
        raise PackageBuildError("File policy top-level fields are invalid")
    if payload["schema_version"] != "huiji_crawler_files.v1" or not isinstance(payload["files"], list):
        raise PackageBuildError("File policy schema or files are invalid")
    entries: list[FilePolicyEntry] = []
    destinations: set[str] = set()
    destination_casefold: set[str] = set()
    sources: set[str] = set()
    for raw in payload["files"]:
        if not isinstance(raw, dict) or set(raw) != {"source", "destination", "role", "critical"}:
            raise PackageBuildError("File policy entry fields are invalid")
        source = _safe_relative(raw["source"], label="source")
        destination = _safe_relative(raw["destination"], label="destination")
        if raw["role"] not in _ALLOWED_ROLES or not isinstance(raw["critical"], bool):
            raise PackageBuildError("File policy role or critical flag is invalid")
        if source in sources:
            raise PackageBuildError(f"Duplicate file policy source: {source}")
        if destination in destinations or destination.casefold() in destination_casefold:
            raise PackageBuildError(f"Duplicate file policy destination: {destination}")
        if _forbidden_destination(destination):
            raise PackageBuildError(f"Forbidden package destination: {destination}")
        candidate = (root / Path(source)).resolve(strict=False)
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise PackageBuildError(f"File policy source escapes project root: {source}") from exc
        if not candidate.is_file():
            raise PackageBuildError(f"File policy source is missing: {source}")
        entries.append(FilePolicyEntry(source, destination, raw["role"], raw["critical"]))
        sources.add(source)
        destinations.add(destination)
        destination_casefold.add(destination.casefold())
    return tuple(sorted(entries, key=lambda item: item.destination.casefold()))


def materialize_staging(
    project_root: Path,
    policy: tuple[FilePolicyEntry, ...],
    stage_root: Path,
) -> dict[str, tuple[str, bool]]:
    root = Path(project_root).resolve(strict=True)
    stage = Path(stage_root).resolve(strict=False)
    if stage.exists():
        raise PackageBuildError(f"Staging root already exists: {stage.name}")
    stage.mkdir(parents=True)
    roles: dict[str, tuple[str, bool]] = {}
    for entry in policy:
        source = (root / Path(entry.source)).resolve(strict=True)
        try:
            source.relative_to(root)
        except ValueError as exc:
            raise PackageBuildError(f"File policy source escaped at copy time: {entry.source}") from exc
        destination = stage / Path(entry.destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        roles[entry.destination] = (entry.role, entry.critical)
    return roles


def scan_stage(
    stage_root: Path,
    *,
    secret_values: tuple[tuple[str, str], ...] = (),
) -> dict[str, object]:
    stage = Path(stage_root).resolve(strict=True)
    violations: list[dict[str, object]] = []
    scanned_files: list[str] = []
    for path in sorted((item for item in stage.rglob("*") if item.is_file()), key=lambda item: item.as_posix()):
        relative = path.relative_to(stage).as_posix()
        scanned_files.append(relative)
        if _forbidden_destination(relative):
            violations.append({"file": relative, "kind": "forbidden_path"})
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        if _HIGH_RISK_SECRET_RE.search(text):
            violations.append({"file": relative, "kind": "credential_structure"})
        for cookie_name, value in secret_values:
            if _contains_credential_value(text, cookie_name=cookie_name, value=value):
                violations.append(
                    {"file": relative, "kind": "credential_value", "cookie_name": cookie_name}
                )
    violations.sort(
        key=lambda item: (str(item["file"]), str(item["kind"]), str(item.get("cookie_name", "")))
    )
    return {
        "schema_version": "huiji_crawler_secret_scan.v1",
        "scanned_files": scanned_files,
        "violations": violations,
        "violation_count": len(violations),
    }


def _license_destination(record: WheelRecord, archive_name: str) -> str:
    path = PurePosixPath(archive_name)
    parts = list(path.parts)
    try:
        index = [part.casefold() for part in parts].index("licenses")
        tail = parts[index + 1 :]
    except ValueError:
        tail = [path.name]
    safe_tail = [part for part in tail if part not in {"", ".", ".."}]
    if not safe_tail:
        safe_tail = ["LICENSE.txt"]
    return PurePosixPath("THIRD_PARTY_LICENSES", record.name, *safe_tail).as_posix()


def generate_supply_chain_materials(
    stage_root: Path,
    records: tuple[WheelRecord, ...],
    *,
    source_tree_hash: str,
) -> dict[str, tuple[str, bool]]:
    stage = Path(stage_root).resolve(strict=True)
    roles: dict[str, tuple[str, bool]] = {}
    components: list[dict[str, object]] = []
    notices: list[dict[str, object]] = []
    for record in sorted(records, key=lambda item: item.name):
        license_destinations: list[str] = []
        with zipfile.ZipFile(record.path) as archive:
            for archive_name in record.license_files:
                destination = _license_destination(record, archive_name)
                if destination in roles:
                    raise PackageBuildError(f"Duplicate license destination: {destination}")
                output = stage / Path(destination)
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_bytes(archive.read(archive_name))
                roles[destination] = ("supply_chain", False)
                license_destinations.append(destination)
        if not license_destinations:
            destination = f"THIRD_PARTY_LICENSES/{record.name}/METADATA-LICENSE.txt"
            text = (record.license_expression or "License text was not included in the wheel metadata") + "\n"
            output = stage / Path(destination)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(text, encoding="utf-8", newline="\n")
            roles[destination] = ("supply_chain", False)
            license_destinations.append(destination)
        component: dict[str, object] = {
            "type": "library",
            "name": record.name,
            "version": record.version,
            "purl": f"pkg:pypi/{record.name}@{record.version}",
            "hashes": [{"alg": "SHA-256", "content": record.sha256}],
        }
        if record.license_expression:
            component["licenses"] = [{"expression": record.license_expression}]
        components.append(component)
        notices.append(
            {
                "name": record.name,
                "version": record.version,
                "wheel_sha256": record.sha256,
                "license_expression": record.license_expression,
                "license_files": sorted(license_destinations),
            }
        )
    serial = uuid.uuid5(uuid.NAMESPACE_URL, f"huiji-crawler:{source_tree_hash}")
    sbom = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "serialNumber": f"urn:uuid:{serial}",
        "version": 1,
        "metadata": {
            "timestamp": FIXED_TIMESTAMP,
            "component": {"type": "application", "name": "huiji-crawler", "version": "p1"},
        },
        "components": components,
    }
    notices_payload = {
        "schema_version": "huiji_crawler_third_party_notices.v1",
        "components": notices,
    }
    _write_json(stage / "sbom.cdx.json", sbom)
    _write_json(stage / "THIRD_PARTY_NOTICES.json", notices_payload)
    roles["sbom.cdx.json"] = ("supply_chain", False)
    roles["THIRD_PARTY_NOTICES.json"] = ("supply_chain", False)
    return roles


def generate_manifest(
    stage_root: Path,
    roles: dict[str, tuple[str, bool]],
) -> dict[str, object]:
    stage = Path(stage_root).resolve(strict=True)
    actual = {
        path.relative_to(stage).as_posix(): path
        for path in stage.rglob("*")
        if path.is_file() and path.name not in {MANIFEST_NAME, MANIFEST_HASH_NAME}
    }
    if set(actual) != set(roles):
        missing_roles = sorted(set(actual) - set(roles))
        missing_files = sorted(set(roles) - set(actual))
        detail = (missing_roles or missing_files or ["unknown"])[0]
        raise PackageBuildError(f"Manifest role coverage mismatch: {detail}")
    files = []
    for relative in sorted(actual, key=str.casefold):
        role, critical = roles[relative]
        path = actual[relative]
        files.append(
            {
                "path": relative,
                "role": role,
                "critical": critical,
                "size": path.stat().st_size,
                "sha256": _sha256(path),
            }
        )
    manifest = {
        "schema_version": "huiji_crawler_package_manifest.v1",
        "target": {"os": "windows", "arch": "x64", "python": ">=3.12.0,<3.13"},
        "mutable_prefixes": [".local/", ".venv/", "workspace/"],
        "files": files,
    }
    encoded = _canonical_bytes(manifest)
    (stage / MANIFEST_NAME).write_bytes(encoded)
    (stage / MANIFEST_HASH_NAME).write_text(
        hashlib.sha256(encoded).hexdigest() + f"  {MANIFEST_NAME}\n",
        encoding="ascii",
        newline="\n",
    )
    return manifest


def create_deterministic_zip(stage_root: Path, output: Path) -> None:
    stage = Path(stage_root).resolve(strict=True)
    destination = Path(output).resolve(strict=False)
    destination.parent.mkdir(parents=True, exist_ok=True)
    files = sorted((path for path in stage.rglob("*") if path.is_file()), key=lambda item: item.relative_to(stage).as_posix())
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in files:
            relative = path.relative_to(stage).as_posix()
            info = zipfile.ZipInfo(relative, date_time=(2026, 7, 20, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = (0o100644 & 0xFFFF) << 16
            info.flag_bits |= 0x800
            archive.writestr(info, path.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)


def evaluate_size(
    zip_size: int,
    *,
    reference_mib: int = 10,
    hard_mib: int = 50,
) -> dict[str, object]:
    hard_bytes = hard_mib * 1024 * 1024
    if zip_size > hard_bytes:
        raise PackageBuildError(f"Standard ZIP exceeds the {hard_mib} MiB hard cap")
    status = "warning" if zip_size > reference_mib * 1024 * 1024 else "ok"
    return {
        "schema_version": "huiji_crawler_package_size.v1",
        "status": status,
        "zip_size": zip_size,
        "reference_mib": reference_mib,
        "hard_mib": hard_mib,
    }


def _source_tree_hash(project_root: Path, policy: tuple[FilePolicyEntry, ...]) -> str:
    digest = hashlib.sha256()
    for entry in policy:
        digest.update(entry.destination.encode("utf-8"))
        digest.update(b"\0")
        digest.update((project_root / Path(entry.source)).read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _load_size_policy(path: Path) -> tuple[int, int, str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PackageBuildError("Cannot read size policy") from exc
    if (
        not isinstance(payload, dict)
        or payload.get("schema_version") != "huiji_crawler_size_policy.v1"
        or not isinstance(payload.get("reference_zip_mib"), int)
        or not isinstance(payload.get("hard_zip_mib"), int)
    ):
        raise PackageBuildError("Size policy is invalid")
    return payload["reference_zip_mib"], payload["hard_zip_mib"], _sha256(path)


def build_standard_package(
    *,
    project_root: Path,
    policy_path: Path,
    lock_path: Path,
    wheelhouse: Path,
    output_dir: Path,
    evidence_dir: Path,
) -> dict[str, object]:
    root = Path(project_root).resolve(strict=True)
    policy_file = Path(policy_path).resolve(strict=True)
    lock_file = Path(lock_path).resolve(strict=True)
    output = Path(output_dir).resolve(strict=False)
    evidence = Path(evidence_dir).resolve(strict=False)
    for candidate, label in ((output, "output"), (evidence, "evidence")):
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise PackageBuildError(f"{label} must resolve inside the project root") from exc
    if evidence.exists():
        raise PackageBuildError("Evidence directory already exists")
    output.mkdir(parents=True, exist_ok=True)
    release_zip = output / ZIP_NAME
    release_size = output / "package-size.v1.json"
    release_hash = output / f"{ZIP_NAME}.sha256"
    release_receipt = output / "build-receipt.v1.json"
    if any(path.exists() for path in (release_zip, release_size, release_hash, release_receipt)):
        raise PackageBuildError("Release artifact already exists")
    evidence.mkdir(parents=True)
    stage = evidence / "staging"
    policy = load_file_policy(root, policy_file)
    requirements_input = root / "packaging" / "huiji-crawler" / "requirements-crawler.in"
    dependency_lock = validate_lock(lock_file, requirements_input, wheelhouse)
    roles = materialize_staging(root, policy, stage)
    source_hash = _source_tree_hash(root, policy)

    path_report = audit_crawler_paths(
        stage,
        stage / "config" / "external-path-allowlist.yaml",
        mode="stage",
    )
    _write_json(evidence / "path-audit-stage.v1.json", path_report)
    if path_report["status"] != "passed":
        raise PackageBuildError("Staging path audit failed")

    canonical_credential = root / ".local" / "accounts" / "default" / "credential.json"
    secret_values: tuple[tuple[str, str], ...] = ()
    if canonical_credential.is_file():
        secret_values = CanonicalCredential.from_bytes(canonical_credential.read_bytes()).secret_values()
    roles.update(generate_supply_chain_materials(stage, dependency_lock.records, source_tree_hash=source_hash))
    secret_report = scan_stage(stage, secret_values=secret_values)
    _write_json(evidence / "secret-scan-stage.v1.json", secret_report)
    if secret_report["violation_count"]:
        raise PackageBuildError("Staging secret scan failed")

    manifest = generate_manifest(stage, roles)
    verify_report = verify_package(stage)
    _write_json(evidence / "package-verification-stage.v1.json", verify_report)

    size_policy_path = root / "packaging" / "huiji-crawler" / "size-policy.v1.json"
    reference_mib, hard_mib, size_policy_hash = _load_size_policy(size_policy_path)
    temporary_zip = output / f".{ZIP_NAME}.tmp"
    temporary_size = output / ".package-size.v1.json.tmp"
    temporary_hash = output / f".{ZIP_NAME}.sha256.tmp"
    temporary_receipt = output / ".build-receipt.v1.json.tmp"
    for path in (temporary_zip, temporary_size, temporary_hash, temporary_receipt):
        path.unlink(missing_ok=True)
    try:
        create_deterministic_zip(stage, temporary_zip)
        size_report = evaluate_size(
            temporary_zip.stat().st_size,
            reference_mib=reference_mib,
            hard_mib=hard_mib,
        )
        extracted = evidence / "verified-extract"
        with zipfile.ZipFile(temporary_zip) as archive:
            archive.extractall(extracted)
        extracted_verify = verify_package(extracted)
        _write_json(evidence / "package-verification-extract.v1.json", extracted_verify)
        zip_hash = _sha256(temporary_zip)
        size_report["uncompressed_size"] = sum(
            path.stat().st_size for path in stage.rglob("*") if path.is_file()
        )
        receipt = {
            "schema_version": "huiji_crawler_build_receipt.v1",
            "source_date_epoch": SOURCE_DATE_EPOCH,
            "builder_version": 1,
            "source_tree_sha256": source_hash,
            "file_policy_sha256": _sha256(policy_file),
            "requirements_lock_sha256": _sha256(lock_file),
            "size_policy_sha256": size_policy_hash,
            "manifest_sha256": _sha256(stage / MANIFEST_NAME),
            "sbom_sha256": _sha256(stage / "sbom.cdx.json"),
            "zip_sha256": zip_hash,
        }
        _write_json(evidence / "build-receipt.v1.json", receipt)
        _write_json(temporary_size, size_report)
        temporary_hash.write_text(
            f"{zip_hash}  {ZIP_NAME}\n",
            encoding="ascii",
            newline="\n",
        )
        _write_json(temporary_receipt, receipt)
        os.replace(temporary_size, release_size)
        os.replace(temporary_hash, release_hash)
        os.replace(temporary_receipt, release_receipt)
        os.replace(temporary_zip, release_zip)
    finally:
        for path in (temporary_zip, temporary_size, temporary_hash, temporary_receipt):
            path.unlink(missing_ok=True)
    return {
        "schema_version": "huiji_crawler_build_result.v1",
        "status": "passed",
        "zip": str(release_zip),
        "zip_sha256": zip_hash,
        "manifest_file_count": len(manifest["files"]),
    }
