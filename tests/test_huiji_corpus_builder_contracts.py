from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

from src.huiji_rag.build.contracts import (
    BuildState,
    CorpusBuildRequest,
    CorpusBuildResult,
)
from src.huiji_rag.build.orchestrator import HuijiCorpusBuilder
import src.huiji_rag.build.orchestrator as orchestrator_module
import src.huiji_rag.build.source_inventory as source_inventory_module


def _request(tmp_path: Path, **overrides: object) -> CorpusBuildRequest:
    values: dict[str, object] = {
        "build_version": "crawler-v3-test",
        "raw_root": tmp_path / "raw",
        "processed_root": tmp_path / "processed",
        "run_dir": tmp_path / "evidence",
        "fidelity_baseline_path": tmp_path / "baseline.json",
        "expected_fidelity_baseline_sha256": "a" * 64,
        "configured_build_version": "dev",
    }
    values.update(overrides)
    return CorpusBuildRequest(**values)


@pytest.mark.parametrize(
    "build_version",
    ["dev", "UPPER", "bad.dot", "bad/slash", "_prefix", "a" * 65],
)
def test_request_rejects_reserved_or_unsafe_build_ids_before_source_parse(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    build_version: str,
) -> None:
    monkeypatch.setattr(
        orchestrator_module,
        "capture_corpus_source_inventory",
        lambda *_args, **_kwargs: pytest.fail("source parsing started before request rejection"),
    )

    with pytest.raises(ValueError):
        HuijiCorpusBuilder().inspect_source(_request(tmp_path, build_version=build_version))


def test_request_rejects_existing_configured_and_active_roots(tmp_path: Path) -> None:
    processed = tmp_path / "processed"
    processed.mkdir()
    existing = processed / "crawler-v3-existing"
    existing.mkdir()
    with pytest.raises(FileExistsError, match="already exists"):
        HuijiCorpusBuilder().validate_request(
            _request(tmp_path, build_version=existing.name, processed_root=processed)
        )

    with pytest.raises(ValueError, match="configured"):
        HuijiCorpusBuilder().validate_request(
            _request(
                tmp_path,
                build_version="crawler-v3-configured",
                processed_root=processed,
                configured_build_version="crawler-v3-configured",
            )
        )

    pointer = processed / "active_build.v1.json"
    pointer.write_text(json.dumps({"build_version": "crawler-v3-active"}), encoding="utf-8")
    with pytest.raises(ValueError, match="active"):
        HuijiCorpusBuilder().validate_request(
            _request(tmp_path, build_version="crawler-v3-active", processed_root=processed)
        )


def test_build_result_state_is_closed_and_payload_is_immutable(tmp_path: Path) -> None:
    result = CorpusBuildResult(
        build_version="crawler-v3-test",
        build_root=tmp_path,
        state=BuildState.BLOCKED,
        blockers=("z", "a", "a"),
        row_counts={"child": 2},
    )
    assert result.state.value == "blocked"
    assert result.blockers == ("a", "z")
    with pytest.raises(TypeError):
        result.row_counts["child"] = 3  # type: ignore[index]
    with pytest.raises(ValueError, match="BuildState"):
        CorpusBuildResult(
            build_version="crawler-v3-test",
            build_root=tmp_path,
            state="ready",  # type: ignore[arg-type]
        )


def test_contract_and_inventory_modules_have_no_runtime_writer_imports() -> None:
    text = "\n".join(
        [
            inspect.getsource(orchestrator_module),
            inspect.getsource(source_inventory_module),
        ]
    )
    import_lines = [line.casefold() for line in text.splitlines() if line.startswith(("import ", "from "))]
    assert not any(
        token in line
        for line in import_lines
        for token in ("pymilvus", "minio", "huiji_wiki", "pymysql")
    )
