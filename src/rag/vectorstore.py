"""Milvus vector store build/load helpers."""
from __future__ import annotations

import json
import re
import time
from typing import Any, Callable

from langchain_core.documents import Document
from pymilvus import DataType, MilvusClient

from config.config import Config
from src.rag.embeddings import get_embeddings

PRIMARY_FIELD = "id"
TEXT_FIELD = "text"
VECTOR_FIELD = "embedding"

INDEX_PARAMS = {
    "metric_type": "COSINE",
    "index_type": "AUTOINDEX",
    "params": {},
}
SEARCH_PARAMS = {
    "metric_type": "COSINE",
    "params": {},
}
ProgressCallback = Callable[[dict[str, Any]], None]

HUIJI_VARCHAR_LIMITS = {
    "child_id": 256,
    "text": 16384,
    "parent_id": 256,
    "entity_id": 64,
    "entity_name": 512,
    "entity_type": 64,
    "category": 64,
    "section_kind": 64,
    "title": 512,
    "media_policy": 64,
    "media_ids": 4096,
    "ancestor_ids": 2048,
    "quality_flags": 1024,
    "route_tags": 1024,
    "source_ref": 4096,
    "content_hash": 128,
}

HUIJI_BUSINESS_FIELDS = (
    "id",
    "text",
    "parent_id",
    "child_id",
    "entity_id",
    "entity_name",
    "entity_type",
    "category",
    "section_kind",
    "title",
    "depth_level",
    "media_policy",
    "media_ids",
    "ancestor_ids",
    "quality_flags",
    "route_tags",
    "source_ref",
    "chunk_index",
    "content_hash",
)


def _is_rate_limit_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return "rate limit" in text or "tpm limit" in text or "429" in text


def ensure_huiji_collection(client: MilvusClient, collection_name: str, dim: int = 1024) -> None:
    if client.has_collection(collection_name):
        return

    schema = MilvusClient.create_schema(auto_id=False, enable_dynamic_field=True)
    schema.add_field("id", DataType.VARCHAR, is_primary=True, max_length=256)
    schema.add_field("embedding", DataType.FLOAT_VECTOR, dim=dim)
    schema.add_field("text", DataType.VARCHAR, max_length=16384)
    schema.add_field("parent_id", DataType.VARCHAR, max_length=256)
    schema.add_field("child_id", DataType.VARCHAR, max_length=256)
    schema.add_field("entity_id", DataType.VARCHAR, max_length=64)
    schema.add_field("entity_name", DataType.VARCHAR, max_length=512)
    schema.add_field("entity_type", DataType.VARCHAR, max_length=64)
    schema.add_field("category", DataType.VARCHAR, max_length=64)
    schema.add_field("section_kind", DataType.VARCHAR, max_length=64)
    schema.add_field("title", DataType.VARCHAR, max_length=512)
    schema.add_field("depth_level", DataType.INT64)
    schema.add_field("media_policy", DataType.VARCHAR, max_length=64)
    schema.add_field("media_ids", DataType.VARCHAR, max_length=4096)
    schema.add_field("ancestor_ids", DataType.VARCHAR, max_length=2048)
    schema.add_field("quality_flags", DataType.VARCHAR, max_length=1024)
    schema.add_field("route_tags", DataType.VARCHAR, max_length=1024)
    schema.add_field("source_ref", DataType.VARCHAR, max_length=4096)
    schema.add_field("chunk_index", DataType.INT64)
    schema.add_field("content_hash", DataType.VARCHAR, max_length=128)

    index_params = client.prepare_index_params()
    index_params.add_index(
        field_name="embedding",
        index_type="AUTOINDEX",
        metric_type="COSINE",
        params={},
    )
    client.create_collection(
        collection_name=collection_name,
        schema=schema,
        index_params=index_params,
        consistency_level="Bounded",
    )


def huiji_child_to_business_row(child: dict[str, Any]) -> dict[str, Any]:
    return {
        PRIMARY_FIELD: str(child["child_id"]),
        TEXT_FIELD: str(child.get("text") or child.get("search_text") or ""),
        "parent_id": str(child.get("parent_id", "")),
        "child_id": str(child.get("child_id", "")),
        "entity_id": str(child.get("entity_id", "")),
        "entity_name": str(child.get("entity_name", "")),
        "entity_type": str(child.get("entity_type", "character")),
        "category": str(child.get("category", "")),
        "section_kind": str(child.get("section_kind", "")),
        "title": str(child.get("title", "")),
        "depth_level": int(child.get("depth_level", 3) or 3),
        "media_policy": str(child.get("media_policy", "")),
        "media_ids": json.dumps(child.get("media_ids", []), ensure_ascii=False, sort_keys=True),
        "ancestor_ids": json.dumps(child.get("ancestor_ids", []), ensure_ascii=False, sort_keys=True),
        "quality_flags": json.dumps(child.get("quality_flags", []), ensure_ascii=False, sort_keys=True),
        "route_tags": json.dumps(child.get("route_tags", []), ensure_ascii=False, sort_keys=True),
        "source_ref": json.dumps(child.get("source_refs", []), ensure_ascii=False, sort_keys=True),
        "chunk_index": int(child.get("chunk_index", 0) or 0),
        "content_hash": str(child.get("content_hash", "")),
    }


