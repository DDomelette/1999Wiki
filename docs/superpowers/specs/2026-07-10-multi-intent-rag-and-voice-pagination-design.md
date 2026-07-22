# 多意图 RAG 检索与语音分页设计

日期：2026-07-10  
状态：待用户审阅  
依据：`docs/specs-and-plans-review-guide.md`

## 1. 背景与目标

当前灰机 RAG 已具备 `QueryPlan`、结构化召回、BM25、Dense、RRF、父子块扩展、媒体挂载和 SSE 输出，但运行时仍按单一 intent 组织检索。真实复现证明：一个同时请求技能和语音的角色问题会被压缩为 `voice`，最终 sources 可能全部来自 voice parent，完整存在的技能数据无法进入上下文。同时，明确语音意图会一次返回该角色 voice parent 下的全部媒体。该事故只用于说明根因，不作为角色名称、技能数量、台词数量或语言数量的固定验收样本。

本设计解决两个相互关联的 P0 问题：

- 一个问题显式包含多个角色 section intent 时，规划、召回、扩展、预算裁剪和媒体挂载必须共同消费全部 intent。
- 语音媒体必须按台词分组并分页，首个 RAG 响应不能一次传输角色的全部音频。

本设计不要求重建 parent/child artifacts，不要求重新向量化，不修改现有 Milvus collection，不修改 MinIO 或 Wiki 数据。

## 2. 总体架构

```mermaid
flowchart LR
    U["用户组合问题"] --> P["Stage 0: primary + secondary intents"]
    P --> B["Intent bundle 与策略合成"]
    B --> K["有上限的自适应候选 K"]
    K --> R["Structured + BM25 + Dense + RRF"]
    R --> A["分 intent source 配额分配"]
    A --> C["全局字符预算与 max sources"]
    C --> M["按最终 sources 挂载媒体类型并集"]
    M --> V["Voice lines 分组与首屏分页"]
    V --> S["SSE: sources + first voice page"]
    S --> F["VoicePanel 按需请求 next cursor"]
```

核心原则：候选 K、最终文本 sources 和媒体分页是三个独立预算。候选 K 可以根据 intent bundle 自适应；最终 sources 必须按 intent 保底并受字符预算约束；媒体数量由分组和分页控制，不反向扩大文本 K。

## 3. Stage 0 多意图规划

### 3.1 模块职责

Stage 0 从原始问题生成一个 primary intent 和零到多个 secondary intents，并保证后续模块可以得到稳定、有序、无重复的 intent bundle。

### 3.2 P0 当前必须满足

- `PLAN-P0-01`：显式并列的角色 section intent 必须全部识别。P0 至少覆盖 `profile_fact`、`skill`、`item`、`culture`、`voice`、`media`、`video` 的组合。
- `PLAN-P0-02`：primary intent 按用户问题中的首次出现顺序确定；其余 intent 按出现顺序进入 `secondary_intents`。
- `PLAN-P0-03`：`secondary_intents` 必须有序去重，且不得重复 primary intent。示例结果必须为 `intent="skill"`、`secondary_intents=("voice",)`。
- `PLAN-P0-04`：LLM 规划结果必须与显式关键词检测结果合并。LLM 不得通过返回单一 intent 删除用户明确表达的其他 intent。
- `PLAN-P0-05`：LLM 不可用、超时、解析失败或 schema 失败时，本地 fallback 必须生成相同的多意图契约。
- `PLAN-P0-06`：API 和检索 debug 必须暴露 `requested_intents`，其值由 `(intent, *secondary_intents)` 有序去重得到。
- `PLAN-P0-07`：现有标量 `media_intent` 只保留兼容含义，不得用于覆盖全部 intent 的媒体需求；媒体类型必须从完整 intent bundle 推导。

### 3.3 P1 可部分支持

- `PLAN-P1-01`：支持需要不同实体或不同 category 的复合问题拆分，例如同时查询角色和心相。
- `PLAN-P1-02`：为隐式多意图和省略主语问题增加置信度与澄清策略。

### 3.4 P2 未来演进

- `PLAN-P2-01`：使用训练后的 intent classifier 或行为数据优化隐式多意图识别。

### 3.5 关键契约与限制

