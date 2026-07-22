from __future__ import annotations

from pathlib import Path


class ProjectPathViolation(ValueError):
    """Raised when project-owned state resolves outside the project root."""


def resolve_project_local_path(
    value: str | Path,
    *,
    project_root: Path,
    label: str,
    must_exist: bool = False,
) -> Path:
    root = project_root.expanduser().resolve(strict=True)
    raw = Path(value).expanduser()
    candidate = raw if raw.is_absolute() else root / raw
    resolved = candidate.resolve(strict=must_exist)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ProjectPathViolation(
            f"{label} must resolve inside the project root: {resolved}"
        ) from exc
    return resolved
