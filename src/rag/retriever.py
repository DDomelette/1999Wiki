"""Retrieval orchestration for Huiji v3 child blocks."""
from __future__ import annotations

from typing import Any, Iterable

from langchain_core.documents import Document

from src.huiji_rag.io import iter_jsonl
from src.huiji_rag.runtime_artifacts import (
    RuntimeArtifactSnapshot,
    resolve_runtime_artifact_snapshot,
)
from src.rag.contracts import EntityRef
from src.rag.hybrid import weighted_rrf
from src.rag.layered_expansion import expand_ranked_children, make_omitted_actions
from src.rag.packet_policy import IntentPolicyBundle, PacketPolicy, compose_packet_policies
from src.rag.ownership import (
    OwnershipDiagnostics,
    assert_packet_ownership,
    filter_owned_rows,
    validate_target_parent,
)
from src.rag.query_plan import INTENT_SECTION_HINTS, QueryPlan, requested_intents
from src.rag.retrieval_budget import (
    allocate_sources,
    calculate_candidate_k,
    calculate_required_source_count,
    clamp_voice_page_size,
)
from src.rag.reranker import OptionalBgeReranker
from src.rag.sparse import LocalBM25SparseIndex
from src.rag.tracing import NullTrace, RequestTrace


_ENTITY_FREE_INTENTS = frozenset({"general"})
_HUJI_RETRIEVAL_STAGES = (
    "retrieval.structured",
    "retrieval.bm25",
    "retrieval.dense",
    "retrieval.fusion",
    "retrieval.rerank",
    "retrieval.expand",
    "retrieval.allocate",
)


class RetrievalExecutionError(RuntimeError):
    """Structured dependency failure that cannot be treated as an empty result."""

    def __init__(self, stage: str, error_class: str) -> None:
        self.stage = str(stage)
        self.error_class = str(error_class)
        super().__init__(f"{self.stage} failed ({self.error_class})")


def _dedupe_nonempty(parts: Iterable[str]) -> list[str]:
    out: list[str] = []
    for part in parts:
        text = str(part or "").strip()
        if text and text not in out:
            out.append(text)
    return out


def require_huiji_runtime_source(cfg: Any) -> None:
    """Reject configurations that do not select the installed Huiji source."""
    huiji = getattr(cfg, "huiji", None)
    enabled = bool(getattr(huiji, "enabled", False))
    source_mode = str(getattr(huiji, "source_mode", "") or "").strip()
    if not enabled or source_mode != "huiji_crawler":
        raise RuntimeError(
            "RAG runtime requires huiji.enabled=true and huiji.source_mode=huiji_crawler"
        )


def _sparse_query_for_plan(query: str, query_plan: QueryPlan | None) -> str:
    if query_plan is None:
        return query
    explicit = str(getattr(query_plan, "sparse_query", "") or "").strip()
    if explicit:
        return explicit
    parts: list[str] = []
    if query_plan.entity:
        parts.append(query_plan.entity)
    parts.extend(query_plan.aliases)
    parts.extend(query_plan.scatter_terms)
    if query_plan.intent in {"profile", "profile_fact", "intro"}:
        parts.extend(("角色资料", "基础资料"))
    else:
        parts.extend(INTENT_SECTION_HINTS.get(query_plan.intent, ()))
    return " ".join(_dedupe_nonempty(parts)) or query


def _plan_mentions_youtium(plan: QueryPlan | None) -> bool:
    if plan is None:
        return False
    haystack = " ".join(
        _dedupe_nonempty(
            [
                plan.original_query,
                plan.normalized_query,
                plan.entity or "",
                getattr(plan, "dense_query", ""),
                getattr(plan, "sparse_query", ""),
                getattr(plan, "media_query", ""),
                *plan.aliases,
                *plan.scatter_terms,
            ]
        )
    ).lower()
    return "\u5c24\u63d0\u59c6" in haystack or "youtium" in haystack


def _section_from_parent(parent_id: str) -> str:
    return parent_id.rsplit("/", 1)[-1] if "/" in parent_id else parent_id