`intent` 仍是 primary intent，`secondary_intents` 仍是兼容字段；不得再引入第二个可独立修改的 intent 真值列表。运行时通过统一 helper 生成 `requested_intents`，所有下游模块只能消费该 helper 的结果。

## 4. Packet Policy 合成与候选召回

### 4.1 模块职责

检索器把每个 requested intent 映射到现有 packet policy，合成所需 sections、source 配额和媒体类型。候选召回仍使用当前 artifacts 和 Milvus，不重新向量化。

### 4.2 P0 当前必须满足

- `RETR-P0-01`：检索器必须消费全部 `requested_intents`，不得只按 primary intent 调用一次 `get_packet_policy()`。
- `RETR-P0-02`：每个 intent 的结构化精确 section 候选必须独立加入候选池，并标记 `matched_intents`。
- `RETR-P0-03`：BM25 与 Dense 候选保持共享召回，RRF 和可选 reranker 在 source 配额分配前执行。
- `RETR-P0-04`：候选 K 必须由所需 source 配额计算，并设置硬上限。默认规则为 `candidate_k = min(100, max(configured_k, 4 * required_source_count))`。
- `RETR-P0-05`：动态 K 只能根据 intent bundle 和 source 配额计算，不得根据已挂载媒体数量二次扩张，不得形成“更多 sources -> 更多媒体 -> 再扩大 K”的反馈循环。
- `RETR-P0-06`：`skill` policy 使用 `all_available` coverage mode。只要全部精确技能子块与其他 intent 的最低配额能同时放入全局 source/字符预算，就必须保留全部技能子块；不得假设每个角色固定拥有 3 条或最多 4 条技能。
- `RETR-P0-07`：`voice` policy 为文本上下文保留最多 8 条不同 voice line；音频总数不占用 source 配额。
- `RETR-P0-08`：组合查询必须先满足各 intent 配额，再按融合分数填充剩余位置；最后才应用全局 `max_sources=20` 和字符预算。
- `RETR-P0-09`：不得对合成后的 sources 再执行无意图感知的 `sources[:top_k]`。最终裁剪必须由 source allocator 完成。
- `RETR-P0-10`：如果实际可用 section 少于配额，返回全部可用数据并记录 `coverage_shortfall`；不得用其他 intent 的重复 rows 伪装配额完成。
- `RETR-P0-11`：`omitted_actions` 只描述真实被预算裁剪的 section，不得把已经满足的 requested intent 生成为遗漏 action。
- `RETR-P0-12`：route debug 必须包含 requested intents、各 intent 候选数、配额、保留数、candidate K、字符使用量和 shortfall。

### 4.3 P1 可部分支持

- `RETR-P1-01`：根据真实评估报告调整不同 intent 的 oversampling 和 source 配额，但不得绕过 P0 上限。
- `RETR-P1-02`：对复杂组合问题执行 intent-specific Dense 子查询并比较共享召回的收益和成本。

### 4.4 P2 未来演进

- `RETR-P2-01`：根据线上反馈自动学习不同 intent 组合的预算参数。

### 4.5 关键契约与限制

动态 K 是候选召回预算，不是最终上下文长度，也不是媒体返回上限。现有 `context_budget_chars` 继续作为最终文本硬限制。预算不足导致任一 requested intent 完全缺失时，该查询不得通过 P0 评估。

## 5. 媒体类型合成与语音分页

### 5.1 模块职责

媒体 registry 只根据最终 sources 挂载媒体，并使用全部 requested intents 的媒体类型并集。语音媒体按 voice line 分组，每个 voice line 内包含现有语言版本。

### 5.2 P0 当前必须满足

