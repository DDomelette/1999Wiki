from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pytest
from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import canonicalize_name


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_INPUT = ROOT / "requirements" / "runtime.in"
DEV_INPUT = ROOT / "requirements" / "dev.in"
RUNTIME_LOCK = ROOT / "requirements" / "runtime.lock.txt"
DEV_LOCK = ROOT / "requirements" / "dev.lock.txt"
ROOT_REQUIREMENTS = ROOT / "requirements.txt"
LOCK_WITHOUT_JIEBA_SHA256 = {
    RUNTIME_LOCK: "b0f131f2ef206fafeec2a442014390e8117fdcd8714de54b982be601452f49a5",
    DEV_LOCK: "fc1d06a6ccf46bf92e1396023d307cf63477d56bd3f14ea4984627d61843c02e",
}

ALLOWED_RUNTIME_DIRECT = {
    "fastapi",
    "jieba",
    "langchain-core",
    "langchain-openai",
    "minio",
    "pydantic",
    "pymilvus",
    "pymysql",
    "python-dotenv",
    "pyyaml",
    "starlette",
    "typing-extensions",
    "uvicorn",
}
REQUIRED_DEV_DIRECT = {
    "httpx",
    "packaging",
    "pip",
    "pip-tools",
    "psutil",
    "pytest",
    "pytest-asyncio",
    "requests",
    "ruamel-yaml",
}
FORBIDDEN_RUNTIME_PACKAGES = {
    "chromadb",
    "gradio",
    "langchain-chroma",
    "langchain-community",
    "langchain-text-splitters",
    "pip",
    "pip-tools",
    "playwright",
    "pytest",
    "streamlit",
}


def _normalized(name: str) -> str:
    return canonicalize_name(name)


def _exact_pin(requirement: Requirement) -> str:
    specifiers = list(requirement.specifier)
    assert requirement.url is None, f"URL requirement is not locked: {requirement}"
    assert requirement.marker is None, f"Marker is not locked for Linux: {requirement}"
    assert len(specifiers) == 1, f"Requirement needs one exact pin: {requirement}"
    specifier = specifiers[0]
    assert specifier.operator == "==" and "*" not in specifier.version, (
        f"Requirement needs an exact == pin: {requirement}"
    )
    return specifier.version


def _requirement(line: str, path: Path) -> Requirement:
    try:
        return Requirement(line)
    except InvalidRequirement as exc:
        raise AssertionError(f"Invalid requirement in {path}: {line!r}") from exc


def _parse_input(
    path: Path,
    *,
    allowed_include: Path | None = None,
) -> tuple[dict[str, Requirement], dict[str, Requirement], tuple[Path, ...]]:
    direct: dict[str, Requirement] = {}
    included: dict[str, Requirement] = {}
    includes: list[Path] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = re.sub(r"\s+#.*$", "", raw_line).strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("-"):
            include_match = re.fullmatch(r"-r\s+(.+)", line)
            assert include_match is not None, f"Unsupported option/editable in {path}: {line!r}"
            include_path = (path.parent / include_match.group(1)).resolve()
            assert allowed_include is not None, f"Includes are not allowed in {path}: {line!r}"
            assert include_path == allowed_include.resolve(), (
                f"Unapproved include in {path}: {line!r}"
            )
            assert not includes, f"Only one include is allowed in {path}"
            include_direct, include_nested, nested_includes = _parse_input(include_path)
            assert not include_nested and not nested_includes
            included.update(include_direct)
            includes.append(include_path)
            continue

        requirement = _requirement(line, path)
        name = _normalized(requirement.name)
        assert name not in direct, f"Duplicate direct requirement in {path}: {name}"
        direct[name] = requirement
    return direct, included, tuple(includes)


def _parse_lock(path: Path) -> dict[str, Requirement]:
    locked: dict[str, Requirement] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        assert not line.startswith("-"), f"Lock contains an index/option directive: {line!r}"
        requirement = _requirement(line, path)
        name = _normalized(requirement.name)
        assert name not in locked, f"Duplicate lock requirement in {path}: {name}"
        _exact_pin(requirement)
        locked[name] = requirement
    return locked


