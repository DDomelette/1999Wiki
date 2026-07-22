from __future__ import annotations

from pathlib import Path

from src.huijiwiki.cookies import CookieLoader
from src.runtime_path_audit import iter_project_text_files


_SENSITIVE_COOKIE_NAME_MARKERS = ("auth", "cf", "clearance", "password", "session", "token")
_MIN_NON_MARKED_SECRET_LENGTH = 12


def _is_sensitive_cookie(name: str, value: str) -> bool:
    lowered = name.casefold()
    return any(marker in lowered for marker in _SENSITIVE_COOKIE_NAME_MARKERS) or len(value) >= _MIN_NON_MARKED_SECRET_LENGTH


def audit_credential_secrecy(project_root: Path, credential_path: Path) -> dict[str, object]:
    root = Path(project_root).resolve(strict=True)
    credential = Path(credential_path).resolve(strict=True)
    loader = CookieLoader(credential)
    loader.load_cookies()
    cookie_values = loader.secret_values()
    sensitive = {
        name: value
        for name, value in cookie_values
        if value and _is_sensitive_cookie(name, value)
    }
    skipped_names = sorted({name for name, _ in cookie_values if name not in sensitive})
    scanned_files: list[str] = []
    violations: list[dict[str, object]] = []

    for relative, path in iter_project_text_files(
        root,
        include_tests=True,
        include_history=True,
        include_eval=True,
    ):
        if path.resolve(strict=False) == credential:
            continue
        scanned_files.append(relative)
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError):
            continue
        for line_number, line in enumerate(lines, start=1):
            for cookie_name, secret in sensitive.items():
                if secret in line:
                    violations.append(
                        {
                            "file": relative,
                            "line": line_number,
                            "cookie_name": cookie_name,
                        }
                    )

    violations.sort(key=lambda item: (str(item["file"]), int(item["line"]), str(item["cookie_name"])))
    return {
        "schema_version": "credential_secrecy_audit.v1",
        "scanned_files": sorted(scanned_files),
        "skipped_short_cookie_names": skipped_names,
        "violations": violations,
        "violation_count": len(violations),
    }
