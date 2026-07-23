from __future__ import annotations

import json
import posixpath
import re
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
BACKEND_DOCKERFILE = ROOT / "docker" / "Dockerfile.backend"
FRONTEND_DOCKERFILE = ROOT / "docker" / "Dockerfile.frontend"
CADDYFILE = ROOT / "docker" / "frontend.Caddyfile"
DOCKERIGNORE = ROOT / ".dockerignore"
FRONTEND_ROOT = ROOT / "frontend" / "react-app"


@dataclass(frozen=True)
class Instruction:
    keyword: str
    arguments: str


@dataclass(frozen=True)
class Stage:
    base: str
    name: str
    instructions: tuple[Instruction, ...]


@dataclass(frozen=True)
class CopySpec:
    sources: tuple[str, ...]
    destination: str
    from_stage: str | None


def _read(path: Path) -> str:
    assert path.is_file(), f"required production packaging file is missing: {path.relative_to(ROOT)}"
    return path.read_text(encoding="utf-8")


def _logical_instructions(text: str) -> list[str]:
    logical: list[str] = []
    current = ""
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        current = f"{current} {stripped}".strip()
        if current.endswith("\\"):
            current = current[:-1].rstrip()
            continue
        logical.append(re.sub(r"\s+", " ", current))
        current = ""
    assert not current, "Dockerfile ends with an incomplete continuation"
    return logical


def _parse_dockerfile_text(text: str) -> tuple[Stage, ...]:
    stages: list[Stage] = []
    current_base: str | None = None
    current_name = ""
    current_instructions: list[Instruction] = []

    def finish_stage() -> None:
        if current_base is not None:
            stages.append(Stage(current_base, current_name, tuple(current_instructions)))

    for line in _logical_instructions(text):
        keyword, separator, arguments = line.partition(" ")
        keyword = keyword.upper()
        assert separator, f"Dockerfile instruction has no arguments: {line}"
        if keyword == "FROM":
            finish_stage()
            tokens = shlex.split(arguments)
            assert tokens, "FROM requires a base image"
            current_base = tokens[0]
            current_name = (
                tokens[-1].lower()
                if len(tokens) >= 3 and tokens[-2].upper() == "AS"
                else f"stage-{len(stages)}"
            )
            current_instructions = []
            continue
        assert current_base is not None, f"instruction appears before FROM: {line}"
        current_instructions.append(Instruction(keyword, arguments))
    finish_stage()
    return tuple(stages)


def _parse_dockerfile(path: Path) -> tuple[Stage, ...]:
    return _parse_dockerfile_text(_read(path))


def _instruction(stage: Stage, keyword: str) -> list[Instruction]:
    return [item for item in stage.instructions if item.keyword == keyword]


def _copy_spec(instruction: Instruction) -> CopySpec:
    assert instruction.keyword == "COPY"
    arguments = instruction.arguments.strip()
    if arguments.startswith("["):
        values = json.loads(arguments)
        assert isinstance(values, list) and len(values) >= 2
        return CopySpec(tuple(values[:-1]), values[-1], None)

    tokens = shlex.split(arguments, posix=True)
    from_stage: str | None = None
    while tokens and tokens[0].startswith("--"):
        flag = tokens.pop(0)
        if flag.startswith("--from="):
            from_stage = flag.split("=", 1)[1]
    assert len(tokens) >= 2, f"COPY needs source and destination: {instruction.arguments}"
    return CopySpec(tuple(tokens[:-1]), tokens[-1], from_stage)


def _normalized_source(source: str) -> str:
    return posixpath.normpath(source.replace("\\", "/"))


def _is_broad_local_copy_source(source: str) -> bool:
    context_relative = _normalized_source(source).lstrip("/")
    if context_relative in {"", ".", "*", "**", "**/*", "src"}:
        return True
    return context_relative.startswith("src/") and any(
        marker in context_relative.removeprefix("src/") for marker in ("*", "?", "[")
    )


def _all_copy_specs(stages: tuple[Stage, ...]) -> list[tuple[Stage, CopySpec]]:
    return [
        (stage, _copy_spec(instruction))
        for stage in stages
        for instruction in _instruction(stage, "COPY")
    ]


