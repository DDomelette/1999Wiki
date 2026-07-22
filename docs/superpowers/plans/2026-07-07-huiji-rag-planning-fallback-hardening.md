# 灰机 RAG 闭环恢复与问答链路硬化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Per current user instruction, do not stage, commit, reset, or clean git state while executing this plan.

**Goal:** 恢复并硬化灰机数据驱动的 RAG 问答闭环，使角色介绍、技能、单品、立绘、语音、视频等查询能稳定经过 QueryPlan、混合召回、实体包扩展、媒体挂载、API/SSE 和聊天前端输出。

**Architecture:** 第一阶段保留当前可用的 `text_child_bge_m3_v3` 作为运行和评估基线，先修运行时链路与评估门禁；只有评估证明父子块、媒体清单或向量库结构本身存在不可绕过的问题时，才进入第二阶段重建。RAG 侧固定 MinIO 共享协议，Wiki 已暂停，不作为当前并行约束；Obsidian 接口可保留但不得进入当前问答系统。

**Tech Stack:** Python, FastAPI, Pydantic, Milvus, local BM25, weighted RRF, SiliconFlow `BAAI/bge-m3`, optional SiliconFlow `BAAI/bge-reranker-v2-m3`, MinIO, React, TypeScript, Vitest, pytest.

## Global Constraints

