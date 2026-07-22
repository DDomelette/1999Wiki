from __future__ import annotations

import hashlib
import inspect
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.rag_eval.client import ObservedExchange, TimingObservation
from src.rag_eval.contracts import (
    Difficulty,
    EvalCase,
    EvaluationEvent,
    JudgeIdentity,
    Severity,
    load_thresholds,
)
from src.rag_eval.deterministic import DeterministicResult
from src.rag_eval.inventory import MilvusSnapshot, PreflightResult, ProtectedDataSnapshot
from src.rag_eval.runner import (
    _build_adjudication_queue,
    RunnerDependencies,
    build_parser,
    evaluate_cases,
    exit_code_for,
    finalize_run,
    run_evaluation,
    summarize_stage_latency,
)


THRESHOLDS = load_thresholds(Path("eval/rag_full_chain_thresholds.v1.json"))


def _snapshot(ids_hash: str = "a" * 64) -> MilvusSnapshot:
    return MilvusSnapshot(
        collection_name="test",
        schema_sha256="b" * 64,
        row_count=1,
        primary_field="id",
        primary_id_count=1,
        primary_ids_sha256=ids_hash,
        load_state={"state": "Loaded"},
        captured_at_utc="2026-07-13T00:00:00Z",
    )


def _protected(ids_hash: str = "a" * 64) -> ProtectedDataSnapshot:
    return ProtectedDataSnapshot(
        milvus=_snapshot(ids_hash),
        minio_inventories={"bucket/prefix": {"objects": []}},
        mysql_tables={"wiki_pages": {"row_count": 1, "sha256": "d" * 64}},
        artifacts={"data/a": {"size": 1, "sha256": "e" * 64}},
        captured_at_utc="2026-07-15T00:00:00Z",
    )


def _case(case_id: str = "case-1") -> EvalCase:
    return EvalCase(
        case_id=case_id,
        query="测试问题",
        difficulty=Difficulty.D1,
        scenario="text",
        allow_no_sources=True,
    )


def _exchange(case_id: str, *, success: bool = True) -> ObservedExchange:
    return ObservedExchange(
        case_id=case_id,
        endpoint="/ask/stream",
        success=success,
        status_code=200 if success else 500,
        route={},
        sources=(),
        media=(),
        media_panels=(),
        failure_actions=(),
        answer="测试回答" if success else "",
        timing=TimingObservation("2026-07-13T00:00:00Z", 1, 2, 3),
        error="" if success else "request failed",
    )


class _Client:
    def __init__(self, *, raise_first: bool = False):
        self.raise_first = raise_first
        self.stream_calls: list[str] = []
        self.sync_calls: list[str] = []

    def ask_stream(self, case):
        self.stream_calls.append(case.case_id)
        if self.raise_first and len(self.stream_calls) == 1:
            raise RuntimeError("isolated request error")
        return _exchange(case.case_id)

    def ask(self, case):
        self.sync_calls.append(case.case_id)
        return _exchange(case.case_id)

    def collect_voice_pages(self, panels):
        return ()


class _Judge:
    def __init__(self, *, fail: bool = False):
        self.fail = fail
        self.pair_calls = 0

    def evaluate_answer(self, case, **kwargs):
        events = ()
        score = 100.0
        if self.fail:
            score = 0.0
            events = (
                EvaluationEvent.create(
                    "ANSWER.JUDGE_FAILED",
                    "M3",
                    Severity.SEV2,
                    case_ids=(case.case_id,),
                    recommended_action="restore judge",
                ),
            )
        return SimpleNamespace(score=score, events=events, judge={"passed": not self.fail})

    def evaluate_answer_pair(self, case, **kwargs):
        self.pair_calls += 1
        return SimpleNamespace(events=(), equivalent=True)


def _deterministic(case, exchange, inventory, thresholds, **kwargs):
    return DeterministicResult(
        module_scores={"M2": 100.0, "M5": 100.0},
        metrics={},
        events=(),
    )