def _pip_install_instructions(stages: tuple[Stage, ...]) -> list[tuple[Stage, Instruction]]:
    pip_install = re.compile(
        r"(?:\bpython(?:\d+(?:\.\d+)*)?\s+-m\s+pip|\bpip(?:\d+(?:\.\d+)*)?)\s+install\b",
        re.IGNORECASE,
    )
    return [
        (stage, instruction)
        for stage in stages
        for instruction in _instruction(stage, "RUN")
        if pip_install.search(instruction.arguments)
    ]


def _dockerignore_rules() -> tuple[str, ...]:
    return tuple(
        line.strip()
        for line in _read(DOCKERIGNORE).splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    )


def _dockerignore_pattern_regex(pattern: str) -> re.Pattern[str]:
    normalized = pattern.replace("\\", "/").lstrip("/").rstrip("/")
    basename_pattern = "/" not in normalized
    expression: list[str] = []
    index = 0
    while index < len(normalized):
        if normalized.startswith("**/", index):
            expression.append("(?:.*/)?")
            index += 3
        elif normalized.startswith("**", index):
            expression.append(".*")
            index += 2
        elif normalized[index] == "*":
            expression.append("[^/]*")
            index += 1
        elif normalized[index] == "?":
            expression.append("[^/]")
            index += 1
        else:
            expression.append(re.escape(normalized[index]))
            index += 1
    prefix = r"(?:^|.*/)" if basename_pattern else "^"
    return re.compile(prefix + "".join(expression) + r"(?:/.*)?$")


def _is_ignored(path: str, rules: tuple[str, ...] | None = None) -> bool:
    normalized_path = posixpath.normpath(path.replace("\\", "/")).lstrip("/")
    ignored = False
    for rule in rules or _dockerignore_rules():
        negated = rule.startswith("!")
        pattern = rule[1:] if negated else rule
        if _dockerignore_pattern_regex(pattern).match(normalized_path):
            ignored = not negated
    return ignored


def _normalized_caddy_lines() -> tuple[str, ...]:
    lines: list[str] = []
    for raw_line in _read(CADDYFILE).splitlines():
        directive = raw_line.split("#", 1)[0].strip()
        if directive:
            lines.append(re.sub(r"\s+", " ", directive))
    return tuple(lines)


def test_parser_ignores_comments_and_scopes_instructions_to_stages() -> None:
    stages = _parse_dockerfile_text(
        """
        # USER app
        FROM python:3.11 AS deps
        # RUN pip install fake-requirements.txt
        RUN python -m venv /opt/venv
        FROM python:3.11 AS runtime
        USER nobody
        """
    )

    assert [stage.name for stage in stages] == ["deps", "runtime"]
    assert _instruction(stages[0], "USER") == []
    assert _instruction(stages[1], "USER") == [Instruction("USER", "nobody")]
    assert _pip_install_instructions(stages) == []


@pytest.mark.parametrize(
    "source",
    [
        ".",
        "./",
        "./.",
        "/",
        "//",
        "*",
        "./*",
        "**",
        "/**",
        "src",
        "src/",
        "./src",
        "/src",
        "src/*",
        "./src/**",
    ],
)
def test_broad_repository_copy_source_variants_are_recognized(source: str) -> None:
    assert _is_broad_local_copy_source(source)


@pytest.mark.parametrize(
    "path",
    [BACKEND_DOCKERFILE, FRONTEND_DOCKERFILE, CADDYFILE, DOCKERIGNORE],
)
def test_required_production_packaging_files_exist(path: Path) -> None:
    assert path.is_file(), f"missing {path.relative_to(ROOT)}"


@pytest.mark.parametrize("dockerfile", [BACKEND_DOCKERFILE, FRONTEND_DOCKERFILE])
def test_dockerfiles_reject_add_and_broad_copy_sources(dockerfile: Path) -> None:
    stages = _parse_dockerfile(dockerfile)
    assert not [
        instruction
        for stage in stages
        for instruction in _instruction(stage, "ADD")
    ], "ADD is forbidden in production images"

    for stage, copy in _all_copy_specs(stages):
        if copy.from_stage is not None:
            continue
        for source in copy.sources:
            assert not _is_broad_local_copy_source(source), (
                f"{dockerfile.name} stage {stage.name} broadly copies {source!r}"
            )