- 需求来源：`D:\PycharmProjects\nlp\LangChain\1999Search\docs\superpowers\specs\2026-07-07-huiji-rag-closed-loop-recovery-design.md`。
- 当前优先级：RAG 问答链路优先；Wiki 页面恢复已暂停，不作为本轮并行约束。
- 当前运行基线：保留并评估 `text_child_bge_m3_v3`，不得在第一阶段删除或覆盖。
- 条件重建目标：若必须重建 Milvus，目标 collection 使用 `text_child_bge_m3_v1`；如旧 `v1` 存在，可删除后重建。
- MinIO 协议由 RAG 固定：`bucket=reverse1999-assets`，`public_base_url=http://127.0.0.1:9002`，`object_prefix=reverse1999`。
- 浏览器只接收 HTTP URL，不允许 API 或前端 payload 泄露 `D:\`、`C:\` 或本地相对资源路径。
- 当前主数据源只允许灰机爬虫处理产物：`data/processed/huiji/{build_version}`；Obsidian 数据不得进入 BM25、Milvus、媒体挂载、RAG API 或聊天前端。
- 不恢复旧 `src/huiji_rag/builder.py` 文件名作为 P0；如需异常实体记录，应落在当前实际构建入口或处理模块。
- 同名不同后缀媒体去重是 P1，不作为第一阶段硬验收；第一阶段只要求媒体跟随正确最终 sources，且不泄露本地路径。
- 不执行 git stage、commit、reset、checkout 或清理工作树。

---

## 1. 目标范围

### 1.1 本轮必须完成的 specs 编号

- `DATA-P0-01` 到 `DATA-P0-06`
- `BLOCK-P0-01` 到 `BLOCK-P0-06`
- `QUERY-P0-01` 到 `QUERY-P0-07`
- `RETR-P0-01` 到 `RETR-P0-07`
- `MEDIA-P0-01` 到 `MEDIA-P0-08`
- `API-P0-01` 到 `API-P0-06`
- `CHAT-P0-01` 到 `CHAT-P0-07`
- `EVAL-P0-01` 到 `EVAL-P0-05`
- `MILVUS-P0-01` 到 `MILVUS-P0-05`
- `BOUNDARY-P0-01` 到 `BOUNDARY-P0-05`

### 1.2 本轮不做

- 不训练 BERT/RoBERTa/MacBERT intent classifier，只在文档中保留未来可插拔位置。
- 不构建图片摘要向量库 `asset_caption_bge_m3_v1`。
- 不把媒体 BM25 文件名检索作为主要图片召回路线。
- 不清空 MinIO，不重爬灰机原始数据。
- 不恢复 Wiki 页面模块，不修改 Wiki 页面组件。
- 不把旧 Obsidian `documents.jsonl` 或旧 `chunks_bge_m3_v1` 作为当前 RAG 主链路。

## 2. 文件结构

### Backend / RAG

- Modify: `D:\PycharmProjects\nlp\LangChain\1999Search\src\rag\query_plan.py`  
  固化 LLM-first QueryPlan、降级状态、三路 query、实体词典 fallback。
- Modify: `D:\PycharmProjects\nlp\LangChain\1999Search\src\rag\entity_lexicon.py`  
  从灰机 parent blocks 建立实体、英文名、别名和最长匹配能力。
- Modify: `D:\PycharmProjects\nlp\LangChain\1999Search\src\rag\reranker.py`  
  补齐 intent query keywords 和稳健 Intent Router 二次确认。
- Modify: `D:\PycharmProjects\nlp\LangChain\1999Search\src\rag\retriever.py`  
  保证 structured exact + BM25 + dense、RRF、reranker、ancestor/sibling expansion 顺序和 debug 输出。
- Modify: `D:\PycharmProjects\nlp\LangChain\1999Search\src\rag\hybrid.py`  
  保持 weighted RRF，不把跨量纲原始分数直接相加。
- Modify: `D:\PycharmProjects\nlp\LangChain\1999Search\src\rag\layered_expansion.py`  
  保证实体包、父块扩展、同级扩展、预算裁剪和 omitted actions。
- Modify: `D:\PycharmProjects\nlp\LangChain\1999Search\src\rag\packet_policy.py`  
  固定 intro、skill、item、voice、video 等 section policy。
- Modify: `D:\PycharmProjects\nlp\LangChain\1999Search\src\rag\chain.py`  
  汇总 planning diagnostics、sources、media、actions、panels，并禁止 Obsidian 进入灰机启用链路。
- Modify: `D:\PycharmProjects\nlp\LangChain\1999Search\src\assets\huiji_registry.py`  
  媒体只跟随最终 sources 的 child_id/parent_id，voice/video 分 panel 输出。
- Modify: `D:\PycharmProjects\nlp\LangChain\1999Search\src\huiji_rag\media.py`  
  校验媒体类型、attach_policy、panel_group、HTTP URL。
- Modify if rebuild gate opens: `D:\PycharmProjects\nlp\LangChain\1999Search\src\huiji_rag\io.py`  
  Reuse `build_paths`, `iter_jsonl`, `write_jsonl`, and `write_json` as the artifact IO contract.
- Modify if rebuild gate opens: `D:\PycharmProjects\nlp\LangChain\1999Search\src\huiji_rag\text.py`  
  Reuse text cleanup helpers for parent/child text generation.
- Modify if rebuild gate opens: `D:\PycharmProjects\nlp\LangChain\1999Search\src\huiji_rag\media.py`  
  Reuse media classification, attach policy, panel grouping, and HTTP URL generation.
- Create if rebuild gate opens: `D:\PycharmProjects\nlp\LangChain\1999Search\scripts\build_huiji_corpus.py`  
  Rebuild parent blocks, child blocks, media assets, BM25 indexes, build report, and excluded entity report.
- Create if rebuild gate opens: `D:\PycharmProjects\nlp\LangChain\1999Search\scripts\build_huiji_index.py`  
  Rebuild Milvus vectors for the selected text child collection.
- Modify: `D:\PycharmProjects\nlp\LangChain\1999Search\backend\main.py`
- Modify: `D:\PycharmProjects\nlp\LangChain\1999Search\backend\sse.py`
- Modify backend schema module if present: `D:\PycharmProjects\nlp\LangChain\1999Search\backend\schemas.py`

### Frontend / Chat Only

- Modify: `D:\PycharmProjects\nlp\LangChain\1999Search\frontend\react-app\src\types\index.ts`
- Modify: `D:\PycharmProjects\nlp\LangChain\1999Search\frontend\react-app\src\api\sse.ts`
- Modify: `D:\PycharmProjects\nlp\LangChain\1999Search\frontend\react-app\src\store\chatStore.ts`
- Modify: `D:\PycharmProjects\nlp\LangChain\1999Search\frontend\react-app\src\components\chat\ChatInput.tsx`
- Modify: `D:\PycharmProjects\nlp\LangChain\1999Search\frontend\react-app\src\components\chat\MessageBubble.tsx`
- Modify: `D:\PycharmProjects\nlp\LangChain\1999Search\frontend\react-app\src\components\chat\MessageActions.tsx`
- Modify: `D:\PycharmProjects\nlp\LangChain\1999Search\frontend\react-app\src\components\chat\MessageAssets.tsx`
- Modify/Create: `D:\PycharmProjects\nlp\LangChain\1999Search\frontend\react-app\src\components\chat\VoicePanel.tsx`
- Modify/Create: `D:\PycharmProjects\nlp\LangChain\1999Search\frontend\react-app\src\components\chat\VideoPanel.tsx`

### Tests / Evaluation

- Modify: `D:\PycharmProjects\nlp\LangChain\1999Search\tests\test_query_plan.py`
- Modify: `D:\PycharmProjects\nlp\LangChain\1999Search\tests\test_entity_lexicon.py`
- Modify: `D:\PycharmProjects\nlp\LangChain\1999Search\tests\test_reranker.py`
- Modify: `D:\PycharmProjects\nlp\LangChain\1999Search\tests\test_retriever.py`
- Modify: `D:\PycharmProjects\nlp\LangChain\1999Search\tests\test_hybrid_retriever.py`
- Modify: `D:\PycharmProjects\nlp\LangChain\1999Search\tests\test_chain_assets.py`
- Modify: `D:\PycharmProjects\nlp\LangChain\1999Search\tests\test_sse.py`
- Create/Modify: `D:\PycharmProjects\nlp\LangChain\1999Search\tests\test_huiji_media_registry.py`
- Create/Modify if data-layer rebuild is triggered: `D:\PycharmProjects\nlp\LangChain\1999Search\tests\test_huiji_build_exclusions.py`
- Create/Modify: `D:\PycharmProjects\nlp\LangChain\1999Search\eval\queries_core.jsonl`
- Create/Modify: `D:\PycharmProjects\nlp\LangChain\1999Search\scripts\evaluate_huiji_rag.py`
- Modify/Create frontend tests under `D:\PycharmProjects\nlp\LangChain\1999Search\frontend\react-app\src\components\chat\*.test.tsx`

## 3. 强制验收门槛

| Spec | 验收方式 | 失败表现 |
| --- | --- | --- |
| `DATA-P0-*` | 检查 RAG runtime 只读取 `data/processed/huiji/dev` 和 MinIO HTTP URL | 读取旧 Obsidian documents、payload 出现本地路径、`???` 无法追踪 |
| `BLOCK-P0-*` | `intro` 查询返回实体包多 section，技能一二三星聚合在同一技能子块，省略项生成 actions | 介绍只给极薄 profile，技能星级散落，缺失项不可继续追问 |
| `QUERY-P0-*` | QueryPlan 单测覆盖 LLM 成功和各类 fallback，输出 dense/sparse/media query | LLM 被静默绕过，实体提取带“的技能”等噪声，fallback 无提示 |
| `RETR-P0-*` | Retriever 单测和真实 eval 验证 structured exact 优先、RRF、reranker 在 expansion 前 | 十四行诗被金蜜儿、空脑袋、尤提姆等跨实体结果抢占 |
| `MEDIA-P0-*` | Registry/chain 测试验证媒体只随最终 sources，voice/video 只在明确 intent 下返回 panel | 图片来自错误实体，非语音问题暴露大量音频，本地路径泄露 |
| `API-P0-*` | SSE/API 测试验证 answer、sources、media、actions、planning diagnostics | 前端无法知道降级原因，sources 缺 child/parent，media 无 URL |
| `CHAT-P0-*` | Vitest/手动 UI 验证按钮、omitted actions、voice/video panel、Markdown 兼容 | 按钮联动错误，临时按钮和常驻按钮混淆，语音无独立面板 |
| `EVAL-P0-*` | `scripts/evaluate_huiji_rag.py` 跑核心 query，输出 machine-readable report | 只能靠截图判断效果，无法定位 entity/intent/retrieval/media 哪层失败 |
| `MILVUS-P0-*` | 第一阶段不删 `v3`；如重建只删/建 `v1`，并对比报告 | `v3` 被覆盖，较新可参考 collection 消失 |
| `BOUNDARY-P0-*` | 测试和 grep 检查当前链路不读 Obsidian，不执行 Wiki 恢复 | Obsidian/Wiki 重新进入问答链路 |

## 4. 执行步骤

### Task 1: 固化 QueryPlan 和实体词典契约

**Files:**
- Modify: `D:\PycharmProjects\nlp\LangChain\1999Search\src\rag\query_plan.py`
- Modify: `D:\PycharmProjects\nlp\LangChain\1999Search\src\rag\entity_lexicon.py`
- Modify: `D:\PycharmProjects\nlp\LangChain\1999Search\tests\test_query_plan.py`
- Modify: `D:\PycharmProjects\nlp\LangChain\1999Search\tests\test_entity_lexicon.py`

**Interfaces:**
- Consumes: `EntityLexicon.match(query: str) -> EntityMatch | None`
- Produces: `QueryPlanner.plan(query: str) -> QueryPlan`
- Produces fields: `planning_status`, `planning_warning`, `planning_error`, `entity`, `intent`, `entity_type`, `dense_query`, `sparse_query`, `media_query`, `packet_policy`, `media_intent`, `route_options`

- [ ] **Step 1: Add failing tests for LLM-first planning**

Add tests that use a fake LLM returning valid JSON for `介绍一下十四行诗` and assert:

```python
assert plan.planning_status == "llm"
assert plan.entity == "十四行诗"
assert plan.intent == "intro"
assert plan.entity_type == "character"
assert plan.packet_policy in {"intro", "intro_full", "entity_packet"}
assert plan.dense_query
assert plan.sparse_query
assert plan.media_query is not None
```

Run:

```powershell
D:\Anaconda32024\envs\LangChain\python.exe -m pytest tests\test_query_plan.py -q
```

Expected before implementation: at least one new assertion fails if LLM result is overridden or diagnostics are missing.

- [ ] **Step 2: Add fallback status tests**

Cover these statuses with fake LLM objects or missing LLM:

```text
fallback_no_llm
fallback_timeout
fallback_api_error
fallback_parse_error
fallback_schema_error
```

Each assertion must require:

```python
assert plan.planning_status == expected_status
assert plan.planning_warning
assert plan.planning_error
```

- [ ] **Step 3: Add entity normalization tests**

Use real or fixture lexicon records and cover:

```text
Sonetto 的技能是什么 -> 十四行诗 / skill
玛蒂尔达的技能有什么 -> 玛蒂尔达 / skill
看一下玛蒂尔达的立绘 -> 玛蒂尔达 / media / image
播放玛蒂尔达语音 -> 玛蒂尔达 / voice / audio
```

The entity must not include suffixes such as `的技能`、`的立绘`、`语音`。

- [ ] **Step 4: Implement minimal code**

Ensure `QueryPlanner` only falls back when LLM is absent, times out, raises API error, returns invalid JSON, or fails schema validation. Ensure fallback calls `EntityLexicon.match()` before regex slicing.

- [ ] **Step 5: Verify**

Run:

```powershell
D:\Anaconda32024\envs\LangChain\python.exe -m pytest tests\test_query_plan.py tests\test_entity_lexicon.py -q
```

Expected: all tests pass.

### Task 2: 补齐稳健 Intent Router

**Files:**
- Modify: `D:\PycharmProjects\nlp\LangChain\1999Search\src\rag\reranker.py`
- Modify: `D:\PycharmProjects\nlp\LangChain\1999Search\tests\test_reranker.py`

**Interfaces:**
- Consumes: `QueryPlan.intent`, `QueryPlan.sparse_query`, candidate `heading_path` / `section_kind`
- Produces: corrected route intent for `general` or low-confidence planning cases

- [ ] **Step 1: Add intent keyword coverage test**

Assert `INTENT_QUERY_KEYWORDS` covers exactly these primary queryable intents:

```python
required = {
    "intro", "profile_fact", "skill", "item", "culture", "voice",
    "media", "video", "psychube", "story", "general_game", "meta_question",
    "profile", "lore",
}
assert required <= set(INTENT_QUERY_KEYWORDS)
```

- [ ] **Step 2: Add general correction tests**

For a `QueryPlan(intent="general")`, create candidate rows whose headings/section kinds include `skills`, `items`, `voice`, `media`, `video`, `story`, `psychube`. Assert queries such as `她的技能是什么`、`介绍她的单品`、`播放语音`、`看立绘`、`看视频` correct to the expected intent.

- [ ] **Step 3: Implement minimal code**

Keep `INTENT_SECTION_HINTS` for heading matching and `INTENT_QUERY_KEYWORDS` for user-query matching. The robust router should not mutate a confident non-general intent unless current code already has an explicit confidence gate.

- [ ] **Step 4: Verify**

Run:

```powershell
D:\Anaconda32024\envs\LangChain\python.exe -m pytest tests\test_reranker.py -q
```

Expected: all tests pass.

### Task 3: 稳定混合召回、实体包和 omitted actions

**Files:**
- Modify: `D:\PycharmProjects\nlp\LangChain\1999Search\src\rag\retriever.py`
- Modify: `D:\PycharmProjects\nlp\LangChain\1999Search\src\rag\hybrid.py`
- Modify: `D:\PycharmProjects\nlp\LangChain\1999Search\src\rag\layered_expansion.py`
- Modify: `D:\PycharmProjects\nlp\LangChain\1999Search\src\rag\packet_policy.py`
- Modify: `D:\PycharmProjects\nlp\LangChain\1999Search\tests\test_retriever.py`
- Modify: `D:\PycharmProjects\nlp\LangChain\1999Search\tests\test_hybrid_retriever.py`

**Interfaces:**
- Consumes: `QueryPlan`
- Produces: ranked child rows, expanded source rows, `last_route_debug`, `last_expansion_debug`, `last_omitted_actions`

- [ ] **Step 1: Add retrieval-order test**

Create a fixture where structured exact for `十四行诗` conflicts with dense/BM25 rows from `金蜜儿`、`空脑袋`、`尤提姆`. Assert final top sources remain within the primary entity when `plan.entity == "十四行诗"`.

- [ ] **Step 2: Add intro entity-packet test**

For `QueryPlan(entity="十四行诗", intent="intro")`, assert selected sources include more than one section kind, prioritizing profile/dossier/culture/skills/items/media according to packet policy. Assert omitted sections become actions when they exceed budget.

- [ ] **Step 3: Add special-intent tests**

Assert `skill` prioritizes skills, `item` prioritizes items, `voice` prioritizes voice, and `video` prioritizes video/media-specific rows. These tests must fail if `intro/profile/story` dominates a special intent.

- [ ] **Step 4: Confirm reranker placement**

Add or keep a test that records call order:

```text
merge candidates -> reranker -> ancestor expansion -> bounded sibling expansion -> budget pruning
```

- [ ] **Step 5: Implement minimal runtime corrections**

Keep retrieval order as:

```text
structured exact + BM25 + dense -> merge/dedupe -> weighted RRF -> optional reranker -> ancestor expansion -> bounded sibling expansion -> rules/budget -> sources/actions
```

- [ ] **Step 6: Verify**

Run:

```powershell
D:\Anaconda32024\envs\LangChain\python.exe -m pytest tests\test_retriever.py tests\test_hybrid_retriever.py -q
```

Expected: all tests pass.

### Task 4: 媒体挂载、MinIO URL 和 panel 输出

**Files:**
- Modify: `D:\PycharmProjects\nlp\LangChain\1999Search\src\assets\huiji_registry.py`
- Modify: `D:\PycharmProjects\nlp\LangChain\1999Search\src\huiji_rag\media.py`
- Modify: `D:\PycharmProjects\nlp\LangChain\1999Search\src\rag\chain.py`
- Modify: `D:\PycharmProjects\nlp\LangChain\1999Search\tests\test_chain_assets.py`
- Create/Modify: `D:\PycharmProjects\nlp\LangChain\1999Search\tests\test_huiji_media_registry.py`

**Interfaces:**
- Consumes: final `sources` containing `child_id` / `parent_id`
- Produces: `media`, `assets`, `media_panels`, with HTTP URLs only

- [ ] **Step 1: Add source-bound media test**

Build media fixtures where a wrong entity has a filename that lexically matches the query. Assert `HuijiMediaRegistry.find_for_retrieval()` only returns media attached to final source `child_id` or `parent_id`.

- [ ] **Step 2: Add local-path leakage test**

Assert every returned media URL starts with `http://` or `https://`, and no returned field contains these patterns:

