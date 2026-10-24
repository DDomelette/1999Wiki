# 1999Wiki 真正 SSE 流式问答设计

## 1. 背景与现状

问答页当前已经使用 `POST /api/ask/stream` 和 SSE，但它并不是真正的模型流式输出：

1. `backend/sse.py::rag_stream_generator` 先同步调用 `chain.execute()`。
2. `RAGExecutionService` 完成检索、完整 LLM 调用、答案规范化、引用校验或修复后，才返回不可变的 `ResponsePacket`。
3. `response_packet_to_sse_events()` 再把已经完成的答案按 32 个字符切成多个 `token` 事件。

因此，浏览器在整个问答链结束前收不到正文。生产环境诊断中，首个 SSE 事件约在请求发出后 2.06 秒到达，`sources`、`token` 和 `done` 几乎同时出现。这种“事后切片”无法降低首字延迟，也无法准确展示问答正处在哪一阶段。

本设计将 `/ask/stream` 改为真正消费 DeepSeek 流式响应，同时继续复用现有检索、答案规范化、引用校验、媒体绑定、会话记忆和发布回滚机制。

## 2. 已确认的产品取舍

- 接受极少数情况下，已经流出的草稿会在引用校验后被最终答案整体校正一次。
- 前端显示一条由后端事件驱动的动态状态，不使用虚构进度或计时器推测：
  - 正在理解问题…
  - 正在检索资料…
  - 正在生成回答…
  - 正在校验引用…
  - 已完成引用校验并修正
- 检索到的来源和媒体元数据可以提前传到浏览器，但图片、音频、画廊和语音面板只在 `done` 后渲染。
- 先在隔离工作树本地迭代和预览；用户确认体验后再合并 `main`、构建镜像并部署，避免每次小改都发布镜像。

## 3. 目标

1. DeepSeek 返回首批文本后尽快在问答页显示，不等待完整答案和引用校验。
2. 用稳定、机器可读的 SSE 阶段事件告诉前端实际处理阶段。
3. 最终展示的答案仍以现有规范化和引用校验结果为准。
4. 多媒体在最终答案确认后一次性显现，避免流式期间布局反复重排或草稿引用与媒体错配。
5. 中止或断连时停止后续处理，不写入不完整会话记忆。
6. 保持同步 `/ask` 的外部行为和响应结构不变。
7. 保持现有 `/media/...`、MinIO、Caddy、Wiki 和 RAG 媒体链路不变。

## 4. 非目标

- 本轮不更换模型、向量库、重排器或提示词。
- 本轮不重做问答页视觉设计。
- 本轮不改变 COS 的备份定位，也不让服务器运行时依赖 COS。
- 本轮不修改 Wiki 图片加载链路。
- 本轮不在本地迭代阶段推送容器镜像或修改生产服务器。
- 本轮不保证模型供应商已经开始生成之前的检索阶段为零延迟；阶段提示负责让等待可感知，真正的正文首字优化从模型生成阶段开始。

## 5. 总体架构

### 5.1 拆分“准备、生成、定稿”

将当前一次性执行拆成三个可复用阶段，但不复制业务规则：

1. `prepare`
   - 解析问题和对话上下文。
   - 执行查询规划、检索、路由和媒体绑定。
   - 生成不可变的 `PreparedExecution`。
2. `generate`
   - 根据 `PreparedExecution` 构造与同步问答相同的消息。
   - 同步 `/ask` 仍可完整调用模型。
   - 流式 `/ask/stream` 使用模型异步流式接口并逐块产生文本。
3. `finalize`
   - 对累积草稿执行与现有实现相同的结构值、语音范围、媒体范围、证据限定、归因、答案范围和缺失意图规范化。
   - 执行现有引用校验或修复。
   - 生成唯一权威的 `ResponsePacket`。

`PreparedExecution` 至少保存：

- 原始执行请求与会话投影；
- 查询计划和路由决策；
- `sources`、`source_map`、`context` 和用于回答的 `answer_context`；
- `assets`、`media`、`media_panels`；
- 缺失意图、规划状态、警告、错误、被省略或失败的动作；
- 无检索结果、检索失败、自由补充、LLM 不可用等分支信息。

该对象冻结检索结果，使流式期间的来源和最终定稿基于同一份证据，防止先发出的来源与最终答案使用不同检索快照。

