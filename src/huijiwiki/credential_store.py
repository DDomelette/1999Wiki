from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .credential_schema import CREDENTIAL_SCHEMA_VERSION, CanonicalCredential
from .errors import CredentialValidationError
from .legacy_credentials import decode_legacy_credential


class CredentialConflictError(RuntimeError):
    """Raised when an existing target differs and replacement was not authorized."""


@dataclass(frozen=True)
class CookieExpiryInspection:
    name: str
    domain: str
    path: str
    expires: int | None

    def to_json(self) -> dict[str, object]:
        return {
            "name": self.name,
            "domain": self.domain,
            "path": self.path,
            "expires": self.expires,
        }


@dataclass(frozen=True)
class CredentialInspection:
    path: Path
    size: int
    sha256: str
    cookie_names: tuple[str, ...]
    cookie_expiries: tuple[CookieExpiryInspection, ...]
    expected_user: str
    schema_version: str = CREDENTIAL_SCHEMA_VERSION

    def to_json(self) -> dict[str, object]:
        return {
            "path": str(self.path),
            "size": self.size,
            "sha256": self.sha256,
            "schema_version": self.schema_version,
            "expected_user": self.expected_user,
            "cookie_names": list(self.cookie_names),
            "cookie_expiries": [item.to_json() for item in self.cookie_expiries],
        }


@dataclass(frozen=True)
class LegacySourceInspection:
    path: Path
    size: int
    sha256: str
    mtime_ns: int
    cookie_names: tuple[str, ...]

    def to_json(self) -> dict[str, object]:
        return {
            "path": str(self.path),
            "size": self.size,
            "sha256": self.sha256,
            "mtime_ns": self.mtime_ns,
            "cookie_names": list(self.cookie_names),
        }


def _inspect_payload(payload: bytes, path: Path) -> CredentialInspection:
    try:
        credential = CanonicalCredential.from_bytes(payload)
    except CredentialValidationError:
        raise
    except Exception as exc:
        raise CredentialValidationError(
            f"Credential file is not parseable: {path.name} ({type(exc).__name__})"
        ) from exc
    return CredentialInspection(
        path=path,
        size=len(payload),
        sha256=hashlib.sha256(payload).hexdigest(),
        cookie_names=credential.cookie_names,
        cookie_expiries=tuple(
            CookieExpiryInspection(
                name=cookie.name,
                domain=cookie.domain,
                path=cookie.path,
                expires=cookie.expires,
            )
            for cookie in credential.cookies
        ),
        expected_user=credential.expected_user,
    )


def _read_and_inspect(path: Path) -> tuple[bytes, CredentialInspection]:
    resolved = Path(path).expanduser().resolve(strict=False)
    try:
        payload = resolved.read_bytes()
    except OSError as exc:
        raise CredentialValidationError(
            f"Credential file cannot be read: {resolved.name} ({type(exc).__name__})"
        ) from exc
    return payload, _inspect_payload(payload, resolved)


def inspect_credential(path: Path) -> CredentialInspection:
    return _read_and_inspect(path)[1]