```text
D:\
C:\
file://
..\
```

- [ ] **Step 3: Add voice/video gating tests**

Assert intro/skill/profile answers do not return bulk audio/video. Assert `voice` intent returns `media_panels.voice` data and `video` intent returns `media_panels.video` data.

- [ ] **Step 4: Implement minimal corrections**

Use final source IDs as the primary join key. Keep existing return-stage duplicate protection if already present, but do not make canonical image dedupe a blocking requirement in this task.

- [ ] **Step 5: Verify MinIO sample access**

Run a small script or test that picks several returned URLs and verifies HTTP reachability. If MinIO is offline, the test may be marked integration/manual, but the plan execution must record that MinIO was unavailable rather than silently passing.

Suggested manual command:

```powershell
Invoke-WebRequest -UseBasicParsing -Method Head "http://127.0.0.1:9002/reverse1999-assets/" -TimeoutSec 5
```

- [ ] **Step 6: Verify tests**

Run:

```powershell
D:\Anaconda32024\envs\LangChain\python.exe -m pytest tests\test_chain_assets.py tests\test_huiji_media_registry.py -q
```

Expected: all tests pass; MinIO availability is recorded separately if not running.

### Task 5: API/SSE 输出 planning diagnostics 和 actions

**Files:**
- Modify: `D:\PycharmProjects\nlp\LangChain\1999Search\src\rag\chain.py`
- Modify: `D:\PycharmProjects\nlp\LangChain\1999Search\backend\main.py`
- Modify: `D:\PycharmProjects\nlp\LangChain\1999Search\backend\sse.py`
- Modify backend schema module if present: `D:\PycharmProjects\nlp\LangChain\1999Search\backend\schemas.py`
- Modify: `D:\PycharmProjects\nlp\LangChain\1999Search\tests\test_sse.py`