### 5.2 同步与流式入口共享领域逻辑

- `/ask`：`prepare → 完整模型调用 → finalize`。
- `/ask/stream`：`prepare → sources → 模型真流式 → finalize → done`。

两条入口共享相同的准备和定稿函数。现有同步接口不能通过调用 SSE 再拼接结果来实现，以免引入传输层依赖；SSE 也不能再次调用完整的 `execute()`，以免模型被调用两次。

### 5.3 异步边界

FastAPI 的 SSE 生成器不能在事件循环中直接运行现有同步检索和校验代码：

- `prepare` 和 `finalize` 通过 `asyncio.to_thread` 执行。
- DeepSeek 流式正文优先使用 LangChain 模型的 `astream(messages)`，由异步生成器直接消费。
- 为测试替身或不支持 `astream` 的兼容模型提供受控的同步 `stream(messages)` 适配器：工作线程写入有界异步队列，并监听取消标记。
- 不使用无界队列，避免慢客户端令 token 在服务器内存无限累积。
- 每个请求只执行一次模型生成。

## 6. SSE 协议

### 6.1 事件顺序

正常的有来源问答必须遵循：

```text
status(understanding)
status(retrieving)
[heartbeat...]
sources
status(generating)
token...
[heartbeat...]
status(validating)
[answer_replace]
[status(corrected)]
done
```

约束：

- `status`、`sources`、`token`、`answer_replace`、`done` 和 `error` 均使用命名 SSE 事件。
- `heartbeat` 使用 SSE 注释行，不进入前端业务回调，也不重复阶段文案。
- `done` 或 `error` 为终止事件；同一请求不能同时发送两者。
- `token` 必须在 `done` 前到达，不能在后端积攒完整答案后一次性批量发送。
- 不产生正文的合法分支，例如检索失败、无结果或 LLM 未配置，可以直接进入 `done`，但仍需发送与实际执行匹配的阶段。

### 6.2 `status`

```text
event: status
data: {"phase":"retrieving"}
```

稳定的 `phase` 枚举：

- `understanding`
- `retrieving`
- `generating`
- `validating`
- `corrected`
- `cancelled`
- `failed`

中文文案由前端按 `phase` 映射，不把展示文本固化为后端协议。正常请求只在阶段变化时发送一次。`corrected` 只在最终答案与已流出草稿不一致时发送。

### 6.3 `sources`

`sources` 沿用当前公开字段，包含：

- `sources`
- `assets`
- `media`
- `media_panels`
- 路由与规划元数据
- 被省略或失败的动作
- 当前会话记忆元数据
- 当前可用的 timing 快照

它不包含草稿答案。前端收到后保存这些数据，但设置为“待完成”，直到 `done` 才交给媒体组件渲染。

### 6.4 `token`

```text
event: token
data: {"token":"文本增量"}
```

- 内容必须是模型实际产生的增量，而不是服务端对完成答案的固定长度切片。
- 保留现有传输清洗，防止不可序列化值或异常字符破坏 SSE。
- 空增量不发送。
- 首个非空 token 到达时记录 `model_first_token` 和 `visible_first_token`，两者不得再由 `done` 伪造。

### 6.5 `answer_replace`

```text
event: answer_replace
data: {
  "answer":"校验后的完整答案",
  "reason":"citation_validation"
}
```

前端原子替换当前草稿，不逐字动画播放校正文本。允许的 `reason`：

- `citation_validation`：引用校验或答案规范化改变了草稿。
- `safe_fallback`：校验过程无法安全保留草稿，替换为安全失败说明。

仅当规范化后的最终答案与浏览器现有草稿不同才发送。随后如果属于正常引用校正，发送 `status(corrected)`。

### 6.6 `done`

`done` 沿用当前完整公开响应，并新增可选的兼容字段：

```json
{
  "answer": "最终权威答案",
  "corrected": true,
  "sources": [],
  "assets": [],
  "media": [],
  "media_panels": [],
  "timing": {}
}
```

- `answer` 永远是最终权威答案。
- `corrected` 表示是否发送过 `answer_replace`。
- 其他现有字段保持兼容。
- 前端以 `done.answer` 再做一次幂等收敛，防止网络分块、回调异常或未来客户端版本导致文本偏差。
- `done` 到达后才解除媒体渲染门禁并清除动态阶段提示。

