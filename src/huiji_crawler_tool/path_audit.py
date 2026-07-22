from __future__ import annotations

import ast
import json
import os
import re
import shutil
import subprocess
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

import yaml
from yaml.nodes import MappingNode, Node, ScalarNode, SequenceNode


class PathAuditError(ValueError):
    """Raised when a structured crawler path audit cannot be configured."""


class PathAuditPolicyError(PathAuditError):
    """Raised when the external path allowlist is invalid or too broad."""


_ALLOWED_CATEGORIES = {"system_executable", "diagnostic_sentinel"}
_SUPPORTED_SUFFIXES = {".py", ".ps1", ".yaml", ".yml", ".json", ".cmd", ".bat"}
_MUTABLE_PREFIXES = {".local", ".venv", "workspace"}
_PATH_KEY_WORDS = {
    "config",
    "credential",
    "dir",
    "directory",
    "executable",
    "file",
    "folder",
    "out",
    "output",
    "path",
    "paths",
    "profile",
    "root",
    "source",
    "target",
}
_DRIVE_SEARCH = re.compile(r"(?i)(?<![A-Za-z0-9_:/])([A-Z]:[\\/]+[^\t\r\n\"'`<>|,;\)\]}]+)")
_UNC_SEARCH = re.compile(r"(?<!\\)(\\\\[^\s\\\"'`<>|,;]+\\+[^\t\r\n\"'`<>|,;\)\]}]+)")
_FILE_URL_SEARCH = re.compile(r"(?i)\b(file://[^\s\"'`<>|,;\)\]}]+)")


@dataclass(frozen=True)
class AllowlistEntry:
    entry_id: str
    file: str
    value: str
    category: str
    reason: str


@dataclass(frozen=True)
class LocatedValue:
    parser: str
    line: int
    column: int
    value: str


def _is_path_key(value: object) -> bool:
    if not isinstance(value, str):
        return False
    words = {word for word in re.split(r"[^a-z0-9]+", value.casefold()) if word}
    return bool(words & _PATH_KEY_WORDS)


def _trim_path(value: str) -> str:
    return value.rstrip(" .")


def _extract_external_paths(value: str) -> list[tuple[int, str]]:
    text = value.strip()
    if not text or text.casefold().startswith(("http://", "https://")):
        return []
    leading_offset = len(value) - len(value.lstrip())
    if re.match(r"(?i)^[A-Z]:[\\/]+[^\\/]", text):
        return [(leading_offset, _trim_path(text))]
    if re.match(r"^\\\\[^\\]+\\+[^\\]+", text):
        return [(leading_offset, _trim_path(text))]
    if text.casefold().startswith("file://") and len(text) > len("file://"):
        return [(leading_offset, _trim_path(text))]
    results: list[tuple[int, str]] = []
    seen: set[tuple[int, str]] = set()
    for pattern in (_FILE_URL_SEARCH, _UNC_SEARCH, _DRIVE_SEARCH):
        for match in pattern.finditer(value):
            candidate = _trim_path(match.group(1))
            if re.fullmatch(r"(?i)[A-Z]:[\\/]+", candidate):
                continue
            if candidate.casefold().startswith(("http://", "https://")):
                continue
            key = (match.start(1), candidate)
            if key not in seen:
                seen.add(key)
                results.append(key)
    return sorted(results, key=lambda item: (item[0], item[1]))


def _python_ignored_string_nodes(tree: ast.AST) -> set[int]:
    ignored: set[int] = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if isinstance(body, list) and body:
            first = body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
                ignored.add(id(first.value))
        if isinstance(node, ast.Call) and node.args:
            function_name = ""
            if isinstance(node.func, ast.Name):
                function_name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                function_name = node.func.attr
            if function_name in {"compile", "findall", "finditer", "fullmatch", "match", "search", "split", "sub", "subn"}:
                pattern = node.args[0]
                if isinstance(pattern, ast.Constant) and isinstance(pattern.value, str):
                    ignored.add(id(pattern))
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            value = node.value
            names = [target.id.casefold() for target in targets if isinstance(target, ast.Name)]
            if any("regex" in name or "pattern" in name for name in names):
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    ignored.add(id(value))
    return ignored