**Interfaces:**
- Produces API/SSE metadata fields: `route`, `planning_status`, `planning_warning`, `planning_error`, `omitted_actions`, `failure_actions`, `media_panels`

- [ ] **Step 1: Add SSE meta test**

Assert a streamed response contains planning diagnostics and action fields in metadata, not only in server logs.

- [ ] **Step 2: Add failure-actions test**

When no reliable sources exist, assert failure actions are exactly:

```text
扩大范围重新搜索
使用自由补充重答
```

When reliable sources exist, assert failure actions are empty or absent.

- [ ] **Step 3: Add source-debug field test**

Assert each source retains enough fields to debug retrieval, such as entity/title plus child or parent identifiers when available.

- [ ] **Step 4: Implement minimal code**

Map `QueryPlan` diagnostics from `RAGChain.retrieve()` / `RAGChain.ask()` into the API/SSE payload. Do not expose internal secrets, API keys, local paths, or full prompts.

- [ ] **Step 5: Verify**

Run:

```powershell
D:\Anaconda32024\envs\LangChain\python.exe -m pytest tests\test_sse.py tests\test_chain_assets.py -q
```

Expected: all tests pass.

### Task 6: 聊天前端动作按钮、消息分层和 voice/video panel

**Files:**
- Modify: `D:\PycharmProjects\nlp\LangChain\1999Search\frontend\react-app\src\types\index.ts`
- Modify: `D:\PycharmProjects\nlp\LangChain\1999Search\frontend\react-app\src\api\sse.ts`
- Modify: `D:\PycharmProjects\nlp\LangChain\1999Search\frontend\react-app\src\store\chatStore.ts`
- Modify: `D:\PycharmProjects\nlp\LangChain\1999Search\frontend\react-app\src\components\chat\ChatInput.tsx`
- Modify: `D:\PycharmProjects\nlp\LangChain\1999Search\frontend\react-app\src\components\chat\MessageBubble.tsx`
- Modify: `D:\PycharmProjects\nlp\LangChain\1999Search\frontend\react-app\src\components\chat\MessageActions.tsx`
- Modify: `D:\PycharmProjects\nlp\LangChain\1999Search\frontend\react-app\src\components\chat\MessageAssets.tsx`
- Modify/Create: `D:\PycharmProjects\nlp\LangChain\1999Search\frontend\react-app\src\components\chat\VoicePanel.tsx`
- Modify/Create: `D:\PycharmProjects\nlp\LangChain\1999Search\frontend\react-app\src\components\chat\VideoPanel.tsx`
- Modify/Create frontend tests under `D:\PycharmProjects\nlp\LangChain\1999Search\frontend\react-app\src\components\chat\*.test.tsx`

