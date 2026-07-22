from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal

import yaml

from .errors import CrawlerConfigError
from .runtime_paths import ToolPaths, resolve_owned_path


CONFIG_SCHEMA_VERSION = "huiji_crawler_config.v1"

_DEFAULTS: dict[str, object] = {
    "expected_user": "POTATO BOT",
    "namespaces": (0, 3500, 10, 828, 14),
    "include_file_manifest": False,
    "sleep": 1.0,
    "progress": True,
    "log_every": 100,
    "transport": "requests",
    "browser_headless": False,
    "browser_verify": True,
    "edge_port": 9222,
    "edge_executable": None,
    "out": None,
    "browser_profile": None,
    "edge_profile": None,
}

_ALLOWED_GROUP_KEYS = {
    "site": {"expected_user"},
    "crawl": {
        "namespaces",
        "include_file_manifest",
        "sleep_seconds",
        "progress",
        "log_every",
        "transport",
    },
    "browser": {"headless", "verify_account"},
    "edge": {"port"},
}

_ENV_FIELDS = {
    "HUIJI_CRAWLER_NAMESPACES": "namespaces",
    "HUIJI_CRAWLER_INCLUDE_FILE_MANIFEST": "include_file_manifest",
    "HUIJI_CRAWLER_SLEEP": "sleep",
    "HUIJI_CRAWLER_EXPECTED_USER": "expected_user",
    "HUIJI_CRAWLER_PROGRESS": "progress",
    "HUIJI_CRAWLER_LOG_EVERY": "log_every",
    "HUIJI_CRAWLER_TRANSPORT": "transport",
    "HUIJI_CRAWLER_BROWSER_HEADLESS": "browser_headless",
    "HUIJI_CRAWLER_BROWSER_VERIFY": "browser_verify",
    "HUIJI_CRAWLER_EDGE_PORT": "edge_port",
    "HUIJI_CRAWLER_EDGE_EXECUTABLE": "edge_executable",
    "HUIJI_CRAWLER_OUT": "out",
    "HUIJI_CRAWLER_BROWSER_PROFILE": "browser_profile",
    "HUIJI_CRAWLER_EDGE_PROFILE": "edge_profile",
}

_FIELDS = frozenset(_DEFAULTS)


@dataclass(frozen=True)
class CrawlerSettings:
    paths: ToolPaths
    namespaces: tuple[int, ...]
    include_file_manifest: bool
    sleep: float
    expected_user: str
    progress: bool
    log_every: int
    transport: Literal["requests", "browser", "edge"]
    browser_headless: bool
    browser_verify: bool
    edge_port: int
    edge_executable: Path | None


def _mapping(value: object, *, label: str) -> dict[str, object]:
    if value is None:
        return {}
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise CrawlerConfigError(f"{label} must be a mapping")
    return dict(value)


def _load_yaml(path: Path) -> dict[str, object]:
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise CrawlerConfigError(
            f"Cannot read crawler settings {path.name} ({type(exc).__name__})"
        ) from exc
    if not isinstance(payload, dict):
        raise CrawlerConfigError("Crawler settings must be a mapping")
    if payload.get("schema_version") != CONFIG_SCHEMA_VERSION:
        raise CrawlerConfigError(
            f"Crawler settings schema_version must be {CONFIG_SCHEMA_VERSION}"
        )
    allowed_top = {"schema_version", *_ALLOWED_GROUP_KEYS}
    unknown_top = sorted(set(payload) - allowed_top)
    if unknown_top:
        raise CrawlerConfigError(f"Unknown crawler settings key: {unknown_top[0]}")

    groups: dict[str, dict[str, object]] = {}
    for group, allowed in _ALLOWED_GROUP_KEYS.items():
        values = _mapping(payload.get(group), label=group)
        unknown = sorted(set(values) - allowed)
        if unknown:
            raise CrawlerConfigError(f"Unknown crawler settings key: {group}.{unknown[0]}")
        groups[group] = values

    flattened: dict[str, object] = {}
    field_map = {
        ("site", "expected_user"): "expected_user",
        ("crawl", "namespaces"): "namespaces",
        ("crawl", "include_file_manifest"): "include_file_manifest",
        ("crawl", "sleep_seconds"): "sleep",
        ("crawl", "progress"): "progress",
        ("crawl", "log_every"): "log_every",
        ("crawl", "transport"): "transport",
        ("browser", "headless"): "browser_headless",
        ("browser", "verify_account"): "browser_verify",
        ("edge", "port"): "edge_port",
    }
    for (group, key), destination in field_map.items():
        if key in groups[group]:
            flattened[destination] = groups[group][key]
    return flattened


