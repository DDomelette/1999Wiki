"""Immutable evidence bundle writer and concise module report renderer."""
from __future__ import annotations

import hashlib
import json
import math
import random
import re
import shutil
import uuid
from pathlib import Path
from typing import Mapping, Sequence

from .contracts import CaseResult, EvalCase, RunManifest, to_jsonable
from .scoring import MODULES, P0_SPEC_IDS, RunSummary


REQUIRED_ARTIFACTS = (
    "run_manifest.v2.json",
    "sample_manifest.v2.jsonl",
    "case_results.v2.jsonl",
    "module_summary.v2.json",
    "evaluation_report.v2.md",
    "pre_protected_snapshot.v2.json",
    "post_protected_snapshot.v2.json",
    "memory_pair_results.v1.jsonl",
    "stage_latency.v1.json",
    "adjudication_queue.v2.jsonl",
    "human_audit_manifest.v1.jsonl",
    "isolated_route_failure.v1.json",
)
_WINDOWS_PATH_RE = re.compile(r"(?i)(?:[a-z]:\\|[a-z]:/)[^\s|`]+")


def select_human_audit(
    cases: Sequence[EvalCase | str],
    *,
    seed: int,
) -> tuple[str, ...]:
    unique: dict[str, EvalCase | str] = {}
    for item in cases:
        case_id = item.case_id if isinstance(item, EvalCase) else str(item)
        if case_id:
            unique.setdefault(case_id, item)
    target = min(len(unique), max(12, math.ceil(0.20 * len(unique))))
    if target == 0:
        return ()

    groups: dict[tuple[object, ...], list[str]] = {}
    for case_id, item in unique.items():
        if isinstance(item, EvalCase):
            group = (
                item.expected_ownership_key[0] if item.expected_ownership_key else "none",
                item.difficulty.value,
                item.scenario,
                item.conversation_mode,
                bool(item.route_options.get("free_supplement")),
            )
        else:
            group = ("unclassified",)
        groups.setdefault(group, []).append(case_id)

    rng = random.Random(seed)
    for values in groups.values():
        values.sort()
        rng.shuffle(values)
    selected: list[str] = []
    ordered_groups = sorted(groups, key=lambda value: tuple(str(item) for item in value))
    while len(selected) < target:
        progressed = False
        for group in ordered_groups:
            values = groups[group]
            if values and len(selected) < target:
                selected.append(values.pop())
                progressed = True
        if not progressed:
            break
    return tuple(selected)


