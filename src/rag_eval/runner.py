"""Read-only full-chain evaluation orchestration and CLI commands."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Mapping, Sequence

from config.config import get_config
from src.rag_eval.client import ObservedExchange, RagEvalClient
from src.rag_eval.contracts import (
    CaseResult,
    EvalCase,
    EvaluationEvent,
    JudgeIdentity,
    RunManifest,
    Severity,
    Thresholds,
    load_thresholds,
    to_jsonable,
)
from src.rag_eval.deterministic import (
    DeterministicResult,
    evaluate_deterministic,
    evaluate_reliability,
)
from src.rag_eval.conversation import (
    build_conversation_tracks,
    evaluate_memory_triplets,
)
from src.rag_eval.inventory import (
    EvaluationInventory,
    MilvusSnapshot,
    PreflightResult,
    ProtectedDataSnapshot,
    capture_inventory,
    capture_milvus_snapshot,
    capture_protected_snapshot,
    compare_protected_snapshots,
    compare_snapshots,
    reconstruct_context,
    run_preflight,
)
from src.rag_eval.judge import AnswerJudge, JudgeConfig, load_judge_config
from src.rag_eval.isolated import run_isolated_route_failure_probe
from src.rag_eval.reporting import render_report, write_run_evidence
from src.rag_eval.sampling import build_sample_manifest, validate_sample_manifest
from src.rag_eval.scoring import RunSummary, classify_run


DEFAULT_THRESHOLDS_PATH = Path("eval/rag_full_chain_thresholds.v1.json")
UNEXPECTED_EXIT_CODE = 20


@dataclass(frozen=True)
class RunnerDependencies:
    thresholds_loader: Callable[[Path], Thresholds] = load_thresholds
    judge_config_loader: Callable[[object], object] = load_judge_config
    preflight_runner: Callable[..., PreflightResult] = run_preflight
    snapshot_loader: Callable[[object], object] = capture_protected_snapshot
    sample_builder: Callable[..., tuple[EvalCase, ...]] = build_sample_manifest
    sample_validator: Callable[..., None] = validate_sample_manifest
    client_factory: Callable[[str], object] = RagEvalClient
    deterministic_evaluator: Callable[..., DeterministicResult] = evaluate_deterministic
    context_builder: Callable[..., str] = reconstruct_context
    judge_factory: Callable[[object], object] = AnswerJudge
    conversation_builder: Callable[..., object] = build_conversation_tracks
    memory_evaluator: Callable[..., object] = evaluate_memory_triplets
    evidence_writer: Callable[..., Path] = write_run_evidence
    isolated_route_probe: Callable[[], Mapping[str, object]] = (
        run_isolated_route_failure_probe
    )
    run_id_factory: Callable[[], str] = lambda: datetime.now(timezone.utc).strftime(
        "%Y%m%dT%H%M%SZ"
    ) + "-" + uuid.uuid4().hex[:8]


@dataclass(frozen=True)
class RunOutcome:
    severity: Severity
    evidence_path: Path
    summary: RunSummary | None = None

    @property
    def exit_code(self) -> int:
        return exit_code_for(self.severity)


def run_evaluation(
    cfg: object,
    base_url: str,
    seed: int,
    output_root: Path,
    *,
    thresholds_path: Path = DEFAULT_THRESHOLDS_PATH,
    dependencies: RunnerDependencies | None = None,
) -> RunOutcome:
    deps = dependencies or RunnerDependencies()
    output_root = Path(output_root)
    run_id = deps.run_id_factory()
    thresholds = deps.thresholds_loader(Path(thresholds_path))

    judge_config: object | None = None
    judge_identity: JudgeIdentity | None = None
    judge_config_error = ""
    try:
        judge_config = deps.judge_config_loader(cfg)
        judge_identity = getattr(judge_config, "identity")
    except Exception as error:
        judge_config_error = str(error)

    preflight = deps.preflight_runner(cfg, base_url, judge_identity)
    if judge_config_error and preflight.allowed_to_run:
        preflight = PreflightResult(
            allowed_to_run=False,
            severity=Severity.SEV0,
            events=(
                EvaluationEvent.create(
                    "READY.JUDGE_UNAVAILABLE",
                    "M1",
                    Severity.SEV0,
                    observed={"message": judge_config_error},
                    recommended_action="configure a distinct independent judge before evaluation",
                ),
            ),
            backend_health=preflight.backend_health,
            minio_ready=preflight.minio_ready,
            inventory=preflight.inventory,
            snapshot=preflight.snapshot,
        )
    if not preflight.allowed_to_run:
        path = _write_gate_evidence(output_root, run_id, "preflight", preflight.events)
        return RunOutcome(preflight.severity, path)

    inventory = preflight.inventory
    if not isinstance(inventory, EvaluationInventory) and not hasattr(inventory, "sha256"):
        event = _runner_event(
            "READY.DATA_UNAVAILABLE", "M1", Severity.SEV0, "preflight returned no inventory"
        )
        path = _write_gate_evidence(output_root, run_id, "preflight", (event,))
        return RunOutcome(Severity.SEV0, path)

    before = preflight.snapshot
    if not isinstance(before, ProtectedDataSnapshot):
        try:
            before = deps.snapshot_loader(cfg)
        except Exception as error:
            event = _runner_event(
                "READY.PROTECTED_SNAPSHOT_UNAVAILABLE",
                "M1",
                Severity.SEV0,
                f"{type(error).__name__}: protected snapshot capture failed",
            )
            path = _write_gate_evidence(
                output_root,
                run_id,
                "protected_snapshot",
                (event,),
            )
            return RunOutcome(Severity.SEV0, path)
    try:
        samples = tuple(deps.sample_builder(inventory, thresholds, seed))
        deps.sample_validator(samples, inventory, thresholds)
    except Exception as error:
        event = _runner_event(
            "RETR.SAMPLE_MANIFEST_INVALID", "M2", Severity.SEV2, str(error)
        )
        path = _write_gate_evidence(output_root, run_id, "sampling", (event,))
        return RunOutcome(Severity.SEV2, path)

    try:
        isolated_route_failure = dict(deps.isolated_route_probe())
        if not isolated_route_failure.get("passed"):
            raise RuntimeError("isolated route failure probe did not pass")
    except Exception as error:
        event = _runner_event(
            "ROUTE.FAILURE_PROBE_FAILED",
            "M4",
            Severity.SEV1,
            f"{type(error).__name__}: {error}",
        )
        path = _write_gate_evidence(
            output_root,
            run_id,
            "isolated_route_failure",
            (event,),
        )
        return RunOutcome(Severity.SEV1, path)

    client = deps.client_factory(base_url)
    assert judge_config is not None
    judge = deps.judge_factory(judge_config)
    cases, exchanges, parity = evaluate_cases(
        samples,
        inventory=inventory,
        thresholds=thresholds,
        client=client,
        judge=judge,
        deterministic_evaluator=deps.deterministic_evaluator,
        context_builder=deps.context_builder,
        parity_minimum=thresholds.sync_stream_parity_minimum,
    )

    exchange_by_id = {exchange.case_id: exchange for exchange in exchanges}
    repeat_pairs = [
        (exchange_by_id[case.repeat_of], exchange_by_id[case.case_id])
        for case in samples
        if case.repeat_of in exchange_by_id and case.case_id in exchange_by_id
    ]
    reliability = evaluate_reliability(exchanges, thresholds, repeat_pairs=repeat_pairs)
    extra_events = list(reliability.events)

    memory_results: tuple[object, ...] = ()
    try:
        tracks = tuple(deps.conversation_builder(inventory, seed=seed))
        if tracks:
            memory_results = tuple(
                deps.memory_evaluator(client, judge, inventory, tracks)
            )
            for result in memory_results:
                extra_events.extend(tuple(getattr(result, "events", ())))
    except Exception as error:
        extra_events.append(
            _runner_event(
                "MEMORY.EVALUATION_FAILED",
                "M3",
                Severity.SEV2,
                f"{type(error).__name__}: memory triplet evaluation failed",
            )
        )

    post_capture_error = ""
    try:
        after = deps.snapshot_loader(cfg)
        changes = _compare_snapshot_state(before, after)
    except Exception as error:
        after = None
        post_capture_error = type(error).__name__
        changes = ["post protected snapshot capture failed"]
    if changes:
        extra_events.append(
            EvaluationEvent.create(
                "READY.READ_ONLY_DRIFT",
                "M1",
                Severity.SEV1,
                observed={"changes": changes, "capture_error": post_capture_error},
                expected={"changes": []},
                recommended_action="stop acceptance and identify the writer before rerunning",
            )
        )
    summary = classify_run(
        cases,
        thresholds,
        extra_events=extra_events,
        excluded_case_ids={case.case_id for case in samples if case.repeat_of is not None},
    )
    assert judge_identity is not None
    manifest = RunManifest(
        run_id=run_id,
        started_at_utc=_utc_now(),
        seed=seed,
        build_version=str(getattr(inventory, "build_version", "")),
        collection_name=str(
            getattr(
                getattr(cfg, "vectorstore", None),
                "collection_name",
                _milvus_snapshot(before).collection_name,
            )
        ),
        production_model=str(getattr(getattr(cfg, "llm", None), "model", "")),
        judge_identity=judge_identity,
        thresholds_sha256=hashlib.sha256(Path(thresholds_path).read_bytes()).hexdigest(),
    )
    queue = _build_adjudication_queue(cases, seed)
    stage_latency = summarize_stage_latency(exchanges, thresholds)
    before_payload = _snapshot_payload(before)
    after_payload = (
        _snapshot_payload(after)
        if after is not None
        else {
            "schema_version": "rag_eval.protected_snapshot/v2",
            "capture_error": post_capture_error,
        }
    )
    run_dir = deps.evidence_writer(
        output_root=output_root,
        manifest=manifest,
        samples=samples,
        cases=cases,
        summary=summary,
        pre_snapshot=before_payload,
        post_snapshot=after_payload,
        adjudication_queue=queue,
        memory_pair_results=memory_results,
        stage_latency=stage_latency,
        isolated_route_failure=isolated_route_failure,
    )
    return RunOutcome(summary.global_severity, run_dir, summary)


def evaluate_cases(
    samples: Sequence[EvalCase],
    *,
    inventory: object,
    thresholds: Thresholds,
    client: object,
    judge: object,
    deterministic_evaluator: Callable[..., DeterministicResult] = evaluate_deterministic,
    context_builder: Callable[..., str] = reconstruct_context,
    parity_minimum: int = 8,
) -> tuple[list[CaseResult], list[ObservedExchange], dict[str, ObservedExchange]]:
    parity_ids = {
        case.case_id
        for case in [item for item in samples if item.repeat_of is None][: max(0, parity_minimum)]
    }
    results: list[CaseResult] = []
    exchanges: list[ObservedExchange] = []
    parity_exchanges: dict[str, ObservedExchange] = {}
    for case in samples:
        try:
            exchange = client.ask_stream(case)
            if exchange.media_panels:
                pages = client.collect_voice_pages(exchange.media_panels)
                exchange = replace(exchange, voice_pages=tuple(pages))
            exchanges.append(exchange)
            parity_exchange = client.ask(case) if case.case_id in parity_ids else None
            if parity_exchange is not None:
                parity_exchanges[case.case_id] = parity_exchange

            deterministic = deterministic_evaluator(
                case,
                exchange,
                inventory,
                thresholds,
                parity_exchange=parity_exchange,
            )
            context = context_builder(inventory, exchange.sources)
            answer = judge.evaluate_answer(
                case,
                answer=exchange.answer,
                context=context,
                sources=exchange.sources,
                media=exchange.media,
                failure_actions=exchange.failure_actions,
            )
            # Parity covers the packet contract. Independent stochastic answer text is
            # scored on its own and is not part of transport parity.
            pair_events: tuple[EvaluationEvent, ...] = ()
            scores = dict(deterministic.module_scores)
            scores["M3"] = float(answer.score)
            results.append(
                CaseResult(
                    case_id=case.case_id,
                    difficulty=case.difficulty,
                    scenario=case.scenario,
                    module_scores=scores,
                    events=tuple((*deterministic.events, *answer.events, *pair_events)),
                    observed={
                        "exchange": to_jsonable(exchange),
                        "deterministic_metrics": to_jsonable(deterministic.metrics),
                    },
                    judge=to_jsonable(answer),
                )
            )
        except Exception as error:
            required = thresholds.weights[case.scenario]
            results.append(
                CaseResult(
                    case_id=case.case_id,
                    difficulty=case.difficulty,
                    scenario=case.scenario,
                    module_scores={module: 0.0 for module in required},
                    events=(
                        _runner_event(
                            "RELY.CASE_EVALUATION_FAILED",
                            "M5",
                            Severity.SEV2,
                            str(error),
                            case_ids=(case.case_id,),
                        ),
                    ),
                    observed={"error": str(error)},
                )
            )
    return results, exchanges, parity_exchanges


def summarize_stage_latency(
    exchanges: Sequence[ObservedExchange],
    thresholds: Thresholds,
) -> Mapping[str, object]:
    stage_values: dict[str, list[float]] = {}
    retrieval_values: list[float] = []
    ttft_values: list[float] = []
    validated_values: list[float] = []
    total_values: list[float] = []
    buffering_deltas: list[float] = []
    for exchange in exchanges:
        for name, value in exchange.timing.stage_ms.items():
            stage_values.setdefault(name, []).append(float(value))
        if exchange.timing.retrieval_ms is not None:
            retrieval_values.append(float(exchange.timing.retrieval_ms))
        if exchange.timing.ttft_ms is not None:
            ttft_values.append(float(exchange.timing.ttft_ms))
        if exchange.timing.validated_ready_ms is not None:
            validated_values.append(float(exchange.timing.validated_ready_ms))
        total_values.append(float(exchange.timing.total_ms))
        if (
            exchange.timing.ttft_ms is not None
            and exchange.timing.model_first_token_ms is not None
        ):
            buffering_deltas.append(
                max(
                    0.0,
                    float(exchange.timing.ttft_ms)
                    - float(exchange.timing.model_first_token_ms),
                )
            )
    stage_p95 = {
        name: _percentile(values, 0.95)
        for name, values in sorted(stage_values.items())
    }
    dominant_stage = max(stage_p95, key=stage_p95.get) if stage_p95 else ""
    buffering_p95 = _optional_percentile(buffering_deltas, 0.95)
    return {
        "sample_count": len(exchanges),
        "fixed_thresholds_ms": {
            "retrieval_p95_ms": float(thresholds.reliability["retrieval_p95_ms"]),
            "ttft_p95_ms": float(thresholds.reliability["ttft_p95_ms"]),
            "total_p95_ms": float(thresholds.reliability["total_p95_ms"]),
        },
        "retrieval_p95_ms": _optional_percentile(retrieval_values, 0.95),
        "validated_ready_p95_ms": _optional_percentile(validated_values, 0.95),
        "visible_ttft_p95_ms": _optional_percentile(ttft_values, 0.95),
        "total_p95_ms": _optional_percentile(total_values, 0.95),
        "visible_buffering_delta_p95_ms": buffering_p95,
        "citation_buffering_changed_visible_ttft": bool(
            buffering_p95 is not None and buffering_p95 > 0
        ),
        "stage_p95_ms": stage_p95,
        "dominant_stage": dominant_stage,
    }


def _optional_percentile(values: Sequence[float], quantile: float) -> float | None:
    return _percentile(values, quantile) if values else None


def _percentile(values: Sequence[float], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(float(value) for value in values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def _milvus_snapshot(value: object) -> MilvusSnapshot:
    if isinstance(value, ProtectedDataSnapshot):
        if not isinstance(value.milvus, MilvusSnapshot):
            raise TypeError("protected snapshot lacks a MilvusSnapshot")
        return value.milvus
    if isinstance(value, MilvusSnapshot):
        return value
    raise TypeError("snapshot loader returned an unsupported object")


def _compare_snapshot_state(before: object, after: object) -> list[str]:
    if isinstance(before, ProtectedDataSnapshot) and isinstance(after, ProtectedDataSnapshot):
        return compare_protected_snapshots(before, after)
    return compare_snapshots(_milvus_snapshot(before), _milvus_snapshot(after))


def _snapshot_payload(value: object) -> Mapping[str, object]:
    serializer = getattr(value, "to_json", None)
    payload = serializer() if callable(serializer) else value
    if not isinstance(payload, Mapping):
        raise TypeError("snapshot is not serializable")
    return dict(payload)


def finalize_run(
    run_dir: Path,
    adjudication_path: Path,
    *,
    human_audit_path: Path | None = None,
    alignment_min: float = 0.85,
) -> Path:
    run_dir = Path(run_dir)
    if (run_dir / "case_results.v2.jsonl").is_file():
        if human_audit_path is None:
            raise ValueError("human audit results are required for evaluator v2")
        return _finalize_v2(
            run_dir,
            Path(adjudication_path),
            Path(human_audit_path),
            alignment_min=alignment_min,
        )
    queue = _read_jsonl(run_dir / "adjudication_queue.v1.jsonl")
    decisions = _read_jsonl(Path(adjudication_path))
    decision_by_id = {str(row.get("adjudication_id") or ""): row for row in decisions}
    missing = [
        str(row.get("adjudication_id") or "")
        for row in queue
        if str(row.get("adjudication_id") or "") not in decision_by_id
    ]
    if missing:
        raise ValueError(f"incomplete adjudication; missing: {', '.join(missing)}")

    final_summary = run_dir / "module_summary.final.v1.json"
    final_report = run_dir / "evaluation_report.final.v1.md"
    if final_summary.exists() or final_report.exists():
        raise FileExistsError("final adjudication evidence already exists")
    automatic_summary_path = run_dir / "module_summary.v1.json"
    automatic_report_path = run_dir / "evaluation_report.v1.md"
    automatic = json.loads(automatic_summary_path.read_text(encoding="utf-8"))
    agreements = [
        str(row.get("automatic_label"))
        == str(decision_by_id[str(row.get("adjudication_id") or "")].get("reviewer_label"))
        for row in queue
    ]
    alignment = sum(agreements) / len(agreements) if agreements else 1.0
    current = Severity(str(automatic.get("global_severity") or "SEV-0"))
    final_severity = current
    if alignment < alignment_min and Severity.SEV2.rank < current.rank:
        final_severity = Severity.SEV2
    payload = dict(automatic)
    payload.update(
        {
            "schema_version": "rag_eval.module_summary.final/v1",
            "predecessor_sha256": _sha256(automatic_summary_path),
            "automatic_report_sha256": _sha256(automatic_report_path),
            "human_alignment": alignment,
            "human_alignment_minimum": alignment_min,
            "global_severity": final_severity.value,
            "accepted": final_severity in {Severity.PASS, Severity.SEV4},
            "accepted_with_warnings": final_severity is Severity.SEV3,
        }
    )
    _atomic_text(final_summary, _canonical_json(payload))
    report = (
        "# RAG Full-Chain Evaluation Final\n\n"
        f"- Global severity: **{final_severity.value}**\n"
        f"- Human/judge agreement: **{alignment:.1%}**\n"
        f"- Required agreement: **{alignment_min:.1%}**\n"
        f"- Automatic report SHA-256: `{_sha256(automatic_report_path)}`\n"
    )
    _atomic_text(final_report, report)
    return final_report


def _finalize_v2(
    run_dir: Path,
    adjudication_path: Path,
    human_audit_path: Path,
    *,
    alignment_min: float,
) -> Path:
    case_rows, case_hashes = _read_jsonl_with_hashes(run_dir / "case_results.v2.jsonl")
    case_by_id = _unique_by(case_rows, "case_id", "case result")
    audit_manifest = _read_jsonl(run_dir / "human_audit_manifest.v1.jsonl")
    audit_by_id = _unique_by(audit_manifest, "case_id", "human audit manifest")
    audit_results = _read_jsonl(human_audit_path)
    audit_result_by_id = _unique_by(audit_results, "case_id", "human audit result")
    _require_exact_keys(audit_by_id, audit_result_by_id, "human audit")

    audit_severities: list[Severity] = []
    agreements: list[bool] = []
    for case_id, manifest_row in audit_by_id.items():
        if case_id not in case_by_id:
            raise ValueError(f"human audit references unknown case: {case_id}")
        expected_hash = str(manifest_row.get("evidence_sha256") or "")
        if expected_hash != case_hashes[case_id]:
            raise ValueError(f"human audit evidence SHA-256 mismatch: {case_id}")
        result = audit_result_by_id[case_id]
        if result.get("schema_version") != "rag_eval.human_audit/v1":
            raise ValueError(f"invalid human audit schema: {case_id}")
        if str(result.get("evidence_sha256") or "") != expected_hash:
            raise ValueError(f"human audit result evidence SHA-256 mismatch: {case_id}")
        if not str(result.get("reviewer") or "").strip():
            raise ValueError(f"human audit reviewer is required: {case_id}")
        decision = str(result.get("decision") or "")
        severity = _parse_reviewed_severity(result.get("severity"), f"human audit {case_id}")
        if decision == "pass" and severity is not Severity.PASS:
            raise ValueError(f"passing human audit must use PASS severity: {case_id}")
        if decision == "fail" and severity is Severity.PASS:
            raise ValueError(f"failing human audit must use incident severity: {case_id}")
        if decision not in {"pass", "fail"}:
            raise ValueError(f"invalid human audit decision: {case_id}")
        if decision == "fail":
            audit_severities.append(severity)
        automatic_failed = _case_has_automatic_failure(case_by_id[case_id])
        agreements.append((decision == "fail") == automatic_failed)

    queue = _read_jsonl(run_dir / "adjudication_queue.v2.jsonl")
    queue_by_key = _unique_event_rows(queue, "adjudication queue")
    decisions = _read_jsonl(adjudication_path)
    decision_by_key = _unique_event_rows(decisions, "adjudication result")
    _require_exact_keys(queue_by_key, decision_by_key, "adjudication")
    adjudicated_severities: list[Severity] = []
    disposition_counts = {"confirm": 0, "dismiss": 0, "adjust": 0}
    for key, row in decision_by_key.items():
        if row.get("schema_version") != "rag_eval.adjudication_result/v2":
            raise ValueError(f"invalid adjudication result schema: {key[0]} {key[1]}")
        if not str(row.get("reviewer") or "").strip() or not str(row.get("reason") or "").strip():
            raise ValueError(f"adjudication reviewer and reason are required: {key[0]} {key[1]}")
        decision = str(row.get("decision") or "")
        if decision not in disposition_counts:
            raise ValueError(f"invalid adjudication decision: {key[0]} {key[1]}")
        severity = _parse_reviewed_severity(
            row.get("severity"), f"adjudication {key[0]} {key[1]}"
        )
        queued_severity = _parse_reviewed_severity(
            queue_by_key[key].get("severity"), f"adjudication queue {key[0]} {key[1]}"
        )
        if decision == "confirm":
            if severity is not queued_severity:
                raise ValueError(f"confirmed adjudication severity changed: {key[0]} {key[1]}")
            adjudicated_severities.append(severity)
        elif decision == "dismiss":
            if severity is not Severity.PASS:
                raise ValueError(f"dismissed adjudication must use PASS: {key[0]} {key[1]}")
        elif severity is Severity.PASS:
            raise ValueError(f"adjusted adjudication requires incident severity: {key[0]} {key[1]}")
        else:
            adjudicated_severities.append(severity)
        disposition_counts[decision] += 1

    final_summary = run_dir / "module_summary.final.v2.json"
    final_report = run_dir / "evaluation_report.final.v2.md"
    if final_summary.exists() or final_report.exists():
        raise FileExistsError("final v2 review evidence already exists")
    automatic_summary_path = run_dir / "module_summary.v2.json"
    automatic_report_path = run_dir / "evaluation_report.v2.md"
    automatic = json.loads(automatic_summary_path.read_text(encoding="utf-8"))
    automatic_severity = Severity(str(automatic.get("global_severity") or "SEV-0"))
    alignment = sum(agreements) / len(agreements) if agreements else 1.0
    candidates = [automatic_severity, *audit_severities, *adjudicated_severities]
    if alignment < alignment_min:
        candidates.append(Severity.SEV2)
    final_severity = min(candidates, key=lambda value: value.rank)
    payload = dict(automatic)
    payload.update(
        {
            "schema_version": "rag_eval.module_summary.final/v2",
            "predecessor_sha256": _sha256(automatic_summary_path),
            "automatic_report_sha256": _sha256(automatic_report_path),
            "human_alignment": alignment,
            "human_alignment_minimum": alignment_min,
            "human_audit_reviewed": len(audit_results),
            "adjudications_reviewed": len(decisions),
            "adjudication_dispositions": disposition_counts,
            "global_severity": final_severity.value,
            "accepted": final_severity in {Severity.PASS, Severity.SEV4},
            "accepted_with_warnings": final_severity is Severity.SEV3,
        }
    )
    _atomic_text(final_summary, _canonical_json(payload))
    report = (
        "# RAG Full-Chain Evaluation Final V2\n\n"
        f"- Global severity: **{final_severity.value}**\n"
        f"- Human audits reviewed: **{len(audit_results)}**\n"
        f"- Adjudications reviewed: **{len(decisions)}**\n"
        f"- Human/automatic agreement: **{alignment:.1%}**\n"
        f"- Automatic report SHA-256: `{_sha256(automatic_report_path)}`\n"
    )
    _atomic_text(final_report, report)
    return final_report


def exit_code_for(severity: Severity) -> int:
    return {
        Severity.PASS: 0,
        Severity.SEV4: 0,
        Severity.SEV3: 3,
        Severity.SEV2: 2,
        Severity.SEV1: 1,
        Severity.SEV0: 10,
    }[severity]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read-only RAG full-chain evaluator")
    sub = parser.add_subparsers(dest="command", required=True)
    preflight = sub.add_parser("preflight")
    preflight.add_argument("--base-url", required=True)
    preflight.add_argument("--output", type=Path, required=True)
    sample = sub.add_parser("sample")
    sample.add_argument("--seed", type=int, required=True)
    sample.add_argument("--output", type=Path, required=True)
    run = sub.add_parser("run")
    run.add_argument("--base-url", required=True)
    run.add_argument("--seed", type=int, required=True)
    run.add_argument("--output-root", type=Path, required=True)
    finalize = sub.add_parser("finalize")
    finalize.add_argument("--run-dir", type=Path, required=True)
    finalize.add_argument("--adjudication", type=Path, required=True)
    finalize.add_argument("--human-audit", type=Path, required=True)
    compare = sub.add_parser("compare-snapshots")
    compare.add_argument("--before", type=Path, required=True)
    compare.add_argument("--after", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cfg = get_config()
    if args.command == "run":
        return run_evaluation(cfg, args.base_url, args.seed, args.output_root).exit_code
    if args.command == "preflight":
        try:
            judge_identity = load_judge_config(cfg).identity
        except Exception:
            judge_identity = None
        result = run_preflight(cfg, args.base_url, judge_identity)
        payload = {
            "schema_version": "rag_eval.preflight/v1",
            "allowed_to_run": result.allowed_to_run,
            "severity": result.severity.value,
            "events": [event.to_json() for event in result.events],
            "backend_health": result.backend_health,
            "minio_ready": result.minio_ready,
            "snapshot": to_jsonable(result.snapshot),
        }
        _atomic_text(args.output, _canonical_json(payload))
        return exit_code_for(result.severity)
    if args.command == "sample":
        thresholds = load_thresholds(DEFAULT_THRESHOLDS_PATH)
        inventory = capture_inventory(cfg)
        samples = build_sample_manifest(inventory, thresholds, args.seed)
        text = "".join(_canonical_json_line({"schema_version": "rag_eval.sample/v1", **case.to_json()}) for case in samples)
        _atomic_text(args.output, text)
        return 0
    if args.command == "finalize":
        finalize_run(
            args.run_dir,
            args.adjudication,
            human_audit_path=args.human_audit,
        )
        return 0
    before = _load_snapshot(args.before)
    after = _load_snapshot(args.after)
    changes = compare_snapshots(before, after)
    print(json.dumps({"equal": not changes, "changes": changes}, ensure_ascii=False))
    return 0 if not changes else 1


def _build_adjudication_queue(cases: Sequence[CaseResult], seed: int) -> list[dict[str, object]]:
    calibration_count = max(1, math.ceil(len(cases) * 0.1)) if cases else 0
    mandatory_case_ids: set[str] = set()
    queue: list[dict[str, object]] = []
    for case in cases:
        seen_codes: set[str] = set()
        for event in case.events:
            if event.severity not in {Severity.SEV1, Severity.SEV2}:
                continue
            if event.event_code in seen_codes:
                continue
            seen_codes.add(event.event_code)
            mandatory_case_ids.add(case.case_id)
            queue.append(
                {
                    "schema_version": "rag_eval.adjudication/v2",
                    "case_id": case.case_id,
                    "event_code": event.event_code,
                    "severity": event.severity.value,
                    "automatic_decision": "confirm",
                    "reason": "severity_candidate",
                    "seed": seed,
                }
            )
    calibration = [
        case
        for case in sorted(cases, key=lambda item: item.case_id)
        if case.case_id not in mandatory_case_ids
    ][:calibration_count]
    for case in calibration:
        queue.append(
            {
                "schema_version": "rag_eval.adjudication/v2",
                "case_id": case.case_id,
                "event_code": "AUDIT.CALIBRATION",
                "severity": Severity.PASS.value,
                "automatic_decision": "confirm",
                "reason": "calibration_sample",
                "seed": seed,
            }
        )
    return sorted(queue, key=lambda row: (str(row["case_id"]), str(row["event_code"])))


def _runner_event(
    code: str,
    module: str,
    severity: Severity,
    message: str,
    *,
    case_ids: tuple[str, ...] = (),
) -> EvaluationEvent:
    return EvaluationEvent.create(
        code,
        module,
        severity,
        case_ids=case_ids,
        observed={"message": message},
        recommended_action="inspect the recorded stage error and rerun the affected module",
    )


def _write_gate_evidence(
    output_root: Path,
    run_id: str,
    gate: str,
    events: Sequence[EvaluationEvent],
) -> Path:
    output_root.mkdir(parents=True, exist_ok=True)
    path = output_root / f"{run_id}.{gate}_failure.v1.json"
    payload = {
        "schema_version": "rag_eval.gate_failure/v1",
        "run_id": run_id,
        "gate": gate,
        "events": [event.to_json() for event in events],
        "captured_at_utc": _utc_now(),
    }
    _atomic_text(path, _canonical_json(payload))
    return path


def _load_snapshot(path: Path) -> MilvusSnapshot:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    allowed = MilvusSnapshot.__dataclass_fields__
    return MilvusSnapshot(**{key: value for key, value in payload.items() if key in allowed})


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            payload = json.loads(line)
            if not isinstance(payload, dict):
                raise ValueError(f"JSONL row must be an object: {path}")
            rows.append(payload)
    return rows


def _read_jsonl_with_hashes(
    path: Path,
) -> tuple[list[dict[str, object]], dict[str, str]]:
    rows: list[dict[str, object]] = []
    hashes: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines(keepends=True):
        if not line.strip():
            continue
        payload = json.loads(line)
        if not isinstance(payload, dict):
            raise ValueError(f"JSONL row must be an object: {path}")
        case_id = str(payload.get("case_id") or "")
        if not case_id or case_id in hashes:
            raise ValueError(f"duplicate or blank case result ID: {case_id}")
        canonical_line = (
            json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        )
        hashes[case_id] = hashlib.sha256(canonical_line.encode("utf-8")).hexdigest()
        rows.append(payload)
    return rows, hashes


def _unique_by(
    rows: Sequence[Mapping[str, object]],
    field: str,
    label: str,
) -> dict[str, Mapping[str, object]]:
    output: dict[str, Mapping[str, object]] = {}
    for row in rows:
        key = str(row.get(field) or "")
        if not key:
            raise ValueError(f"{label} has blank {field}")
        if key in output:
            raise ValueError(f"duplicate {label} {field}: {key}")
        output[key] = row
    return output


def _unique_event_rows(
    rows: Sequence[Mapping[str, object]],
    label: str,
) -> dict[tuple[str, str], Mapping[str, object]]:
    output: dict[tuple[str, str], Mapping[str, object]] = {}
    for row in rows:
        key = (str(row.get("case_id") or ""), str(row.get("event_code") or ""))
        if not all(key):
            raise ValueError(f"{label} has blank case_id or event_code")
        if key in output:
            raise ValueError(f"duplicate {label}: {key[0]} {key[1]}")
        output[key] = row
    return output


def _require_exact_keys(
    expected: Mapping[object, object],
    actual: Mapping[object, object],
    label: str,
) -> None:
    missing = sorted(str(key) for key in set(expected) - set(actual))
    unknown = sorted(str(key) for key in set(actual) - set(expected))
    if missing:
        raise ValueError(f"incomplete {label}; missing: {', '.join(missing)}")
    if unknown:
        raise ValueError(f"unknown {label} result: {', '.join(unknown)}")


def _parse_reviewed_severity(value: object, label: str) -> Severity:
    try:
        return Severity(str(value))
    except ValueError as error:
        raise ValueError(f"invalid reviewed severity for {label}") from error


def _case_has_automatic_failure(row: Mapping[str, object]) -> bool:
    events = row.get("events")
    if not isinstance(events, list):
        return False
    for event in events:
        if not isinstance(event, Mapping):
            continue
        try:
            severity = Severity(str(event.get("severity") or "PASS"))
        except ValueError:
            continue
        if severity.rank <= Severity.SEV2.rank:
            return True
    return False


def _canonical_json(payload: Mapping[str, object]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"


def _canonical_json_line(payload: Mapping[str, object]) -> str:
    return _canonical_json(payload)


def _atomic_text(path: Path, text: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(text, encoding="utf-8", newline="\n")
    temporary.replace(path)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
