"""FastAPI backend for health, RAG ask, category metadata, and static HTML."""
from __future__ import annotations

import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.responses import StreamingResponse

from backend.categories_meta import CATEGORIES_META
from backend.conversation_runtime import (
    acquire_lease,
    clear_memory,
    install_uvicorn_access_log_filter,
    memory_info_for,
    release_lease,
)
from backend.schemas import (
    AskRequest,
    AskResponse,
    AssetItem,
    CategoriesResponse,
    CategoryDocsResponse,
    HealthResponse,
    MediaItem,
    SourceItem,
    VoicePanelPage,
    normalize_asset_items,
    normalize_media_items,
    normalize_media_panels,
    normalize_route,
    sanitize_transport_value,
)
from backend.sse import rag_stream_generator
from backend.wiki import router as wiki_router
from config.config import get_config
from src.assets.voice_pagination import InvalidVoiceCursor, VoiceCursorBuildMismatch
from src.huiji_rag.provenance import VerificationIssue, VerificationResult, verify_runtime
from src.rag.chain import RAGChain, VoicePaginationUnavailable
from src.rag.conversation import ConversationMemoryStore
from src.rag.execution import AskExecutionInput, build_completed_turn
from src.rag.retriever import Retriever
from src.rag.serializers import response_packet_to_public_dict
from src.rag.tracing import make_request_trace, trace_snapshot_to_public
from src.rag.vectorstore import load_vectorstore
from src.utils.text_cleaner import clean_markdown

cfg = get_config()
install_uvicorn_access_log_filter()

