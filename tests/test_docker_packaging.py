from __future__ import annotations

import re
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
BACKEND_DOCKERFILE = ROOT / "docker" / "Dockerfile.backend"
FRONTEND_DOCKERFILE = ROOT / "docker" / "Dockerfile.frontend"
CADDYFILE = ROOT / "docker" / "frontend.Caddyfile"
DOCKERIGNORE = ROOT / ".dockerignore"


def _read(path: Path) -> str:
    assert path.is_file(), f"required production packaging file is missing: {path.relative_to(ROOT)}"
    return path.read_text(encoding="utf-8")


def _logical_dockerfile_lines(text: str) -> list[str]:
    return [
        re.sub(r"\s+", " ", line.strip())
        for line in re.sub(r"\\\r?\n", " ", text).splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


@pytest.mark.parametrize(
    "path",
    [BACKEND_DOCKERFILE, FRONTEND_DOCKERFILE, CADDYFILE, DOCKERIGNORE],
)
def test_required_production_packaging_files_exist(path: Path) -> None:
    assert path.is_file(), f"missing {path.relative_to(ROOT)}"


def test_backend_uses_pinned_python_stages_and_runtime_lock_only() -> None:
    text = _read(BACKEND_DOCKERFILE)
    lines = _logical_dockerfile_lines(text)

    assert sum(line.startswith("FROM python:3.11.15-slim-bookworm") for line in lines) == 2
    assert "requirements/runtime.lock.txt" in text
    assert re.search(r"\bpip\s+install\b.*-r\s+\S*runtime\.lock\.txt\b", " ".join(lines))
    assert "requirements.txt" not in text
    assert "requirements/runtime.in" not in text
    assert "/opt/venv" in text


def test_backend_final_stage_is_an_explicit_runtime_allow_list() -> None:
    text = _read(BACKEND_DOCKERFILE)
    lines = _logical_dockerfile_lines(text)
    required_fragments = {
        "COPY backend ./backend",
        "COPY config/config.py config/settings.yaml ./config/",
        "COPY config/provenance ./config/provenance",
        "COPY src/__init__.py ./src/",
        "COPY src/rag ./src/rag",
        "COPY src/assets ./src/assets",
        "COPY src/utils ./src/utils",
        "src/huiji_wiki/repository.py",
        "src/huijiwiki/errors.py",
        "src/huijiwiki/project_paths.py",
        "src/huiji_rag/runtime_artifacts.py",
        "src/huiji_rag/build/contracts.py",
    }
    for fragment in required_fragments:
        assert fragment in " ".join(lines), f"missing runtime copy contract: {fragment}"
    assert "src/huiji_rag/build/__init__.py" not in " ".join(lines)

    forbidden_broad_copies = (
        r"^COPY\s+\.\s+",
        r"^COPY\s+src\s+",
        r"^COPY\s+src/huiji_rag\s+",
        r"^COPY\s+src/huiji_wiki\s+",
        r"^COPY\s+src/huijiwiki\s+",
    )
    for line in lines:
        assert not any(re.search(pattern, line) for pattern in forbidden_broad_copies), line


def test_backend_runs_as_non_root_with_one_uvicorn_worker() -> None:
    text = _read(BACKEND_DOCKERFILE)
    lines = _logical_dockerfile_lines(text)

    assert any(line == "USER app" for line in lines)
    assert not any(line == "USER root" for line in lines)
    assert (
        'CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", '
        '"--port", "8000", "--workers", "1"]'
    ) in text
    assert 'python -c "import backend.main"' in text


def test_frontend_builds_with_pinned_node_and_serves_only_dist_with_caddy() -> None:
    text = _read(FRONTEND_DOCKERFILE)
    lines = _logical_dockerfile_lines(text)

    assert lines[0] == "FROM node:22.23.1-alpine AS build"
    assert any(line == "RUN npm ci" for line in lines)
    assert any(line == "RUN npm run build" for line in lines)
    assert any(line == "FROM caddy:2.11.4-alpine" for line in lines)

    runtime_start = next(i for i, line in enumerate(lines) if line == "FROM caddy:2.11.4-alpine")
    runtime_lines = lines[runtime_start + 1 :]
    runtime_copies = [line for line in runtime_lines if line.startswith("COPY ")]
    assert runtime_copies == [
        "COPY --from=build /app/dist /srv",
        "COPY docker/frontend.Caddyfile /etc/caddy/Caddyfile",
    ]


def test_caddy_routes_health_and_api_before_spa_fallback() -> None:
    text = _read(CADDYFILE)
    health = text.index("handle /health")
    api = text.index("handle /api/*")
    fallback = text.index("handle {")

    assert health < fallback
    assert api < fallback
    assert text.count("reverse_proxy backend:8000") == 2
    assert "root * /srv" in text
    assert "try_files {path} /index.html" in text
    assert "file_server" in text


def test_dockerignore_excludes_sensitive_and_development_payloads() -> None:
    lines = {
        line.strip()
        for line in _read(DOCKERIGNORE).splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    required_patterns = {
        ".git/",
        ".worktrees/",
        ".env",
        ".env.*",
        "data/",
        "vectorstore/",
        "**/node_modules/",
        "**/dist/",
        "tests/",
        "src/huiji_crawler_packaging/",
        "src/huiji_crawler_tool/",
        "src/rag_eval/",
        "eval/",
        "logs/",
        "backups/",
        "*.log",
        "*.bak",
    }
    assert required_patterns <= lines


def test_dockerignore_keeps_every_production_build_input() -> None:
    lines = {
        line.strip()
        for line in _read(DOCKERIGNORE).splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    assert not {
        "frontend/",
        "frontend/react-app/",
        "frontend/react-app/public/",
        "src/",
        "src/rag/",
        "src/assets/",
        "src/utils/",
        "src/huiji_rag/",
        "src/huiji_wiki/",
        "src/huijiwiki/",
        "config/",
        "requirements/",
        "package.json",
        "package-lock.json",
        "*.png",
        "*.jpg",
        "*.mp4",
        "*.ttf",
        "*.otf",
    } & lines

    public_assets = list((ROOT / "frontend" / "react-app" / "public").rglob("*"))
    assert len([path for path in public_assets if path.is_file()]) == 17


@pytest.mark.parametrize("dockerfile", [BACKEND_DOCKERFILE, FRONTEND_DOCKERFILE])
def test_dockerfiles_never_copy_forbidden_runtime_or_credentials(dockerfile: Path) -> None:
    text = _read(dockerfile).lower()
    forbidden_sources = (
        "infra/mysql",
        "infra/minio",
        "infra/milvus",
        "vectorstore",
        "data/",
        "rag-artifacts",
        "crawler-output",
        "src/huiji_crawler",
        "src/rag_eval",
        "eval/",
        ".env",
        "credential",
        "cookie",
        "browser_profile",
    )
    for source in forbidden_sources:
        assert source not in text, f"{dockerfile.name} references forbidden source {source!r}"