def _deps(tmp_path, calls, *, allowed=True, invalid_sample=False, judge_fail=False, drift=False):
    inventory = SimpleNamespace(build_version="test", sha256="i" * 64)
    before = _protected()
    after = _protected("c" * 64) if drift else before
    client = _Client()
    config = SimpleNamespace(
        llm=SimpleNamespace(model="production", base_url="https://prod", api_key="x"),
        vectorstore=SimpleNamespace(collection_name="test"),
    )
    judge_config = SimpleNamespace(
        identity=JudgeIdentity("https://judge", "judge", "v1")
    )

    def thresholds_loader(path):
        calls.append("thresholds")
        return THRESHOLDS

    def preflight(*args, **kwargs):
        calls.append("preflight")
        event = () if allowed else (
            EvaluationEvent.create(
                "READY.BACKEND_UNAVAILABLE", "M1", Severity.SEV0,
                recommended_action="restore backend",
            ),
        )
        return PreflightResult(allowed, Severity.PASS if allowed else Severity.SEV0, event, inventory=inventory)

    snapshots = iter((before, after))

    def snapshot_loader(cfg):
        calls.append("snapshot")
        return next(snapshots)

    def sample_builder(*args):
        calls.append("sample")
        return (_case(),)

    def sample_validator(*args):
        calls.append("validate")
        if invalid_sample:
            raise ValueError("invalid sample manifest")

    def client_factory(base_url):
        calls.append("client")
        return client

    def evidence_writer(**kwargs):
        calls.append("evidence")
        path = tmp_path / kwargs["manifest"].run_id
        path.mkdir(parents=True)
        (path / "summary.txt").write_text(kwargs["summary"].global_severity.value)
        return path

    return config, client, RunnerDependencies(
        thresholds_loader=thresholds_loader,
        judge_config_loader=lambda cfg: judge_config,
        preflight_runner=preflight,
        snapshot_loader=snapshot_loader,
        sample_builder=sample_builder,
        sample_validator=sample_validator,
        client_factory=client_factory,
        deterministic_evaluator=_deterministic,
        context_builder=lambda inventory, sources: "",
        judge_factory=lambda cfg: _Judge(fail=judge_fail),
        conversation_builder=lambda *args, **kwargs: (),
        memory_evaluator=lambda *args, **kwargs: (),
        evidence_writer=evidence_writer,
        isolated_route_probe=lambda: {
            "schema_version": "rag_eval.isolated_route_failure/v1",
            "passed": True,
        },
        run_id_factory=lambda: "run-test",
    )


def test_failed_preflight_writes_gate_evidence_and_sends_no_requests(tmp_path):
    calls = []
    cfg, client, deps = _deps(tmp_path, calls, allowed=False)
    outcome = run_evaluation(cfg, "http://backend", 1999, tmp_path, dependencies=deps)
    assert outcome.severity is Severity.SEV0
    assert outcome.evidence_path.is_file()
    assert client.stream_calls == []
    assert calls == ["thresholds", "preflight"]


def test_invalid_sample_manifest_stops_before_client_creation(tmp_path):
    calls = []
    cfg, client, deps = _deps(tmp_path, calls, invalid_sample=True)
    outcome = run_evaluation(cfg, "http://backend", 1999, tmp_path, dependencies=deps)
    assert outcome.severity is Severity.SEV2
    assert client.stream_calls == []
    assert "client" not in calls
    assert calls[:5] == ["thresholds", "preflight", "snapshot", "sample", "validate"]


def test_one_case_exception_does_not_abort_remaining_cases():
    client = _Client(raise_first=True)
    cases, _, _ = evaluate_cases(
        (_case("a"), _case("b")),
        inventory=SimpleNamespace(),
        thresholds=THRESHOLDS,
        client=client,
        judge=_Judge(),
        deterministic_evaluator=_deterministic,
        context_builder=lambda inventory, sources: "",
        parity_minimum=0,
    )
    assert [case.case_id for case in cases] == ["a", "b"]
    assert any(event.event_code == "RELY.CASE_EVALUATION_FAILED" for event in cases[0].events)
    assert cases[1].score is None


def test_endpoint_parity_does_not_hard_compare_independent_natural_language_answers():
    client = _Client()
    judge = _Judge()

    evaluate_cases(
        (_case("a"),),
        inventory=SimpleNamespace(),
        thresholds=THRESHOLDS,
        client=client,
        judge=judge,
        deterministic_evaluator=_deterministic,
        context_builder=lambda inventory, sources: "",
        parity_minimum=1,
    )

    assert client.sync_calls == ["a"]
    assert judge.pair_calls == 0


