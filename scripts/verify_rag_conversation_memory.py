from __future__ import annotations

# ruff: noqa: E402 -- direct script execution needs PROJECT_ROOT on sys.path.

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Mapping, Sequence

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.config import get_config
from src.huiji_rag.io import build_paths
from src.rag_eval.client import RagEvalClient
from src.rag_eval.conversation import (
    ConversationTrack,
    ConversationTrackResult,
    build_conversation_tracks,
    evaluate_conversation_global_checks,
    evaluate_conversation_tracks,
)
from src.rag_eval.contracts import Severity
from src.rag_eval.inventory import (
    EvaluationInventory,
    MilvusSnapshot,
    capture_inventory,
    capture_milvus_snapshot,
    compare_snapshots,
)


SPEC_PATH = (
    PROJECT_ROOT
    / "docs"
    / "superpowers"
    / "specs"
    / "2026-07-13-rag-short-term-conversation-memory-design.md"
)
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "eval" / "rag_conversation_memory"


def _default_artifact_loader(cfg: object) -> Mapping[str, object]:
    paths = build_paths(cfg)
    result: dict[str, object] = {}
    for name in ("parent_blocks", "child_blocks", "media_assets", "build_manifest"):
        path = Path(getattr(paths, name))
        if path.is_file():
            result[name] = {
                "size": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
    return result


def _default_health_check(base_url: str) -> bool:
    try:
        response = requests.get(f"{base_url}/health", timeout=(2.0, 5.0))
        return response.status_code == 200 and response.json().get("status") == "ok"
    except Exception:
        return False


@dataclass(frozen=True)
class VerifierDependencies:
    config_loader: Callable[[], object] = get_config
    inventory_loader: Callable[[object], EvaluationInventory] = capture_inventory
    snapshot_loader: Callable[[object], MilvusSnapshot] = capture_milvus_snapshot
    artifact_loader: Callable[[object], Mapping[str, object]] = _default_artifact_loader
    client_factory: Callable[[str], object] = RagEvalClient
    track_evaluator: Callable[
        [object, Sequence[ConversationTrack]],
        Sequence[ConversationTrackResult],
    ] = evaluate_conversation_tracks
    global_evaluator: Callable[
        [object, Sequence[ConversationTrack]],
        ConversationTrackResult,
    ] = evaluate_conversation_global_checks
    process_factory: Callable[..., object] = subprocess.Popen
    health_check: Callable[[str], bool] = _default_health_check
    sleep: Callable[[float], None] = time.sleep
    monotonic: Callable[[], float] = time.monotonic


_dependencies = VerifierDependencies()


def _canonical_json(payload: Mapping[str, object]) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ) + "\n"


def _write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(text, encoding="utf-8", newline="\n")
    temporary.replace(path)


def _write_json(path: Path, payload: Mapping[str, object]) -> None:
    _write_atomic(path, _canonical_json(payload))


def _write_jsonl(path: Path, rows: Sequence[Mapping[str, object]]) -> None:
    text = "".join(_canonical_json(row) for row in rows)
    _write_atomic(path, text)


def _new_run_directory(output_root: Path) -> Path:
    output_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    for _attempt in range(32):
        candidate = output_root / f"{stamp}-{uuid.uuid4().hex[:8]}"
        try:
            candidate.mkdir()
            return candidate
        except FileExistsError:
            continue
    raise RuntimeError("unable to allocate a unique evidence directory")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_requirement_ids() -> tuple[tuple[str, ...], tuple[str, ...]]:
    text = SPEC_PATH.read_text(encoding="utf-8")
    p0 = tuple(sorted(set(re.findall(r"`([A-Z-]+P0-\d{2})`", text))))
    deferred = tuple(sorted(set(re.findall(r"`([A-Z-]+P[12]-\d{2})`", text))))
    if len(p0) != 82:
        raise ValueError(f"expected 82 P0 requirement IDs, found {len(p0)}")
    return p0, deferred