def huiji_child_to_milvus_row(child: dict[str, Any], vector: list[float]) -> dict[str, Any]:
    return {**huiji_child_to_business_row(child), VECTOR_FIELD: vector}


def validate_huiji_child_for_milvus(child: dict[str, Any], row_number: int) -> None:
    values = {
        "child_id": str(child.get("child_id", "")),
        "text": str(child.get("text") or child.get("search_text") or ""),
        "parent_id": str(child.get("parent_id", "")),
        "entity_id": str(child.get("entity_id", "")),
        "entity_name": str(child.get("entity_name", "")),
        "entity_type": str(child.get("entity_type", "character")),
        "category": str(child.get("category", "")),
        "section_kind": str(child.get("section_kind", "")),
        "title": str(child.get("title", "")),
        "media_policy": str(child.get("media_policy", "")),
        "media_ids": json.dumps(child.get("media_ids", []), ensure_ascii=False),
        "ancestor_ids": json.dumps(child.get("ancestor_ids", []), ensure_ascii=False),
        "quality_flags": json.dumps(child.get("quality_flags", []), ensure_ascii=False),
        "route_tags": json.dumps(child.get("route_tags", []), ensure_ascii=False),
        "source_ref": json.dumps(child.get("source_refs", []), ensure_ascii=False),
        "content_hash": str(child.get("content_hash", "")),
    }
    for field, limit in HUIJI_VARCHAR_LIMITS.items():
        value = values[field]
        if len(value) > limit:
            raise ValueError(
                f"huiji child row {row_number} field {field} length {len(value)} exceeds Milvus limit {limit}"
            )


def embed_documents_with_retry(
    embeddings: Any,
    texts: list[str],
    max_retries: int = 3,
    retry_seconds: float = 60.0,
    sleeper: Callable[[float], None] = time.sleep,
    progress: ProgressCallback | None = None,
) -> list[list[float]]:
    attempt = 0
    while True:
        try:
            return embeddings.embed_documents(texts)
        except Exception as exc:
            attempt += 1
            if not _is_rate_limit_error(exc) or attempt > max_retries:
                raise
            if progress:
                progress({
                    "event": "rate_limited",
                    "attempt": attempt,
                    "max_retries": max_retries,
                    "retry_seconds": retry_seconds,
                    "error": str(exc),
                })
            sleeper(retry_seconds)


def query_existing_huiji_ids(client: Any, collection_name: str, limit: int = 100000) -> set[str]:
    try:
        client.load_collection(collection_name)
    except Exception:
        pass
    rows = client.query(
        collection_name=collection_name,
        filter='id != ""',
        output_fields=[PRIMARY_FIELD],
        limit=limit,
    )
    return {str(row.get(PRIMARY_FIELD, "")) for row in rows if row.get(PRIMARY_FIELD)}


def milvus_entity_to_document(entity: dict[str, Any]) -> Document:
    metadata = {
        "id": entity.get(PRIMARY_FIELD, ""),
        "source": entity.get("source", entity.get("parent_id", "")),
        "name": entity.get("name", entity.get("entity_name", "")),
        "category": entity.get("category", ""),
        "heading_path": entity.get("heading_path", entity.get("section_kind", "")),
        "chunk_index": entity.get("chunk_index", 0),
        "parent_id": entity.get("parent_id", ""),
        "child_id": entity.get("child_id", entity.get(PRIMARY_FIELD, "")),
        "entity_id": entity.get("entity_id", ""),
        "entity_name": entity.get("entity_name", entity.get("name", "")),
        "entity_type": entity.get("entity_type", ""),
        "section_kind": entity.get("section_kind", ""),
        "title": entity.get("title", ""),
        "depth_level": entity.get("depth_level", 3),
        "media_policy": entity.get("media_policy", ""),
        "media_ids": entity.get("media_ids", ""),
        "ancestor_ids": entity.get("ancestor_ids", ""),
        "quality_flags": entity.get("quality_flags", ""),
        "route_tags": entity.get("route_tags", ""),
        "source_ref": entity.get("source_ref", ""),
        "content_hash": entity.get("content_hash", ""),
    }
    return Document(page_content=entity.get(TEXT_FIELD, ""), metadata=metadata)


