from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Iterable

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.config import get_config
from src.rag.chain import RAGChain
from src.rag.retriever import Retriever
from src.rag.vectorstore import load_vectorstore


LOCAL_PATH_MARKERS = ("D:\\", "C:\\", "file://", "..\\")
RANKING_DEBUG_KEYS = (
    "bm25_rank",
    "dense_rank",
    "structured_rank",
    "reranker_score",
    "exact_entity_bonus",
    "intent_section_bonus",
    "profile_section_bonus",
    "non_character_profile_penalty",
    "profile_skill_penalty",
    "youtium_penalty",
)


def compute_recall(actual: Iterable[str], expected: Iterable[str]) -> float:
    expected_set = {str(item) for item in expected if str(item)}
    if not expected_set:
        return 1.0
    actual_set = {str(item) for item in actual if str(item)}
    return len(actual_set & expected_set) / len(expected_set)


def iter_eval_rows(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            stripped = line.strip()
            if stripped:
                yield json.loads(stripped)


def _model_to_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "__dict__"):
        return dict(value.__dict__)
    return {}


def _contains_local_path(value: Any) -> bool:
    if isinstance(value, str):
        return any(marker in value for marker in LOCAL_PATH_MARKERS)
    if isinstance(value, dict):
        return any(_contains_local_path(item) for item in value.values())
    if isinstance(value, list | tuple):
        return any(_contains_local_path(item) for item in value)
    return False


def _ranking_debug(source: dict[str, Any]) -> dict[str, Any]:
    debug = source.get("debug") if isinstance(source.get("debug"), dict) else {}
    out: dict[str, Any] = {}
    for key, value in debug.items():
        if key in RANKING_DEBUG_KEYS or key.startswith(("quality_", "rrf_", "section_", "keyword_", "vector_", "entity_")):
            if isinstance(value, (int, float, str, bool)):
                out[key] = value
    return out


def _route_entity(result: dict[str, Any]) -> str:
    route = result.get("route") or {}
    plan = _model_to_dict(result.get("plan"))
    return str(route.get("entity") or plan.get("entity") or "")


def _route_intent(result: dict[str, Any]) -> str:
    route = result.get("route") or {}
    plan = _model_to_dict(result.get("plan"))
    return str(route.get("intent") or plan.get("intent") or "")


def _plan_field(result: dict[str, Any], key: str) -> str:
    plan = _model_to_dict(result.get("plan"))
    return str(plan.get(key) or "")


def _source_sections(sources: list[dict[str, Any]]) -> set[str]:
    sections: set[str] = set()
    for source in sources:
        for field in ("section_kind", "parent_id", "heading_path", "retrieval_stage"):
            value = str(source.get(field) or "").lower()
            if value:
                sections.add(value)
    return sections


def _media_type(item: dict[str, Any]) -> str:
    asset_type = str(item.get("asset_type") or item.get("role") or "").lower()
    mime = str(item.get("mime") or "").lower()
    if asset_type in {"voice", "audio"} or mime.startswith("audio/"):
        return "voice"
    if asset_type == "video" or mime.startswith("video/"):
        return "video"
    if mime.startswith("image/") or asset_type in {"portrait", "skill", "skin", "image", "media"}:
        return "image"
    return asset_type


def _has_required_section(sections: set[str], required: str) -> bool:
    needle = required.lower()
    return any(needle in section for section in sections)