### 6.7 `error`

```text
event: error
data: {
  "message":"面向用户的安全错误说明",
  "phase":"generating",
  "partial":true
}
```

- 不向浏览器泄露堆栈、密钥、内部地址或原始异常细节。
- 详细异常只进入服务器日志和追踪。
- `partial=true` 表示浏览器已收到部分草稿；该草稿必须明确标记为“未完成，未经过引用校验”，不能显示媒体，也不能写入记忆。

## 7. 后端状态与分支行为

### 7.1 正常有来源回答

1. 获取会话 lease。
2. 发出 `understanding`。
3. 发出 `retrieving`，在线程中执行 `prepare`。
4. 发出 `sources`。
5. 发出 `generating`，消费 DeepSeek 流式块并累积 `draft`。
6. 发出 `validating`，在线程中执行 `finalize`。
7. 如最终答案变化，发出 `answer_replace` 和 `corrected`。
8. 验证公开响应 schema，发出 `done`。
9. 仅当最终包可提交时构建完整会话轮次并释放 lease。

### 7.2 自由补充

自由补充分支也使用真正流式模型生成，`grounding_mode` 保持 `ungrounded`，随后运行适用于该分支的现有校验逻辑。它可以没有来源，但仍在 `done` 前隐藏媒体。

### 7.3 无需或不能调用模型的分支

检索失败、空检索且不允许自由补充、LLM 未配置等分支不会伪造 token。它们由 `prepare/finalize` 生成现有安全答案并直接 `done`，同时保留原有 `turn_outcome` 规则。

### 7.4 生成失败

- 首 token 前失败：发送 `status(failed)` 与终止 `error`。
- 已发送 token 后失败：保留当前草稿供用户查看，发送带 `partial=true` 的终止 `error`；界面标注未完成和未校验。
- 两种情况均不写会话记忆、不显示媒体。

### 7.5 校验失败

引用校验或定稿本身抛出异常时，不允许把未经校验的草稿当成最终答案：

1. 发送 `answer_replace(reason=safe_fallback)`，替换为安全失败说明。
2. 发送终止 `error`，供前端结束 loading 状态。
3. 不显示媒体，不写会话记忆。

### 7.6 客户端取消与断连

- 浏览器的 `AbortSignal` 取消读取。
- 服务端在长阶段之间及流式循环中检查 `request.is_disconnected()`。
- 断连后设置取消标记，关闭上游异步流或同步适配器，停止排队 token。
- 不再发送事件，不执行非必要定稿，不写会话记忆。
- 在 `finally` 中始终释放会话 lease；`completed_turn` 保持为空。
- 若上游网络库无法立即中断正在进行的单次阻塞读取，后台适配器也必须丢弃后续结果并在读取返回后退出，不能继续占用无界资源。

## 8. 心跳与代理传输

- 当 `prepare`、模型等待或 `finalize` 超过心跳间隔时，每 10 秒发送一次 SSE 注释：

```text
: heartbeat

```

- 心跳不改变前端阶段。
- 响应保持 `text/event-stream`、`Cache-Control: no-cache` 和禁止代理缓冲所需的响应头。
- Caddy 必须保持流式转发，不能为该路由聚合响应或缓存 SSE。
- 本地容器验收需要记录每个事件的到达时间，证明 `token` 在 `done` 和引用校验完成前抵达，而不是只检查最终页面看起来会逐字显示。

## 9. 前端状态设计

### 9.1 消息状态

助手消息增加或明确以下状态：

- `phase`：后端阶段枚举。
- `streaming`：请求是否尚未终止。
- `draft`/`content`：当前已流出的正文。
- `finalized`：是否收到 `done`。
- `corrected`：是否发生整体校正。
- `correctionNotice`：由真实 `corrected` 事件触发、完成后仍可短暂保留的校正提示。
- `pendingSources`、`pendingAssets`、`pendingMedia`、`pendingMediaPanels`：已收到但尚未开放渲染的数据。
- `partialError`：是否保留未校验的部分回答。

不要求把 `draft` 与 `content` 存成两份长期状态；实现可用现有 `content` 累积 token，只要 `answer_replace` 和 `done` 都能原子覆盖。

### 9.2 动态阶段文案

