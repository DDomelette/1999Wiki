from __future__ import annotations

import hashlib
import json
from pathlib import Path

from src.rag_eval.client import ObservedExchange, TimingObservation
from src.rag_eval.contracts import Severity
from src.rag_eval.conversation import ConversationTrackResult
from src.rag_eval.inventory import (
    ChildRecord,
    EntityRecord,
    EvaluationInventory,
    MilvusSnapshot,
)


def _inventory():
    entities = {}
    children = {}
    for index, intents in enumerate((("skill", "voice"), ("item", "culture"))):
        entity_id = f"entity-{index}"
        name = f"测试实体{index}"
        by_intent = {}
        for intent in intents:
            child_id = f"fixture:{entity_id}/{intent}:1"
            by_intent[intent] = (child_id,)
            children[child_id] = ChildRecord(
                child_id=child_id,
                parent_id=f"fixture:{entity_id}/{intent}",
                entity_id=entity_id,
                entity_name=name,
                entity_type="character",
                category="character",
                section_kind=intent,
                title=intent,
                route_tags=(intent,),
                text="controlled evidence",
                media_ids=(),
            )
        entities[entity_id] = EntityRecord(
            entity_id=entity_id,
            entity_name=name,
            entity_type="character",
            category="character",
            aliases=(),
            child_ids_by_intent=by_intent,
            media_ids_by_type={},
        )
    return EvaluationInventory(
        build_version="fixture",
        entities=entities,
        children=children,
        media={},
        parent_ids=tuple(sorted({child.parent_id for child in children.values()})),
        sha256="a" * 64,
    )


def _snapshot():
    return MilvusSnapshot(
        collection_name="fixture",
        schema_sha256="b" * 64,
        row_count=2,
        primary_field="id",
        primary_id_count=2,
        primary_ids_sha256="c" * 64,
        load_state={"state": "Loaded"},
        captured_at_utc="2026-07-14T00:00:00Z",
    )


def _exchange(*, status="new", entity=None):
    payload = {"memory": {"status": status, "turns_used": 0, "rewrite_mode": "none"}}
    return ObservedExchange(
        case_id="probe",
        endpoint="/ask",
        success=True,
        status_code=200,
        route={"entity": entity},
        sources=(),
        media=(),
        media_panels=(),
        failure_actions=(),
        answer="controlled",
        timing=TimingObservation("2026-07-14T00:00:00Z", None, None, 1.0),
        raw=payload,
    )


class _Client:
    def __init__(self, exchange):
        self.exchange = exchange

    def ask(self, case, *, conversation_id=None):
        return self.exchange


class _Process:
    def __init__(self):
        self.terminate_count = 0
        self.wait_count = 0

    def terminate(self):
        self.terminate_count += 1

    def wait(self, timeout=None):
        self.wait_count += 1
        return 0


def test_run_writes_canonical_evidence_without_runtime_conversation_ids(tmp_path, monkeypatch):
    from scripts import verify_rag_conversation_memory as module

    inventory = _inventory()
    snapshot = _snapshot()
    deps = module.VerifierDependencies(
        config_loader=lambda: object(),
        inventory_loader=lambda _cfg: inventory,
        snapshot_loader=lambda _cfg: snapshot,
        artifact_loader=lambda _cfg: {"artifact": {"size": 1, "sha256": "d" * 64}},
        client_factory=lambda _url: object(),
        track_evaluator=lambda _client, tracks: tuple(
            ConversationTrackResult(track.track_id, Severity.PASS, {"ok": True}, {})
            for track in tracks
        ),
        global_evaluator=lambda _client, _tracks: ConversationTrackResult(
            "conversation-global-fixture",
            Severity.PASS,
            {"ok": True},
            {},
        ),
    )
    monkeypatch.setattr(module, "_dependencies", deps)

    exit_code = module.main([
        "run",
        "--base-url", "http://example",
        "--seed", "20260713",
        "--output-root", str(tmp_path),
    ])

    assert exit_code == 0
    summary = json.loads(next(tmp_path.rglob("summary.v1.json")).read_text(encoding="utf-8"))
    assert summary["schema_version"] == "rag_conversation_memory.summary/v1"
    assert summary["global_severity"] in {"PASS", "SEV-4", "SEV-3"}
    assert "conversation_id" not in json.dumps(summary)
    run_dir = next(path.parent for path in tmp_path.rglob("run_manifest.v1.json"))
    assert {path.name for path in run_dir.iterdir()} == {
        "run_manifest.v1.json",
        "sample_manifest.v1.jsonl",
        "track_results.v1.jsonl",
        "summary.v1.json",
        "p0-coverage.partial.v1.json",
        "artifacts.pre.v1.json",
        "artifacts.post.v1.json",
        "milvus.pre.v1.json",
        "milvus.post.v1.json",
    }