def _lock_without_jieba(path: Path) -> bytes:
    data = path.read_bytes()
    entry = b"jieba==0.42.1\n    # via -r requirements/runtime.in\n"
    assert data.count(entry) == 1, f"Expected one canonical Jieba lock entry in {path}"
    return data.replace(entry, b"")


def test_input_parser_normalizes_names_and_extras(tmp_path: Path) -> None:
    requirements = tmp_path / "requirements.in"
    requirements.write_text(
        "LangChain_Core[TRACING]==1.4.8  # reason\npython_dotenv==1.2.2\n",
        encoding="utf-8",
    )

    direct, included, includes = _parse_input(requirements)

    assert set(direct) == {"langchain-core", "python-dotenv"}
    assert {_normalized(extra) for extra in direct["langchain-core"].extras} == {"tracing"}
    assert not included
    assert not includes


@pytest.mark.parametrize(
    "unsupported",
    [
        "--index-url https://example.invalid/simple",
        "--trusted-host example.invalid",
        "-e ../editable",
        "-r shared.in",
    ],
)
def test_input_parser_rejects_unapproved_control_lines(
    tmp_path: Path,
    unsupported: str,
) -> None:
    requirements = tmp_path / "requirements.in"
    requirements.write_text(f"{unsupported}\n", encoding="utf-8")

    with pytest.raises(AssertionError):
        _parse_input(requirements)


def test_runtime_input_is_the_exact_direct_linux_boundary() -> None:
    direct, included, includes = _parse_input(RUNTIME_INPUT)

    assert set(direct) == ALLOWED_RUNTIME_DIRECT
    assert {
        name: {_normalized(extra) for extra in requirement.extras}
        for name, requirement in direct.items()
        if requirement.extras
    } == {"uvicorn": {"standard"}}
    assert not included
    assert not includes
    for requirement in direct.values():
        _exact_pin(requirement)
    assert _exact_pin(direct["jieba"]) == "0.42.1"


def test_development_input_has_one_runtime_include_and_exact_tool_pins() -> None:
    direct, included, includes = _parse_input(
        DEV_INPUT,
        allowed_include=RUNTIME_INPUT,
    )

    assert set(direct) == REQUIRED_DEV_DIRECT
    assert set(included) == ALLOWED_RUNTIME_DIRECT
    assert includes == (RUNTIME_INPUT.resolve(),)
    for requirement in direct.values():
        _exact_pin(requirement)
    assert _exact_pin(direct["pip"]) == "25.2"
    assert _exact_pin(direct["pip-tools"]) == "7.5.1"


def test_linux_runtime_lock_is_pinned_and_excludes_non_runtime_packages() -> None:
    locked = _parse_lock(RUNTIME_LOCK)

    assert locked.keys().isdisjoint(FORBIDDEN_RUNTIME_PACKAGES)
    assert "setuptools" in locked
    assert "uvloop" in locked
    assert "httptools" in locked
    assert "watchfiles" in locked
    assert "pip" not in locked
    assert "pip-tools" not in locked
    assert _exact_pin(locked["jieba"]) == "0.42.1"


def test_linux_development_lock_contains_the_pinned_compiler() -> None:
    locked = _parse_lock(DEV_LOCK)

    assert _exact_pin(locked["pip"]) == "25.2"
    assert _exact_pin(locked["pip-tools"]) == "7.5.1"
    assert _exact_pin(locked["jieba"]) == "0.42.1"
    assert "setuptools" in locked


def test_jieba_is_the_only_runtime_and_development_lock_delta() -> None:
    for path, expected_sha256 in LOCK_WITHOUT_JIEBA_SHA256.items():
        assert hashlib.sha256(_lock_without_jieba(path)).hexdigest() == expected_sha256


def test_root_requirements_includes_only_the_development_lock() -> None:
    assert ROOT_REQUIREMENTS.read_text(encoding="utf-8").splitlines() == [
        "-r requirements/dev.lock.txt"
    ]
