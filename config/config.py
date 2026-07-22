"""Central configuration loader for settings.yaml plus environment overrides."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

from src.huijiwiki.project_paths import resolve_project_local_path


@dataclass
class EmbeddingCfg:
    provider: str
    base_url: str
    model: str
    api_key: str


@dataclass
class LLMCfg:
    provider: str
    base_url: str
    model: str
    api_key: str
    thinking: str = "disabled"


@dataclass
class RAGCfg:
    chunk_size: int
    chunk_overlap: int
    top_k: int


@dataclass
class ServerCfg:
    backend_port: int
    streamlit_port: int
    gradio_port: int
    frontend_delay_seconds: int


@dataclass
class VectorstoreCfg:
    provider: str
    uri: str
    db_name: str
    collection_name: str


@dataclass
class AssetStorageCfg:
    provider: str
    endpoint: str
    public_base_url: str
    bucket_name: str
    secure: bool
    object_prefix: str
    access_key: str
    secret_key: str


@dataclass
class MysqlCfg:
    host: str
    port: int
    database: str
    user: str
    password: str
    charset: str


@dataclass
class WikiCfg:
    enabled: bool
    default_page_limit: int


@dataclass
class HuijiCfg:
    enabled: bool
    raw_root: Path
    processed_root: Path
    credential_file: Path
    build_version: str
    text_collection_name: str
    asset_caption_collection_name: str
    source_mode: str = "huiji_crawler"
    provenance_baseline: Path = Path("config/provenance/huiji-dev.v1.json")


@dataclass
class RerankerCfg:
    enabled: bool
    provider: str
    base_url: str
    model: str
    api_key: str


@dataclass
class RetrievalCfg:
    bm25_k: int
    dense_k: int
    rerank_k: int
    context_budget_chars: int
    sibling_window: int
    candidate_oversample: int = 4
    candidate_k_max: int = 100
    voice_page_size: int = 8
    voice_page_size_max: int = 20


@dataclass
class PathsCfg:
    project_root: Path
    vectorstore: Path
    frontend_html: Path


@dataclass
class Config:
    embedding: EmbeddingCfg
    llm: LLMCfg
    rag: RAGCfg
    server: ServerCfg
    vectorstore: VectorstoreCfg
    assets: AssetStorageCfg
    mysql: MysqlCfg
    wiki: WikiCfg
    huiji: HuijiCfg
    reranker: RerankerCfg
    retrieval: RetrievalCfg
    paths: PathsCfg


_config: Config | None = None


def _normalize_llm_thinking(value: object) -> str:
    mode = "disabled" if value is None else str(value).strip().lower()
    if mode not in {"enabled", "disabled"}:
        raise ValueError("llm.thinking must be 'enabled' or 'disabled'")
    return mode


def get_config() -> Config:
    """Load settings once and let environment variables override API keys."""
    global _config
    if _config is not None:
        return _config

    project_root = Path(__file__).resolve().parents[1]
    load_dotenv(project_root / ".env")

    with open(project_root / "config" / "settings.yaml", "r", encoding="utf-8") as f:
        raw: dict[str, Any] = yaml.safe_load(f)

    embedding_raw = raw["embedding"]
    llm_raw = raw["llm"]
    vectorstore_raw = raw["vectorstore"]
    assets_raw = raw["assets"]
    mysql_raw = raw.get("mysql", {})
    wiki_raw = raw.get("wiki", {})
    huiji_raw = raw.get("huiji", {})
    reranker_raw = raw.get("reranker", {})
    retrieval_raw = raw.get("retrieval", {})

    credential_env = os.environ.get("HUIJI_CONFIG_PATH")
    credential_file = resolve_project_local_path(
        credential_env
        or huiji_raw.get("credential_file")
        or ".local/huiji/credentials/config.dat",
        project_root=project_root,
        label="HUIJI_CONFIG_PATH" if credential_env else "huiji.credential_file",
    )

    cfg = Config(
        embedding=EmbeddingCfg(
            provider=embedding_raw["provider"],
            base_url=embedding_raw["base_url"],
            model=embedding_raw["model"],
            api_key=os.environ.get("SILICONFLOW_API_KEY") or embedding_raw.get("api_key", "") or "",
        ),
        llm=LLMCfg(
            provider=llm_raw["provider"],
            base_url=llm_raw["base_url"],
            model=llm_raw["model"],
            api_key=os.environ.get("DEEPSEEK_API_KEY") or llm_raw.get("api_key", "") or "",
            thinking=_normalize_llm_thinking(llm_raw.get("thinking", "disabled")),
        ),
        rag=RAGCfg(
            chunk_size=raw["rag"]["chunk_size"],
            chunk_overlap=raw["rag"]["chunk_overlap"],
            top_k=raw["rag"]["top_k"],
        ),
        server=ServerCfg(
            backend_port=raw["server"]["backend_port"],
            streamlit_port=raw["server"]["streamlit_port"],
            gradio_port=raw["server"]["gradio_port"],
            frontend_delay_seconds=raw["server"]["frontend_delay_seconds"],
        ),
        vectorstore=VectorstoreCfg(
            provider=vectorstore_raw["provider"],
            uri=vectorstore_raw["uri"],
            db_name=vectorstore_raw["db_name"],
            collection_name=vectorstore_raw["collection_name"],
        ),
        assets=AssetStorageCfg(
            provider=assets_raw["provider"],
            endpoint=assets_raw["endpoint"],
            public_base_url=assets_raw["public_base_url"],
            bucket_name=assets_raw["bucket_name"],
            secure=bool(assets_raw.get("secure", False)),
            object_prefix=assets_raw.get("object_prefix", "reverse1999"),
            access_key=(
                os.environ.get("MINIO_ACCESS_KEY")
                or os.environ.get("MINIO_ROOT_USER")
                or assets_raw.get("access_key", "")
                or ""
            ),
            secret_key=(
                os.environ.get("MINIO_SECRET_KEY")
                or os.environ.get("MINIO_ROOT_PASSWORD")
                or assets_raw.get("secret_key", "")
                or ""
            ),
        ),
        mysql=MysqlCfg(
            host=os.environ.get("MYSQL_HOST") or str(mysql_raw.get("host", "127.0.0.1")),
            port=int(os.environ.get("MYSQL_PORT") or mysql_raw.get("port", 3306)),
            database=os.environ.get("MYSQL_DATABASE") or str(mysql_raw.get("database", "reverse1999_wiki")),
            user=os.environ.get("MYSQL_USER") or str(mysql_raw.get("user", "root")),
            password=os.environ.get("MYSQL_PASSWORD") or str(mysql_raw.get("password", "")),
            charset=str(mysql_raw.get("charset", "utf8mb4")),
        ),
        wiki=WikiCfg(
            enabled=bool(wiki_raw.get("enabled", True)),
            default_page_limit=int(wiki_raw.get("default_page_limit", 30)),
        ),
        huiji=HuijiCfg(
            enabled=bool(huiji_raw.get("enabled", False)),
            source_mode=str(huiji_raw.get("source_mode", "")),
            raw_root=resolve_project_local_path(
                huiji_raw.get("raw_root", "data/huiji/res1999"),
                project_root=project_root,
                label="huiji.raw_root",
            ),
            processed_root=resolve_project_local_path(
                huiji_raw.get("processed_root", "data/processed/huiji"),
                project_root=project_root,
                label="huiji.processed_root",
            ),
            credential_file=credential_file,
            build_version=str(huiji_raw.get("build_version", "dev")),
            text_collection_name=str(huiji_raw.get("text_collection_name", "text_child_bge_m3_v3")),
            asset_caption_collection_name=str(
                huiji_raw.get("asset_caption_collection_name", "asset_caption_bge_m3_v1")
            ),
            provenance_baseline=resolve_project_local_path(
                huiji_raw.get(
                    "provenance_baseline",
                    "config/provenance/huiji-dev.v1.json",
                ),
                project_root=project_root,
                label="huiji.provenance_baseline",
            ),
        ),
        reranker=RerankerCfg(
            enabled=bool(reranker_raw.get("enabled", False)),
            provider=str(reranker_raw.get("provider", "siliconflow")),
            base_url=str(reranker_raw.get("base_url", embedding_raw.get("base_url", ""))),
            model=str(reranker_raw.get("model", "BAAI/bge-reranker-v2-m3")),
            api_key=os.environ.get("SILICONFLOW_API_KEY") or reranker_raw.get("api_key", "") or "",
        ),
        retrieval=RetrievalCfg(
            bm25_k=int(retrieval_raw.get("bm25_k", 40)),
            dense_k=int(retrieval_raw.get("dense_k", 40)),
            rerank_k=int(retrieval_raw.get("rerank_k", 60)),
            context_budget_chars=int(retrieval_raw.get("context_budget_chars", 9000)),
            sibling_window=int(retrieval_raw.get("sibling_window", 1)),
            candidate_oversample=int(retrieval_raw.get("candidate_oversample", 4)),
            candidate_k_max=int(retrieval_raw.get("candidate_k_max", 100)),
            voice_page_size=int(retrieval_raw.get("voice_page_size", 8)),
            voice_page_size_max=int(retrieval_raw.get("voice_page_size_max", 20)),
        ),
        paths=PathsCfg(
            project_root=project_root,
            vectorstore=project_root / "vectorstore",
            frontend_html=project_root / "frontend" / "html",
        ),
    )
    _config = cfg
    return cfg


def reset_config_for_test() -> None:
    """Reset singleton config for tests."""
    global _config
    _config = None
