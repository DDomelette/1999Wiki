from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Iterator

import yaml


class PathAuditPolicyError(ValueError):
    """Raised when the external-path allowlist is invalid or too broad."""


@dataclass(frozen=True)
class AllowlistEntry:
    entry_id: str
    file: str
    value: str
    category: str
    reason: str

    def to_json(self) -> dict[str, str]:
        return {
            "id": self.entry_id,
            "file": self.file,
            "value": self.value,
            "category": self.category,
            "reason": self.reason,
        }


_ALLOWED_CATEGORIES = {"system_executable", "diagnostic_sentinel"}
_TEXT_SUFFIXES = {
    ".bat",
    ".cmd",
    ".css",
    ".html",
    ".ini",
    ".js",
    ".json",
    ".jsx",
    ".md",
    ".ps1",
    ".py",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".yaml",
    ".yml",
}
_TEXT_NAMES = {".env.example", ".gitattributes", ".gitignore", "Dockerfile"}
_EXCLUDED_DIR_NAMES = {
    ".git",
    ".idea",
    ".local",
    ".pytest_cache",
    ".ruff_cache",
    ".superpowers",
    ".vscode",
    "__pycache__",
    "backups",
    "data",
    "dist",
    "node_modules",
    "playwright-report",
    "test-results",
    "tests",
    "vectorstore",
    "动效预选",
}
_EXCLUDED_PREFIXES = {
    "docs/huiji-crawler/plans": "historical_plan",
    "docs/huiji-crawler/specs": "historical_spec",
    "docs/superpowers/plans": "historical_plan",
    "docs/superpowers/specs": "historical_spec",
    "infra/milvus/volumes": "runtime_volume",
}
_EXCLUDED_EXACT = {
    ".env": "private_environment",
    "config/external-path-allowlist.yaml": "policy_input",
    "recovery-huiji-crawler-baseline.txt": "generated_recovery_evidence",
    "recovery-status-before.txt": "generated_recovery_evidence",
}
_STATIC_EXCLUDED_SCOPES = (
    (".env", "private_environment"),
    (".local", "private_runtime"),
    ("data", "runtime_data"),
    ("eval", "generated_evidence"),
    ("tests", "test_fixture"),
    ("backups", "backup"),
    ("vectorstore", "runtime_data"),
    ("frontend/react-app/dist", "generated_frontend"),
    ("frontend/react-app/node_modules", "dependency_tree"),
    ("kimi_web/dist", "generated_frontend"),
    ("kimi_web/node_modules", "dependency_tree"),
    ("infra/milvus/volumes", "runtime_volume"),
    ("docs/superpowers/specs", "historical_spec"),
    ("docs/superpowers/plans", "historical_plan"),
    ("docs/huiji-crawler/specs", "historical_spec"),
    ("docs/huiji-crawler/plans", "historical_plan"),
    ("config/external-path-allowlist.yaml", "policy_input"),
)

_DRIVE_PATH_RE = re.compile(
    r"(?i)(?<![A-Za-z0-9_:/])"
    r"([A-Z]:[\\/]+(?=[^\s\\/\"'`<>|,;])[^\t\r\n\"'`<>|,;]*)"
)
_UNC_PATH_RE = re.compile(
    r"(?<!\\)((?:\\\\){1,2}[A-Za-z0-9][A-Za-z0-9._-]*\\+"
    r"(?=[^\s\\\"'`<>|,;])[^\t\r\n\"'`<>|,;]+)"
)
_FILE_URL_RE = re.compile(
    r"(?i)\b(file://(?=[^\s\[\](){}^$*+?\\\"'`<>|,;])"
    r"[^\t\r\n\"'`<>|,;]+)"
)