def test_backend_dependency_stage_installs_only_the_runtime_lock() -> None:
    stages = _parse_dockerfile(BACKEND_DOCKERFILE)
    assert [(stage.base, stage.name) for stage in stages] == [
        ("python:3.11.15-slim-bookworm", "deps"),
        ("python:3.11.15-slim-bookworm", "runtime"),
    ]
    deps = stages[0]
    installs = _pip_install_instructions(stages)
    assert len(installs) == 1
    install_stage, install = installs[0]
    assert install_stage is deps
    assert re.search(r"-r\s+\S*runtime\.lock\.txt\b", install.arguments)

    dependency_copies = [_copy_spec(item) for item in _instruction(deps, "COPY")]
    assert dependency_copies == [
        CopySpec(("requirements/runtime.lock.txt",), "/tmp/runtime.lock.txt", None)
    ]


def test_backend_final_stage_copy_sources_are_the_runtime_allow_list() -> None:
    runtime = _parse_dockerfile(BACKEND_DOCKERFILE)[1]
    copies = [_copy_spec(item) for item in _instruction(runtime, "COPY")]
    local_sources = {
        _normalized_source(source)
        for copy in copies
        if copy.from_stage is None
        for source in copy.sources
    }
    assert local_sources == {
        "backend",
        "config/config.py",
        "config/settings.yaml",
        "config/provenance",
        "src/__init__.py",
        "src/rag",
        "src/assets",
        "src/utils",
        "src/huiji_wiki/__init__.py",
        "src/huiji_wiki/models.py",
        "src/huiji_wiki/repository.py",
        "src/huijiwiki/__init__.py",
        "src/huijiwiki/errors.py",
        "src/huijiwiki/models.py",
        "src/huijiwiki/project_paths.py",
        "src/huiji_rag/__init__.py",
        "src/huiji_rag/active_pointer.py",
        "src/huiji_rag/io.py",
        "src/huiji_rag/media.py",
        "src/huiji_rag/models.py",
        "src/huiji_rag/normalizer.py",
        "src/huiji_rag/provenance.py",
        "src/huiji_rag/runtime_artifacts.py",
        "src/huiji_rag/source.py",
        "src/huiji_rag/build/contracts.py",
    }
    external_copies = [copy for copy in copies if copy.from_stage is not None]
    assert external_copies == [CopySpec(("/opt/venv",), "/opt/venv", "deps")]
    assert "src/huiji_rag/build/__init__.py" not in local_sources


def test_backend_final_stage_has_executable_runtime_contracts() -> None:
    runtime = _parse_dockerfile(BACKEND_DOCKERFILE)[1]
    assert _instruction(runtime, "USER") == [Instruction("USER", "app")]
    assert _instruction(runtime, "EXPOSE") == [Instruction("EXPOSE", "8000")]

    command = _instruction(runtime, "CMD")
    assert len(command) == 1
    assert json.loads(command[0].arguments) == [
        "uvicorn",
        "backend.main:app",
        "--host",
        "0.0.0.0",
        "--port",
        "8000",
        "--workers",
        "1",
    ]

    healthchecks = _instruction(runtime, "HEALTHCHECK")
    assert len(healthchecks) == 1
    healthcheck = healthchecks[0].arguments
    assert "--interval=30s" in healthcheck
    assert "--timeout=5s" in healthcheck
    assert "--start-period=30s" in healthcheck
    assert "--retries=3" in healthcheck
    assert "http://127.0.0.1:8000/health" in healthcheck

    runs = _instruction(runtime, "RUN")
    import_gate = [
        item
        for item in runs
        if re.fullmatch(r"""python -c ["']import backend\.main["']""", item.arguments)
    ]
    assert len(import_gate) == 1
    assert runtime.instructions.index(_instruction(runtime, "USER")[0]) < runtime.instructions.index(
        import_gate[0]
    )