- `MEDIA-P0-01`：允许媒体类型由全部 requested intents 取并集。`skill + voice` 不能被标量 `media_intent=audio` 收窄为只有 voice。
- `MEDIA-P0-02`：媒体继续只通过最终 source 的 `child_id` 或 `parent_id` 挂载，并保持同实体约束。
- `MEDIA-P0-03`：voice line 使用 `child_id` 作为稳定分组键；同一 child 下的 `zh/en/jp/kr` 等音频作为 variants 返回，缺少某种语言时只返回实际存在的 variant。只有至少存在一个可用 HTTP audio variant 的 child 才进入 playable voice line 集合；只有文本但没有可播放媒体的 voice child 仍可作为回答 source，但不生成空播放器行。
- `MEDIA-P0-04`：voice line 的默认标题优先使用中文 transcript，其次使用任一可用 transcript，最后回退到稳定文件标题。
- `MEDIA-P0-05`：语音顺序按 parent、voice line 数字序号和现有 sort order 稳定排序。
- `MEDIA-P0-06`：首屏默认返回 8 条 voice lines，服务端允许的 page size 范围为 1 到 20；首屏不得返回该角色全部 voice media。
- `MEDIA-P0-07`：第一页通过现有 Ask/SSE `media_panels` 返回；后续页通过只读 `GET /api/media/voice/page?cursor=<opaque>` 获取。
- `MEDIA-P0-08`：cursor 必须绑定 build version、实体、voice parent 和最后一条 voice line，不得包含本地路径、密钥或客户端可修改的裸 offset。
- `MEDIA-P0-09`：voice page response 必须返回 `lines`、`page_size`、`total_lines`、`has_more` 和 `next_cursor`；最后一页 `has_more=false`、`next_cursor=null`。
- `MEDIA-P0-10`：顶层 `media/assets` 和 voice panel 首次响应只包含当前页 variants，不能同时保留该角色完整 voice media 集合的副本。
- `MEDIA-P0-11`：分页接口只读当前已加载的 `media_assets.jsonl` 和 voice transcript 映射，不访问 Milvus、不修改 MinIO、不重新检索文本。
- `MEDIA-P0-12`：分页追加必须按 `voice_line_id` 和 `media_id` 去重；重复 cursor 请求必须返回相同结果。

### 5.3 P1 可部分支持

- `MEDIA-P1-01`：前端可预取下一页，但预取失败不得影响当前页播放。
- `MEDIA-P1-02`：支持用户默认语言偏好，只改变每条台词默认选中的 variant，不删除其他语言。

### 5.4 P2 未来演进

- `MEDIA-P2-01`：从可靠数据源补充 `voice_pack_id`、`skin_id`、皮肤名称和默认/皮肤语音包关系。
- `MEDIA-P2-02`：在完成语音包标注后提供皮肤筛选；未标注记录进入“未分类”，不得按文件名猜测皮肤业务语义。

### 5.5 关键契约与限制

P0 不提供皮肤筛选。当前 artifacts 的 voice `panel_group` 全部为 `default`，文件名不足以作为皮肤真值。P2 标注完成前，API 不得暴露伪造的皮肤分类。

建议 voice panel 类型契约：

```ts
interface VoiceLineGroup {
  voice_line_id: string
  title: string
  variants: MediaItem[]
}

interface VoicePanelPage {
  type: 'voice'
  grouping: 'voice_line'
  entity_id: string
  lines: VoiceLineGroup[]
  page_size: number
  total_lines: number
  has_more: boolean
  next_cursor: string | null
}
```

## 6. API、SSE 与聊天前端

### 6.1 模块职责

API/SSE 输出多意图诊断和语音首屏，聊天前端按 voice line 渲染，并按 cursor 追加后续页。

### 6.2 P0 当前必须满足

- `API-P0-01`：Ask 与 SSE route metadata 必须返回 `requested_intents` 和检索配额 debug，不泄露 prompt、密钥或本地路径。
- `API-P0-02`：新增只读 `GET /api/media/voice/page?cursor=<opaque>`；接口只接受服务端签发的 opaque cursor，非法 cursor 返回 400。
- `API-P0-03`：cursor 对应 build version 已变化时返回 409，并提示客户端从第一页重新加载。
- `API-P0-04`：分页 API 不调用 QueryPlanner、Retriever、LLM 或 embedding API。
- `CHAT-P0-01`：VoicePanel 按 voice line 显示一行，每行提供已有语言 variants 的切换控件和一个播放控件。
- `CHAT-P0-02`：默认优先选择 `zh`，不存在时按 `en`、`jp`、`kr`、其他语言顺序选择首个 variant。
- `CHAT-P0-03`：面板底部只有在 `has_more=true` 时显示“加载更多”命令；点击后追加下一页，不替换已加载台词。
- `CHAT-P0-04`：加载中禁止重复请求；分页失败显示局部重试，不删除已加载内容，不影响答案和 sources。
- `CHAT-P0-05`：切换语言或加载下一页前必须停止当前音频，继续保持同一时刻只播放一个音频。
- `CHAT-P0-06`：组件必须保持稳定高度约束和滚动区域，分页追加不能推动消息主体发生无界布局增长。
- `CHAT-P0-07`：MessageBubble 必须真正消费 `mediaPanels`。存在 voice panel 时，顶层 `media/assets` 中的兼容 voice items 不得再次渲染，首屏每个音频只能出现一次。