在正在回复的助手气泡中只显示一行动态状态：

| phase | 文案 |
| --- | --- |
| `understanding` | 正在理解问题… |
| `retrieving` | 正在检索资料… |
| `generating` | 正在生成回答… |
| `validating` | 正在校验引用… |
| `corrected` | 已完成引用校验并修正 |
| `cancelled` | 已停止生成 |
| `failed` | 回答生成失败 |

阶段行与正文可同时存在：收到首 token 后，正文开始显示，阶段仍可从“正在生成”切换到“正在校验”。`done` 后清除普通阶段行。

`corrected` 事件同时设置独立的 `correctionNotice`。该提示在 `done` 后保留约 2.5 秒再淡出，使紧邻到达的 `corrected` 和 `done` 不会被 React 批处理成不可见状态。计时器只负责隐藏一条已经由后端事实触发的提示，不能产生或推进任何处理阶段；`done`、最终正文和媒体渲染均不等待这 2.5 秒。

用户主动停止时，前端可以立即显示 `cancelled`，这是对本地用户动作的确认；服务端断连后无法再可靠地向已关闭连接发送状态。其余处理阶段必须由后端事件驱动。

### 9.3 媒体显示门禁

- `onSources` 只填充 pending 数据。
- token 流出期间不挂载媒体组件，不发起媒体请求。
- `onDone` 用最终数据覆盖 pending 数据并一次性开放渲染。
- `answer_replace` 只替换正文，不改变媒体集合。
- `error`、取消或断连时清空 pending 媒体。
- 现有图片、音频、画廊、Live2D、语音分页与 `/media/...` URL 处理不变。

该门禁保证真正流式输出不会破坏 RAG 当前正常工作的多媒体显示，也避免媒体请求与正文生成争抢首字带宽。

### 9.4 SSE 解析

前端解析器增加：

- `onStatus(phase)`
- `onAnswerReplace(answer, reason)`

解析器仍需支持任意网络分块：一个 SSE 事件可能被拆成多次 `read()`，多个事件也可能在一次读取中到达。心跳注释应忽略。收到终止事件后应停止接受后续业务事件。

## 10. 会话记忆一致性

- 只有 `done` 对应的最终 `ResponsePacket` 满足现有可提交条件时，才写入用户问题和最终答案。
- 已流出的草稿永不进入记忆。
- `answer_replace` 后写入的是校正答案。
- 失败、取消、断连和安全回退不提交轮次。
- 会话 lease 的获取与释放语义保持现状，所有退出路径必须释放。
- 同一会话的并发请求仍遵循现有内存存储并发策略，本轮不改变锁粒度。

## 11. 追踪与性能指标

保留现有 trace，并使时间点符合真实含义：

- `request_started`
- `retrieval_ready`
- `model_started`
- `model_first_token`
- `visible_first_token`
- `validated_ready`
- `completed`

补充或校准以下耗时：

- `time_to_first_status_ms`
- `time_to_sources_ms`
- `time_to_model_first_token_ms`
- `time_to_visible_first_token_ms`
- `validation_ms`
- `total_ms`

`visible_first_token` 只在首个非空 `token` 发出时记录；无 token 分支可为空，不能在 `done` 时伪造。追踪字段可以进入 `sources`/`done` 的 timing 快照，但内部异常和敏感配置不能进入公开响应。

## 12. 测试驱动实施范围

### 12.1 后端单元测试

先增加失败测试，再写实现：

1. `status → sources → generating → token → validating → done` 顺序。
2. token 来自模型真实流，不是对最终答案的 32 字切片。
3. 模型生成结束前已经可以取得首 token。
4. 无校正时不发送 `answer_replace` 或 `corrected`。
5. 引用修复改变答案时发送一次 `answer_replace`，且 `done.answer` 与替换内容一致。
6. 定稿安全回退不会把草稿当成最终答案。
7. 检索失败、无结果、LLM 未配置等分支不伪造 token。
8. 首 token 前和首 token 后的生成异常具有不同 `partial` 语义。
9. 客户端断连会关闭流、释放 lease 且不提交记忆。
10. 只在最终可提交答案上构建 `completed_turn`。
11. 长阶段会产生心跳注释，心跳不影响事件状态机。
12. transport sanitization 继续覆盖 token、替换答案和错误消息。
13. 同步 `/ask` 与流式 `done` 在同一固定检索/模型输入下得到等价公开结果。

