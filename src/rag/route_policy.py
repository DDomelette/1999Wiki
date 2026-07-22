"""Authorization and outcome policy for grounded versus free RAG routes."""
from __future__ import annotations

from collections.abc import Mapping, Sequence

from src.rag.contracts import RetrievalOutcome, RouteAuthorization, RouteDecision
from src.rag.query_plan import QueryPlan, requested_intents


def normalize_action_type(action_payload: Mapping[str, object] | None) -> str:
    payload = action_payload or {}
    explicit = str(payload.get("action_type") or "").strip()
    if explicit in {"expand_search", "force_free_supplement", "expand_parent"}:
        return explicit
    legacy_intent = str(payload.get("intent") or "").strip()
    legacy_policy = str(payload.get("packet_policy") or "").strip()
    if legacy_intent == "llm_general" or legacy_policy == "free_supplement":
        return "force_free_supplement"
    if legacy_intent == "expanded_rag" or legacy_policy == "expanded":
        return "expand_search"
    return ""


def authorize_route(
    plan: QueryPlan,
    route_options: Mapping[str, object] | None,
    action_payload: Mapping[str, object] | None,
) -> RouteAuthorization:
    options = route_options or {}
    action_type = normalize_action_type(action_payload)
    force = action_type == "force_free_supplement"
    allow_after_empty = options.get("free_supplement") is True or options.get(
        "freeSupplement"
    ) is True
    expanded = (
        action_type == "expand_search"
        or options.get("expanded") is True
    )
    planner_route = str(getattr(plan, "route", "rag_grounded") or "rag_grounded")
    if planner_route == "hybrid_answer" or planner_route not in {
        "rag_grounded",
        "expanded_rag",
        "llm_general",
    }:
        planner_route = "rag_grounded"
    proposed_route = "expanded_rag" if expanded else planner_route
    reason = (
        "explicit_recovery_action"
        if force
        else (
            "toggle_allows_empty_fallback"
            if allow_after_empty
            else "default_closed"
        )
    )
    return RouteAuthorization(
        semantic_intents=requested_intents(plan),
        proposed_route=proposed_route,
        allow_free_supplement_after_empty=allow_after_empty,
        force_free_supplement=force,
        authorization_reason=reason,
    )


def classify_retrieval_outcome(
    sources: Sequence[object],
    coverage_shortfall: Mapping[str, int],
    *,
    failed: bool = False,
) -> RetrievalOutcome:
    if failed:
        return "failed"
    if not sources:
        return "empty"
    if any(type(value) is int and value > 0 for value in coverage_shortfall.values()):
        return "partial"
    return "sufficient"


def finalize_route(
    authorization: RouteAuthorization,
    outcome: RetrievalOutcome,
) -> RouteDecision:
    if outcome == "failed":
        return RouteDecision(
            authorization,
            outcome,
            "rag_grounded",
            "retrieval_failed",
        )
    if authorization.force_free_supplement:
        return RouteDecision(
            authorization,
            outcome,
            "llm_general",
            "explicit_recovery_action",
        )
    if outcome == "empty" and authorization.allow_free_supplement_after_empty:
        return RouteDecision(
            authorization,
            outcome,
            "llm_general",
            "authorized_empty_fallback",
        )
    grounded_route = (
        "expanded_rag"
        if authorization.proposed_route == "expanded_rag"
        else "rag_grounded"
    )
    return RouteDecision(
        authorization,
        outcome,
        grounded_route,
        f"grounded_{outcome}",
    )


__all__ = [
    "authorize_route",
    "classify_retrieval_outcome",
    "finalize_route",
    "normalize_action_type",
]