### 6.3 P1 可部分支持

- `API-P1-01`：支持语音台词标题搜索或直接跳转到指定 voice line。
- `CHAT-P1-01`：记忆用户语言偏好并跨消息复用。

### 6.4 P2 未来演进

- `CHAT-P2-01`：完成可靠标注后加入皮肤/语音包筛选控件。

### 6.5 关键契约与限制

分页是服务端分页，不得先把全部媒体放入 SSE 再由前端隐藏。前端不得通过解析文件名推断皮肤、角色或语言之外的业务语义。

## 7. 跨模块数据流

对于任意同时具有技能和语音数据的角色，P0 目标数据流为：

```text
原始问题
  -> intent="skill"
  -> secondary_intents=("voice",)
  -> requested_intents=("skill", "voice")
  -> 合成 sections=(skills, voice)
  -> 从 artifacts 计算 skill child 集合 S、voice text child 集合 T
  -> voice_text_target=P_text=min(configured_voice_page_size, |T|)
  -> required_source_count=|S|+P_text；若超过全局预算则由 allocator 记录 shortfall
  -> candidate_k=min(100, max(configured_k, 4*(|S|+P_text)))
  -> 结构化候选 + BM25 + Dense + RRF
  -> source allocator 在预算允许时保留全部 S + P_text 条不同 voice text sources
  -> 全局 max_sources 与字符预算
  -> 媒体类型并集包含 skill image 与 voice
  -> 媒体 registry 计算 playable voice line 集合 V 与 variant media 集合 M
  -> SSE 返回前 min(configured_voice_page_size, |V|) 条 playable lines 及其实际 variants
  -> 用户点击加载更多，分页 API 返回后续 line
```

## 8. 错误处理原则

- Stage 0 只识别出一个 intent 时，保持现有单 intent 行为，不构造虚假 secondary intent。
- 某个 requested intent 没有真实 section 时，返回 coverage shortfall 和对应恢复 action，不用其他 section 填充。
- 候选 K 达到硬上限后仍无法满足配额时，保留可用结果并让评估失败，不继续无限扩大。
- 单个音频 URL 不可用时，只标记该 variant 失败，不影响同 line 的其他语言、其他 lines、文本答案或 sources。
- cursor 非法、过期或与当前 build 不一致时，不回退到全量媒体响应。
- 任一响应不得出现 `D:\`、`C:\`、`file://`、`local_relpath` 或 MinIO 凭据。

## 9. 测试与硬验收方向

### 9.1 P0 自动化验证

- `EVAL-P0-01`：QueryPlan 单测覆盖 `技能和语音`、`单品和图片`、`文化、技能及语音`，验证顺序、去重和 fallback。
- `EVAL-P0-02`：policy 合成单测验证全部 requested intents 被消费，媒体类型取并集。
- `EVAL-P0-03`：candidate K 单测验证按配额增长、最大值为 100、与媒体记录数量无关。
- `EVAL-P0-04`：source allocator 单测验证配额先于全局分数和最终裁剪。
- `EVAL-P0-05`：语音 registry 单测验证 child_id 分组、语言 variants、稳定排序、分页和 cursor 幂等。
- `EVAL-P0-06`：API/SSE 单测验证首屏、next cursor、400 非法 cursor、409 build mismatch 和无本地路径。
- `EVAL-P0-07`：VoicePanel 测试验证语言切换、单音频播放、加载更多、去重、局部重试和稳定滚动区域。
- `EVAL-P0-08`：现有单 intent 核心评估必须保持通过，非 voice 问题不得自动返回 voice panel。
- `EVAL-P0-09`：真实数据 evaluator 必须从当前 artifacts 动态计算每个角色的 skill child IDs、voice text child IDs、playable voice line IDs、语言集合和 media IDs，禁止在测试代码中写死角色名、角色 ID 或预期数量。
- `EVAL-P0-10`：真实数据 evaluator 必须执行确定性的分层抽样，并在报告中输出本次样本实体及其动态预期值，确保失败能够复现。
- `EVAL-P0-11`：当 artifacts 中存在只有 voice 文本但缺少可播放媒体、或缺少某个 requested section 的角色时，evaluator 必须额外抽样至少一个此类角色，验证文本仍可回答且媒体/coverage shortfall 不被伪造数据填充。