**Interfaces:**
- Consumes SSE metadata from Task 5
- Produces UI for regular mode buttons, temporary failure buttons, omitted action buttons, image grid, voice panel, video panel

- [ ] **Step 1: Add type coverage**

Extend TypeScript types to include planning diagnostics and any missing source identifiers (`child_id`, `parent_id`, `section_kind`) if the backend emits them.

- [ ] **Step 2: Add ChatInput test**

Assert default state has both persistent mode buttons disabled. Assert clicking `扩大检索` does not automatically toggle `自由补充`, and clicking `自由补充` does not automatically toggle `扩大检索`.

- [ ] **Step 3: Add MessageActions test**

Assert temporary failure buttons use labels:

```text
扩大范围重新搜索
使用自由补充重答
```

Assert their CSS class or data attribute differs from persistent mode buttons, such as `data-action-kind="recovery"`.

- [ ] **Step 4: Add MessageBubble structure test**

Assert message shell, body text, media, actions, voice panel, and video panel are separate DOM regions, each with stable class or `data-animation-slot` attributes. The layout must not depend on text being Markdown.

- [ ] **Step 5: Add VoicePanel and VideoPanel tests**

Voice panel must render playable rows with a separate background progress layer. Video panel must render independently from the image grid.

- [ ] **Step 6: Implement minimal UI code**