def _track_manifest(track: ConversationTrack) -> dict[str, object]:
    return {
        "track_id": track.track_id,
        "initial_entity_id": track.initial_entity_id,
        "initial_entity_name": track.initial_entity_name,
        "initial_query": track.initial_query,
        "follow_up_query": track.follow_up_query,
        "multi_intent_query": track.multi_intent_query,
        "switch_query": track.switch_query,
        "switch_entity_id": track.switch_entity_id,
        "switch_entity_name": track.switch_entity_name,
        "expected_follow_intents": [track.follow_intent],
        "expected_multi_intents": list(track.multi_intents),
        **dict(track.derivation),
    }


def _track_result(result: ConversationTrackResult) -> dict[str, object]:
    return {
        "track_id": result.track_id,
        "severity": result.severity.value,
        "checks": dict(result.checks),
        "observations": dict(result.observations),
    }


def _partial_coverage(
    run_dir: Path,
    *,
    passed: bool,
) -> dict[str, object]:
    p0_ids, deferred_ids = load_requirement_ids()
    evidence_path = run_dir / "track_results.v1.jsonl"
    evidence_hash = _sha256(evidence_path)
    executed = {
        "EVAL-MEM-P0-10",
        "GATE-MEM-P0-01",
        "GATE-MEM-P0-02",
        "GATE-MEM-P0-03",
        "GATE-MEM-P0-04",
        "GATE-MEM-P0-05",
        "GATE-MEM-P0-06",
        "GATE-MEM-P0-08",
        "SAFETY-MEM-P0-04",
    }
    coverage = []
    for requirement_id in p0_ids:
        status = ("passed" if passed else "failed") if requirement_id in executed else "pending"
        coverage.append({
            "requirement_id": requirement_id,
            "status": status,
            "evidence_path": evidence_path.name if requirement_id in executed else "",
            "sha256": evidence_hash if requirement_id in executed else "",
            "observed": "dynamic tracks executed" if requirement_id in executed else "pending later gate",
            "expected": "approved P0 contract",
            "failure_behavior": "block final coverage" if status != "passed" else "none",
        })
    return {
        "schema_version": "rag_conversation_memory.coverage_partial/v1",
        "coverage": coverage,
        "deferred": [
            {"requirement_id": requirement_id, "status": "deferred"}
            for requirement_id in deferred_ids
        ],
    }


def run_verifier(base_url: str, seed: int, output_root: Path) -> int:
    run_dir = _new_run_directory(output_root)
    cfg = _dependencies.config_loader()
    inventory = _dependencies.inventory_loader(cfg)
    pre_artifacts = dict(_dependencies.artifact_loader(cfg))
    pre_snapshot = _dependencies.snapshot_loader(cfg)
    tracks = build_conversation_tracks(inventory, seed=seed)
    client = _dependencies.client_factory(base_url)
    track_results = tuple(_dependencies.track_evaluator(client, tracks))
    global_result = _dependencies.global_evaluator(client, tracks)
    results = (*track_results, global_result)
    post_artifacts = dict(_dependencies.artifact_loader(cfg))
    post_snapshot = _dependencies.snapshot_loader(cfg)

    artifact_equal = pre_artifacts == post_artifacts
    snapshot_changes = compare_snapshots(pre_snapshot, post_snapshot)
    result_pass = all(result.severity is Severity.PASS for result in results)
    passed = artifact_equal and not snapshot_changes and result_pass
    global_severity = Severity.PASS if passed else Severity.SEV1

    _write_json(run_dir / "artifacts.pre.v1.json", {
        "schema_version": "rag_conversation_memory.artifacts/v1",
        "artifacts": pre_artifacts,
    })
    _write_json(run_dir / "artifacts.post.v1.json", {
        "schema_version": "rag_conversation_memory.artifacts/v1",
        "artifacts": post_artifacts,
    })
    _write_json(run_dir / "milvus.pre.v1.json", pre_snapshot.to_json())
    _write_json(run_dir / "milvus.post.v1.json", post_snapshot.to_json())
    _write_jsonl(
        run_dir / "sample_manifest.v1.jsonl",
        [_track_manifest(track) for track in tracks],
    )
    _write_jsonl(
        run_dir / "track_results.v1.jsonl",
        [_track_result(result) for result in results],
    )
    _write_json(run_dir / "run_manifest.v1.json", {
        "schema_version": "rag_conversation_memory.run_manifest/v1",
        "seed": seed,
        "base_url": base_url,
        "inventory_sha256": inventory.sha256,
        "track_count": len(tracks),
        "result_count": len(results),
    })
    _write_json(run_dir / "summary.v1.json", {
        "schema_version": "rag_conversation_memory.summary/v1",
        "global_severity": global_severity.value,
        "track_count": len(tracks),
        "result_count": len(results),
        "failed_result_count": sum(
            result.severity is not Severity.PASS for result in results
        ),
        "artifact_equal": artifact_equal,
        "milvus_changes": snapshot_changes,
    })
    _write_json(
        run_dir / "p0-coverage.partial.v1.json",
        _partial_coverage(run_dir, passed=passed),
    )
    return 0 if passed else 1