def _parse_python(path: Path) -> list[LocatedValue]:
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text, filename=str(path))
    ignored_strings = _python_ignored_string_nodes(tree)
    values: list[LocatedValue] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str) or id(node) in ignored_strings:
            continue
        for offset, candidate in _extract_external_paths(node.value):
            values.append(
                LocatedValue(
                    parser="python_ast",
                    line=int(getattr(node, "lineno", 1)),
                    column=int(getattr(node, "col_offset", 0)) + 1 + offset,
                    value=candidate,
                )
            )
    return values


def _walk_yaml_node(node: Node, *, semantic: bool = False) -> Iterable[LocatedValue]:
    if isinstance(node, MappingNode):
        for key_node, value_node in node.value:
            key = key_node.value if isinstance(key_node, ScalarNode) else ""
            yield from _walk_yaml_node(value_node, semantic=_is_path_key(key))
        return
    if isinstance(node, SequenceNode):
        for item in node.value:
            yield from _walk_yaml_node(item, semantic=semantic)
        return
    if isinstance(node, ScalarNode) and semantic and isinstance(node.value, str):
        for offset, candidate in _extract_external_paths(node.value):
            yield LocatedValue(
                parser="yaml",
                line=node.start_mark.line + 1,
                column=node.start_mark.column + 1 + offset,
                value=candidate,
            )


def _parse_yaml(path: Path) -> list[LocatedValue]:
    text = path.read_text(encoding="utf-8")
    yaml.safe_load(text)
    node = yaml.compose(text)
    return [] if node is None else list(_walk_yaml_node(node))


def _line_column(text: str, needle: str) -> tuple[int, int]:
    offset = text.find(needle)
    if offset < 0:
        return 1, 1
    return text.count("\n", 0, offset) + 1, offset - text.rfind("\n", 0, offset)


def _walk_json(value: object, *, text: str, semantic: bool = False) -> Iterable[LocatedValue]:
    if isinstance(value, dict):
        for key, child in value.items():
            yield from _walk_json(child, text=text, semantic=_is_path_key(key))
        return
    if isinstance(value, list):
        for child in value:
            yield from _walk_json(child, text=text, semantic=semantic)
        return
    if isinstance(value, str) and semantic:
        for _, candidate in _extract_external_paths(value):
            line, column = _line_column(text, json.dumps(value, ensure_ascii=False)[1:-1])
            yield LocatedValue(parser="json", line=line, column=column, value=candidate)


def _parse_json(path: Path) -> list[LocatedValue]:
    text = path.read_text(encoding="utf-8")
    payload = json.loads(text)
    return list(_walk_json(payload, text=text))


def _powershell_inspector() -> Path:
    return Path(__file__).resolve().parents[2] / "bootstrap" / "inspect_powershell_paths.ps1"


