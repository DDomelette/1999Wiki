"""Freeze Story Segment gold or capture a read-only active-system baseline.

The gold-freeze mode is deliberately available only against a D-accepted
Thread-C release receipt.  Baseline capture is implemented below as a separate
mode so the frozen labels cannot depend on candidate retrieval output.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import asdict, fields, is_dataclass
from datetime import datetime, timezone
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping, Sequence
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.rag_eval.story_segment_baseline import (
    AtomEvidenceTarget,
    StorySegmentEvalCase,
    canonical_evidence_text,
    evidence_sha256,
    load_story_segment_eval,
    load_story_segment_thresholds,
    match_active_evidence_to_atoms,
    verify_eval_gold_against_atom_artifact,
)


C_RELEASE_SCHEMA = "rag.thread-c-release/v1"
EVAL_SCHEMA = "rag.story-segment-eval-case/v1"
GOLD_ARTIFACT_SHA256 = "40d17b412a60c44bcdab953d9d382d3fb32f0812026b0eb51b972961c40999a1"
DEFAULT_C_RELEASE_RECEIPT = Path(
    "eval/story_segment/dependencies/c-release-20260802T110503Z/c-release-receipt.v1.json"
)
BASELINE_SCHEMA = "rag.story-segment-active-baseline/v1"
EQUIVALENCE_SCHEMA = "rag.story-segment-atom-equivalence/v1"
NON_IDENTITY_FIELDS = frozenset({"captured_at_utc", "run_id", "baseline_identity_sha256"})
SOURCE_REF_FIELDS = (
    "source_title",
    "json_path",
    "source_content_sha256",
    "revid",
    "pageid",
)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_json(payload: Mapping[str, object]) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _canonical_bytes(payload: Mapping[str, object]) -> bytes:
    return (_canonical_json(payload) + "\n").encode("utf-8")


def baseline_business_sha256(payload: Mapping[str, object]) -> str:
    """Hash every baseline fact except explicitly non-identity run metadata."""

    business = {key: value for key, value in payload.items() if key not in NON_IDENTITY_FIELDS}
    return hashlib.sha256(_canonical_bytes(business)).hexdigest()


def case_result_sha256(payload: Mapping[str, object]) -> str:
    result = {key: value for key, value in payload.items() if key != "result_sha256"}
    return hashlib.sha256(_canonical_bytes(result)).hexdigest()


def _jsonable(value: object) -> object:
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _sanitize_source_refs(value: object) -> list[dict[str, object]]:
    if not isinstance(value, (list, tuple)):
        return []
    refs: list[dict[str, object]] = []
    for raw in value:
        if not isinstance(raw, Mapping):
            continue
        ref = {
            field: raw[field]
            for field in SOURCE_REF_FIELDS
            if field in raw and isinstance(raw[field], (str, int))
        }
        if ref:
            refs.append(dict(sorted(ref.items())))
    return refs


def sanitize_active_result(result: Mapping[str, object]) -> dict[str, object]:
    """Keep only source-backed retrieval evidence; generated text is excluded."""

    content = canonical_evidence_text(str(result.get("text") or result.get("content") or ""))
    score = result.get("score", result.get("bm25_score", result.get("vector_score", 0.0)))
    try:
        numeric_score = float(score or 0.0)
    except (TypeError, ValueError):
        numeric_score = 0.0
    atom_id = result.get("atom_id")
    normalized_hash = result.get("normalized_evidence_sha256")
    if not isinstance(normalized_hash, str) or len(normalized_hash) != 64:
        normalized_hash = evidence_sha256(content)
    return {
        "atom_id": str(atom_id) if isinstance(atom_id, str) and atom_id else None,
        "category": str(result.get("category") or ""),
        "child_id": str(result.get("child_id") or result.get("id") or ""),
        "content": content,
        "entity_id": str(result.get("entity_id") or ""),
        "entity_name": str(result.get("entity_name") or result.get("name") or ""),
        "entity_type": str(result.get("entity_type") or ""),
        "heading_path": str(result.get("heading_path") or result.get("title") or ""),
        "normalized_evidence_sha256": normalized_hash,
        "owner_entity_id": str(result.get("owner_entity_id") or ""),
        "owner_page_id": str(result.get("owner_page_id") or ""),
        "parent_id": str(result.get("parent_id") or result.get("source") or ""),
        "score": numeric_score,
        "section_kind": str(result.get("section_kind") or ""),
        "source_refs": _sanitize_source_refs(result.get("source_refs")),
    }


def build_equivalence_rows(
    gold_by_query: Mapping[str, Sequence[AtomEvidenceTarget]],
    observations: Mapping[str, Mapping[str, Sequence[Mapping[str, object]]]],
    *,
    evidence_text_by_sha256: Mapping[str, str],
) -> tuple[dict[str, object], ...]:
    """Build stable, independently re-matchable equivalence evidence."""

    rows: list[dict[str, object]] = []
    for query_id in sorted(gold_by_query):
        targets = tuple(gold_by_query[query_id])
        observed = observations.get(query_id, {})
        for stage in ("retrieval_at_k", "final_context"):
            active_results: list[dict[str, object]] = []
            for raw in observed.get(stage, ()):
                item = dict(raw)
                item["gold_evidence_text_by_sha256"] = dict(evidence_text_by_sha256)
                active_results.append(item)
            matches = match_active_evidence_to_atoms(active_results, targets, stage=stage)  # type: ignore[arg-type]
            target_by_id = {target.atom_id: target for target in targets}
            for match in matches:
                active = (
                    active_results[match.result_rank - 1]
                    if 1 <= match.result_rank <= len(active_results)
                    else {}
                )
                target = target_by_id[match.atom_id]
                rows.append(
                    {
                        "active_source_refs": _sanitize_source_refs(active.get("source_refs")),
                        "atom_id": match.atom_id,
                        "match_rule": match.match_rule,
                        "matched": match.matched,
                        "matched_span": list(match.matched_span) if match.matched_span else None,
                        "normalized_evidence_sha256": target.normalized_evidence_sha256,
                        "query_id": match.query_id,
                        "reason_code": match.reason_code,
                        "result_rank": match.result_rank,
                        "schema_version": EQUIVALENCE_SCHEMA,
                        "stage": match.stage,
                        "target_source_ref": {
                            "json_path": target.source_json_path,
                            "source_content_sha256": target.source_content_sha256,
                            "source_title": target.source_title,
                        },
                    }
                )
    stage_order = {"retrieval_at_k": 0, "final_context": 1}
    rows.sort(
        key=lambda row: (
            str(row["query_id"]),
            stage_order[str(row["stage"])],
            int(row["result_rank"]),
            str(row["atom_id"]),
        )
    )
    return tuple(rows)


def _load_c_release(receipt_path: Path) -> tuple[dict[str, object], Path]:
    receipt_path = receipt_path.resolve(strict=True)
    sidecar = receipt_path.with_suffix(".sha256")
    if not sidecar.is_file():
        raise ValueError("C release SHA-256 sidecar is missing")
    expected = sidecar.read_text(encoding="utf-8").strip().split()[0]
    actual = _sha256_file(receipt_path)
    if expected != actual:
        raise ValueError("C release receipt SHA-256 does not match its sidecar")
    payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != C_RELEASE_SCHEMA:
        raise ValueError("unsupported C release receipt schema")
    if payload.get("e_dependency_ready") is not True:
        raise ValueError("C release is not ready for the E dependency")
    if payload.get("story_dependency_blockers") != []:
        raise ValueError("C release still contains Story dependency blockers")
    if payload.get("protected_identity_count") != 32 or payload.get("protected_drift_count") != 0:
        raise ValueError("C release protected identity gate failed")
    published = payload.get("published_artifacts")
    if not isinstance(published, dict):
        raise ValueError("C release published artifacts are missing")
    story_atoms = published.get("story_atoms")
    if not isinstance(story_atoms, dict):
        raise ValueError("C release Story Atom identity is missing")
    atom_path = Path(str(story_atoms.get("path", ""))).resolve(strict=True)
    if story_atoms.get("sha256") != GOLD_ARTIFACT_SHA256:
        raise ValueError("C release Story Atom identity is not the approved artifact")
    if _sha256_file(atom_path) != story_atoms.get("sha256"):
        raise ValueError("C release Story Atom artifact hash mismatch")
    if story_atoms.get("row_count") != 142811:
        raise ValueError("C release Story Atom row count mismatch")
    return payload, atom_path


def _load_atoms(path: Path) -> tuple[dict[str, object], ...]:
    rows = tuple(json.loads(line) for line in path.read_text(encoding="utf-8").splitlines())
    if len(rows) != 142811:
        raise ValueError("Story Atom artifact changed during gold freeze")
    identifiers = [str(row.get("child_id", "")) for row in rows]
    if len(set(identifiers)) != len(identifiers) or any(not value for value in identifiers):
        raise ValueError("Story Atom IDs are empty or duplicated")
    return rows


def _eligible(row: Mapping[str, object]) -> bool:
    text = row.get("content")
    return (
        isinstance(text, str)
        and 6 <= len(text) <= 240
        and "<" not in text
        and "\x00" not in text
        and isinstance(row.get("source_refs"), list)
        and len(row["source_refs"]) == 1
    )


def _atom_target(row: Mapping[str, object]) -> dict[str, str]:
    refs = row["source_refs"]
    assert isinstance(refs, list) and len(refs) == 1 and isinstance(refs[0], dict)
    ref = refs[0]
    text = canonical_evidence_text(str(row["content"]))
    return {
        "atom_id": str(row["child_id"]),
        "normalized_evidence_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "source_content_sha256": str(ref["source_content_sha256"]),
        "source_json_path": str(ref["json_path"]),
        "source_title": str(ref["source_title"]),
    }


def _mention_spans(query: str, names: Sequence[str]) -> list[dict[str, object]]:
    spans: list[dict[str, object]] = []
    cursor = 0
    for name in names:
        start = query.find(name, cursor)
        if start < 0:
            raise ValueError(f"query does not contain ordered Story mention: {name}")
        end = start + len(name)
        spans.append({"end": end, "kind": "story_mention", "start": start, "text": name})
        cursor = end
    return spans


def _case(
    *,
    query_id: str,
    query: str,
    stratum: str,
    query_type: str,
    rows_by_group: Sequence[Sequence[Mapping[str, object]]] = (),
    owners: Sequence[str] = (),
    owner_names: Sequence[str] = (),
    origin: str | None = "direct_query",
    coverage: str | None = "complete",
    forbidden: Sequence[str] = (),
    allow_shortfall: bool = False,
    evidence_state: str = "sufficient",
    narrative_coverage: str = "local",
    retrieval_outcome: str = "sufficient",
    planner_calls: int = 1,
    detector_calls: int = 1,
    retriever_calls: int = 1,
    continuation: Mapping[str, object] | None = None,
    anchor: Mapping[str, object] | None = None,
    topic_source: bool = False,
    branch_constraints: Mapping[str, object] | None = None,
    scope_applicable: bool = True,
) -> dict[str, object]:
    groups: list[dict[str, object]] = []
    source_relevance: dict[str, str] = {}
    for index, rows in enumerate(rows_by_group, 1):
        atoms = [_atom_target(row) for row in rows]
        group_id = f"{query_id}-g{index}"
        groups.append({"atoms": atoms, "group_id": group_id})
        source_relevance.update({atom["atom_id"]: "required" for atom in atoms})
    review_sources = [
        f"{atom['source_title']}:{atom['source_json_path']}@{atom['source_content_sha256']}"
        for group in groups
        for atom in group["atoms"]
    ]
    topic_sources: list[dict[str, object]] = []
    if topic_source:
        topic_sources.append(
            {
                "content_sha256": "cc869a3854cea277551ce78a28908b4ed315e5345455b8d02327ea5acf4d9607",
                "pageid": 161,
                "revid": 366311,
                "source_title": "暴雨",
                "source_type": "page",
            }
        )
    return {
        "allow_shortfall": allow_shortfall,
        "anchor": dict(anchor or {}),
        "branch_constraints": dict(
            branch_constraints
            or {
                "allow_cross_exclusive_branch": False,
                "allow_cycle_reentry": False,
                "allowed_story_owner_ids": list(owners),
            }
        ),
        "continuation": dict(continuation or {}),
        "expected_answer_scope": (
            {
                "applicable": True,
                "value": {
                    "authorization_coverage_scope": coverage,
                    "evidence_state": evidence_state,
                    "narrative_coverage": narrative_coverage,
                },
            }
            if scope_applicable
            else {"applicable": False, "value": None}
        ),
        "expected_authorization_origin": origin,
        "expected_call_counts": {
            "planner": planner_calls,
            "reranker": 0,
            "retriever": retriever_calls,
            "story_detector": detector_calls,
        },
        "expected_retrieval_outcome": retrieval_outcome,
        "expected_story_owner_ids": list(owners),
        "expected_story_owner_order": list(owners),
        "forbidden_owner_ids": list(forbidden),
        "gold_artifact_sha256": GOLD_ARTIFACT_SHA256,
        "query": query,
        "query_id": query_id,
        "query_type": query_type,
        "request_plan_source_spans": _mention_spans(query, owner_names),
        "required_atom_groups": groups,
        "required_topic_page_sources": topic_sources,
        "review": {
            "review_basis": "Thread D inspected the exact C-release Atom rows and source refs",
            "review_sources": review_sources,
            "reviewed_by": "thread_d",
            "status": "human_reviewed",
        },
        "schema_version": EVAL_SCHEMA,
        "source_relevance": source_relevance,
        "stratum": stratum,
    }


def _snippet(row: Mapping[str, object], limit: int = 72) -> str:
    text = canonical_evidence_text(str(row["content"])).replace("\n", " ")
    return text if len(text) <= limit else text[:limit] + "…"


def _build_cases(rows: Sequence[Mapping[str, object]]) -> tuple[dict[str, object], ...]:
    by_story: dict[str, list[Mapping[str, object]]] = {}
    story_order: list[str] = []
    for row in rows:
        story_id = str(row["entity_id"])
        if story_id not in by_story:
            by_story[story_id] = []
            story_order.append(story_id)
        if _eligible(row):
            by_story[story_id].append(row)
    story_order = [story_id for story_id in story_order if len(by_story[story_id]) >= 5]
    for story_id in story_order:
        by_story[story_id].sort(key=lambda row: (int(row["chunk_index"]), str(row["child_id"])))

    cases: list[dict[str, object]] = []

    # 12 exact lexical cases: short dialogue, numeric text and internal IDs are
    # retained verbatim in the query while remaining explicitly Story-scoped.
    exact_story_ids = story_order[:12]
    for index, story_id in enumerate(exact_story_ids, 1):
        candidates = sorted(by_story[story_id], key=lambda row: (len(str(row["content"])), str(row["child_id"])))
        row = candidates[min(index - 1, len(candidates) - 1)]
        name = str(row["entity_name"])
        query = f"在剧情《{name}》（Data:Story/{story_id}.json）中精确查找：{_snippet(row, 96)}"
        cases.append(_case(query_id=f"exact-{index:02d}", query=query, stratum="exact_atom", query_type="exact_lexical", rows_by_group=((row,),), owners=(f"story:{story_id}",), owner_names=(name,)))

    # Protected non-Story aliases and one raw Story ID are explicit fixtures;
    # these prevent the Story detector from treating every short number or
    # long-word substring as a Story owner.
    for query_id, query in (("exact-13", "6是谁？"), ("exact-14", "37有什么技能？"), ("exact-15", "角色星锑的技能是什么？")):
        cases.append(_case(query_id=query_id, query=query, stratum="exact_atom", query_type="protected_non_story_alias", rows_by_group=(), owners=(), owner_names=(), origin=None, coverage=None, retrieval_outcome="sufficient", scope_applicable=False))
    raw_story_row = by_story["304502"][0]
    raw_story_name = str(raw_story_row["entity_name"])
    cases.append(_case(query_id="exact-16", query=f"Data:Story/304502 对应的剧情《{raw_story_name}》中写了什么？", stratum="exact_atom", query_type="internal_story_id", rows_by_group=((raw_story_row,),), owners=("story:304502",), owner_names=(raw_story_name,)))
    cases.append(_case(query_id="exact-17", query="请解释 Data:Story/304502式样 这一连续长词的命名规则。", stratum="exact_atom", query_type="long_substring_negative", rows_by_group=(), owners=(), owner_names=(), origin=None, coverage=None, retrieval_outcome="empty", scope_applicable=False))

    # 10 single-Story facts across early/middle/late positions.
    for index, story_id in enumerate(story_order[12:22], 1):
        candidates = by_story[story_id]
        row = candidates[((index - 1) % 3) * (len(candidates) - 1) // 2]
        name = str(row["entity_name"])
        query = f"剧情《{name}》中哪段内容说明了“{_snippet(row)}”？"
        cases.append(_case(query_id=f"single-{index:02d}", query=query, stratum="single_story_fact", query_type=("opening_fact", "middle_fact", "ending_fact")[(index - 1) % 3], rows_by_group=((row,),), owners=(f"story:{story_id}",), owner_names=(name,)))

    # 10 multi-detail cases; every detail is a separate required group.
    for index, story_id in enumerate(story_order[22:32], 1):
        candidates = by_story[story_id]
        first = candidates[len(candidates) // 3]
        second = candidates[(2 * len(candidates)) // 3]
        name = str(first["entity_name"])
        query = f"请结合剧情《{name}》说明“{_snippet(first, 42)}”和“{_snippet(second, 42)}”这两个细节。"
        cases.append(_case(query_id=f"multi-detail-{index:02d}", query=query, stratum="single_story_multi_detail", query_type=("cause", "process", "relationship")[(index - 1) % 3], rows_by_group=((first,), (second,)), owners=(f"story:{story_id}",), owner_names=(name,), allow_shortfall=True, evidence_state="partial", narrative_coverage="bounded", retrieval_outcome="partial"))

    # 8 graph-boundary cases. Gold is source-backed; constraints, not labels,
    # prohibit crossing an unselected choice/cycle/terminal boundary.
    boundary_types = ("choice", "exclusive_branch", "merge", "cycle", "terminal", "choice", "merge", "terminal")
    for index, story_id in enumerate(story_order[32:40], 1):
        candidates = by_story[story_id]
        row = candidates[len(candidates) // 2]
        name = str(row["entity_name"])
        boundary_type = boundary_types[index - 1]
        query = f"仅依据剧情《{name}》当前路径，说明“{_snippet(row)}”；不要跨越未选择的{boundary_type}边界。"
        cases.append(_case(query_id=f"branch-{index:02d}", query=query, stratum="branch_boundary", query_type=boundary_type, rows_by_group=((row,),), owners=(f"story:{story_id}",), owner_names=(name,), forbidden=(f"story:{story_order[40 + index]}",), branch_constraints={"allow_cross_exclusive_branch": False, "allow_cycle_reentry": False, "boundary_type": boundary_type, "selected_story_owner_id": f"story:{story_id}"}))

    # 8 explicit two/three Story cases, preserving original owner order.
    multi_pool = story_order[40:58]
    for index in range(8):
        selected = multi_pool[index * 2:index * 2 + (3 if index >= 6 else 2)]
        selected = selected[:3]
        selected_rows = [by_story[story_id][len(by_story[story_id]) // 2] for story_id in selected]
        names = [str(row["entity_name"]) for row in selected_rows]
        query = "、".join(f"《{name}》" for name in names) + "分别有哪些关键片段？按提问顺序回答。"
        cases.append(_case(query_id=f"multi-story-{index + 1:02d}", query=query, stratum="multi_story", query_type=f"explicit_{len(selected)}_story", rows_by_group=tuple((row,) for row in selected_rows), owners=tuple(f"story:{story_id}" for story_id in selected), owner_names=tuple(names), allow_shortfall=True, evidence_state="partial", narrative_coverage="bounded", retrieval_outcome="partial"))

    # 8 Topic/Page definition + Story-example cases, anchored to the exact
    # 2026-07-07 暴雨 page revision and eight distinct Story sources.
    storm_rows: list[Mapping[str, object]] = []
    seen_stories: set[str] = set()
    for row in rows:
        if _eligible(row) and "暴雨" in str(row["content"]) and str(row["entity_id"]) not in seen_stories:
            storm_rows.append(row)
            seen_stories.add(str(row["entity_id"]))
        if len(storm_rows) == 8:
            break
    if len(storm_rows) != 8:
        raise ValueError("could not freeze eight distinct 暴雨 Story examples")
    for index, row in enumerate(storm_rows, 1):
        story_id = str(row["entity_id"])
        name = str(row["entity_name"])
        query = f"暴雨是什么？再用剧情《{name}》中的“{_snippet(row)}”作为例证。"
        cases.append(_case(query_id=f"topic-story-{index:02d}", query=query, stratum="topic_story", query_type="topic_definition_with_story_example", rows_by_group=((row,),), owners=(f"story:{story_id}",), owner_names=(name,), topic_source=True, allow_shortfall=True, evidence_state="partial", narrative_coverage="bounded", retrieval_outcome="partial"))

    # 4 character-to-Story mention cases deliberately allow evidence shortfall.
    character_targets = (("伊索尔德", "100601"), ("伊索尔德", "100607"), ("十四行诗", "100002"), ("十四行诗", "100003"))
    for index, (term, target_story_id) in enumerate(character_targets, 1):
        row = next(row for row in rows if _eligible(row) and str(row["entity_id"]) == target_story_id and term in str(row["content"]))
        story_id = str(row["entity_id"])
        name = str(row["entity_name"])
        if index == 1:
            query = f"伊索尔德是在哪一章出现的？请以剧情《{name}》的来源说明。"
        elif index == 2:
            query = f"伊索尔德是怎么疯掉的？请结合剧情《{name}》作有限综合。"
        elif index == 3:
            query = f"十四行诗在剧情《{name}》中经历了什么？若资料不足请明确范围。"
        else:
            query = f"十四行诗的技能是什么？另外介绍剧情《{name}》中的相关片段。"
        cases.append(_case(query_id=f"character-story-{index:02d}", query=query, stratum="character_story_shortfall", query_type="character_story_mention" if index < 4 else "character_skill_story_composite", rows_by_group=((row,),), owners=(f"story:{story_id}",), owner_names=(name,), allow_shortfall=True, evidence_state="partial", narrative_coverage="bounded", retrieval_outcome="partial"))

    # 12 authorization-state cases: direct 1/2/3, deterministic pagination,
    # denial, continuation, tamper rejection, anchor set/clear and open domain.
    auth_ids = story_order[58:91]
    auth_rows = {story_id: by_story[story_id][len(by_story[story_id]) // 2] for story_id in auth_ids}
    def add_auth(index: int, selected: Sequence[str], *, query_suffix: str, **kwargs: object) -> None:
        selected_rows = [auth_rows[story_id] for story_id in selected]
        names = [str(row["entity_name"]) for row in selected_rows]
        query = "、".join(f"《{name}》" for name in names) + query_suffix
        cases.append(_case(query_id=f"auth-{index:02d}", query=query, stratum="authorization", query_type=str(kwargs.pop("query_type", "direct_authorization")), rows_by_group=tuple((row,) for row in selected_rows[:3]), owners=tuple(f"story:{story_id}" for story_id in selected[:3]), owner_names=tuple(names), **kwargs))
    add_auth(1, auth_ids[:1], query_suffix="讲了什么？")
    add_auth(2, auth_ids[1:3], query_suffix="分别讲了什么？")
    add_auth(3, auth_ids[3:6], query_suffix="分别讲了什么？")
    for index, count in ((4, 4), (5, 5), (6, 32)):
        selected = auth_ids[:count]
        selected_rows = [auth_rows[story_id] for story_id in selected]
        names = [str(row["entity_name"]) for row in selected_rows]
        query = "请依次介绍" + "、".join(f"《{name}》" for name in names) + "。"
        cases.append(_case(query_id=f"auth-{index:02d}", query=query, stratum="authorization", query_type=f"direct_{count}_story_pagination", rows_by_group=(), owners=(), owner_names=tuple(names), origin="direct_query", coverage=None, evidence_state="empty", narrative_coverage="local", retrieval_outcome="not_applicable", retriever_calls=0, scope_applicable=False, branch_constraints={"authorization_status": "needs_continuation", "detected_owner_count": count, "page_size": 3}))
    selected = auth_ids[:33]
    selected_rows = [auth_rows[story_id] for story_id in selected]
    names = [str(row["entity_name"]) for row in selected_rows]
    query = "请依次介绍" + "、".join(f"《{name}》" for name in names) + "。"
    cases.append(_case(query_id="auth-07", query=query, stratum="authorization", query_type="direct_33_story_denied", rows_by_group=(), owners=(), owner_names=tuple(names), origin="direct_query", coverage=None, evidence_state="empty", narrative_coverage="local", retrieval_outcome="not_applicable", retriever_calls=0, scope_applicable=False, branch_constraints={"authorization_status": "denied", "reason": "narrow_story_scope"}))
    continuation_id = auth_ids[0]
    continuation_row = auth_rows[continuation_id]
    cases.append(_case(query_id="auth-08", query="继续上一页剧情范围。", stratum="authorization", query_type="verified_continuation", rows_by_group=((continuation_row,),), owners=(f"story:{continuation_id}",), owner_names=(), origin="verified_continuation", coverage="page_partial", planner_calls=0, detector_calls=1, continuation={"expected_status": "valid", "max_payload_bytes": 65536, "page_index": 2}))
    cases.append(_case(query_id="auth-09", query="继续上一页剧情范围（篡改动作）。", stratum="authorization", query_type="tampered_continuation", rows_by_group=(), owners=(), owner_names=(), origin="verified_continuation", coverage=None, evidence_state="empty", narrative_coverage="local", retrieval_outcome="not_applicable", planner_calls=0, detector_calls=1, retriever_calls=0, scope_applicable=False, continuation={"expected_status": "rejected", "tamper": "payload_hash"}))
    anchor_id = auth_ids[1]
    anchor_row = auth_rows[anchor_id]
    cases.append(_case(query_id="auth-10", query="后来发生了什么？", stratum="authorization", query_type="validated_anchor", rows_by_group=((anchor_row,),), owners=(f"story:{anchor_id}",), owner_names=(), origin="validated_conversation_anchor", coverage="anchor_follow_up", anchor={"expected_transition": "consume", "owner_id": f"story:{anchor_id}"}))
    cases.append(_case(query_id="auth-11", query="刚才两个剧情后来分别发生了什么？", stratum="authorization", query_type="multi_owner_anchor_clear", rows_by_group=(), owners=(), owner_names=(), origin=None, coverage=None, evidence_state="empty", narrative_coverage="local", retrieval_outcome="not_applicable", retriever_calls=0, scope_applicable=False, anchor={"expected_transition": "clear", "reason": "multiple_story_owners"}))
    open_row = auth_rows[auth_ids[2]]
    cases.append(_case(query_id="auth-12", query="暴雨在哪些剧情中造成了影响？", stratum="authorization", query_type="open_story_domain", rows_by_group=((open_row,),), owners=(), owner_names=(), origin="direct_query", coverage="open_story_domain", allow_shortfall=True, evidence_state="partial", narrative_coverage="non_exhaustive", retrieval_outcome="partial", topic_source=True))

    # 8 orthogonal AnswerScope/outcome cases.
    answer_rows = [by_story[story_id][len(by_story[story_id]) // 2] for story_id in story_order[91:99]]
    scope_matrix = (
        ("sufficient", "local", "complete", "sufficient", False),
        ("partial", "bounded", "complete", "partial", True),
        ("partial", "non_exhaustive", "complete", "partial", True),
        ("empty", "local", "complete", "empty", False),
        ("empty", "local", None, "not_applicable", False),
        ("empty", "local", "complete", "failed", False),
        ("sufficient", "local", "anchor_follow_up", "sufficient", False),
        ("partial", "bounded", "complete", "partial", True),
    )
    for index, (row, matrix) in enumerate(zip(answer_rows, scope_matrix), 1):
        evidence_state, narrative, coverage, outcome, shortfall = matrix
        story_id = str(row["entity_id"])
        name = str(row["entity_name"])
        query = f"依据剧情《{name}》回答“{_snippet(row)}”所涉及的信息；按证据范围作答。"
        origin = "direct_query"
        owner_names: tuple[str, ...] = (name,)
        planner_calls = 1
        scope_applicable = outcome != "not_applicable" and outcome != "failed"
        anchor: Mapping[str, object] | None = None
        branch_constraints: Mapping[str, object] | None = None
        if index == 5:
            query = "你好，你是谁？"
            origin = None
            owner_names = ()
        elif index == 7:
            query = "接着呢？"
            origin = "validated_conversation_anchor"
            owner_names = ()
            anchor = {"expected_transition": "consume", "owner_id": f"story:{story_id}"}
        elif index == 8:
            query = f"你好。另外，请依据剧情《{name}》回答“{_snippet(row)}”所涉及的信息。"
            branch_constraints = {"allow_cross_exclusive_branch": False, "allow_cycle_reentry": False, "allowed_story_owner_ids": [f"story:{story_id}"], "top_level_grounding_mode": "mixed"}
        has_evidence = outcome in {"sufficient", "partial"}
        cases.append(_case(query_id=f"answer-scope-{index:02d}", query=query, stratum="answer_scope", query_type=("local_fact", "bounded", "exhaustive", "empty", "not_applicable", "failed", "anchor", "mixed_composite")[index - 1], rows_by_group=((row,),) if has_evidence else (), owners=(f"story:{story_id}",) if outcome != "not_applicable" else (), owner_names=owner_names, origin=origin, coverage=coverage, allow_shortfall=shortfall, evidence_state=evidence_state, narrative_coverage=narrative, retrieval_outcome=outcome, planner_calls=planner_calls, retriever_calls=0 if outcome == "not_applicable" else 1, scope_applicable=scope_applicable, anchor=anchor, branch_constraints=branch_constraints))

    if len(cases) < 80:
        raise AssertionError(f"expected at least 80 frozen cases, got {len(cases)}")
    return tuple(cases)


def freeze_gold(c_release_receipt: Path, output: Path) -> None:
    _, atom_path = _load_c_release(c_release_receipt)
    cases = _build_cases(_load_atoms(atom_path))
    payload = "".join(_canonical_json(case) + "\n" for case in cases)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(payload, encoding="utf-8", newline="\n")


def _git(*args: str, text_output: bool = True) -> str | bytes:
    result = subprocess.run(
        ["git", *args],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=text_output,
        encoding="utf-8" if text_output else None,
    )
    return result.stdout.strip() if text_output else result.stdout


def _assert_git_ancestor(ancestor: str, descendant: str, *, label: str) -> None:
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", ancestor, descendant],
        cwd=PROJECT_ROOT,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise ValueError(f"{label} is not an ancestor of {descendant}")


def _git_blob_sha256(commit: str, relative_path: str) -> str:
    raw = _git("show", f"{commit}:{relative_path}", text_output=False)
    assert isinstance(raw, bytes)
    return hashlib.sha256(raw).hexdigest()


def _count_lines(path: Path) -> int:
    count = 0
    with path.open("rb") as handle:
        for count, _ in enumerate(handle, 1):
            pass
    return count


def _validate_file_identity(path: Path, identity: Mapping[str, object], *, jsonl: bool) -> None:
    if path.stat().st_size != identity.get("size_bytes"):
        raise ValueError(f"published artifact size mismatch: {path.name}")
    if _sha256_file(path) != identity.get("sha256"):
        raise ValueError(f"published artifact SHA-256 mismatch: {path.name}")
    if jsonl and _count_lines(path) != identity.get("row_count"):
        raise ValueError(f"published artifact row count mismatch: {path.name}")


def validate_c_release_for_baseline(
    receipt_path: Path,
) -> tuple[dict[str, object], Path, dict[str, str]]:
    receipt, atom_path = _load_c_release(receipt_path)
    receipt_path = receipt_path.resolve(strict=True)
    release_root = receipt_path.parent
    current_head = str(_git("rev-parse", "HEAD"))
    c_merge = str(receipt.get("c_merge_commit") or "")
    if not re.fullmatch(r"[0-9a-f]{40}", c_merge):
        raise ValueError("C release merge commit is invalid")
    _assert_git_ancestor(c_merge, current_head, label="C release merge commit")

    phases = receipt.get("c_phase_commits")
    if not isinstance(phases, Mapping):
        raise ValueError("C release phase commits are missing")
    required_phases = ("c8a", "c8b", "c8c", "c8d", "c8d_product_acceptance", "c9")
    phase_commits: dict[str, str] = {}
    for phase in required_phases:
        commit = str(phases.get(phase) or "")
        if not re.fullmatch(r"[0-9a-f]{40}", commit):
            raise ValueError(f"C release phase commit is invalid: {phase}")
        _assert_git_ancestor(commit, c_merge, label=f"C release {phase} commit")
        phase_commits[phase] = commit

    if receipt.get("story_parent_atom_source_ref_closure") is not True:
        raise ValueError("C release Story Parent/Atom/source-ref closure failed")
    if receipt.get("fidelity_returned_normally") is not True:
        raise ValueError("C release fidelity did not return normally")
    counters = receipt.get("forbidden_activity_counters")
    if not isinstance(counters, Mapping):
        raise ValueError("C release forbidden activity counters are missing")
    for key in (
        "activation",
        "active_pointer_changes",
        "downloads",
        "milvus_writes",
        "minio_writes",
        "mysql_writes",
        "production_writes",
        "vector_or_embedding_builds",
        "writes_outside_exact_outputs",
    ):
        if counters.get(key) != 0:
            raise ValueError(f"C release forbidden activity counter is nonzero: {key}")

    published = receipt.get("published_artifacts")
    assert isinstance(published, Mapping)
    artifact_paths: dict[str, str] = {}
    for name, jsonl in (
        ("build_manifest", False),
        ("parent_blocks", True),
        ("story_atoms", True),
        ("source_refs", True),
    ):
        identity = published.get(name)
        if not isinstance(identity, Mapping):
            raise ValueError(f"C release published artifact is missing: {name}")
        path = Path(str(identity.get("path") or "")).resolve(strict=True)
        if release_root not in path.parents:
            raise ValueError(f"C release artifact escaped the fixed release root: {name}")
        _validate_file_identity(path, identity, jsonl=jsonl)
        artifact_paths[name] = str(path)
    if Path(artifact_paths["story_atoms"]) != atom_path:
        raise ValueError("C release Story Atom path is inconsistent")

    source_snapshot = receipt.get("source_snapshot_identity")
    if not isinstance(source_snapshot, Mapping):
        raise ValueError("C release source snapshot identity is missing")
    for name, raw in source_snapshot.items():
        if not isinstance(raw, Mapping):
            raise ValueError(f"C source snapshot entry is invalid: {name}")
        source = (PROJECT_ROOT / str(raw.get("relative_path") or "")).resolve(strict=True)
        if PROJECT_ROOT not in source.parents:
            raise ValueError(f"C source snapshot path escaped project root: {name}")
        _validate_file_identity(source, raw, jsonl=True)

    decisions = receipt.get("approved_decisions")
    if not isinstance(decisions, Mapping):
        raise ValueError("C release approved decisions are missing")
    tracked_contracts = {
        "c8b_story_migration_sha256": "docs/superpowers/specs/2026-07-29-rag-thread-c-story-migration-decision.md",
        "c8c_legacy_media_sha256": "docs/superpowers/specs/2026-07-29-rag-thread-c-legacy-media-decision.md",
    }
    for key, relative_path in tracked_contracts.items():
        if _git_blob_sha256(c_merge, relative_path) != decisions.get(key):
            raise ValueError(f"C release approved decision differs from merged contract: {key}")
    closure_plan = "docs/superpowers/plans/2026-07-29-rag-thread-c-closure-gates.md"
    _git("cat-file", "-e", f"{c_merge}:{closure_plan}")

    execution = receipt.get("c8d_execution")
    if not isinstance(execution, Mapping):
        raise ValueError("C8d execution receipt is missing")
    entrypoint = str(execution.get("entrypoint_relative_path") or "")
    if _git_blob_sha256(c_merge, entrypoint) != execution.get("entrypoint_sha256"):
        raise ValueError("C8d entrypoint differs from the merged hash-pinned version")
    output_hashes = {
        str(item.get("sha256"))
        for item in execution.get("output_files", ())
        if isinstance(item, Mapping)
    }
    if receipt.get("fidelity_result_sha256") not in output_hashes:
        raise ValueError("C release fidelity result is not bound to C8d outputs")
    return receipt, atom_path, artifact_paths


def _file_schema_and_rows(path: Path) -> tuple[str, int]:
    if path.suffix == ".jsonl":
        row_count = 0
        schema = ""
        with path.open("r", encoding="utf-8") as handle:
            for row_count, line in enumerate(handle, 1):
                if row_count == 1:
                    first = json.loads(line)
                    schema = str(first.get("schema_version") or first.get("schema") or "")
        return schema, row_count
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError(f"active artifact JSON is not an object: {path.name}")
    records = payload.get("records")
    return str(payload.get("schema_version") or payload.get("schema") or ""), len(records) if isinstance(records, list) else 1


def _active_artifact_receipt(snapshot: object) -> dict[str, object]:
    artifacts: dict[str, dict[str, object]] = {}
    for name in ("manifest_path", "parent_blocks", "child_blocks", "media_assets", "child_bm25", "media_bm25"):
        path = Path(getattr(snapshot, name)).resolve(strict=True)
        schema, rows = _file_schema_and_rows(path)
        artifacts[name] = {
            "path": str(path),
            "row_count": rows,
            "schema_version": schema,
            "sha256": _sha256_file(path),
            "size_bytes": path.stat().st_size,
        }
    return {
        "artifact_schema_version": str(getattr(snapshot, "artifact_schema_version")),
        "artifacts": artifacts,
        "build_root": str(Path(getattr(snapshot, "build_root")).resolve()),
        "build_version": str(getattr(snapshot, "build_version")),
        "capability": str(getattr(snapshot, "capability")),
        "collection_name": str(getattr(snapshot, "collection_name")),
        "manifest_sha256": str(getattr(snapshot, "manifest_sha256")),
        "source_mode": str(getattr(snapshot, "source_mode")),
        "tuple_sha256": str(getattr(snapshot, "tuple_sha256")),
    }


def _gold_targets(cases: Sequence[StorySegmentEvalCase]) -> dict[str, tuple[AtomEvidenceTarget, ...]]:
    return {
        case.query_id: tuple(
            target
            for group in case.required_atom_groups
            for target in group.atoms
        )
        for case in cases
    }


def _load_gold_evidence(
    atom_path: Path,
    gold_by_query: Mapping[str, Sequence[AtomEvidenceTarget]],
) -> dict[str, str]:
    wanted = {
        target.atom_id: target.normalized_evidence_sha256
        for targets in gold_by_query.values()
        for target in targets
    }
    evidence: dict[str, str] = {}
    found: set[str] = set()
    with atom_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            atom_id = str(row.get("child_id") or "")
            expected_hash = wanted.get(atom_id)
            if expected_hash is None:
                continue
            text = canonical_evidence_text(str(row.get("content") or ""))
            if evidence_sha256(text) != expected_hash:
                raise ValueError(f"gold evidence hash changed: {atom_id}")
            previous = evidence.setdefault(expected_hash, text)
            if previous != text:
                raise ValueError("one gold evidence hash maps to different text")
            found.add(atom_id)
    if found != set(wanted):
        raise ValueError("gold evidence text lookup is incomplete")
    return evidence


class _NoOpAssetRegistry:
    def find_for_retrieval(self, *_args: object, **_kwargs: object) -> list[object]:
        return []


class _ForbiddenGenerationLLM:
    def __getattr__(self, name: str) -> object:
        raise AssertionError(f"answer generation is forbidden during baseline capture: {name}")


@contextmanager
def _capture_rrf_rows() -> Iterator[list[list[dict[str, object]]]]:
    import src.rag.retriever as retriever_module

    original = retriever_module.weighted_rrf
    calls: list[list[dict[str, object]]] = []

    def recording_rrf(*args: object, **kwargs: object) -> list[dict[str, Any]]:
        ranked = original(*args, **kwargs)
        calls.append([sanitize_active_result(row) for row in ranked[:80]])
        return ranked

    retriever_module.weighted_rrf = recording_rrf
    try:
        yield calls
    finally:
        retriever_module.weighted_rrf = original


@contextmanager
def _capture_or_replay_dense_rows(
    retriever: object,
    replay_rows: Sequence[Mapping[str, object]] | None,
) -> Iterator[list[dict[str, object]]]:
    original = retriever._dense_rows_for_plan
    captured: list[dict[str, object]] = []

    def dense_rows(query: str, plan: object, candidate_k: int) -> list[dict[str, object]]:
        if replay_rows is None:
            rows = original(query, plan, candidate_k)
            serialized = _jsonable(rows)
            if not isinstance(serialized, list) or not all(isinstance(row, dict) for row in serialized):
                raise ValueError("active dense candidates are not serializable")
            captured.extend(serialized)
            return rows
        restored = _jsonable(replay_rows)
        if not isinstance(restored, list) or not all(isinstance(row, dict) for row in restored):
            raise ValueError("replay dense candidates are invalid")
        captured.extend(restored)
        return [dict(row) for row in restored]

    retriever._dense_rows_for_plan = dense_rows
    try:
        yield captured
    finally:
        retriever._dense_rows_for_plan = original


def _request_plan_receipt(plan: object) -> dict[str, object]:
    payload = _jsonable(plan)
    if not isinstance(payload, dict):
        raise ValueError("active RequestPlan is not serializable")
    return payload


def request_plan_from_receipt(payload: Mapping[str, object]) -> object:
    """Strictly rebuild a v1 RequestPlan without invoking either Planner."""

    from src.rag.query_plan import QueryPlan
    from src.rag.request_plan import PlannedSubtask, RequestPlan, validate_request_plan

    allowed_request = {field.name for field in fields(RequestPlan)}
    if set(payload) != allowed_request:
        raise ValueError("replay RequestPlan fields differ from the active v1 contract")
    raw_subtasks = payload.get("subtasks")
    if not isinstance(raw_subtasks, list):
        raise ValueError("replay RequestPlan subtasks must be an array")
    subtasks: list[PlannedSubtask] = []
    allowed_subtask = {field.name for field in fields(PlannedSubtask)}
    allowed_query = {field.name for field in fields(QueryPlan)}
    tuple_query_fields = {
        "aliases",
        "section_hints",
        "scatter_terms",
        "target_levels",
        "secondary_intents",
    }
    for raw_subtask in raw_subtasks:
        if not isinstance(raw_subtask, Mapping) or set(raw_subtask) != allowed_subtask:
            raise ValueError("replay PlannedSubtask fields differ from the active v1 contract")
        raw_query_plan = raw_subtask.get("query_plan")
        query_plan = None
        if raw_query_plan is not None:
            if not isinstance(raw_query_plan, Mapping) or set(raw_query_plan) != allowed_query:
                raise ValueError("replay QueryPlan fields differ from the active v1 contract")
            query_values = dict(raw_query_plan)
            for name in tuple_query_fields:
                value = query_values.get(name)
                if not isinstance(value, list):
                    raise ValueError(f"replay QueryPlan {name} must be an array")
                query_values[name] = tuple(str(item) for item in value)
            route_options = query_values.get("route_options")
            if not isinstance(route_options, Mapping):
                raise ValueError("replay QueryPlan route_options must be an object")
            query_values["route_options"] = dict(route_options)
            query_plan = QueryPlan(**query_values)
        depends_on = raw_subtask.get("depends_on")
        if not isinstance(depends_on, list):
            raise ValueError("replay PlannedSubtask depends_on must be an array")
        subtasks.append(
            PlannedSubtask(
                subtask_id=str(raw_subtask["subtask_id"]),
                order=int(raw_subtask["order"]),
                task_type=str(raw_subtask["task_type"]),  # type: ignore[arg-type]
                query=str(raw_subtask["query"]),
                query_plan=query_plan,
                depends_on=tuple(str(item) for item in depends_on),
            )
        )
    plan = RequestPlan(
        original_query=str(payload["original_query"]),
        subtasks=tuple(subtasks),
        aggregation_mode=str(payload["aggregation_mode"]),  # type: ignore[arg-type]
        planning_status=str(payload["planning_status"]),
        planning_warning=str(payload["planning_warning"]),
        planning_error=str(payload["planning_error"]),
        schema_version=str(payload["schema_version"]),
    )
    return validate_request_plan(plan)


def _capture_case(
    case: StorySegmentEvalCase,
    *,
    planner: object | None,
    chain: object,
    request_plan: object | None = None,
    replay_case: Mapping[str, object] | None = None,
) -> tuple[dict[str, object], dict[str, list[dict[str, object]]]]:
    if request_plan is None:
        if planner is None:
            raise ValueError("live baseline capture requires a RequestPlanner")
        request_plan = planner.plan(case.query)
    retrieval_at_k: list[dict[str, object]] = []
    final_context: list[dict[str, object]] = []
    subtask_receipts: list[dict[str, object]] = []
    replay_subtasks: dict[str, Mapping[str, object]] = {}
    if replay_case is not None:
        raw_replay_subtasks = replay_case.get("subtasks")
        if not isinstance(raw_replay_subtasks, list):
            raise ValueError("replay baseline subtasks are missing")
        for raw in raw_replay_subtasks:
            if not isinstance(raw, Mapping):
                raise ValueError("replay baseline subtask is invalid")
            subtask_id = str(raw.get("subtask_id") or "")
            if not subtask_id or subtask_id in replay_subtasks:
                raise ValueError("replay baseline subtask IDs are invalid")
            replay_subtasks[subtask_id] = raw
    for subtask in sorted(request_plan.subtasks, key=lambda item: item.order):
        replay_subtask = replay_subtasks.get(subtask.subtask_id)
        raw_dense = replay_subtask.get("dense_candidates") if replay_subtask is not None else None
        if raw_dense is not None and (
            not isinstance(raw_dense, list) or not all(isinstance(row, Mapping) for row in raw_dense)
        ):
            raise ValueError("replay dense candidate cassette is invalid")
        with _capture_or_replay_dense_rows(chain._retriever, raw_dense) as dense_candidates:
            with _capture_rrf_rows() as rrf_calls:
                result = chain.retrieve(
                    subtask.query,
                    _request_plan=request_plan,
                    _subtask=subtask,
                    _allocate_citations=True,
                )
        if replay_subtask is not None and raw_dense is None and subtask.task_type == "knowledge_base":
            raise ValueError("replay knowledge subtask is missing its dense cassette")
        for call in rrf_calls:
            retrieval_at_k.extend(call)
        sources = [
            sanitize_active_result(source)
            for source in result.get("sources", ())
            if isinstance(source, Mapping)
        ]
        context = canonical_evidence_text(str(result.get("context") or ""))
        for source in sources:
            content = canonical_evidence_text(str(source.get("content") or "")).strip()
            if content and content not in context:
                raise ValueError(
                    f"allocated source is absent from final context: {case.query_id}/{subtask.subtask_id}"
                )
        final_context.extend(sources)
        route = result.get("route")
        route_payload = dict(route) if isinstance(route, Mapping) else {}
        subtask_receipts.append(
            {
                "dense_candidates": dense_candidates,
                "final_context_count": len(sources),
                "order": int(subtask.order),
                "query": str(subtask.query),
                "request_plan_subtask": _jsonable(subtask),
                "retrieval_at_k_count": sum(len(call) for call in rrf_calls),
                "retrieval_failed": bool(result.get("retrieval_failed", False)),
                "retrieval_outcome": str(route_payload.get("retrieval_outcome") or "not_applicable"),
                "route": _jsonable(route_payload),
                "subtask_id": str(subtask.subtask_id),
                "task_type": str(subtask.task_type),
            }
        )
    observations = {
        "final_context": final_context,
        "retrieval_at_k": retrieval_at_k,
    }
    receipt = {
        "expected": {
            "answer_scope": _jsonable(case.expected_answer_scope),
            "authorization_origin": case.expected_authorization_origin,
            "retrieval_outcome": case.expected_retrieval_outcome,
            "story_owner_ids": list(case.expected_story_owner_ids),
        },
        "final_context": final_context,
        "query": case.query,
        "query_id": case.query_id,
        "request_plan": _request_plan_receipt(request_plan),
        "retrieval_at_k": retrieval_at_k,
        "stratum": case.stratum,
        "subtasks": subtask_receipts,
    }
    receipt["result_sha256"] = case_result_sha256(receipt)
    return receipt, observations


def _pointer_identity(cfg: object) -> dict[str, object]:
    processed_root = Path(getattr(getattr(cfg, "huiji"), "processed_root")).resolve()
    pointer_path = (processed_root / "active_build.v1.json").resolve(strict=True)
    payload = json.loads(pointer_path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("active pointer is not an object")
    return {
        "path": str(pointer_path),
        "payload": _jsonable(payload),
        "sha256": _sha256_file(pointer_path),
        "size_bytes": pointer_path.stat().st_size,
    }


def _verification_receipt(result: object) -> dict[str, object]:
    return {
        "allowed": bool(getattr(result, "allowed", False)),
        "baseline_sha256": str(getattr(result, "baseline_sha256", "")),
        "evidence_relpath": str(getattr(result, "evidence_relpath", "")),
        "issues": [
            issue.to_public_dict()
            for issue in sorted(getattr(result, "issues", ()))
        ],
        "status": str(getattr(result, "status", "error")),
    }


def _write_canonical_jsonl(path: Path, rows: Sequence[Mapping[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = "".join(_canonical_json(row) + "\n" for row in rows)
    path.write_text(payload, encoding="utf-8", newline="\n")


def _load_replay_request_plans(
    receipt_path: Path,
    cases: Sequence[StorySegmentEvalCase],
) -> tuple[dict[str, object], dict[str, Mapping[str, object]]]:
    receipt_path = receipt_path.resolve(strict=True)
    payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != BASELINE_SCHEMA:
        raise ValueError("replay baseline receipt schema is invalid")
    if receipt_path.read_bytes() != _canonical_bytes(payload):
        raise ValueError("replay baseline receipt is not canonical JSON")
    if payload.get("baseline_identity_sha256") != baseline_business_sha256(payload):
        raise ValueError("replay baseline receipt business identity is invalid")
    if payload.get("main_commit") != _git("rev-parse", "HEAD"):
        raise ValueError("replay baseline receipt belongs to another commit")
    raw_cases = payload.get("cases")
    if not isinstance(raw_cases, list) or len(raw_cases) != len(cases):
        raise ValueError("replay baseline receipt case set differs from frozen gold")
    expected = {case.query_id: case.query for case in cases}
    plans: dict[str, object] = {}
    replay_cases: dict[str, Mapping[str, object]] = {}
    for raw in raw_cases:
        if not isinstance(raw, Mapping):
            raise ValueError("replay baseline case is not an object")
        query_id = str(raw.get("query_id") or "")
        if query_id not in expected or raw.get("query") != expected[query_id] or query_id in plans:
            raise ValueError("replay baseline query identity differs from frozen gold")
        request_plan = raw.get("request_plan")
        if not isinstance(request_plan, Mapping):
            raise ValueError("replay baseline RequestPlan is missing")
        plans[query_id] = request_plan_from_receipt(request_plan)
        replay_cases[query_id] = raw
    if set(plans) != set(expected):
        raise ValueError("replay baseline RequestPlan coverage is incomplete")
    return plans, replay_cases


def _verified_manifest_milvus(cfg: object, pointer: Mapping[str, object]) -> dict[str, object]:
    from src.huiji_rag.active_pointer import resolve_activation_evidence

    processed_root = Path(getattr(getattr(cfg, "huiji"), "processed_root")).resolve()
    raw_pointer = pointer.get("payload")
    if not isinstance(raw_pointer, Mapping):
        raise ValueError("active pointer receipt payload is missing")
    manifest_path, _ = resolve_activation_evidence(processed_root, raw_pointer)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    milvus = manifest.get("milvus") if isinstance(manifest, Mapping) else None
    if not isinstance(milvus, Mapping):
        raise ValueError("active activation manifest Milvus identity is missing")
    return dict(_jsonable(milvus))


def capture_active_baseline(
    *,
    queries_path: Path,
    thresholds_path: Path,
    equivalence_output: Path,
    receipt_output: Path,
    c_release_receipt: Path = DEFAULT_C_RELEASE_RECEIPT,
    reranker_disabled: bool,
    replay_request_plans_from_receipt: Path | None = None,
) -> dict[str, object]:
    if not reranker_disabled:
        raise ValueError("active Story baseline requires --reranker-disabled")

    from config.config import get_config
    from src.huiji_rag.provenance import verify_runtime
    from src.huiji_rag.runtime_artifacts import resolve_runtime_artifact_snapshot
    from src.rag.chain import RAGChain
    from src.rag.request_plan import RequestPlanner
    from src.rag.retriever import Retriever
    from src.rag.vectorstore import load_vectorstore

    c_release, atom_path, c_artifact_paths = validate_c_release_for_baseline(c_release_receipt)
    cases = load_story_segment_eval(queries_path.resolve(strict=True))
    load_story_segment_thresholds(thresholds_path.resolve(strict=True))
    target_count = verify_eval_gold_against_atom_artifact(
        cases,
        atom_path,
        expected_artifact_sha256=GOLD_ARTIFACT_SHA256,
    )
    gold_by_query = _gold_targets(cases)
    evidence_texts = _load_gold_evidence(atom_path, gold_by_query)
    replay_loaded = (
        _load_replay_request_plans(replay_request_plans_from_receipt, cases)
        if replay_request_plans_from_receipt is not None
        else None
    )
    replay_plans = replay_loaded[0] if replay_loaded is not None else None
    replay_cases = replay_loaded[1] if replay_loaded is not None else None

    cfg = get_config()
    if bool(getattr(getattr(cfg, "reranker", None), "enabled", False)):
        raise ValueError("configured reranker must be disabled for the active baseline")
    verification_before = verify_runtime(cfg)
    if not verification_before.allowed:
        raise ValueError("active runtime provenance verification failed")
    snapshot_before = resolve_runtime_artifact_snapshot(cfg)
    active_artifacts = _active_artifact_receipt(snapshot_before)
    pointer_before = _pointer_identity(cfg)
    milvus_identity = _verified_manifest_milvus(cfg, pointer_before)
    vectorstore = load_vectorstore(cfg)
    retriever = Retriever(cfg, vectorstore, artifact_snapshot=snapshot_before)
    if bool(getattr(retriever._reranker, "enabled", False)):
        raise ValueError("runtime reranker is enabled")
    chain = RAGChain(cfg, retriever, asset_registry=_NoOpAssetRegistry())
    chain._llm = _ForbiddenGenerationLLM()
    planner = RequestPlanner(chain._planner_llm, query_planner=chain._query_planner)

    case_receipts: list[dict[str, object]] = []
    observations: dict[str, Mapping[str, Sequence[Mapping[str, object]]]] = {}
    for index, case in enumerate(cases, 1):
        print(f"baseline case {index}/{len(cases)}: {case.query_id}", flush=True)
        case_receipt, observed = _capture_case(
            case,
            planner=planner if replay_plans is None else None,
            chain=chain,
            request_plan=replay_plans.get(case.query_id) if replay_plans is not None else None,
            replay_case=replay_cases.get(case.query_id) if replay_cases is not None else None,
        )
        case_receipts.append(case_receipt)
        observations[case.query_id] = observed

    equivalence_rows = build_equivalence_rows(
        gold_by_query,
        observations,
        evidence_text_by_sha256=evidence_texts,
    )
    _write_canonical_jsonl(equivalence_output, equivalence_rows)
    equivalence_sha = _sha256_file(equivalence_output)

    verification_after = verify_runtime(cfg)
    if not verification_after.allowed:
        raise ValueError("active runtime provenance changed during baseline capture")
    snapshot_after = resolve_runtime_artifact_snapshot(cfg)
    pointer_after = _pointer_identity(cfg)
    if snapshot_after.tuple_sha256 != snapshot_before.tuple_sha256:
        raise ValueError("active artifact tuple changed during baseline capture")
    if pointer_after != pointer_before:
        raise ValueError("active pointer changed during baseline capture")

    captured_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    receipt: dict[str, object] = {
        "active_runtime": {
            "active_pointer": pointer_before,
            "artifacts": active_artifacts,
            "milvus": milvus_identity,
            "verification": _verification_receipt(verification_before),
        },
        "captured_at_utc": captured_at,
        "cases": case_receipts,
        "counters": {
            "case_count": len(cases),
            "equivalence_row_count": len(equivalence_rows),
            "generation_calls": 0,
            "gold_target_count": target_count,
            "reranker_calls": 0,
            "baseline_live_request_planner_invocations": len(cases),
            "baseline_live_dense_embedding_calls": sum(
                1
                for case in case_receipts
                for subtask in case["subtasks"]
                if subtask["task_type"] == "knowledge_base"
            ),
        },
        "c_release": {
            "artifact_paths": c_artifact_paths,
            "c_merge_commit": c_release["c_merge_commit"],
            "path": str(c_release_receipt.resolve()),
            "schema_version": c_release["schema_version"],
            "sha256": _sha256_file(c_release_receipt),
            "story_atom_sha256": GOLD_ARTIFACT_SHA256,
        },
        "equivalence": {
            "logical_path": "eval/story_baseline_atom_equivalence.v1.jsonl",
            "row_count": len(equivalence_rows),
            "sha256": equivalence_sha,
        },
        "execution_contract": {
            "answer_generation_forbidden": True,
            "determinism_method": "one_live_active_plan_and_dense_sample_then_hash_pinned_replay",
            "final_answer_used_as_evidence": False,
            "planner_then_retrieve_only": True,
            "reranker_disabled": True,
            "retrieval_at_k": 80,
        },
        "inputs": {
            "capture_code_sha256": _sha256_file(Path(__file__).resolve()),
            "matcher_code_sha256": _sha256_file(Path(__file__).resolve().parents[1] / "src/rag_eval/story_segment_baseline.py"),
            "normalization": "NFC+CRLF_or_CR_to_LF",
            "queries_path": "eval/story_segment_eval.v1.jsonl",
            "queries_sha256": _sha256_file(queries_path),
            "thresholds_path": "eval/story_segment_thresholds.v1.json",
            "thresholds_sha256": _sha256_file(thresholds_path),
        },
        "main_commit": str(_git("rev-parse", "HEAD")),
        "models": {
            "embedding_model": str(cfg.embedding.model),
            "embedding_provider": str(cfg.embedding.provider),
            "llm_model": str(cfg.llm.model),
            "llm_provider": str(cfg.llm.provider),
            "llm_thinking": str(cfg.llm.thinking),
        },
        "retrieval_config": {
            "bm25_k": int(cfg.retrieval.bm25_k),
            "candidate_k_max": int(cfg.retrieval.candidate_k_max),
            "candidate_oversample": int(cfg.retrieval.candidate_oversample),
            "context_budget_chars": int(cfg.retrieval.context_budget_chars),
            "dense_k": int(cfg.retrieval.dense_k),
            "rag_top_k": int(cfg.rag.top_k),
            "rerank_k": int(cfg.retrieval.rerank_k),
            "reranker_enabled": bool(cfg.reranker.enabled),
            "reranker_model": str(cfg.reranker.model),
            "sibling_window": int(cfg.retrieval.sibling_window),
            "voice_page_size": int(cfg.retrieval.voice_page_size),
            "voice_page_size_max": int(cfg.retrieval.voice_page_size_max),
        },
        "run_id": f"story-baseline-{uuid4().hex}",
        "schema_version": BASELINE_SCHEMA,
    }
    receipt["baseline_identity_sha256"] = baseline_business_sha256(receipt)
    receipt_output.parent.mkdir(parents=True, exist_ok=True)
    receipt_output.write_bytes(_canonical_bytes(receipt))
    return receipt


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--freeze-gold-from-c-release", type=Path)
    parser.add_argument("--gold-output", type=Path, default=Path("eval/story_segment_eval.v1.jsonl"))
    parser.add_argument("--queries", type=Path)
    parser.add_argument("--thresholds", type=Path)
    parser.add_argument("--equivalence-output", type=Path)
    parser.add_argument("--receipt-output", type=Path)
    parser.add_argument("--c-release-receipt", type=Path, default=DEFAULT_C_RELEASE_RECEIPT)
    parser.add_argument("--replay-request-plans-from-receipt", type=Path)
    parser.add_argument("--reranker-disabled", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.freeze_gold_from_c_release is not None:
        freeze_gold(args.freeze_gold_from_c_release, args.gold_output)
        return 0
    required = {
        "--queries": args.queries,
        "--thresholds": args.thresholds,
        "--equivalence-output": args.equivalence_output,
        "--receipt-output": args.receipt_output,
    }
    missing = [name for name, value in required.items() if value is None]
    if missing:
        raise SystemExit(f"active baseline capture requires: {', '.join(missing)}")
    capture_active_baseline(
        queries_path=args.queries,
        thresholds_path=args.thresholds,
        equivalence_output=args.equivalence_output,
        receipt_output=args.receipt_output,
        c_release_receipt=args.c_release_receipt,
        reranker_disabled=args.reranker_disabled,
        replay_request_plans_from_receipt=args.replay_request_plans_from_receipt,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