def test_frontend_stages_build_then_serve_only_dist_as_caddy() -> None:
    stages = _parse_dockerfile(FRONTEND_DOCKERFILE)
    assert [(stage.base, stage.name) for stage in stages] == [
        ("node:22.23.1-alpine", "build"),
        ("caddy:2.11.4-alpine", "stage-1"),
    ]
    build, runtime = stages
    assert [item.arguments for item in _instruction(build, "RUN")] == [
        "npm ci",
        "npm run build",
    ]
    assert {
        _normalized_source(source)
        for copy in (_copy_spec(item) for item in _instruction(build, "COPY"))
        for source in copy.sources
    } == {
        "frontend/react-app/package.json",
        "frontend/react-app/package-lock.json",
        "frontend/react-app/index.html",
        "frontend/react-app/tsconfig.json",
        "frontend/react-app/tsconfig.node.json",
        "frontend/react-app/vite.config.ts",
        "frontend/react-app/src",
        "frontend/react-app/public",
    }
    assert [_copy_spec(item) for item in _instruction(runtime, "COPY")] == [
        CopySpec(("/app/dist",), "/srv", "build"),
        CopySpec(("docker/frontend.Caddyfile",), "/etc/caddy/Caddyfile", None),
    ]
    assert _instruction(runtime, "USER") == [Instruction("USER", "caddy")]

    runtime_setup = " ".join(item.arguments for item in _instruction(runtime, "RUN"))
    assert re.search(r"\baddgroup\b.*\bcaddy\b", runtime_setup)
    assert re.search(r"\badduser\b.*\bcaddy\b", runtime_setup)
    assert re.search(r"\bchown\b.*\bcaddy:caddy\b.*?/config\b.*?/data\b", runtime_setup)


def test_caddy_configuration_exactly_routes_api_before_spa() -> None:
    assert _normalized_caddy_lines() == (
        ":8080 {",
        "handle /health {",
        "reverse_proxy backend:8000",
        "}",
        "handle /api/wiki/* {",
        "reverse_proxy backend:8000",
        "}",
        "handle /api/media/* {",
        "reverse_proxy backend:8000",
        "}",
        "handle_path /api/* {",
        "reverse_proxy backend:8000",
        "}",
        "handle {",
        "root * /srv",
        "try_files {path} /index.html",
        "file_server",
        "}",
        "}",
    )