def test_restart_probe_uses_two_processes_and_observes_memory_loss(tmp_path, monkeypatch):
    from scripts import verify_rag_conversation_memory as module

    processes = []
    clients = iter([
        _Client(_exchange(status="new", entity="测试实体0")),
        _Client(_exchange(status="new", entity=None)),
    ])

    def process_factory(*args, **kwargs):
        process = _Process()
        processes.append(process)
        return process

    deps = module.VerifierDependencies(
        config_loader=lambda: object(),
        inventory_loader=lambda _cfg: _inventory(),
        snapshot_loader=lambda _cfg: _snapshot(),
        artifact_loader=lambda _cfg: {},
        client_factory=lambda _url: next(clients),
        track_evaluator=lambda _client, _tracks: (),
        process_factory=process_factory,
        health_check=lambda _url: True,
        sleep=lambda _seconds: None,
    )
    monkeypatch.setattr(module, "_dependencies", deps)

    exit_code = module.main([
        "restart-probe",
        "--host", "127.0.0.1",
        "--port", "8011",
        "--seed", "20260713",
        "--output-root", str(tmp_path),
    ])

    assert exit_code == 0
    report = json.loads(next(tmp_path.rglob("restart-probe.v1.json")).read_text(encoding="utf-8"))
    assert report["after_restart"]["memory_status"] == "new"
    assert report["after_restart"]["inherited_entity"] is None
    assert len(processes) == 2
    assert all(process.terminate_count == 1 for process in processes)
    assert all(process.wait_count == 1 for process in processes)


def _write_coverage(root: Path, ids: list[str]):
    root.mkdir(parents=True, exist_ok=True)
    evidence = root / "evidence.bin"
    evidence.write_bytes(b"evidence")
    digest = hashlib.sha256(evidence.read_bytes()).hexdigest()
    payload = {
        "coverage": [{
            "requirement_id": requirement_id,
            "status": "passed",
            "evidence_path": "evidence.bin",
            "sha256": digest,
            "observed": "passed",
            "expected": "passed",
            "failure_behavior": "block",
        } for requirement_id in ids],
    }
    (root / "coverage.v1.json").write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )


def test_finalize_coverage_requires_hash_pinned_evidence_from_every_gate(tmp_path):
    from scripts import verify_rag_conversation_memory as module

    ids = list(module.load_requirement_ids()[0])
    roots = [tmp_path / name for name in ("conversation", "gate", "full", "playwright")]
    chunks = [ids[index::4] for index in range(4)]
    for root, chunk in zip(roots, chunks):
        _write_coverage(root, chunk)

    exit_code = module.main([
        "finalize-coverage",
        "--conversation-run", str(roots[0]),
        "--gate-root", str(roots[1]),
        "--full-chain-run", str(roots[2]),
        "--playwright-report", str(roots[3]),
    ])

    assert exit_code == 0
    final = json.loads((roots[0] / "p0-coverage.final.v1.json").read_text(encoding="utf-8"))
    assert len(final["coverage"]) == 82
    assert all(item["status"] == "passed" for item in final["coverage"])


def test_finalize_missing_playwright_creates_no_final_file(tmp_path):
    from scripts import verify_rag_conversation_memory as module

    existing = [tmp_path / name for name in ("conversation", "gate", "full")]
    for root in existing:
        _write_coverage(root, [])

    exit_code = module.main([
        "finalize-coverage",
        "--conversation-run", str(existing[0]),
        "--gate-root", str(existing[1]),
        "--full-chain-run", str(existing[2]),
        "--playwright-report", str(tmp_path / "missing"),
    ])

    assert exit_code != 0
    assert not (existing[0] / "p0-coverage.final.v1.json").exists()