def write_run_evidence(
    *,
    output_root: Path,
    manifest: RunManifest,
    samples: Sequence[EvalCase],
    cases: Sequence[CaseResult],
    summary: RunSummary,
    pre_snapshot: Mapping[str, object],
    post_snapshot: Mapping[str, object],
    adjudication_queue: Sequence[Mapping[str, object]],
    memory_pair_results: Sequence[object],
    stage_latency: Mapping[str, object],
    isolated_route_failure: Mapping[str, object] | None = None,
) -> Path:
    output_root = Path(output_root)
    run_dir = output_root / manifest.run_id
    if run_dir.exists():
        raise FileExistsError(f"run_id already exists: {manifest.run_id}")
    output_root.mkdir(parents=True, exist_ok=True)
    temporary_dir = output_root / f".{manifest.run_id}.tmp-{uuid.uuid4().hex}"
    temporary_dir.mkdir()

    predecessor: str | None = None
    try:
        predecessor = _write_json(
            temporary_dir / REQUIRED_ARTIFACTS[0],
            _document(to_jsonable(manifest), "rag_eval.run_manifest/v2", predecessor),
        )
        sample_documents = [
            _document(sample.to_json(), "rag_eval.sample/v2", predecessor)
            for sample in samples
        ]
        predecessor = _write_jsonl(
            temporary_dir / REQUIRED_ARTIFACTS[1],
            sample_documents,
        )
        case_documents = [
            _document(to_jsonable(case), "rag_eval.case_result/v2", predecessor)
            for case in cases
        ]
        predecessor = _write_jsonl(
            temporary_dir / REQUIRED_ARTIFACTS[2],
            case_documents,
        )
        case_hashes = {
            str(row.get("case_id") or ""): _json_line_sha256(row)
            for row in case_documents
        }
        summary_payload = to_jsonable(summary)
        assert isinstance(summary_payload, dict)
        summary_payload.update(
            {
                "run_id": manifest.run_id,
                "snapshot_equal": _snapshots_equal(pre_snapshot, post_snapshot),
            }
        )
        predecessor = _write_json(
            temporary_dir / REQUIRED_ARTIFACTS[3],
            _document(summary_payload, "rag_eval.module_summary/v2", predecessor),
        )
        report = render_report(
            summary,
            predecessor_sha256=predecessor,
            run_id=manifest.run_id,
            snapshot_equal=_snapshots_equal(pre_snapshot, post_snapshot),
        )
        predecessor = _write_text(temporary_dir / REQUIRED_ARTIFACTS[4], report)
        predecessor = _write_json(
            temporary_dir / REQUIRED_ARTIFACTS[5],
            _document(dict(pre_snapshot), "rag_eval.protected_snapshot/v2", predecessor),
        )
        predecessor = _write_json(
            temporary_dir / REQUIRED_ARTIFACTS[6],
            _document(dict(post_snapshot), "rag_eval.protected_snapshot/v2", predecessor),
        )
        predecessor = _write_jsonl(
            temporary_dir / REQUIRED_ARTIFACTS[7],
            [
                _document(
                    _mapping_payload(row),
                    "rag_eval.memory_pair_result/v1",
                    predecessor,
                )
                for row in memory_pair_results
            ],
        )
        predecessor = _write_json(
            temporary_dir / REQUIRED_ARTIFACTS[8],
            _document(dict(stage_latency), "rag_eval.stage_latency/v1", predecessor),
        )
        predecessor = _write_jsonl(
            temporary_dir / REQUIRED_ARTIFACTS[9],
            [
                _document(dict(row), "rag_eval.adjudication/v2", predecessor)
                for row in adjudication_queue
            ],
        )
        by_id = {sample.case_id: sample for sample in samples}
        unique_samples = [sample for sample in samples if sample.repeat_of is None]
        audit_ids = select_human_audit(unique_samples, seed=manifest.seed)
        audit_rows = []
        for case_id in audit_ids:
            sample = by_id[case_id]
            evidence_sha256 = case_hashes.get(case_id)
            if evidence_sha256 is None:
                raise ValueError(f"human audit case lacks result evidence: {case_id}")
            audit_rows.append(
                _document(
                    {
                        "case_id": case_id,
                        "seed": manifest.seed,
                        "stratum": {
                            "entity_type": (
                                sample.expected_ownership_key[0]
                                if sample.expected_ownership_key
                                else "none"
                            ),
                            "difficulty": sample.difficulty.value,
                            "scenario": sample.scenario,
                            "conversation_mode": sample.conversation_mode,
                            "free_supplement": bool(
                                sample.route_options.get("free_supplement")
                            ),
                        },
                        "evidence_ref": f"case_results.v2.jsonl#{case_id}",
                        "evidence_sha256": evidence_sha256,
                    },
                    "rag_eval.human_audit_manifest/v1",
                    predecessor,
                )
            )
        predecessor = _write_jsonl(temporary_dir / REQUIRED_ARTIFACTS[10], audit_rows)
        _write_json(
            temporary_dir / REQUIRED_ARTIFACTS[11],
            _document(
                dict(isolated_route_failure or {"passed": False, "missing": True}),
                "rag_eval.isolated_route_failure/v1",
                predecessor,
            ),
        )
        temporary_dir.replace(run_dir)
    except BaseException:
        shutil.rmtree(temporary_dir, ignore_errors=True)
        raise
    return run_dir