def test_frontend_caddy_routes_preserved_and_stripped_api_families(
    tmp_path: Path,
) -> None:
    docker = shutil.which("docker")
    assert docker, "Docker CLI is required for Caddy routing validation"
    frontend = _read(CADDYFILE).replace("backend:8000", "127.0.0.1:18000")
    config = tmp_path / "Caddyfile"
    config.write_text(
        "{\n\tadmin off\n\tauto_https off\n}\n\n"
        + frontend
        + '\n:18000 {\n\trespond "{uri}" 200\n}\n',
        encoding="utf-8",
        newline="\n",
    )
    probe = (
        "set -eu; "
        "caddy start --config /tmp/Caddyfile --adapter caddyfile >/tmp/caddy.log 2>&1; "
        "trap 'caddy stop >/dev/null 2>&1 || true' EXIT; "
        "wget -qO- 'http://127.0.0.1:8080/health'; printf '\\n'; "
        "wget -qO- 'http://127.0.0.1:8080/api/wiki/pages?limit=1'; printf '\\n'; "
        "wget -qO- 'http://127.0.0.1:8080/api/media/voice/page?cursor=x'; printf '\\n'; "
        "wget -qO- 'http://127.0.0.1:8080/api/ask'; printf '\\n'; "
        "wget -qO- 'http://127.0.0.1:8080/api/category/story/docs?limit=1'; printf '\\n'"
    )
    result = subprocess.run(
        [
            docker,
            "run",
            "--rm",
            "-v",
            f"{config}:/tmp/Caddyfile:ro",
            "--entrypoint",
            "/bin/sh",
            "caddy:2.11.4-alpine",
            "-c",
            probe,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.splitlines() == [
        "/health",
        "/api/wiki/pages?limit=1",
        "/api/media/voice/page?cursor=x",
        "/ask",
        "/category/story/docs?limit=1",
    ]


def test_dockerignore_excludes_representative_private_and_development_paths() -> None:
    rules = _dockerignore_rules()
    required_literal_rules = {
        ".git/",
        ".worktrees/",
        ".local/",
        ".venv/",
        "venv/",
        ".env",
        ".env.*",
        "**/*credentials*.json",
        "**/*cookies*.json",
        "**/*credential*",
        "**/*credential*/",
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
    assert required_literal_rules <= set(rules)

    forbidden_paths = (
        ".git/config",
        ".worktrees/review/HEAD",
        ".env",
        "backend/.env.production",
        ".local/huiji/credentials/config.dat",
        ".local/accounts/default/credential.json",
        "runtime/huiji/credentials/config.dat",
        "runtime/accounts/default/credential.json",
        ".venv/bin/python",
        "venv/Scripts/python.exe",
        "data/huiji/corpus.jsonl",
        "vectorstore/index.bin",
        "frontend/react-app/node_modules/vite/package.json",
        "frontend/react-app/dist/index.html",
        "tests/test_backend.py",
        "src/huiji_crawler_tool/main.py",
        "src/rag_eval/runner.py",
        "eval/results.json",
        "logs/backend.log",
        "backups/release.bak",
    )
    for path in forbidden_paths:
        assert _is_ignored(path, rules), f"expected .dockerignore to exclude {path}"


def test_dockerignore_has_no_catch_all_and_keeps_every_production_input() -> None:
    rules = _dockerignore_rules()
    catch_all = {".", "./", "*", "**", "**/*", "/*", "/**", "/**/*"}
    assert not {rule.lstrip("!") for rule in rules} & catch_all

    required_paths = {
        ".dockerignore",
        "docker/Dockerfile.backend",
        "docker/Dockerfile.frontend",
        "docker/frontend.Caddyfile",
        "requirements/runtime.lock.txt",
        "config/config.py",
        "config/settings.yaml",
        "config/provenance/huiji-dev.v1.json",
        "backend/main.py",
        "src/__init__.py",
        "src/rag/chain.py",
        "src/assets/public_url.py",
        "src/utils/text_cleaner.py",
        "src/huiji_wiki/repository.py",
        "src/huijiwiki/errors.py",
        "src/huiji_rag/runtime_artifacts.py",
        "src/huiji_rag/build/contracts.py",
        "frontend/react-app/package.json",
        "frontend/react-app/package-lock.json",
        "frontend/react-app/index.html",
        "frontend/react-app/tsconfig.json",
        "frontend/react-app/tsconfig.node.json",
        "frontend/react-app/vite.config.ts",
        "frontend/react-app/src/main.tsx",
    }
    public_assets = {
        path.relative_to(ROOT).as_posix()
        for path in (FRONTEND_ROOT / "public").rglob("*")
        if path.is_file()
    }
    assert len(public_assets) == 17
    required_paths.update(public_assets)

    for path in sorted(required_paths):
        assert not _is_ignored(path, rules), f"required build input is ignored: {path}"


def test_public_video_is_real_nonempty_content_not_an_lfs_pointer() -> None:
    video = FRONTEND_ROOT / "public" / "videos" / "pv.mp4"
    assert video.stat().st_size > 0
    assert b"git-lfs.github.com/spec/v1" not in video.read_bytes()[:256]


@pytest.mark.parametrize("dockerfile", [BACKEND_DOCKERFILE, FRONTEND_DOCKERFILE])
def test_copy_sources_never_reference_payloads_or_credentials(dockerfile: Path) -> None:
    forbidden = re.compile(
        r"(^|/)(?:data|vectorstore|eval|infra|rag-artifacts|crawler-output|"
        r"huiji_crawler[^/]*|rag_eval|browser_profile)(?:/|$)|"
        r"(?:^|/)(?:\.env[^/]*|[^/]*credentials?[^/]*|[^/]*cookies?[^/]*)(?:/|$)",
        re.IGNORECASE,
    )
    for stage, copy in _all_copy_specs(_parse_dockerfile(dockerfile)):
        if copy.from_stage is not None:
            continue
        for source in copy.sources:
            assert not forbidden.search(_normalized_source(source)), (
                f"{dockerfile.name} stage {stage.name} copies forbidden source {source!r}"
            )