def _parse_powershell(path: Path) -> list[LocatedValue]:
    executable = shutil.which("powershell.exe") or shutil.which("powershell")
    if not executable:
        raise RuntimeError("PowerShell parser is unavailable")
    completed = subprocess.run(
        [
            executable,
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(_powershell_inspector()),
            "-Path",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    payload = json.loads(completed.stdout or "[]")
    if isinstance(payload, dict):
        payload = [payload]
    if not isinstance(payload, list):
        raise ValueError("PowerShell parser returned an invalid payload")
    values: list[LocatedValue] = []
    for item in payload:
        if not isinstance(item, dict):
            raise ValueError("PowerShell parser returned an invalid item")
        raw = str(item.get("value", ""))
        for offset, candidate in _extract_external_paths(raw):
            values.append(
                LocatedValue(
                    parser="powershell_ast",
                    line=int(item["line"]),
                    column=int(item["column"]) + offset,
                    value=candidate,
                )
            )
    return values


def _parse_text_fallback(path: Path) -> list[LocatedValue]:
    values: list[LocatedValue] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        for offset, candidate in _extract_external_paths(line):
            values.append(
                LocatedValue(
                    parser="text_fallback",
                    line=line_number,
                    column=offset + 1,
                    value=candidate,
                )
            )
    return values


def _parse_file(path: Path) -> list[LocatedValue]:
    suffix = path.suffix.casefold()
    if suffix == ".py":
        return _parse_python(path)
    if suffix == ".ps1":
        return _parse_powershell(path)
    if suffix in {".yaml", ".yml"}:
        return _parse_yaml(path)
    if suffix == ".json":
        return _parse_json(path)
    if suffix in {".cmd", ".bat"}:
        return _parse_text_fallback(path)
    return []


def _load_policy(path: Path) -> tuple[list[AllowlistEntry], list[str]]:
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise PathAuditPolicyError(f"Cannot read path allowlist ({type(exc).__name__})") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != "external_path_allowlist.v1":
        raise PathAuditPolicyError("Path allowlist schema_version must be external_path_allowlist.v1")
    raw_entries = payload.get("entries")
    if not isinstance(raw_entries, list):
        raise PathAuditPolicyError("Path allowlist entries must be a list")
    entries: list[AllowlistEntry] = []
    duplicates: list[str] = []
    seen_ids: set[str] = set()
    seen_keys: set[tuple[str, str]] = set()
    for index, raw in enumerate(raw_entries):
        if not isinstance(raw, dict):
            raise PathAuditPolicyError("Every path allowlist entry must be an object")
        required = {"id", "file", "value", "category", "reason"}
        if set(raw) != required or not all(isinstance(raw[key], str) and raw[key].strip() for key in required):
            raise PathAuditPolicyError("Every path allowlist entry requires exact non-empty fields")
        entry_id = raw["id"].strip()
        file = PurePosixPath(raw["file"].replace("\\", "/")).as_posix()
        value = raw["value"].strip()
        category = raw["category"].strip()
        reason = raw["reason"].strip()
        if any(character in file + value for character in "*?[]"):
            raise PathAuditPolicyError(f"Wildcards are forbidden in path allowlist entry: {entry_id}")
        file_path = PurePosixPath(file)
        if file_path.is_absolute() or ".." in file_path.parts:
            raise PathAuditPolicyError(f"Allowlist file must be root-relative: {entry_id}")
        if category not in _ALLOWED_CATEGORIES:
            raise PathAuditPolicyError(f"Unsupported path allowlist category: {category}")
        key = (file, value)
        if entry_id in seen_ids or key in seen_keys:
            duplicates.append(entry_id or f"entry-{index}")
        seen_ids.add(entry_id)
        seen_keys.add(key)
        entries.append(AllowlistEntry(entry_id, file, value, category, reason))
    return entries, sorted(duplicates)


def _lexical_path(path: Path) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def _collect_files(
    root: Path,
    includes: Sequence[Path],
    *,
    mode: str,
) -> tuple[list[tuple[str, Path]], list[dict[str, str]]]:
    lexical_root = _lexical_path(root)
    inputs = [lexical_root] if mode == "stage" else [_lexical_path(item if item.is_absolute() else root / item) for item in includes]
    for candidate in inputs:
        try:
            candidate.relative_to(lexical_root)
        except ValueError as exc:
            raise PathAuditError(f"Include must be inside root: {candidate}") from exc
    sorted_inputs = sorted(set(inputs), key=lambda item: (len(item.parts), str(item).casefold()))
    for index, parent in enumerate(sorted_inputs):
        for child in sorted_inputs[index + 1 :]:
            try:
                child.relative_to(parent)
            except ValueError:
                continue
            raise PathAuditError(f"Overlapping include paths are forbidden: {parent} and {child}")

    files: dict[str, Path] = {}
    escapes: list[dict[str, str]] = []

    def register(candidate: Path) -> None:
        relative = candidate.relative_to(lexical_root).as_posix()
        if mode == "stage" and PurePosixPath(relative).parts[0] in _MUTABLE_PREFIXES:
            return
        try:
            resolved = candidate.resolve(strict=True)
            resolved.relative_to(root)
        except (OSError, ValueError):
            escapes.append({"path": relative, "resolved_path": str(candidate.resolve(strict=False))})
            return
        if resolved.is_file() and resolved.suffix.casefold() in _SUPPORTED_SUFFIXES:
            files[relative] = resolved

    for item in sorted_inputs:
        if not item.exists():
            raise PathAuditError(f"Include does not exist: {item}")
        try:
            resolved_item = item.resolve(strict=True)
            resolved_item.relative_to(root)
        except (OSError, ValueError):
            relative = item.relative_to(lexical_root).as_posix()
            escapes.append({"path": relative, "resolved_path": str(item.resolve(strict=False))})
            continue
        if item.is_file():
            register(item)
            continue
        for directory, dirnames, filenames in os.walk(item, followlinks=False):
            directory_path = Path(directory)
            kept: list[str] = []
            for dirname in sorted(dirnames):
                child = directory_path / dirname
                relative = child.relative_to(lexical_root).as_posix()
                if mode == "stage" and PurePosixPath(relative).parts[0] in _MUTABLE_PREFIXES:
                    continue
                if child.is_symlink():
                    register(child)
                    continue
                kept.append(dirname)
            dirnames[:] = kept
            for filename in sorted(filenames):
                register(directory_path / filename)
    escapes.sort(key=lambda item: (item["path"], item["resolved_path"]))
    return sorted(files.items()), escapes


def audit_crawler_paths(
    root: Path,
    policy_path: Path,
    *,
    includes: Sequence[Path] | None = None,
    mode: str = "source",
) -> dict[str, object]:
    if mode not in {"source", "stage"}:
        raise PathAuditError("mode must be source or stage")
    resolved_root = Path(root).expanduser().resolve(strict=True)
    resolved_policy = Path(policy_path).expanduser().resolve(strict=True)
    entries, duplicate_ids = _load_policy(resolved_policy)
    files, path_escapes = _collect_files(
        resolved_root,
        tuple(includes or ()),
        mode=mode,
    )
    first_by_key: dict[tuple[str, str], AllowlistEntry] = {}
    for entry in entries:
        first_by_key.setdefault((entry.file, entry.value), entry)
    used_ids: set[str] = set()
    scanned_files: list[str] = []
    parse_errors: list[dict[str, str]] = []
    matches: list[dict[str, object]] = []
    for relative, path in files:
        if path == resolved_policy:
            continue
        scanned_files.append(relative)
        try:
            values = _parse_file(path)
        except Exception as exc:
            parse_errors.append({"file": relative, "parser": path.suffix.casefold(), "error_type": type(exc).__name__})
            continue
        for located in values:
            entry = first_by_key.get((relative, located.value))
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
                    "parser": located.parser,
                    "file": relative,
                    "line": located.line,
                    "column": located.column,
                    "value": located.value,
                    "category": category,
                    "allowlist_id": allowlist_id,
                    "reason": reason,
                }
            )
    matches.sort(
        key=lambda item: (
            str(item["file"]),
            int(item["line"]),
            int(item["column"]),
            str(item["value"]),
        )
    )
    parse_errors.sort(key=lambda item: (item["file"], item["parser"], item["error_type"]))
    stale_ids = sorted(entry.entry_id for entry in entries if entry.entry_id not in used_ids)
    failed_counts = {
        "parse_error_count": len(parse_errors),
        "unclassified_external_path_count": sum(
            1 for item in matches if item["category"] == "unclassified"
        ),
        "stale_allowlist_count": len(stale_ids),
        "duplicate_allowlist_count": len(duplicate_ids),
        "path_escape_count": len(path_escapes),
    }
    return {
        "schema_version": "huiji_crawler_path_audit.v1",
        "root": str(resolved_root),
        "mode": mode,
        "scanned_files": sorted(scanned_files),
        "matches": matches,
        "parse_errors": parse_errors,
        "stale_allowlist_ids": stale_ids,
        "duplicate_allowlist_ids": duplicate_ids,
        "path_escapes": path_escapes,
        **failed_counts,
        "status": "passed" if not any(failed_counts.values()) else "failed",
    }