Keep Markdown rendering compatible, not mandatory. Render plain text with sensible paragraphs and line breaks when no Markdown syntax is present.

- [ ] **Step 7: Verify frontend tests**

Run:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search\frontend\react-app
npm test -- --run
```

Expected: all tests pass.

### Task 7: 建立核心 eval 闭环

**Files:**
- Create/Modify: `D:\PycharmProjects\nlp\LangChain\1999Search\eval\queries_core.jsonl`
- Create/Modify: `D:\PycharmProjects\nlp\LangChain\1999Search\scripts\evaluate_huiji_rag.py`

**Interfaces:**
- Consumes real config, processed artifacts, current Milvus collection, MinIO registry data
- Produces machine-readable report containing query, planning, sources, media, violations, pass/fail

- [ ] **Step 1: Create core query set**

Create JSONL records with at least these cases:

```json
{"id":"intro_sonetto","query":"介绍一下十四行诗","expected_entity":"十四行诗","expected_intent":"intro","required_sections":["profile","dossier"],"forbid_media_types":["voice","video"]}
{"id":"skill_sonetto","query":"十四行诗的技能是什么","expected_entity":"十四行诗","expected_intent":"skill","required_sections":["skill"],"forbid_media_types":["voice","video"]}
{"id":"item_sonetto","query":"介绍一下十四行诗的单品","expected_entity":"十四行诗","expected_intent":"item","required_sections":["item"],"forbid_media_types":["voice","video"]}
{"id":"image_sonetto","query":"看一下十四行诗的立绘","expected_entity":"十四行诗","expected_intent":"media","required_media_types":["image"]}
{"id":"voice_sonetto","query":"播放十四行诗语音","expected_entity":"十四行诗","expected_intent":"voice","required_media_types":["voice"]}
{"id":"intro_matilda","query":"介绍一下玛蒂尔达","expected_entity":"玛蒂尔达","expected_intent":"intro","forbid_media_types":["voice","video"]}
{"id":"skill_matilda","query":"玛蒂尔达的技能有什么","expected_entity":"玛蒂尔达","expected_intent":"skill","required_sections":["skill"]}
{"id":"image_matilda","query":"看一下玛蒂尔达的图片","expected_entity":"玛蒂尔达","expected_intent":"media","required_media_types":["image"]}
{"id":"general_game","query":"1999是什么游戏","expected_intent":"general_game","allow_no_entity":true}
```

- [ ] **Step 2: Implement evaluator output schema**

Each result row must include:

```json
{
  "id": "intro_sonetto",
  "query": "介绍一下十四行诗",
  "planning_status": "llm",
  "entity": "十四行诗",
  "intent": "intro",
  "dense_query": "...",
  "sparse_query": "...",
  "top_sources": [],
  "media_count": 0,
  "media_types": [],
  "omitted_actions": [],
  "failure_actions": [],
  "violations": [],
  "passed": true
}
```

- [ ] **Step 3: Implement violation checks**

Check at least:

```text
wrong_entity
wrong_intent
missing_required_section
missing_required_media
forbidden_media_type
local_path_leak
unknown_entity_leak
voice_auto_leak
no_sources_without_failure_actions
```

- [ ] **Step 4: Run eval on current v3**

Run:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search
D:\Anaconda32024\envs\LangChain\python.exe scripts\evaluate_huiji_rag.py --queries eval\queries_core.jsonl --output eval\latest_report.jsonl
```