def _section_matches_policy(row: dict[str, Any], policy: PacketPolicy) -> bool:
    if not policy.sections:
        return True
    parent_section = _section_from_parent(str(row.get("parent_id", "")))
    section_kind = str(row.get("section_kind", ""))
    normalized = {
        "skill": "skills",
        "skin": "skins",
    }.get(section_kind, section_kind)
    return parent_section in policy.sections or section_kind in policy.sections or normalized in policy.sections


def _row_child_id(row: dict[str, Any]) -> str:
    return str(row.get("child_id") or row.get("id") or "")


def _row_matched_intents(row: dict[str, Any]) -> tuple[str, ...]:
    value = row.get("matched_intents", ())
    if isinstance(value, str):
        return (value,) if value else ()
    if isinstance(value, (list, tuple, set)):
        return tuple(str(item) for item in value if str(item))
    return ()


def _tag_row_intents(row: dict[str, Any], intents: Iterable[str]) -> dict[str, Any]:
    item = dict(row)
    merged = list(_row_matched_intents(item))
    for intent in intents:
        if intent and intent not in merged:
            merged.append(intent)
    item["matched_intents"] = tuple(merged)
    return item


def _row_to_result(row: dict[str, Any], stage: str) -> dict[str, Any]:
    metadata_debug = row.get("debug") if isinstance(row.get("debug"), dict) else {}
    metadata_debug = dict(metadata_debug)
    metadata_debug["matched_intents"] = _row_matched_intents(row)
    return {
        "name": str(row.get("entity_name") or row.get("name") or ""),
        "category": str(row.get("category") or ""),
        "source": str(row.get("source") or row.get("parent_id") or ""),
        "score": float(row.get("score", row.get("bm25_score", row.get("vector_score", 0.0))) or 0.0),
        "content": str(row.get("text") or row.get("content") or ""),
        "heading_path": str(row.get("heading_path") or row.get("title") or ""),
        "chunk_index": int(row.get("chunk_index", 0) or 0),
        "retrieval_stage": stage,
        "child_id": _row_child_id(row),
        "parent_id": str(row.get("parent_id", "")),
        "section_kind": str(row.get("section_kind", "")),
        "entity_type": str(row.get("entity_type", "")),
        "entity_id": str(row.get("entity_id", "")),
        "media_policy": str(row.get("media_policy", "")),
        "media_ids": tuple(row.get("media_ids") or ()),
        "debug": metadata_debug,
    }


def _entity_ref_for_plan(plan: QueryPlan) -> EntityRef | None:
    entity_type = str(getattr(plan, "entity_type", None) or "").strip()
    entity_id = str(getattr(plan, "entity_id", None) or "").strip()
    entity_name = str(getattr(plan, "entity", None) or "").strip()
    if not (entity_type and entity_id and entity_name):
        return None
    return EntityRef(
        entity_type=entity_type,
        entity_id=entity_id,
        entity_name=entity_name,
        aliases=tuple(getattr(plan, "aliases", ()) or ()),
        resolution_mode=str(getattr(plan, "resolution_mode", "unresolved") or "unresolved"),
    )


def _doc_to_huiji_row(doc: Document, score: float, rank: int) -> dict[str, Any]:
    metadata = dict(doc.metadata)
    child_id = str(metadata.get("child_id") or metadata.get("id") or "")
    return {
        "child_id": child_id,
        "parent_id": str(metadata.get("parent_id", "")),
        "entity_id": str(metadata.get("entity_id", "")),
        "entity_name": str(metadata.get("entity_name") or metadata.get("name") or ""),
        "name": str(metadata.get("entity_name") or metadata.get("name") or ""),
        "category": str(metadata.get("category", "")),
        "section_kind": str(metadata.get("section_kind", "")),
        "title": str(metadata.get("title") or metadata.get("heading_path") or ""),
        "text": doc.page_content,
        "search_text": str(metadata.get("search_text") or doc.page_content),
        "chunk_index": int(metadata.get("chunk_index", 0) or 0),
        "media_ids": tuple(metadata.get("media_ids") or ()),
        "media_policy": str(metadata.get("media_policy", "")),
        "source": str(metadata.get("source") or metadata.get("parent_id") or ""),
        "heading_path": str(metadata.get("heading_path") or metadata.get("title") or ""),
        "entity_type": str(metadata.get("entity_type", "")),
        "quality_flags": tuple(metadata.get("quality_flags") or ()),
        "route_tags": tuple(metadata.get("route_tags") or ()),
        "vector_score": float(score),
        "dense_rank": rank,
    }


