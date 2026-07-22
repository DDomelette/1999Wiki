# 1999Search

> CURRENT STATUS 2026-07-20: RAG 的唯一正式数据源是 Huiji crawler（`source_mode=huiji_crawler`）。活动 Milvus collection 是 `reverse1999_rag.text_child_bge_m3_v3`，Retriever/RAGChain 只会在 hash-pinned provenance 门禁通过后加载。旧命令已禁用且相关文件已移除，不能作为回滚路径。

1999Search 是《重返未来：1999》的本地 RAG 问答与 Wiki 展示项目。FastAPI 提供同步问答、SSE 流式问答、短期会话记忆、媒体绑定和按台词分页的语音接口；React 前端消费同一套 API。

## 当前数据流

```text
Huiji crawler snapshot
  -> parent_blocks / child_blocks / media_assets
  -> BM25 + BAAI/bge-m3 shadow collection
  -> hash-pinned provenance baseline
  -> Retriever + HuijiMediaRegistry
  -> RAGChain -> FastAPI -> frontend
```

运行时不会自动构建 artifacts、重建 Milvus 或切换 collection。Huiji artifacts、BM25、活动 collection 或 baseline 任一不一致时，后端保持 health-only 状态，RAG 接口返回 503。

## 主要目录

```text
1999Search/
|-- backend/                  FastAPI 应用和 SSE
|-- config/                   settings 与 provenance baseline
|-- data/huiji/res1999/       crawler snapshot
|-- data/processed/huiji/     parent/child/media/BM25 artifacts
|-- docs/                     架构、runbook、specs 与 plans
|-- frontend/react-app/       React + Vite 前端
|-- scripts/                  审计、验证、评估与 Huiji shadow 构建
|-- src/huiji_rag/            crawler 到 RAG artifacts 的处理链
|-- src/rag/                  planner、retriever、memory、citations、chain
`-- tests/                    单元、契约与验收测试
```

## 环境

1. 使用 `langchain` Conda 环境安装依赖。
2. 在 `.env` 中配置 embedding、LLM、MinIO 与 MySQL 凭据。
3. 启动 Milvus、MinIO 和 MySQL。
4. 保持 `config/settings.yaml` 中 `huiji.enabled: true` 与 `huiji.source_mode: huiji_crawler`。

```powershell
conda activate langchain
pip install -r requirements.txt
python scripts\verify_huiji_runtime.py
```

非交互 shell 可直接使用环境中的 Python 绝对路径或 `conda run -n langchain`。

## 启动

```powershell
.\start.ps1
# 或
.\start.bat
```

启动器和直接 uvicorn 启动都会先执行 provenance verifier。默认入口：

| 服务 | 地址 |
|---|---|
| Web / API | http://127.0.0.1:8000 |
| React dev | http://127.0.0.1:5173 |
| Milvus | 127.0.0.1:19600 |
| MinIO S3 / Console | 127.0.0.1:9002 / 127.0.0.1:9003 |
| MySQL | 127.0.0.1:3307 |

手动启动后端：

```powershell
python scripts\verify_huiji_runtime.py
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

React 开发服务器：

```powershell
cd frontend\react-app
npm install
npm run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

## 索引维护

只允许创建显式命名且不存在的 shadow collection。构建命令不会激活、覆盖或删除 collection：

```powershell
python scripts\build_huiji_index.py `
  --collection-name text_child_bge_m3_shadow_<unique-id> `
  --run-dir eval\huiji_provenance\<run-id>\shadow-build
```

活动 collection 的切换必须经过独立审计、baseline 更新和明确审批。不要通过删除 `vectorstore/`、删除活动 collection 或恢复退休数据链路来修复索引。

完整操作流程见 [Huiji RAG runbook](docs/huiji-rag-runbook.md)，系统结构见 [architecture](docs/architecture.md)。