### 9.2 P0 真实数据硬门槛

- `GATE-P0-01`：evaluator 从同时拥有 skill、voice text 和 playable voice media 的角色中生成样本集。样本数为 `min(8, eligible_character_count)`；必须覆盖 playable voice line 数量的低位、中位和高位样本，并在数据存在差异时覆盖不同 skill 数量与语言覆盖数量；其余名额按确定性分位点补齐。
- `GATE-P0-02`：每个抽样角色的真实组合问题都必须输出 `requested_intents=(skill, voice)`，不得因角色名或数据量不同退化为单 intent。
- `GATE-P0-03`：对每个抽样角色，evaluator 从 artifacts 得到 skill 集合 `S` 和 voice text 集合 `T`。当 `|S| + min(page_size, |T|)` 未超过全局 source/字符预算时，最终 sources 必须包含全部 `S` 和目标数量的不同 voice text sources；超过预算时必须保证两个 intent 均有覆盖并报告 shortfall。
- `GATE-P0-04`：对每个抽样角色，evaluator 从可用 HTTP audio media 得到 playable voice line 集合 `V`。首个 SSE voice panel 必须报告动态计算的 `total_lines=|V|`、配置 page size、正确的 `has_more`，且首屏 variants 必须精确等于首屏 playable lines 在 artifacts 中实际存在的 media IDs。
- `GATE-P0-05`：连续请求某个抽样角色的所有 cursor 后，返回的 voice line IDs 必须与 artifacts 中 `V` 完全相等，所有 variant media IDs 必须与该角色 playable voice media 集合完全相等；不得重复、遗漏或额外返回其他实体媒体。
- `GATE-P0-06`：每个抽样角色的技能图片和语音媒体允许类型必须同时存在于媒体策略；标量 `media_intent=audio` 不得删除 skill media。
- `GATE-P0-07`：整个实现不运行向量化，不重建 artifacts，不修改或清空 `text_child_bge_m3_v3`，实施前后 collection 行数和 schema 不变。
- `GATE-P0-08`：抽样角色必须完成真实 Ask/SSE、后续分页 API 和 React VoicePanel 的端到端验收，不能只用单个角色或 mock 测试宣称完成。
- `GATE-P0-09`：如果当前 artifacts 存在缺 section 或 voice media 不完整的角色，至少一个异常样本必须验证正确 shortfall：不得生成空播放行，不得拉取其他实体媒体，不得把缺失数据报告为完整覆盖。

## 10. 与旧方案和其他线程的关系

本设计扩展现有 character packet routing，不替换 RRF、reranker、Milvus schema 或媒体 source 绑定规则。它明确废止以下运行时行为：

- 用单一 `_strong_intent_from_query()` 覆盖显式并列 intent。
- `secondary_intents` 只写入 QueryPlan 但不参与检索。
- 只使用 primary intent 获取一个 packet policy。
- 合成结果完成后再执行无意图感知的 `sources[:top_k]`。
- 明确语音 intent 时一次返回 voice parent 下全部音频。

实现时必须以开始执行时的工作区现状为准。若其他线程已修改 `query_plan.py`、`packet_policy.py`、`retriever.py`、`layered_expansion.py`、`huiji_registry.py` 或前端媒体类型，应在同一接口契约下合并，不得覆盖或回退对方已完成的改动。

后续 implementation plan 只能包含本 spec 的 P0 条目。根据本轮用户约束，plan 不得创建任何 P1 可选任务；P1 与 P2 只能在 Deferred / Out of Scope 中引用，尤其不得提前实现皮肤筛选或根据文件名猜测皮肤语音包。
