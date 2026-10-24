from __future__ import annotations

import ast
import hashlib
import json
import sqlite3
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


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )


def _recovery_fixture(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    raw = tmp_path / "raw"
    raw.mkdir()
    data = raw / "data_pages.jsonl"
    data.write_text(
        '{"site":"res1999","pageid":1,"revid":2,'
        '"title":"Data:Item/1.json","content":"{}",'
        '"content_sha256":"' + hashlib.sha256(b"{}").hexdigest() + '",'
        '"json_valid":true}\n',
        encoding="utf-8",
    )
    state = raw / "crawl_state.sqlite"
    with sqlite3.connect(state) as connection:
        connection.execute("CREATE TABLE crawl_runs (id INTEGER PRIMARY KEY)")

    manifest = tmp_path / "recovery/manifest.json"
    audit = tmp_path / "recovery/audit.json"
    apply = tmp_path / "recovery/apply.json"
    files = {
        "data_pages.jsonl": {
            "size": data.stat().st_size,
            "sha256": _sha256(data),
            "rows": 1,
            "invalid_payload_rows": 0,
        },
        "crawl_state.sqlite": {
            "size": state.stat().st_size,
            "sha256": _sha256(state),
        },
    }
    _write_json(
        manifest,
        {
            "schema_version": "huiji-source-recovery/v1",
            "snapshot_id": "cli-fixture",
            "files": files,
            "recover": ["data_pages.jsonl", "crawl_state.sqlite"],
        },
    )
    _write_json(
        audit,
        {
            "status": "ready",
            "snapshot_id": "cli-fixture",
            "invalid_payload_rows": 0,
        },
    )
    _write_json(
        apply,
        {
            "status": "completed",
            "snapshot_id": "cli-fixture",
            "files": {
                name: {
                    "status": "recovered",
                    "size": details["size"],
                    "sha256": details["sha256"],
                }
                for name, details in files.items()
            },
        },
    )
    return raw, manifest, audit, apply


def _candidate_args(
    tmp_path: Path,
    manifest: Path,
    audit: Path,
    apply: Path,
    *,
    build_version: str = "candidate-a",
    run_name: str = "run",
) -> list[str]:
    return [
        "candidate",
        "--build-version",
        build_version,
        "--fidelity-baseline",
        str(tmp_path / "missing-baseline.json"),
        "--expected-fidelity-baseline-sha256",
        "a" * 64,
        "--run-dir",
        str(tmp_path / run_name),
        "--raw-root",
        str(tmp_path / "raw"),
        "--processed-root",
        str(tmp_path / "processed"),
        "--recovery-manifest",
        str(manifest),
        "--recovery-audit-receipt",
        str(audit),
        "--recovery-apply-receipt",
        str(apply),
    ]


def test_candidate_cli_builds_explicit_request_and_returns_blocked_exit_code(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    captured = {}
    monkeypatch.setattr(cli, "get_config", lambda: _config(tmp_path))
    manifest = tmp_path / "recovery/manifest.json"
    audit = tmp_path / "recovery/audit.json"
    apply = tmp_path / "recovery/apply.json"

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
    code = cli.main(_candidate_args(tmp_path, manifest, audit, apply))

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
    assert request.recovery_manifest_path == manifest
    assert request.recovery_audit_receipt_path == audit
    assert request.recovery_apply_receipt_path == apply


@pytest.mark.parametrize(
    "missing_option",
    [
        "--recovery-manifest",
        "--recovery-audit-receipt",
        "--recovery-apply-receipt",
    ],
)
def test_candidate_cli_requires_every_recovery_evidence_path_before_builder(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    missing_option: str,
) -> None:
    monkeypatch.setattr(
        HuijiCorpusBuilder,
        "build_candidate",
        lambda *_args, **_kwargs: pytest.fail("builder ran without required recovery evidence"),
    )
    args = _candidate_args(
        tmp_path,
        tmp_path / "manifest.json",
        tmp_path / "audit.json",
        tmp_path / "apply.json",
    )
    option_index = args.index(missing_option)
    del args[option_index : option_index + 2]

    with pytest.raises(SystemExit) as error:
        cli.main(args)

    assert error.value.code == 2


def test_cli_rejects_unpaired_pinned_evidence_before_builder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli, "get_config", lambda: _config(tmp_path))
    monkeypatch.setattr(
        HuijiCorpusBuilder,
        "build_candidate",
        lambda *_args, **_kwargs: pytest.fail("builder ran with unpinned evidence"),
    )
    args = _candidate_args(
        tmp_path,
        tmp_path / "manifest.json",
        tmp_path / "audit.json",
        tmp_path / "apply.json",
    )
    args.extend(["--minio-inventory", str(tmp_path / "inventory.json")])
    code = cli.main(args)
    assert code == 2


def test_candidate_cli_real_builder_distinguishes_invalid_and_valid_recovery(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    raw, manifest, audit, apply = _recovery_fixture(tmp_path)
    assert raw == tmp_path / "raw"
    monkeypatch.setattr(cli, "get_config", lambda: _config(tmp_path))
    invalid_audit = tmp_path / "recovery/invalid-audit.json"
    _write_json(
        invalid_audit,
        {
            "status": "ready",
            "snapshot_id": "different-snapshot",
            "invalid_payload_rows": 0,
        },
    )

    invalid_code = cli.main(
        _candidate_args(
            tmp_path,
            manifest,
            invalid_audit,
            apply,
            build_version="candidate-invalid",
            run_name="invalid-run",
        )
    )
    invalid_payload = json.loads(capsys.readouterr().out)

    assert invalid_code == 3
    assert invalid_payload["state"] == "blocked"
    assert invalid_payload["blockers"] == ["source_recovery_invalid"]

    valid_code = cli.main(
        _candidate_args(
            tmp_path,
            manifest,
            audit,
            apply,
            build_version="candidate-valid",
            run_name="valid-run",
        )
    )
    valid_payload = json.loads(capsys.readouterr().out)

    assert valid_code == 3
    assert valid_payload["state"] == "blocked"
    assert valid_payload["blockers"] == ["fidelity_baseline_missing"]
    assert "source_recovery_invalid" not in valid_payload["blockers"]
    assert not (_config(tmp_path).huiji.processed_root / "active_build.v1.json").exists()


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
