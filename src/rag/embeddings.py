"""SiliconFlow (OpenAI 兼容) embedding 封装。"""
from __future__ import annotations

from langchain_openai import OpenAIEmbeddings

from config.config import Config


def get_embeddings(cfg: Config) -> OpenAIEmbeddings:
    return OpenAIEmbeddings(
        model=cfg.embedding.model,
        openai_api_key=cfg.embedding.api_key,
        openai_api_base=cfg.embedding.base_url,
    )