Expected: report is written and failures identify a layer: planning, retrieval, media, API, or data artifact.

### Task 8: Obsidian/Wiki boundary verification

**Files:**
- Modify tests only unless runtime violates boundary: `D:\PycharmProjects\nlp\LangChain\1999Search\tests\*.py`
- Modify code only if tests prove leakage: `D:\PycharmProjects\nlp\LangChain\1999Search\src\rag\*.py`

**Interfaces:**
- Consumes config with `huiji.enabled == true`
- Produces assurance that active RAG does not read Obsidian artifacts

- [ ] **Step 1: Add boundary test**

Patch or fixture old `data/processed/documents.jsonl` with a unique fake string. Assert a Huiji-enabled query never returns that fake string in context, answer sources, media, or debug.

- [ ] **Step 2: Add path grep verification**

Run:

```powershell
rg "data/processed/documents|Obsidian|obsidian|chunks_bge_m3_v1" D:\PycharmProjects\nlp\LangChain\1999Search\src D:\PycharmProjects\nlp\LangChain\1999Search\backend
```

Expected: any matches are either legacy fallback code gated off when Huiji is enabled, comments/docs, or tests. Active Huiji runtime must not depend on them.

- [ ] **Step 3: Verify**

Run:

```powershell
D:\Anaconda32024\envs\LangChain\python.exe -m pytest tests -q
```

If full test suite is too broad due unrelated existing failures, record unrelated failures and still run the focused RAG tests listed in Section 5.

### Task 9: Conditional data-layer rebuild gate

**Files:**
- Modify only if Task 7 proves current artifacts are structurally wrong: `D:\PycharmProjects\nlp\LangChain\1999Search\src\huiji_rag\io.py`
- Modify only if Task 7 proves current artifacts are structurally wrong: `D:\PycharmProjects\nlp\LangChain\1999Search\src\huiji_rag\text.py`
- Modify only if Task 7 proves current artifacts are structurally wrong: `D:\PycharmProjects\nlp\LangChain\1999Search\src\huiji_rag\media.py`
- Create if missing and rebuild gate opens: `D:\PycharmProjects\nlp\LangChain\1999Search\scripts\build_huiji_corpus.py`
- Create if missing and rebuild gate opens: `D:\PycharmProjects\nlp\LangChain\1999Search\scripts\build_huiji_index.py`
- Modify only if switching target collection: `D:\PycharmProjects\nlp\LangChain\1999Search\config\settings.yaml`
- Create/Modify only if rebuild gate opens: `D:\PycharmProjects\nlp\LangChain\1999Search\tests\test_huiji_build_exclusions.py`

**Interfaces:**
- Consumes raw Huiji data and current processed artifacts
- Produces rebuilt `data/processed/huiji/{build_version}` and Milvus `text_child_bge_m3_v1`

- [ ] **Step 1: Do not start this task unless eval proves runtime-only fixes are insufficient**

Valid triggers:

```text
child_blocks lack required parent_id/child_id/section_kind fields
skills cannot represent three star levels in one skill child
voice/media assets cannot be joined by child_id/parent_id
entity_name anomalies such as ??? are present in processed artifacts and cannot be filtered safely at runtime
Milvus schema mismatches current child block schema
```

- [ ] **Step 2: Preserve v3 and target v1 only**

If rebuild is triggered, delete only `text_child_bge_m3_v1` if it exists. Do not delete `text_child_bge_m3_v3`.

- [ ] **Step 3: Rebuild processed artifacts**

