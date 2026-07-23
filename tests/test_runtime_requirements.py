from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_INPUT = ROOT / "requirements" / "runtime.in"
DEV_INPUT = ROOT / "requirements" / "dev.in"
ROOT_REQUIREMENTS = ROOT / "requirements.txt"

REQUIRED_RUNTIME_PACKAGES = {
    "fastapi",
    "langchain-core",
    "langchain-openai",
    "minio",
    "pydantic",
    "pymilvus",
    "pymysql",
    "python-dotenv",
    "pyyaml",
    "uvicorn",
}
FORBIDDEN_RUNTIME_PACKAGES = {
    "chromadb",
    "gradio",
    "langchain-chroma",
    "pip",
    "pip-tools",
    "playwright",
    "pytest",
    "streamlit",
}

_REQUIREMENT_NAME = re.compile(
    r"^(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)"
    r"(?:\[[A-Za-z0-9._,-]+\])?"
    r"(?=\s*(?:@|[<>=!~;]|$))"
)


def _normalize_package_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _requirement_names(path: Path) -> set[str]:
    names: set[str] = set()
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = re.sub(r"\s+#.*$", "", raw_line).strip()
        if not line or line.startswith(("#", "-")):
            continue

        match = _REQUIREMENT_NAME.match(line)
        if match is None:
            raise AssertionError(f"Unrecognized requirement line in {path}: {raw_line!r}")
        names.add(_normalize_package_name(match.group("name")))
    return names


def _requirement_specifiers(path: Path) -> dict[str, str]:
    specifiers: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = re.sub(r"\s+#.*$", "", raw_line).strip()
        if not line or line.startswith(("#", "-")):
            continue

        match = _REQUIREMENT_NAME.match(line)
        if match is None:
            raise AssertionError(f"Unrecognized requirement line in {path}: {raw_line!r}")
        name = _normalize_package_name(match.group("name"))
        specifiers[name] = line[match.end() :].strip()
    return specifiers


def test_requirement_parser_handles_supported_input_syntax(tmp_path: Path) -> None:
    requirements = tmp_path / "requirements.in"
    requirements.write_text(
        "\n".join(
            [
                "# comment",
                "--index-url https://example.invalid/simple",
                "-r shared.in",
                "LangChain_Core[tracing]>=0.3 ; python_version >= '3.11'  # reason",
                "python_dotenv",
            ]
        ),
        encoding="utf-8",
    )

    assert _requirement_names(requirements) == {
        "langchain-core",
        "python-dotenv",
    }


def test_runtime_input_contains_only_the_runtime_boundary() -> None:
    runtime_packages = _requirement_names(RUNTIME_INPUT)

    assert REQUIRED_RUNTIME_PACKAGES <= runtime_packages
    assert runtime_packages.isdisjoint(FORBIDDEN_RUNTIME_PACKAGES)


def test_root_requirements_includes_only_the_development_lock() -> None:
    assert ROOT_REQUIREMENTS.read_text(encoding="utf-8").splitlines() == [
        "-r requirements/dev.lock.txt"
    ]


def test_development_input_pins_the_lock_compiler_toolchain() -> None:
    specifiers = _requirement_specifiers(DEV_INPUT)

    assert specifiers["pip"] == "==25.2"
    assert specifiers["pip-tools"] == "==7.5.1"
