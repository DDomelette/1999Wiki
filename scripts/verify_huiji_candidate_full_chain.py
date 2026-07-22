"""Run isolated retrieval acceptance against one hash-pinned candidate tuple."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.config import get_config
from src.assets.huiji_registry import HuijiMediaRegistry
from src.huiji_rag.io import iter_jsonl
from src.huiji_rag.provenance import (
    safe_relative_path,
    sha256_file,
    verify_runtime,
    write_hash_pinned_json,
)
from src.huiji_rag.runtime_artifacts import (
    RuntimeArtifactSnapshot,
    resolve_isolated_candidate_snapshot,
    resolve_runtime_artifact_snapshot,
)
from src.rag.citations import build_source_map
from src.rag.query_plan import QueryPlan
from src.rag.retriever import Retriever
from src.rag.vectorstore import MilvusVectorstore


_SHA256_CHARS = frozenset("0123456789abcdef")
_CASE_SPECS = (
    ("multi_skill_voice", ("skill", "voice"), ("skill", "voice"), "audio"),
    ("collection", ("collection",), ("item",), "image"),
    ("culture_dossier", ("culture_dossier",), ("culture",), "none"),
    ("udimo", ("udimo",), ("udimo",), "image"),
    ("skill", ("skill",), ("skill",), "image"),
    ("voice", ("voice",), ("voice",), "audio"),
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify one isolated Huiji candidate tuple")
    parser.add_argument("--build-root", type=Path, required=True)
    parser.add_argument("--expected-build-manifest-sha256", required=True)
    parser.add_argument("--shadow-collection", required=True)
    parser.add_argument("--shadow-evidence", type=Path, required=True)
    parser.add_argument("--expected-shadow-evidence-sha256", required=True)
    parser.add_argument("--protected-compare", type=Path, required=True)
    parser.add_argument("--expected-protected-compare-sha256", required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    return parser


def _require_sha256(value: str, label: str) -> str:
    digest = str(value or "").strip().lower()
    if len(digest) != 64 or any(char not in _SHA256_CHARS for char in digest):
        raise ValueError(f"{label} SHA-256 is invalid")
    return digest


def _load_pinned_json(path: Path, expected_sha256: str, label: str) -> dict[str, Any]:
    target = Path(path).resolve()
    expected = _require_sha256(expected_sha256, label)
    if not target.is_file() or sha256_file(target) != expected:
        raise ValueError(f"{label} SHA-256 mismatch")
    payload = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{label} is not a JSON object")
    return payload


def _owner_key(row: Mapping[str, object]) -> tuple[str, str, str]:
    entity_type = str(row.get("entity_type") or "")
    entity_id = str(row.get("entity_id") or "")
    scoped_owner = str(row.get("owner_entity_id") or "")
    if scoped_owner and ":" in scoped_owner:
        scoped_type, scoped_id = scoped_owner.split(":", 1)
        entity_type = entity_type or scoped_type
        entity_id = entity_id or scoped_id
    return (
        entity_type,
        entity_id,
        str(row.get("entity_name") or ""),
    )


def select_case_owners(
    child_rows: Iterable[Mapping[str, object]],
    media_rows: Iterable[Mapping[str, object]],
) -> dict[str, tuple[str, str, str]]:
    sections: dict[tuple[str, str, str], Counter[str]] = defaultdict(Counter)
    for row in child_rows:
        owner = _owner_key(row)
        if all(owner):
            sections[owner][str(row.get("section_kind") or "")] += 1
    media_roles: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    for row in media_rows:
        owner = _owner_key(row)
        if all(owner) and bool(row.get("is_available")):
            media_roles[owner].add(str(row.get("media_role") or ""))

    selected: dict[str, tuple[str, str, str]] = {}
    for label, required_sections, _intents, _media_intent in _CASE_SPECS:
        candidates = []
        for owner, counts in sections.items():
            if any(counts[section] <= 0 for section in required_sections):
                continue
            if "voice" in required_sections and counts["voice"] < 8:
                continue
            roles = media_roles.get(owner, set())
            if label in {"skill", "multi_skill_voice"} and "skill" not in roles:
                continue
            if label in {"voice", "multi_skill_voice"} and "voice" not in roles:
                continue
            if label == "collection" and "collection_item" not in roles:
                continue
            if label == "udimo" and "udimo" not in roles:
                continue
            candidates.append(owner)
        if not candidates:
            raise ValueError(f"candidate inventory lacks dynamic sample: {label}")
        selected[label] = min(
            candidates,
            key=lambda owner: hashlib.sha256(
                f"{owner[0]}:{owner[1]}".encode("utf-8")
            ).hexdigest(),
        )
    return selected


def _plan(
    owner: tuple[str, str, str],
    intents: tuple[str, ...],
    media_intent: str,
) -> QueryPlan:
    entity_type, entity_id, entity_name = owner
    query = f"{entity_name} {' '.join(intents)}"
    return QueryPlan(
        original_query=query,
        normalized_query=query,
        entity=entity_name,
        aliases=(),
        intent=intents[0],
        section_hints=(),
        scatter_terms=(),
        confidence=1.0,
        media_intent=media_intent,
        entity_type=entity_type,
        entity_id=entity_id,
        resolution_mode="exact_id",
        dense_query=query,
        sparse_query=query,
        secondary_intents=intents[1:],
        planning_status="fallback_no_llm",
    )


def validate_voice_pages(
    registry: HuijiMediaRegistry,
    first_page: Mapping[str, object],
) -> dict[str, object]:
    pages: list[Mapping[str, object]] = [first_page]
    seen_cursors: set[str] = set()
    while bool(pages[-1].get("has_more")):
        cursor = str(pages[-1].get("next_cursor") or "")
        if not cursor or cursor in seen_cursors or len(pages) >= 1000:
            raise ValueError("voice pagination cursor is invalid")
        seen_cursors.add(cursor)
        pages.append(registry.get_voice_page(cursor))

    line_ids: list[str] = []
    binding_ids: list[str] = []
    languages: set[str] = set()
    for page in pages:
        lines = page.get("lines")
        if not isinstance(lines, list) or len(lines) > int(page.get("page_size") or 0):
            raise ValueError("voice page geometry is invalid")
        for line in lines:
            if not isinstance(line, Mapping):
                raise ValueError("voice line is invalid")
            line_id = str(line.get("voice_line_id") or "")
            variants = line.get("variants")
            if not line_id or not isinstance(variants, list) or not variants:
                raise ValueError("voice line variants are invalid")
            line_ids.append(line_id)
            line_languages: set[str] = set()
            for variant in variants:
                if not isinstance(variant, Mapping):
                    raise ValueError("voice variant is invalid")
                binding_id = str(variant.get("binding_id") or variant.get("asset_id") or "")
                language = str(variant.get("language") or "")
                if not binding_id or not language or language in line_languages:
                    raise ValueError("voice language variants are not unique")
                binding_ids.append(binding_id)
                line_languages.add(language)
                languages.add(language)
    if len(line_ids) != len(set(line_ids)) or len(binding_ids) != len(set(binding_ids)):
        raise ValueError("voice pagination repeats lines or bindings")
    total_lines = int(first_page.get("total_lines") or 0)
    if len(line_ids) != total_lines:
        raise ValueError("voice pagination total differs from traversed lines")
    return {
        "page_count": len(pages),
        "line_count": len(line_ids),
        "binding_count": len(binding_ids),
        "language_count": len(languages),
    }


def _run_case(
    label: str,
    owner: tuple[str, str, str],
    intents: tuple[str, ...],
    media_intent: str,
    *,
    retriever: Retriever,
    registry: HuijiMediaRegistry,
    top_k: int,
    voice_page_size: int,
) -> dict[str, object]:
    plan = _plan(owner, intents, media_intent)
    sources = retriever.search(plan.original_query, k=top_k, query_plan=plan)
    if not sources:
        raise ValueError(f"isolated retrieval returned no sources: {label}")
    if any(
        str(row.get("entity_type") or "") != owner[0]
        or str(row.get("entity_id") or "") != owner[1]
        for row in sources
    ):
        raise ValueError(f"isolated retrieval crossed owner boundary: {label}")
    debug = dict(retriever.last_route_debug)
    requested = tuple(str(value) for value in debug.get("requested_intents", ()))
    if requested != intents:
        raise ValueError(f"isolated retrieval intent tuple mismatch: {label}")
    shortfall = dict(debug.get("coverage_shortfall") or {})
    if any(int(shortfall.get(intent, 1)) != 0 for intent in intents):
        raise ValueError(f"isolated retrieval coverage shortfall: {label}")
    candidates = dict(debug.get("intent_candidates") or {})
    if any(int(candidates.get(intent, 0)) <= 0 for intent in intents):
        raise ValueError(f"isolated retrieval lacks pre-budget candidates: {label}")

    cited_sources, refs = build_source_map(sources)
    expected_citations = [f"S{index:02d}" for index in range(1, len(refs) + 1)]
    if [ref.citation_id for ref in refs] != expected_citations:
        raise ValueError(f"citation sequence mismatch: {label}")
    if any(
        ref.entity_type != owner[0]
        or ref.entity_id != owner[1]
        or not ref.child_id
        for ref in refs
    ):
        raise ValueError(f"citation identity mismatch: {label}")
    if [str(row.get("citation_id") or "") for row in cited_sources] != expected_citations:
        raise ValueError(f"citation source map mismatch: {label}")

    bundle = registry.find_bundle_for_retrieval(
        plan,
        sources,
        limit=50,
        voice_page_size=voice_page_size,
    )
    roles = Counter(str(item.get("media_role") or "") for item in bundle.items)
    if label == "collection" and roles["collection_item"] <= 0:
        raise ValueError("collection media binding was not retained")
    if label == "udimo" and roles["udimo"] <= 0:
        raise ValueError("udimo media binding was not retained")
    if label == "skill" and roles["skill"] <= 0:
        raise ValueError("skill media binding was not retained")
    voice = None
    if "voice" in intents:
        if not bundle.panels:
            raise ValueError(f"voice panel is missing: {label}")
        voice = validate_voice_pages(registry, bundle.panels[0])
    return {
        "label": label,
        "owner_sha256": hashlib.sha256(
            f"{owner[0]}:{owner[1]}".encode("utf-8")
        ).hexdigest(),
        "requested_intents": list(intents),
        "source_count": len(sources),
        "source_sections": sorted({str(row.get("section_kind") or "") for row in sources}),
        "intent_candidates": {key: int(value) for key, value in sorted(candidates.items())},
        "intent_retained": {
            key: int(value)
            for key, value in sorted(dict(debug.get("intent_retained") or {}).items())
        },
        "citation_count": len(refs),
        "media_role_counts": dict(sorted(roles.items())),
        "voice": voice,
    }


def _global_media_checks(
    registry: HuijiMediaRegistry,
    media_rows: Sequence[Mapping[str, object]],
    child_rows: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    resources: dict[str, set[str]] = defaultdict(set)
    owner_roles: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    collection_sources: dict[tuple[str, str, str], Mapping[str, object]] = {}
    for row in media_rows:
        resources[str(row.get("resource_id") or "")].add(str(row.get("binding_id") or ""))
        owner_roles[_owner_key(row)].add(str(row.get("media_role") or ""))
    for row in child_rows:
        if str(row.get("section_kind") or "") == "collection":
            collection_sources.setdefault(_owner_key(row), row)
    shared = [values for values in resources.values() if len(values) > 1]
    if not shared or any("" in values for values in shared):
        raise ValueError("shared resource binding identity is invalid")

    negative_candidates = sorted(
        owner
        for owner, roles in owner_roles.items()
        if "collection_item" in roles
        and "udimo" not in roles
        and owner in collection_sources
        and all(owner)
    )
    if not negative_candidates:
        raise ValueError("candidate lacks missing-role negative sample")
    owner = negative_candidates[0]
    source = collection_sources[owner]
    negative_plan = _plan(owner, ("udimo",), "image")
    negative_bundle = registry.find_bundle_for_retrieval(
        negative_plan,
        [
            {
                "entity_type": owner[0],
                "entity_id": owner[1],
                "name": owner[2],
                "child_id": str(source.get("child_id") or ""),
                "parent_id": str(source.get("parent_id") or ""),
            }
        ],
        limit=50,
    )
    if negative_bundle.items or negative_bundle.panels:
        raise ValueError("missing udimo role fell back to unrelated media")
    return {
        "shared_resource_group_count": len(shared),
        "shared_binding_count": sum(len(values) for values in shared),
        "missing_role_fallback_blocked": True,
    }


def _runtime_projection(value: object) -> dict[str, object]:
    return {
        "status": str(getattr(value, "status", "")),
        "issues": [item.to_public_dict() for item in getattr(value, "issues", ())],
        "baseline_sha256": str(getattr(value, "baseline_sha256", "")),
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    cfg = get_config()
    project_root = Path(cfg.paths.project_root).resolve()
    run_dir = Path(args.run_dir).resolve()
    evidence_path = run_dir / "full-chain.v1.json"
    status = "error"
    failure_code = "candidate_full_chain_error"
    payload: dict[str, object] = {}
    try:
        safe_relative_path(evidence_path, project_root)
        if run_dir.exists():
            raise FileExistsError("full-chain run directory already exists")
        shadow_evidence = _load_pinned_json(
            args.shadow_evidence,
            args.expected_shadow_evidence_sha256,
            "shadow evidence",
        )
        protected = _load_pinned_json(
            args.protected_compare,
            args.expected_protected_compare_sha256,
            "protected compare",
        )
        shadow = str(args.shadow_collection or "").strip()
        if (
            shadow_evidence.get("status") != "pass"
            or shadow_evidence.get("collection") != shadow
            or protected.get("status") != "pass"
            or dict(protected.get("allowed_shadow_addition") or {}).get("collection") != shadow
        ):
            raise ValueError("shadow acceptance evidence does not authorize this tuple")

        active_before = resolve_runtime_artifact_snapshot(cfg)
        runtime_before = verify_runtime(cfg)
        if not runtime_before.allowed:
            raise ValueError("active runtime is not healthy before isolated acceptance")
        candidate = resolve_isolated_candidate_snapshot(
            cfg,
            args.build_root,
            expected_manifest_sha256=args.expected_build_manifest_sha256,
            collection_name=shadow,
            active_snapshot=active_before,
        )
        if shadow_evidence.get("candidate_build_version") != candidate.build_version:
            raise ValueError("shadow evidence build version differs from candidate")
        post_fp = shadow_evidence.get("post_fingerprint")
        if not isinstance(post_fp, Mapping) or int(post_fp.get("row_count") or -1) <= 0:
            raise ValueError("shadow evidence fingerprint is invalid")

        child_rows = [dict(row) for row in iter_jsonl(candidate.child_blocks)]
        media_rows = [dict(row) for row in iter_jsonl(candidate.media_assets)]
        if int(post_fp.get("row_count") or -1) != len(child_rows):
            raise ValueError("shadow row count differs from candidate child count")
        selected = select_case_owners(child_rows, media_rows)

        isolated_cfg = copy.deepcopy(cfg)
        isolated_cfg.vectorstore.collection_name = shadow
        vectorstore = MilvusVectorstore(isolated_cfg)
        retriever = Retriever(isolated_cfg, vectorstore, artifact_snapshot=candidate)
        registry = HuijiMediaRegistry(isolated_cfg, artifact_snapshot=candidate)
        top_k = max(20, int(getattr(isolated_cfg.retrieval, "max_sources", 20)))
        voice_page_size = int(getattr(isolated_cfg.retrieval, "voice_page_size", 8))
        cases = []
        for label, _sections, intents, media_intent in _CASE_SPECS:
            cases.append(
                _run_case(
                    label,
                    selected[label],
                    intents,
                    media_intent,
                    retriever=retriever,
                    registry=registry,
                    top_k=top_k,
                    voice_page_size=voice_page_size,
                )
            )
        global_checks = _global_media_checks(registry, media_rows, child_rows)

        runtime_after = verify_runtime(cfg)
        active_after = resolve_runtime_artifact_snapshot(cfg)
        if _runtime_projection(runtime_before) != _runtime_projection(runtime_after):
            raise ValueError("active runtime verifier changed during isolated acceptance")
        if (
            active_before.tuple_sha256 != active_after.tuple_sha256
            or active_before.collection_name != active_after.collection_name
            or active_after.collection_name == shadow
        ):
            raise ValueError("production runtime tuple changed during isolated acceptance")
        status = "pass"
        failure_code = ""
        payload = {
            "candidate": {
                "build_version": candidate.build_version,
                "build_manifest_sha256": candidate.manifest_sha256,
                "tuple_sha256": candidate.tuple_sha256,
                "collection": candidate.collection_name,
                "child_count": len(child_rows),
                "media_binding_count": len(media_rows),
            },
            "active_before": {
                "build_version": active_before.build_version,
                "tuple_sha256": active_before.tuple_sha256,
                "collection": active_before.collection_name,
            },
            "active_after": {
                "build_version": active_after.build_version,
                "tuple_sha256": active_after.tuple_sha256,
                "collection": active_after.collection_name,
            },
            "runtime_verifier": _runtime_projection(runtime_after),
            "cases": cases,
            "global_media_checks": global_checks,
            "shadow_evidence": {
                "path": safe_relative_path(args.shadow_evidence, project_root),
                "sha256": _require_sha256(
                    args.expected_shadow_evidence_sha256, "shadow evidence"
                ),
            },
            "protected_compare": {
                "path": safe_relative_path(args.protected_compare, project_root),
                "sha256": _require_sha256(
                    args.expected_protected_compare_sha256, "protected compare"
                ),
            },
        }
    except FileExistsError:
        failure_code = "full_chain_evidence_exists"
        status = "blocked"
    except ValueError as error:
        failure_code = str(error).split(":", 1)[0].replace(" ", "_")[:120]
        status = "blocked"
    except Exception:
        failure_code = "candidate_full_chain_error"
        status = "error"

    evidence = {
        "schema_version": "huiji.candidate-full-chain/v1",
        "status": status,
        "failure_code": failure_code,
        **payload,
    }
    try:
        write_hash_pinned_json(evidence_path, evidence)
        print(
            f"status={status} failure={failure_code or 'none'} "
            f"evidence={safe_relative_path(evidence_path, project_root)}"
        )
    except Exception as error:
        print(f"status=error error_type={type(error).__name__}", file=sys.stderr)
        return 3
    return 0 if status == "pass" else 2 if status == "blocked" else 3


if __name__ == "__main__":
    raise SystemExit(main())