def render_report(
    summary: RunSummary,
    *,
    predecessor_sha256: str | None,
    run_id: str = "",
    snapshot_equal: bool | None = None,
) -> str:
    lines = [
        "# RAG Full-Chain Evaluation",
        "",
        f"- Run ID: **{run_id or 'unassigned'}**",
        f"- Global severity: **{summary.global_severity.value}**",
        f"- Accepted: **{str(summary.accepted).lower()}**",
        f"- Accepted with warnings: **{str(summary.accepted_with_warnings).lower()}**",
        f"- Cases: **{summary.case_count}**",
        f"- Snapshot equal: **{str(snapshot_equal).lower() if snapshot_equal is not None else 'pending'}**",
        f"- Evidence predecessor SHA-256: `{predecessor_sha256 or 'none'}`",
        "",
        "## Modules",
        "",
        "| Module | Score | Severity | Worst event |",
        "|---|---:|---|---|",
    ]
    for module in MODULES:
        item = summary.modules[module]
        score = "n/a" if item.score is None else f"{item.score:.2f}"
        worst = min(item.events, key=lambda event: event.severity.rank, default=None)
        lines.append(
            f"| {module} | {score} | {item.severity.value} | "
            f"{worst.event_code if worst else '-'} |"
        )

    lines.extend(
        [
            "",
            "## D1-D4",
            "",
            "| Difficulty | Count | Mean | Floor pass | Severity |",
            "|---|---:|---:|---:|---|",
        ]
    )
    for difficulty, item in summary.difficulties.items():
        mean = "n/a" if item.mean_score is None else f"{item.mean_score:.2f}"
        pass_rate = "n/a" if item.floor_pass_rate is None else f"{item.floor_pass_rate:.1%}"
        lines.append(
            f"| {difficulty.value} | {item.count} | {mean} | {pass_rate} | {item.severity.value} |"
        )

    clusters = _failure_clusters(summary)
    lines.extend(["", "## Failure Clusters", ""])
    if not clusters:
        lines.append("No failure clusters.")
    else:
        for index, cluster in enumerate(clusters[:5], start=1):
            lines.append(
                f"{index}. `{cluster['code']}` ({cluster['severity']}, "
                f"{cluster['count']} occurrence(s), {cluster['cases']} case(s))"
            )

    actions = _remediation_actions(summary)
    lines.extend(["", "## Remediation", ""])
    if not actions:
        lines.append("No remediation required.")
    else:
        for index, action in enumerate(actions[:5], start=1):
            lines.append(f"{index}. {_sanitize_report_text(action)}")
    lines.extend(["", "## P0 Coverage", ""])
    for module in MODULES:
        ids = ", ".join(f"`{spec_id}`" for spec_id in P0_SPEC_IDS[module])
        lines.append(f"- {module}: {ids}")
    return "\n".join(lines) + "\n"


def _failure_clusters(summary: RunSummary) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str], dict[str, object]] = {}
    for event in summary.events:
        key = (event.event_code, event.severity.value)
        cluster = grouped.setdefault(
            key,
            {
                "code": event.event_code,
                "severity": event.severity.value,
                "rank": event.severity.rank,
                "count": 0,
                "case_ids": set(),
            },
        )
        cluster["count"] = int(cluster["count"]) + 1
        case_ids = cluster["case_ids"]
        assert isinstance(case_ids, set)
        case_ids.update(event.case_ids)
    result = []
    for cluster in grouped.values():
        case_ids = cluster.pop("case_ids")
        assert isinstance(case_ids, set)
        cluster["cases"] = len(case_ids)
        result.append(cluster)
    return sorted(result, key=lambda item: (int(item["rank"]), -int(item["count"]), str(item["code"])))


def _remediation_actions(summary: RunSummary) -> list[str]:
    ordered: list[tuple[int, str]] = []
    for event in summary.events:
        if event.recommended_action:
            ordered.append((event.severity.rank, event.recommended_action))
    for warning in summary.warnings:
        ordered.append((SeverityRank.WARNING, warning.recommended_action))
    seen: set[str] = set()
    actions: list[str] = []
    for _, action in sorted(ordered, key=lambda item: item[0]):
        if action not in seen:
            seen.add(action)
            actions.append(action)
    return actions


class SeverityRank:
    WARNING = 3


def _document(
    payload: Mapping[str, object],
    schema_version: str,
    predecessor_sha256: str | None,
) -> dict[str, object]:
    result = dict(payload)
    result["schema_version"] = schema_version
    result["predecessor_sha256"] = predecessor_sha256
    return result


def _write_json(path: Path, payload: Mapping[str, object]) -> str:
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    return _write_text(path, text)


def _write_jsonl(path: Path, rows: Sequence[Mapping[str, object]]) -> str:
    text = "".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        for row in rows
    )
    return _write_text(path, text)


def _json_line_sha256(row: Mapping[str, object]) -> str:
    text = json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _mapping_payload(value: object) -> dict[str, object]:
    payload = to_jsonable(value)
    if not isinstance(payload, dict):
        raise TypeError("evidence row must serialize to an object")
    return payload


def _write_text(path: Path, text: str) -> str:
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(text, encoding="utf-8", newline="\n")
    temporary.replace(path)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sanitize_report_text(value: str) -> str:
    sanitized = _WINDOWS_PATH_RE.sub("[local-path-redacted]", value)
    return sanitized.replace("api_key", "credential").replace("API_KEY", "credential")


def _snapshots_equal(
    before: Mapping[str, object],
    after: Mapping[str, object],
) -> bool:
    return _stable_snapshot_value(before) == _stable_snapshot_value(after)


def _stable_snapshot_value(value: object) -> object:
    if isinstance(value, Mapping):
        ignored = {"captured_at_utc", "inventory_sha256", "predecessor_sha256"}
        return {
            str(key): _stable_snapshot_value(item)
            for key, item in value.items()
            if key not in ignored
        }
    if isinstance(value, (list, tuple)):
        return [_stable_snapshot_value(item) for item in value]
    return value