def evaluate_result(row: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    sources = list(result.get("sources") or [])
    media = list(result.get("media") or result.get("assets") or [])
    route_entity = _route_entity(result)
    route_intent = _route_intent(result)
    media_types = [_media_type(item) for item in media]
    section_values = _source_sections(sources)
    violations: list[str] = []

    expected_entity = str(row.get("expected_entity") or "")
    if expected_entity and route_entity and route_entity != expected_entity:
        violations.append("wrong_entity")
    elif expected_entity and not route_entity:
        source_names = {str(source.get("name") or "") for source in sources}
        if expected_entity not in source_names:
            violations.append("wrong_entity")

    expected_intent = str(row.get("expected_intent") or "")
    if expected_intent and route_intent and route_intent != expected_intent:
        violations.append("wrong_intent")
    elif expected_intent and not route_intent:
        violations.append("wrong_intent")

    for section in row.get("required_sections", []) or []:
        if not _has_required_section(section_values, str(section)):
            violations.append("missing_required_section")
            break

    for media_type in row.get("required_media_types", []) or []:
        if str(media_type) not in media_types:
            violations.append("missing_required_media")
            break

    forbidden_media = {str(item) for item in row.get("forbid_media_types", []) or []}
    if forbidden_media & set(media_types):
        violations.append("forbidden_media_type")

    if _contains_local_path(result):
        violations.append("local_path_leak")

    if route_intent != "voice" and "voice" in media_types:
        violations.append("voice_auto_leak")

    if not sources and not row.get("allow_no_entity") and not result.get("failure_actions"):
        violations.append("no_sources_without_failure_actions")

    return {
        "id": row.get("id", row.get("query", "")),
        "query": row.get("query", ""),
        "planning_status": result.get("planning_status", ""),
        "planning_warning": result.get("planning_warning", ""),
        "planning_error": result.get("planning_error", ""),
        "entity": route_entity,
        "intent": route_intent,
        "dense_query": _plan_field(result, "dense_query"),
        "sparse_query": _plan_field(result, "sparse_query"),
        "top_sources": [
            {
                "name": source.get("name", ""),
                "source": source.get("source", ""),
                "child_id": source.get("child_id", ""),
                "parent_id": source.get("parent_id", ""),
                "section_kind": source.get("section_kind", ""),
                "score": source.get("score", 0),
                "ranking_debug": _ranking_debug(source),
            }
            for source in sources[:5]
        ],
        "media_count": len(media),
        "media_types": media_types,
        "omitted_actions": result.get("omitted_actions", []),
        "failure_actions": result.get("failure_actions", []),
        "violations": violations,
        "passed": not violations,
    }


def _rate(count: int, total: int) -> float:
    return float(count / total) if total else 0.0


def summarize_evaluations(
    evaluated_rows: list[dict[str, Any]],
    thresholds: dict[str, dict[str, float]] | None = None,
    runtime_options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    total = len(evaluated_rows)
    passed_count = sum(1 for item in evaluated_rows if item.get("passed"))
    failed = [item for item in evaluated_rows if not item.get("passed")]

    def count_violation(name: str) -> int:
        return sum(1 for item in evaluated_rows if name in set(item.get("violations") or []))

    metrics = {
        "pass_rate": _rate(passed_count, total),
        "entity_accuracy": 1.0 - _rate(count_violation("wrong_entity"), total),
        "intent_accuracy": 1.0 - _rate(count_violation("wrong_intent"), total),
        "local_path_leak_rate": _rate(count_violation("local_path_leak"), total),
        "voice_auto_leak_rate": _rate(count_violation("voice_auto_leak"), total),
    }
    threshold_violations: list[str] = []
    for metric, rule in (thresholds or {}).items():
        if metric not in metrics:
            continue
        value = float(metrics[metric])
        if "min" in rule and value < float(rule["min"]):
            threshold_violations.append(f"{metric} below min {rule['min']}: {value}")
        if "max" in rule and value > float(rule["max"]):
            threshold_violations.append(f"{metric} above max {rule['max']}: {value}")

    return {
        "id": "summary",
        "query_count": total,
        "passed_count": passed_count,
        "failed_count": len(failed),
        "metrics": metrics,
        "threshold_violations": threshold_violations,
        "failed_cases": [
            {
                "id": item.get("id", ""),
                "violations": list(item.get("violations") or []),
            }
            for item in failed
        ],
        "runtime_options": runtime_options or {},
    }


def load_thresholds(path: Path | None) -> dict[str, dict[str, float]]:
    if path is None:
        return {}
    if not path.exists():
        raise FileNotFoundError(f"thresholds file not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("thresholds file must contain a JSON object")
    return data


def apply_runtime_overrides(cfg: Any, reranker_enabled: bool | None = None) -> None:
    if reranker_enabled is not None and hasattr(cfg, "reranker"):
        cfg.reranker.enabled = bool(reranker_enabled)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate Huiji RAG retrieval behavior.")
    parser.add_argument("--queries", default="eval/queries_core.jsonl")
    parser.add_argument("--output", default="eval/latest_report.jsonl")
    parser.add_argument("--thresholds", default="", help="Optional JSON threshold file.")
    reranker_group = parser.add_mutually_exclusive_group()
    reranker_group.add_argument("--reranker-enabled", action="store_true", help="Enable reranker for this eval run only.")
    reranker_group.add_argument("--reranker-disabled", action="store_true", help="Disable reranker for this eval run only.")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    query_path = Path(args.queries)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    thresholds = load_thresholds(Path(args.thresholds)) if args.thresholds else {}

    cfg = get_config()
    reranker_override: bool | None = None
    if args.reranker_enabled:
        reranker_override = True
    elif args.reranker_disabled:
        reranker_override = False
    apply_runtime_overrides(cfg, reranker_enabled=reranker_override)
    chain = RAGChain(cfg, Retriever(cfg, load_vectorstore(cfg)))
    rows = list(iter_eval_rows(query_path))

    evaluated_rows: list[dict[str, Any]] = []
    with output_path.open("w", encoding="utf-8") as fh:
        for row in rows:
            result = chain.retrieve(row["query"])
            evaluated = evaluate_result(row, result)
            evaluated_rows.append(evaluated)
            line = json.dumps(evaluated, ensure_ascii=False)
            fh.write(line + "\n")
            print(line)

        summary = summarize_evaluations(
            evaluated_rows,
            thresholds=thresholds,
            runtime_options={
                "reranker_enabled": bool(getattr(getattr(cfg, "reranker", None), "enabled", False)),
                "thresholds": str(Path(args.thresholds)) if args.thresholds else "",
            },
        )
        line = json.dumps(summary, ensure_ascii=False)
        fh.write(line + "\n")
        print(line)
    if summary["threshold_violations"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