class MilvusVectorstore:
    """Small Milvus adapter matching the subset of LangChain VectorStore we use."""

    def __init__(self, cfg: Config) -> None:
        if cfg.vectorstore.provider != "milvus":
            raise ValueError(f"Unsupported vectorstore provider: {cfg.vectorstore.provider}")
        self.collection_name = cfg.vectorstore.collection_name
        self.client = MilvusClient(uri=cfg.vectorstore.uri, db_name=cfg.vectorstore.db_name)
        self._embeddings = get_embeddings(cfg)
        if not self.client.has_collection(self.collection_name):
            raise RuntimeError(
                f"Milvus collection not found: {cfg.vectorstore.db_name}.{self.collection_name}"
            )

    def similarity_search_with_relevance_scores(self, query: str, k: int = 4, expr: str | None = None, **_: Any):
        query_vector = self._embeddings.embed_query(query)
        results = self.client.search(
            collection_name=self.collection_name,
            data=[query_vector],
            anns_field=VECTOR_FIELD,
            filter=expr or "",
            limit=k,
            output_fields=["*"],
            search_params=SEARCH_PARAMS,
        )
        output = []
        for hit in results[0] if results else []:
            entity = hit.get("entity", hit)
            doc = milvus_entity_to_document(entity)
            score = hit.get("distance", hit.get("score", 0.0))
            output.append((doc, float(score)))
        return output

    def similarity_search(self, query: str, k: int = 4, expr: str | None = None, **kwargs: Any) -> list[Document]:
        return [doc for doc, _ in self.similarity_search_with_relevance_scores(query, k=k, expr=expr, **kwargs)]

    def query_rows(self, expr: str, limit: int = 10000) -> list[dict[str, Any]]:
        return self.client.query(
            collection_name=self.collection_name,
            filter=expr,
            output_fields=["*"],
            limit=limit,
        )


def _new_milvus(cfg: Config) -> MilvusVectorstore:
    return MilvusVectorstore(cfg)


_MILVUS_COLLECTION_NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,254}\Z")


def build_huiji_shadow_collection(
    cfg: Config,
    children: list[dict[str, Any]],
    *,
    collection_name: str,
    active_collection_names: tuple[str, ...],
    batch_size: int = 64,
    batch_delay_seconds: float = 0.6,
    max_retries: int = 3,
    retry_seconds: float = 60.0,
    progress: ProgressCallback | None = None,
    client_factory: Callable[[Config], Any] | None = None,
    embeddings_factory: Callable[[Config], Any] | None = None,
    collection_ensurer: Callable[[Any, str], None] | None = None,
    sleeper: Callable[[float], None] = time.sleep,
) -> int:
    """Create and populate one new non-active Huiji collection."""
    target = str(collection_name or "").strip()
    if not _MILVUS_COLLECTION_NAME_RE.fullmatch(target):
        raise ValueError("invalid Milvus collection name")
    active = {str(name).strip() for name in active_collection_names if str(name).strip()}
    if target in active:
        raise ValueError("target is an active collection")
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")
    for row_number, child in enumerate(children, start=1):
        validate_huiji_child_for_milvus(child, row_number=row_number)

    if client_factory is None:
        client = MilvusClient(uri=cfg.vectorstore.uri, db_name=cfg.vectorstore.db_name)
    else:
        client = client_factory(cfg)
    if client.has_collection(target):
        raise FileExistsError(f"target collection already exists: {target}")
    ensure = collection_ensurer or ensure_huiji_collection
    ensure(client, target)

    embeddings = (embeddings_factory or get_embeddings)(cfg)
    total = len(children)
    inserted = 0
    for start in range(0, total, batch_size):
        batch = children[start:start + batch_size]
        texts = [str(child.get("search_text") or child.get("text") or "") for child in batch]
        vectors = embed_documents_with_retry(
            embeddings,
            texts,
            max_retries=max_retries,
            retry_seconds=retry_seconds,
            sleeper=sleeper,
            progress=progress,
        )
        if len(vectors) != len(batch):
            raise RuntimeError("embedding response count differs from input batch")
        rows = [huiji_child_to_milvus_row(child, vector) for child, vector in zip(batch, vectors)]
        if rows:
            client.insert(collection_name=target, data=rows)
            inserted += len(rows)
        if progress:
            progress({"event": "batch_done", "inserted": inserted, "total": total})
        if batch_delay_seconds > 0 and start + batch_size < total:
            if progress:
                progress({
                    "event": "batch_delay",
                    "delay_seconds": batch_delay_seconds,
                    "inserted": inserted,
                    "total": total,
                })
            sleeper(batch_delay_seconds)
    client.flush(collection_name=target)
    return inserted


def build_huiji_vectorstore(*_args: Any, **_kwargs: Any) -> None:
    raise RuntimeError(
        "unsafe_huiji_builder_disabled: use build_huiji_shadow_collection with an explicit new target"
    )


def load_vectorstore(cfg: Config) -> MilvusVectorstore:
    """Load the configured Milvus collection."""
    return _new_milvus(cfg)