### 12.2 前端单元与组件测试

1. SSE 解析器支持 `status`、`answer_replace`、心跳和跨 chunk 事件。
2. 状态文案按后端阶段变化，不使用本地虚构计时。
3. token 逐步追加，校正事件原子替换，`done` 幂等收敛。
4. 收到 `sources` 后媒体仍不渲染；只有 `done` 后渲染。
5. 图片、音频、画廊和语音面板在 `done` 后仍使用现有组件正常显示。
6. 取消和错误会清除 pending 媒体。
7. 部分生成失败保留草稿并显示“未完成，未经过引用校验”。
8. 发送新问题、清空会话或组件卸载会中止旧流，旧事件不能污染新消息。

### 12.3 集成与人工验收

- Python 相关 SSE、执行、记忆和 RAG 固定数据测试通过。
- React 全量测试、TypeScript 检查和生产构建通过。
- 本地后端和前端联调可见五个实际阶段。
- 记录本地 SSE 事件时间戳，确认首 token 明显早于 `validating`/`done`。
- 短答案和长答案均持续分块到达，不是结束时批量喷出。
- 验证无校正、引用校正、无结果、生成失败和主动停止。
- 验证回答完成后图片、音频、画廊、语音分页正常显示。
- 验证 token 生成期间浏览器不会提前请求待定媒体。
- Docker Compose 本地验证 Caddy 不缓冲 SSE。

## 13. 本地工作树与依赖约束

- 实施分支：`codex/true-sse-streaming`
- 隔离工作树：`D:\1999Wiki\.worktrees\codex\true-sse-streaming`
- 主工作区 `D:\1999Wiki` 保持可供其他迭代使用。
- 当前基线：
  - 前端 50 个测试文件、245 个测试通过。
  - 后端相关基线 70 个测试通过。
- Windows 直接安装完整 `requirements.txt` 会在 Linux 专用的 `uvloop==0.22.1` 处失败。开发测试沿用现有 Windows Python 环境；Linux/Docker 构建继续安装并使用 `uvloop`。实施若调整依赖声明，必须使用平台条件标记，而不是从服务器依赖中删除 `uvloop`。
- 当前 npm 审计已有 6 个与本功能无关的漏洞提示，本轮不夹带依赖升级。
- 主工作区中与本功能无关的未跟踪文档不得触碰或提交。

## 14. 本地预览、发布与回滚

### 14.1 本地迭代

1. 在隔离工作树完成测试驱动实施。
2. 运行后端、React 和 Docker 相关验证。
3. 启动本地预览，提供访问地址和验收问题。
4. 用户体验后可继续在同一工作树调整。
5. 未获最终确认前不合并 `main`、不推送发布镜像、不更改服务器。

### 14.2 最终发布

用户确认本地效果后：

1. 确认工作树干净、所有验证通过。
2. 将功能分支合并到 `main`。
3. 推送 GitHub。
4. 以合并提交生成唯一 `sha-<commit>` 前后端镜像。
5. 同步发布到 GHCR 和 TCR，服务器优先从 TCR 拉取。
6. 部署到当前非活动的 Blue 环境。
7. 通过健康检查、SSE 时间戳、问答、引用校正和多媒体冒烟测试后切流。
8. 保留当前 Green 镜像和容器作为即时回滚版本。

若新流式协议、前端体验或多媒体出现异常，直接切回 Green；回滚不依赖重新构建镜像。

## 15. 验收标准

本功能只有同时满足以下条件才算完成：

- 浏览器收到的是 DeepSeek 实际流式增量。
- 首个正文 token 在完整答案和引用校验之前可见。
- 阶段文案与后端真实阶段一致。
- 最终正文始终收敛到经过现有规范化和引用校验的答案。
- 发生校正时用户能看到轻量提示，且只整体替换一次。
- 多媒体只在 `done` 后显示，并保持图片、音频、画廊和语音功能正常。
- 中止、断连和失败不会提交不完整会话记忆。
- 同步 `/ask` 不发生兼容性回归。
- 本地测试、构建、Docker 流式验收全部通过。
- 用户完成本地预览并明确批准后，才进入合并与服务器发布。