def canonical_json(payload: dict[str, object]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"


def atomic_write_canonical_json(path: Path, payload: dict[str, object]) -> None:
    resolved = Path(path).expanduser().resolve(strict=False)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            prefix=f".{resolved.name}.",
            suffix=".tmp",
            dir=resolved.parent,
            delete=False,
        ) as temporary:
            temporary.write(canonical_json(payload))
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = Path(temporary.name)
        os.replace(temporary_path, resolved)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def atomic_write_validated_credential(
    target: Path,
    payload: bytes,
    *,
    replace: bool,
) -> CredentialInspection:
    resolved_target = Path(target).expanduser().resolve(strict=False)
    expected = _inspect_payload(payload, resolved_target)
    if resolved_target.exists():
        try:
            existing = inspect_credential(resolved_target)
        except CredentialValidationError as exc:
            if not replace:
                raise CredentialConflictError(
                    f"Credential target exists but is not a valid v2 credential: {resolved_target.name}"
                ) from exc
        else:
            if existing.sha256 == expected.sha256:
                return existing
            if not replace:
                raise CredentialConflictError(
                    f"Credential target already exists with different content: {resolved_target.name}"
                )

    resolved_target.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=f".{resolved_target.name}.",
            suffix=".tmp",
            dir=resolved_target.parent,
            delete=False,
        ) as temporary:
            temporary.write(payload)
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = Path(temporary.name)

        temporary_inspection = inspect_credential(temporary_path)
        if (
            temporary_inspection.sha256 != expected.sha256
            or temporary_inspection.size != expected.size
            or temporary_inspection.cookie_names != expected.cookie_names
            or temporary_inspection.expected_user != expected.expected_user
        ):
            raise CredentialValidationError("Temporary credential verification failed")

        os.replace(temporary_path, resolved_target)
        temporary_path = None
        installed = inspect_credential(resolved_target)
        if (
            installed.sha256 != expected.sha256
            or installed.size != expected.size
            or installed.cookie_names != expected.cookie_names
            or installed.expected_user != expected.expected_user
        ):
            raise CredentialValidationError("Installed credential verification failed")
        return installed
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _read_legacy_source(
    source: Path,
    *,
    expected_user: str,
) -> tuple[bytes, CanonicalCredential, LegacySourceInspection]:
    try:
        resolved = Path(source).expanduser().resolve(strict=True)
        before = resolved.stat()
        payload = resolved.read_bytes()
    except OSError as exc:
        raise CredentialValidationError(
            f"Legacy credential source cannot be read ({type(exc).__name__})"
        ) from exc
    credential = decode_legacy_credential(payload, expected_user=expected_user)
    return (
        payload,
        credential,
        LegacySourceInspection(
            path=resolved,
            size=len(payload),
            sha256=hashlib.sha256(payload).hexdigest(),
            mtime_ns=before.st_mtime_ns,
            cookie_names=credential.cookie_names,
        ),
    )


def _verify_source_unchanged(source: LegacySourceInspection) -> None:
    try:
        stat = source.path.stat()
        payload = source.path.read_bytes()
    except OSError as exc:
        raise CredentialValidationError("Legacy credential source changed during import") from exc
    if (
        stat.st_size != source.size
        or stat.st_mtime_ns != source.mtime_ns
        or hashlib.sha256(payload).hexdigest() != source.sha256
    ):
        raise CredentialValidationError("Legacy credential source changed during import")


def import_legacy_credential(
    source: Path,
    target: Path,
    *,
    expected_user: str,
    replace: bool = False,
) -> dict[str, object]:
    _, credential, source_inspection = _read_legacy_source(
        source,
        expected_user=expected_user,
    )
    canonical_payload = credential.to_bytes()
    resolved_target = Path(target).expanduser().resolve(strict=False)
    status = "imported"
    if resolved_target.exists():
        try:
            target_before = inspect_credential(resolved_target)
        except CredentialValidationError as exc:
            if not replace:
                raise CredentialConflictError(
                    f"Credential target exists but is not a valid v2 credential: {resolved_target.name}"
                ) from exc
        else:
            expected_hash = hashlib.sha256(canonical_payload).hexdigest()
            if target_before.sha256 == expected_hash:
                _verify_source_unchanged(source_inspection)
                return {
                    "schema_version": "huiji_credential_import.v2",
                    "status": "already_same_canonical",
                    "source": source_inspection.to_json(),
                    "target": target_before.to_json(),
                }
            if not replace:
                raise CredentialConflictError(
                    f"Credential target already exists with different content: {resolved_target.name}"
                )
        status = "replaced"

    _verify_source_unchanged(source_inspection)
    target_inspection = atomic_write_validated_credential(
        resolved_target,
        canonical_payload,
        replace=replace,
    )
    _verify_source_unchanged(source_inspection)
    return {
        "schema_version": "huiji_credential_import.v2",
        "status": status,
        "source": source_inspection.to_json(),
        "target": target_inspection.to_json(),
    }


def import_credential(
    source: Path,
    target: Path,
    *,
    replace: bool = False,
    expected_user: str = "POTATO BOT",
) -> dict[str, object]:
    """Compatibility alias for the explicit legacy import workflow."""
    return import_legacy_credential(
        source,
        target,
        expected_user=expected_user,
        replace=replace,
    )