def _memory_status(exchange: object) -> str:
    raw = getattr(exchange, "raw", {})
    memory = raw.get("memory") if isinstance(raw, Mapping) else None
    return str(memory.get("status") or "") if isinstance(memory, Mapping) else ""


def _route_entity(exchange: object) -> str | None:
    route = getattr(exchange, "route", {})
    value = route.get("entity") if isinstance(route, Mapping) else None
    return value if isinstance(value, str) and value else None


def _wait_healthy(base_url: str, timeout_seconds: float = 120.0) -> None:
    deadline = _dependencies.monotonic() + timeout_seconds
    while _dependencies.monotonic() < deadline:
        if _dependencies.health_check(base_url):
            return
        _dependencies.sleep(0.25)
    raise TimeoutError("isolated backend health check timed out")


def run_restart_probe(
    project_root: Path,
    host: str,
    port: int,
    seed: int,
    output_root: Path,
) -> int:
    run_dir = _new_run_directory(output_root)
    cfg = _dependencies.config_loader()
    track = build_conversation_tracks(
        _dependencies.inventory_loader(cfg),
        seed=seed,
        limit=2,
    )[0]
    controlled_id = str(uuid.uuid4())
    controlled_digest = hashlib.sha256(controlled_id.encode("ascii")).hexdigest()
    base_url = f"http://{host}:{port}"
    processes: list[object] = []
    stopped: set[int] = set()
    streams: list[object] = []

    def stop(process: object) -> None:
        marker = id(process)
        if marker in stopped:
            return
        stopped.add(marker)
        try:
            process.terminate()
        finally:
            process.wait(timeout=30)

    def start(index: int) -> object:
        stdout = (run_dir / f"process-{index}.stdout.log").open("w", encoding="utf-8")
        stderr = (run_dir / f"process-{index}.stderr.log").open("w", encoding="utf-8")
        streams.extend((stdout, stderr))
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        process = _dependencies.process_factory(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "backend.main:app",
                "--host",
                host,
                "--port",
                str(port),
            ],
            cwd=str(project_root),
            shell=False,
            creationflags=flags,
            stdout=stdout,
            stderr=stderr,
        )
        processes.append(process)
        return process

    try:
        first_process = start(1)
        _wait_healthy(base_url)
        first = _dependencies.client_factory(base_url).ask(
            _probe_case(track.track_id, "initial", track.initial_query),
            conversation_id=controlled_id,
        )
        stop(first_process)

        start(2)
        _wait_healthy(base_url)
        second = _dependencies.client_factory(base_url).ask(
            _probe_case(track.track_id, "after-restart", track.follow_up_query),
            conversation_id=controlled_id,
        )
        passed = (
            _memory_status(first) == "new"
            and _memory_status(second) == "new"
            and _route_entity(second) is None
        )
        report = {
            "schema_version": "rag_conversation_memory.restart_probe/v1",
            "controlled_id_sha256": controlled_digest,
            "before_restart": {
                "memory_status": _memory_status(first),
                "resolved_entity": _route_entity(first),
            },
            "after_restart": {
                "memory_status": _memory_status(second),
                "inherited_entity": _route_entity(second),
            },
            "passed": passed,
        }
        _write_json(run_dir / "restart-probe.v1.json", report)
        return 0 if passed else 1
    finally:
        for process in processes:
            try:
                stop(process)
            except Exception:
                pass
        for stream in streams:
            stream.close()