def _parse_bool(value: object, *, label: str, from_environment: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if from_environment and isinstance(value, str):
        normalized = value.strip().casefold()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    raise CrawlerConfigError(f"{label} must be a boolean")


def _parse_namespaces(value: object, *, label: str) -> tuple[int, ...]:
    items: list[object]
    if isinstance(value, str):
        items = [item for token in value.split() for item in token.split(",") if item]
    elif isinstance(value, (list, tuple)):
        items = list(value)
    else:
        raise CrawlerConfigError(f"{label} must be a list or comma-separated string")
    parsed: list[int] = []
    for item in items:
        if isinstance(item, bool):
            raise CrawlerConfigError(f"{label} contains an invalid namespace")
        try:
            parsed.append(int(item))
        except (TypeError, ValueError) as exc:
            raise CrawlerConfigError(f"{label} contains an invalid namespace") from exc
    if not parsed:
        raise CrawlerConfigError(f"{label} must not be empty")
    return tuple(parsed)


def _parse_values(values: Mapping[str, object], *, environment_fields: set[str]) -> dict[str, object]:
    parsed = dict(values)
    for field in ("include_file_manifest", "progress", "browser_headless", "browser_verify"):
        parsed[field] = _parse_bool(
            parsed[field],
            label=field,
            from_environment=field in environment_fields,
        )
    parsed["namespaces"] = _parse_namespaces(parsed["namespaces"], label="namespaces")

    expected_user = parsed["expected_user"]
    if not isinstance(expected_user, str) or not expected_user.strip():
        raise CrawlerConfigError("expected_user must be a non-empty string")
    parsed["expected_user"] = expected_user.strip()

    transport = parsed["transport"]
    if not isinstance(transport, str) or transport not in {"requests", "browser", "edge"}:
        raise CrawlerConfigError("transport must be requests, browser or edge")

    if isinstance(parsed["sleep"], bool):
        raise CrawlerConfigError("sleep must be a non-negative number")
    try:
        parsed["sleep"] = float(parsed["sleep"])
    except (TypeError, ValueError) as exc:
        raise CrawlerConfigError("sleep must be a non-negative number") from exc
    if parsed["sleep"] < 0:
        raise CrawlerConfigError("sleep must be a non-negative number")

    for field, minimum, maximum in (("log_every", 1, None), ("edge_port", 1, 65535)):
        raw = parsed[field]
        if isinstance(raw, bool):
            raise CrawlerConfigError(f"{field} must be an integer")
        try:
            number = int(raw)
        except (TypeError, ValueError) as exc:
            raise CrawlerConfigError(f"{field} must be an integer") from exc
        if number < minimum or (maximum is not None and number > maximum):
            raise CrawlerConfigError(f"{field} is outside the supported range")
        parsed[field] = number
    return parsed


def _resolve_external_executable(value: object, *, root: Path) -> Path | None:
    if value in (None, ""):
        return None
    if not isinstance(value, (str, Path)):
        raise CrawlerConfigError("Edge executable path is invalid")
    raw = Path(value).expanduser()
    candidate = raw if raw.is_absolute() else root / raw
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise CrawlerConfigError("Edge executable does not exist") from exc
    if not resolved.is_file():
        raise CrawlerConfigError("Edge executable must be a file")
    return resolved


def load_crawler_settings(
    *,
    tool_root: Path,
    cli_overrides: Mapping[str, object] | None = None,
    environ: Mapping[str, str] | None = None,
) -> CrawlerSettings:
    paths = ToolPaths.from_root(tool_root)
    yaml_values = _load_yaml(paths.settings_file)
    merged = dict(_DEFAULTS)
    merged.update(yaml_values)

    environment = {} if environ is None else dict(environ)
    environment_fields: set[str] = set()
    for variable, field in _ENV_FIELDS.items():
        if variable in environment:
            merged[field] = environment[variable]
            environment_fields.add(field)

    overrides = {} if cli_overrides is None else dict(cli_overrides)
    unknown_overrides = sorted(set(overrides) - _FIELDS)
    if unknown_overrides:
        raise CrawlerConfigError(f"Unknown CLI override: {unknown_overrides[0]}")
    for field, value in overrides.items():
        if value is not None:
            merged[field] = value
            environment_fields.discard(field)

    parsed = _parse_values(merged, environment_fields=environment_fields)
    workspace = paths.workspace
    browser_profile = paths.browser_profile
    edge_profile = paths.edge_profile
    if parsed["out"] not in (None, ""):
        workspace = resolve_owned_path(parsed["out"], root=paths.root, label="out")
    if parsed["browser_profile"] not in (None, ""):
        browser_profile = resolve_owned_path(
            parsed["browser_profile"],
            root=paths.root,
            label="browser_profile",
        )
    if parsed["edge_profile"] not in (None, ""):
        edge_profile = resolve_owned_path(
            parsed["edge_profile"],
            root=paths.root,
            label="edge_profile",
        )
    paths = replace(
        paths,
        workspace=workspace,
        browser_profile=browser_profile,
        edge_profile=edge_profile,
    )
    edge_executable = _resolve_external_executable(
        parsed["edge_executable"],
        root=paths.root,
    )
    return CrawlerSettings(
        paths=paths,
        namespaces=parsed["namespaces"],
        include_file_manifest=parsed["include_file_manifest"],
        sleep=parsed["sleep"],
        expected_user=parsed["expected_user"],
        progress=parsed["progress"],
        log_every=parsed["log_every"],
        transport=parsed["transport"],
        browser_headless=parsed["browser_headless"],
        browser_verify=parsed["browser_verify"],
        edge_port=parsed["edge_port"],
        edge_executable=edge_executable,
    )
