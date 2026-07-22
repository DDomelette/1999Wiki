"""Retrieval-augmented generation package."""

from src.rag.contracts import (
    CitationValidation,
    EntityRef,
    FrozenRetrievalPacket,
    ResponsePacket,
    RouteAuthorization,
    RouteDecision,
    SourceRef,
)
from src.rag.tracing import NullTrace, RequestTrace, TraceSnapshot, make_request_trace
from src.rag.ownership import OwnershipDiagnostics, OwnershipViolation
from src.rag.route_policy import authorize_route, classify_retrieval_outcome, finalize_route

__all__ = [
    "CitationValidation",
    "EntityRef",
    "FrozenRetrievalPacket",
    "NullTrace",
    "OwnershipDiagnostics",
    "OwnershipViolation",
    "RequestTrace",
    "ResponsePacket",
    "RouteAuthorization",
    "RouteDecision",
    "SourceRef",
    "TraceSnapshot",
    "make_request_trace",
    "authorize_route",
    "classify_retrieval_outcome",
    "finalize_route",
]
