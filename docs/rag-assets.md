# RAG 媒体资产

## 当前状态

正式 RAG 媒体数据只来自灰机 Wiki crawler snapshot。构建产物为 `data/processed/huiji/dev/media_assets.jsonl`，对象存储使用 `reverse1999-assets` bucket；浏览器只接收 HTTP URL，不接收本地文件路径。

当前数据源、构建、审计和 MinIO 契约以 [huiji-rag-runbook.md](huiji-rag-runbook.md) 与 [wiki-rag-contract-record.md](wiki-rag-contract-record.md) 为准。

## 旧链路

`scripts/build_assets.py` 对应的 Obsidian 资产链路已停用，命令会以 `legacy_obsidian_pipeline_disabled` 退出，不能写入正式 RAG 数据，也不作为回滚路径。旧的 `data/processed/assets.jsonl` 仅是历史格式，不是当前 source of truth。
