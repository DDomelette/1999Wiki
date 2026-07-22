from __future__ import annotations

import ast
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import build_huiji_corpus as cli
from src.huiji_rag.build.contracts import BuildState, CorpusBuildResult
from src.huiji_rag.build.orchestrator import HuijiCorpusBuilder
from src.huiji_rag.builder import HuijiCorpusBuilder as FacadeCorpusBuilder


ROOT = Path(__file__).resolve().parents[1]


def _config(tmp_path: Path) -> SimpleNamespace:
    processed = tmp_path / "processed"
    return SimpleNamespace(
        huiji=SimpleNamespace(
            raw_root=tmp_path / "raw",
            processed_root=processed,
            build_version="dev",
            text_collection_name="active-text",
            asset_caption_collection_name="active-media",
        ),
        assets=SimpleNamespace(
            public_base_url="http://127.0.0.1:9002",
            bucket_name="reverse1999-assets",
            object_prefix="reverse1999",
        ),
        embedding=SimpleNamespace(provider="test", model="test-model"),
        vectorstore=SimpleNamespace(collection_name="active-text"),
    )


def test_candidate_cli_builds_explicit_request_and_returns_blocked_exit_code(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    captured = {}
    monkeypatch.setattr(cli, "get_config", lambda: _config(tmp_path))

    def build(_self: HuijiCorpusBuilder, request):
        captured["request"] = request
        return CorpusBuildResult(
            build_version=request.build_version,
            build_root=tmp_path / "processed/candidate-a",
            state=BuildState.BLOCKED,
            blockers=("test_gate",),
            row_counts={"parents": 1, "excluded": 2, "conflicts": 3},
        )

    monkeypatch.setattr(HuijiCorpusBuilder, "build_candidate", build)
    code = cli.main(
        [
            "candidate",
            "--build-version",
            "candidate-a",
            "--fidelity-baseline",
            str(tmp_path / "baseline.json"),
            "--expected-fidelity-baseline-sha256",
            "a" * 64,
            "--run-dir",
            str(tmp_path / "run"),
        ]
    )

    assert code == 3
    payload = json.loads(capsys.readouterr().out)
    assert payload["state"] == "blocked"
    assert payload["conflict_or_exclusion_counts"] == {
        "conflicts": 3,
        "excluded": 2,
    }
    request = captured["request"]
    assert request.project_root == cli.PROJECT_ROOT
    assert request.forbidden_collection_names == ("active-media", "active-text")


def test_cli_rejects_unpaired_pinned_evidence_before_builder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli, "get_config", lambda: _config(tmp_path))
    monkeypatch.setattr(
        HuijiCorpusBuilder,
        "build_candidate",
        lambda *_args, **_kwargs: pytest.fail("builder ran with unpinned evidence"),
    )
    code = cli.main(
        [
            "candidate",
            "--build-version",
            "candidate-a",
            "--fidelity-baseline",
            str(tmp_path / "baseline.json"),
            "--expected-fidelity-baseline-sha256",
            "a" * 64,
            "--run-dir",
            str(tmp_path / "run"),
            "--minio-inventory",
            str(tmp_path / "inventory.json"),
        ]
    )
    assert code == 2


def test_proposal_command_is_create_new_blocked_and_does_not_bootstrap_pointer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cfg = _config(tmp_path)
    monkeypatch.setattr(cli, "get_config", lambda: cfg)
    monkeypatch.setattr(
        HuijiCorpusBuilder,
        "verify_candidate",
        lambda *_args, **_kwargs: {
            "state": "ready_for_embedding",
            "row_counts": {},
            "semantic_corpus": {},
            "blockers": [],
        },
    )
    code = cli.main(
        [
            "proposal",
            "--proposal-id",
            "proposal-a",
            "--candidate-build-root",
            str(tmp_path / "candidate"),
            "--expected-build-manifest-sha256",
            "b" * 64,
            "--output-root",
            str(tmp_path / "proposals"),
        ]
    )

    assert code == 3
    payload = json.loads(capsys.readouterr().out)
    assert payload["allowed_for_activation_review"] is False
    assert "active_pointer_not_bootstrapped" in payload["blockers"]
    assert not (cfg.huiji.processed_root / "active_build.v1.json").exists()
    with pytest.raises(FileExistsError):
        cli._run_proposal(
            cli.build_parser().parse_args(
                [
                    "proposal",
                    "--proposal-id",
                    "proposal-a",
                    "--candidate-build-root",
                    str(tmp_path / "candidate"),
                    "--expected-build-manifest-sha256",
                    "b" * 64,
                    "--output-root",
                    str(tmp_path / "proposals"),
                ]
            )
        )


def test_single_public_full_builder_and_forbidden_writer_scan() -> None:
    assert FacadeCorpusBuilder is HuijiCorpusBuilder
    builder_classes: list[tuple[Path, str]] = []
    build_candidate_defs: list[Path] = []
    for path in (ROOT / "src").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == "HuijiCorpusBuilder":
                builder_classes.append((path, node.name))
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "build_candidate":
                build_candidate_defs.append(path)
    assert builder_classes == [
        (ROOT / "src/huiji_rag/build/orchestrator.py", "HuijiCorpusBuilder")
    ]
    assert build_candidate_defs == [ROOT / "src/huiji_rag/build/orchestrator.py"]

    scanned = [
        ROOT / "src/huiji_rag/build/orchestrator.py",
        ROOT / "scripts/build_huiji_corpus.py",
    ]
    imports: list[str] = []
    source = "\n".join(path.read_text(encoding="utf-8") for path in scanned)
    for path in scanned:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.append(node.module or "")
    assert not any(
        token in name.casefold()
        for name in imports
        for token in ("pymilvus", "pymysql", "huiji_wiki", "minio")
    )
    assert "write_text" not in source
    assert "active_build.v1.json.write" not in source
    assert "config/settings.yaml" not in source
    assert "config/provenance" not in source