def _normalized_relative(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _is_frontend_test_file(relative: str) -> bool:
    name = PurePosixPath(relative).name.lower()
    return ".test." in name or ".spec." in name


def _excluded_reason(
    relative: str,
    *,
    include_tests: bool,
    include_history: bool,
    include_eval: bool,
) -> str | None:
    if relative in _EXCLUDED_EXACT:
        return _EXCLUDED_EXACT[relative]
    parts = PurePosixPath(relative).parts
    if not include_eval and parts and parts[0] == "eval":
        return "generated_evidence"
    for part in parts:
        if part in _EXCLUDED_DIR_NAMES and not (part == "tests" and include_tests):
            return "excluded_directory"
    if not include_history:
        for prefix, reason in _EXCLUDED_PREFIXES.items():
            if relative == prefix or relative.startswith(prefix + "/"):
                return reason
    if not include_tests and _is_frontend_test_file(relative):
        return "test_fixture"
    if relative.endswith(".log"):
        return "generated_log"
    return None


def iter_project_text_files(
    project_root: Path,
    *,
    include_tests: bool = False,
    include_history: bool = False,
    include_eval: bool = False,
) -> Iterator[tuple[str, Path]]:
    root = Path(project_root).resolve(strict=True)
    for directory, dirnames, filenames in os.walk(root):
        directory_path = Path(directory)
        relative_directory = "" if directory_path == root else _normalized_relative(directory_path, root)
        kept_dirs: list[str] = []
        for dirname in sorted(dirnames):
            relative = f"{relative_directory}/{dirname}".strip("/")
            if include_eval and relative == "eval":
                kept_dirs.append(dirname)
                continue
            reason = _excluded_reason(
                relative,
                include_tests=include_tests,
                include_history=include_history,
                include_eval=include_eval,
            )
            if reason is None:
                kept_dirs.append(dirname)
        dirnames[:] = kept_dirs

        for filename in sorted(filenames):
            path = directory_path / filename
            relative = _normalized_relative(path, root)
            if _excluded_reason(
                relative,
                include_tests=include_tests,
                include_history=include_history,
                include_eval=include_eval,
            ) is not None:
                continue
            if path.suffix.lower() not in _TEXT_SUFFIXES and path.name not in _TEXT_NAMES:
                continue
            yield relative, path


def _load_allowlist(policy_path: Path) -> list[AllowlistEntry]:
    try:
        payload = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise PathAuditPolicyError(f"Cannot read path allowlist: {type(exc).__name__}") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != "external_path_allowlist.v1":
        raise PathAuditPolicyError("Path allowlist schema_version must be external_path_allowlist.v1")
    raw_entries = payload.get("entries")
    if not isinstance(raw_entries, list):
        raise PathAuditPolicyError("Path allowlist entries must be a list")

    entries: list[AllowlistEntry] = []
    seen_ids: set[str] = set()
    for raw in raw_entries:
        if not isinstance(raw, dict):
            raise PathAuditPolicyError("Every path allowlist entry must be an object")
        values = {key: str(raw.get(key, "")).strip() for key in ("id", "file", "value", "category", "reason")}
        if not all(values.values()):
            raise PathAuditPolicyError("Every path allowlist entry requires id, file, value, category and reason")
        if values["id"] in seen_ids:
            raise PathAuditPolicyError(f"Duplicate path allowlist id: {values['id']}")
        if values["category"] not in _ALLOWED_CATEGORIES:
            raise PathAuditPolicyError(f"Unsupported path allowlist category: {values['category']}")
        if any(character in values["file"] + values["value"] for character in "*?[]"):
            raise PathAuditPolicyError(f"Wildcards are forbidden in path allowlist entry: {values['id']}")
        file_path = PurePosixPath(values["file"].replace("\\", "/"))
        if file_path.is_absolute() or ".." in file_path.parts:
            raise PathAuditPolicyError(f"Allowlist file must be project-relative: {values['id']}")
        seen_ids.add(values["id"])
        entries.append(
            AllowlistEntry(
                entry_id=values["id"],
                file=file_path.as_posix(),
                value=values["value"],
                category=values["category"],
                reason=values["reason"],
            )
        )
    return entries


def _line_matches(text: str) -> list[tuple[int, int, str]]:
    matches: list[tuple[int, int, str]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        seen: set[tuple[int, str]] = set()
        for pattern in (_DRIVE_PATH_RE, _UNC_PATH_RE, _FILE_URL_RE):
            for match in pattern.finditer(line):
                value = match.group(1)
                key = (match.start(1), value)
                if key in seen:
                    continue
                seen.add(key)
                matches.append((line_number, match.start(1) + 1, value))
    return matches


def audit_external_paths(project_root: Path, policy_path: Path) -> dict[str, object]:
    root = Path(project_root).resolve(strict=True)
    policy = Path(policy_path).resolve(strict=True)
    entries = _load_allowlist(policy)
    by_key = {(entry.file, entry.value): entry for entry in entries}
    used_ids: set[str] = set()
    scanned_files: list[str] = []
    matches: list[dict[str, object]] = []

    for relative, path in iter_project_text_files(root):
        scanned_files.append(relative)
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        for line, column, value in _line_matches(text):
            entry = by_key.get((relative, value))
            if entry is None:
                category = "unclassified"
                allowlist_id = None
                reason = None
            else:
                category = entry.category
                allowlist_id = entry.entry_id
                reason = entry.reason
                used_ids.add(entry.entry_id)
            matches.append(
                {
                    "file": relative,
                    "line": line,
                    "column": column,
                    "value": value,
                    "category": category,
                    "allowlist_id": allowlist_id,
                    "reason": reason,
                }
            )

    matches.sort(key=lambda item: (str(item["file"]), int(item["line"]), int(item["column"]), str(item["value"])))
    stale_ids = sorted(entry.entry_id for entry in entries if entry.entry_id not in used_ids)
    return {
        "schema_version": "external_path_inventory.v1",
        "project_root": str(root),
        "scanned_files": sorted(scanned_files),
        "excluded_scopes": [
            {"path": path, "reason": reason}
            for path, reason in _STATIC_EXCLUDED_SCOPES
        ],
        "matches": matches,
        "allowlist_entries": [entry.to_json() for entry in entries],
        "unclassified_external_path_count": sum(
            1 for item in matches if item["category"] == "unclassified"
        ),
        "stale_allowlist_count": len(stale_ids),
        "stale_allowlist_ids": stale_ids,
    }