def test_snapshot_drift_forces_sev1_and_judge_outage_cannot_pass(tmp_path):
    calls = []
    cfg, _, deps = _deps(tmp_path, calls, drift=True)
    drifted = run_evaluation(cfg, "http://backend", 1999, tmp_path, dependencies=deps)
    assert drifted.severity is Severity.SEV1
    assert drifted.summary.accepted is False

    other = tmp_path / "other"
    calls = []
    cfg, _, deps = _deps(other, calls, judge_fail=True)
    failed_judge = run_evaluation(cfg, "http://backend", 1999, other, dependencies=deps)
    assert failed_judge.severity is Severity.SEV2
    assert failed_judge.summary.accepted is False


def test_protected_snapshot_failure_stops_before_any_sampled_request(tmp_path):
    calls = []
    cfg, client, deps = _deps(tmp_path, calls)

    def unavailable(_cfg):
        calls.append("snapshot")
        raise RuntimeError("protected state unavailable")

    deps = RunnerDependencies(**{**deps.__dict__, "snapshot_loader": unavailable})

    outcome = run_evaluation(cfg, "http://backend", 1999, tmp_path, dependencies=deps)

    assert outcome.severity is Severity.SEV0
    assert client.stream_calls == []
    assert calls == ["thresholds", "preflight", "snapshot"]


def test_runner_reuses_protected_snapshot_captured_by_preflight(tmp_path):
    calls = []
    cfg, _, deps = _deps(tmp_path, calls)
    before = _protected()

    def preflight_with_snapshot(*args, **kwargs):
        calls.append("preflight")
        return PreflightResult(
            True,
            Severity.PASS,
            (),
            inventory=SimpleNamespace(build_version="test", sha256="i" * 64),
            snapshot=before,
        )

    def post_snapshot(_cfg):
        calls.append("snapshot")
        return before

    deps = RunnerDependencies(
        **{
            **deps.__dict__,
            "preflight_runner": preflight_with_snapshot,
            "snapshot_loader": post_snapshot,
        }
    )

    run_evaluation(cfg, "http://backend", 1999, tmp_path, dependencies=deps)

    assert calls.count("snapshot") == 1


def test_stage_latency_reports_individual_p95_and_validation_boundaries():
    exchanges = []
    for index in range(20):
        exchange = _exchange(f"case-{index}")
        exchanges.append(
            ObservedExchange(
                **{
                    **exchange.__dict__,
                    "timing": TimingObservation(
                        "2026-07-15T00:00:00Z",
                        retrieval_ms=100.0 + index,
                        ttft_ms=200.0 + index,
                        total_ms=300.0 + index,
                        model_first_token_ms=120.0 + index,
                        validated_ready_ms=180.0 + index,
                        stage_ms={
                            "planner.normalize": 10.0 + index,
                            "retrieval.dense": 50.0 + index,
                        },
                    ),
                }
            )
        )

    summary = summarize_stage_latency(exchanges, THRESHOLDS)

    assert summary["fixed_thresholds_ms"] == {
        "retrieval_p95_ms": 5000.0,
        "ttft_p95_ms": 15000.0,
        "total_p95_ms": 45000.0,
    }
    assert summary["stage_p95_ms"]["retrieval.dense"] > summary["stage_p95_ms"]["planner.normalize"]
    assert summary["dominant_stage"] == "retrieval.dense"
    assert summary["validated_ready_p95_ms"] is not None
    assert summary["visible_buffering_delta_p95_ms"] is not None