class Retriever:
    """Search the installed Huiji v3 artifacts and active vector collection."""

    def __init__(
        self,
        cfg: Any,
        vectorstore: Any,
        artifact_snapshot: RuntimeArtifactSnapshot | None = None,
    ) -> None:
        require_huiji_runtime_source(cfg)
        self.cfg = cfg
        self.vectorstore = vectorstore
        self.artifact_snapshot = artifact_snapshot or resolve_runtime_artifact_snapshot(cfg)
        vector_collection = str(getattr(vectorstore, "collection_name", "") or "")
        if (
            vector_collection
            and self.artifact_snapshot.collection_name
            and vector_collection != self.artifact_snapshot.collection_name
        ):
            raise RuntimeError("Huiji artifact and vector collection tuple mismatch")
        self.last_omitted_actions: list[dict[str, Any]] = []
        self.last_expansion_debug: dict[str, Any] = {}
        self.last_route_debug: dict[str, Any] = {}
        self._huiji_children: list[dict[str, Any]] = []
        self._huiji_sparse = LocalBM25SparseIndex()
        self._load_huiji_children()
        reranker_cfg = getattr(cfg, "reranker", None)
        self._reranker = OptionalBgeReranker(
            enabled=bool(getattr(reranker_cfg, "enabled", False)),
            base_url=str(getattr(reranker_cfg, "base_url", "")),
            api_key=str(getattr(reranker_cfg, "api_key", "")),
            model=str(getattr(reranker_cfg, "model", "BAAI/bge-reranker-v2-m3")),
        )

    def _load_huiji_children(self) -> None:
        snapshot = self.artifact_snapshot
        if not snapshot.child_blocks.is_file():
            raise RuntimeError("Huiji child artifact is missing")
        self._huiji_children = [
            self._normalize_child_row(row) for row in iter_jsonl(snapshot.child_blocks)
        ]
        if not self._huiji_children:
            raise RuntimeError("Huiji child artifact is empty")
        if snapshot.child_bm25.exists():
            self._huiji_sparse = LocalBM25SparseIndex.load(snapshot.child_bm25)
        else:
            self._huiji_sparse.build(self._huiji_children)

    def _normalize_child_row(self, row: dict[str, Any]) -> dict[str, Any]:
        item = dict(row)
        item.setdefault("name", item.get("entity_name", ""))
        item.setdefault("source", item.get("parent_id", ""))
        item.setdefault("heading_path", item.get("title", ""))
        item.setdefault("search_text", item.get("text", ""))
        for key in ("media_ids", "quality_flags", "route_tags", "ancestor_ids"):
            value = item.get(key, ())
            if isinstance(value, list):
                item[key] = tuple(value)
            elif value is None:
                item[key] = ()
        return item

    def search(
        self,
        query: str,
        k: int | None = None,
        category: str | None = None,
        query_plan: QueryPlan | None = None,
        trace: RequestTrace | NullTrace | None = None,
    ) -> list[dict[str, Any]]:
        active_trace = trace or NullTrace()
        self.last_omitted_actions = []
        self.last_expansion_debug = {}
        self.last_route_debug = {}
        top_k = int(k or getattr(getattr(self.cfg, "rag", None), "top_k", 4) or 4)

        if query_plan is None:
            raise RetrievalExecutionError("retrieval.plan", "MissingQueryPlan")
        return self._search_huiji(query, top_k, query_plan, active_trace)

    def _search_huiji(
        self,
        query: str,
        top_k: int,
        plan: QueryPlan,
        trace: RequestTrace | NullTrace,
    ) -> list[dict[str, Any]]:
        retrieval_cfg = getattr(self.cfg, "retrieval", None)
        bm25_k = int(getattr(retrieval_cfg, "bm25_k", max(top_k * 4, 20)) or max(top_k * 4, 20))
        dense_k = int(getattr(retrieval_cfg, "dense_k", max(top_k * 4, 20)) or max(top_k * 4, 20))
        rerank_k = int(getattr(retrieval_cfg, "rerank_k", max(top_k * 6, 30)) or max(top_k * 6, 30))
        configured_budget = int(getattr(retrieval_cfg, "context_budget_chars", 9000) or 9000)
        sibling_window = int(getattr(retrieval_cfg, "sibling_window", 1) or 1)
        oversample = int(getattr(retrieval_cfg, "candidate_oversample", 4) or 4)
        candidate_k_max = int(getattr(retrieval_cfg, "candidate_k_max", 100) or 100)
        raw_voice_page_size = getattr(retrieval_cfg, "voice_page_size", None)
        raw_voice_page_size_max = getattr(retrieval_cfg, "voice_page_size_max", None)
        configured_voice_page_size = int(8 if raw_voice_page_size is None else raw_voice_page_size)
        voice_page_size_max = int(20 if raw_voice_page_size_max is None else raw_voice_page_size_max)
        voice_page_size = clamp_voice_page_size(configured_voice_page_size, voice_page_size_max)
        configured_max_sources = int(getattr(retrieval_cfg, "max_sources", 20) or 20)
        max_sources = min(max(0, top_k), max(1, configured_max_sources))

        intents = requested_intents(plan)
        owner = _entity_ref_for_plan(plan)
        ownership_checks: list[OwnershipDiagnostics] = []
        artifact_capability = str(
            getattr(getattr(self, "artifact_snapshot", None), "capability", "v3")
        )
        bundle = compose_packet_policies(
            getattr(plan, "entity_type", None),
            intents,
            artifact_capability,
        )

        if owner is None and any(intent not in _ENTITY_FREE_INTENTS for intent in intents):
            targets = {
                intent: max(1, int(policy.source_target))
                for intent, policy in zip(bundle.requested_intents, bundle.policies)
            }
            required_source_count = sum(targets.values())
            candidate_k = calculate_candidate_k(
                max(bm25_k, dense_k),
                required_source_count,
                oversample,
                candidate_k_max,
            )
            for stage in _HUJI_RETRIEVAL_STAGES:
                attributes = {} if stage == "retrieval.structured" else {"candidate_k": candidate_k}
                with trace.span(stage, **attributes):
                    pass
            self.last_route_debug = {
                "requested_intents": list(bundle.requested_intents),
                "candidate_k": candidate_k,
                "required_source_count": required_source_count,
                "intent_candidates": {intent: 0 for intent in targets},
                "intent_targets": targets,
                "intent_retained": {intent: 0 for intent in targets},
                "coverage_shortfall": dict(targets),
                "chars_used": 0,
                "max_sources": max_sources,
                "owner_before": 0,
                "owner_after": 0,
                "owner_mismatch": 0,
                "missing_owner_metadata": 0,
                "owner_shortfall": 0,
                "unresolved_owner": True,
            }
            return []

        def owner_gate(rows: Iterable[dict[str, Any]], stage: str) -> list[dict[str, Any]]:
            kept, diagnostics = filter_owned_rows(rows, owner, stage)
            ownership_checks.append(diagnostics)
            return kept

        validate_target_parent(
            getattr(plan, "target_parent_id", None),
            owner,
            self._huiji_children,
        )
        budget = min(configured_budget, bundle.context_budget_chars)
        exact_rows_by_intent: dict[str, list[dict[str, Any]]] = {}
        structured_by_id: dict[str, dict[str, Any]] = {}
        with trace.span("retrieval.structured"):
            for intent, policy in zip(bundle.requested_intents, bundle.policies):
                exact_rows = owner_gate([
                    _tag_row_intents(row, (intent,))
                    for row in self._structured_rows_for_plan(plan, policy)
                ], f"structured.{intent}")
                exact_rows_by_intent[intent] = exact_rows
                for row in exact_rows:
                    child_id = _row_child_id(row)
                    if child_id not in structured_by_id:
                        structured_by_id[child_id] = row
                    else:
                        structured_by_id[child_id] = _tag_row_intents(
                            structured_by_id[child_id],
                            _row_matched_intents(row),
                        )

        required_source_count = calculate_required_source_count(
            bundle,
            exact_rows_by_intent,
            voice_page_size,
        )
        max_sources = min(
            max(1, configured_max_sources),
            max(max_sources, required_source_count),
        )
        candidate_k = calculate_candidate_k(
            max(bm25_k, dense_k),
            required_source_count,
            oversample,
            candidate_k_max,
        )
        bm25_rows = list(structured_by_id.values())
        with trace.span("retrieval.bm25", candidate_k=candidate_k):
            bm25_rows.extend(owner_gate(
                self._bm25_rows_for_plan(query, plan, candidate_k),
                "bm25",
            ))
        with trace.span("retrieval.dense", candidate_k=candidate_k):
            dense_rows = owner_gate(
                self._dense_rows_for_plan(query, plan, candidate_k),
                "dense",
            )
        with trace.span("retrieval.fusion", candidate_k=candidate_k):
            ranked = weighted_rrf(
                bm25_rows,
                dense_rows,
                entity=plan.entity,
                intent=plan.intent,
                allow_youtium=_plan_mentions_youtium(plan),
                semantic_intents=bundle.requested_intents,
                intent_sections={
                    intent: policy.sections
                    for intent, policy in zip(bundle.requested_intents, bundle.policies)
                },
            )
            ranked = owner_gate(
                [self._infer_matched_intents(row, bundle) for row in ranked],
                "rrf",
            )
        with trace.span("retrieval.rerank", candidate_k=candidate_k):
            ranked = self._reranker.rerank(
                str(getattr(plan, "dense_query", "") or plan.normalized_query or query),
                ranked,
                limit=max(rerank_k, candidate_k, required_source_count),
            )
            ranked = owner_gate(ranked, "rerank")
        with trace.span("retrieval.expand", candidate_k=candidate_k):
            expansion_children = owner_gate(
                [self._infer_matched_intents(row, bundle) for row in self._huiji_children],
                "expand.candidates",
            )
            expanded = expand_ranked_children(
                ranked,
                expansion_children,
                bundle.expansion_policy,
                budget_chars=0,
                sibling_window=sibling_window,
                owner=owner,
                semantic_intents=intents,
            )
            expanded_sources = owner_gate(expanded.sources, "expand")
        with trace.span("retrieval.allocate", candidate_k=candidate_k):
            allocation = allocate_sources(
                expanded_sources,
                exact_rows_by_intent,
                bundle,
                max_sources=max_sources,
                context_budget_chars=budget,
                voice_page_size=voice_page_size,
                owner=owner,
            )
            allocated_sources = owner_gate(allocation.sources, "allocate")
        coverage_by_intent = {item.intent: item for item in allocation.coverage}
        entity_name = plan.entity or (
            str(ranked[0].get("entity_name") or ranked[0].get("name") or "") if ranked else ""
        )
        candidate_actions = make_omitted_actions(
            expansion_children,
            entity_name,
            owner,
            intents,
        )
        omitted_actions: list[dict[str, Any]] = []
        omitted_parent_ids: set[str] = set()
        for action in candidate_actions:
            action_intent = str(action.get("intent", ""))
            coverage = coverage_by_intent.get(action_intent)
            if coverage is not None and coverage.shortfall == 0:
                continue
            parent_id = str(action.get("target_parent_id", ""))
            if parent_id and parent_id not in omitted_parent_ids:
                omitted_actions.append(action)
                omitted_parent_ids.add(parent_id)
        self.last_omitted_actions = omitted_actions
        self.last_expansion_debug = expanded.debug
        owner_before = sum(item.before_count for item in ownership_checks)
        owner_after = sum(item.after_count for item in ownership_checks)
        owner_mismatch = sum(item.owner_mismatch for item in ownership_checks)
        missing_owner_metadata = sum(
            item.missing_owner_metadata for item in ownership_checks
        )
        self.last_route_debug = {
            "requested_intents": list(bundle.requested_intents),
            "candidate_k": candidate_k,
            "required_source_count": required_source_count,
            "intent_candidates": {item.intent: item.available for item in allocation.coverage},
            "intent_targets": {item.intent: item.target for item in allocation.coverage},
            "intent_retained": {item.intent: item.retained for item in allocation.coverage},
            "coverage_shortfall": {item.intent: item.shortfall for item in allocation.coverage},
            "chars_used": allocation.chars_used,
            "max_sources": max_sources,
            "owner_before": owner_before,
            "owner_after": owner_after,
            "owner_mismatch": owner_mismatch,
            "missing_owner_metadata": missing_owner_metadata,
            "owner_shortfall": (
                max((item.owner_shortfall for item in ownership_checks), default=0)
                if owner
                else 0
            ),
            "ownership_key": list(owner.ownership_key) if owner else [],
            "ownership_stages": {
                item.stage: {
                    "before": item.before_count,
                    "after": item.after_count,
                    "owner_mismatch": item.owner_mismatch,
                    "missing_owner_metadata": item.missing_owner_metadata,
                }
                for item in ownership_checks
            },
        }
        results = [_row_to_result(row, "huiji_hybrid") for row in allocated_sources]
        assert_packet_ownership(owner, results, ())
        return results

    def _infer_matched_intents(
        self,
        row: dict[str, Any],
        bundle: IntentPolicyBundle,
    ) -> dict[str, Any]:
        matched = list(_row_matched_intents(row))
        for intent, policy in zip(bundle.requested_intents, bundle.policies):
            if _section_matches_policy(row, policy) and intent not in matched:
                matched.append(intent)
        return _tag_row_intents(row, matched)

    def _filter_to_owner(
        self,
        ranked: list[dict[str, Any]],
        plan: QueryPlan,
    ) -> list[dict[str, Any]]:
        return filter_owned_rows(ranked, _entity_ref_for_plan(plan), "filter")[0]

    def _structured_rows_for_plan(self, plan: QueryPlan, policy: PacketPolicy) -> list[dict[str, Any]]:
        if not plan.entity:
            return []
        target_parent_id = getattr(plan, "target_parent_id", None)
        rows: list[dict[str, Any]] = []
        for row in self._huiji_children:
            if str(row.get("entity_name", "")) != plan.entity:
                continue
            if str(row.get("category", "")) != "character" and getattr(plan, "entity_type", None) == "character":
                continue
            if target_parent_id and str(row.get("parent_id", "")) != target_parent_id:
                continue
            if not _section_matches_policy(row, policy):
                continue
            item = dict(row)
            item["structured_rank"] = len(rows) + 1
            item["bm25_score"] = 1.0
            debug = dict(item.get("debug", {}))
            debug["structured_exact"] = True
            item["debug"] = debug
            rows.append(item)
        return rows

    def _bm25_rows_for_plan(self, query: str, plan: QueryPlan, limit: int) -> list[dict[str, Any]]:
        sparse_query = _sparse_query_for_plan(query, plan)
        rows = self._huiji_sparse.search(sparse_query, top_k=limit)
        return [self._normalize_child_row(row) for row in rows]

    def _dense_rows_for_plan(self, query: str, plan: QueryPlan, limit: int) -> list[dict[str, Any]]:
        dense_query = str(getattr(plan, "dense_query", "") or plan.normalized_query or query)
        try:
            results = self.vectorstore.similarity_search_with_relevance_scores(dense_query, k=limit, expr=None)
        except Exception:
            try:
                docs = self.vectorstore.similarity_search(dense_query, k=limit, expr=None)
            except Exception as error:
                raise RetrievalExecutionError(
                    "retrieval.dense",
                    type(error).__name__,
                ) from error
            return [_doc_to_huiji_row(doc, 0.0, rank) for rank, doc in enumerate(docs, start=1)]
        return [_doc_to_huiji_row(doc, score, rank) for rank, (doc, score) in enumerate(results, start=1)]
