from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .errors import ToolPathViolation


def resolve_owned_path(
    value: str | Path,
    *,
    root: Path,
    label: str,
    must_exist: bool = False,
) -> Path:
    resolved_root = Path(root).expanduser().resolve(strict=True)
    raw = Path(value).expanduser()
    candidate = raw if raw.is_absolute() else resolved_root / raw
    try:
        resolved = candidate.resolve(strict=must_exist)
    except OSError as exc:
        raise ToolPathViolation(f"{label} cannot be resolved inside the tool root") from exc
    try:
        resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise ToolPathViolation(f"{label} must resolve inside the tool root: {resolved}") from exc
    return resolved


@dataclass(frozen=True)
class ToolPaths:
    root: Path
    settings_file: Path
    credential_file: Path
    workspace: Path
    browser_profile: Path
    edge_profile: Path
    refresh_runtime: Path
    lock_file: Path

    @classmethod
    def from_root(cls, root: Path) -> "ToolPaths":
        resolved_root = Path(root).expanduser().resolve(strict=True)

        def owned(relative: str, label: str) -> Path:
            return resolve_owned_path(relative, root=resolved_root, label=label)

        return cls(
            root=resolved_root,
            settings_file=owned("config/crawler.yaml", "settings_file"),
            credential_file=owned(
                ".local/accounts/default/credential.json",
                "credential_file",
            ),
            workspace=owned("workspace/default/res1999", "workspace"),
            browser_profile=owned(
                ".local/accounts/default/browser-profile",
                "browser_profile",
            ),
            edge_profile=owned(
                ".local/accounts/default/edge-profile",
                "edge_profile",
            ),
            refresh_runtime=owned(
                ".local/accounts/default/refresh-runtime",
                "refresh_runtime",
            ),
            lock_file=owned(".local/locks/default.lock", "lock_file"),
        )