def test_v2_adjudication_queue_is_event_scoped_and_keeps_reviewed_severity():
    cases = [
        SimpleNamespace(
            case_id="case-a",
            events=(
                EvaluationEvent.create(
                    "CITE.UNKNOWN_OR_STALE_ID",
                    "M3",
                    Severity.SEV1,
                    case_ids=("case-a",),
                    recommended_action="repair citation",
                ),
                EvaluationEvent.create(
                    "RELY.STAGE_SPAN_INCOMPLETE",
                    "M5",
                    Severity.SEV2,
                    case_ids=("case-a",),
                    recommended_action="repair trace",
                ),
            ),
        )
    ]

    queue = _build_adjudication_queue(cases, seed=1999)

    event_rows = [row for row in queue if row["event_code"] != "AUDIT.CALIBRATION"]
    assert {(row["case_id"], row["event_code"], row["severity"]) for row in event_rows} == {
        ("case-a", "CITE.UNKNOWN_OR_STALE_ID", "SEV-1"),
        ("case-a", "RELY.STAGE_SPAN_INCOMPLETE", "SEV-2"),
    }
    assert all(row["schema_version"] == "rag_eval.adjudication/v2" for row in queue)


def test_finalize_refuses_incomplete_adjudication_without_editing_automatic_files(tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    automatic = run_dir / "case_results.v1.jsonl"
    automatic.write_text('{"case_id":"a"}\n', encoding="utf-8")
    (run_dir / "module_summary.v1.json").write_text(
        json.dumps({"schema_version": "rag_eval.module_summary/v1", "global_severity": "SEV-2"}),
        encoding="utf-8",
    )
    (run_dir / "evaluation_report.v1.md").write_text("automatic\n", encoding="utf-8")
    (run_dir / "adjudication_queue.v1.jsonl").write_text(
        '\n'.join([
            json.dumps({"adjudication_id": "a", "automatic_label": "fail"}),
            json.dumps({"adjudication_id": "b", "automatic_label": "pass"}),
        ]) + '\n',
        encoding="utf-8",
    )
    decisions = tmp_path / "decisions.jsonl"
    decisions.write_text(json.dumps({"adjudication_id": "a", "reviewer_label": "fail"}) + "\n")
    before = hashlib.sha256(automatic.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="incomplete adjudication.*b"):
        finalize_run(run_dir, decisions)
    assert hashlib.sha256(automatic.read_bytes()).hexdigest() == before
    assert not (run_dir / "module_summary.final.v1.json").exists()


def test_v2_finalize_requires_hash_pinned_human_audit_and_event_adjudication(tmp_path):
    run_dir = tmp_path / "run-v2"
    run_dir.mkdir()
    case_row = {
        "schema_version": "rag_eval.case_result/v2",
        "predecessor_sha256": "a" * 64,
        "case_id": "case-a",
        "difficulty": "D1",
        "scenario": "text",
        "module_scores": {"M2": 100, "M3": 100, "M5": 100},
        "events": [],
    }
    case_line = json.dumps(
        case_row, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ) + "\n"
    evidence_sha256 = hashlib.sha256(case_line.encode("utf-8")).hexdigest()
    automatic = run_dir / "case_results.v2.jsonl"
    automatic.write_text(case_line, encoding="utf-8")
    (run_dir / "module_summary.v2.json").write_text(
        json.dumps({"schema_version": "rag_eval.module_summary/v2", "global_severity": "PASS"}),
        encoding="utf-8",
    )
    (run_dir / "evaluation_report.v2.md").write_text("automatic v2\n", encoding="utf-8")
    (run_dir / "human_audit_manifest.v1.jsonl").write_text(
        json.dumps({
            "schema_version": "rag_eval.human_audit_manifest/v1",
            "case_id": "case-a",
            "evidence_sha256": evidence_sha256,
            "evidence_ref": "case_results.v2.jsonl#case-a",
        }) + "\n",
        encoding="utf-8",
    )
    (run_dir / "adjudication_queue.v2.jsonl").write_text(
        json.dumps({
            "schema_version": "rag_eval.adjudication/v2",
            "case_id": "case-a",
            "event_code": "CITE.UNKNOWN_OR_STALE_ID",
            "severity": "SEV-1",
        }) + "\n",
        encoding="utf-8",
    )
    audit_results = tmp_path / "human.jsonl"
    audit_results.write_text(
        json.dumps({
            "schema_version": "rag_eval.human_audit/v1",
            "case_id": "case-a",
            "reviewer": "local-review",
            "decision": "fail",
            "severity": "SEV-1",
            "notes": "evidence reviewed",
            "evidence_sha256": evidence_sha256,
        }) + "\n",
        encoding="utf-8",
    )
    adjudication = tmp_path / "adjudication.jsonl"
    adjudication.write_text(
        json.dumps({
            "schema_version": "rag_eval.adjudication_result/v2",
            "case_id": "case-a",
            "event_code": "CITE.UNKNOWN_OR_STALE_ID",
            "decision": "confirm",
            "severity": "SEV-1",
            "reason": "automatic evidence confirmed",
            "reviewer": "local-review",
        }) + "\n",
        encoding="utf-8",
    )
    before = hashlib.sha256(automatic.read_bytes()).hexdigest()

    with pytest.raises(ValueError, match="human audit results are required"):
        finalize_run(run_dir, adjudication)

    final_report = finalize_run(
        run_dir,
        adjudication,
        human_audit_path=audit_results,
    )

    final_summary = json.loads(
        (run_dir / "module_summary.final.v2.json").read_text(encoding="utf-8")
    )
    assert final_report.name == "evaluation_report.final.v2.md"
    assert final_summary["global_severity"] == "SEV-1"
    assert final_summary["human_audit_reviewed"] == 1
    assert final_summary["adjudications_reviewed"] == 1
    assert hashlib.sha256(automatic.read_bytes()).hexdigest() == before


def test_v2_finalize_rejects_human_audit_evidence_hash_mismatch(tmp_path):
    run_dir = tmp_path / "bad-v2"
    run_dir.mkdir()
    case_line = json.dumps({"case_id": "case-a"}, sort_keys=True, separators=(",", ":")) + "\n"
    (run_dir / "case_results.v2.jsonl").write_text(case_line, encoding="utf-8")
    (run_dir / "module_summary.v2.json").write_text(
        json.dumps({"global_severity": "PASS"}), encoding="utf-8"
    )
    (run_dir / "evaluation_report.v2.md").write_text("automatic\n", encoding="utf-8")
    (run_dir / "adjudication_queue.v2.jsonl").write_text("", encoding="utf-8")
    (run_dir / "human_audit_manifest.v1.jsonl").write_text(
        json.dumps({"case_id": "case-a", "evidence_sha256": "a" * 64}) + "\n",
        encoding="utf-8",
    )
    audit = tmp_path / "bad-human.jsonl"
    audit.write_text(
        json.dumps({
            "schema_version": "rag_eval.human_audit/v1",
            "case_id": "case-a",
            "reviewer": "local-review",
            "decision": "pass",
            "severity": "PASS",
            "notes": "reviewed",
            "evidence_sha256": "a" * 64,
        }) + "\n",
        encoding="utf-8",
    )
    adjudication = tmp_path / "empty-adjudication.jsonl"
    adjudication.write_text("", encoding="utf-8")

    with pytest.raises(ValueError, match="evidence SHA-256 mismatch"):
        finalize_run(run_dir, adjudication, human_audit_path=audit)


@pytest.mark.parametrize(
    ("severity", "code"),
    [(Severity.PASS, 0), (Severity.SEV4, 0), (Severity.SEV3, 3),
     (Severity.SEV2, 2), (Severity.SEV1, 1), (Severity.SEV0, 10)],
)
def test_exit_codes_are_stable(severity, code):
    assert exit_code_for(severity) == code


def test_cli_has_all_required_commands_and_runner_has_no_write_api_calls():
    parser = build_parser()
    for command in ("preflight", "sample", "run", "finalize", "compare-snapshots"):
        namespace = parser.parse_args([command, "--help"] if False else [command, *_minimum_args(command)])
        assert namespace.command == command
    source = inspect.getsource(__import__("src.rag_eval.runner", fromlist=["runner"]))
    for forbidden in (".insert(", ".upsert(", ".delete(", ".put_object(", ".remove_object("):
        assert forbidden not in source


def _minimum_args(command):
    return {
        "preflight": ["--base-url", "http://x", "--output", "out.json"],
        "sample": ["--seed", "1", "--output", "out.jsonl"],
        "run": ["--base-url", "http://x", "--seed", "1", "--output-root", "out"],
        "finalize": [
            "--run-dir", "run",
            "--adjudication", "decisions.jsonl",
            "--human-audit", "human.jsonl",
        ],
        "compare-snapshots": ["--before", "a.json", "--after", "b.json"],
    }[command]