Run only after code changes and tests for corpus build pass:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search
D:\Anaconda32024\envs\LangChain\python.exe scripts\build_huiji_corpus.py
```

Expected output: parent blocks, child blocks, media assets, BM25 indexes, build report, and excluded entities report are regenerated.

- [ ] **Step 4: Rebuild Milvus v1**

Run after setting the target collection to `text_child_bge_m3_v1`. If `build_huiji_index.py` has no collection argument, first set both `vectorstore.collection_name` and `huiji.text_collection_name` in `config/settings.yaml` to `text_child_bge_m3_v1`; if the script implements `--collection-name`, pass `--collection-name text_child_bge_m3_v1` instead:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search
D:\Anaconda32024\envs\LangChain\python.exe scripts\build_huiji_index.py
```

Expected output: vectors inserted into `text_child_bge_m3_v1` with no varchar overflow, no silent truncation, and no unhandled rate-limit failure.

- [ ] **Step 5: Compare v1 against v3**

Run Task 7 eval on both v3 and v1 and compare violations. Switch runtime config to `text_child_bge_m3_v1` only if v1 is equal or better on core eval and preserves media behavior.

## 5. Focused Verification Commands

Run these after the relevant tasks:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search
D:\Anaconda32024\envs\LangChain\python.exe -m pytest tests\test_query_plan.py tests\test_entity_lexicon.py -q
D:\Anaconda32024\envs\LangChain\python.exe -m pytest tests\test_reranker.py -q
D:\Anaconda32024\envs\LangChain\python.exe -m pytest tests\test_retriever.py tests\test_hybrid_retriever.py -q
D:\Anaconda32024\envs\LangChain\python.exe -m pytest tests\test_chain_assets.py tests\test_huiji_media_registry.py tests\test_sse.py -q
D:\Anaconda32024\envs\LangChain\python.exe scripts\evaluate_huiji_rag.py --queries eval\queries_core.jsonl --output eval\latest_report.jsonl
```

Frontend:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search\frontend\react-app
npm test -- --run
```

Optional manual browser check after backend/frontend are running:

```text
1. 介绍一下十四行诗
2. 十四行诗的技能是什么
3. 介绍一下十四行诗的单品
4. 看一下十四行诗的立绘
5. 播放十四行诗语音
6. 介绍一下玛蒂尔达
```

For each response, inspect visible answer, sources, media cards/panels, omitted actions, and whether any fallback warning is shown.

## 6. Optional P1 Work After P0 Passes

Only start these after Section 5 passes:

- Add data-layer and registry-layer `canonical_asset_key` dedupe for same visual asset across `.webp/.png/.jpg/.gif`.
- Add BGE-M3 sparse as an additional sparse route and compare against BM25 with eval A/B.
- Enable `BAAI/bge-reranker-v2-m3` by default only after latency, rate-limit, and eval improvements are measured.
- Add query/action telemetry for future intent classifier training.
- Add visual captions and `asset_caption_bge_m3_v1` media vector retrieval.
- Add richer voice grouping by language, skin, and line category.
- Add Wiki route-resolve fields to sources after Wiki module resumes.

## 7. Deferred / Out of Scope

- BERT/RoBERTa/MacBERT intent classifier training.
- LangGraph multi-pass expansion loop.
- Multi-chain parallel answer composition.
- CDN, private bucket, signed URL, media center UI.
- Full Wiki module recovery.
- Obsidian rebuild from Huiji data.
- Git cleanup or commit workflow.

## 8. Completion Self-Check

Before declaring completion, check every item below:

- [ ] `DATA-P0-*`: Huiji processed artifacts are the active source; no local path leaks; abnormal entities are traceable.
- [ ] `BLOCK-P0-*`: intro uses entity packet; skills keep star variants together; omitted actions exist for trimmed sections.
- [ ] `QUERY-P0-*`: LLM-first planning and all fallback statuses are tested and visible.
- [ ] `RETR-P0-*`: structured exact, BM25, dense, RRF, reranker-before-expansion, and debug are tested.
- [ ] `MEDIA-P0-*`: media follows final sources; voice/video panel gating works; MinIO HTTP URLs are valid.
- [ ] `API-P0-*`: API/SSE returns sources, media, actions, planning diagnostics, and no local paths.
- [ ] `CHAT-P0-*`: chat UI renders Markdown-compatible/plain text, buttons, actions, image grid, voice panel, video panel.
- [ ] `EVAL-P0-*`: core query eval exists and produces a report for current v3.
- [ ] `MILVUS-P0-*`: v3 preserved; v1 rebuild only if gate conditions are met.
- [ ] `BOUNDARY-P0-*`: Wiki paused; Obsidian excluded from active RAG.
- [ ] P1 items are either completed after P0 or explicitly left unexecuted.
- [ ] P2 items did not enter implementation scope.