app = FastAPI(title="1999Search RAG", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        f"http://localhost:{cfg.server.streamlit_port}",
        f"http://localhost:{cfg.server.gradio_port}",
        f"http://127.0.0.1:{cfg.server.streamlit_port}",
        f"http://127.0.0.1:{cfg.server.gradio_port}",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(wiki_router)

_state: dict[str, Any] = {
    "vs": None,
    "retriever": None,
    "chain": None,
    "memory": ConversationMemoryStore(),
    "loaded": False,
    "provenance_checked": False,
    "provenance": None,
}


def _memory_store() -> ConversationMemoryStore:
    store = _state.get("memory")
    if not isinstance(store, ConversationMemoryStore):
        store = ConversationMemoryStore()
        _state["memory"] = store
    return store


def _verify_provenance_once() -> VerificationResult:
    current = _state.get("provenance")
    if _state.get("provenance_checked") and isinstance(current, VerificationResult):
        return current
    try:
        result = verify_runtime(cfg)
    except Exception:
        result = VerificationResult(
            status="error",
            issues=(VerificationIssue("verification_internal_error", "runtime"),),
            baseline_sha256="",
        )
    _state["provenance"] = result
    _state["provenance_checked"] = True
    return result


def _ensure_loaded() -> None:
    provenance = _verify_provenance_once()
    if not provenance.allowed:
        _state.update(vs=None, retriever=None, chain=None, loaded=False)
        return
    if _state.get("loaded"):
        return
    try:
        vs = load_vectorstore(cfg)
        retriever = Retriever(cfg, vs)
        chain = RAGChain(cfg, retriever)
        _state.update(vs=vs, retriever=retriever, chain=chain, loaded=True)
    except Exception as e:
        print(f"[backend] vectorstore load failed: {e}")
        _state["loaded"] = False


def _is_milvus_vectorstore(vs: Any) -> bool:
    return hasattr(vs, "client") and hasattr(vs, "collection_name")


def _milvus_string_expr(field: str, value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'{field} == "{escaped}"'


def _total_doc_count(vs: Any) -> int:
    if vs is None:
        return 0
    if _is_milvus_vectorstore(vs):
        try:
            stats = vs.client.get_collection_stats(collection_name=vs.collection_name)
            return int(stats.get("row_count", 0))
        except Exception:
            return 0
    try:
        return int(vs._collection.count())
    except Exception:
        return 0


def _model_to_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "dict"):
        return value.dict()
    return dict(value)


@app.on_event("startup")
async def _startup() -> None:
    _ensure_loaded()


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    _ensure_loaded()
    chain = _state.get("chain")
    vs = _state.get("vs")
    provenance = _state.get("provenance")
    if isinstance(provenance, VerificationResult):
        public_provenance = provenance.to_public_dict()
        provenance_status = str(public_provenance["status"])
        provenance_errors = [
            str(issue.get("code") or "")
            for issue in public_provenance["issues"]
            if isinstance(issue, dict) and issue.get("code")
        ]
        provenance_evidence = str(public_provenance.get("evidence_relpath") or "")
    else:
        provenance_status = "pending"
        provenance_errors = []
        provenance_evidence = ""
    return HealthResponse(
        status="ok" if _state["loaded"] else "error",
        vectorstore_loaded=_state["loaded"],
        llm_ready=bool(chain and chain.llm_ready()),
        doc_count=_total_doc_count(vs),
        provenance_status=provenance_status,
        provenance_errors=provenance_errors,
        provenance_evidence=provenance_evidence,
    )


@app.post("/ask", response_model=AskResponse)
async def ask(req: AskRequest) -> AskResponse | JSONResponse:
    _ensure_loaded()
    chain = _state.get("chain")
    if chain is None:
        return JSONResponse(
            {"answer": "向量库加载失败，请检查 Milvus、embedding key 与索引。", "sources": []},
            status_code=503,
        )
    store = _memory_store()
    trace = make_request_trace()
    with trace.span("memory.acquire"):
        lease = await acquire_lease(store, req.conversation_id)
    completed_turn = None
    try:
        route_options = _model_to_dict(req.route_options)
        action_payload = _model_to_dict(req.action_payload) if req.action_payload else None
        execution_request = AskExecutionInput(
            question=req.question,
            category=req.category,
            route_options=route_options,
            action_payload=action_payload,
            memory_status=lease.status,
            memory_turns_used=len(lease.projection.turns),
        )
        packet = chain.execute(
            req.question,
            req.category,
            route_options,
            action_payload,
            lease.projection,
            memory_status=lease.status,
            memory_turns_used=len(lease.projection.turns),
            trace=trace,
        )
        with trace.span("response.serialize"):
            public_payload = response_packet_to_public_dict(packet)
            AskResponse.model_validate(public_payload)
        completed_turn = build_completed_turn(
            execution_request,
            packet,
            datetime.now(timezone.utc),
        )
        trace.mark_visible_first_token()
        trace.mark_completed()
        public_payload["timing"] = trace_snapshot_to_public(trace.snapshot())
        response = AskResponse.model_validate(public_payload)
        return response
    finally:
        await release_lease(store, lease, completed_turn)


@app.delete("/conversations/{conversation_id}", status_code=204)
async def clear_conversation(conversation_id: UUID) -> Response:
    await clear_memory(_memory_store(), conversation_id)
    return Response(status_code=204)


@app.get("/api/media/voice/page", response_model=VoicePanelPage)
async def voice_page(cursor: str) -> VoicePanelPage:
    chain = _state.get("chain")
    if not _state.get("loaded") or chain is None:
        raise HTTPException(status_code=503, detail="RAG chain is unavailable")
    get_voice_page = getattr(chain, "get_voice_page", None)
    if not callable(get_voice_page):
        raise HTTPException(status_code=503, detail="Voice pagination unavailable")
    try:
        page = get_voice_page(cursor)
    except VoicePaginationUnavailable as exc:
        raise HTTPException(status_code=503, detail="Voice pagination unavailable") from exc
    except InvalidVoiceCursor as exc:
        raise HTTPException(status_code=400, detail="Invalid voice cursor") from exc
    except VoiceCursorBuildMismatch as exc:
        raise HTTPException(
            status_code=409,
            detail="Voice media build changed; reload first page",
        ) from exc
    return VoicePanelPage.model_validate(sanitize_transport_value(page))


def _count_by_category(vs: Any, category: str) -> int:
    if _is_milvus_vectorstore(vs):
        try:
            rows = vs.client.query(
                collection_name=vs.collection_name,
                filter=_milvus_string_expr("category", category),
                output_fields=["id"],
                limit=100000,
            )
            return len(rows)
        except Exception:
            return 0
    try:
        return vs._collection.count(where={"category": category})
    except TypeError:
        try:
            res = vs._collection.get(where={"category": category}, include=[], limit=100000)
            return len(res.get("ids", []))
        except Exception:
            return 0
    except Exception:
        return 0


def _make_display_snippet(text: str, limit: int = 200) -> str:
    text = re.sub(
        r"%% DATAVIEW_PUBLISHER: start.*?%% DATAVIEW_PUBLISHER: end %%",
        "",
        text,
        flags=re.DOTALL,
    )
    text = re.sub(r"^%% DATAVIEW_PUBLISHER: .*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"```dataview.*?```", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = clean_markdown(text)
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("|"):
            continue
        lines.append(stripped)
    snippet = re.sub(r"\s+", " ", " ".join(lines)).strip()
    return snippet[:limit]


@app.get("/categories", response_model=CategoriesResponse)
async def categories():
    _ensure_loaded()
    vs = _state.get("vs")
    out = []
    for meta in CATEGORIES_META:
        doc_count = _count_by_category(vs, meta["key"]) if vs is not None else 0
        out.append({
            "key": meta["key"],
            "title": meta["title"],
            "subtitle": meta["subtitle"],
            "description": meta["description"],
            "doc_count": doc_count,
            "cover_prompt": meta["cover_prompt"],
        })
    return CategoriesResponse(categories=out)


@app.get("/category/{key}/docs", response_model=CategoryDocsResponse)
async def category_docs(key: str, limit: int = 50):
    _ensure_loaded()
    vs = _state.get("vs")
    docs_out = []
    if vs is not None:
        if _is_milvus_vectorstore(vs):
            try:
                rows = vs.client.query(
                    collection_name=vs.collection_name,
                    filter=_milvus_string_expr("category", key),
                    output_fields=["text", "name", "source"],
                    limit=limit,
                )
                for row in rows:
                    docs_out.append({
                        "name": row.get("name", ""),
                        "source": row.get("source", ""),
                        "snippet": _make_display_snippet(row.get("text") or ""),
                    })
            except Exception as e:
                print(f"[backend] category docs query failed: {e}")
        else:
            try:
                res = vs._collection.get(
                    where={"category": key},
                    include=["documents", "metadatas"],
                    limit=limit,
                )
                ids = res.get("ids", [])
                documents = res.get("documents", [])
                metadatas = res.get("metadatas", [])
                for i in range(len(ids)):
                    doc_text = documents[i] if i < len(documents) else ""
                    meta = metadatas[i] if i < len(metadatas) else {}
                    docs_out.append({
                        "name": meta.get("name", ""),
                        "source": meta.get("source", ""),
                        "snippet": _make_display_snippet(doc_text or ""),
                    })
            except Exception as e:
                print(f"[backend] category docs query failed: {e}")
    return CategoryDocsResponse(key=key, docs=docs_out)


@app.post("/ask/stream")
async def ask_stream(req: AskRequest, request: Request):
    _ensure_loaded()
    chain = _state.get("chain")
    if chain is None:
        return JSONResponse(
            {"answer": "向量库加载失败，请检查 Milvus、embedding key 与索引。", "sources": []},
            status_code=503,
        )
    gen = rag_stream_generator(
        chain,
        req.question,
        req.category,
        route_options=_model_to_dict(req.route_options),
        action_payload=_model_to_dict(req.action_payload) if req.action_payload else None,
        memory_store=_memory_store(),
        conversation_id=req.conversation_id,
        is_disconnected=request.is_disconnected,
    )
    return StreamingResponse(
        gen,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


html_dir = cfg.paths.frontend_html
if html_dir.exists():
    app.mount("/", StaticFiles(directory=str(html_dir), html=True), name="html")