def _probe_case(track_id: str, suffix: str, query: str):
    from src.rag_eval.contracts import Difficulty, EvalCase

    return EvalCase(
        case_id=f"{track_id}-{suffix}",
        query=query,
        difficulty=Difficulty.D2,
        scenario="restart-probe",
    )


def _coverage_documents(root: Path) -> list[Path]:
    if root.is_file():
        return [root]
    return sorted(root.rglob("*.json")) if root.is_dir() else []


def finalize_coverage(
    conversation_run: Path,
    gate_root: Path,
    full_chain_run: Path,
    playwright_report: Path,
) -> int:
    roots = (conversation_run, gate_root, full_chain_run, playwright_report)
    if any(not root.exists() for root in roots):
        return 1
    merged: dict[str, dict[str, object]] = {}
    for root in roots:
        documents = _coverage_documents(root)
        if not documents:
            return 1
        for document in documents:
            try:
                payload = json.loads(document.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            entries = payload.get("coverage") if isinstance(payload, dict) else None
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                requirement_id = str(entry.get("requirement_id") or "")
                status = str(entry.get("status") or "")
                if not requirement_id or status != "passed":
                    if requirement_id and status == "failed":
                        merged[requirement_id] = dict(entry)
                    continue
                evidence_value = str(entry.get("evidence_path") or "")
                expected_hash = str(entry.get("sha256") or "")
                evidence = Path(evidence_value)
                if not evidence.is_absolute():
                    evidence = document.parent / evidence
                if not evidence.is_file() or _sha256(evidence) != expected_hash:
                    continue
                if merged.get(requirement_id, {}).get("status") != "failed":
                    merged[requirement_id] = dict(entry)

    p0_ids, deferred_ids = load_requirement_ids()
    if any(merged.get(requirement_id, {}).get("status") != "passed" for requirement_id in p0_ids):
        return 1
    final_path = conversation_run / "p0-coverage.final.v1.json"
    if final_path.exists():
        return 1
    payload = {
        "schema_version": "rag_conversation_memory.coverage_final/v1",
        "coverage": [merged[requirement_id] for requirement_id in p0_ids],
        "deferred": [
            {"requirement_id": requirement_id, "status": "deferred"}
            for requirement_id in deferred_ids
        ],
    }
    data = _canonical_json(payload).encode("utf-8")
    descriptor = os.open(final_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
    try:
        os.write(descriptor, data)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    run = subparsers.add_parser("run")
    run.add_argument("--base-url", required=True)
    run.add_argument("--seed", type=int, required=True)
    run.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)

    restart = subparsers.add_parser("restart-probe")
    restart.add_argument("--host", required=True)
    restart.add_argument("--port", type=int, required=True)
    restart.add_argument("--seed", type=int, required=True)
    restart.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)

    finalize = subparsers.add_parser("finalize-coverage")
    finalize.add_argument("--conversation-run", type=Path, required=True)
    finalize.add_argument("--gate-root", type=Path, required=True)
    finalize.add_argument("--full-chain-run", type=Path, required=True)
    finalize.add_argument("--playwright-report", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "run":
            return run_verifier(args.base_url, args.seed, args.output_root)
        if args.command == "restart-probe":
            return run_restart_probe(
                PROJECT_ROOT,
                args.host,
                args.port,
                args.seed,
                args.output_root,
            )
        return finalize_coverage(
            args.conversation_run,
            args.gate_root,
            args.full_chain_run,
            args.playwright_report,
        )
    except Exception as exc:
        print(f"conversation verifier failed: {type(exc).__name__}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
